# Why Speculative Decoding
`LAST_UPDATED: 2026-08-27` · Status: core page
Sources: verified against Leviathan et al. (arXiv:2211.17192), Chen et al. (arXiv:2302.01318), Stern et al. (arXiv:1811.08475), Xia et al. survey (arXiv:2401.07851); see [21 Comparison Matrix and References](21-comparison-and-references.md).

## 30-Second Explanation
Autoregressive LLM decoding is a **serial loop**: token N+1 cannot exist until token N
has been committed, and each commitment costs a full forward pass that streams every
model weight from HBM. Speculative decoding attacks the *serial* part, not the
arithmetic: a cheap drafter guesses several future tokens, and the expensive target
model checks them all in **one** parallel forward pass. Same distribution, fewer
sequential steps.

## The baseline: normal autoregressive decoding
```text
Prompt
   ↓
Prefill  (one parallel pass over the prompt)
   ↓
Token 1
   ↓
Forward pass  (full weight stream, 1 token out)
   ↓
Token 2
   ↓
Forward pass
   ↓
Token 3
   ...
```

Generation is sequential because the model itself is defined by the chain rule:

```text
P(x1, ..., xn) = P(x1) · P(x2|x1) · P(x3|x1,x2) · ... · P(xn|x1..xn-1)
```

Token N+1 is sampled from `P(x_{N+1} | x1..xN)` — a distribution that does not exist
until token N is known and in the KV cache. This is not an implementation artifact; it
is the model's semantics. Parallelizing decode means changing *how the sequence of
distributions is realized*, not denying the dependency.

### PREFILL vs DECODE
```text
PREFILL → highly parallel: N tokens × 1 pass, arithmetic intensity high,
          compute-bound, saturates tensor cores.
DECODE  → highly sequential: 1 token × 1 pass per step, arithmetic intensity ~1 FLOP
          per weight-byte loaded, memory-bound, GPU starved.
```

## The bottleneck: why decode is hard to make fast
Every decode step is a full transformer forward pass whose cost is dominated not by
math but by **memory traffic**:

