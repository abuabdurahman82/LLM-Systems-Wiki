# vLLM
`LAST_UPDATED: 2026-08-16` · Status: engine page (architecture facts [F] from vLLM
README/docs + SOSP'23 paper; performance claims [I] — verify via `Labs/Lab-8`)

## 30-Second Explanation
The default open LLM serving engine: Python-first, paged KV (PagedAttention), widest
model/quant ecosystem, pluggable attention kernels. "Get a new model running correctly
today" is its superpower.

## Architecture
- **Scheduler:** Python async event loop, **iteration-level continuous batching** [F].
  Priority queue; preemption by recompute or swap-to-CPU [F: docs].
- **KV cache manager:** **PagedAttention** — block pool (default 16 tokens) + per-request
  block tables; near-zero fragmentation [F: SOSP'23, arXiv:2309.06180].
- **Prefix caching:** hash-based **APC** — prefix hash → block list; physically shares
  paged blocks across requests via refcounts; enable via `--enable-prefix-caching` [F].
- **Chunked prefill:** `--enable-chunked-prefill`, co-scheduled with decode steps [F].
- **Attention backends:** FlashAttention, **FlashInfer**, TRTLLM-GEN, **FlashMLA**, Triton
  — runtime-selected per model/hardware [F: README]. Paged KV supported across backends.
- **GEMM/MoE:** CUTLASS / TRTLLM-GEN / CuTeDSL / FusedMoE kernels [F: README].
- **Quantization (widest coverage):** FP8, NVFP4/MXFP4, INT8/INT4, GPTQ, AWQ, GGUF,
  compressed-tensors, ModelOpt [F: README].
- **Speculative decoding:** n-gram, suffix, EAGLE, DFlash [F: README].
- **Parallelism:** TP, PP, EP, DP (data-parallel attention), multi-node via NCCL [F].
- **CUDA graphs:** decode steps captured as graphs (piecewise capture in V1); annotate
  graph-hit fraction when benchmarking (coverage varies at odd batch sizes). [I]
- **Disaggregation:** "disaggregated prefill, decode, and encode"; KV transfer via shared
  memory / NIXL / RDMA [F: README].
- **Observability:** Prometheus metrics in V1 (`gpu_cache_utilization`,
  `num_requests_waiting`, …) [F: docs]; OpenTelemetry experimental [F].

## Where it stands (fit, not performance verdict)
- Best fit: new-model day-0 support, quant coverage, K8s ecosystem, research.
- Open question (H4 in the engine comparison): does the Python event loop actually bite
  at B≥128? Unverified — test it.

## Mermaid
```
flowchart LR
  HTTP --> API --> Sched[Python scheduler / iteration-level]
  Sched --> APC[APC hash lookup] --> Alloc[Block allocation]
  Alloc --> Batch[Continuous batch] --> Prefill[Prefill: FlashInfer/FA]
  Prefill --> KV[(KV blocks)] --> Decode[Decode: CUDA-graph GEMV]
  KV <--> Decode
  Decode --> Sample[Sampling] --> SSE[Stream]
```

## Related
`Serving-Engines/SGLang.md` · `Serving-Engines/TensorRT-LLM.md` ·
`Inference/Continuous-Batching.md` · `KV-Cache/README.md`.
