# Zero-to-Hero GPU Systems Learning Path
`LAST_UPDATED: 2026-08-21 · Status: core page` · The ordered roadmap through the whole
GPU-Systems section. Each level lists the concepts, the exercises, and a **mastery
criterion** (the thing you must be able to explain/compute without looking it up).
Companion to `../Learning-Path/Zero-to-Hero.md` (the broader LLM path) — this is the
GPU-systems deep track.

## 30-Second Explanation
This path goes from "what is a GPU" to "I can design and debug a multi-node LLM
inference system." It is deliberately **80/20**: each level ends with a mastery check,
so you stop when you can defend the concept, not when you've read the page. The 13
levels stack: you cannot do L9 until you pass L8.

```
L0 GPU fundamentals → L1 CUDA → L2 memory → L3 profiling → L4 GEMM → L5 Triton →
L6 attention → L7 LLM kernels → L8 engines → L9 multi-GPU → L10 multi-node →
L11 production serving → L12 inference research
```

## Level 0 — GPU fundamentals
- **Read:** `Architecture.md`, `Bandwidth-vs-Compute.md`.
- **Concepts:** CPU vs GPU (latency vs throughput), SIMT, SMs, CUDA/Tensor cores,
  warps, grid/block/warp/thread, HBM, NVLink, occupancy, **arithmetic intensity** + the
  **roofline**.
- **Exercises:** hand-derive the H100 BF16 ridge point (P/BW). Explain why decode is
  memory-bound and prefill is compute-bound.
- **Mastery:** "Why can thousands of threads make slow memory look fast?" — answer with
  latency hiding + TLP, no notes.

## Level 1 — CUDA basics
- **Read:** `CUDA-From-Zero.md`, `Kernel-Life.md`.
- **Concepts:** runtime vs driver, kernel launch, thread indexing, HtoD/DtoH, sync,
  launch overhead, why many tiny kernels hurt, streams/graphs.
- **Exercises:** Lab 1 (vector add), Lab 2 (naive GEMM). Trace one kernel end-to-end.
- **Mastery:** write a vector-add kernel from memory; estimate per-token launch overhead.

## Level 2 — Memory hierarchy
- **Read:** `Memory-Hierarchy.md`, `Memory-Optimizations.md`.
- **Concepts:** registers/shared/L1/L2/HBM capacities, latencies, BW; coalescing,
  bank conflicts, tiling, register blocking, double buffering, async copies.
- **Exercises:** Lab 4 (coalescing), Lab 5 (shared memory).
- **Mastery:** given a bad access pattern, predict the transaction count and fix it.

## Level 3 — Profiling
- **Read:** `Profiling.md`, `GPU-Metrics.md`, `Perf-Experiment-Template.md`.
- **Concepts:** nvidia-smi / DCGM / Nsight Systems / Nsight Compute / PyTorch Profiler;
  SM/Tensor-Core util, BW util, occupancy, warp stalls, L2 hit, TTFT/ITL/TPOT, goodput.
- **Exercises:** Lab 9 (profile attention). Build a benchmark that isn't theater.
- **Mastery:** given a slow kernel, name the tool that answers "why" and the metric that
  proves the fix.

## Level 4 — GEMM
- **Read:** `GEMM.md`, `Tensor-Cores.md`, `Custom-GEMM.md`.
- **Concepts:** M/N/K, naive → coalesced → tiled → shared → register → warp → Tensor
  Core; GEMM shape dependence; cuBLAS/CUTLASS/Triton roles; grouped/skinny/quantized
  GEMMs.
- **Exercises:** Lab 3 (tiled GEMM), Lab 7 (Triton GEMM). Compute AI for M=1 vs M=4096.
- **Mastery:** explain why a decode GEMV and a prefill GEMM are different kernels.

## Level 5 — Triton
- **Read:** `Triton.md`.
- **Concepts:** `@triton.jit`, blocks, pointers, masks, autotune; torch.compile→Inductor
  → Triton; Triton vs CUDA vs PyTorch.
- **Exercises:** Lab 6 (Triton softmax), Lab 7.
- **Mastery:** write a fused elementwise in Triton; say when to drop to CUDA/CUTLASS.

## Level 6 — Attention optimization
- **Read:** `FlashAttention.md`, `../Attention/README.md`.
- **Concepts:** standard attention IO cost, FlashAttention's IO-aware tiling + online
  softmax, FA-2/FA-3, long-context implications.
- **Exercises:** Lab 10 (FlashAttention benchmark).
- **Mastery:** explain why FlashAttention is an **IO** win, not just a FLOP win.

