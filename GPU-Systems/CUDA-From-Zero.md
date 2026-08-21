# CUDA Programming for LLM Engineers
`LAST_UPDATED: 2026-08-21 · Status: core page` · PART II of the GPU-systems zero-to-hero
path. Claims tagged [F] primary source (CUDA C Programming Guide, arXiv bank) / [A]
engineering assumption / [I] inference / [E] hand-derived arithmetic.

## 30-Second Explanation
CUDA lets you run a **kernel** — a C++ function executed by thousands of threads — on
the GPU's HBM. Host code (1) allocates device memory, (2) copies data in, (3) launches
`kernel<<<grid, block>>>(args)` so the grid of blocks is scheduled onto SMs, (4) waits,
(5) copies results out. Every LLM inference kernel (norms, adds, activations, GEMM,
attention) is built from the same five-step pattern and two rules: **map each thread to
contiguous data** (coalescing) and **keep data in fast on-chip memory as long as
possible** (shared memory, registers). Master vec-add and tiled GEMM and you can read
every engine's kernel code.

## What CUDA Is
- **CUDA** = NVIDIA's model for running code on the GPU: C++ extensions
  (`__global__`, `__device__`, `__shared__`, `__syncthreads()`) + a host-side API.
  Authoritative reference: CUDA C Programming Guide
  (https://docs.nvidia.com/cuda/cuda-c-programming-guide/) [F].
- **Runtime vs driver API:** the **runtime API** (`cudaMalloc`, `cudaMemcpy`,
  `kernel<<<>>>`) manages an implicit context and is what you use; the **driver API**
  (`cuLaunchKernel`, `cuMemAlloc`, no `<<<>>>` syntax) is the lower layer with explicit
  contexts. Runtime sits on top of the driver; cuBLAS/NCCL use both — learn runtime
  first [F].
- **Host vs device code:** host code runs on the CPU; device code (kernels,
  `__device__` helpers) runs on the GPU and sees only HBM + on-chip memory. Host code
  cannot dereference a device pointer and vice versa. A **kernel** is a `__global__`
  function: one CPU call, many threads, all from the same code — parallelism comes
  from the launch config (grid of blocks, block of threads).

## The Launch Model: `kernel<<<grid, block>>>(args)`

### What
A launch declares how to split work: `block` = threads per block, `grid` = blocks. The
hardware schedules blocks onto SMs as capacity frees up; you never schedule a thread.
`blockDim` ≤ 1024; a **warp** = 32 threads is the atomic unit of execution (SIMT: one
instruction, 32 lanes) [F: CUDA programming guide; SM/warp model in Architecture.md].

### Why
You cannot place threads on cores — thousands of small cores plus massive
thread-switching hide memory latency for you **if and only if** your split gives each
warp 32 contiguous addresses. "Writing a kernel" = choose the split, then make the
memory pattern right.

### How
- Coordinates: `threadIdx` (in block), `blockIdx` (in grid); dims `blockDim`/`gridDim`.
  The 1D **global id** formula: `i = blockIdx.x * blockDim.x + threadIdx.x` — always
  guard with `if (i < n)` (grid is a ceil-divided superset).
- 2D work: `dim3` launch; row from `y`, col from `x` — the contiguous dimension
  **must** be `x`. Mapping a 128×128 matrix with 16×16 blocks:

```
 grid (8×8 blocks = 64 blocks)                block (16×16 = 256 threads)
 ┌──────┬──────┬──────────┐                    ┌───────────────────────────┐
 │B0,0  │B1,0  │  ...     │                    │ T0,0 T0,1 ... T0,15    │← warp 0 (2
 ├──────┼──────┼──────────┤                    │ T1,0 T1,1 ... T1,15    │  rows × 16)
 │B0,1  │B1,1  │          │   block B3,4       │  ...                    │
 │ ...  │ ...  │          │   covers C rows    │ T15,0 ... T15,15       │← warp 15
 └──────┴──────┴──────────┘   C[64..79]         └───────────────────────────┘
 64 blocks → scheduled across ~132 SMs [F: H100 spec]
```

### When
Smallest block that keeps ≥ 1 work-item per thread, coalesced access; 128–256 threads
is the sweet spot [A]; size the grid with ceil division.

### Hardware impact
`threadIdx` order decides which addresses a warp's 32 lanes touch together — coalescing
is the whole argument of §1–§2. Fewer blocks than SMs idles SMs; far more is cheap
(blocks are the work unit, not the placement unit) [I].

### Inference impact
Most LLM kernels are elementwise or rowwise (norms, adds, bias, activations):
grid = rows (batch·seq), block = hidden-dim chunk. At decode batch=1 the grids are
tiny → you are **launch-bound**, not bandwidth-bound — the motivation for CUDA
Graphs + fusion (Kernel-Life.md, Fused-Kernels.md).

### Example [E]
vec-add over n = 10⁶, block = 256 → grid = ⌈10⁶/256⌉ = **3907 blocks**; block 3906
runs ids 999,936..999,999 (64 live, 192 idle). 10⁶ threads = 31,250 warps ≈ 236
warps/SM on a 132-SM H100 [E] — plenty in flight to hide HBM latency.

### Failure modes
- Missing `if (i < n)` → OOB write in the last block (silent corruption).
- Block > 1024 or not a multiple of 32 → launch fails; check `cudaGetLastError()`.
- 1D grid indexing a 2D array → strided warp accesses → 4–32× HBM cost [I].

### How to measure
`ncu` (Nsight Compute): occupancy, warp-stall reasons, sectors/request. `nsys`
(Nsight Systems): launch rate (kernels/s) when suspecting launch-bound.

## Memory: Host ↔ Device, and Synchronization

### What
HBM is **not** CPU-addressable. Every kernel argument is a **device pointer**; data
crosses the PCIe boundary only through explicit copies:

```
 HOST (CPU RAM)                        GPU (HBM)
 x_host ──cudaMalloc──► x_dev ◄──cudaMemcpy(H2D)──┐
 y_host ──cudaMalloc──► y_dev ◄──cudaMemcpy(H2D)──┤  kernel<<<grid,block>>>(x_dev,y_dev,z_dev)
                                                   │        blocks → SMs; warps → 32 lanes
 z_host ◄──cudaMemcpy(D2H)── z_dev ◄─kernel writes─┘
 host code continues only after cudaDeviceSynchronize() (or stream sync)
 finally: cudaFree(x_dev), cudaFree(y_dev), cudaFree(z_dev)
```

Core calls [F: CUDA programming guide]: `cudaMalloc`/`cudaFree`,
`cudaMemcpy`/`cudaMemcpyAsync` (H2D/D2H/H2H), `cudaHostAlloc` (pinned pages),
`cudaDeviceSynchronize` / `cudaStreamSynchronize` / `cudaEvent*`.

### Why
HBM reads are ~50× faster than moving the same bytes over PCIe (H100: 3.35 TB/s HBM
vs ~64 GB/s PCIe 5.0 x16 [F: NVIDIA specs, ../Hardware/README.md]). Discipline: copy
**once** at load, live on-chip forever, copy out only what you need (logits).

### How
```cuda
int n = 1000000;
float *x_d, *y_d, *z_d;
cudaMalloc(&x_d, n * sizeof(float));
cudaMemcpy(x_d, x_h, n * sizeof(float), cudaMemcpyHostToDevice);   // H2D
vecAdd<<<(n + 255) / 256, 256>>>(x_d, y_d, z_d, n);                // async
cudaDeviceSynchronize();                                           // wait
cudaMemcpy(z_h, z_d, n * sizeof(float), cudaMemcpyDeviceToHost);   // D2H
cudaFree(x_d); cudaFree(y_d); cudaFree(z_d);
```
- **Default stream:** launches + sync copies from one host thread run **in order** —
  the simplest correct model.
- **Streams:** named FIFOs; same-stream work is ordered, different-stream work may
  **overlap** (a copy engine + SMs at once). Engines overlap KV movement with compute;
  CUDA Graphs replay a whole stream graph in one launch (Kernel-Life.md).
- **Pinned host memory:** `cudaHostAlloc` pages let `cudaMemcpyAsync` DMA directly;
  pageable RAM forces a staging copy + implicit sync [F].

### When
Production: allocate once (weights, KV pool, activation buffers), H2D at load, D2H
only for sampling/logits. Debug: keep host mirrors and D2H-diff against CPU.

### Hardware impact
The copy path is the slow lane: 40 GB of weights ≈ 0.63 s over PCIe 5.0 [E: 40e9 ÷
64e9] but ~12 ms through HBM [E: 40e9 ÷ 3.35e12]. Kernel time is HBM-dominated
**unless** you copy every step — which you must not.

### Inference impact
Weights + KV live in HBM for the server's life, so H2D is a one-time cost; the
per-token cost is HBM reads, not PCIe (../Inference/The-Life-of-a-Token.md).
Multi-GPU turns some "copies" into NCCL collectives over NVLink (NCCL.md).

### Example [E]
n = 10⁶ floats: 4 MB/tensor; 3 copies = 12 MB over PCIe ≈ 0.19 ms [E: 12e6 ÷ 64e9]
vs the kernel moving the same 12 MB in HBM ≈ 3.6 µs [E: 12e6 ÷ 3.35e12]. Same bytes,
~50× slower per copy — load once, compute forever.

### Failure modes
- Host pointer in a kernel (or device pointer on host) → illegal address, crash.
- Reading results before `cudaDeviceSynchronize` → stale/garbage host data.
- `cudaMemcpyAsync` from pageable memory → silently synchronizes.
- No `cudaFree` → device OOM (`cudaErrorMemoryAllocation`).

### How to measure
`nsys` timeline: copy phases vs kernel phases; gaps = sync stalls. `ncu`:
`dram__throughput`. `nvidia-smi` / DCGM PCIe counters for copy saturation.

## Eight Worked Examples

Each: CPU version → GPU change → thread organization → access pattern → expected
bottleneck → profile → improve. Floats shown for clarity; production runs BF16/FP16.

### 1. Vector add: `z[i] = x[i] + y[i]`
- **CPU:** one core loops i = 0..n-1, add, store; AVX does 4–8 elements/cycle.
- **GPU change:** one **thread** per i — n threads run in parallel across SMs.
- **Threads:** 1D grid; `block = 256` (8 warps), `grid = ⌈n/256⌉`.
- **Access:** fully coalesced — lane L reads `x[base+L]`, `y[base+L]` contiguous.
- **Bottleneck:** pure HBM bandwidth (AI = 2 FLOP / 12 B ≈ 0.17 [E]) — on the flat
  memory roof of the [Roofline](../Inference/Roofline.md).
- **Profile/Improve:** `ncu` → `dram__throughput` should hit peak, SM util ≈ 0; use
  `float4` loads to cut address work — you are bandwidth-capped, so stop there.
- Pseudo: `for i in 0..n: z[i] = x[i] + y[i]` (one thread per i)

```cuda
__global__ void vecAdd(const float* x, const float* y, float* z, int n) {
  int i = blockIdx.x * blockDim.x + threadIdx.x;
  if (i < n) z[i] = x[i] + y[i];
}
// host: vecAdd<<<(n + 255) / 256, 256>>>(x_d, y_d, z_d, n);
// n = 1e6 moves 3 · 1e6 · 4 B = 12 MB [E] — the kernel's entire budget.
```

### 2. Matrix add: `C[r,c] = A[r,c] + B[r,c]`
- **CPU:** nested row loop over M·N elements, AVX-vectorized along the row.
- **GPU change:** same per-element work; the split becomes 2D.
- **Threads:** `dim3 block(32, 8)` (256); `dim3 grid(⌈N/32⌉, ⌈M/8⌉)`;
  `row = blockIdx.y*blockDim.y + threadIdx.y`, `col = blockIdx.x*blockDim.x + threadIdx.x`.
- **Access:** coalesced along `x` (contiguous col).
- **Bottleneck:** bandwidth, same as vec-add (12 B/element [E]).
- **Profile/Improve:** `ncu` — sectors/request ≈ 4 is a perfect coalesce; `float4`
  loads; this is the bandwidth ceiling, nothing more to gain.
- Pseudo: `for r in 0..M: for c in 0..N: C[r,c] = A[r,c] + B[r,c]`

```cuda
__global__ void matAdd(const float* A, const float* B, float* C, int M, int N) {
  int col = blockIdx.x * blockDim.x + threadIdx.x;
  int row = blockIdx.y * blockDim.y + threadIdx.y;
  if (row < M && col < N) C[row*N + col] = A[row*N + col] + B[row*N + col];
}
// host: dim3 b(32, 8);
//       matAdd<<<dim3((N+31)/32, (M+7)/8), b>>>(A_d, B_d, C_d, M, N);
```

### 3. Naive GEMM: `C[i,j] = Σ_k A[i,k]·B[k,j]` (one thread per output)
- **CPU:** triple loop i,j,k with k innermost; compiler vectorizes along k.
- **GPU change:** same math; each (i,j) is a thread, k-loop runs serially in
  that thread's registers.
- **Threads:** 2D grid exactly like §2.
- **Access:** `A[i*K+k]` coalesced across lanes (contiguous k), but `B[k*N+j]` is
  **strided by N** across lanes → 32 separate cache lines per warp [I].
- **Bottleneck:** HBM re-reads: A fetched N times, B M times (ignoring L2).
  M=N=K=1024: ≈ 2·1024³·4 B ≈ **8.6 GB** for 2.15 GFLOP → AI ≈ 0.25 FLOP/B [E] —
  far below the roofline.
- **Profile/Improve:** `ncu` → `dram__bytes` vs FLOPs, poor L2 hit; tile into shared
  memory (§4) — the single biggest win in CUDA.
- Pseudo: `for i,j: acc=0; for k in 0..K: acc += A[i,k]*B[k,j]; C[i,j]=acc`

```cuda
__global__ void gemmNaive(const float* A, const float* B, float* C,
                          int M, int N, int K) {
  int i = blockIdx.y * blockDim.y + threadIdx.y;
  int j = blockIdx.x * blockDim.x + threadIdx.x;
  if (i < M && j < N) {
    float acc = 0.0f;
    for (int k = 0; k < K; ++k) acc += A[i*K+k] * B[k*N+j];
    C[i*N+j] = acc;
  }
}
```

### 4. Tiled GEMM: shared-memory tiles (the big one)
- **What.** Same C = A·B, but a T×T block of threads loads `[T×T]` tiles of A and B
  into **shared memory** (per-SM SRAM) and computes its C tile from there. HBM
  traffic drops ~1/T [I].
- **Why.** In §3, thread (i,j) re-fetches A's row i N times and B's column j M times
  from HBM. Shared memory is where 32×32 threads **share** fetched data — reuse goes
  O(1) → O(T). This is the skeleton of every fast GEMM and of FlashAttention [F:
  arXiv:2205.14135].
- **Threads:** `dim3(T,T)` blocks on a `⌈M/T⌉ × ⌈N/T⌉` grid; each thread accumulates
  one C element across all k-slices.
- **When.** Any GEMM with meaningful K — i.e., all real ones; cuBLAS/CUTLASS
  implement this plus the higher rungs.
- Pseudo: block owns a T×T C tile; per k-slice: load 2 tiles → `__syncthreads()` →
  T FMAs/thread in registers → `__syncthreads()` → next slice.

```cuda
#define T 32
__global__ void gemmTiled(const float* A, const float* B, float* C,
                          int M, int N, int K) {
  __shared__ float As[T][T], Bs[T][T];
  int i = blockIdx.y * T + threadIdx.y;
  int j = blockIdx.x * T + threadIdx.x;
  float acc = 0.0f;
  for (int t = 0; t < K; t += T) {
    As[threadIdx.y][threadIdx.x] = A[i*K + t + threadIdx.x];
    Bs[threadIdx.y][threadIdx.x] = B[(t + threadIdx.y)*N + j];
    __syncthreads();                       // tile fully loaded
    for (int k = 0; k < T; ++k)
      acc += As[threadIdx.y][k] * Bs[k][threadIdx.x];
    __syncthreads();                       // done reading before overwrite
  }
  C[i*N + j] = acc;
}
// host: gemmTiled<<<dim3(N/T, M/T), dim3(T, T)>>>(A_d, B_d, C_d, M, N, K);
```

- **Access:** global loads coalesced (one element/thread per tile load); the K·T FMAs
  per thread run against shared memory + registers — no HBM in the inner loop.
- **Bottleneck:** shifts from HBM re-reads to **shared-memory bandwidth + bank
  conflicts**; still far from compute peak (no register blocking, no Tensor Cores).
- **Example [E, hand-derived].** M=N=K=1024, float, T=32:
  - HBM naive: ≈ 2·(1024·1024·4 B)·1024 ≈ **8.59 GB** (A read N×, B read M×, no L2).
  - HBM tiled: A read N/T + B read M/T times + C once ≈ 2·134.2 MB + 4.19 MB ≈
    **272 MB** → **~32× (= 1/T) less**. Shared memory per block: 2·32·32·4 B = 8 KB.
  FLOPs identical (2·1024³ = 2.15 GFLOP) — only bytes moved.
- **Profile/Improve:** `ncu` → `l1tex` wavefronts, `dram__bytes` (≈ 1/32 of §3),
  achieved AI = FLOPs/dram bytes; pad `As[T][T+1]` to break bank conflicts,
  register-block to `[4×4]`, double-buffer, then Tensor Cores (GEMM.md).
- **Failure modes.** Missing the second `__syncthreads()` → tile overwritten while
  still read (silent race); T too big for the SM's shared memory → launch fails;
  diagonal shared accesses → bank conflicts.

### 5. Reduction (sum): `s = Σ x[i]`
- **CPU:** serial accumulate; no parallelism without extra work.
- **GPU change:** hierarchical sum — each thread grid-strides a chunk → **block tree**
  in shared memory → one value per block → `atomicAdd` (or a second small kernel).
- **Threads:** 1D blocks of 256; the first 5 tree levels are "free" with warp shuffles
  — `__shfl_down_sync` moves lanes' values with no shared memory, no sync [F: guide].
- **Access:** coalesced global reads; the tree is log₂(256) = 8 steps, one warp/level.
- **Bottleneck:** not bandwidth but **tree latency + the cross-block step**; large n
  is bandwidth-bound, small n is latency-bound [I].
- **Profile/Improve:** `ncu` → `stalled_barrier`, shared-mem throughput; shuffles for
  in-warp levels, `atomicAdd` when blocks < ~1024, single-kernel reduction (last-block
  finishes trick) to kill the second launch.
- Pseudo: `partial = Σ chunk(i); s = block-tree(partial); out += atomic(s)`

```cuda
__global__ void blockReduce(const float* x, float* out, int n) {
  __shared__ float sm[256];
  int tid = threadIdx.x;
  float v = 0.0f;
  for (int i = blockIdx.x*256 + tid; i < n; i += 256) v += x[i];
  sm[tid] = v; __syncthreads();
  for (int s = 128; s > 0; s >>= 1) {      // tree: 8 steps
    if (tid < s) sm[tid] += sm[tid + s];
    __syncthreads();
  }
  if (tid == 0) atomicAdd(out, sm[0]);     // cross-block
}
```

### 6. Softmax (per-row): `y[r,j] = exp(x[r,j]−m_r) / Σ_k exp(x[r,k]−m_r)`
- **CPU:** per row: pass 1 for max (stability), pass 2 for exp+sum, pass 3 write.
- **GPU change:** one **block per row**; the row is the reduction unit.
- **Threads:** `grid = (rows)`, `block = 256`; each thread covers `d/256` via
  grid-stride.
- **Access:** coalesced along j; passes 2–3 re-read the row — for d = 4096 it stays in
  L1/L2 between passes [I], so re-reads are cheap.
- **Bottleneck:** bandwidth plus SFU load from `expf`.
- **Profile/Improve:** `ncu` → `sm__inst_executed_pipe_xu`, L2 hit on re-reads; single-
  pass online softmax, or stash exp in shared memory; in LLMs softmax lives **inside**
  attention, where FlashAttention folds it in and never materializes S×S [F:
  arXiv:2205.14135; ../Attention/README.md].
- Pseudo: `m = rowmax(x); l = Σ exp(x−m); y = exp(x−m)/l` (3 row-wise passes)

```cuda
__global__ void rowSoftmax(const float* x, float* y, int d) {
  int r = blockIdx.x, tid = threadIdx.x;
  const float* xr = x + (long)r * d;
  __shared__ float sm[256];
  float m = -INFINITY, l = 0.0f;
  for (int j = tid; j < d; j += blockDim.x) m = fmaxf(m, xr[j]);
  blockReduceMax(sm, m, &m);               // §5 tree (max) / shuffles
  for (int j = tid; j < d; j += blockDim.x) l += expf(xr[j] - m);
  blockReduceAdd(sm, l, &l);               // §5 tree (sum)
  float inv = 1.0f / l;
  for (int j = tid; j < d; j += blockDim.x)
    y[(long)r*d + j] = expf(xr[j] - m) * inv;
}
// host: rowSoftmax<<<rows, 256>>>(x_d, y_d, d);
```

### 7. LayerNorm (per-row): `y = (x−μ)·√(1/(σ²+ε))·g + b`
- **CPU:** 2 passes per row (mean, variance), then normalize.
- **GPU change:** one block per row; two block reductions (Σx, Σx²), then a normalize.
- **Threads:** `grid = (rows)`, `block = 128`.
- **Access:** coalesced; the row is read ~2–3× (stats + normalize) unless held in
  registers.
- **Bottleneck:** bandwidth — ~4·d·4 B per row FP32 [E]; FLOPs are trivial.
- **Profile/Improve:** `ncu` → `dram__bytes` vs the 3–4×-of-minimum ideal, L2 hits;
  hold the row in **registers** (d = 4096, block = 128 → 32 floats/thread, fits) so
  re-reads cost nothing, and fuse the residual add into the kernel (Fused-Kernels.md)
  — production engines do exactly this.
- Pseudo: `μ=mean(x); σ²=var(x); y=(x−μ)/√(σ²+ε)*g+b` (row-wise, 2–3 passes)

```cuda
__global__ void rowLayerNorm(const float* x, const float* g, const float* b,
                             float* y, int d) {
  int r = blockIdx.x, tid = threadIdx.x;
  const float* xr = x + (long)r * d;
  __shared__ float sm[128];
  float s = 0.0f, ss = 0.0f;
  for (int j = tid; j < d; j += blockDim.x) { s += xr[j]; ss += xr[j]*xr[j]; }
  blockReduce2(sm, &s, &ss);               // two trees (or one fused)
  float mu = s/d, rstd = rsqrtf(ss/d - mu*mu + 1e-5f);
  for (int j = tid; j < d; j += blockDim.x)
    y[(long)r*d + j] = (xr[j] - mu) * rstd * g[j] + b[j];
}
```

### 8. RMSNorm (per-row): `y = x·g / √(mean(x²)+ε)` — what LLaMA/Qwen actually run
- **CPU:** one pass for Σx², one to scale — cheaper than LayerNorm (no mean/shift).
- **GPU change:** the §7 skeleton minus the mean: one block reduction + one scale pass.
- **Threads:** `grid = (rows)`, `block = 128`.
- **Access:** coalesced; 2–3 reads of the row (Σx², then x·g) unless register-resident.
- **Bottleneck:** bandwidth: 3 arrays × d × 4 B = **48 KB/row** at d = 4096 FP32 [E];
  at small batch the kernel is tiny, so **launch overhead** dominates, not bytes [I].
- **Profile/Improve:** `nsys` / torch profiler — count norm launches per step (2×L per
  token!); fuse residual add + RMSNorm (`x = h + x; y = rms(x)` — one fewer HBM
  round-trip + one fewer launch, Fused-Kernels.md); register-resident row; capture the
  step in CUDA Graphs at decode batch (Kernel-Life.md).
- **Why it matters for LLMs:** pre-norm decoders run `x' = x + Attn(RMSNorm(x))`,
  `y = x' + MLP(RMSNorm(x'))` [F: RMSNorm arXiv:1910.07467; LLaMA arXiv:2302.13971;
  Qwen2.5 arXiv:2412.15115] → **2L RMSNorm kernels per token** (64 at L = 32). Each is
  tiny; the real cost is launches + HBM footprint — exactly what fusion/graphs attack.
- Pseudo: `ss = Σ x²; rstd = 1/√(ss/d + ε); y = x * rstd * g`

```cuda
__global__ void rowRMSNorm(const float* x, const float* g, float* y, int d) {
  int r = blockIdx.x, tid = threadIdx.x;
  const float* xr = x + (long)r * d;
  __shared__ float sm[128];
  float ss = 0.0f;
  for (int j = tid; j < d; j += blockDim.x) ss += xr[j]*xr[j];
  blockReduceAdd(sm, ss, &ss);             // §5 tree / shuffles
  float rstd = rsqrtf(ss/d + 1e-6f);
  for (int j = tid; j < d; j += blockDim.x)
    y[(long)r*d + j] = xr[j] * rstd * g[j];
}
// host: rowRMSNorm<<<rows, 128>>>(x_d, g_d, y_d, d);
```

## The Recurring Pattern (and where it leads)

Every kernel above — and essentially every kernel in an inference engine — is the same
four-step recipe:
1. **Pick a grid/block** that covers the data with ~1 work-item per thread and enough
   in-flight warps to hide HBM latency.
2. **Map thread → element** with `blockIdx × blockDim + threadIdx` (+ bounds check).
3. **Coalesce:** the warp's 32 lanes must touch 32 contiguous addresses.
4. **Minimize HBM round-trips:** shared-memory tiles for reuse (§4), one-row-per-block
   for rowwise stats (§6–8), register-resident rows, and fusion to delete round-trips
   entirely (Fused-Kernels.md).

§1–3 are bandwidth-bound; §4 is where compute starts to matter (GEMM.md); §5–8 are the
LLM glue that makes or breaks decode latency. Next pages: `./Fused-Kernels.md` (why
§7+§8 fuse with the residual add), `./GEMM.md` (the §3→§4→Tensor-Core ladder in full),
`./Kernel-Life.md` (what happens after `<<<`), `./Triton.md` (writing §1–§8 without C++).

## Related
`../Inference/The-Life-of-a-Token.md` · `../Inference/Roofline.md` · `./Architecture.md`
· `./GEMM.md` · `./Fused-Kernels.md` · `../Attention/README.md` · `./Kernel-Life.md` ·
`./Memory-Hierarchy.md` · `./Profiling.md`

## Key Takeaways
1. A kernel = one function + a launch config; you choose the split, the hardware
   schedules the warps.
2. `i = blockIdx.x * blockDim.x + threadIdx.x` + bounds check + coalesced access is
   80% of writing correct fast CUDA.
3. HBM and PCIe differ ~50× per byte → copy once, compute on-chip, sync explicitly.
4. Shared-memory tiling cuts GEMM HBM traffic ~1/T — the core idea behind every
   advanced LLM kernel.
5. Norms/reductions are tiny; their cost is **launch overhead + HBM footprint**, which
   is what fusion and CUDA Graphs target in real engines.
