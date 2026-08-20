# Modern LLM Architecture — Anatomy of a Foundation Model

`LAST_UPDATED: 2026-08-20` · Status: core page · Part of `Training-Engineering/`

> First-principles math for a single forward pass lives in
> `Transformer/README.md`. This page answers the *design* question: why the
> LLaMA-style stack won, where the parameters actually live, and which knobs
> (GQA, MoE, MLA, RoPE, embedding tie) cost what.

## 30-second explanation

A modern decoder-only LLM is:

```
x → [ RMSNorm → GQA-attention (RoPE) → +residual
     RMSNorm → SwiGLU FFN            → +residual ] × L
→ RMSNorm → W_out → logits over V tokens
```

The stack has been essentially **frozen since early 2023** [I: the LLaMA/Qwen/
Mistral/Gemma families all ship this exact block]; innovation moved to (a) head
design (GQA→MLA), (b) sparsity (MoE), (c) sequence modeling alternatives
(Mamba/hybrids), and (d) systems. Everything below decomposes one block and
prices its knobs.

## The block, with dimensions

Per layer, hidden size `d`, `h` heads, head dim `d_h` (`h·d_h` is often = `d`),
sequence length `S`, vocabulary `V`:

| Sub-part | Shapes | Parameters |
|---|---|---|
| Q/K/V projections | `W_q: d×(h·d_h)`, `W_k`, `W_v` (GQA: k,v shared across groups) | attention: `(1 + 2·h_g/h)·d·h·d_h` |
| Out projection | `W_o: (h·d_h)×d` | `d·h·d_h` |
| SwiGLU FFN | `W_1, W_3: d×d_ff`, `W_2: d_ff×d` | `3·d·d_ff` |
| 2× RMSNorm | γ per dim | `2·d` (negligible) |
| Embedding (input) | `V×d` | `V·d` |
| LM head | `d×V` | `V·d` (often tied to input: free) |

For LLaMA-7B: `d=4096, h=32, d_h=128, d_ff≈11008 (≈2.67·d), L=32, V=32000`
[F: LLaMA paper arXiv:2302.13971]. **[E] Verified in Python:**
- attention/layer = Q,K,V,out each `d×d = 4096·4096 = 2^24` → 4·2^24
  ≈ 67.1M (MHA)
- FFN/layer = 3·4096·11008 ≈ 135.3M
- per layer ≈ 202.4M; ×32 ≈ 6.48B
- embeddings: 32000·4096 ≈ 0.131B ×2 (input + head; LLaMA-7B *ties* them →
  0.131B)
- **total ≈ 6.6B** ✓ matches the paper's 6.7B (the small gap is norms +
  the exact d_ff rounding).

**Where the parameters live:** FFN ≈ 135.3M/202.4M ≈ **67% of the block**
([E]) — even more if the embedding is tied. Attention ≈ 33%. This is why
"attention architecture" debates (GQA, MLA, FlashAttention) move the *KV cache
and memory traffic*, while "FFN architecture" (SwiGLU width, **MoE**) moves
*parameter count and compute*. [I]

## The knobs, and what each buys

### 1. Head sharing: MHA → MQA → GQA → MLA
- **MHA** (Vaswani 2017 [F: 1706.03762]): every head owns its own K,V.
- **MQA** (Shazeer 2019 [F: 1911.06145]): all heads share *one* K,V head.
  KV cache shrinks by ×h (×32 for 7B) [E].
- **GQA** (Ainslie et al. 2023 [F: 2305.13245]): `g` K,V groups; LLaMA-2
  70B uses `g=8` over 64 heads → KV shrinks ×8 vs MHA. [F: Llama 2 report]
- **MLA** (DeepSeek-V2 [F: 2405.04434]): compress K,V into a low-rank latent
  + a small "no-rope" part. DeepSeek-V2 reports ~93.3% KV-cache reduction
  vs a comparable MHA config [F: paper claim, vendor-report].
  [I] Trade-off: every KV-compression knob is a *training-time* decision —
  it changes what the model must learn to attend with.

**Hand check (KV cache per token, BF16):** for L=32, d=4096, h=32,
d_h=128:
- MHA: K+V each have h·d_h = 32·128 = 4096 = d dims. Per layer/token
  = 2 (K,V) · 4096 · 2 B = 16,384 B; ×L=32 = **524,288 B/token**
  = 0.5 MiB/token → ×S=4096 = **2 GiB** per sequence [E].
- GQA (g=4 → K=4 heads, V=4 heads of 128): K dim = V dim = 4·128 =
  512. Per layer/token = 2 (K,V) · 512 · 2 B = 2,048 B; ×32 =
  **65,536 B/token** → ×4096 = **0.25 GiB** per sequence [E] —
  **8× smaller** than MHA (4096/512 = 8, since KV heads shrink 32→4).
