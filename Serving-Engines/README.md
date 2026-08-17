# Serving Engines — Overview
`LAST_UPDATED: 2026-08-16` · Status: section index

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

Other engines (shorter pages, fill as needed):
- **llama.cpp** — GGUF quantized inference, CPU/edge, day-0 for local runs [F: repo]
- **TGI (text-generation-inference)** — HF's engine; FlashAttention, paged, continuous
  batching [F: repo]
- **MLC LLM** — unified compiler (MLC-LLM/relax) across devices, incl. mobile/JS [F: repo]
- **NVIDIA Dynamo** — disaggregated orchestration layer over TRT-LLM
  (`Inference/Prefill-Decode-Disaggregation.md`) [F]
- **llm-d** — K8s-native disaggregated serving (Red Hat/Google/NVIDIA/Intel et al.) [F]

## Key Takeaways
Engine choice = workload fit + ecosystem + ops, *then* measured performance. Benchmark
fairness requires pinning: kernel, quant, sampling, context limit, batching config, CUDA
graphs, prefix-cache behavior, versions (see the engine-comparison fairness checklist in
`Labs/Lab-8`).
