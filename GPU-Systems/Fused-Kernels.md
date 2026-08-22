# Fused Kernels
`LAST_UPDATED: 2026-08-21 · Status: core page` · All [E] arithmetic hand-derived;
hardware constants cross-checked against `../Hardware/README.md` and NVIDIA specs.

## 30-Second Explanation
Most LLM layers are written as a *chain* of small kernels, and each boundary in the chain
forces a tensor through HBM:
```
Kernel1 → write HBM → Kernel2 → read HBM → write HBM → Kernel3 → read HBM → …
    vs
FusedKernel → do all ops in registers/shared → write the final result once
```
Fusion is the practice of merging those kernels so the intermediate tensors **never touch
HBM at all**. The payoff, in order of size: (1) less HBM traffic — intermediates that
were written and re-read are kept in registers or shared memory instead [I]; (2) fewer
kernel launches — each launch has CPU-side overhead, and at decode batch sizes the GPU is
often *launch-bound* (`Kernel-Life.md`); (3) lower sync overhead — each kernel boundary is
an implicit stream sync; (4) better register/cache reuse — a value written then re-read is
worse than a value that stayed in registers. FlashAttention is the most famous instance:
it fuses `QKᵀ → softmax → ×V` so the S×S score matrix never materializes
(`./FlashAttention.md`) [F: FlashAttention, arXiv:2205.14135]. But fusion is **not free** —
it buys traffic at the cost of register pressure, complexity, and compile time; the second
half of this page is about when it *doesn't* pay.

## What
**Kernel fusion**: replacing a sequence of kernels `K1, K2, …, Kn` that communicate only
through intermediate tensors in global memory with a single kernel that computes the whole
chain and writes one result. The fused kernel executes each "phase" of the chain in
registers or shared memory, where intermediates are free. Two flavors:
- **Elementwise/epilogue fusion** — cheap per-element ops (bias, activation, residual add,
  RMSNorm scale) folded into the *epilogue* of a GEMM or the *prologue* of the next op.
  This is what `torch.compile`/Inductor and hand-written engine kernels do by default [A].
- **Algorithmic fusion** — a restructured algorithm that avoids materializing a tensor the
  original formulation writes out (FlashAttention's online softmax; fused SwiGLU).

Fusion happens at layer L2 (compiler) and L3 (kernel) of `./Kernel-Stack.md`: the compiler
fuses pointwise ops into GEMM epilogues, and hand-written kernels (Triton/CUDA/CUTLASS)
fuse at the algorithm level.

## Why
Every unfused boundary costs, per intermediate tensor `T` of size `N` elements in `b` bytes:
```
+1 HBM write of T   (N·b bytes)
+1 HBM read of T    (N·b bytes)
+1 kernel launch    (CPU-side, ~µs order) [A]
+1 stream sync      (implicit)
```
For memory-bound decode, where the GPU is already streaming weights at full HBM bandwidth,
the intermediate traffic is *pure overhead* on top of the weight bytes [I]. For
launch-bound decode (B=1, small model), the launch overhead can exceed the compute time
of the tiny kernel entirely (`Kernel-Life.md`). The per-layer op list in
`../Inference/The-Life-of-a-Token.md` shows how many fusion opportunities exist: every
layer has ≥6 elementwise/norm boundaries around ~5 GEMMs.

## How
1. **Identify the chain.** Two adjacent kernels are fusable if kernel `K2` reads exactly
   what `K1` wrote (or a strict slice of it), and `K2`'s per-element work is cheap relative
   to `K1`'s memory traffic [A].
2. **Pick the host kernel.** Usually the *dominant* kernel (the GEMM) absorbs the cheap
   one into its **epilogue** (post-MMA, pre-store) or **prologue**. The epilogue is the
   cheapest seam: each output tile is already in registers; add bias, apply activation,
   store — zero extra HBM traffic for the op itself.
3. **Keep intermediates in fast memory.** Epilogue values: registers. Row reductions
   (RMSNorm): one block per row, row in registers/shared, tree-reduce in shared
   (`./CUDA-From-Zero.md`, examples 7–8). Cross-tile state (softmax over S): online
   rescaling, as in FlashAttention.
4. **Mind the dtype.** The fused chain must stay in one precision end-to-end; dequant
   (below) is the case where the *host* kernel runs in FP32-equivalent registers while
   HBM carries quantized bytes [A].
5. **Verify numerics.** Fusing changes rounding order (epilogue fusions usually don't;
   algorithmic fusions like online softmax do, bounded rescaling [F: arXiv:2205.14135]).

## When
- **Decode (B small):** fusion and CUDA Graphs together are the main lever — kernels are
  tiny and the GPU idles between launches [I].
- **Prefill with long S:** intermediate *sizes* grow with S (attention scores are S×S),
  so algorithmic fusion (FlashAttention) saves the most bytes per token.
- **Memory-bound ops (norms, activations, dequant):** always fuse — they add no FLOPs,
  only bytes.
- **Not when:** the intermediate is tiny or L2-resident (see Failure modes), or the fused
  kernel's register pressure cuts occupancy enough to lose more compute than you saved.

## Hardware impact
- **HBM:** the direct win — fewer bytes moved. HBM is the decode bottleneck
  (`../Inference/Roofline.md`), so traffic cuts land almost 1:1 on ITL at low batch [I].
- **L2 cache:** fused chains keep working sets small; intermediates that would have
  streamed HBM now stay in L2 [A].
- **Registers:** fusion's *cost*. The host kernel now holds more live state (e.g., GEMM
  accumulator + bias + activation temporaries), so registers/thread rise and
  **occupancy can drop**. At 100% occupancy a kernel hides HBM latency with other warps;
  at 50% it may stall on memory instead [A].
