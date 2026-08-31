# Draft and Verify: The Core Algorithm
`LAST_UPDATED: 2026-08-27` · Status: core page
Sources: verified against Leviathan et al. (arXiv:2211.17192), Chen et al. (arXiv:2302.01318), Stern et al. (arXiv:1811.08475), Zhou et al. Draft&Verify (arXiv:2309.08168); see [21 Comparison Matrix and References](21-comparison-and-references.md).

## 30-Second Explanation
One loop: **draft K tokens → verify all K in one target pass → accept the longest
prefix that the target agrees with → append one bonus token → repeat.** With
distribution-preserving rejection sampling, every emitted token is a sample from the
target model's own conditional distribution — the output is provably identical to
running the target alone, just faster.

## Historical origin
Two eras, one idea:

```text
2018  Blockwise Parallel Decoding (Stern et al., arXiv:1811.08475)
      - trains extra prediction heads to propose blocks (retraining required)
      - verifies a block in one pass; accepts the longest GREEDY-consistent prefix
      - greedy-only acceptance: changes the sampling distribution unless T=0
2022  Speculative Decoding (Leviathan et al., arXiv:2211.17192)
      - separate draft model, no target retraining
      - REJECTION SAMPLING acceptance ⇒ output distribution exactly preserved
        for ANY temperature/sampling scheme
2023  Speculative Sampling (Chen et al., arXiv:2302.01318)
      - DeepMind's independent formulation; same accept rule; popularized it
```

Blockwise (2018) proved block verification works but needed retrained heads and only
preserved greedy outputs. The 2022-23 papers' leap was an acceptance rule that makes
speculation **lossless for arbitrary sampling**: that is the moment speculative
decoding became safe to deploy.

## The algorithm
```text
loop:
    # 1. DRAFT (K cheap steps of the drafter, autoregressive)
    for i in 1..K:  t_i ~ q(· | x_<, t_<i)

    # 2. VERIFY (ONE parallel target pass over [context, t_1..t_K])
    p_i = target(· | x_<, t_1..t_i)      for i = 1..K

    # 3. ACCEPT/REJECT walk (left to right)
    for i in 1..K:
        r ~ Uniform(0,1)
        if r < min(1, p_i(t_i) / q_i(t_i)):      # acceptance rule
            accept t_i;  continue
            # first failure stops the walk:
        resample  t_i' ~ norm(max(p_i - q_i, 0)) # correction distribution
            break

    # 4. COMMIT: accepted prefix + one bonus token from the target
    if all K accepted:  also sample bonus x+ ~ p_K(· | x_<, t_1..t_K)
```

Notation: `q_i` = drafter distribution at position i, `p_i` = target distribution at
the same position.

## The mathematics of losslessness
For a drafted token `t ~ q` with target distribution `p` over the same context, define
the acceptance probability and residual:

```text
accept prob :  min(1, p(t)/q(t))
residual    :  norm(max(p - q, 0))(t)  =  (p(t) - q(t))+ / Σ_u (p(u) - q(u))+
```

Then the mixture

```text
P(emit t) = q(t) · min(1, p(t)/q(t))  +  residual(t) · (1 - Σ_u q(u)·min(1, p(u)/q(u)))
          = p(t)          [exactly]
```

Intuition in three lines: where the drafter already agrees with the target (`q ≤ p`),
drafting passes tokens through unchanged. Where the drafter overshoots the target, the
token is sometimes rejected, and the correction distribution re-injects exactly the
probability mass `p - q` the drafter stole. The mixture reconstitutes `p` regardless of
how bad `q` is — **badness costs speed, never correctness** [F: Leviathan et al. 2022,
Thm 3.5-3.8; Chen et al. 2023].

Consequences:
- Greedy decoding (T=0): the walk reduces to "accept while `t_i` equals the target's
  argmax" — the accepted prefix is *identical* to greedy target output.
- Temperature/top-p sampling: the rule above applies to the full distributions; no
  bias at any temperature.
- The bonus token is drawn from the target itself, so each cycle guarantees ≥ 1
  accepted token.

### What "lossless" does and does not mean
- **Lossless** = the emitted sequence distribution equals the target model's, up to
  floating-point non-determinism from batched kernels (engine-level logprobs can wobble
  — vLLM documents this [F: docs.vllm.ai]).
- **Not lossless:** approximate verification (ASD 2608.03447 accepts some mismatches
  under a regret budget [F]), distillation shortcuts, or draft-only streaming without
  target verification. These trade quality for speed and must be labeled as such.

