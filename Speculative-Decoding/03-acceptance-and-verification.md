# Acceptance and Verification: The Math That Governs Everything
`LAST_UPDATED: 2026-08-27` · Status: core page
Sources: formulas per Leviathan et al. (arXiv:2211.17192); all numbers in this page computed this session (scripts at /tmp/sd-research/math_sd.py) [E]; batch-inversion evidence from D-cut (2607.14647), Nightjar (2512.22420), "Performance or Illusion?" (2601.11580) [F].

## 30-Second Explanation
Everything in speculative decoding reduces to one currency: **accepted tokens per
target forward pass**. Acceptance rate α per drafted position determines the expected
accepted length τ ≈ (1-α^{K+1})/(1-α); draft cost divides the speedup; and the optimal
draft length K is where marginal acceptance no longer pays for its own verification.
High acceptance alone is not the goal — high *net* throughput is.

## The quantities
| Symbol | Name | Meaning |
|---|---|---|
| α | token acceptance rate | P(a drafted token is accepted), per position |
| α_k | position-k acceptance | acceptance conditional on the first k-1 tokens accepted |
| τ | accepted length (mean) | expected tokens committed per cycle, bonus included |
| K | speculative depth | tokens drafted per cycle |
| c | draft-cost ratio | drafter step cost / target step cost |

## The prefix picture
```text
Draft:      A → B → C → D → E
Target:     A ✓
            B ✓
            C ✓
            D ✗
Accepted = A B C,  then bonus token from the target = A B C X
```

Acceptance compounds multiplicatively along the block. If each position k has its own
per-token acceptance α_k, the probability the first j draft tokens are all accepted is
the **prefix survival** `a_j = α_1·α_2·...·α_j` — a product that decays fast when the
α_k fall. This is the quantity DSpark's scheduler estimates and prunes on (see
[12 DSpark](12-dspark.md)).

## Why acceptance decays with depth (suffix decay)
Position k is drafted conditioned on the *drafter's* own tokens t_1..t_{k-1}. Each
commitment narrows the future: the deeper into the block, the more the drafter's
context has drifted from any single path the target would have taken, and the lower
α_k goes. A parallel drafter (one pass, no intra-block conditioning) suffers the worst
version of this: positions beyond the first are marginal samples that can collide —
"of problem" instead of "of course" [F: DSpark 2607.05147 §3.1]. An autoregressive
drafter conditions properly but pays K sequential steps; the whole drafter-design space
is a fight against suffix decay.

## The expected-length model
For i.i.d. per-position acceptance α and depth K (Leviathan et al. 2022):

```text
E[tokens per verify pass] = 1 + α + α² + ... + α^K = (1 - α^(K+1)) / (1 - α)
```

Python-verified values [E]:

| α \ K | 2 | 4 | 8 | 16 |
|---|---|---|---|---|
| 0.5 | 1.75 | 1.94 | 2.00 | 2.00 |
| 0.7 | 2.19 | 2.77 | 3.20 | 3.33 |
| 0.8 | 2.44 | 3.36 | 4.33 | 4.89 |
| 0.9 | 2.71 | 4.10 | 6.13 | 8.33 |
| 0.95 | 2.85 | 4.52 | 7.40 | 11.64 |

The plateau is the point: at α=0.8, drafting beyond K≈21 adds < 0.01 tokens [E], and
at α=0.5 the ceiling is ~2 tokens no matter what. **Long blocks are only useful when
acceptance is high — the block length is capped by decay, not by the drafter's
throughput.**

Worked decay example (per-position α_k = 0.98, 0.95, 0.92, 0.80, 0.60, 0.40, 0.20, 0.10)
[E]:
- P(all 8 accepted) = 0.33% — the full block almost never survives.
- E[accepted length] = 4.06 tokens.
- P(first 4 accepted) = 68.5% — verifying positions 5-8 mostly burns capacity.

## The speedup model
Time per cycle = K drafter steps + 1 target verify pass. Baseline = 1 token per target
pass. With c = drafter/target step-cost ratio:

```text
S(K) = E[tokens per pass] / (1 + K·c)
```

Python-verified optima [E]:

| c (draft cost ratio) | α=0.8 best K | speedup |
|---|---|---|
| 0.02 | 11 | 3.82× |
| 0.05 | 8 | 3.09× |
| 0.10 | 6 | 2.47× |
| 0.20 | 4 | 1.87× |

| α (acceptance) | best K at c=0.05 | speedup |
|---|---|---|
| 0.6 | 4 | 1.92× |
| 0.7 | 6 | 2.35× |
| 0.8 | 8 | 3.09× |
| 0.9 | 13 | 4.67× |

Read this table twice:
1. **Cheap drafter ⇒ deeper speculation.** The optimal K moves from 4 to 11 as the
   drafter gets cheaper; K is a knob coupled to c, not a constant.
2. **High acceptance ≠ automatically high throughput.** Acceptance multiplies the
   numerator, but the denominator (draft cost) and the *verify* cost of the deeper
   block both grow too. The metric that matters is net tokens/sec, and beyond optimal
   K it *declines*.