| Factor | What happens at decode (batch small) |
|---|---|
| Weight reads | Every step streams all weights (e.g. ~140 GB for a 70B BF16 model) to produce 1 token |
| Arithmetic intensity | ~2 FLOPs per weight byte → far below any GPU's ridge point [E] |
| HBM bandwidth | The step time ≈ total-weight-bytes / memory-bandwidth (41.8 ms for 140 GB on an H100's 3.35 TB/s [E]) |
| KV cache reads | Attention re-reads the whole cached context each step |
| Kernel launch + sync | Hundreds of small kernels per step; launch overhead and synchronization dominate at tiny batch |
| GPU occupancy | Tensor cores idle: batch-1 GEMV/MATVEC shapes do not fill SMs |

See `../Inference/Roofline.md` and `../Inference/The-Life-of-a-Token.md` for the
baseline roofline treatment; `../KV-Cache/README.md` for cache growth.

The consequence: at batch size 1, a modern GPU decoding a large model runs at a few
percent of its FLOPs capability — it is a **bandwidth machine acting as a latency
machine**. Batching helps throughput by amortizing the weight stream across requests,
but a *single* user's latency (ITL/TPOT) is still one-token-per-pass. That is the gap
speculative decoding attacks.

## The core idea
> **Analogy.** A junior writer drafts the next several sentences quickly. A senior editor
> reads all of them *at once*, strikes the first wrong word, and hands back everything
> up to the mistake plus one guaranteed-correct word of their own. The editor's review
> is one pass regardless of how many words the junior proposed.

In LLM terms:

```text
             ┌──────────────┐
Current ────▶│ Draft Model  │   (cheap, K sequential steps of a small model,
Tokens       └──────┬───────┘    or one parallel pass of extra heads)
                    │
              predict K tokens
                    │
                    ▼
          [t1][t2][t3][t4]
                    │
                    ▼
             ┌──────────────┐
             │ Target Model │   (ONE forward pass over [ctx, t1..tK])
             └──────┬───────┘
                    │
          verify simultaneously
                    │
          ┌─────────┴────────┐
          │                  │
     Accepted prefix     Rejected suffix
     (+ 1 bonus token)   (rollback)
```

The key economics: **verifying K candidate tokens costs almost the same as generating
one token** while the model is bandwidth-bound. The weights are streamed once either
way; the K+1 positions ride along as an extra batch dimension. Verifying K drafted
tokens in one pass is therefore much cheaper than K independent target passes — that is
the entire economic argument.

## What the target pass must decide (vocabulary preview)
For each drafted position i, the target pass produces `p_target(·|ctx, t1..ti)`. The
engine then walks the block left to right: accept a token if it is consistent with the
target's distribution under the acceptance rule, stop at the first rejection, and
commit the longest valid prefix plus one bonus token drawn from the target's own
correction distribution. The full acceptance rule and its losslessness proof are in
[02 Draft and Verify](02-draft-and-verify.md); the acceptance-rate mathematics are in
[03 Acceptance and Verification](03-acceptance-and-verification.md).

### Why this converts sequential → partially parallel
- **Without speculation:** 1 target pass ⇒ 1 token. Emitted tokens-per-pass = 1.
- **With speculation:** 1 target pass ⇒ A accepted tokens (A ≥ 1, the bonus token
  included), where A is the average accepted prefix length.
- The serial dependency chain is now *draft-steps + 1 target pass per cycle* instead of
  *1 target pass per token*. If the drafter is cheap and honest, the chain shortens.

### What speculation is NOT
- It is not caching or reuse — every committed token is (in distribution) exactly what
  the target model would have produced. See [02](02-draft-and-verify.md) for the proof.
- It is not automatically a throughput win: at high concurrency the verify batch
  capacity is precious, and verifying doomed tokens *steals* capacity from other
  requests. See [15 Batching and Scheduling](15-batching-and-scheduling.md).

## Example (hand-calculable)
Draft K=4 tokens with a 1B drafter; target is 70B BF16 on an H100 (3.35 TB/s).
One target weight stream ≈ 140 GB / 3.35 TB/s ≈ 41.8 ms [E]. Baseline: 1 token per
41.8 ms ≈ 24 tok/s. If verification accepts on average A=3.4 tokens, each 41.8 ms
target pass yields ~4 tokens ⇒ ~96 tok/s before draft cost [E]; with a drafter at
~5% of the target's step cost, net speedup ≈ 4 / (1 + 4·0.05) ≈ 3.4× [E]. The same
arithmetic at batch 64 shows why the win shrinks — see
[13 GPU System Behavior](13-gpu-system-behavior.md) and
[15 Batching and Scheduling](15-batching-and-scheduling.md).

## Failure modes
- Low drafter-target agreement ⇒ few accepted tokens ⇒ pure overhead.
- High concurrency ⇒ verification crowds out useful batch capacity.
- Stochastic sampling (high temperature) lowers greedy-style acceptance unless the
  acceptance rule is distribution-preserving.
- Long draft blocks ⇒ verify FLOPs and transient KV grow; the tail is usually rejected
  (suffix decay).

## How to measure it
Accepted length per verify pass (τ), token acceptance rate α, tokens/s/user,
TTFT/TPOT/ITL percentiles, GPU SM and HBM utilization. Definitions and a full
benchmark protocol: [18 Performance Benchmarking](18-performance-benchmarking.md).

## Key Takeaways
1. Decode is sequential by construction (chain rule) and bandwidth-bound in practice;
   batching fixes throughput, not per-user latency.
2. Speculative decoding replaces "1 token per target pass" with "A tokens per target
   pass", A = average accepted prefix length (bonus token included).
3. Verification of K tokens rides the same weight stream as verification of 1 token —
   that asymmetry is the free lunch being harvested.
4. The technique's ceiling is set by acceptance rate, its floor by draft cost, and its
   interaction with concurrency by batch-capacity economics.
5. It is lossless when verification is distribution-preserving — which the standard
   algorithm proves; quality loss only appears with approximate/unverified variants.

## Related
[02 Draft and Verify](02-draft-and-verify.md) ·
[03 Acceptance and Verification](03-acceptance-and-verification.md) ·
`../Inference/The-Life-of-a-Token.md` · `../Inference/Roofline.md` ·
`../Inference/Inference-Metrics.md` · `../KV-Cache/README.md`

## References
- Leviathan, Kalman, Matias, *Fast Inference from Transformers via Speculative
  Decoding*, arXiv:2211.17192 [F]
- Chen et al., *Accelerating Large Language Model Decoding with Speculative
  Sampling*, arXiv:2302.01318 [F]
- Stern et al., *Blockwise Parallel Decoding for Deep Autoregressive Models*,
  arXiv:1811.08475 [F]
- Xia et al., *Unlocking Efficiency in Large Language Model Inference: A Comprehensive
  Survey of Speculative Decoding*, arXiv:2401.07851 [F]