- **SM issue:** epilogue ops add instructions per tile but almost never FLOPs; compute
  cost is negligible vs the GEMM [A].

## Inference impact
- **TTFT (prefill):** dominated by FlashAttention-class fusion (S×S traffic removal) and
  fused QKV/MLP epilogues; norm/bias fusions save microseconds each but ×32 layers
  adds up [I].
- **ITL (decode):** fused RMSNorm, fused bias+act, and in-kernel dequant directly shrink
  `bytes_per_token`, and launch cuts shrink the launch-bound portion of ITL
  (`../Inference/The-Life-of-a-Token.md`, stage 9 notes sampling is
  launch-overhead-bound, not math-bound).
- **Capacity:** FlashAttention's no-materialization property is what makes long-context
  attention fit at all; at S=32k the S×S score matrix would be multi-GiB per head
  (`../Inference/The-Life-of-a-Token.md` stage 5 shows the arithmetic) [E, derived there].

## Example
Smallest meaningful fusion, bias+SiLU after a `[S,d]·[d,d]` GEMM (`b=2` BF16, S=4096):
```
unfused:  GEMM:  read X+S·d·b, read W → write T [S,d]      (launch 1)
          bias+SiLU: read T, read bias → write T' [S,d]    (launch 2)
fused:    GEMM+epilogue: read X, read W, read bias →
          per tile: T_reg += bias; T_reg = SiLU(T_reg); write T'   (launch 1)
saved: 2·S·d·b = 2·4096·4096·2 = 67,108,864 B = 64 MiB HBM traffic, 1 launch
```
Full worked numbers in [E] section below.

## Failure modes
- **Occupancy collapse:** the fused kernel registers exceed the per-SM budget; the
  compiler spills to local memory (which is HBM) — *more* traffic than the unfused chain.
  Symptom: `nsight compute` shows register count up, occupancy down, DRAM traffic not
  down [A].
- **Wrong-shape specialization:** the fused kernel is tuned for S=4096; at S=128 the
  tiles are mostly padding and the unfused chain (small kernels, good L2) wins [A].
- **Graph breaks:** with `torch.compile`, any op that can't be traced (dynamic shape,
  host callback, `.item()`) breaks the graph at that point → the ops after the break run
  unfused/eager [A: PyTorch docs].
- **Numerics drift:** aggressive fusion changes reduction order; a fused RMSNorm that
  reduces in 1 pass instead of 2 can differ by an ULP or two — fine in FP16/BF16,
  occasionally a problem in FP32 training [A].
- **Debugging blind spot:** a fused kernel failing gives one opaque error instead of
  "kernel 3 of 8"; kernel-level unit tests (run each phase standalone) are the mitigation.

## How to measure it
- **Kernel count + launch time:** Nsight Systems timeline — count kernels per decode step
  and the gaps between them; fused steps show fewer boxes and fewer gaps [F: Nsight docs].
- **HBM bytes:** `nsight compute` → `dram__bytes` per kernel; compare chain total vs fused
  kernel. The [E] example predicts 64 MiB/layer for a bias+SiLU fusion.
- **Occupancy:** `nsight compute` → achieved occupancy + registers/thread, before/after.
- **End-to-end:** ITL and TTFT at fixed batch via the pinned protocol in
  `./Perf-Experiment-Template.md`; expect the win to *shrink* as batch grows (intermediate
  traffic amortizes, launch overhead amortizes faster) [I].