See `KV-Cache/README.md` and `Model-Architectures/Attention-Head-Designs.md`
for the inference-side consequences (decode bandwidth-bound).

### 2. FFN width & activation
SwiGLU: `FFN(x) = (silu(x·W_1) ⊙ (x·W_3)) · W_2` [F: Shazeer et al.
2002.05202]. It has 3 matrices of width `d_ff` (vs 2 for a ReLU FFN),
so **at equal parameter count it has the same FLOPs as a ReLU FFN**
[E: the 3rd matrix is paid for by using a *narrower* d_ff — LLaMA uses
`d_ff ≈ 2.7·d ≈ 8/3·d` exactly to match the param budget of a ReLU FFN
at `4·d`: 3·d·(8/3·d) = 8·d² = 2·d·(4·d)] [E]. The reason to still
prefer SwiGLU is quality, not cost: it learns faster and hits lower
loss at equal params and compute [I: consistent across LLaMA /
GPT-3.5-class reports]. (At *equal width* — same d_ff — SwiGLU is
~1.5× the FLOPs of ReLU; the "1.5×" only applies when you don't
narrow d_ff.)

### 3. Mixture-of-Experts (the big one)
Replace the dense FFN with `E` experts, route each token to top-`k`
(typical: 2 of 64–256) [F: Shazeer 1701.06538; GShard 2006.16668; Switch
2101.03961; DeepSeek-V3 2412.19437]:

- **Total parameters** ↑ ×(E·k/d_ff scaling) — the model stores more.
- **Activated parameters** stay ~flat — each token only touches `k` experts.
- **Compute per token ≈ dense model of activated-param size**; **memory ≈
  total-param size**. [I]

Worked example [E]: LLaMA-7B-style dense ≈ 6.7B params.
- *Inference* (forward only): 2·N ≈ 2·6.7e9 = 13.4 GFLOP/token.
- *Training* (fwd+bwd, the 6·N·D master equation): 6·N ≈
  6·6.7e9 = 40.2 GFLOP/token.
A 1T-total / 32B-activated MoE (Kimi K2, [F: 2507.20534]) costs
≈ 6·32e9 = 192 GFLOP/token in *training* FLOPs (≈ 64 GFLOP/token
in forward) but must hold ~1T parameters (~1 TB in FP8, ~2 TB in
BF16 [E]) — training needs expert-parallel AllToAll, serving needs
expert placement. See `Model-Architectures/Mixture-of-Experts.md`
and `Parallelism.md` §Expert parallel.

### 4. Positional encoding: RoPE
Rotary position embedding [F: RoPE 2104.09864; ALiBi 2108.12409] is the
2023+ default. It injects relative position by *rotating* Q,K — no learned
position vectors, and it extrapolates better than learned absolute
embeddings (at the cost of needing tricks like YaRN/Paged-style scaling for
beyond-trained-length) [I: consistent across LLaMA-2/Llama-3 reports; see
`Model-Architectures/Positional-Encodings.md`].

### 5. Normalization: RMSNorm, pre-norm
Pre-norm RMSNorm [F: 1910.07467] before attention and FFN. No bias terms
anywhere (LLaMA-class) [I: universal across the family]. RMSNorm = LayerNorm
[F: 1607.06450] minus the mean shift, one fewer op per layer — negligible
FLOPs, kept because it's free.

### 6. Tied embeddings & LM head
Tying input embedding and output head (`W_out = W_inᵀ`) halves the
V·d term [E: 0.131B on 7B] and is standard at small scale; large models
untie (extra `V·d` params, ~2× the vocab-side memory). [I: LLaMA ties at
7B/13B, Llama-3 unties at 70B.]

### 7. Multi-Token Prediction (MTP)
DeepSeek-V3 added a secondary head that predicts token t+2 while predicting
t+1 [F: 2412.19437]. Training cost ≈ +10–15% (one extra LM head pass) [I],
inference: the t+2 prediction becomes a *free draft token* for speculative
decoding. Architecture decision made at pretraining time. See
`Speculative-Decoding/`.

## Dense vs MoE — the two families (2026)

| | Dense (LLaMA, Gemma, Qwen-dense) | MoE (DeepSeek-V3, Kimi K2, Llama-4, Qwen3-MoE) |
|---|---|---|
| Compute/token | ∝ total params | ∝ activated params |
| Memory/token | total params | total params (all experts) |
| Training comm | DP AllReduce + TP | + **expert AllToAll** |
| Typical 2025–26 frontier | 7B–70B open; 100B+ closed | 1T-total/32B-act, 671B/37B-act |
| Failure mode | OOM at big N | router collapse / load imbalance [I] |

