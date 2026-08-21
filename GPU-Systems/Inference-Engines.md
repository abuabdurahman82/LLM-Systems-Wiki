# LLM Inference Engines — Why They Exist
`LAST_UPDATED: 2026-08-21 · Status: core page` · Overview of the engine layer; deep dives
in `vLLM.md`, `SGLang.md`, `TensorRT-LLM.md`; comparison in `Engine-Comparison.md`.

## 30-Second Explanation
`model.generate()` is a **research toy**, not a server. It processes one batch at a time,
reallocates the KV cache per call, has no concurrent-request scheduler, no memory
management, no prefix reuse, no quantization pipeline, no multi-GPU parallelism, and no
observability. An **inference engine** is the production layer that turns a checkpoint
into a fast, concurrent, memory-bounded, observable service. The three dominant engines —
**vLLM**, **SGLang**, **TensorRT-LLM** — each pick a different architectural bet
(compatibility+pluggable kernels vs program-aware zero-overhead runtime vs
compile-time-peak-NVIDIA). This page explains *why* engines exist and *what* they do;
the deep dives explain *how*.

## What
An LLM inference engine is software that:
1. **Loads** a checkpoint into the right precision/layout for the hardware.
2. **Manages the KV cache** — allocates, paces, shares, evicts, quantizes it
   (`../KV-Cache/README.md`).
3. **Schedules requests** — continuous batching, chunked prefill, prefix-aware
   (`../Inference/Continuous-Batching.md`).
4. **Runs the model** through optimized kernels (GEMM, attention, norm, dequant) —
   often with CUDA Graphs to kill launch overhead (`Kernel-Life.md`).
5. **Parallelizes** across GPUs (TP/PP/EP/DP/CP) (`Multi-GPU.md`, `NCCL.md`).
6. **Exposes an API** (OpenAI-compatible `/v1/chat/completions`, `/v1/completions`) and
   **metrics** (Prometheus).
7. **Serves concurrently** — thousands of in-flight requests, each at a different
   decode position.

## Why `Transformers.generate()` is not enough
The HF `generate()` loop is a **single-stream, synchronous, per-call** batcher:
- **No concurrency:** one `generate()` call holds the GPU; the next request waits.
- **KV cache is local & re-allocated** per call; no sharing across calls; no paging;
  the GPU OOMs at modest batch × context.
- **No continuous batching:** static batching pads all sequences to the longest →
  wasted compute on the shorter ones.
- **No prefix caching:** repeated system prompts are re-prefilled every time →
  TTFT waste.
- **No kernel optimization:** runs whatever PyTorch ops are there; no CUDA Graphs,
  no fused kernels, no Tensor-Core tuning.
- **No quantization path, no multi-GPU, no metrics, no SLO routing.**

So `generate()` is fine for a notebook, not for a service.

### The gap the engines fill (the "what")
| Capability | `generate()` | Engine |
|---|---|---|
| Concurrent requests | 1 | 100s–1000s |
| KV cache mgmt | per-call, OOM-prone | paged, shared, quantized |
| Batching | static (padded) | continuous |
| Prefix reuse | none | APC / RadixAttention |
| Kernel path | eager PyTorch | fused + CUDA Graphs + Tensor Cores |
| Multi-GPU | manual | TP/PP/EP/DP |
| Observability | none | Prometheus metrics |
| SLO routing | none | router + goodput |

## How it works (the request path, engine-generic)
```
HTTP request
   │
   ▼
API server (tokenize, route, auth)
   │
   ▼
Scheduler (admit? add to batch? chunk prefill? use prefix cache? schedule decode?)
   │
   ▼
Batch builder (assemble this step's tokens + KV block pointers)
   │
   ▼
Model runner (run the transformer loop: L × (QKV+attn+O + MLP) + logits)
   │   ← this is where the kernels run (GEMM.md, FlashAttention.md, Fused-Kernels.md)
   │   ← CUDA Graphs replay the launch sequence (Kernel-Life.md)
   ▼
KV cache update (append new K/V rows into paged blocks)
   │
   ▼
Sampling (top-p/top-k/min-p → token)
   │
   ▼
Detokenize + stream back (SSE)
   │
   ▼
Repeat for next token (decode loop) until EOS/max_tokens
```

The **scheduler** is the brain; the **model runner** is the muscle; the **KV cache
manager** is the memory; the **kernels** are the hands. `vLLM.md`/`SGLang.md`/
`TensorRT-LLM.md` trace one request through each engine's specific version of this.

