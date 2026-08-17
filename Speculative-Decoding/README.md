# Speculative Decoding
`LAST_UPDATED: 2026-08-16` · Status: core section

## 30-Second Explanation
A small **draft** model proposes k tokens cheaply; the large **target** model verifies all
k in one parallel pass; accepted tokens are kept (in expectation), rejected ones are
resampled. Same output distribution as the target alone, but fewer target forward passes
per emitted token → lower ITL.

## Why This Exists
Decode is bandwidth-bound: each target pass streams all weights to produce 1 token.
Speculative decoding amortizes that weight stream over k verified tokens.

## Problem It Solves
ITL / latency for latency-sensitive, low-batch interactive workloads (where batching
alone can't help).

## How It Works (math + loop)
```
draft:  x1..xk  (k cheap forward passes, small model)
target: forward on prompt + x1..xk  → p_target(·|prompt+x_i) for all i
for i in 1..k:
    if  x_i ~ p_target:  accept
    else: resample from normalized (p_target - p_draft); stop
```
**Unchanged distribution** [F: Leviathan et al. 2022 "Fast Inference from Transformers via
Speculative Decoding", arXiv:2211.17192; Chen et al. 2023 "Accelerating Large Language
Model Decoding with Speculative Sampling", arXiv:2302.01318] — this is the key
theoretical property.

## Key quantities
- **Acceptance rate α:** expected fraction of drafts accepted. Speedup ≈ k·α (capped by
  draft cost). α is model/distance-dependent. [F/I]
- **Expected speedup:** ~ (1 + α + α² + … ) target tokens per target pass, minus draft cost.

## The research lineage
- **Classical** (Leviathan 2022; Chen 2023) [F] — separate draft model.
- **n-gram / self-draft** — reuse context or prior outputs; no extra model. [I]
- **Medusa** (Cai 2024, arXiv:2401.10774) [F] — extra heads on the target predict future
  tokens; verify with target. No separate draft model.
- **EAGLE / EAGLE-2** (Li 2024, arXiv:2401.15077 / arXiv:2406.16858) [F] — lightweight
  autoregressive head on the target's features; high acceptance; now a production
  standard in vLLM/SGLang. [F: vLLM/SGLang docs]
- **Multi-Token Prediction (MTP)** (Gloeckle 2024, arXiv:2404.19745) [F] — train the model
  to predict multiple next tokens; DeepSeek-V3 uses MTP [F: tech report].
- **Self-speculative / lookahead** — chunked self-verification, draft = target on subset.
- **DFlash / Spec V2 / STAGE** (2024–2026) [F: SGLang] — tree/layer-wise drafting for
  higher acceptance.
- **2026 edge/edge-cloud**: SPADE, MemSpec, DARTree (diffusion drafting) [preprint 2026-08,
  UNVERIFIED].

## When it helps / does nothing / hurts
- **Helps:** low batch (B≈1–8), latency-critical, large target where draft is tiny,
  coherent/low-entropy text (code, templated). [I]
- **Does nothing:** high batch (weight stream already amortized), short outputs. [I]
- **Hurts:** draft-target mismatch (low α), very long drafts (verify cost), hardware where
  the draft model itself is bandwidth-bound, or when the target is already small. [I]

## Production practice
- vLLM and SGLang both ship EAGLE + n-gram + Medusa-class spec decoding [F: docs].
- Acceptance is workload-dependent; measure per-workload, don't assume a fixed speedup.

## Related
`Inference/The-Life-of-a-Token.md` · `Inference/Roofline.md` · `Labs/Lab-7`.

## Key Takeaways
Speculative decoding is a **latency** tool (ITL), not a **throughput** tool. It's
distribution-preserving. EAGLE/MTP are the 2024+ workhorses. Measure acceptance per
workload.
