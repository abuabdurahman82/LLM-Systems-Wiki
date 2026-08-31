# Speculative-Decoding Taxonomy
`LAST_UPDATED: 2026-08-27` · Status: core page
Sources: per-family primary papers cited inline; IDs verified as listed in [21 Comparison Matrix and References](21-comparison-and-references.md).

## 30-Second Explanation
"Speculative decoding" is a family: any cheap proposer + a verifier + an acceptance
rule. The families differ in *where the proposal comes from* (external model, the
target itself, extra heads, features, retrieval), *how proposals are structured*
(chain vs tree), and *how verification is scheduled* (static vs per-request vs
load-aware). Picking a family = trading draft latency, acceptance, memory, training
cost, and serving complexity against your workload.

## The family tree
```text
SPECULATIVE DECODING
│
├── Independent Draft Model ......... classical (Leviathan 2211.17192, Chen 2302.01318)
├── Self-Speculative ................ Draft&Verify 2309.08168, LayerSkip 2404.16710,
│                                     early exit, hybrid-model self-spec 2605.01106
├── Multi-Head Prediction ........... Medusa 2401.10774
├── Multi-Token Prediction (MTP) .... Gloeckle 2404.19737, DeepSeek-V3 2412.19437
├── Feature-Level Drafting .......... EAGLE 2401.15077, EAGLE-2 2406.16858, EAGLE-3 2503.01840
├── Tree-Based Speculation .......... SpecInfer 2305.09781, EAGLE dynamic trees
├── Retrieval-Based Speculation ..... REST 2311.08252, prompt-lookup n-gram
├── Parallel Drafting ............... DFlash, DeLS-Spec 2607.07409
├── Semi-Autoregressive Drafting .... DSpark 2607.05147, PCTree 2608.02123
└── Adaptive / Load-Aware ........... DISCO 2405.04304, D-cut 2607.14647,
                                      Nightjar 2512.22420, DSpark scheduling
```

## Per-family fact sheet

### Independent draft model
- **Proposer/verifier:** small model drafts; full target verifies. Ex: Llama-1B → Llama-70B.
- **Topology:** chain. **Training:** none if an aligned checkpoint exists.
- **Memory:** second model + second KV cache (draft contexts).
- **Acceptance:** good only if the drafter is genuinely close to the target (distillation helps).
- **Ideal:** any workload when a same-family small model exists. **Limits:** two-model ops;
  tokenizers must align; drafter latency grows with size.
- Deep dive: [05 Classical Speculative Decoding](05-classical-speculative-decoding.md).

### Self-speculative (target drafts with less compute)
- **Proposer:** the target itself — shallow layers (Draft & Verify), early exit (LayerSkip),
  or architecture-native components (hybrid SSM/attention subgraphs, 2605.01106).
- **Verifier:** the full target. **Topology:** chain.
- **Training:** none (layer-selection heuristics) to a modified recipe (LayerSkip).
- **Memory:** no second model; draft KV is partially shared.
- **Acceptance:** lower than trained drafters; architecture-dependent.
- **Ideal:** single-model deployments, edge/CPU where a second model is unaffordable.
  **Limits:** weak on models without redundant layers.

### Multi-head prediction (Medusa)
- **Proposer:** extra decoding heads on the target's top hidden state, each predicting
  t+1, t+2, ... t+n in one pass; candidates form a tree; tree attention verifies.
- **Training:** fine-tune heads only (Medusa-1, frozen backbone, lossless; >2.2×) or
  heads+backbone (Medusa-2, 2.3-3.6×) [F: 2401.10774 abstract].
- **Memory:** heads are small; tree attention adds verify width.
- **Ideal:** owned models where a light fine-tune is OK. **Limits:** needs training;
  heads drift on out-of-domain data.
- Deep dive: [08 Medusa](08-medusa.md).

### Multi-Token Prediction (MTP)
- **Proposer:** future-token prediction modules trained *with* the model (Gloeckle:
  n parallel heads; DeepSeek: causal chain of depth D modules).
- **Key distinction:** MTP-as-training-objective (better representations) vs
  MTP-as-drafter (the trained module proposes tokens at serving).
- **Ideal:** models shipped with native MTP modules (DeepSeek-V3: D=1, 85-90% second-token
  acceptance, 1.8× TPS [F: 2412.19437 §5.4.3]).
- **Limits:** not retrofit-able without training; D=1 is a short block — multi-depth
  reuse is where products differ.
- Deep dives: [10 Multi-Token Prediction](10-multi-token-prediction.md),
  [11 DeepSeek MTP](11-deepseek-mtp.md).

### Feature-level drafting (EAGLE family)
- **Proposer:** lightweight autoregressive drafter over the target's hidden features
  (not tokens), fed feature + sampled-embedding pairs; tree drafting (EAGLE-2 dynamic
  trees); EAGLE-3 fuses low/mid/high features and trains with training-time test.
