# Triton for LLM Kernel Engineers
`LAST_UPDATED: 2026-08-21 · Status: core page` · PART IX of the GPU-systems zero-to-hero
path. Claims tagged [F] primary source (Triton repo/docs, PyTorch docs) / [A] engineering
assumption / [I] inference / [E] Python-verified arithmetic.

## 30-Second Explanation
**Triton** is OpenAI's language + compiler for writing GPU kernels **in Python**: you
describe how one *program* handles a **block (tile) of data** — `tl.load`/`tl.store` over
tensors — and the compiler lowers that to PTX, deciding warp partitioning, shared-memory
layout, and SM scheduling for you [F: github.com/triton-lang/triton; triton-lang.org docs].
The shift vs CUDA: you stop managing 32 threads in a warp and start moving on 2D/3D
**tiles** — the compiler does the warp-level work. `@triton.autotune` benchmarks
block-size/warp/stage configs and picks the best per shape. This is also why Triton
matters at the framework level: `torch.compile`'s **Inductor** backend *emits* Triton
kernels for fused ops, and engines (vLLM, SGLang) ship Triton-based custom kernels.
Expect near-CUDA performance for most fused ops [A]; hand-written CUDA/CUTLASS or
cuBLAS/FlashInfer still win on the hottest kernels.

## What
A **Triton kernel** is a `@triton.jit`-decorated Python function. The compiler specializes
it over **constexpr** values (block sizes, dtypes) and non-constexpr args (pointers, shape
integers); on launch it JIT-compiles to PTX per (config, shape, arch) and caches the
binary [F: Triton docs]. The program's unit of work is a **block of data**: the kernel
body operates on whole tensors (`tl.arange(0, BLOCK)`), not individual threads.
**Program** = one instance of the kernel launched over one tile; a **grid** = the set of
programs. You never mention warps, shared memory, or `__syncthreads()`.

## Why
Three reasons LLM engineers write Triton instead of CUDA C++:
1. **Tile-level reasoning matches kernel design.** A GEMM *is* a tiling problem
   (`GEMM.md`); Triton makes the tile first-class instead of forcing a manual 32-lane
   warp partition.
2. **Fusion is cheap.** Epilogues (bias + activation), row reductions, dequant + GEMM
   are a few lines in the loop body — the register plumbing CUDA needs disappears
   (`Fused-Kernels.md`).
3. **It is the compiler-generated kernel.** Inductor emits Triton, so knowing Triton
   means you can read (and rewrite) what `torch.compile` produces.

## How — the mental model shift, and the core primitives
### From warps to tiles
In CUDA (§CUDA-From-Zero.md) you compute `i = blockIdx.x * blockDim.x + threadIdx.x`,
guard bounds, coalesce lanes, and synchronize shared memory yourself. In Triton each
**program** owns a slice of the output: it computes an *offset vector*, loads a block of
values **as one tensor**, operates on the whole tensor, and stores it. The compiler maps
that tensor across the warps of the assigned SMs — coalescing, vectorization, and
shared-memory staging are compiler decisions you influence with block sizes and
`num_warps`/`num_stages`, not with lane-level code [F: Triton docs].

```
 grid: 977 programs                        one program (BLOCK = 1024)
 ┌──────┬──────┬─────┐                      off = pid * 1024 + [0..1023]
 │P0    │P1    │ ... │                      mask = off < n       ← tail guard
 ├──────┼──────┼─────┤   P3 loads           x = tl.load(x + off, mask=mask)
 │P3 ..│      │     │   1024 floats        y = tl.load(y + off, mask=mask)
 └──────┴──────┴─────┘   AS ONE TENSOR     tl.store(out + off, x + y, mask=mask)
 programs → scheduled onto SMs
 (compiler picks warp partitioning, vector widths, shared-memory layout)
```

### The primitives
- **`@triton.jit`** — marks a function as a kernel; `tl.program_id(axis)` is the program's
  coordinate in the grid.
- **Block size (`BLOCK`, `BM`/`BN`/`BK`)** — the tile per program. Passed as
  `tl.constexpr` so the compiler can unroll and specialize; must be a power of two.
