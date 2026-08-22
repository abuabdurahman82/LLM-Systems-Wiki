# FlashAttention — Exact Attention, Reorganized for IO

`LAST_UPDATED: 2026-08-21 · Status: core page` · All [E] arithmetic verified in Python
this session; citation ids cross-checked against the verified arXiv bank.

## 30-Second Explanation
Standard attention computes `softmax(QKᵀ/√d_h)·V` by first writing an **S×S score matrix
to HBM**, then an **S×S probability matrix to HBM**, per head. At S=32k, h=64, BF16 the
score matrix alone is **128 GiB** — more than an 80 GB GPU holds, before the probability
matrix, weights, or KV cache [E, Worked Example 1]. **FlashAttention is an IO-aware
algorithm, not a faster approximation.** It computes the *identical* exact softmax
attention — same FLOPs, same numbers — but tiles Q, K, V into blocks that fit in SRAM
(shared memory), so the S×S matrix is **never materialized in HBM**. Only the output O
and small running statistics (m_i, l_i) touch HBM. The win is HBM *traffic* and *capacity*,
never arithmetic [F: arXiv:2205.14135]. In the `../Attention/README.md` taxonomy this is
**class B — a kernel change: same math, better IO**.

## Standard Attention: the Math and Its Hidden HBM Cost

```
Attention(Q,K,V) = softmax( QKᵀ / √d_h ) · V        (per head)
Q, K, V ∈ R^(S × d_h)
```

### Naive implementation, step by step
What a standard `nn.MultiheadAttention`-style kernel actually does, per head:

1. **Scores:** `S = Q·Kᵀ / √d_h` — GEMM `[S,d_h] × [d_h,S]` → writes an **S×S matrix to
   HBM**. (FLOPs: 2·S²·d_h.)
2. **Max (numerics):** row-max of S for the exp shift — read S back from HBM, write a
   [S] row of maxima.
3. **Probabilities:** `P = softmax(S)` row-wise — read S, compute exp, write an
   **S×S matrix P to HBM**.
4. **Output:** `O = P·V` — GEMM `[S,S] × [S,d_h]` → read P and V from HBM, write O
   `[S,d_h]`. (FLOPs: 2·S²·d_h.)

**Where the S×S matrices are created:** in HBM, steps 1 and 3. Neither S nor P ever
needs to be a full matrix mathematically — softmax is *row-local* (row i of P depends
only on row i of S) and the final GEMM only needs row i of P at a time. The naive form
materializes them because that is the shape a GEMM library expects. [I]

### Quantifying the cost
- **Capacity:** O(S²·h) bytes for S (+ P: another O(S²·h)). This is the *growing* term:
  weights are O(N), activations O(S·d), but S and P are O(S²·h).
- **HBM traffic (per layer, per head):** write S + read S (softmax) + write P + read P
  (GEMM) = **4·S² elements** — the two GEMMs themselves also stream Q, K, V, O, but those
  are O(S·d_h) and vanish next to S². [I]
- **FLOPs:** 2·S²·d_h (QKᵀ) + 2·S²·d_h (P·V) = **4·S²·d_h per head** [F] — the same
  number `../Inference/The-Life-of-a-Token.md` Stage 5 uses.
- **Cross-ref:** The-Life-of-a-Token Stage 5 [E]: at S=32k, h=64, BF16,
  S×S·h·2B = **128 GiB** for the score matrix alone — that is why the naive form
  "cannot fit," not merely "is slow."

The attention FLOPs (4·S²·d_h per head) are *already* compute-bound in prefill; the
*killer* is the S² HBM traffic + capacity. FlashAttention attacks the traffic; the
FLOPs are untouched.

## The Key Insight

> **FlashAttention is primarily an IO-aware algorithm, not merely a faster mathematical
> approximation.** It computes the **same exact softmax attention** — bit-for-bit the
> same result as the naive form up to floating-point summation order — but rearranges
> the computation so the S×S matrix is **NEVER materialized in HBM**: it lives in SRAM
> (shared memory) as tiles. This is an **IO-optimization (data-movement) result, not a
> math change** [F: arXiv:2205.14135].

The paper's own framing: "a missing principle is making attention algorithms IO-aware —
accounting for reads and writes between levels of GPU memory." FlashAttention tiles the
computation to reduce HBM↔SRAM reads/writes and proves the resulting HBM access count is
lower than standard attention's, *and optimal for a range of SRAM sizes* [F:
arXiv:2205.14135, abstract].

## The Mechanism

