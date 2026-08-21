# The LLM Kernel Stack — Where Every Layer Plugs In
`LAST_UPDATED: 2026-08-21 · Status: core page` · This is the "where do I stand" map of the
handbook. If you only remember one picture, remember this one.

## 30-Second Explanation
An LLM token does not run on "a GPU" — it runs through a **stack of layers**, each of which
translates the next-higher intent into the next-lower mechanism. PyTorch says "multiply
these tensors"; the compiler says "fuse these three ops"; Triton/CUDA/CUTLASS says "launch
this kernel with this tile size"; cuBLAS/cuDNN/custom kernels say "issue these Tensor Core
MMA instructions"; the CUDA runtime says "put these warps on these SMs"; the SM says
"execute these FMAs"; HBM says "here are the bytes." **Every optimization in this
handbook is a decision made at one of these layers.** Knowing which layer a knob lives in
is the first skill of GPU-systems engineering.

```
┌──────────────────────────────────────────────────────────────┐
│  LLM Framework        PyTorch / JAX / vLLM / SGLang / TRT-LLM│
│  (ops, scheduler, KV mgmt, batching)                         │
├──────────────────────────────────────────────────────────────┤
│  Compiler / Runtime     torch.compile / Inductor / Triton    │
│  (graph capture, fusion, codegen, CUDA Graphs)               │
├──────────────────────────────────────────────────────────────┤
│  Kernel layer           Triton kernels · CUTLASS · CUDA C++  │
│  (the actual GPU programs: GEMM, attention, norm, dequant)   │
├──────────────────────────────────────────────────────────────┤
│  Math libraries         cuBLAS / cuBLASLt / cuDNN / FlashInfer│
│  (optimized, shape-specialized, autotuned)                   │
├──────────────────────────────────────────────────────────────┤
│  CUDA Runtime           streams, events, Graphs, allocators  │
├──────────────────────────────────────────────────────────────┤
│  GPU hardware           SMs · Tensor Cores · shared/L1/L2     │
├──────────────────────────────────────────────────────────────┤
│  Memory                 HBM3e · HBM3 · GDDR7                │
└──────────────────────────────────────────────────────────────┘
   Interconnect: NVLink / NVSwitch (intra-node) · PCIe · IB/RoCE (inter-node)
```

## Each layer, in one paragraph

### LLM Framework (PyTorch / vLLM / SGLang / TRT-LLM)
The **top** layer. It owns the *semantic* model: the transformer loop, the KV cache
manager, the batch scheduler, the continuous-batching logic, the sampling. It decides
**what** to compute (which tokens, in which batch, with which KV blocks) and issues
framework-level ops. It does **not** write GPU instructions. Inference engines live here
and they are where `../Serving-Engines/vLLM.md` · `SGLang.md` · `TensorRT-LLM.md` live.
**Knobs:** model choice, TP/PP/EP, max-num-seqs, chunked-prefill, prefix-cache, quant.

### Compiler / Runtime (torch.compile, Inductor, Triton frontend, CUDA Graphs)
Captures the op graph, **fuses** redundant ops (e.g. `x = add(x, b); y = relu(x); z = mul
(y, gate)` → one kernel), lowers to Triton or CUDA, and captures **CUDA Graphs** to kill
launch overhead. `torch.compile` is the entry point; **Inductor** is the backend that
emits Triton. **Knobs:** `mode="max-autotune"`, fusion on/off, graph-break handling.

### Kernel layer (Triton / CUTLASS / CUDA C++)
The **actual GPU programs**. This is where `GEMM.md`, `FlashAttention.md`,
`Fused-Kernels.md`, `Custom-GEMM.md`, `Triton.md` live. A Triton kernel is written in
Python, compiled to PTX, and run on the SMs. A CUTLASS template instantiates a tiled
Tensor-Core GEMM for a specific (M,N,K,dtype,arch). **Knobs:** block sizes, pipeline
depth, dtype, split-K, warp specialization.

### Math libraries (cuBLAS / cuBLASLt / cuDNN / FlashInfer)
Vendor-optimized, **shape-specialized, autotuned** kernels. cuBLASLt picks the best algo
per GEMM shape at runtime. FlashInfer is the paged-KV attention engine used by SGLang and
vLLM. When you "call torch.matmul," this is what runs. **Knobs:** algo selection,
workspace size, `cudnn.benchmark`.

### CUDA Runtime
Streams (parallel work queues), events (timestamps for sync), **CUDA Graphs** (capture a
sequence of kernel launches into a single graph object to eliminate per-launch CPU
overhead), allocators (caching allocator to avoid repeated cudaMalloc). **Knobs:**
stream-per-op, graph capture, allocator pooling.

### GPU Hardware (SMs, Tensor Cores, caches)
The physical execution. `Architecture.md` covers this in depth. SMs host warps;
Tensor Cores do mixed-precision MMA; shared/L1/L2 are the on-chip memory hierarchy.