- **Pointers** — kernel args are raw device pointers; `ptr + off` builds addresses.
- **`tl.load` / `tl.store`** — vectorized load/store of a block; `mask=` handles tails
  (no OOB access — the Triton equivalent of CUDA's `if (i < n)`), `other=` supplies the
  masked value.
- **Grid / launch model** — `kernel[grid_size](args)` launches `grid_size` programs;
  grid size = ⌈work / tile⌉. 1D, 2D, or 3D grids work like CUDA's `gridDim`
  [F: Triton docs].
- **Reductions / matmul** — `tl.max(x, axis=0)`, `tl.sum(x, axis=0)`, `tl.dot(a, b)`
  (the latter maps to Tensor Core MMA when dtypes/shapes allow [F: Triton docs]).

## When
- **Use Triton for:** fused elementwise/reduction ops, custom (skinny/grouped/quantized)
  GEMMs, attention variants, anything you'd otherwise fuse by hand in CUDA.
- **Use CUDA C++/CUTLASS for:** the single hottest kernels where you need exact warp
  control or Tensor-Core scheduling (see tradeoffs at the end of this page).
- **Use plain PyTorch** when the op is already a library call (matmul → cuBLAS) — don't
  hand-write a GEMM a tuned library already beats on large-M shapes.

## Hardware impact
You no longer choose warp count, register tile, or bank-conflict-free shared layouts
directly — the compiler does. Your knobs (BLOCK, `num_warps`, `num_stages`) still set the
hardware regime: bigger tiles → more shared-memory residency per SM; more `num_stages` →
deeper software pipelining of the K-loop (async copy of the next tile while computing on
the current one [I]). On H100 a `[128×128]` FP32 GEMM tile's shared footprint is
2·128·128·4 B = **128 KB** [E] — inside the SM's ~228 KB shared/L1 carveout
[F: NVIDIA H100 spec], so one program's tiles fit on one SM.

## Inference impact
- **Fused epilogues** (GEMM + bias + activation, `Fused-Kernels.md`) cut an HBM
  round-trip per linear layer → directly lowers decode latency (ITL) and prefill TTFT.
- **Custom GEMM shapes** (decode M=1..32, grouped MoE) are where Triton kernels beat the
  default cuBLAS pick (`Custom-GEMM.md`) — that is where engines differentiate.
- **Compiler path:** if the model runs under `torch.compile`, your pointwise ops may
  *already* be fused Triton kernels — know which layer you're optimizing.

## Example [E, Python-verified]
Vec-add, n = 10⁶, BLOCK = 1024: grid = ⌈10⁶/1024⌉ = **977 programs** (last program has
576 live lanes); bytes moved = 3·10⁶·4 B = **12 MB** → HBM floor ≈ 12e6 ÷ 3.35e12 ≈
**3.6 µs** on H100 [E]. Arithmetic intensity = 2 FLOP / 12 B ≈ 0.17 — flat on the memory
roof of the [Roofline](../Inference/Roofline.md); no kernel beats the bandwidth ceiling.

## Failure modes
- **Missing mask** → OOB read/write on the tail (silent corruption, like CUDA's missing
  `if (i < n)`).
- **BLOCK not a power of two** (or too small for the data) → compile error or bad
  vectorization; `tl.arange` needs power-of-two extents.
- **Autotune in the hot path** → first-call latency spikes (configs are benchmarked on
  the first call per key shape); warm up or cache the config (`Custom-GEMM.md` notes the
  same for cuBLASLt).
- **Assuming `tl.dot` = Tensor Cores** — wrong dtype/shape falls back to FMA path [I].
- **Ignoring Inductor:** hand-writing a kernel for an op that torch.compile would fuse
  better (or vice versa — a graph break disabling fusion, `Kernel-Stack.md`).

## How to measure it
- **Nsight Systems** — kernel durations + launch gaps (is the Triton kernel even the
  bottleneck? `Profiling.md`).
- **Nsight Compute** — Triton compiles to a named PTX kernel, so all `ncu` metrics apply:
  `dram__throughput`, `sm__throughput`, shared-memory occupancy, achieved occupancy.
- **`torch.profiler`** — when the kernel came from Inductor, it shows up under the
  fused-op name; compare fused vs eager kernel counts.
- **Triton's own benchmark** — `triton.testing.perf_hit` / the tutorial's bench harness:
  sweep M/N/K, plot TFLOP/s vs cuBLAS to see where your kernel wins.

## Autotuning: `@triton.autotune`
You cannot pick one tile for all shapes (large-M prefill wants big BM/BN; skinny decode
M wants small M-tiles, maybe split-K). `@triton.autotune` turns the config space into a
benchmark:

```python
import triton
import triton.language as tl

@triton.autotune(
    configs=[
        triton.Config({'BM': 128, 'BN': 128, 'BK': 64, 'GROUP_M': 8},
                      num_warps=8, num_stages=3),
        triton.Config({'BM': 64,  'BN': 128, 'BK': 64, 'GROUP_M': 4},
                      num_warps=4, num_stages=3),
        triton.Config({'BM': 32,  'BN': 128, 'BK': 64, 'GROUP_M': 4},
                      num_warps=4, num_stages=4),
    ],
    key=['M', 'N', 'K'],   # re-benchmark when these change
)
@triton.jit
def gemm_kernel(a_ptr, b_ptr, c_ptr, M, N, K,
                BM: tl.constexpr, BN: tl.constexpr, BK: tl.constexpr,
                GROUP_M: tl.constexpr):
    ...  # body identical to the plain kernel below
```

Mechanism [F: Triton docs]: on the first call for a given `key`, Triton runs each config
with warmup + a timed benchmark, picks the fastest, and caches the choice keyed by the
`key` values. Later calls with the same key skip straight to the winner. Consequences:
first-call cost scales with #configs (hence the warm-up failure mode above), and the
`key` should include every shape that matters (a decode engine keys on M, N, K, dtype,
arch). This is Triton's answer to cuBLASLt's runtime algo selection — one knob, many
tile/warp/pipeline variants.

## Four Worked Examples

Same format as CUDA-From-Zero.md: what it computes → kernel → program organization →
expected bottleneck → profile → improve.

### 1. Vector add: `z[i] = x[i] + y[i]`
- **What:** elementwise add; the Triton "hello world" and the canonical first kernel in
  the official tutorial [F: Triton docs].
- **Programs:** 1D grid, ⌈n/BLOCK⌉ programs, each handles BLOCK contiguous elements.
- **Bottleneck:** HBM bandwidth — 12 B/element (2 read + 1 write, FP32), AI ≈ 0.17 [E,
  same as CUDA-From-Zero.md §1]; flat on the memory roof.
- **Profile/Improve:** `ncu` → `dram__throughput` near peak, SM util ≈ 0 → done, stop
  optimizing. Larger BLOCK and `num_warps` only help up to the point where the tile
  saturates memory; beyond that, nothing.

```python
import triton
import triton.language as tl

@triton.jit
def add_kernel(x_ptr, y_ptr, out_ptr, n, BLOCK: tl.constexpr):
    pid = tl.program_id(0)
    off = pid * BLOCK + tl.arange(0, BLOCK)
    mask = off < n                      # tail: no OOB access
    x = tl.load(x_ptr + off, mask=mask)
    y = tl.load(y_ptr + off, mask=mask)
    tl.store(out_ptr + off, x + y, mask=mask)

def add(x, y, out, n, BLOCK=1024):
    add_kernel[(triton.cdiv(n, BLOCK),)](x, y, out, n, BLOCK=BLOCK)
```

Note the entire "warp management" of the CUDA version — `threadIdx`, coalescing,
vector loads — is gone: `off` is a vector, `tl.load` is a block operation.

### 2. Softmax (per-row): `y[r,:] = exp(x[r,:]−m_r) / Σ_k exp(...)`
- **What:** one block row of a `[rows × d]` activation (e.g. attention logits before
  paged-KV lookup, or a classifier head). CUDA version: `./CUDA-From-Zero.md` §6
  (one block per row, grid-stride, two shared-memory reductions).
- **Programs:** grid = rows; each program loads its whole row as one vector and does
  `tl.max` / `tl.sum` — block reductions the compiler lowers for you.
- **Bottleneck:** bandwidth — reads x twice (max pass, exp pass) + writes once; for
  rows=1024, d=4096 FP32 that's 3 × 16.8 MB ≈ **50.3 MB (48 MiB)** of HBM traffic,
  floor ≈ 50.3e6 ÷ 3.35e12 ≈ **15 µs** [E]. Plus SFU (`exp`) issue, usually hidden.
- **Fusion opportunity:** the CUDA kernel runs 3 passes over the row in registers/shared
  memory; Triton's single-pass form loads once, computes max/exp/sum on the same block
  tensor, writes once — one fewer HBM/L2 round-trip than a naive 3-kernel or 3-launch
  decomposition. In attention, this softmax is normally *further* fused: FlashAttention
  folds it into the QKᵀ·V loop and never materializes the S×S row at all
  (`FlashAttention.md`).
- **Profile/Improve:** `ncu` → `dram__bytes` vs the 3× minimum; if the row doesn't fit
  one block (`BLOCK < d`), the compiler grid-strides internally — check L2 hits on the
  re-read. For d up to 32K, one program per row with `BLOCK = next_power_of_2(d)`
  keeps everything register/shared-resident [A].

```python
@triton.jit
def row_softmax_kernel(x_ptr, out_ptr, d, BLOCK: tl.constexpr):
    row = tl.program_id(0)
    off = tl.arange(0, BLOCK)
    mask = off < d
    x = tl.load(x_ptr + row * d + off, mask=mask, other=-float('inf'))
    m = tl.max(x, axis=0)                       # row max (stability)
    e = tl.exp(x - m)
    l = tl.sum(e, axis=0)                       # row sum of exps
    tl.store(out_ptr + row * d + off, e / l, mask=mask)

def row_softmax(x, out, rows, d):
    row_softmax_kernel[(rows,)](x, out, d,
                                BLOCK=triton.next_power_of_2(d))
```

### 3. Matrix multiplication (tiled GEMM) — the canonical Triton tutorial
- **What:** `C[M,N] = A[M,K] · B[K,N]` with 2D output tiling. This is the kernel the
  Triton tutorials build and is the same tiled-GEMM ladder as `GEMM.md` §4 and
  `./CUDA-From-Zero.md` §4 — but the shared-memory tile, the syncs, and the k-loop
  pipeline are all inferred by the compiler from `tl.dot` + the loop.
- **Programs:** grid = ⌈M/BM⌉ × ⌈N/BN⌉ (flattened to 1D); program (pid_m, pid_n) owns a
  `[BM×BN]` tile of C, accumulated over k-slices of `[BM×BK] × [BK×BN]`. `GROUP_M`
  orders pids for L2 locality across SMs (M-grouped ordering — the same reason CUTLASS
  uses rasterization orders).
- **Bottleneck:** for M=N=K=1024 FP32, 2·1024³ = **2.15 GFLOP** [E]; HBM floor with
  BM=BN=128: A read N/BN = 8×, B read M/BM = 8×, plus C → ≈ **71.3 MB (68 MiB)** [E],
  i.e. ~120× less than the untiled ~8.59 GB [E] (same arithmetic as GEMM.md §4, T=32
  gave ~32×; here the tile is 4× the edge). Real cost is FLOPs, not bytes, at this shape.
- **Profile/Improve:** `ncu` → `sm__throughput` + `sm__inst_executed_pipe_tensor` (is
  `tl.dot` on the Tensor-Core path for your dtype?), shared-memory occupancy, L2 hit on
  A/B tiles. Sweep BM/BN/BK/`num_warps`/`num_stages` via `@triton.autotune` (§above).
  Compare against cuBLASLt on the same shape: for large-M dense GEMM, cuBLAS usually
  wins [A] — Triton's value here is the *fusability* of the kernel (next example) and
  the shapes cuBLAS doesn't specialize (`Custom-GEMM.md`).

```python
@triton.jit
def gemm_kernel(a_ptr, b_ptr, c_ptr, M, N, K,
                BM: tl.constexpr, BN: tl.constexpr, BK: tl.constexpr,
                GROUP_M: tl.constexpr):
    pid = tl.program_id(0)
    num_pid_m, num_pid_n = tl.cdiv(M, BM), tl.cdiv(N, BN)
    in_group = GROUP_M * num_pid_n
    gid = pid // in_group
    first_m = gid * GROUP_M
    size_m = min(num_pid_m - first_m, GROUP_M)
    pid_m = first_m + (pid % in_group) % size_m
    pid_n = (pid % in_group) // size_m

    rm = pid_m * BM + tl.arange(0, BM)
    rn = pid_n * BN + tl.arange(0, BN)
    acc = tl.zeros((BM, BN), dtype=tl.float32)
    for k in range(0, K, BK):
        rk = k + tl.arange(0, BK)
        a = tl.load(a_ptr + rm[:, None] * K + rk[None, :],
                    mask=(rm[:, None] < M) & (rk[None, :] < K), other=0.0)
        b = tl.load(b_ptr + rk[:, None] * N + rn[None, :],
                    mask=(rk[:, None] < K) & (rn[None, :] < N), other=0.0)
        acc = tl.dot(a, b, acc)
    tl.store(c_ptr + rm[:, None] * N + rn[None, :], acc,
             mask=(rm[:, None] < M) & (rn[None, :] < N))
```

(Host launch: `gemm_kernel[(num_pid_m * num_pid_n,)](a, b, c, M, N, K, BM=128, BN=128,
BK=64, GROUP_M=8, num_warps=8, num_stages=3)` — or drop the constants into
`@triton.autotune`.)

### 4. Fused activation: GEMM + bias + ReLU epilogue
- **What:** `C = relu(A·B + bias)` in one kernel — the pattern behind every linear layer
  with activation in a Transformer MLP/QKV. The unfused version is GEMM (writes C to HBM)
  then bias-add + ReLU (reads C, writes C again).
- **The fusion:** the epilogue runs *in registers/shared* on the accumulator, before the
  tile is ever stored. For M=N=1024 FP32 that saves a full extra read+write of C:
  2 × 4.19 MB = **8.4 MB (8 MiB)** [E] of HBM traffic, and one kernel launch.
- **Programs:** identical grid to §3; the only body change is two lines after the loop.
- **Bottleneck:** same GEMM regime as §3 (compute-bound for large M; bandwidth-bound for
  skinny M where the epilogue's C write dominates).
- **Profile/Improve:** compare total `dram__bytes` of fused vs unfused — the saved
  C-round-trip shows up directly; for decode-scale M (1..32) this fusion plus
  autotuned small M-tiles is frequently better than "cuBLAS GEMM + aten bias_add +
  aten.relu" (`Custom-GEMM.md`, `Fused-Kernels.md`). The same epilogue slot is where
  SwiGLU (gate/up GEMMs + elementwise multiply) and quant-dequant GEMMs go.

```python
@triton.jit
def gemm_bias_relu_kernel(a_ptr, b_ptr, bias_ptr, c_ptr, M, N, K,
                          BM: tl.constexpr, BN: tl.constexpr, BK: tl.constexpr,
                          GROUP_M: tl.constexpr):
    # ... pid_m / pid_n / rm / rn / k-loop: exactly gemm_kernel's body ...
    pid = tl.program_id(0)
    num_pid_m, num_pid_n = tl.cdiv(M, BM), tl.cdiv(N, BN)
    in_group = GROUP_M * num_pid_n
    gid = pid // in_group
    first_m = gid * GROUP_M
    size_m = min(num_pid_m - first_m, GROUP_M)
    pid_m = first_m + (pid % in_group) % size_m
    pid_n = (pid % in_group) // size_m
    rm = pid_m * BM + tl.arange(0, BM)
    rn = pid_n * BN + tl.arange(0, BN)
    acc = tl.zeros((BM, BN), dtype=tl.float32)
    for k in range(0, K, BK):
        rk = k + tl.arange(0, BK)
        a = tl.load(a_ptr + rm[:, None] * K + rk[None, :],
                    mask=(rm[:, None] < M) & (rk[None, :] < K), other=0.0)
        b = tl.load(b_ptr + rk[:, None] * N + rn[None, :],
                    mask=(rk[:, None] < K) & (rn[None, :] < N), other=0.0)
        acc = tl.dot(a, b, acc)
    bias = tl.load(bias_ptr + rn, mask=rn < N, other=0.0)
    c = tl.maximum(acc + bias[:, None], 0.0)    # ReLU epilogue in-register
    tl.store(c_ptr + rm[:, None] * N + rn[None, :], c,
             mask=(rm[:, None] < M) & (rn[None, :] < N))
```

## torch.compile / Inductor relationship (the "compiler generates kernels" path)

### What
`torch.compile(model)` [F: PyTorch docs] captures the model's op graph (torch.fx), and
**Inductor** — the default backend compiler — (1) fuses adjacent pointwise/reduction ops
into single kernels, (2) chooses a codegen target per fused region: cuBLAS for plain
matmul, **Triton for the fused kernels**, aten fallbacks otherwise, and (3) can capture
the result as a CUDA Graph. The emitted Triton source is inspectable via
`TORCHINDUCTOR_PRINT_KERNELS` / the autotune logs.

### Why
This is the other route to "fast kernels on the SMs" besides hand-written CUDA
(`Kernel-Stack.md`): you write model code, and the compiler *generates* the kernel —
often a fused GEMM+bias+activation or a fused norm — at a quality close to hand-fused
CUDA [A]. For many LLM layers, Inductor's generated Triton kernels are what actually run
under `torch.compile`.

### How
Flow: `model(x)` eager → graph capture (graph breaks force eager fallback — the classic
failure mode) → fusion passes (e.g. `add` + `relu` + `mul` into one pointwise kernel;
bias folded into a GEMM epilogue) → Triton codegen per fused region → PTX → SM.
`mode="max-autotune"` [F: PyTorch docs] additionally benchmarks Triton tile configs
(Inductor drives the same autotune machinery as `@triton.autotune`) and cuBLASLt algos.

### When
Production serving: keep `torch.compile` on the hot model path, keep hand-written
Triton/CUDA for the few kernels Inductor fuses poorly. Debug: when a graph break shows,
you've lost the fusion — fix the break, don't hand-roll the kernel.

### Hardware impact
None direct — Inductor decides the Triton config; the hardware sees the same
program/tile mapping as a hand-written kernel. The lever you control is *which* ops get
fused (no break, right dtypes, no in-place aliasing that blocks fusion).

### Inference impact
Fused kernels cut per-layer HBM round-trips and launches → lower TTFT and ITL; on
decode (many tiny kernels), launch-count reduction alone can dominate — same story as
`Fused-Kernels.md`, but automated.

### Example
`y = F.linear(x, W) + b; y = F.relu(y)` eager = 3 kernels (GEMM, bias, relu) + 2 extra
HBM passes over C. Inductor: 1 Triton GEMM kernel with the bias+ReLU epilogue
(example 4 above, shape-specialized by the compiler) — the saved traffic and launch are
exactly the 8.4 MB + 1 launch computed there [E] (for M=N=1024 FP32).

### Failure modes
- **Graph break** → eager fallback → no fusion, no CUDA-Graph capture.
- **Autotune noise:** max-autotune benchmarks on first call; on a serving box the first
  request pays the cost — pre-warm per shape.
- **Bad codegen choice:** Inductor may pick a Triton kernel where a cuBLAS call would be
  faster on your shape (or vice versa); check `TORCHINDUCTOR_LOG` + profile.
- **Non-compilable ops** (dynamic control flow, host callbacks) → fallback or error.

### How to measure it
- `TORCHINDUCTOR_LOG=1` / `TORCHINDUCTOR_VERBOSE=1` — see the generated Triton + the
  config Inductor autotuned to.
- `torch.profiler` — kernel list: count of kernels/step before vs after compile; names
  like `triton_poi_fused_add_relu_…` are Inductor-emitted Triton.
- A/B: `mode="reduce-overhead"` vs eager end-to-end tok/s on your workload
  (`Perf-Experiment-Template.md`).

## CUDA C++ vs Triton vs PyTorch (framework level)

| aspect | CUDA C++ | Triton | PyTorch (framework) |
|---|---|---|---|
| **control granularity** | Thread: warps, lanes, explicit shared mem, `__syncthreads`, bank conflicts | Tile/block: 2D tensor ops; compiler lowers to warps; `num_warps`/`num_stages` as knobs | Whole tensor ops (`nn.Linear`, `F.softmax`); no memory-level control |
| **boilerplate** | High: pointers, syncs, coalescing, launch config, dtype plumbing | Medium: grid function + masks + constexpr tiles | Minimal: model code |
| **portability** | NVIDIA-only (PTX/SASS) | NVIDIA primary, AMD backend; one source, new backends possible [F: Triton docs] | Cross-vendor via backends/compilers |
| **autotune** | Manual (cuBLASLt algo search, hand-written tile variants) | Built-in `@triton.autotune` (benchmarks configs, caches per key) | Inductor autotune; cuBLASLt heuristics under eager |
| **when to use** | Hottest single kernels, Tensor-Core scheduling, CUTLASS templates, max control | Fused ops, custom/skinny/quant GEMM, attention variants, fast research iteration | Default: application code; let the compiler fuse |
| **typical perf ceiling** | Highest achievable (vendor libs + hand-tuned CUTLASS define the ceiling) | Near-CUDA for most fused ops [A]; below tuned cuBLAS/CUTLASS on some hot GEMM/attention shapes [I] | = whatever the backend emits (cuBLAS + fused Triton); fusion usually wins vs eager |

## Why Triton became central to the AI kernel ecosystem
1. **It is Inductor's kernel backend.** `torch.compile` made fused-kernel codegen a
   default PyTorch path, and Inductor emits Triton for it — so every `torch.compile`
   user is implicitly a Triton user (`Kernel-Stack.md`, "Compiler / Runtime" layer).
2. **Research speed.** A fused attention/GEMM experiment is an afternoon in Python, not
   a week of C++ + `ncu` archaeology; the mental model (tiles, not warps) matches how
   kernel design is actually reasoned about in the ML literature [I].
3. **Engines ship Triton kernels.** vLLM and SGLang use Triton for custom ops
   (quant/dequant GEMM, fused norms, paged-attention glue, sampling) where CUDA C++ would
   need a separate build farm per arch [I]; the README table of `Kernel-Stack.md` lists
   Triton as the extensibility layer for both.
4. **The "compiler path" vs "hand-written path"** now coexist: hand-written
   CUDA/CUTLASS for the known-hottest kernels (cuBLAS GEMM, FlashAttention-class
   attention, FlashInfer paged attention); Triton (hand or Inductor-generated) for the
   long tail of fused, shape-specialized ops.

## Tradeoffs: where Triton's ceiling is
- **Very hot GEMMs / attention:** on large-M dense GEMM and on the attention core,
  tuned cuBLAS/CUTLASS or specialized libraries (FlashInfer) can still beat Triton —
  the vendor kernels exploit Tensor-Core scheduling, warp specialization, and TMA more
  deeply than a general tile-level DSL can [I]. Frame it as an expectation, not a
  measurement: on some shapes Triton's ceiling sits below a tuned CUTLASS GEMM [A].
- **First-call latency** (autotune benchmarking) and **debug difficulty** (the generated
  PTX is what you profile; reading a compiler's warp layout is harder than reading your
  own C++).
- **The hedge:** keep Triton for fusion and shape-specialization (where it beats the
  unfused baseline by construction), keep vendor/hand-written CUDA for the 2–3 kernels
  that dominate your profile — and re-measure after any model/hardware change
  (`Cross-Layer-Optimization.md`).

## Related
`./CUDA-From-Zero.md` (the thread-level baseline) · `./GEMM.md` · `./Custom-GEMM.md` ·
`./Fused-Kernels.md` · `./Kernel-Stack.md` (stack position: L2/L3) · `./FlashAttention.md` ·
`./Tensor-Cores.md` · `./Profiling.md` · `../Inference/Inference-Optimization.md` ·
`../Inference/Roofline.md`.

## Key Takeaways
1. Triton = Python DSL + compiler: you own the **tile**, the compiler owns the **warp**.
2. `tl.load/store` + mask + `tl.program_id` + a grid function = the entire programming
   model; autotune removes per-shape tile guesswork.
3. Fused epilogues (bias/activation, GEMM+bias+ReLU) are the highest-leverage Triton
   pattern in LLMs — they cut HBM round-trips and launches, the decode killers.
4. `torch.compile` → Inductor → **emits Triton** — the compiler-generated kernel path
   coexists with hand-written CUDA; know which path your model is on.
5. Ceiling: near-CUDA for most fused ops [A]; cuBLAS/CUTLASS/FlashInfer still win the
   hottest GEMM/attention shapes — use Triton for the long tail, libraries for the core.
