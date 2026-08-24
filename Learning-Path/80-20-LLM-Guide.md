# The 80/20 of LLM Engineering
`LAST_UPDATED: 2026-08-16` · The 20% of concepts that explain 80% of modern LLM engineering.
Ranked by explanatory power.

## The core ten (learn these cold)
1. **The Transformer layer** (Norm → attention → Norm → FFN → residual) — one repeated
   block does everything.
2. **Q/K/V + softmax(QKᵀ/√d)V + causal mask** — the whole "thinking" in four matrices;
   know every shape.
3. **Matrix multiplication (GEMM)** — 90% of a forward pass is GEMMs; know 2MNK FLOPs.
4. **Tensor shapes as a debugging language** — [B,S,d], [S,h,d_h], S×S, [1,V]; most
   "bugs" are shape bugs.
5. **Prefill vs decode** — compute-bound vs bandwidth-bound; the master switch of
   inference.
6. **The roofline** — performance = min(peak, BW × AI); prefill on the compute roof,
   decode on the memory roof.
7. **The KV cache** — `2·L·B·h_kv·d_h·S·b`; the serving budget equation; why long
   context + high concurrency explode memory.
8. **Continuous batching** — iteration-level scheduling; why GPUs stay busy; GEMV→GEMM.
9. **Tokenization** — the unit of everything; why "context length" is in tokens, not
   characters; why the same "word" can be 1–4 tokens.
10. **Post-training (SFT → preference → reasoning RL)** — why a base model ≠ an
    assistant; where "helpfulness" comes from.

## The supporting ten (know the shape, not the detail)
11. **GPU memory hierarchy** (HBM ↔ SRAM ↔ registers) — why FlashAttention exists.
12. **Quantization** (BF16/FP8/NVFP4/INT4) — bytes-per-param; decode = bandwidth.
13. **Parallelism** (TP/PP/DP/EP/CP) — which one moves which bytes, over which fabric.
14. **Attention variants** (MHA/MQA/GQA/MLA) — h_kv as the KV-budget dial.
15. **Speculative decoding** — draft-verify; a latency tool, not a throughput tool.
16. **MoE** — capacity without compute; expert parallelism + AllToAll.
17. **Prefix caching / RadixAttention** — shared-prefix reuse; TTFT economics.
18. **P/D disaggregation** — split the two roofline regimes; KV transfer is the cost.
19. **Tool use / agents** — model + harness + tools + loop; harness sets how much of
    the model you reach.
20. **Evaluation discipline** — percentiles at fixed concurrency; protocol over number;
    contamination/saturation awareness.

## The one-page mental model
```
prompt → tokens → embed → L×[attn + FFN] → last-pos logits → sample
pre:  GEMMs, compute roof          (TTFT)
post: GEMVs, memory roof           (ITL)
KV:   2·L·B·h_kv·d_h·S·b           (the budget)
batch: GEMV→GEMM up to the ridge   (throughput)
quant: fewer bytes/token           (decode speed)
```

## What this 20% does NOT cover (the other 80% of your time)
- Distributed systems debugging (NCCL timeouts, stragglers, fabric config).
- Data engineering (crawls, dedup, mixtures, licensing).
- Safety/evals depth (injection, reward hacking, SLO design).
- Frontier research details (MLA internals, GRPO nuances, KV-learned eviction).

## The 80/20 of the OTHER half: keeping it up
A companion 80/20 exists for *operating* (not just building) LLM systems —
queue growth over GPU%, goodput over throughput, KV-as-resource, retry danger,
admission control, infra-health ≠ answer-quality, everything-is-a-release:
`Production-Operations/39-llm-sre-80-20.md`. Start there once you can run and
serve models (`Production-Operations/40-llm-sre-zero-to-hero.md` is the levelled
route into ops).

## Related
`Zero-to-Hero.md` · `Inference/Roofline.md` · `Transformer/README.md` ·
`Production-Operations/39-llm-sre-80-20.md`.
