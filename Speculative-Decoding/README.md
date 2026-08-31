# Speculative Decoding: From Draft-and-Verify to EAGLE, MTP, DSpark, and Modern LLM Serving
`LAST_UPDATED: 2026-08-27` · Status: core section (expanded handbook)

> **Draft cheaply, verify in parallel, accept the prefix.** Speculative decoding turns the
> sequential token loop of autoregressive decoding into a partially parallel
> draft-then-verify pipeline — the only widely deployed technique that cuts the
> *number* of sequential target-model passes per emitted token without changing the
> output distribution.

## The one-sentence version
**A cheap proposer suggests K future tokens; the expensive target model verifies all K in
one forward pass; the longest accepted prefix (plus one bonus token) is committed — the
result is distribution-identical to the target model alone, but each target forward pass
now yields several tokens instead of one.**

This section is the engineering handbook: intuition → algorithms → mathematics → GPU
behavior → serving-system behavior → implementations → benchmarking → production
recommendations, current through 2026-08.

## The 30-second explanation
Decode is memory-bandwidth-bound: each generated token streams all model weights from
HBM to produce a single token of output. Speculative decoding amortizes that weight
stream over multiple tokens. A drafter (small model, extra heads, retrieval table, or
the target's own shallow layers) proposes a block; the target verifies the whole block
in one pass; rejection sampling guarantees the output distribution is *exactly* the
target's. Speedup = accepted tokens per target step, discounted by draft cost — and it
is a **latency/interactivity tool that peaks at low-to-moderate concurrency**, not a
free throughput multiplier at saturation.

## The organizing taxonomy (the spine)
```text
SPECULATIVE DECODING
│
├── By drafter source
│   ├── Independent draft model .......... classical (Leviathan 2022, Chen 2023)
│   ├── Self-speculation (same model) .... Draft & Verify, LayerSkip, early exit
│   ├── Target-attached heads ............ Medusa (multi-head), MTP (native module)
│   ├── Feature-level drafter ............ EAGLE / EAGLE-2 / EAGLE-3
│   ├── Parallel / semi-AR drafter ....... DFlash, DSpark, DeLS-Spec, PCTree
│   └── Retrieval / n-gram ............... REST, prompt lookup, suffix decoding
│
├── By proposal topology
│   ├── Chain (one candidate sequence)
│   └── Tree (SpecInfer, Medusa, EAGLE dynamic trees)
│
└── By verification policy
    ├── Static: verify all K drafted tokens (classical)
    ├── Dynamic per-request: confidence thresholds, adaptive-k (DISCO, SpecEE)
    └── Global load-aware: schedule verification vs batch capacity (DSpark, D-cut, Nightjar)
```

## The generational timeline
```text
2018    Blockwise Parallel Decoding (Stern et al.) —— retrained heads, greedy acceptance
        │
2022-23 CLASSICAL SPECULATIVE DECODING
        Leviathan et al. 2211.17192 · Chen et al. 2302.01318 (speculative sampling)
        Small draft model + rejection-sampling verification (lossless)
        │
    ┌───┴────────────┬──────────────────────┐
    ▼                ▼                      ▼
2023-24 SPECINER  2023-24 RETRIEVAL/    2024 MEDUSA
  token trees      SELF-SPEC              extra decoding heads
  multi-drafter    REST · Lookahead ·     tree attention
  tree verify      Draft&Verify · LayerSkip  typical acceptance
    │
    ▼
2024-25 EAGLE ──▶ EAGLE-2 ──▶ EAGLE-3
        feature-level drafting · dynamic draft trees · training-time test
        │
2024-26 MTP (Gloeckle 2404.19737) · DeepSeek-V3 native MTP module (2412.19437)
        train-time multi-token objectives reused as drafters
        │
2026    PARALLEL + ADAPTIVE SERVING
        DFlash (parallel drafting) → DSpark (semi-AR drafting +
        confidence-scheduled verification, DeepSeek-V4 production)
        └─ successors: DeLS-Spec · PCTree · ASD · D-cut · Nightjar
```

## The "five generations" mental model
An educational lens (not terminology used by the original researchers):

| Gen | Idea | Representatives |
|---|---|---|
| 1 | Small external drafter, chain, static verify | Leviathan/Chen 2022-23 |
| 2 | Tree / multi-candidate speculation | SpecInfer, REST |
| 3 | Target-attached prediction heads | Medusa |
| 4 | Feature-level & native-MTP speculation | EAGLE-1/2/3, DeepSeek MTP |
| 5 | Adaptive, load-aware speculative serving | DSpark, D-cut, Nightjar |

## Reading order
### Foundations (the 20% that carries the 80%)
- [01 Why Speculative Decoding](01-why-speculative-decoding.md) — the sequential-decode
  bottleneck, arithmetic intensity, and the core draft/verify idea.
- [02 Draft and Verify](02-draft-and-verify.md) — the algorithm, rejection-sampling
  math, and why the output distribution is provably unchanged.
- [03 Acceptance and Verification](03-acceptance-and-verification.md) — acceptance rate,
  the analytical speedup model, theoretical upper bounds, algorithmic vs system speedup.
- [04 Taxonomy](04-speculative-decoding-taxonomy.md) — the family tree, training-free vs
  training-based, the five-generation lens.

### The technique deep dives
- [05 Classical Speculative Decoding](05-classical-speculative-decoding.md) — draft-model
  sizing, the sweet-spot trade-off, historical timeline.
- [06 Retrieval and Self-Speculation](06-retrieval-and-self-speculative.md) — REST,
  n-gram, lookahead, Draft & Verify, LayerSkip.
- [07 SpecInfer and Tree Verification](07-specinfer-tree-decoding.md) — token trees,
  multi-drafter merging, tree-attention verification.
- [08 Medusa](08-medusa.md) — multiple decoding heads, candidate trees, typical acceptance.
- [09 The EAGLE Family](09-eagle-family.md) — EAGLE → EAGLE-2 → EAGLE-3, feature-level
  drafting, training-time test.
- [10 Multi-Token Prediction](10-multi-token-prediction.md) — MTP as training objective
  and as drafter.
- [11 DeepSeek MTP](11-deepseek-mtp.md) — the V3 MTP module architecture, MTP-1 serving.
- [12 DSpark](12-dspark.md) — semi-autoregressive drafting, confidence-scheduled
  verification, DeepSeek-V4 deployment, EAGLE-3 vs MTP vs DSpark.

### Systems engineering
- [13 GPU System Behavior](13-gpu-system-behavior.md) — what speculation does to tensor
  cores, HBM, occupancy; roofline; quantization interactions.
- [14 KV Cache and PagedAttention](14-kv-cache-and-paged-attention.md) — draft KV,
  commit/rollback, paged allocation, prefix caching.
- [15 Batching and Scheduling](15-batching-and-scheduling.md) — continuous batching
  interaction, batch-size scaling, latency vs throughput, disaggregated serving.
- [16 Workloads, Sampling, and MoE](16-workloads-sampling-and-moe.md) — acceptance across
  domains, sampling parameters, quantization, MoE expert-routing effects.

### Practice
- [17 Framework Implementations](17-framework-implementations.md) — vLLM, SGLang,
  TensorRT-LLM, llama.cpp, NVIDIA Dynamo.
- [18 Performance Benchmarking](18-performance-benchmarking.md) — metrics, experiment
  matrix, labs, home-lab guidance, cost per million tokens.
- [19 Production Design](19-production-design.md) — serving architecture, decision tree,
  when it works / when it hurts, myths vs reality.
- [20 Future Research](20-future-research.md) — the 2025-2026 frontier and open problems.
- [21 Comparison Matrix and References](21-comparison-and-references.md) — the flagship
  comparison table, glossary, and source list.

## Related
`../Inference/The-Life-of-a-Token.md` · `../Inference/Roofline.md` ·
`../Inference/Continuous-Batching.md` · `../Inference/Prefill-Decode-Disaggregation.md` ·
`../KV-Cache/README.md` · `../KV-Cache/Paged-KV-Cache.md` ·
`../KV-Cache/Prompt-and-Prefix-Caching.md` · `../Quantization/README.md` ·
`../Attention/README.md` · `../Model-Architectures/README.md` ·
`../Serving-Engines/vLLM.md` · `../Serving-Engines/SGLang.md` ·
`../Serving-Engines/TensorRT-LLM.md` · `../Distributed-Inference/README.md` ·
`../GPU-Communication/README.md` · `../Labs/`

## Key Takeaways
1. Speculative decoding converts sequential decode into draft (cheap, possibly
   parallel) + verify (one parallel target pass) + commit-prefix; lossless under
   standard rejection sampling.
2. The speedup currency is **accepted tokens per target forward pass**; the ledger also
   contains draft latency, KV overhead, and batch-capacity consumption.
3. Acceptance decays with speculative depth (suffix decay); longer draft blocks are
   not automatically better.
4. Gains peak at low-to-moderate concurrency where the target is memory-bandwidth-bound;
   at saturation, wasted verification can make serving *slower* — hence load-aware
   scheduling (Gen-5 systems).
5. EAGLE-3 (feature-level drafter), native MTP (trained future-token predictor), and
   DSpark (semi-AR parallel drafter + confidence scheduling) are the 2026 production
   front-runners; choose by model support, concurrency profile, and engineering budget —
   benchmark, don't assume.
