# Custom GEMM and Matrix Multiplication Kernels
`LAST_UPDATED: 2026-08-21 · Status: core page` · PART XI — answers "why write a GEMM when
cuBLAS already does it?" Hardware constants per `../Hardware/README.md`; all [E]
arithmetic hand-derived.

## 30-Second Explanation
cuBLAS/cuBLASLt is the most-optimized GEMM code in existence: years of vendor tuning,
per-shape autotuning, and Tensor-Core paths for every dtype/arch combination. For the
"common" shapes (balanced M, N, K; contiguous layouts; standard dtypes) it is the best
default, full stop [A]. But LLM inference lives in the corners the general library serves
poorly or not at all: **M = 1..32 decode** (skinny, bandwidth-bound, tile waste),
**grouped MoE expert GEMMs** (many different-M GEMMs in one launch), **quantized
weight-only formats** (GPTQ/AWQ packed 4-bit with per-group scales — not a cuBLAS input
type), and **fused GEMM+epilogue** work (dequant, router, activation in-kernel). So
inference engines keep a **kernel portfolio**: cuBLASLt for large-M dense GEMMs,
CUTLASS-built kernels for shape-specialized GEMMs, Triton-generated kernels for fused/
quantized ops, and hand-written CUDA for the hottest paths — and *select among them at
runtime* per (M, N, K, dtype, arch). That selection logic is a core engine feature
(`Inference-Engines.md`, `vLLM.md`). This page: the shape-specific argument, the GEMM
variant taxonomy, kernel selection, and the roles/composition of cuBLAS / cuBLASLt /
CUTLASS / Triton / custom CUDA, plus a "when you'd write each" decision guide.

## Why cuBLAS is so good (and where it wins)
- **Autotuned per shape:** cuBLASLt's runtime API returns a *heuristic* algorithm for a
  given (M, N, K, layout, dtype) — `cublasLtMatmulAlgoGetHeuristic` — and engines can
  additionally search/benchmark candidate algos (`cublasLtMatmulAlgoGet` +
  `cublasLtMatmulAlgoCheck`) and cache the winner [F: NVIDIA docs].
- **Years of tuning:** decades of kernel development across GPU generations, with
  Tensor-Core mainloops (MMA/wgmma/TMA) for every supported precision
  [F: NVIDIA docs; `Tensor-Cores.md`].
- **Covers the "common" shapes well:** balanced or large M, K ≥ ~512, standard dtypes
  (FP16/BF16/FP32/TF32/FP8/INT8), contiguous row/col-major layouts [A].
- **Verdict:** for prefill (M = S, often ≥ 256) and large-batch decode, cuBLASLt is
  usually the correct first choice; beating it requires shape-specific work [A].

## Why a custom kernel when cuBLAS exists (the shape-specific argument)

### What
The claim: **the same GEMM operation, same weights, same GPU, can need two fundamentally
different kernels because M (tokens in flight) moves the workload between the memory and
compute roofs** (`GEMM.md`). A kernel tuned for M=4096 prefill is often sub-optimal at
M=1 decode, and a GEMM library's generic/heuristic path is exactly what you get when no
specialized kernel is registered for your shape [A].

### Why
- **Two roofs, two kernels:** at M=1, AI ≈ 1 FLOP/byte → HBM-bound; the whole kernel is a
  bandwidth-optimized weight streamer (a GEMV). At M=4096, AI ≈ 1364 FLOP/byte →
  Tensor-Core-bound; the kernel is a tiling/pipelining exercise. One heuristic cannot be
  optimal on both roofs (`Bandwidth-vs-Compute.md`) [E, Example below].
- **Tile waste at small M:** GEMM tiles (e.g. 128×128) pad M to the tile boundary; at
  M=1..32 most of each row-tile is padding → wasted issue slots and extra shared/register
  pressure [A].
- **Formats the library doesn't speak:** GPTQ/AWQ pack weights as 4-bit with per-group
  16-bit scales (arXiv:2210.17323, arXiv:2306.00978). That storage format is not a
  cuBLAS input type — dequant + scale application must happen in-kernel
  (`../Quantization/README.md`) [A].
