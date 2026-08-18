# The Life of a Token — prompt → next token, first principles
`LAST_UPDATED: 2026-08-16` · Status: core page · All [E] numbers verified in Python;
this page was adversarially reviewed by an independent LLM evaluator in a prior
investigation and revised (5 confirmed errors fixed, 3 claims refuted against the
evaluator).

Classification key: **[F]** established fact (paper/doc/spec) · **[A]** engineering
assumption · **[I]** inference · **[E]** verified empirically in this environment.

## 30-Second Explanation
A prompt becomes integer token IDs → embedding lookups → L transformer layers (attention +
FFN) → a distribution over the vocabulary → a sampled token. That happens once for the
whole prompt (**prefill**, compute-bound, parallel) and then once per generated token
(**decode**, bandwidth-bound, one token at a time). The KV cache is the bridge between the
two and the dominant constraint on concurrency.

## Why This Exists
Autoregressive LMs cannot compute position t without positions < t. Serving must therefore
answer: how do we make "compute the whole prompt fast" (TTFT) and "compute one token at a
time fast" (ITL / tok-per-s) both affordable on bandwidth-limited GPUs? Every major
inference innovation (batching, GQA, PagedAttention, FlashAttention, prefix caching,
quantization) is an answer to one of those two questions.

## Problem It Solves
Turning a trained next-token model into a fast, concurrent, memory-bounded service.

## First-Principles Explanation

### Stage 0 — The master switch: PREFILL vs DECODE
- **PREFILL** = process the S prompt tokens in **one parallel pass** → hidden states for
  all S positions + fill the KV cache. Cost O(2·N·S) FLOPs, dense GEMMs [S,d]×[d,d] →
  **compute-bound** [F: scaling literature].
- **DECODE** = generate one token per step; each step reads the full prior KV. Cost
  O(2·N) FLOPs/step; GEMMs degenerate to GEMVs [1,d]×[d,d] → **memory-bandwidth-bound** [I:
  roofline-derived, see `Roofline.md`].

### Stage 1 — Prompt → Tokenization (CPU)
WHY: models consume integer token IDs, not bytes. WHAT: BPE/SentencePiece merges →
`ids int32 [S]` (toy: [4]). PERFORMANCE: microseconds, CPU-bound, negligible. DATA: host
RAM → tokenizer. BOTTLENECK: none. [F: standard in Qwen/Llama/GPT]

### Stage 2 — Embedding (GPU, row lookup)
WHY: map IDs → dense vectors. WHAT: `X = E[:,ids]`, table `E [V, d]`. TENSOR: `X [S, d]`
(toy [4,6]). DATA: gather S rows of d·bytes. BOTTLENECK: none per use, but the table is
V=150k, d=4096, BF16 → 150,000×4096×2 B = 614M params ≈ **1.23 GB (≈1.14 GiB)** resident
in HBM [E]. Often **tied** to `lm_head`. [F]

### Stage 3 — L transformer layers (the "thinking")
WHY: L residual blocks where representations are transformed. WHAT (pre-norm, modern
default [F: LLaMA]):
```
x' = x + Attention( RMSNorm(x) )
y  = x' + FFN( RMSNorm(x') )
```
TENSOR: residual `[S, d]` throughout. PERFORMANCE: L sequential passes → latency ∝ L
(32 layers = 32 serial "waves"). DATA: each layer streams ~⅔ of N in weights + S·d
activations. BOTTLENECK: at decode, weight streaming (see roofline). [I]

### Stage 4 — Q/K/V projection (the math)
```
Q = X·Wq      K = X·Wk      V = X·Wv      Wq,Wk,Wv ∈ R^(d × h·d_h)
Q,K,V ∈ R^(S × h·d_h)  → reshape [S, h, d_h]
```
WHY: each position gets (a) what it looks **for** (Q), (b) what it can be found **by**
(K), (c) the information it **carries** (V). WHAT: 3 GEMMs. Prefill: dense,
compute-bound. Decode: GEMVs, bandwidth-bound. Per-token linear FLOPs ≈
3d²(QKV) + d²(out-proj) + ~8.1d²(SwiGLU MLP) = ~12.1d² → **QKV ≈ 25% of a layer's
linear FLOPs** [E].

