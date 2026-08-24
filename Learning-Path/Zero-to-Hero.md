# Zero-to-Hero Learning Path
`LAST_UPDATED: 2026-08-23` · Ten levels; each = concepts / papers / courses / projects /
hands-on. (Estimates assume ~10–20h/level; "hero" = can run + evaluate + extend a
serving stack and read the frontier literature critically.)

> **Ops companion:** once you can build and serve (Levels 3–6), a separate
> levelled path covers *reliability & production operations* (SLI/SLO/SLA,
> goodput, GPU monitoring, queueing, autoscaling, distributed-inference
> reliability, releases, chaos/incidents, multi-region DR):
> `Production-Operations/40-llm-sre-zero-to-hero.md` + `Production-Operations/39-llm-sre-80-20.md`.

## LEVEL 0 — Math + Python
- **Concepts:** linear algebra (vectors, matrices, GEMM), probability (distributions,
  cross-entropy), calculus (chain rule), Python + numpy + Jupyter.
- **Papers/resources:** 3Blue1Brown linear algebra & calculus playlists;
  "Mathematics for Machine Learning" (Deisenroth et al., free book).
- **Project:** implement matrix multiply + softmax + cross-entropy by hand in numpy;
  verify shapes.
- **Exercise:** write the GEMM FLOP formula 2MNK and compute FLOPs for [4096×4096]³.

## LEVEL 1 — Neural networks
- **Concepts:** perceptron → MLP → backprop → SGD/Adam → overfitting → train/val/test.
- **Papers:** original backprop (1986); "Neural Networks and Deep Learning" (Goodfellow
  ch. 1-6); "The Annotated GPU" not needed yet.
- **Courses:** fast.ai Part 1; CS231n (vision as NN intro).
- **Project:** train an MLP on MNIST; plot loss; observe overfitting.
- **Exercise:** add weight decay + gradient clipping; watch the difference.

## LEVEL 2 — Transformer fundamentals
- **Concepts:** tokenization (BPE), embeddings, Q/K/V, scaled dot-product attention,
  causal mask, FFN, residuals, RMSNorm, logits, sampling; **tensor shapes at every
  stage**.
- **Papers:** Vaswani 2017; Su 2021 (RoPE); Zhang 2019 (RMSNorm); Shazeer 2020 (SwiGLU).
- **Wiki:** `Transformer/README.md` (read all of it); `Inference/The-Life-of-a-Token.md`.
- **Project:** implement a 2-layer d=6 transformer from scratch (the toy in
  `Transformer/README.md`), next-token on a small corpus; compare logits to a
  HF-small model.
- **Exercise:** trace one token's tensor shapes through the toy model by hand.

## LEVEL 3 — LLM training
- **Concepts:** next-token objective, data pipeline (clean/dedup/mix), scaling laws
  (Kaplan/Chinchilla), AdamW, warmup+cosine, mixed precision (BF16), checkpointing,
  distributed basics (DP/ZeRO), comm ops (AllReduce/AllGather).
- **Papers:** Chinchilla (2022); ZeRO (2020); Mixed Precision (2017).
- **Wiki:** `Training/README.md`; `Distributed-Inference/README.md`.
- **Project:** train a 10M-param LM on TinyShakespeare/T5-small split with HF
  Transformers + accelerate; log MFU.
- **Exercise:** estimate your training FLOPs (6·N·tokens rule of thumb [I]) and compare
  to measured.

## LEVEL 4 — Inference
- **Concepts:** prefill vs decode, KV cache (memory equation), roofline, arithmetic
  intensity, GEMM vs GEMV, TTFT/ITL/tok/s, continuous batching, PagedAttention,
  FlashAttention (IO, not math).
- **Papers:** vLLM/SOSP'23; FlashAttention 1/2/3; Chinchilla not needed; Orca 2022.
- **Wiki:** `Inference/*` (all), `KV-Cache/*`, `Attention/README.md`.
- **Project:** serve a 7B model with vLLM on 1 GPU; measure TTFT/ITL at B=1/8/32
  (Labs 1, 5); watch `gpu_cache_utilization` (Lab 2).