## Why verify-in-parallel is cheap
A target forward pass over `1 + K` positions executes the same weight stream as a pass
over 1 position; the extra positions are extra rows in the batch dimension:

```text
Cost of one target pass, B=1:      ≈ weight-bytes / HBM-bandwidth   (+ attention)
Verify K candidates:               ≈ same weight stream, K+1 positions of math
K independent target passes:       = K × (weight stream)   ← what speculation removes
```

While the pass is memory-bound (low batch), the math rides almost free on the weight
stream. This is why speculation is a *bandwidth-arbitrage* technique: it converts
wasted bandwidth headroom into tokens per pass. Numbers and the roofline treatment:
[13 GPU System Behavior](13-gpu-system-behavior.md).

## Draft sources (where t_1..t_K come from)
Any cheap generator of conditional distributions `q_i` works:

| Draft source | Training | Example |
|---|---|---|
| Small model, same tokenizer | none (existing checkpoint) | Llama-1B → Llama-70B |
| Target's own shallow layers | none (layer choice) | Draft & Verify (2309.08168) |
| Early-exit of target | modified recipe | LayerSkip (2404.16710) |
| Extra heads on target | fine-tune heads | Medusa (2401.10774) |
| Feature-level drafter | train drafter | EAGLE-3 (2503.01840) |
| Native MTP module | trained with model | DeepSeek-V3 (2412.19437) |
| Retrieval / n-gram | none (datastore) | REST (2311.08252) |

Each row has its own latency/acceptance profile — the taxonomy and per-family analysis
are in [04 Taxonomy](04-speculative-decoding-taxonomy.md) and the deep-dive pages.

## Worked example (hand-calculable)
Greedy decoding, K=4, drafter proposes `["The", "cat", "sat", "on"]`:

```text
Target argmax check:
  position 1: "The" == argmax p1 → accept
  position 2: "cat" == argmax p2 → accept
  position 3: "sat" == argmax p3 → accept
  position 4: "on" != argmax p4  → reject; commit "on" from argmax p4 (bonus)
Emitted this cycle: "The cat sat on"   (4 tokens for 1 target pass)
```

Under sampling, replace the argmax checks with `min(1, p/q)` tests plus a resample on
first rejection — same prefix logic, exact target distribution.

## Failure modes
- Drafter-target vocabulary mismatch: acceptance needs aligned tokenizers (vLLM ships
  a Token-Level Intersection mode for cross-vocab drafters, greedy-only [F: docs]).
- KV rollback bugs: rejected positions must be evicted, not just ignored — see
  [14 KV Cache and PagedAttention](14-kv-cache-and-paged-attention.md).
- Sampling-parameter drift: engines verify with the *same* distributions used at
  request time; a mismatch (e.g. verifying greedy while serving T=0.9) silently biases
  output.

## How to measure it
Per-cycle: drafted K, accepted A, bonus (always 1), reject position histogram. Per
workload: mean τ = E[A]+1, α per position. Protocol: [18 Performance Benchmarking](18-performance-benchmarking.md).

## Key Takeaways
1. Draft K → verify K in one pass → commit longest prefix + bonus token.
2. The accept rule `min(1, p/q)` plus the residual correction reproduces the target
   distribution exactly — losslessness is a theorem, not a heuristic.
3. Blockwise decoding (2018) is the greedy-only ancestor; the 2022-23 rejection-sampling
   form is what made speculation deployable for sampling workloads.
4. Verification parallelism is nearly free in the bandwidth-bound regime — the whole
   technique lives on this asymmetry.
5. Losslessness still requires correct implementation: KV rollback, sampling-parameter
   consistency, and (for cross-vocab drafters) token-alignment care.

## Related
[01 Why Speculative Decoding](01-why-speculative-decoding.md) ·
[03 Acceptance and Verification](03-acceptance-and-verification.md) ·
[04 Taxonomy](04-speculative-decoding-taxonomy.md) ·
`../Inference/The-Life-of-a-Token.md` · `../KV-Cache/README.md` ·
`../Inference/Inference-Metrics.md`

## References
- Leviathan et al., arXiv:2211.17192 [F] · Chen et al., arXiv:2302.01318 [F] ·
  Stern et al., arXiv:1811.08475 [F] · Zhou et al., arXiv:2309.08168 [F] ·
  vLLM speculative decoding docs [F: docs.vllm.ai]
