# GPU Systems Glossary
`LAST_UPDATED: 2026-08-21 · Status: core page` · The GPU/kernel/distributed/serving term
index for this section. Complements the global `../Glossary/README.md` (LLM-side terms);
this page owns the hardware → kernel → engine → cluster terms and points to the deep-dive
page where each is taught.

## 30-Second Explanation
A glossary for the whole GPU-systems layer, from the SM up to the cluster router. Use it
to look up a term quickly; each entry is one line + a link to the page that actually
teaches it. Terms are grouped by layer: **hardware → CUDA/kernel → memory → GEMM/precision
→ engines → parallelism → network → metrics**.

## Hardware & execution model
- **SM (streaming multiprocessor)** — the GPU's basic compute unit: CUDA cores, Tensor
  cores, registers, shared memory, warp schedulers. → `Architecture.md`
- **CUDA core** — a scalar FP/INT ALU thread (NOT a full core); peak FLOPS comes from
  Tensor cores. → `Architecture.md`
- **Tensor core** — the mixed-precision matrix-multiply-accumulate unit; the source of
  peak TFLOPS. → `Tensor-Cores.md`
- **warp** — 32 threads executing lockstep (SIMT); the unit of warp scheduling. → `Architecture.md`
- **thread / block / grid** — the execution hierarchy: grid→block→warp→thread; a block
  maps to one SM. → `Architecture.md`
- **occupancy** — fraction of an SM's max resident warps that are actually resident; set
  by registers-per-thread and shared memory. → `Architecture.md`, `Memory-Hierarchy.md`
- **register (file)** — per-thread scratch (256 KB/SM on H100); over-subscription →
  **register spilling** to HBM. → `Memory-Hierarchy.md`
- **shared memory / L1** — per-SM explicit scratch + cache (~228 KB Hopper); tiling
  target; 32-bank → **bank conflicts**. → `Memory-Hierarchy.md`
- **L2 cache** — per-GPU shared cache (~50 MB H100). → `Memory-Hierarchy.md`
- **HBM / GDDR** — the main GPU memory (HBM3 3.35 TB/s H100); the decode roof. → `Hardware/README.md`, `Memory-Hierarchy.md`
- **coalescing** — 32 threads touching 32 contiguous bytes → one memory transaction;
  the single biggest kernel perf lever. → `Memory-Optimizations.md`

## CUDA & kernels
- **CUDA (C++)** — the low-level kernel language (thread-level control). → `CUDA-From-Zero.md`
- **kernel** — a function launched on the GPU; **kernel launch** has ~µs overhead. → `Kernel-Life.md`
- **kernel launch overhead** — the CPU→driver→GPU handoff cost; many tiny kernels →
  launch-bound. → `Kernel-Life.md`
- **CUDA stream / event / graph** — async queues, sync points, and captured launch-DAGs
  that cut launch overhead. → `Kernel-Life.md`
- **CUDA kernel** — also: one launch of a kernel over a grid. → `Kernel-Life.md`
- **Triton** — Python kernel language; compiler handles warps; `@triton.jit`, autotune. → `Triton.md`
- **kernel fusion** — merge N kernels (N HBM round-trips) into 1; fewer launches, less
  HBM traffic. → `Fused-Kernels.md`
- **epilogue / prologue** — the fusion sites around a GEMM (bias+act, layernorm). → `Fused-Kernels.md`

## GEMM & precision
- **GEMM** — C = A×B; `2MNK` FLOPs; the core LLM op. → `GEMM.md`
- **M / N / K** — tokens (batch×seq), out-features, in-features. M small = decode GEMV. → `GEMM.md`
- **GEMV** — M=1 GEMM (a vector×matrix); the decode bottleneck. → `GEMM.md`, `Custom-GEMM.md`
- **grouped GEMM** — many small GEMMs (one per expert) in one launch; the MoE op. → `Custom-GEMM.md`
- **skinny GEMM** — M small, N,K large; cuBLAS's generic path is not optimal here. → `Custom-GEMM.md`
- **cuBLAS / cuBLASLt** — the default GEMM library; Lt adds runtime algo selection. → `Custom-GEMM.md`
- **CUTLASS** — NVIDIA's template library for building custom Tensor-Core GEMMs. → `Custom-GEMM.md`
- **FlashAttention** — IO-aware exact attention (tiling + online softmax, no S×S HBM). → `FlashAttention.md`
- **FP32 / TF32 / FP16 / BF16 / FP8 / INT8 / INT4 / FP4 / NVFP4** — precision formats;
  the precision↔bandwidth↔quality trade. → `Tensor-Cores.md`, `../Quantization/README.md`
- **W4A16 / W8A8** — quantized GEMM dtypes (weight-4 act-16, etc.). → `../Quantization/README.md`