- **Regression check:** run the unfused and fused paths side by side on the target shape
  distribution — fusion is shape-specific, so benchmark *your* shapes, not the default one.

## HBM Timeline — N Kernels vs One Fused
Concretizing the pattern: down-MLP path `M = GEMM(X,W2)` → `M' = bias(M)+SiLU(M)` →
`Y = GEMM(M', W3)`, where `M, M'` are `[S, d]` intermediates.

```
UNFUSED — 3 kernels, intermediates round-trip HBM
time ─────────────────────────────────────────────────────────────────────►
 K1: GEMM(X·W2)          K2: bias+SiLU           K3: GEMM(M'·W3)
    read  X  (HBM)          read  M'  (HBM)        read  Y'  (HBM)
    read  W2 (HBM)          read  b   (HBM)        read  W3  (HBM)
    write M  (HBM) ─────►   write M'  (HBM) ─────►  write Y  (HBM)
    [launch 1]              [launch 2]              [launch 3]

intermediate HBM ops:  M: 1 write + 1 read · M': 1 write + 1 read
                       = 4 × S×d×b bytes of pure round-trip
launches: 3, stream syncs: 2

FUSED — K2 absorbed into K1's epilogue, single write of the intermediate
time ─────────────────────────────────────────────────────────────────────►
 K1': GEMM(X·W2) + epilogue        K3': GEMM(M'·W3)
    read  X  (HBM)                   read  M'  (HBM)
    read  W2 (HBM)                   read  W3  (HBM)
    read  b  (HBM, once per row)     write Y  (HBM)
    per tile in registers:           [launch 2]
       acc += b; acc = SiLU(acc)
    write M' (HBM, once) ─────►
    [launch 1]

intermediate HBM ops:  M: GONE (kept in registers) · M': 1 write + 1 read
                       = 2 × S×d×b bytes of round-trip
launches: 2, stream syncs: 1
```
General law: an n-kernel chain with n−1 intermediates does `2(n−1)` intermediate
HBM ops; the fused version does only what it physically must (final result writes,
plus any intermediate that a later *separate* GEMM still needs to read) [E, derived].

## Transformer Fusion Catalog
Each entry: what's fused · HBM traffic saved · launches saved · access-pattern note.
All "traffic saved" figures assume the unfused baseline writes each intermediate to HBM;
actual savings shrink when an intermediate is L2-resident [A].

| # | Fusion | What's fused | Saved (per layer, S tokens, b bytes/elt) | Launches |
|---|---|---|---|---|
| 1 | bias + activation | GEMM epilogue | 2·S·d·b (one intermediate) | 1 |
| 2 | RMSNorm | row reduce + scale (+residual) | 2·S·d·b (residual-fused form) | 1–2 |
| 3 | residual add + norm | add + RMSNorm in one pass | 2·S·d·b | 1 |
| 4 | QKV projection | 3 GEMMs → 1 | 2·S·d·b (X re-reads) | 2 |
| 5 | RoPE | rotation in epilogue/prologue | 2·S·(h·d_h)·b ×2 (Q,K) | 2 |
| 6 | attention (FA) | QKᵀ + softmax + ×V | ~2·S²·d_h·b per head | 1 |
| 7 | MLP (SwiGLU) | silu·mul (+weight concat) | 2·S·d_ff·b | 1–2 |
| 8 | dequant | dequant inside GEMM | d·b_w·b (per GEMM, weight-sized) | 1 |

### 1. bias + activation (bias+GELU/SiLU)
Fused into the GEMM **epilogue**: the output tile is in registers when the epilogue runs,
so `acc += bias[j]; acc = act(acc)` costs instructions only. Saves one HBM write+read of
the `[S,d]` intermediate. Access pattern: the bias row is a tiny `[d]` vector broadcast
across every tile's columns — load it once into shared, no extra HBM. This is the most
common single fusion in any engine (it's the default `F.linear` + activation lowering in
Inductor [A]).

### 2. RMSNorm
`y = x·g / √(mean(x²)+ε)` [F: RMSNorm, arXiv:1910.07467]. One block per row: read the row,
tree-reduce Σx² in shared memory, scale, write. A full **reduction + normalize in one
kernel** — the unfused form would be reduce-kernel + scale-kernel (or 3 reads of the row
in one pass). `./CUDA-From-Zero.md` **example 8** has the block-reduction kernel and notes
the bandwidth/launch trade-off. Access pattern: coalesced row reads; the row is re-read
from L2/registers for the scale pass — that's why keeping it register-resident
matters [I]. Pre-norm decoders run **2L RMSNorm kernels per token** (L=32 → 64) — pure
launch overhead when unfused [F: LLaMA, arXiv:2302.13971].