### Stage 5 — Attention
```
Attention(Q,K,V) = softmax( Q·Kᵀ / √d_h ) · V      (per head)
```
- `Q·Kᵀ`: `[d_h, S]×[S, d_h]` → `[S,S]` per head, O(S²·d_h); **and** `×V` costs the same
  → **4·S²·d_h FLOPs per head** [F].
- **Why √d_h:** with q,k ~ N(0,1), Var(q·k) ≈ d_h; unscaled scores grow with d_h →
  softmax saturates to near one-hot. Scaling keeps variance ≈1 [F: Vaswani 2017].
- **Causal mask:** score[i,j] = −∞ for j>i → lower-triangular; this is what makes
  generation autoregressive (position i sees only ≤i) [F].
- **FlashAttention removes the S×S HBM materialization** (`Attention/README.md` §4).
  At S=32k, h=64, the S×S score matrix ×h×2B = 128 GiB — why it exists [E].
- Prefill: dense S×S → compute-bound. Decode: `[1,d_h]×[d_h,L_ctx]` GEMVs against the KV
  cache → bandwidth-bound, cost grows with context [I].

### Stage 6 — KV-cache creation
WHY: step t needs all prior K,V; recomputing would be O(S²) per token. The cache makes it
O(1) append + O(S) read. WHAT: append each token's K,V row (all S at prefill; 1/step at
decode). TENSOR: `K, V: [L, B, h_kv, d_h, S]` (paged in vLLM/SGLang). **The governing
formula:**
```
KV bytes = 2 · L · B · h_kv · d_h · S · b        (b: 2=BF16, 1=FP8/INT8)
```
EXAMPLE [E, Python-verified]: L=32, h_kv=8 (GQA), d_h=128, S=8192, b=2, B=1 →
**1,073,741,824 B = 1.0 GiB**; at S=128k → **16 GiB for one sequence**. DATA: written
once, **read every decode step for every active sequence** → caps concurrency.
BOTTLENECK: HBM capacity + decode bandwidth.

### Stage 7 — FFN/MLP
WHY: position-wise feature transform; where most parameters live. WHAT: SwiGLU
`H1=X·W1; H2=X·W2; Y = (silu(H1)·H2)·W3`, d_ff ≈ 2.7d. TENSOR: `H [S, d_ff]`. ~50–70% of
per-layer params. [I: e.g. Llama-3-8B d_ff=14336 vs d=4096]. Same compute/bandwidth split
as QKV.

### Stage 8 — Output norm + Logits
WHY: a distribution over the vocabulary, for the **last** position only in serving.
WHAT: RMSNorm on `h_last [1, d]` → `Z = h_last · W_embᵀ [1, V]`. COMPUTE: computing all
S positions would be an S·V GEMM (8192×150k×2B = **2.46 GB ≈ 2.3 GiB** of scores — why
serving skips it) [E: arithmetic; F: standard practice]. BOTTLENECK: O(V) matvec, trivial.

### Stage 9 — Sampling
WHY: turn logits into a token. WHAT: temperature → top-k / top-p / min-p filter →
softmax → sample (greedy if T=0). TENSOR: `probs [1, V]`. BOTTLENECK: **kernel-launch
overhead**, not the O(V) math [F: vLLM sampling design; I].

### Stage 10 — Decode loop → next token
WHY: autoregressive — token t+1 needs h_t. WHAT: sampled id → embedding → the full L-layer
stack again with S=1; attention reads all L_ctx KV rows; append new K,V row.
`ITL ≈ bytes_per_step / effective_BW + overheads` [I]. Repeat until EOS / max_tokens.

## PREFILL vs DECODE — side-by-side
| Aspect | Prefill | Decode |
|---|---|---|
| Tokens/step | S (parallel) | 1 |
| GEMM shape | [S,d]×[d,d] dense | [B,d]×[d,d], B small |
| Arithmetic intensity | ≈ d/b (≈2048 @ d=4096, BF16) | ≈ 2B·d/(2B·b+d·b_w) (B=1 → ~1) |
| Regime | **compute-bound** | **bandwidth-bound** |
| Dominant metric | **TTFT** | **ITL** |
| Attention | O(S²) dense, tensor-core happy | GEMV vs KV, O(L_ctx) |
| KV cache | written (big burst) | read every step (grows) |
| SM utilization | high, near peak | low (single-digit % of peak) [I/A] |
| HBM traffic | weights once + S×d activations + S² scores | **ALL weights + ALL KV, every token** |