### Memory (HBM/GDDR) + Interconnect
HBM3e/3/GDDR7 holds weights + KV + activations. NVLink/NVSwitch connect GPUs intra-node;
PCIe connects GPU↔host; IB/RoCE connect nodes. `Multi-Node.md`, `Scale-Up-vs-Scale-Out.md`,
`Topology.md` cover the fabric.

## Where inference engines interact with the stack
This is the crux. **An inference engine is a layer-L1 framework that orchestrates
decisions across L2–L5.** Concretely:
- **vLLM** (L1) → decides batch + KV blocks (L1) → issues ops → torch.compile/Inductor
  (L2) fuses → Triton/cuBLASLt kernels (L3/L4) → CUDA Graphs (L5) → SMs (L6).
- **SGLang** (L1) → RadixAttention scheduling (L1) → FlashInfer paged-KV kernels (L4) →
  CUDA Graphs (L5).
- **TensorRT-LLM** (L1) → **compile-time** graph optimization (L2, done at build time,
  not runtime) → custom fused kernels (L3) → CUDA Graphs (L5).

The **key difference**: vLLM/SGLang optimize at **runtime** (flexible, can adapt to
dynamic workloads); TRT-LLM optimizes at **build time** (faster, but must re-build for
each model + quant + shape). This is the "max-optimization vs flexibility" trade-off in
`TensorRT-LLM.md`.

## The "next limiting resource" principle (preview of Cross-Layer-Optimization.md)
Because layers are **cascaded**, optimizing one layer **exposes** the next. Examples:
- You speed up the GEMM kernel (L3) → now the GEMM finishes sooner → **NCCL AllReduce
  (fabric) becomes the bottleneck** (L7, interconnect).
- You quantize to FP4 (L1/L4) → weight bytes drop → decode is no longer bandwidth-bound →
  **scheduler overhead or kernel-launch gaps become the bottleneck** (L1/L5).
- You add FlashAttention (L3) → prefill HBM traffic drops → now the **scheduler's
  chunked-prefill decision** is the limiter (L1).
The skill: after every optimization, **re-measure and ask "what is the next limiting
resource?"** That is the whole of `Cross-Layer-Optimization.md`.

## How to read the stack when debugging
1. **Symptom is TTFT (prefill)?** → Look at L3 (attention/GEMM kernels), L2 (fusion),
   L4 (cuBLAS algo), L1 (chunked-prefill decision, prefix-cache hit).
2. **Symptom is ITL (decode)?** → Look at L4 (skinny GEMM / KV read), L5 (CUDA Graphs,
   launch gaps), L1 (batch size, KV pressure), L6 (HBM bandwidth).
3. **Symptom is P99 tail?** → Look at L1 (scheduler), L5 (launch variance), L7 (fabric).
4. **Symptom is OOM?** → Look at L1 (KV budget), L4 (workspace), L6 (HBM capacity).

## Failure modes (stack-level)
- **Layer mismatch:** a "kernel fix" that doesn't help because the bottleneck is at L1
  (scheduler) not L3. (Fix: profile the whole stack first, `Diagnostics.md`.)
- **Graph break:** torch.compile falls back to eager at a graph break → you lose the
  fusion + CUDA-Graph benefit. (Fix: eliminate the break.)
- **Wrong autotune cache:** cuBLASLt picks a bad algo for a new shape → re-warm or
  disable autotune for that shape.
- **Clock/power throttling:** the hardware layer (L6) throttles between runs → your
  "faster" kernel is actually running at lower clocks. (Fix: log clocks, `Perf-Experiment-Template.md`.)

## How to measure which layer is the bottleneck
- **Nsight Systems** (whole-stack timeline): shows kernel time, launch gaps, stream
  activity, NCCL time. The "where is time spent?" tool. [F: Nsight Systems docs]
- **Nsight Compute** (per-kernel): shows SM/Tensor-Core/HBM utilization. The "why is
  this kernel slow?" tool.
- **torch.profiler** (op-level): shows which framework op is slow.
- **Engine metrics** (vLLM/SGLang/TRT-LLM Prometheus): TTFT, ITL, batch size, KV util.
Full tool guide: `Profiling.md`.

## Related
`GEMM.md` · `Tensor-Cores.md` · `Triton.md` · `Custom-GEMM.md` · `Fused-Kernels.md` ·
`FlashAttention.md` · `Inference-Engines.md` · `../Serving-Engines/README.md` ·
`../Inference/Inference-Optimization.md` · `Diagnostics.md` · `Profiling.md`.

## Key Takeaways
1. A token runs through **7 layers** of the stack; every optimization is a decision at
   one of them.
2. **Inference engines are L1 frameworks** that orchestrate L2–L5; they differ in
   runtime vs build-time optimization.
3. **Layers cascade**: fixing one exposes the next. Always find the next limiting
   resource (`Cross-Layer-Optimization.md`).
4. **Debug by layer**: TTFT→L3/L2, ITL→L4/L5/L1, P99→L1/L5/L7, OOM→L1/L6.