- **Training:** one-time drafter training on target outputs.
- **Acceptance:** the 2024-25 acceptance/latency frontier for many open models
  (SGLang docs' best-tier default [F: docs.sglang.ai]).
- **Ideal:** low-to-mid concurrency latency. **Limits:** drafter training run required;
  coupling to target internals.
- Deep dive: [09 EAGLE Family](09-eagle-family.md).

### Tree-based speculation
- **Proposer:** multiple drafter branches (multiple SSMs in SpecInfer; multiple head
  continuations in Medusa; confidence-expanded trees in EAGLE-2) merged into a token tree.
- **Verifier:** target in one tree-attention pass; longest accepted *path* wins.
- **Why trees beat chains:** hedges the drafter's uncertainty — early rejections no
  longer invalidate every downstream token, at the price of wider verification batches.
- **Memory/compute:** verify batch = tree size; grows super-linearly if unchecked
  (SMART 2604.09731 documents the resulting "efficiency paradox").
- Deep dive: [07 SpecInfer](07-specinfer-tree-decoding.md).

### Retrieval-based speculation
- **Proposer:** suffix-array/n-gram lookup over a corpus (REST), the live prompt
  (prompt-lookup), or generated text (vLLM ngram, SGLang NGRAM, suffix decoding).
- **Training:** none. **Topology:** tree (REST) or chain (prompt-lookup).
- **Ideal:** code, templated/structured output, summarization, editing — any workload
  whose output echoes known text. Connects directly to
  [../KV-Cache/Prompt-and-Prefix-Caching.md](../KV-Cache/Prompt-and-Prefix-Caching.md).
- **Limits:** near-zero acceptance on novel prose; datastore memory.
- Deep dive: [06 Retrieval and Self-Speculation](06-retrieval-and-self-speculative.md).

### Parallel drafting
- **Proposer:** one forward pass emits the whole block (DFlash-class), anchor token +
  mask positions; drafting latency ~ independent of block size.
- **Catch:** no intra-block dependency ⇒ fast suffix decay (the "of problem" problem).
- **Ideal:** long blocks at low latency; drafts re-ranked by a confidence model.
- **Limits:** acceptance at depth; mitigation is exactly what semi-AR drafting adds.

### Semi-autoregressive drafting (DSpark-class)
- **Proposer:** parallel backbone + lightweight sequential module (Markov/RNN head)
  injecting intra-block dependency at negligible latency.
- **Scheduler:** confidence head estimates per-position prefix survival; verification
  length scheduled per request against the engine's throughput profile.
- **Ideal:** production serving under live, variable load.
- Deep dive: [12 DSpark](12-dspark.md).

### Adaptive / load-aware speculation
- **What varies:** speculative depth (DISCO), tree size (SMART), verification depth
  (D-cut), enable/disable per load (Nightjar), per-request verify length (DSpark).
- **Why it exists:** wasted verification is a batch-capacity tax at concurrency —
  the evidence and mechanisms are in
  [15 Batching and Scheduling](15-batching-and-scheduling.md).

## Training-free vs training-required
```text
SPECULATIVE DECODING
├── Training-free ........ independent draft models, retrieval/n-gram, self-speculation
│                          (layer-skip choice), lookahead/Jacobi
└── Training required .... Medusa heads, EAGLE drafters, MTP modules,
                           DSpark-class semi-AR drafters, boost-tuned SpecInfer SSMs
```
Deployment implication: training-free methods deploy in minutes and lag the state of
the art; trained methods buy higher acceptance with a training pipeline, checkpoint
management per target model, and re-training on model upgrades.

## Five-generation mental model (educational lens, not researchers' terminology)
| Gen | Principle | Families |
|---|---|---|
| 1 | external small drafter | classical |
| 2 | trees / multi-candidate | SpecInfer, REST |
| 3 | target-attached heads | Medusa |
| 4 | feature-level & native MTP | EAGLE-1/2/3, DeepSeek MTP |
| 5 | adaptive, load-aware serving | DSpark, D-cut, Nightjar |

Generations *compound* rather than replace: DSpark's scheduler (Gen 5) runs on top of
parallel drafting; EAGLE-3 (Gen 4) uses trees (Gen 2) in its draft expansion.

## Key Takeaways
1. The taxonomy's first axis is the drafter's *source*; the second is proposal
   *topology*; the third — the newest — is *verification scheduling*.
2. Training-free families trade acceptance for deployability; trained families buy
   acceptance with pipeline and per-model upkeep.
3. Parallel drafting solves draft latency but inherits suffix decay; semi-AR drafting
   is the 2026 synthesis (parallel speed + AR dependency).
4. Tree speculation is the general shape; chains are its degenerate case.
5. There is no universal winner: the right family is a function of model ownership,
   workload predictability, and concurrency profile.

## Related
[03 Acceptance and Verification](03-acceptance-and-verification.md) ·
[05 Classical](05-classical-speculative-decoding.md) ·
[09 EAGLE Family](09-eagle-family.md) · [12 DSpark](12-dspark.md) ·
[19 Production Design](19-production-design.md)

## References
Full ID list in [21 Comparison Matrix and References](21-comparison-and-references.md).