## When to use which (philosophy, not performance verdict)
| Engine | Philosophy | Best fit |
|---|---|---|
| **vLLM** | Max compatibility + pluggable kernel ecosystem [F] | New-model day-0; widest quant coverage; general serving |
| **SGLang** | Program-aware runtime, zero-overhead scheduling [F] | Agentic/structured, shared-prefix, high-concurrency |
| **TensorRT-LLM** | Compiled, NVIDIA-specific peak [F] | Peak perf on a stable model + hardware you control |
| **llama.cpp** | GGUF, CPU/edge, day-0 [F: repo] | Local/edge, low-precision, no-GPU |
| **TGI** | HF's engine, FlashAttention, paged [F: repo] | HF-native serving |
| **NVIDIA Dynamo** | Disaggregated orchestration over TRT-LLM [F] | P/D at scale |
| **llm-d** | K8s-native disaggregated serving [F] | Cloud-native P/D |

**No universal fastest engine.** The winner depends on model architecture, hardware,
request pattern, context length, concurrency, quantization, and SLO. Measure with
`Perf-Experiment-Template.md` before choosing. (Full matrix: `Engine-Comparison.md`.)

## Hardware impact
Engines decide the **kernel path** and the **memory layout**, which is what the GPU
sees:
- vLLM/SGLang → paged KV + FlashAttention/FlashInfer + CUDA Graphs → high HBM efficiency,
  low launch overhead.
- TRT-LLM → build-time-optimized fused kernels → peak Tensor-Core utilization on the
  target arch, at the cost of re-build per change.

## Inference impact
- **TTFT:** prefix caching + chunked prefill (all three) → lower TTFT on repeated
  prompts.
- **ITL:** continuous batching to B* + CUDA Graphs + quant → lower ITL.
- **Throughput:** continuous batching + multi-GPU → higher tok/s.
- **Capacity:** paged KV + quant + GQA/MLA → more concurrent sequences.
- **Tail latency (P99):** scheduler quality + P/D + KV-aware routing.

## Example
A 27B model on 1×H100: `generate()` B=1 → ~65 tok/s ceiling but **one request at a time,
no concurrency, OOMs at 8k×32**. vLLM with continuous batching + paged KV + FP8 weights
→ same single-request speed, **but 100s of concurrent requests, prefix reuse, P99
controlled**. The model didn't change; the engine did.

## Failure modes
- **Wrong engine for the workload:** picking TRT-LLM for a new model (re-build cost) or
  vLLM when you need peak stable-model perf. (Fix: match philosophy to workload.)
- **Untuned config:** max-num-seqs too low → underutilized; too high → OOM/P99.
- **Kernel mismatch:** a model whose attention doesn't fit the engine's kernel path
  (e.g. a new MLA variant) → falls back to slow path.
- **No warm-up:** cold start reads as "slow engine." (Fix: `Perf-Experiment-Template.md`.)

## How to measure it
- **Throughput/TTFT/ITL P50/P95/P99** at fixed concurrency (client + engine metrics).
- **KV utilization, batch size, prefix-cache hit rate** (engine Prometheus).
- **GPU util + HBM BW util + launch gaps** (Nsight, `Profiling.md`).
- **Goodput** at your SLO (req/s where P99 ITL < target).

## The three deep dives (what to read next)
- `vLLM.md` — PagedAttention, continuous batching, scheduling, prefix caching,
  chunked prefill, spec decode, TP/PP/EP, observability.
- `SGLang.md` — RadixAttention, program-aware scheduling, structured generation,
  cache-aware scheduling, multi-node.
- `TensorRT-LLM.md` — build/convert, compiled kernels, inflight batching, paged KV,
  wide-EP + NVL72, the max-opt vs flexibility trade.
- `Engine-Comparison.md` — the full matrix + the fairness checklist.

## Related
`vLLM.md` · `SGLang.md` · `TensorRT-LLM.md` · `Engine-Comparison.md` ·
`Load-Balancing.md` · `Kernel-Stack.md` · `../Serving-Engines/README.md` ·
`../Inference/Continuous-Batching.md` · `../KV-Cache/README.md` · `../Speculative-Decoding/README.md`.

## Key Takeaways
1. `generate()` is a toy; engines are the production layer (concurrency, KV mgmt,
   scheduling, kernels, parallelism, observability).
2. The request path is **scheduler → batch → model runner (kernels) → KV update →
   sample → stream**; the engine's quality is its scheduler + kernel path.
3. Three philosophies: vLLM (compatibility/pluggable), SGLang (program-aware/zero-overhead),
   TRT-LLM (compile-time peak). **No universal winner — measure on your workload.**