- **Compound ops the library won't fuse:** router+top-k + grouped GEMM for MoE
  (arXiv:2401.06066, arXiv:2401.04088); GEMM+bias+SwiGLU+quantize epilogues
  (`Fused-Kernels.md`). cuBLAS computes C=A·B; the rest is extra launches + HBM round-trips [I].

### How
1. **Register a shape-specialized kernel:** build it for the exact (M-range, N, K, dtype,
   arch) the engine actually sees (e.g. "M ≤ 32, K ∈ {4096, 11008}, BF16/FP8, Hopper").
2. **Match the roof:** bandwidth-bound M → vectorized, coalesced weight streaming, no
   padding waste, maximize HBM bytes/cycle; compute-bound M → MMA mainloop + TMA/async
   pipelining (`Memory-Optimizations.md`).
3. **Fuse the neighbors:** dequant/scale (W4A16), router gather/scatter (MoE),
   activation/quant epilogue — one HBM round-trip instead of N (`Fused-Kernels.md`).
4. **Register with the engine's kernel-selection table** (next section) so it is chosen
   per (shape, dtype, arch) at runtime, not hardcoded.

### When
- **Always worth it:** M ≤ 32 decode on quantized models; MoE grouped GEMM; any fused
  GEMM+dequant+activation path; new arch/dtype combos the library hasn't shipped.
- **Rarely worth it:** large-M dense GEMM in a standard dtype on a mainstream arch —
  cuBLASLt is the incumbent champion; measure before assuming you can beat it [A].

### Hardware impact
- Skinny/decode kernels target **DRAM throughput** (`dram__throughput` ≈ peak): the kernel
  is a weight streamer; Tensor Core utilization is low by construction
  (`Tensor-Cores.md`).
- Shape-specialized compute kernels target **MMA pipe utilization**: tile choice and
  K-pipelining tuned to the SM's register/SMEM budgets (`Memory-Hierarchy.md`).
- Quantized kernels split work: dequant/scale on **CUDA cores**, the MMA on **Tensor
  Cores** — the split must not starve the MMA feed (`Tensor-Cores.md`).

### Inference impact
- **ITL/TPOT (decode):** a bandwidth-optimal skinny/decode kernel streams the same bytes
  at full DRAM efficiency; a mis-picked large-M kernel leaves bandwidth on the table —
  the ceiling is `BW ÷ bytes-per-token` (`../Inference/Roofline.md`).
- **TTFT (prefill):** custom buys you at most the last few % of MFU here; the wins
  instead come from FP8/FP4 dtype paths and FlashAttention (`FlashAttention.md`).
- **Throughput (MoE):** grouped GEMM avoids N×launch overhead and lets the scheduler
  balance token counts across experts in one kernel (`MoE-Expert-Parallelism.md`).

### Example [E, hand-derived]
One MLP weight matrix `[4096 × 4096]` BF16 (b_w = 2 B/param):
- **M = 1 (decode GEMV):** FLOPs = 2·1·4096·4096 = **33.55 MFLOP**; weight bytes =
  4096·4096·2 = **33.55 MB** → AI = 33.55e6 / 33.55e6 = **1.0 FLOP/byte** → memory roof.
