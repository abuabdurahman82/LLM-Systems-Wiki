# TensorRT-LLM
`LAST_UPDATED: 2026-08-16` · Status: engine page (architecture facts [F] from TRT-LLM
README/docs/tech blogs; performance claims [I] — verify via `Labs/Lab-8`)

## 30-Second Explanation
NVIDIA's compiled serving stack: kernels are built/compiled for a specific
model+precision+parallelism config; the C++ runtime treats prefill-decode
disaggregation, wide expert parallelism, and CUDA-graph batch tuning as first-class
deployment primitives. Peak NVIDIA performance, at the cost of build/compile friction.

## Architecture
- **Scheduler:** C++ engine; iteration-level "in-flight batching"; **ADP Balance** —
  load-balancing strategy across instances for multi-instance deployments [F: blog].
- **KV cache manager:** paged blocks, configurable block size; **KV cache quantization**
  (FP8/INT8) and **KV cache reuse** as separate runtime features [F: docs].
- **Chunked context:** designed to coexist with CUDA-graph capture [F: blog].
- **Attention:** custom compiled attention kernels (per model), paged by design [F: README].
  (Distinct from FlashInfer/FA — a different kernel family; benchmark fairness requires
  pinning which kernels ran.)
- **GEMM/MoE:** custom compiled kernels; **wide expert parallelism** optimization series;
  MoE-optimized [F: 3-part wide-EP blog].
- **Quantization:** FP8, INT8, INT4, NVFP4, plus ModelOpt integration [F: docs].
- **Speculative decoding:** n-gram, EAGLE, Llama-draft; **guided decoding + speculative
  decoding run cooperatively across CPU/GPU** (distinctive *implementation*; vLLM/SGLang
  also do constrained decoding + spec — a capability distinction, not a unique one) [F:
  blog; I: framing].
- **Parallelism:** TP, PP, EP, DWDP (distributed weight DP); NVL72-optimized; most
  *documented* multi-node stack in public blogs [F: blogs — documentation volume, not
  measured maturity].
- **Disaggregation:** prefill/decode disaggregation; most production-hardened in the
  NVIDIA ecosystem [F].
- **Observability:** Prometheus + structured per-request JSON payloads + step-level
  logging [F: docs] — the most granular of the three engines.
- **ModelOpt / Dynamo:** TRT-LLM pairs with ModelOpt (quantization) and NVIDIA Dynamo
  (disaggregated orchestration) — see `Inference/Prefill-Decode-Disaggregation.md`.

## Where it stands (fit, not performance verdict)
- Best fit: peak latency/throughput on a known, stable model on NVIDIA hardware;
  multi-node NVL72-class deployments; MoE with wide EP.
- Costs: build/compile step per config; less flexibility for new-model day-0; Python API
  overhead on top of the C++ engine [I].

## Mermaid
```
flowchart LR
  Py[Python API] --> Eng[C++ engine]
  Eng --> Sched[in-flight batching / ADP balance]
  Sched --> Reuse[KV reuse / paged KV quant]
  Sched --> Chunk[chunked context]
  Chunk --> Graph[CUDA-graph captured kernels]
  Graph --> K[(compiled attention/GEMM/MoE)]
  K --> Sample[sampling] --> Stream[stream + structured JSON log]
```

## Related
`Serving-Engines/vLLM.md` · `Serving-Engines/SGLang.md` ·
`Inference/Prefill-Decode-Disaggregation.md` · `Hardware/README.md`.
