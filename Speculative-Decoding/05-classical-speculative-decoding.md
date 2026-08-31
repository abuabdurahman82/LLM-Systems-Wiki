# Classical Draft-Model Speculative Decoding
`LAST_UPDATED: 2026-08-27` · Status: core page
Sources: Leviathan et al. arXiv:2211.17192, Chen et al. arXiv:2302.01318, Stern et al. arXiv:1811.08475 (all title-verified); paper-reported numbers marked [F: paper]; math [E].

## 30-Second Explanation
The original recipe: a small draft model from the same family proposes K tokens
autoregressively; the large target verifies them in one pass with rejection sampling.
Everything hinges on drafter *size*: too small ⇒ low acceptance, too big ⇒ drafting
costs as much as it saves. The sweet spot is typically a drafter 10-100× smaller than
the target that shares its tokenizer and domain.

## The canonical loop
```text
Small Draft Model (e.g. Llama-1B)
       ↓
Generate K tokens (K sequential cheap passes)
       ↓
Large Target Model (e.g. Llama-70B)
       ↓
Verify K tokens in parallel (1 pass)
       ↓
Accept longest valid prefix (+ 1 bonus token)
```

## What the papers report
- Leviathan et al. (2211.17192): 2-3× faster decoding on T5X/Chinchilla-family setups,
  lossless, no target retraining [F: abstract]. Introduced the α-decay model and the
  E[tokens] formula used across this section.
- Chen et al. (2302.01318): same acceptance rule, independent formulation (speculative
  sampling), demonstrated on Chinchilla 70B with ~2× decode speedup [F: abstract].
- Both frame the win as "amortize the weight stream"; the acceptance mathematics are in
  [03 Acceptance and Verification](03-acceptance-and-verification.md).

## The drafter-sizing trade-off
```text
Draft too small → fast drafting → poor acceptance → few accepted tokens
Draft too large → good acceptance → expensive drafting → cycle dominated by drafter
```

Formal shape (from the speedup model S(K) = E[τ]/(1+K·c), see [03](03-acceptance-and-verification.md)):
- Drafter cost c grows roughly linearly with drafter size; acceptance α also grows with
  drafter capacity, but with diminishing returns (both are log-linear in scale —
  Scylla/SD scaling laws, 2505.07858 [F]).
- Optimal drafter sits where dS/d(size) = 0 — in practice 1-3B drafters for 60-70B
  targets are the common sweet spot [I: across published pairings; verify per workload].

| Drafter size | Draft latency | Acceptance α | VRAM | Net effect |
|---|---|---|---|---|
| Tiny (0.1-0.5B) | minimal | low | +~1-2 GB | often < 1.5× [I] |
| Small (1-3B) | low | high | +2-6 GB | usually the sweet spot [I] |
| Mid (7-8B) | moderate | high | +14-16 GB | pays at batch>1; KV double-tax |
| Same family, quantized | low | slightly ↓ | small | often the best $/token trade [I] |

Python-verified sensitivity [E]: at α=0.8, c=0.05 ⇒ 3.09× net; halve the drafter (c=0.025)
but lose 10 points of acceptance (α=0.7) ⇒ 2.35×; double it (c=0.1) for α=0.85 ⇒
~2.6×. Acceptance must be *bought efficiently* — acceptance points that cost more
latency than they return are a net loss.

## Model-loading and ops overhead
- A second model means: second weights resident (or swapped), a second KV arena, a
  second graph/capture set, and scheduler coupling. vLLM/SGLang accept a
  `draft_model` with its own TP size (`draft_tensor_parallel_size`) [F: docs].
- Quantized drafters (e.g. INT4/FP4 draft under a BF16/FP8 target) shrink the second
  model's footprint; acceptance impact is usually small for the *draft* side because
  only rank-order matters, but verify the claim per model — see
  [16 Workloads, Sampling, and MoE](16-workloads-sampling-and-moe.md).

## Historical timeline (phase 0 → 1)
```text
2018   Blockwise Parallel Decoding (Stern et al., 1811.08475)
       - retrained multi-head proposals; greedy block verification; no draft model
       - the "verify a block in one pass" core idea
2022   Speculative Decoding (Leviathan et al., 2211.17192)
       - rejection-sampled acceptance, lossless for any sampler; draft model = any
         cheap network; E[τ] formula and (γ, α) speedup analysis
2023   Speculative Sampling (Chen et al., 2302.01318)
       - same rule, DeepMind framing; production interest ignites
2023   SpecInfer (2305.09781), Draft&Verify (2309.08168), OSD (2310.07177),
       REST (2311.08252) — trees, self-speculation, online distillation, retrieval
```
Blockwise needed retraining and preserved only greedy output; the 2022-23 rejection-
sampling form is training-free on the target and lossless for any sampler — that
combination is what turned the idea into an industry default.

## Worked example (hand-calculable)
Pairing: draft 1B (BF16, 2 GB weights) → target 70B (BF16, 140 GB), H100 [E].
- Target step ≈ 41.8 ms (weight stream); draft step ≈ 2/140 × 41.8 ≈ 0.6 ms ⇒ c ≈ 0.014 [E].
- At α=0.8, K=8: E[τ] = (1-0.8⁹)/0.2 ≈ 4.33 [E]; S ≈ 4.33/(1+8·0.014) ≈ 3.9× [E].
- VRAM: 140 + 2 GB weights + KV — the drafter is rounding error; the *draft KV arena*
  is the real added cost at scale ([14](14-kv-cache-and-paged-attention.md)).

## Failure modes
- Tokenizer mismatch between drafter and target (alignment needed; greedy-only
  workarounds like vLLM's TLI mode [F: docs]).
- Domain drift: a general drafter underperforms on code/math; consider domain-tuned or
  online-distilled drafters (OSD 2310.07177 [F]).
- Batched serving: the win shrinks with concurrency — schedule K per load
  ([15](15-batching-and-scheduling.md)).

## How to measure it
Sweep drafter size {0.5B, 1B, 3B, 7B} × depth K {2..16}; record α per position, τ,
tok/s/user, VRAM, and per-request p50/p95. Protocol: [18 Performance Benchmarking](18-performance-benchmarking.md).
Reproduce Lab 2 ([18](18-performance-benchmarking.md)) for the sweet spot on your stack.

## Key Takeaways
1. Classical SD = two models, chain drafting, rejection-sampled verification, ≥1 token
   guaranteed per target pass.
2. Drafter size is an optimization variable: the objective is net speedup
   S(α(size), c(size)), not acceptance alone.
3. The 2018→2022 transition (retrained heads → training-free lossless acceptance) is
   the historical pivot of the whole field.
4. Two-model ops cost (memory, loading, TP for the drafter) is real but usually
   outweighed by the latency win at low concurrency.
5. Measure α and c on *your* workload — both are workload-dependent and the published
   pairs are hypotheses, not guarantees.

## Related
[02 Draft and Verify](02-draft-and-verify.md) · [03 Acceptance and Verification](03-acceptance-and-verification.md) ·
[04 Taxonomy](04-speculative-decoding-taxonomy.md) ·
[09 EAGLE Family](09-eagle-family.md) (the modern replacement for many classical pairs) ·
`../Serving-Engines/vLLM.md`

## References
- Leviathan et al., arXiv:2211.17192 [F] · Chen et al., arXiv:2302.01318 [F]
- Stern et al., arXiv:1811.08475 [F] · Scylla scaling laws, arXiv:2505.07858 [F]
- vLLM / SGLang speculative decoding docs [F: docs]
