# 26 — Shadow Testing

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

**Shadow testing** runs a *candidate* model on a *copy* of real production
traffic while the *current* model keeps serving the user. It is the safest way to
measure a candidate under real-world load — **its output never reaches the user** —
so latency/quality/cost/error comparisons are obtained with zero risk to users.

## Architecture

```
Production request
      ↓
Current model ──────────► user  (unchanged)
      │
      └── copy of request
           ↓
      candidate model
           ↓
      offline evaluation
```

The user path is untouched. The candidate sees the same prompts (copied) and its
outputs go to evaluation, not to the caller. `[I]` architecture.

## What shadow compares

| Dimension | Question |
|---|---|
| **Latency** | TTFT/TPOT/E2E of candidate vs current under real load |
| **Quality** | correctness/groundedness/format on real prompts (judge/eval) |
| **Cost** | tokens + $/request, GPU cost of candidate path |
| **Error rate** | timeouts, parse failures, refusals, tool failures |
| **Goodput** | how many requests would have met all SLOs ([03](03-goodput-vs-throughput.md)) |

## Operational practice (`[I]`)

1. **Isolate the candidate** — separate pool/compute so it doesn't steal capacity
   from production (else shadow becomes a DoS of itself, like deep probes,
   [19](19-llm-health-checks.md)).
2. **Sample representatively** — copy the real distribution (including long
   prompts/tails), not just easy traffic.
3. **Tag provenance** — candidate outputs carry `shadow:true`, `candidate_model_id`
   so they're never confused for production ([23](23-llm-tracing.md)).
4. **Score offline** — judge/classifiers + golden set, not just latency
   ([24](24-quality-observability.md), [28](28-llm-regression-testing.md)).
5. **Cost the shadow** — shadow burns real GPU/compute; budget it
   ([33](33-cost-as-an-sre-signal.md)).

## Related

`24-quality-observability.md` · `25-model-release-engineering.md` ·
`27-canary-deployment.md` · `28-llm-regression-testing.md`

## Key takeaways

1. Shadow runs the candidate on *copies* of traffic; output never reaches the user.
2. Compare latency, quality, cost, error rate, goodput.
3. Isolate candidate compute so shadow doesn't hurt production.
4. Tag shadow outputs and cost the shadow run.