## Engines & serving
- **inference engine** — the runtime that schedules batches + manages KV (vLLM/SGLang/
  TRT-LLM). → `Inference-Engines.md`
- **PagedAttention** — block-based KV + block tables; the vLLM memory foundation. → `vLLM.md`, `../KV-Cache/README.md`
- **continuous batching** — iteration-level admission/eviction; the Orca idea. → `../Inference/Continuous-Batching.md`, `vLLM.md`
- **prefix caching** — reuse KV for shared prefixes (vLLM APC, SGLang RadixAttention). → `vLLM.md`, `SGLang.md`
- **chunked prefill** — prefill a long prompt in chunks interleaved with decode. → `../Inference/Continuous-Batching.md`
- **RadixAttention** — SGLang's radix-tree prefix cache. → `SGLang.md`
- **KV cache** — stored K,V per position; the decode-era HBM consumer. → `../KV-Cache/README.md`
- **speculative decoding** — draft-verify; EAGLE/MTP. → `../Speculative-Decoding/README.md`
- **goodput** — SLO-conforming requests/sec. → `../Inference/Inference-Metrics.md`, `GPU-Metrics.md`

## Parallelism
- **TP / PP / DP / EP / SP / CP** — tensor / pipeline / data / expert / sequence / context
  parallelism. → `Multi-GPU.md`, `Tensor-Parallelism.md`, `Pipeline-Parallelism.md`, `MoE-Expert-Parallelism.md`
- **AllReduce / AllGather / ReduceScatter / AllToAll / Broadcast / Send-Recv** — NCCL
  collectives; AllReduce = ReduceScatter + AllGather (the standard 2-phase
  decomposition, run in ring/tree form). → `NCCL.md`
- **NCCL** — NVIDIA's collective library; ranks + communicators + algorithms. → `NCCL.md`
- **pipeline bubble** — idle fraction `(p−1)/(m+p−1)` of a PP schedule. → `Pipeline-Parallelism.md`
- **hot expert** — an over-subscribed MoE expert that becomes the step-time ceiling. → `MoE-Expert-Parallelism.md`
- **capacity factor** — the MoE dispatch buffer sized above expected load. → `MoE-Expert-Parallelism.md`

## Network & topology
- **NVLink / NVSwitch** — intra-node GPU fabric (~900 GB/s H100; 72-GPU NVL72 domain). → `Hardware/README.md`, `Scale-Up-vs-Scale-Out.md`
- **InfiniBand / RoCE / Ethernet** — inter-node RDMA fabrics (~50 GB/s/link NDR). → `Networking/README.md`, `Multi-Node.md`
- **RDMA** — remote direct memory access (zero-copy, kernel-bypass). → `Networking/README.md`, `Multi-Node.md`
- **GPUDirect (RDMA/Storage)** — GPU↔NIC / GPU↔NVMe without host bounce. → `Multi-Node.md`
- **scale-up / scale-out** — NVLink domain vs RDMA fabric; the two regimes. → `Scale-Up-vs-Scale-Out.md`
- **NUMA / NIC / GPU affinity** — placing work near its memory/NIC to avoid a host-bridge
  hop. → `Topology.md`
- **`nvidia-smi topo -m`** — the GPU↔GPU / GPU↔NIC path matrix (NV#/PIX/PHB/NODE/SYS). → `Topology.md`

## Metrics & tools
- **TTFT / ITL / TPOT** — time-to-first-token / inter-token latency / time-per-output-
  token. → `GPU-Metrics.md`, `../Inference/Inference-Metrics.md`
- **SM / Tensor-Core util** — fraction of compute units busy. → `GPU-Metrics.md`, `Profiling.md`
- **memory-bandwidth utilization** — achieved HBM BW / peak; the decode tell. → `GPU-Metrics.md`
- **arithmetic intensity** — FLOPs/byte; below the roofline ridge = bandwidth-bound. → `Bandwidth-vs-Compute.md`, `../Inference/Roofline.md`
- **roofline** — `achieved = min(peak, BW × AI)`. → `../Inference/Roofline.md`
- **warp stall** — a warp waiting (memory/dependency); the Nsight "why is it slow" signal. → `GPU-Metrics.md`
- **P50/P95/P99** — latency percentiles. → `../Inference/Inference-Metrics.md`
- **nvidia-smi / DCGM / Nsight Systems / Nsight Compute / PyTorch Profiler** — the tools;
  "where is time?" vs "why is this kernel slow?" vs "what's the GPU doing over time?". → `Profiling.md`

## Related
`README.md` (section map) · `../Glossary/README.md` (global LLM glossary) ·
`Zero-to-Hero-Path.md` (which page teaches what) · `Case-Studies.md` (terms in context).