- **Exercise:** hand-compute KV bytes for your model at 8k/32k ctx (`Labs/Lab-2`).

## LEVEL 5 — Distributed LLM systems
- **Concepts:** TP/PP/DP/EP/CP + their collectives; NVLink vs RDMA; roofline at scale;
  P/D disaggregation; KV transfer physics.
- **Papers:** Megatron-LM (2019) + Megatron-3; Ring Attention (2022); DistServe (2024);
  Mooncake (2024).
- **Wiki:** `Distributed-Inference/README.md`; `Networking/README.md`;
  `Inference/Prefill-Decode-Disaggregation.md`.
- **Project:** run TP=2 inference on 2 GPUs; compare ITL to TP=1; explain the AllReduce
  cost.
- **Exercise:** sketch the comm pattern for TP=4 vs TP=8; which fabric do you need?

## LEVEL 6 — Optimization (quantization, speculative, KV)
- **Concepts:** FP16/BF16/FP8/NVFP4/INT4; weight-only vs W+A; KV quant; GPTQ/AWQ/
  SmoothQuant/GGUF; speculative decoding (draft-verify, EAGLE/MTP); KV eviction
  (H2O/SnapKV).
- **Papers:** GPTQ; AWQ; SmoothQuant; KIVI (2024); EAGLE; H2O; SnapKV.
- **Wiki:** `Quantization/README.md`; `Speculative-Decoding/README.md`;
  `KV-Cache/Eviction.md`.
- **Project:** benchmark BF16 vs FP8 vs INT4 on the same 7B (Lab 4); enable EAGLE
  spec decode and measure acceptance (Lab 7).
- **Exercise:** for a 27B model, compute the roofline decode ceiling for each quant
  (the numbers are in `Inference/Roofline.md`).

## LEVEL 7 — Agents
- **Concepts:** tool calling, ReAct loop, planning, memory, reflection, subagents,
  verification, sandboxing, computer use, coding agents; model-vs-harness.
- **Papers:** ReAct (2022); Reflexion (2023); MemGPT (2023); SWE-agent (2024).
- **Wiki:** `Agents/README.md`; `Harness-Engineering/README.md`;
  `Context-Engineering/README.md`; `RAG/README.md`.
- **Project:** build a two-model agent/evaluator (Lab 12): a worker model + an
  independent evaluator that critiques; measure how much the harness changes outcomes.
- **Exercise:** run the same task with (a) bare model, (b) +retrieval, (c) +verifier;
  record the deltas.

## LEVEL 8 — Research
- **Concepts:** read a paper critically (claims vs evidence vs protocol); design a
  reproducible experiment (the benchmark-fairness checklist from
  `Serving-Engines/README.md`); reproduce results; write a lineage note; run an
  independent evaluator over your own claims.
- **Papers:** pick 3 from `Latest-Research/` + `Research-Papers/` and reproduce one
  number.
- **Wiki:** `Evaluation/README.md`; `Benchmarks/README.md`;
  `Research-Lineage/README.md`; open questions in each section.
- **Project:** a full mini-benchmark: one model, one workload, three configs,
  P50/P95/P99, roofline prediction vs measurement, written up with [F]/[I]/[E] tags.
- **Exercise:** find a vendor claim, mark it [marketing], design the experiment that
  would actually test it.

## The 80/20 shortcut
If you only have 20% of the time, do: **L2 (transformer + shapes) + L4 (inference +
KV + roofline) + L6 (quant/spec)** — that trio explains 80% of modern LLM engineering.
See `Learning-Path/80-20-LLM-Guide.md`.

## Related
`Labs/README.md` · `80-20-LLM-Guide.md` · `Transformer/README.md`.

 The GPU-Systems zero-to-hero path (13 levels, hardware→kernel→engine→cluster): `GPU-Systems/Zero-to-Hero-Path.md`.