## Hand-Calculable Example (all [E]-verified)
Toy: L=2, d=6, h=2, d_h=3, V=10, d_ff=12, S=4, BF16.
- `ids [4] → X [4,6]`; per layer Q,K,V `[4,6]→[4,2,3]`; scores `[4,4]` (causal: 6/16 live)
- FLOPs (2MNK/GEMM): QKV 3×(2·4·6·6)=**864**; Attn 2 heads ×(QKᵀ 2·4·4·3 + ×V 2·4·4·3)
  = 2×(96+96) = **384**; out-proj 2·4·6·6=**288**; SwiGLU 3×(2·4·12·6)=**1728** →
  **3,264/layer**; ×2 = 6,528; + logits 2·1·6·10=**120** → **≈6,648 FLOPs** for the 4
  cached tokens; each decode step re-reads the same weights.
- **Scale-up (27B, S=8192)** [E]: Prefill 2·N·S = **4.42e14 ≈ 442 TFLOP** ·
  Decode/token 2·N = **54 GFLOP** · Weights **BF16 50.3 GiB / NVFP4 ≈ 14.1 GiB**
  (NVFP4 counts ~4.5 bit/param including per-block scale overhead; pure 4-bit
  would be 12.6 GiB) ·
  KV@8192 **1.0 GiB** (@128k **16 GiB**) · Attention share of prefill @8192
  (d=4096, 32 layers) ≈ **8%** (grows ~S²).

## Impact on Training
Training is the same math with gradients: 2× the FLOPs (forward+backward ≈ 3× forward in
practice), and it is almost always compute-bound — the roofline regime is the opposite of
decode [I].

## Performance Implications
- **TTFT** ≈ queue + prefill ≈ queue + (2·N·S)/achieved_compute + attention overhead.
  Levers: prefix cache (skip work), FlashAttention, chunked prefill, FP4/FP8 weights.
- **ITL** ≈ (weight_bytes + KV_bytes)/effective_BW + kernel overheads. Levers: GQA/MQA,
  KV-quant, batching, paged + continuous batching, weight-quant.
- **Throughput** = B · decode_rate, rising with B toward the compute ridge; prefill
  interference (continuous batching) sets the real operating point.
- **KV consumption** = `2·L·B·h_kv·d_h·S·b` — the master constraint on
  concurrency × context.
Full metric glossary: `Inference/Inference-Metrics.md`.

## Advantages / Limitations
- This is a **single-GPU mental model**. Multi-GPU adds TP/PP/EP communication
  (`Distributed-Inference/README.md`), and disaggregated serving splits prefill/decode
  across machines (`Inference/Prefill-Decode-Disaggregation.md`).
- "Low SM utilization at decode" is an inference from the roofline, not a universal
  measurement [I].

## Important Research
Vaswani et al. 2017 (MHA, √d, causal) [F: arXiv:1706.03762] · Dao et al. 2022/2023/2024
(FlashAttention 1/2/3) [F] · Kwon et al. 2023 SOSP (PagedAttention/vLLM) [F] ·
Shazeer 2019 (MQA) [F: arXiv:1911.06145] · Ainslie et al. 2023 (GQA) [F: arXiv:2305.13245] ·
Williams/Waterman/Patterson 2009 (roofline) [F] · Pope et al. 2022 (scaling) [F] ·
Zheng et al. 2024 (SGLang/RadixAttention) [F: arXiv:2312.07104] ·
Leviathan et al. 2023 (speculative decoding, arXiv:2211.17192) [F] ·
Yu et al. 2022 OSDI (Orca, iteration-level scheduling, arXiv:2211.06863) [F].

## Related Topics
`Transformer/README.md` · `Inference/Roofline.md` · `Inference/Inference-Optimization.md` · `KV-Cache/README.md` ·
`Inference/Continuous-Batching.md` · `Attention/README.md`

## Key Takeaways
1. One token's life = tokenize → embed → L×(attention+FFN) → last-position logits → sample.
2. Prefill (compute roof) and decode (memory roof) are different problems wearing the same
   model.
3. The KV formula `2·L·B·h_kv·d_h·S·b` is the single most important budget equation in
   serving.
4. Every serving optimization targets either prefill work or decode bytes.

## References
See "Important Research". Numbers: [E] Python-verified (reproducible via `Labs/Lab-2`).
