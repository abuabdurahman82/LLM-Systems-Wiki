# LLM Training & Model Architecture Engineering

`LAST_UPDATED: 2026-08-20` · Status: first-class section · Phase 1 of the Training & Model Architecture Engineering expansion

> Scope: how modern LLMs are architected, how they are pretrained, how training
> scales from 1 GPU to 10,000+, and how architecture / compute / memory / network
> constrain each other. This section is the *engineering* view; `Transformer/` is
> the first-principles math, `Post-Training/` is the alignment stage,
> `Inference/` is the serving side.

## The five questions this section answers

| # | Question | Page |
|---|---|---|
| 1 | How is a modern LLM architected (and why those specific parts)? | `Model-Anatomy.md` |
| 2 | How is a foundation model actually pretrained (the full recipe)? | `Pretraining-Recipe.md` |
| 3 | What are the scaling laws — and what do they say to do with C, N, D? | `Scaling-Laws.md` |
| 4 | How do you split one model across thousands of GPUs? | `Parallelism.md` |
| 5 | How do you take a real run from 1 GPU to 10,000+ and keep it alive? | `Scaling-1-to-10k.md` |
| — | How do architecture, hardware, memory, and network interact? | `Interaction.md` |

## Reading paths

- **Engineer onboarding:** `Model-Anatomy.md` → `Pretraining-Recipe.md` →
  `Parallelism.md` → `Scaling-1-to-10k.md` → `Interaction.md`.
- **Theory-first:** `Scaling-Laws.md` → `Model-Anatomy.md` → `Parallelism.md`.
- **"Why is training so expensive?"** → `Interaction.md` (the cost model) +
  `Pretraining-Recipe.md` (what the money actually buys).

## How the five pieces fit

```
            ┌────────────────────────────────────────────┐
            │  Model Anatomy  (parameters P, tokens T,   │
            │  layers L, head design, MoE or not)        │
            └──────────────┬─────────────────────────────┘
                           │ defines (N, D, S, L, d)
            ┌──────────────▼─────────────────────────────┐
            │  Scaling Laws  (compute C = 6·N·D,         │
            │  Chinchilla ~1:20, data ceilings, MFU)     │
            └──────────────┬─────────────────────────────┘
                           │ picks N, D, batch, precision
            ┌──────────────▼─────────────────────────────┐
            │  Parallelism  (DP × TP × PP × EP × SP,     │
            │  memory equation, comm patterns, bubbles)   │
            └──────────────┬─────────────────────────────┘
                           │ assigns work to GPUs
            ┌──────────────▼─────────────────────────────┐
            │  1 → 10,000 GPUs  (cluster topology, MFU,  │
            │  stability, fault tolerance, checkpoints)   │
            └──────────────┬─────────────────────────────┘
                           │ all of it lands on hardware
            ┌──────────────▼─────────────────────────────┐
            │  Interaction  (HBM BW vs FLOPS, NVLink vs  │
            │  IB, roofline, $/token, decision framework)│
            └────────────────────────────────────────────┘
```

## Claim tags (wiki-wide)

`[F]` verified primary source this session (arXiv id fetched + title-checked, or
fetched vendor page) · `[E]` computed/verified in Python this session ·
`[I]` author inference · `[A]` assumption · `UNVERIFIED` could not be
confirmed at research time.

## Verified-source snapshot (2026-08-20)

Frontier pretraining reports fetched live: DeepSeek-V3.2 (arXiv:2512.02556,
2025-12-02), Kimi K2 (arXiv:2507.20534, 2025-07-28; 32B activated / 1T total,
15.5T tokens, zero loss spikes, MuonClip optimizer), Qwen3
(arXiv:2505.09388, 2025-05-14), Llama 4 Herd (arXiv:2601.11659, 2026-01-15),
DeepSeek-V3 (arXiv:2412.19437; 671B/37B activated, 14.8T tokens, 2.788M H800
GPU-hours, no irrecoverable spikes), MegaScale (arXiv:2402.15627; 55.2% MFU at
175B on 12,288 GPUs). Hardware: NVIDIA DGX B200 spec page (1,440 GB HBM3e,
64 TB/s, 72/36 PFLOPS FP4/FP8 dense per node (144/72 sparse), 14.4 TB/s
NVLink5 aggregate, 400 Gb/s
IB/ethernet) and H100 datacenter page (900 GB/s NVLink per GPU; H200 variant
= 141 GB HBM3e), fetched 2026-08-20; raw fetches retained in `/tmp/te-research/`.

## Related sections

`Transformer/` (first-principles math) · `Model-Architectures/` (head designs,
MoE, positional encodings) · `Hardware/` · `Networking/` · `Distributed-Inference/`
(serving-side parallelism) · `Post-Training/` · `Inference/Roofline.md` ·
`KV-Cache/`.

## Key takeaways

1. A modern dense LLM is ~75% FFN parameters, ~25% attention — so architecture
   choices (GQA, MoE, MLA) are mostly *FFN and KV-cache* choices.
2. Pretraining is one objective (cross-entropy next-token) run until the
   compute budget or data runs out; everything else (data mix, precision,
   parallelism) is a way to spend that budget efficiently.
3. **C ≈ 6·N·D** total training FLOPs (i.e. ≈6·N per token) is the master
   equation; MFU 40–60% is the reality gap between it and wall-clock.
4. Parallelism is not one choice but a product (DP×TP×PP×EP×SP), and each factor
   trades memory against a specific communication pattern — match the pattern
   to the fabric (NVLink vs IB).
5. At 10k+ GPUs, *stability* (not peak efficiency) is the binding constraint:
   failure rate, checkpoint cadence, stragglers, and loss spikes decide real
   cost.