## Theoretical upper bound
Let α → 1 (perfect drafter). What still caps speedup?
- **Draft cost floor:** even a free-ish drafter takes K serial steps per cycle; at
  small K the cycle is draft-dominated, so an infinitely good drafter argues for
  *bigger* K, which re-exposes verify cost.
- **Verification width:** verifying K+1 positions is not free FLOPs — at large batch
  it is compute, not bandwidth, and stops being free (see below).
- **Memory movement and KV ops:** committing/rolling back speculative KV entries,
  longer attention over the block, cache-resize churn.
- **Kernel/scheduler overheads:** variable-width batches defeat fixed-shape CUDA-graph
  replay (one motivation for DSpark's asynchronous design [F: 2607.05147 §5.2]).
- **Batch size:** at B≫1 the +K positions multiply across requests; the batch, not the
  weight stream, becomes the budget.

## Algorithmic speedup vs system speedup (the distinction that matters)
```text
ALGORITHM:  how many tokens are accepted per target forward pass?
            (τ from the tables above — publishable, reproducible)

SYSTEM:     how much does wall-clock latency/throughput actually improve?
            = algorithmic gain, discounted by:
              draft latency in the serving loop
              batch-capacity consumption of verification
              KV memory (draft model + speculative entries)
              kernel efficiency (variable-width shapes vs CUDA graphs)
              scheduler behavior under the live request mix
```

A reported "3× speculative speedup" measured at batch 1 does not imply 3× production
throughput at batch 64. Evidence that gains shrink or invert with load [F]:
- *Speculative Decoding: Performance or Illusion?* (2601.11580): on production-grade
  vLLM, verification dominates execution and measured gains fall well below
  theoretical upper bounds once realistic batch sizes are used.
- D-cut (2607.14647): with high concurrency, long drafts can make speculation *slower*
  than autoregressive decoding; cross-request verification pruning restores
  1.26× → 1.65× average speedup.
- Nightjar (2512.22420): speculation helps in low-load memory-bound regimes and
  degrades in high-load compute-bound ones; the planner sometimes disables it.
- DSpark (2607.05147): frames indiscriminate verification as a batch-capacity problem
  and schedules verification against a profiled engine capacity curve.
See [15 Batching and Scheduling](15-batching-and-scheduling.md) for the mechanism.

## Worked example (hand-calculable)
70B BF16 target (140 GB) on an H100 (3.35 TB/s): one weight stream ≈ 41.8 ms [E].
At B=1, K=0 (baseline): ~24 tok/s. Verifying a K=4 block (5 positions, same weight
stream): ~120 tok/s ceiling [E] — ×5 from bandwidth amortization alone, before
acceptance. With α=0.8, E[tokens/pass] = 3.36 at K=4 [E] ⇒ ~80 tok/s; subtract the
draft cost at c=0.05 ⇒ ~3.1× net [E]. Now put B=64 through the same pass: the verify
batch is 64×(K+1) = 320 token-slots versus 64 without speculation — the compute
5×'s too, and the pass is no longer bandwidth-bound. That is where the win dies.

## Failure modes
- Overdrafting: K beyond the plateau pays verify FLOPs + transient KV for tokens that
  die at the first rejection.
- Confidence mis-calibration: any threshold scheduler built on uncalibrated confidence
  mis-truncates (DSpark adds Sequential Temperature Scaling for exactly this [F]).
- Ignoring load: a static K tuned at batch 1 is the wrong K at batch 64.

## How to measure it
Acceptance per position (α_k histogram), mean τ, drafted-vs-verified token counts,
verify batch occupancy, tokens/s/user and total tok/s at fixed concurrency sweep.
Protocol: [18 Performance Benchmarking](18-performance-benchmarking.md).

## Key Takeaways
1. τ = (1-α^(K+1))/(1-α) is the workhorse formula; α decays with depth, so K has a
   ceiling beyond which extra drafts are waste.
2. Optimal K grows as draft cost c falls and as α rises — tune them together.
3. Prefix survival `a_j = ∏ α_i` is the quantity that load-aware schedulers estimate
   and prune on.
4. Algorithmic acceptance is not system throughput: batch capacity, KV memory, and
   kernel behavior discount the headline numbers, sometimes to zero or below.
5. The theoretical limit at perfect acceptance is set by draft latency, verification
   width, and memory operations — speculation never becomes free.

## Related
[02 Draft and Verify](02-draft-and-verify.md) ·
[12 DSpark](12-dspark.md) · [15 Batching and Scheduling](15-batching-and-scheduling.md) ·
[13 GPU System Behavior](13-gpu-system-behavior.md) ·
`../Inference/Roofline.md` · `../Inference/Inference-Metrics.md`

## References
- Leviathan et al., arXiv:2211.17192 [F] · Chen et al., arXiv:2302.01318 [F]
- DSpark, arXiv:2607.05147 [F] · D-cut, arXiv:2607.14647 [F] · Nightjar, arXiv:2512.22420 [F]
- *Speculative Decoding: Performance or Illusion?*, arXiv:2601.11580 [F: independent benchmark]
- All numeric tables: Python-verified this session [E]