- **M = 4096 (prefill):** FLOPs = 2·4096·4096·4096 = **137.4 GFLOP**; bytes ≈ weights
  33.55 MB + A 33.55 MB + C ≈ **100.7 MB** → AI = 137.4e9 / 1.007e8 ≈ **1364 FLOP/byte**
  → compute roof (≈ d/b_w = 2048 if A/C weren't re-streamed; weights dominate [E]).
- The M=1 case: total work (33.55e6 FLOP) is trivial on any Tensor Core; the *only*
  variable is how close the kernel gets to `3.35 TB/s ÷ 33.55 MB` per weight matrix.
  That's a memory kernel design problem, not a FLOP problem — exactly what a generic
  GEMM heuristic is not built for [I].

### Failure modes
- **Assuming "custom" always wins:** at large M a dequant-heavy custom GEMM can lose to
  plain cuBLAS BF16 — measure both (`Tensor-Cores.md` failure modes).
- **Picking a large-M kernel for M=1:** the classic cuBLAS-default trap; engines fix it
  with explicit skinny/decode paths or cuBLASLt algo selection (`GEMM.md` failure modes).
- **Over-specializing:** a kernel tuned for exactly M=4096 breaks at M=4095 or on the
  next arch; parameterize the M-range, keep a cuBLAS fallback.
- **Skipping the fusion:** shipping a "better GEMM" that then does 3 extra HBM round-trips
  (dequant → GEMM → quantize) undoes the win (`Fused-Kernels.md`).

### How to measure it
- **Nsight Compute:** `dram__throughput` (skinny: target ≈ DRAM peak),
  `sm__inst_executed_pipe_tensor` + achieved FLOP/s vs the *correct* dtype peak
  (compute kernels) [F: Nsight Compute docs] → `Profiling.md`, `GPU-Metrics.md`.
- **Per-shape A/B:** same (M, N, K, dtype) on cuBLASLt-best-algo vs custom kernel,
  fixed protocol (`Perf-Experiment-Template.md`); report µs per kernel and bytes/FLOP.
- **End-to-end:** decode tok/s at B=1 and prefill TTFT — kernel wins only count if they
  survive scheduling, KV traffic, and launch overhead (`Diagnostics.md`).

## The LLM shape taxonomy: GEMM variants and why cuBLAS struggles

| GEMM variant | Shape profile | Why cuBLAS struggles | What a custom kernel adds | LLM use |
|---|---|---|---|---|
| **Skinny** | M = 1..32, N,K large | generic/heuristic path tuned for balanced shapes; tile padding + algo choice sub-optimal at tiny M [I] | GEMV-specialized: full-bandwidth streaming, vectorized loads, zero padding waste | decode projections/MLP at B=1..32 |
| **Grouped** | many GEMMs, same N,K, *different* M, one launch | strided-batched GEMM needs uniform shape per slice; MoE experts have per-expert M; N separate launches are launch-bound [A]. Newer cuBLASLt versions expose grouped GEMM [I: version-dependent — check what you ship] | one kernel, per-group offsets, work-balancing across groups | MoE expert GEMMs (arXiv:2401.06066, 2401.04088) |
| **Batched** | stack of *same-shape* GEMMs | cuBLAS serves uniform strided batches well; the gap is **ragged** batches — per-request S and paged KV aren't one uniform strided call [I] | ragged/paged batching, per-slice pointers | per-request attention projections, per-head GEMMs |
| **Quantized** | W4A16 / W8A8 / W4A4, in-kernel dequant | 4-bit weight-only (GPTQ/AWQ packed + per-group scales) is not a library input type; 8/4-bit compute paths need scale handling tuned to the model [A] | in-register dequant + scale, mixed-precision accumulate, quantized epilogue | GPTQ/AWQ/FP8/FP4 serving (arXiv:2210.17323, 2306.00978) |
| **MoE (grouped + routing)** | grouped GEMM + top-k gather/scatter fused | routing/dispatch isn't a GEMM library's job; unfused = N launches + HBM round-trips | router fused into the GEMM launch; expert GEMMs + combine in one kernel | DeepSeek/Mixtral-class MoE layers |
| **Decode (skinny + quant)** | M = 1..32 *and* W4/W8 | the compound corner: tiny-M bandwidth regime × non-library formats; library INT8/FP8 paths target balanced shapes [I] | skinny tiles + low-bit dequant in one kernel; the hottest kernel in a serving stack | production decode GEMMs |

## Grouped and skinny GEMMs: the two hardest LLM shapes

### What
Two regimes where "one GEMM" is not the right unit of work:
- **Skinny GEMM/GEMV:** M = 1..32, N,K large. The decode linear layers.
- **Grouped GEMM:** a *set* of GEMMs sharing N,K but with different M_i (tokens routed to
  expert i), computed in one kernel launch — the MoE expert path
  (`MoE-Expert-Parallelism.md`).

### Why
- **Skinny:** at M=1 the layer is a weight streamer — the kernel's only job is to hit
  DRAM peak while the MMA/ALU path idles (`GEMM.md` roofline split). Any padding,
  unvectorized load, or large-M tile choice steals bandwidth → directly steals tok/s.
- **Grouped:** with E experts, running E separate GEMMs means E launch overheads, E
  scheduler round-trips, and no cross-expert load balancing; a single grouped kernel
  streams each expert's weights once for its M_i tokens and lets the grid span all
  experts [I].

### How
- **Skinny/decode:** treat it as a memory kernel — vectorized 128-bit loads of packed
  weights, dequant + scale in registers, one K-stream per output tile, no M-padding
  (`../Quantization/README.md` for the packed formats).
- **Grouped:** pass per-group (M_i, offset) arrays; grid tiles across groups; a
  block-internal or work-stealing scheduler maps (group, tile) pairs so imbalance from
  uneven routing doesn't strand SMs [A].
- Both: fuse the epilogue (activation, quantize, top-k combine) to avoid extra HBM trips
  (`Fused-Kernels.md`).

### When
- **Skinny:** every decode step of a dense or MoE model at B ≤ ~32; also small-prefill
  chunks below the knee batch B* (`Bandwidth-vs-Compute.md`).
- **Grouped:** every MoE layer forward pass (prefill *and* decode — MoE prefill is
  grouped too, with large M_i) [I].

### Hardware impact
- **Skinny:** DRAM controller is the resource; expect `dram__throughput` ≈ peak and low
  Tensor Core utilization — that's *correct* behavior, not a bug
  (`Tensor-Cores.md`, `GPU-Metrics.md`).
- **Grouped:** SMs must stay fed across groups of differing sizes; occupancy and the
  block scheduler, not FLOPs, determine throughput [I].

### Inference impact
- **ITL:** skinny kernel quality ≈ decode tok/s at low B; bytes-per-token is the ceiling
  and the kernel decides how close you get (`../Inference/Roofline.md`).
- **MoE throughput/TTFT:** grouped GEMM removes per-expert launch overhead and exposes
  expert imbalance as an in-kernel scheduling problem instead of E sequential GEMMs
  (`MoE-Expert-Parallelism.md`).

### Example [E, hand-derived]
MoE layer: 8 experts, each expert weight `[4096 × 4096]` BF16 (33.55 MB each);
B = 256 tokens, top-k = 2, perfectly balanced → M_i = 256·2/8 = **64 tokens/expert**.
- **Naive path:** 8 separate GEMM launches, each `[64,4096]·[4096,4096]`. Per-expert
  FLOPs = 2·64·4096·4096 = **2.15 GFLOP**; total = 8 × 2.15 GFLOP = **17.2 GFLOP**;
  weight bytes streamed = 8 × 33.55 MB = **256 MiB** (each expert's weights read once —
  correct since M_i ≫ 1).
- **Grouped path:** one kernel, same 17.2 GFLOP and 256 MiB, but no inter-launch gaps and
  the scheduler can start expert j's tiles while expert i's are draining. The FLOP/byte
  budget is identical; the difference is **overhead + balance**, which at 64-token
  groups is the whole game [E: totals above; overhead claim is [I]].
- Unbalanced case (one hot expert gets 512, another 8): grouped kernel + capacity-factor
  control beats 8 sequential launches badly at the tail (`MoE-Expert-Parallelism.md`).

### Failure modes
- **Hot experts / skewed routing:** one expert's M_i dominates → its tiles become the
  critical path; needs capacity factors or rebalancing, not a faster kernel
  (`MoE-Expert-Parallelism.md`).
- **M_i = 0 (unrouted expert):** kernel must skip empty groups without serializing
  [A].
- **Skinny kernel fed a large M:** an M≤32-tuned kernel launched at M=1024 pads and
  wastes — keep the M-range in the selection key, with a fallback [A].
- **Unaligned packed weights:** 4-bit packs that aren't 128-bit aligned break the
  vectorized load path and silently halve effective bandwidth (`Memory-Hierarchy.md`).

### How to measure it
- **Skinny:** DRAM throughput vs peak and achieved tok/s at B=1; compare kernel to the
  `BW ÷ bytes-per-token` ceiling (hand-computable per `GEMM.md` Example) [E].
- **Grouped:** total kernel time vs Σ(per-expert FLOPs ÷ expected rate); check tail
  latency under skewed routing distributions; Nsight per-kernel SM occupancy
  [F: Nsight Compute docs].
- **A/B:** grouped vs E×cuBLAS launches, same token mix — report wall-time, not just
  average-expert time (`Perf-Experiment-Template.md`).

## Kernel selection: how engines pick a kernel per step
An inference engine treats the GEMM as a **lookup**: (M, N, K, dtype, arch, model-arch)
→ best kernel, decided per step because those inputs change step to step:
- **Batch size M:** decode B=1..32 → skinny/decode (often quantized) kernel; M ≥ knee
  batch B* → cuBLASLt/`Tensor-Core`-tuned dense kernel (`GEMM.md`).
- **Sequence length:** prefill S → large-M compute kernel + FlashAttention; chunked
  prefill chunks sized to land on a good M bucket [I].
- **Precision:** BF16 → cuBLASLt; FP8/INT8 → FP8 GEMM path; W4A16/W4A4 → custom
  dequant-GEMM path (`Tensor-Cores.md`'s two quantization routes).
- **GPU arch:** Hopper (TMA/wgmma, FP8) vs Blackwell (FP4/NVFP4 MMA) changes which
  mainloop is available — a kernel registered for Hopper isn't portable [A].
- **Model arch:** dense vs MoE (grouped GEMM), GQA/MLA (attention GEMM shapes)
  (`MoE-Expert-Parallelism.md`).
Engines implement this as a kernel-selection table (or runtime heuristic + optional
autotune/benchmark pass) and can override per shape [I: engine design; see
`Inference-Engines.md`, `vLLM.md` — vLLM's quant/GEMM backends and `TensorRT-LLM.md`'s
compiled kernels are the two extremes: pluggable selection vs build-time selection].

## The ecosystem and its roles
**Roles, not a list — each layer answers a different question:**
- **cuBLAS / cuBLASLt — "give me the best off-the-shelf GEMM."** The default
  high-performance GEMM library [F: NVIDIA docs]. cuBLASLt adds the *runtime*
  algorithm-selection API: `cublasLtMatmul` + `cublasLtMatmulAlgoGetHeuristic`
  (auto-pick) or explicit algo search/benchmark-and-cache — the engine's lever for
  "same GEMM, better algo" without writing a kernel [F: NVIDIA docs].
- **CUTLASS — "bring your own GEMM, professionally."** NVIDIA's C++ template library
  for building Tensor-Core GEMMs: composable mainloop + epilogue templates over the
  CuTe layout algebra, with arch-specific collectives (TMA/wgmma on Hopper-era
  kernels) [F: CUTLASS docs, github.com/NVIDIA/cutlass]. This is how shape-specialized,
  quantized, and MoE GEMM kernels are *built* — you instantiate a template for your
  (tile, layout, epilogue, dtype), not hand-roll PTX from zero [A].
- **Triton — "generate the kernel from Python."** The Python-DSL/autotune path:
  `@triton.jit` block-level programs compiled to PTX, with built-in autotuning over
  block shapes; the fast-iteration layer for fused/quantized/dequant kernels
  [F: Triton docs, github.com/triton-lang/triton; `Triton.md`]. Many engines' quant and
  fused-MoE kernels are Triton programs; FlashInfer (arXiv:2501.01005) is an example of a
  custom-kernel library built on this class of tools.
- **Custom CUDA (C++/PTX/WMMA) — "maximum control for the hottest kernel."**
  Hand-written kernels where you control every load, tile, and register; the highest
  effort and highest ceiling, used for the hottest paths: decode GEMV, fused MoE,
  exotic layouts (`CUDA-From-Zero.md`, `Kernel-Life.md`).

**How they compose** — the engine holds one selection table; each candidate layer is a
different point on the effort↔control spectrum:
```
GEMM request (M, N, K, dtype, arch, model-arch)
   │  engine kernel-selection table (per step)
   ├──► cuBLASLt  ── heuristic/search picks 1 of N built-in algos
   │     role: default large-M dense GEMM
   ├──► CUTLASS   ── compiled per (tile, layout, epilogue, dtype)
   │     role: shape-specialized / quant / MoE GEMMs
   ├──► Triton    ── @triton.jit + autotune → PTX
   │     role: fused GEMM+dequant+activation, fast iteration
   └──► custom CUDA (WMMA/PTX mma)
         role: hottest kernels, max control
   ▼
SMs / Tensor Cores / HBM  — same hardware; only the kernel differs
```
An engine picks among these **per (shape, dtype, arch)** — e.g. cuBLASLt for prefill
dense BF16, CUTLASS-built grouped GEMM for MoE, Triton dequant-GEMM for W4A16 decode,
hand-written GEMV for B=1 hot paths [I: composition pattern observed across
`Inference-Engines.md` and `vLLM.md`].

## When you'd write each (decision guide)
| Situation | Pick | Why |
|---|---|---|
| Large-M dense GEMM, standard dtype, mainstream arch | **cuBLASLt** (algo selection) | incumbent champion; hard to beat [A] |
| New arch/dtype combo with no library path yet | **CUTLASS template** | tested collectives + mainloops, arch-specific, no PTX-from-zero [F: CUTLASS docs] |
| Fused GEMM + dequant/bias/act/quant | **Triton** | iteration speed, autotune, Python; proven for quant/fused-MoE kernels [F: Triton docs] |
| MoE grouped GEMM | **CUTLASS or Triton** (custom CUDA if both fall short) | per-group offsets + epilogue fusion; effort scales with MoE complexity |
| Decode GEMV at M ≤ 32, quantized | **hand-written CUDA** (Triton to prototype first) | hottest kernel in the stack; max control of the memory path [I] |
| Prototype / research kernel | **Triton first**, port to CUDA/CUTLASS if it wins | measure before hand-rolling |
| Anything at large M where cuBLASLt already hits your roof | **don't write it** | a custom kernel that doesn't beat cuBLASLt at large M is a maintenance liability [A] |

Pitfalls: (1) **premature hand-rolling** — benchmark cuBLASLt's best algo before writing
a line; (2) **kernel regression** — verify the custom path didn't regress the *other*
regime (e.g. W4A16 decode kernel accidentally selected at large M); (3) **skip the
epilogue fusion** — the GEMM itself winning while 3 extra HBM round-trips lose
(`Fused-Kernels.md`).

## Related
`GEMM.md` (the naive→TensorCore ladder this page builds on) · `Tensor-Cores.md`
(dtype paths + the two quantization routes) · `Triton.md` · `Fused-Kernels.md` ·
`../Quantization/README.md` · `MoE-Expert-Parallelism.md` · `Inference-Engines.md` ·
`vLLM.md` · `TensorRT-LLM.md` · `Kernel-Stack.md` · `Memory-Hierarchy.md` ·
`Profiling.md` · `../Inference/Roofline.md`.

## Key Takeaways
1. **cuBLAS is the default; custom is for the corners** — skinny M, grouped MoE,
   non-library quant formats, fused epilogues.
2. **M (tokens) is the regime switch**: M=1..32 wants a bandwidth kernel; M≥B* wants an
   MMA-pipelined kernel; a generic heuristic can't be optimal on both roofs.
3. **The portfolio composes**: cuBLASLt picks an algo, CUTLASS builds a kernel, Triton
   generates one, custom CUDA is the fallback — selected per (shape, dtype, arch).
4. **Grouped GEMM changes the unit of work** from "one GEMM" to "a set of GEMMs in one
   launch" — that's the MoE expert path; skinny GEMM is its B≤32 twin.
5. **Measure per shape**: A/B the candidate kernel on the exact (M, N, K, dtype, arch)
   before trusting it; kernel wins only count if they survive the serving stack.
