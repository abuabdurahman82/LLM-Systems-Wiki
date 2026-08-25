# Serving Engines — Overview
`LAST_UPDATED: 2026-08-24` · Status: section index

**Where to start:** `Engine-Landscape.md` (the layer-stack mental model: engines vs
packaging vs distributed platforms — the category distinctions). The seven-way
matrix: `Engine-Mega-Comparison.md` (vLLM / SGLang / TRT-LLM / llama.cpp / NIM /
Dynamo / llm-d, PART-18 style capability matrix + decision guide).

The big three, each a different architectural philosophy:

| | vLLM | SGLang | TensorRT-LLM |
|---|---|---|---|
| **Identity** | efficient memory management + pluggable kernel ecosystem [F] | program-aware runtime + low-overhead CPU scheduling [F] | compiled, specialized NVIDIA stack [F] |
| **Scheduler** | Python async, iteration-level [F] | Python, "zero-overhead" per-iter design (vendor term), program-aware [F] | C++ in-flight batching, ADP balance [F] |
| **Prefix cache** | hash APC, shared paged blocks [F] | RadixAttention tree, structural sharing [F] | KV reuse (config-level) [F] |
| **Attention** | widest set: FA, FlashInfer, TRTLLM-GEN, FlashMLA, Triton [F] | FlashInfer-centric [F] | custom compiled [F] |
| **Quant coverage** | widest (FP8/NVFP4/INT4/GPTQ/AWQ/GGUF/…) [F] | FP4/FP8/INT4/AWQ/GPTQ [F] | FP8/INT8/INT4/NVFP4 + ModelOpt [F] |
| **Spec decoding** | n-gram/EAGLE/DFlash [F] | EAGLE/STAGE/DFlash/Spec V2 + compressed-FSM [F] | n-gram/EAGLE + CPU-GPU cooperative guided [F] |
| **MoE/multi-node** | TP/PP/EP [F] | large-scale EP (96×H100 blog) [F] | wide EP + ADP + DWDP + NVL72 (most documented) [F] |
| **Observability** | Prometheus V1 [F] | Prometheus [F] | Prometheus + per-request JSON + step logs [F] |

**Engineering fit (not a performance verdict):** vLLM = new-model day-0 + quant breadth;
SGLang = agentic/structured/high-concurrency shared-prefix; TRT-LLM = peak NVIDIA perf on
a stable model. Performance rankings are **hypotheses** (H1–H10) pending the §5 benchmark
in the engine-comparison investigation (2026-08); see `Labs/Lab-8`.

Other engines (dedicated deep dives now exist for two of these):
- **llama.cpp** — `Llama-CPP.md`: GGUF/GGML, backend matrix (CUDA/Metal/Vulkan/
  SYCL/ROCm/CPU), layer placement, quantization families, CPU↔GPU execution [F: repo]
- **NVIDIA NIM** — `NVIDIA-NIM.md`: production microservice packaging layer (NOT an
  engine); NIM LLM 2.x = nim-llm + nimlib + vLLM [F: docs, 2026-08-24]
- **TGI (text-generation-inference)** — HF's engine; FlashAttention, paged, continuous
  batching [F: repo]
- **MLC LLM** — unified compiler (MLC-LLM/relax) across devices, incl. mobile/JS [F: repo]
- **NVIDIA Dynamo** — `../Distributed-Inference/NVIDIA-Dynamo.md` (deep dive):
  distributed serving platform over vLLM/SGLang/TRT-LLM (P/D pools, KV routing, KVBM,
  NIXL); see also `Inference/Prefill-Decode-Disaggregation.md`
- **llm-d** — `../Distributed-Inference/llm-d.md` (deep dive): K8s-native distributed
  serving (Router Proxy+EPP, InferencePool/Variant, KV indexer/offloader);
  head-to-head: `../Distributed-Inference/Dynamo-vs-llm-d.md`

## Key Takeaways
Engine choice = workload fit + ecosystem + ops, *then* measured performance. Benchmark
fairness requires pinning: kernel, quant, sampling, context limit, batching config, CUDA
graphs, prefix-cache behavior, versions (see the engine-comparison fairness checklist in
`Labs/Lab-8`).

## Related
 Engine comparison (vLLM/SGLang/TRT-LLM matrix, no fake numbers) + the GPU-Systems
 engines: `GPU-Systems/Inference-Engines.md`. Seven-way matrix incl. llama.cpp/NIM/
 Dynamo/llm-d: `Engine-Mega-Comparison.md`. Layer-stack mental model:
 `Engine-Landscape.md`. Cluster-layer platforms: `../Distributed-Inference/Overview.md`.
