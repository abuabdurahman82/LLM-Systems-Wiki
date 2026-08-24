# 03 — Goodput vs Throughput

`LAST_UPDATED: 2026-08-23` · Status: foundational page

## 30-Second Explanation

**Throughput** counts *all completed work*; **goodput** counts only the work
that *satisfies the SLO* (and, for LLMs, the quality/correctness/cost bar).
A system with high throughput but low goodput is wasting GPU capacity on
failures. Goodput should be a **first-class production metric** for LLM
platforms.

## The definitions

```
Throughput = total completed work  / time
Goodput    = useful work satisfying required SLO / time
```

For LLMs, "useful work satisfying required SLO" means a request that completes
**and** meets latency **and** quality **and** correctness **and** policy/cost
bounds. (The multi-factor version below is a *conceptual model*.)

## The worked example

| | Server A | Server B |
|---|---|---|
| Throughput | 100 req/s | 80 req/s |
| Fraction missing latency SLO | 40% | 2% |
| Goodput (latency only) | 100 × 0.60 = **60 req/s** | 80 × 0.98 = **78.4 req/s** |

Server B *accepts fewer requests* but *delivers more* acceptable ones. Under a
rigorous latency SLO, **B is the better production system** — even though its
raw throughput is lower. `[I]` derived from the definition.

Why is this the right lens? A request that misses its latency SLO still consumed
GPU prefill+decode work, KV memory, and power — *wasted* capacity from the
user's perspective. Throughput counting it as a success overstates capacity.

## Extending goodput beyond latency

Goodput generalizes to *any* constraint that makes output "useful." For LLMs the
useful set is defined by intersecting multiple conditions. We define a
conceptual, deliberately general expression:

```
Useful Goodput =
    Requests satisfying
        latency
        AND quality
        AND correctness
        AND policy constraints
    per unit time
```

> **This is a conceptual model ([I]), not a single implementable formula.**
> There is no one universal way to quantify "quality" or "correctness," and the
> weights/order depend on your product. Use it as a frame for *which* conditions
> your goodput should intersect in your specific case, and define each condition
> as a measurable SLI.

Components to consider:

| Constraint | What it filters out | SLI it maps to |
|---|---|---|
| **Latency** | Requests that are too slow | TTFT, TPOT, E2E percentiles |
| **Quality** | Outputs below a quality bar | Judge score, human feedback, benchmark pass rate |
| **Correctness** | Wrong model / hallucination / incorrect reasoning | Eval-set groundedness/correctness, tool success |
| **Cost** | Outputs that blew the budget | $/successful request, token spend ([33](33-cost-as-an-sre-signal.md)) |

**Practical note:** in production, teams usually *start* with the latency-only
intersection (easy to measure continuously) and add quality/correctness terms as
batched eval signals, because quality per-request is expensive to score online.

## Goodput in operations

- **Capacity planning** should be driven by goodput so you don't buy GPUs to
  serve failures ([07](07-llm-capacity-planning.md)).
- **Autoscaling** should scale on goodput-aware signals, not raw utilization
  ([17](17-llm-autoscaling-reliability.md)).
- **Dashboards** should show goodput as a headline number, not buried
  ([21](21-production-dashboard.md)).
- **Alerting** should fire on goodput dips (symptom of the *product outcome*),
  not just on GPU gauges ([22](22-alerting-strategy.md)).

## Related

`02-sli-slo-sla-for-llms.md` · `07-llm-capacity-planning.md` ·
`17-llm-autoscaling-reliability.md` · `21-production-dashboard.md` ·
`Inference/Production-Serving/12-observability-and-slos.md`

## Key takeaways

1. Goodput = work that satisfies the SLO; throughput = all completed work.
2. High throughput with high SLO-miss rate can be strictly worse than lower
   throughput with high goodput.
3. For LLMs, goodput should intersect latency + quality + correctness + cost —
   a conceptual model, not a universal formula.
4. Drive capacity, autoscaling, dashboards and alerting with goodput.