### 1. Tiling
Split Q, K, V into blocks that fit in SRAM: Q → [Q₁..Q_T], K,V → [K₁..K_T'] with block
sizes `br × bc` chosen so `[br,d_h]` + `[bc,d_h]` + a `[br,bc]` tile of S fit in shared
memory. The kernel processes **one Q-block at a time against streaming K/V-blocks**:

```
for i in Q-blocks:
    load Q_i into SRAM
    O_i, m_i, l_i = 0, -inf, 0
    for j in K/V-blocks:
        load K_j, V_j into SRAM
        S_ij = Q_i·K_jᵀ / √d_h        # [br,bc] — lives ONLY in SRAM
        ... online-softmax update of m_i, l_i, O_i (SRAM) ...
    write O_i → HBM; write (m_i, l_i) → HBM (for the backward pass)
```

Each S_ij tile is computed, softmaxed (against running statistics), multiplied by V_j,
accumulated into O_i, and **discarded** — never stored in HBM. [F: arXiv:2205.14135]

### 2. What actually touches HBM
- **Read:** Q once, K/V streamed through *once per Q-block*... no — K/V are read from
  HBM once per outer-Q-block loop; with Q-loop outer, each K/V block is re-read for
  every Q-block. The theorem below is why that's still a win: the re-read count scales
  with d_h, not S². [I: loop order follows FA1/FA2]
- **Write:** O (S×d_h per head) + the running stats (m_i, l_i: O(S) each).
- **The partial attention accumulates in SRAM; the S×S never exists in HBM at all.**

### 3. Online softmax — why streaming works at all
You cannot pre-compute the global row-max/sum because row i of S is only seen *as K
blocks stream by*. The fix: softmax is **shift-invariant** — `softmax(x)_i = e^{x_i-m} /
Σ e^{x_j-m}` is unchanged for any constant shift m [I: elementary, one line]. So keep
*running* statistics and rescale when the max moves:

```
given a new tile S_ij (block j of the row):
  m_i^(new)  = max( m_i^(old), rowmax(S_ij) )
  α_i        = exp( m_i^(old) - m_i^(new) )          # ≤ 1, rescale factor
  P_ij       = exp( S_ij - m_i^(new) )               # safe: no overflow, tile-local
  l_i^(new)  = α_i · l_i^(old) + rowsum(P_ij)        # running row-sum
  O_i^(new)  = α_i · O_i^(old) + P_ij · V_j          # rescale old output, add new
at the end:  O_i  = O_i / l_i                        # single row-division
```

The accumulated O_i is kept *unscaled* (in the m_i^(old) frame) and rescaled by α_i
whenever a larger max arrives. Cost: one extra [br] vector op per tile — O(S·d_h) extra
work total, negligible against 4·S²·d_h [I]. This "blockwise/online" softmax is the
load-bearing trick; without it, tiling would still force S×S writes.

### 4. The IO result
FA1's IO analysis [F: arXiv:2205.14135] counts HBM element-accesses per head, with
M = SRAM size in elements:

```
standard attention :  2·S²·d_h  +  10·S·d_h²
FlashAttention     :  S²·d_h²/M  +  10·S·d_h
```

- The S² coefficient drops from `2·d_h` to `d_h²/M` → factor **2M/d_h** [E: Worked
  Example 2]; the linear term drops from `d_h` to `1`.
- Big-O: **O(S²) → O(S²·d_h/M)** in HBM accesses; with M ~ S·d_h the S² term collapses
  toward O(S·d_h) — *the S² term vanishes* (M is fixed hardware, S is the variable).
- Memory capacity: O(S²·h) → **O(S·h)** (store Q, K, V, O, m, l; recompute S on the fly).
- FLOPs: **unchanged** — 4·S²·d_h per head either way. The speedup comes from HBM.

```
NAIVE ATTENTION (HBM flow, per head)              FLASHATTENTION (HBM flow, per head)
─────────────────────────────────────             ───────────────────────────────────
 HBM                                             HBM
 Q [S,d]  K [S,d]  V [S,d]                       Q [S,d]  K [S,d]  V [S,d]
   │          │          │                         │         │         │
   ▼          ▼          ▼                         ▼ tile    ▼ tile    ▼ tile
┌────────────┐  GEMM      SRAM (per SM, ~227 KiB)
│            │◄────────────┼──────────────────────►┌─────────────────────────┐
S [S,S] ──►  │             │  Q_i [br,d]           │ Q_i · K_jᵀ → S_ij [br,bc]│
write to HBM │             │  K_j,V_j [bc,d]       │  (S_ij lives HERE,      │
   │          │             │  S_ij [br,bc]  ◄─────►│   never in HBM)        │
   ▼          ▼             │  P_ij, O_i [br,d]     │  online-softmax:       │
┌────────────┐  GEMM      │  m_i,l_i [br]         │  m_i, l_i, O_i updated │
│  P [S,S]   │◄───────────►│  (SRAM only)          │   in SRAM per tile     │
write to HBM │             └───────────┬──────────┘─────────────────────────┘
   │          │                        │
   ▼          ▼                        │ write-back (once per Q-block):
 O [S,d]     O [S,d]                   │  O_i [br,d]      → HBM
                                        │  m_i, l_i [br]   → HBM
HBM traffic: write+read S + write+read P = 4·S² elements
             → O(S²) HBM traffic, O(S²) capacity
HBM traffic: Q,K,V stream (each K/V block re-read per Q-block, ×d_h/M
             vs ×S) + O,m,l once → O(S²·d_h/M) ≈ O(S·d_h), O(S) capacity
```

## FA1, FA2, FA3 — and Inference-Specific Variants

| | When | What | Result | Source |
|---|---|---|---|---|
| **FA1** | 2022 | Exact, IO-aware; tiling + online softmax; O(S) memory; block-sparse extension | BERT-large: 15% end-to-end wall-clock vs MLPerf 1.1 record; GPT-2 (seq 1k): 3×; LRA (1k–4k): 2.4×; enables longer context (better GPT-2 ppl, LRA +6.4 pts) | [F: arXiv:2205.14135] |
| **FA2** | 2023 | FA1 only hit **25–40% of peak FLOPs/s**; the gap was *work partitioning* (loop order, fewer non-matmul FLOPs, more parallelism over heads/blocks) | ~**2× over FA1** on most shapes; now the default baseline | [F: arXiv:2307.08691] |
| **FA3** | 2024 (ICLR'25) | Exploits **Hopper asynchrony**: warp-specialized ping-pong scheduling (producer/consumer warps overlap GEMM+softmax+TMA), **FP8** attention | ~**1.5–2× over FA2** on Hopper | [F: arXiv:2407.08608] |
| Paged variants | 2023– | **PagedAttention** (vLLM, SOSP'23): KV in blocks + block tables, kernel indexes by table [F: arXiv:2309.06180]; **FlashInfer**: prefill+decode kernels for *paged* KV and *ragged* batches (SGLang's primary backend, vLLM backend too) [F: arXiv:2501.01005] | These serve *inference* specifically: decode GEMVs against paged KV; they change KV *storage*, not the attention math — class B + class C in `../Attention/README.md` |

Note the lineage: FA1 fixed the *IO*; FA2 fixed the *work partitioning*; FA3 fixed the
*schedule on Hopper*. Each kept the exact-math promise.

## Standard vs FlashAttention

| Dimension | Standard (naive) | FlashAttention |
|---|---|---|
| **FLOPs** | 4·S²·d_h per head | **identical** — same math; FA does NOT reduce FLOPs |
| **HBM traffic (S² term)** | O(S²) — coefficient 2·d_h per head | O(S²·d_h/M) — coefficient d_h²/M; factor 2M/d_h lower [E] |
| **Memory capacity** | O(S²·h) for S and P in HBM | **O(S)** — only Q,K,V,O,m,l; S² never materialized |
| **Prefill latency** | HBM round-trips for S,P serialize the GEMMs | fewer round-trips → up to ~2–4× over optimized baselines on long seqs [F: arXiv:2205.14135] |
| **Throughput (tok/s, prefill)** | capacity-limited at long S | O(S) memory → higher sustained batch/seq at same GPU |
| **Correctness** | exact | **exact** (same result; only summation order differs) [F] |
| **Backward pass** | must store S and P for gradients | recomputes S_ij tiles on the fly (stores only m_i, l_i) → O(S) activation memory [F: arXiv:2205.14135] |

Be precise when quoting this: any claim "FlashAttention cuts FLOPs" is wrong. The win is
traffic + capacity. (FLOPs reduction belongs to *approximate* attention: sliding window,
linear attention, block-sparse — class A in `../Attention/README.md`.)

## Worked Examples [E, Python-verified this session]

### Example 1 — Why naive attention "cannot fit"
S=32,768 (32k), h=64 heads, d_h=128, BF16 (b=2 B/elem):

```
one S×S matrix:      32768² × 2 B        = 2,147,483,648 B = 2.000 GiB
× 64 heads:          2 GiB × 64          = 128 GiB   ← score matrix only
score + probability: 2 × 128 GiB         = 256 GiB
H100 SXM capacity:   80 GB = 74.5 GiB   → 128 GiB does NOT fit (let alone +P, +weights, +KV)
naive S×S HBM traffic (write+read S and P, all heads): 4·S²·h·b = 512 GiB per layer
  at H100's 3.35 TB/s HBM3 ≈ 164 ms per layer — a HBM-time lower bound, before any FLOPs
```

Cross-ref `../Inference/The-Life-of-a-Token.md` Stage 5, which cites the same
128 GiB figure [E].

### Example 2 — HBM-traffic reduction ratio for a given SRAM size M
FA1's theorem (per head, element-accesses): standard `2·S²·d + 10·S·d²` vs
FlashAttention `S²·d²/M + 10·S·d` [F: arXiv:2205.14135]. With d=d_h=128:

```
S²-term coefficient:  standard 2·d = 256      →  FA d²/M
S²-term reduction:    factor 2M/d
   toy    M = 16,384 elements (32 KiB):  2·16384/128 = 256×
   H100   M ≈ 227 KiB/SM ≈ 116,224 BF16 elems: 2·116224/128 ≈ 1,816×
linear-term reduction: factor d = 128×
full ratio @ S=32k, M=116,224:  (2·S²·128 + 10·S·128²) / (S²·128²/116224 + 10·S·128)
  = 280.25e9 / 0.193e9 ≈ 1,450× fewer HBM element accesses
```

Hand-check the S²-only ratio: 2M/d = 2·116,224/128 = 1,816. [E]

## 9-Field Template — FlashAttention (the algorithm)

### What
Exact softmax attention with the S×S never materialized in HBM; tiled in SRAM with online
softmax. Class B (kernel) in `../Attention/README.md`.

### Why
The S² HBM traffic + capacity of standard attention is the bottleneck, not the FLOPs;
naive attention can't even fit at S≥16k on modern GPUs [E: Example 1].

### How
Tile Q,K,V into SRAM; stream K/V blocks per Q-block; update running (m_i, l_i, O_i) in
SRAM; write O + stats to HBM. Backward recomputes tiles instead of storing S,P.

### When
Any prefill/long-context attention; any training step with S ≫ d_h/M. Not relevant for
S≈1 decode GEMVs (see Implications).

### Hardware impact
SRAM (shared memory) is the new scratchpad for the S² data; HBM only sees O + O(S)
stats; Tensor Cores still do the S_ij and O_ij GEMMs (`./Tensor-Cores.md`) — FA3's
warp-specialized scheduling overlaps those GEMMs with softmax/TMA on Hopper.

### Inference impact
Prefill TTFT: O(S) memory → longer prompts, bigger batches; decode: no effect on the
KV-read floor (honest limit, below).

### Example
Worked Examples 1–2 above: 128 GiB S×S @32k/h=64; 1,450× fewer HBM accesses @ H100 M.

### Failure modes
- Small S (S < few·br): tiling overhead dominates; naive or a small-S kernel can win. [A]
- Ragged/paged KV at decode: need paged variants (FlashInfer/PagedAttention), not
  plain-FA forward. [I]
- FP8 (FA3): accuracy-sensitive models may need per-tensor scaling care. [A]
- Non-Hopper FP8: FA3 speedups are Hopper-specific; don't extrapolate. [A]

### How to measure it
Profile HBM traffic: `dram__throughput` (Nsight Compute) for attention kernels;
torch.profiler shows FA kernels replacing the S/P elementwise kernels; capacity: watch
`memory_allocated` vs S² curve — flat under FA, quadratic under standard. [F: Nsight
Compute docs]

## 9-Field Template — Online Softmax (the mechanism)

### What
Streaming softmax: maintain running row-max m_i and row-sum l_i over tiles; rescale
accumulated output by α_i = exp(m_old − m_new) when a larger max arrives; final O_i/l_i.

### Why
Softmax is shift-invariant, so the global max/sum are only needed *at the end* — every
tile can be normalized against the running max, making block-wise attention exact.
[I: invariance is one-line; FA1 presents the full algorithm, arXiv:2205.14135]

### How
Per-tile update: m_new = max(m_old, rowmax(S_ij)); P_ij = exp(S_ij − m_new);
l_new = α·l_old + rowsum(P_ij); O_new = α·O_old + P_ij·V_j; end: divide O by l.

### When
Whenever K/V is processed in blocks: FA1/2/3 forward *and* backward; also any
chunked/online normalization kernel.

### Hardware impact
[br]-wide vector ops per tile (O(S·d_h) total); no S×S storage; keeps exp() on
SRAM-resident tiles → fewer HBM stalls; more SMs usable on the (non-GEMM) softmax work
that FA2 parallelizes across blocks.

### Inference impact
Enables the O(S) memory that makes prefill at 100k+ context feasible; decode kernels
(FlashInfer) reuse the same streaming-softmax math against paged KV.

### Example
Hand-check: two tiles, row of S = [1, 3] then [2, 4]. m: 3 → 4; α = e^(3−4) ≈ 0.368.
l = 0.368·(e^1+e^3... use tile-local: tile1 P=[e^{1−3}, e^{3−3}]=[0.135,1], l₁=1.135;
tile2 P=[e^{2−4}, e^{4−4}]=[0.135,1], l₂=0.368·1.135+1.135≈1.551. O/l gives exactly
softmax([1,3,2,4]). [E: arithmetic]

### Failure modes
- m_i = −∞ on the first tile → guard the α = e^(−∞ − m) case (α:=0). [A: standard guard]
- Underflow of e^{s−m} for very negative s: harmless (→0), but FP8 tile quantization of
  P_ij adds noise → FP8 accuracy care. [I]
- Accumulator dtype: O_i in FP32/TF32 even if inputs are BF16, or you lose the rescale.
  [A: kernel convention]

### How to measure it
Correctness: compare O vs `F.softmax(QKᵀ/√d)·V` (max abs diff ~1e-3 in BF16); the
rescale factor α's distribution (nsight trace of the epilogue, or a debug kernel). [I]

## Implications

- **Long context:** the S² term is the killer — 128 GiB @32k [E] vs O(S·h) under FA.
  FlashAttention is what made 32k→128k+ training/serving feasible on single-node GPUs;
  it is the prefill-side enabler, while GQA/MLA/quantization attack the *KV* side
  (`../KV-Cache/README.md`).
- **Prefill:** still compute-bound (4·S²·d_h FLOPs per head, unchanged), but now
  IO-efficient — no HBM round-trips for S/P; FA2/FA3 push toward the GEMM roof
  (`./GEMM.md`: attention was the op that couldn't reach it).
- **Training:** backprop of attention must store S and P (another 2·O(S²·h)) under the
  naive form; FA recomputes S_ij tiles and stores only m_i, l_i → activation memory
  O(S), enabling longer sequences / bigger batches at the same HBM. [F: arXiv:2205.14135]
- **Inference (decode) — the honest limit:** at decode S=1 per step; attention is a GEMV
  over the KV cache, reading 2·h_kv·d_h·L_ctx·b bytes *per layer per token*. Flash
  Attention does **NOT** reduce those KV reads — there is no S² to eliminate at S=1.
  The decode floor belongs to GQA/MQA/MLA, KV quantization, paging/eviction: see
  `../KV-Cache/README.md` and `../Inference/The-Life-of-a-Token.md` Stage 6/10. FA's
  decode contribution is the kernel's *scheduling* (FlashInfer, warp-specialization),
  not fewer bytes. [I]
- **Kernel stack context:** FA is the canonical example of the fusion + tiling pattern
  (`./Fused-Kernels.md`), built on the GEMM tiling discipline (`./GEMM.md`) and the
  SRAM/HBM asymmetry (`./Memory-Hierarchy.md`, `./Bandwidth-vs-Compute.md`); its
  scheduling ideas (producer/consumer, TMA overlap) generalize into
  `./Memory-Optimizations.md`-class kernels.

## Related
`../Attention/README.md` (class B) · `../Inference/The-Life-of-a-Token.md` (Stage 5: the
128 GiB S×S) · `./GEMM.md` · `./Tensor-Cores.md` · `./Memory-Hierarchy.md` ·
`./Memory-Optimizations.md` · `./Fused-Kernels.md` · `../KV-Cache/README.md` ·
`../Inference/Roofline.md` · `./vLLM.md` (PagedAttention) · `./SGLang.md` (FlashInfer)

## Key Takeaways
1. FlashAttention changes **IO, not math**: same 4·S²·d_h FLOPs, exact result.
2. The S×S lives in SRAM as tiles; only O + (m_i, l_i) touch HBM.
3. HBM traffic O(S²) → O(S²·d_h/M): the S² term vanishes as S grows (M is hardware-fixed).
4. FA1 fixed IO, FA2 fixed work partitioning (~2×), FA3 fixed Hopper scheduling + FP8 (~1.5–2×).
5. Decode KV reads are **not** FA's problem — GQA/MLA/quant/paging are.