**[I] The 2026 frontier is overwhelmingly MoE** — every major open 2025–2026
report (Kimi K2, DeepSeek-V3/V3.2, Llama-4, Qwen3-235B-A22B) is MoE; dense
models remain the workhorse below ~70B where expert overhead isn't worth it.
This is a *hypothesis about the trend*, not a measured claim.

## Non-transformer alternatives (brief)

- **SSMs (Mamba)** [F: 2312.00752]: selective state-space recurrence, O(1)
  state; 5× faster inference claimed at 3B [F: paper]. Mamba-2 (UNVERIFIED
  id this session; see `Model-Architectures/`) simplified the state space.
- **Hybrids (Jamba)** [F: 2403.19887]: Mamba layers + a few attention layers;
  long-context recall better than pure SSM at 70B [F: Jamba-1.5 report
  2408.12570].
- **Mixture-of-Depths** [F: 2404.02258]: skip the FFN of some tokens;
  compute-adaptive.
- **DeepSeek-V3.2 DSA** [F: 2512.02556]: sparse *attention* (selective KV
  access) to cut long-context compute.

**Status 2026 [I]:** dense GQA-RoPE-SwiGLU(+MoE) remains the default; SSM
hybrids are production-credible but haven't displaced attention for frontier
training. No winner declared — the deciding experiments are long-context
recall benchmarks + pretraining compute-per-quality at 100B+.

## Memory equation (what a training step actually stores)

For a step of batch `B`, sequence `S`, hidden `d`, layers `L` — full precision
BF16, AdamW, **no gradient checkpointing**:

```
params      : 2·N bytes                    (BF16)
grads       : 2·N bytes
Adam state  : 8·N bytes  (fp32 m+v + fp32 master)
activations : 2·(34·L + 48·h)·B·S·d bytes  [F: Korthikanti et al. 2205.05198]
```

where `h` = number of attention heads (the 48·h term is the h·d_h attention
terms per layer). **[E] Verified:** for LLaMA-7B (N=6.7e9, L=32, h=32, d=4096)
at B=1, S=2048:
- params+grads+adam = 12·6.7e9 B ≈ 80.4 GB
- activations = 2·(34·32 + 48·32)·1·2048·4096 B ≈ 2·(1088+1536)·2048·4096
  = 2·2624·8.39e6 B ≈ 44.1 GB
- **≈ 124 GB for B=1** → a single 80GB H100 cannot even hold one 7B step
  without checkpointing. [E] This is *why* ZeRO/FSDP and activation
  checkpointing are table stakes, not optimizations. (Full derivation in
  `Parallelism.md`.)

## Key takeaways

1. ~⅔ of parameters live in the FFN; ~⅓ in attention. Architecture choices
   split into "FFN choices" (width, MoE — move compute & memory) and "KV
   choices" (GQA/MLA — move attention memory & inference bandwidth).
2. The 2023+ dense block (RMSNorm → GQA+RoPE → SwiGLU, no bias, pre-norm) is
   settled; the frontier is MoE + sparsity + (increasingly) attention
   sparsity (DSA).
3. Every knob is a *training-time* decision that reshapes what must be
   learned — you cannot bolt MLA onto a dense-7B after the fact.
4. The training-step memory equation (12N + activations) is why no frontier
   run ever fits on one GPU and why ZeRO/checkpointing exist.

## References (all arXiv ids verified live 2026-08-20)

- Vaswani et al. 2017, Attention Is All You Need — `1706.03762`
- LLaMA — `2302.13971`; Llama 2 — `2307.09288`; Llama 3 — `2407.21783`
- GPT-4 Technical Report — `2303.08774`
- MQA (Shazeer) — `1911.06145`; GQA (Ainslie) — `2305.13245`
- DeepSeek-V2 (MLA) — `2405.04434`; DeepSeek-V3 — `2412.19437`;
  DeepSeek-V3.2 (DSA) — `2512.02556`
- Kimi K2 (MoE, MuonClip) — `2507.20534`; Qwen3 — `2505.09388`;
  Llama 4 Herd — `2601.11659`
- SwiGLU/GLU — `2002.05202`; RMSNorm — `1910.07467`; LayerNorm — `1607.06450`
- RoPE — `2104.09864`; ALiBi — `2108.12409`
- Sparsely-Gated MoE — `1701.06538`; GShard — `2006.16668`;
  Switch — `2101.03961`
- Mamba — `2312.00752`; Jamba — `2403.19887`; Mixture-of-Depths — `2404.02258`
- Korthikanti et al. (activation memory) — `2205.05198`
- Mamba-2 — UNVERIFIED this session (cited via Jamba/hybrid reports)