### 3. residual add + normalization
`x' = h + x; y = RMSNorm(x')` in one kernel: read `h` and `x`, add in registers, reduce,
scale, write `y`. Unfused = add-kernel (read h, read x, write s) + norm-kernel (read s,
write y) = 5 array touches, 2 launches; fused = 3 array touches, 1 launch → saves
2·S·d·b HBM + 1 launch. This is the standard fused kernel in LLaMA-family engines
(usually `add_rms_norm`) [A]. Access pattern: two coalesced rows per row of output; the
sum lives in registers across the reduction.

### 4. QKV projection
Three GEMMs `X·Wq, X·Wk, X·Wv` share the **same input X** → one GEMM against
`[Wq|Wk|Wv]` concatenated along N: `X · Wqkv` with N = (h + 2·h_kv)·d_h. The output is
already laid out contiguously as Q,K,V segments, so the reshape/split after is a view, not
a copy [A: standard layout; LLaMA's reference uses fused QKV, arXiv:2302.13971]. Saves
2 re-reads of X from HBM (2·S·d·b) and 2 launches; weight reads unchanged. Access pattern:
identical K-tile streaming as one GEMM — no new pattern, just a wider N. The same trick
applies to any GEMM family sharing an input (e.g., MLP up+gate, entry 7).

### 5. rotary embeddings (RoPE)
Position-dependent rotation of Q,K: `q'_i = q_i·cos θ + (±)q_j·sin θ`
[F: RoFormer, arXiv:2104.09864; see `../Model-Architectures/Positional-Encodings.md`].
Unfused = a separate kernel that reads Q,K, writes Q',K'. Fused: applied in the **GEMM
epilogue** of the QKV projection (θ depends only on position, computed on the fly or
pre-computed in shared) or in the attention kernel's K/V load path. Saves 2·S·(h·d_h)·b
writes + the same reads, and 1–2 launches per layer. Access pattern: each element pairs
with its neighbor at offset d_h/2 — still coalesced within a warp; no extra HBM.

### 6. attention (FlashAttention)
Fuses `QKᵀ → scale → softmax → ×V` so the S×S score matrix is never materialized in HBM:
tiling in S with **online softmax** (running max + rescale) keeps partial results in
SRAM [F: FlashAttention, arXiv:2205.14135; full treatment in `./FlashAttention.md`].
Standard attention does ~2 HBM passes over the S×S scores per head (write scores, read for
PV) plus softmax read/write; FlashAttention's HBM traffic is O(S·d_h), not O(S²·d_h).
Access pattern: block-cyclic tiling of Q and K^T/V tiles; the S×S matrix becomes
tile-serial, which is why this is an *IO-aware algorithm* rather than a faster
approximation — FLOPs are ~the same, bytes are far fewer [F].

### 7. MLP (fused SwiGLU)
SwiGLU FFN: `H1 = X·W1; H2 = X·W2; Y = silu(H1)·H2 · W3` [F: LLaMA uses SwiGLU,
arXiv:2302.13971]. Practical fusion stack: (a) concatenate W1,W2 → **one** GEMM producing
`[H1|H2]` (saves one X re-read, 1 launch); (b) a fused `silu(H1)·H2` elementwise kernel
instead of separate SiLU + mul (reads H1,H2, writes M once: 3 array touches vs 5, 1
launch); (c) down-proj GEMM. Fully fusing the down-proj into (b) is *not* generally
possible — W3 needs the whole `[S,d_ff]` row, a cross-tile dependency — so the down GEMM
stays separate in most engines [I: check the engine's kernel list rather than assume].
Net: 2–3 launches saved and ~2·S·d_ff·b less intermediate traffic per layer.

### 8. quantization / dequantization
Instead of a `dequant` kernel (read quantized weight, write full-precision weight to HBM)
followed by a GEMM, the GEMM kernel **dequantizes inside itself**: load the quantized
weight tile (4–8× fewer bytes), load the per-block scales, dequant into registers, then
issue the Tensor Core MMA [F: GPTQ, arXiv:2210.17323; AWQ, arXiv:2306.00978; formats in
`../Quantization/README.md`]. Saves one full write+read of the weight matrix per layer per
GEMM — at BF16-equivalent, that's `2·d·d·b_w` bytes (hundreds of MB for a 4096² GEMM in
BF16 terms), which is why quantized GEMM is a decode-bandwidth lever, not just a
compute one. Access pattern: quantized tiles are smaller and denser, often *better*
coalesced; scales are a tiny `[d/blk]` vector per tile.

## Worked Example [E] — fusing bias+SiLU into a GEMM epilogue
Setup: S = 4096 tokens, intermediate `[S, d]` with d = 4096, BF16 (b = 2 bytes).
The intermediate is written once and read once by the unfused chain:
```
bytes(intermediate)   = S · d · b        = 4096 · 4096 · 2
                        = 4096 · 4096 = 16,777,216  ×2
                        = 33,554,432 B  = 32 MiB
HBM saved by fusion   = 2 · S · d · b    = 2 × 33,554,432
                        = 67,108,864 B   = 64 MiB  (0.0671 GB decimal)
launches saved        = 1
```
Time value, assuming a bandwidth-optimal unfused baseline on H100 HBM3 (3.35 TB/s,
[F: NVIDIA H100 specs]):
```
67,108,864 B / 3.35·10¹² B/s ≈ 2.0·10⁻⁵ s ≈ 20 µs per layer [E, arithmetic]
```
i.e. up to ~20 µs/layer recovered if the baseline was bandwidth-bound on that
intermediate; in practice the fused chain also avoids 1 launch (~µs order, [A]) and one
sync. Per-layer savings are small vs the GEMMs themselves, which is why engines fuse
*all* pointwise ops and why the algorithmic fusions (FlashAttention, in-GEMM dequant)
matter more at the byte level [I].

## The Limits of Fusion (equally important)
Fusion is a trade, not a free lunch. The costs, in the order they bit people:
- **Register pressure → occupancy.** The fused kernel holds more live values. If
  registers/thread pass the occupancy cliff, the SM loses warps to hide HBM latency and
  the kernel *stalls* — potentially slower than the unfused chain, whose low-occupancy
  kernels were bandwidth-optimal to begin with [A]. Check achieved occupancy in
  `nsight compute` before and after; don't assume "fewer bytes" = "faster".
- **Complexity.** A fused kernel is harder to write, harder to debug (one opaque failure
  vs 8 localized ones), and harder to **autotune** — the config space (tile sizes ×
  epilogue variants × dtype paths) explodes, and autotune time grows with it [A].
- **Compilation overhead.** JIT-compiled fused kernels (Triton/Inductor) have longer
  first-run compile; more fused variants = more compile to cache. `torch.compile` is
  especially sensitive: any **graph break** forces eager execution from that point,
  silently losing every fusion after it [A: PyTorch docs]. AOT engines (TRT-LLM) pay
  this at build time instead [A: `./TensorRT-LLM.md`].
- **Shape specialization.** A fused kernel autotuned for S=4096 prefill can be worse at
  S=1–32 decode (different tiling, different register budget). Engines ship *separate*
  fused kernels for prefill and decode for exactly this reason
  (`./GEMM.md` § "shape") [I].
- **Not always a win.** If the intermediate is **small** (fits in L2) or **short-lived**
  (written and read by a kernel that's still in flight), the HBM round-trip already costs
  ~nothing — fusion saves bytes that weren't being spent. If fusion cuts occupancy, it
  can *hurt* compute-bound prefill even while cutting HBM bytes. The honest test is:
  measure `dram__bytes` **and** achieved occupancy **and** end-to-end latency, on your
  shape distribution, before and after [I].

## Related
`./GEMM.md` (epilogues attach here) · `./CUDA-From-Zero.md` (examples 7–8: LayerNorm,
RMSNorm) · `./FlashAttention.md` (algorithmic fusion) · `./Kernel-Stack.md` (fusion lives
at L2/L3) · `./Kernel-Life.md` (launch overhead) · `./Memory-Hierarchy.md` (what fusion
avoids touching) · `../Quantization/README.md` (in-GEMM dequant) ·
`../Model-Architectures/Positional-Encodings.md` (RoPE) ·
`../Inference/The-Life-of-a-Token.md` (the op list to fuse) · `./Perf-Experiment-Template.md`.

## Key Takeaways
1. Fusion = keep intermediates out of HBM: saves `2·N·b` bytes per intermediate + a launch.
2. Two flavors: epilogue/elementwise fusion (cheap, everywhere) and algorithmic fusion
   (FlashAttention-class, where the bytes are quadratic in S).
3. The costs are register pressure/occupancy, complexity, compile time, and shape
   specialization — a fused kernel is a *different kernel*, not a strictly better one.
4. Measure the fusion: `dram__bytes`, kernel count, occupancy, and ITL/TTFT on your
   shapes — not just "fewer kernels".