## Level 7 — LLM kernels
- **Read:** `Fused-Kernels.md`, `Kernel-Stack.md`, `Kernel-Life.md`.
- **Concepts:** fusion (bias+act, RMSNorm, QKV, RoPE, attention, MLP), where the kernel
  sits in the stack, kernel launch overhead → CUDA Graphs.
- **Exercises:** Lab 8 (fusion experiment).
- **Mastery:** given a 5-op Python sequence, say what one fused kernel saves.

## Level 8 — Inference engines
- **Read:** `Inference-Engines.md`, `vLLM.md`, `SGLang.md`, `TensorRT-LLM.md`,
  `Engine-Comparison.md`.
- **Concepts:** why engines exist; PagedAttention, continuous batching, prefix caching,
  chunked prefill, RadixAttention, TRT graph optimization, inflight batching.
- **Exercises:** Lab 11 (HF), Lab 12 (vLLM), Lab 13 (vLLM vs SGLang), Lab 14 (TRT-LLM).
- **Mastery:** trace one request through an engine (HTTP → scheduler → batch → kernel →
  KV → token).

## Level 9 — Multi-GPU
- **Read:** `Multi-GPU.md`, `Tensor-Parallelism.md`, `Pipeline-Parallelism.md`,
  `MoE-Expert-Parallelism.md`, `NCCL.md`, `Distributed-Architectures.md`.
- **Concepts:** TP/PP/EP/DP/CP, AllReduce/AllGather/ReduceScatter/AllToAll, NVLink,
  the 11 reference topologies.
- **Exercises:** Lab 18 (1-GPU vs TP), Lab 19 (NCCL all-reduce).
- **Mastery:** given a model + fabric, pick the topology and justify the collective
  placement.

## Level 10 — Multi-node distributed inference
- **Read:** `Multi-Node.md`, `Scale-Up-vs-Scale-Out.md`, `Topology.md`.
- **Concepts:** the performance hierarchy, RDMA/GPUDirect, NVLink vs IB/RoCE, topology
  (`nvidia-smi topo -m`), NUMA/NIC/GPU affinity.
- **Exercises:** Lab 20 (multi-node). Run `nvidia-smi topo -m` on a box and read it.
- **Mastery:** explain why TP must stay intra-node and what kills NCCL throughput.

## Level 11 — Production-scale LLM serving
- **Read:** `Prefill-Decode-Disaggregation.md`, `Load-Balancing.md`,
  `Cross-Layer-Optimization.md`, `Diagnostics.md`, `Case-Studies.md`.
- **Concepts:** P/D split + KV transfer, "balance remaining work not requests",
  cross-layer bottleneck-chasing, the diagnostic decision tree.
- **Exercises:** Lab 15 (continuous batching), Lab 16 (prefix cache), Lab 17
  (speculative decode). Walk the diagnostic tree on a real incident.
- **Mastery:** given "ITL spiked at P99", run the decision tree to the likely cause.

## Level 12 — Inference research
- **Read:** `Research-Lineage.md`, `Research-Radar.md`, `../Latest-Research/2026-08.md`.
- **Concepts:** the idea lineages (attention, KV/PagedAttention/vLLM, GEMM/CUTLASS/
  Triton, quantization, spec-decode); what's production vs research-stage.
- **Exercises:** read 2 papers in a lineage; summarize the key idea + its limitation.
- **Mastery:** place a new result in the lineage and say what it unblocks.

## The 80/20 short list (the 15 that explain 80%)
1 Matrix multiplication · 2 arithmetic intensity · 3 memory bandwidth · 4 GPU memory
hierarchy · 5 kernel launch overhead · 6 kernel fusion · 7 FlashAttention · 8 KV cache ·
9 continuous batching · 10 tensor parallelism · 11 NCCL collectives · 12 GPU/network
topology · 13 prefill vs decode · 14 quantization · 15 profiling.
Each is explained in the page above; together they cover most of what you'll face.

## How to know you're ready to move on
You advance when you can **(a)** state the concept in 2 sentences, **(b)** compute the
core number by hand (a byte count, an intensity, a collective size), and **(c)** name the
failure mode and the metric that exposes it. If you can't, re-do the level's exercise —
don't read the next level.

## Related
`README.md` (the section map) · `../Learning-Path/Zero-to-Hero.md` (broader LLM path) ·
`../Learning-Path/80-20-LLM-Guide.md` · `Glossary.md` · `Labs.md` · `Research-Lineage.md`.
