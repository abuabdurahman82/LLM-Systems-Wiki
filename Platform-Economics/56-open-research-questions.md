# 56 — Open Research Questions

`LAST_UPDATED: 2026-08-24` · Status: research page · Marked `OPEN` — honest open
problems, not settled facts.

## The central hypothesis

> **"A successful multi-tenant LLM platform should optimize cost per useful
> SLO-compliant outcome, not simply GPU utilization, requests per second, or
> tokens per second."**

**Where it holds:** when cost-of-failure and quality matter more than raw rate —
i.e. most business/agentic/RAG workloads ([43-goodput-economics](43-goodput-economics.md),
[45-cost-of-failure](45-cost-of-failure.md)).

**Attempts to falsify (where tokens/sec may still be right):** when throughput is
the product (a batch labeling farm, an eval batch, a bulk summarization job) with
no strict SLO and no quality-failure cost, **tokens/sec / GPU utilization IS the
correct economic metric** — goodput degenerates to throughput. Also, at the
*GPU/scheduler* layer, utilization and tokens/sec remain the physical control
variables even when the *business* metric is goodput
([05](05-gpu-utilization-economics.md), [09-batching-and-economics](09-batching-and-economics.md)).
**Verdict: the hypothesis holds at the business/platform layer but must
decompose into tokens/sec/GPU at the scheduling layer.** `OPEN` — unresolved
how to price the "good" boundary without per-task evals.

## Open questions (with competing arguments)

1. **Can token pricing accurately represent GPU cost?**
   - Yes: tokens ≈ the metered, user-visible consumption unit
     ([06](06-token-economics.md)). No: KV residency, long context, and decode
     cost don't map to a single token price ([07](07-prefill-decode-economics.md),
     [08](08-kv-cache-economics.md)). → Make price multi-dimensional.

2. **How should KV-cache capacity be priced?**
   - As memory (reservation) vs as saved prefill (reward). Both are defensible;
     the platform likely needs *both* ([08](08-kv-cache-economics.md)).

3. **Should tenants pay for reserved capacity or actual consumption?**
   - Reserved → predictable but idle-taxes tenants ([30](30-capacity-reservation.md));
     consumption → fair but surprises tenants. Hybrid is the pragmatic answer.

4. **How should agent workflows be metered?**
   - Per-call vs per-run; per-run aligns incentives but needs run attribution and
     cost budgeting ([35-agent-economics](35-agent-economics.md)).

5. **How should speculative tokens be charged?**
   - Drafts that get accepted = real output; rejected = overhead. Charging for
     rejected drafts is contested; most platforms absorb them
     ([06](06-token-economics.md)).

6. **Can model routers optimize quality-cost automatically?**
   - Routing is a live optimization problem ([11](11-economic-model-routing.md),
     [22](22-budget-aware-routing.md)); online learning is promising but risks
     silent quality drift without evals.

7. **How do you economically value cache affinity?**
   - Cache-aware placement changes which tenant wins caching ([08](08-kv-cache-economics.md),
     [Inference/Production-Serving/08-cache-aware-routing](../Inference/Production-Serving/08-cache-aware-routing.md));
     pricing it fairly is unsolved.

8. **How should reasoning tokens be accounted for?**
   - They're output-like cost but hidden ([35](35-agent-economics.md)); whether to
     bill them separately or fold into the answer price is an open call.

9. **How should multi-model cascades be priced?**
   - Pay-per-stage vs blended average; both distort ([11](11-economic-model-routing.md)).

10. **Can goodput become the core platform economic metric?**
    - The thesis above ([43](43-goodput-economics.md)); blocked on defining
      "good" cheaply at scale ([36-evaluator-economics](36-evaluator-economics.md)).

11. **How should heterogeneous GPU capacity be normalized?**
    - GPU-hours of an H100 ≠ an A100 ≠ a B200; no accepted normalization
      ([46-gpuaas-pricing](46-gpuaas-pricing.md), [10-model-economics](10-model-economics.md)).

## How to investigate

- **Measure, don't argue:** instrument metering, cost, and goodput
  ([13-tenant-metering](13-tenant-metering.md), [42-multi-tenant-observability](42-multi-tenant-observability.md)).
- **Use the simulator** ([49-llm-platform-economic-simulator](49-llm-platform-economic-simulator.md))
  for economic hypotheses; run experiments in [Labs/README](Labs/README.md).
- **Adjudicate with evidence** — these are `OPEN`, trade-offs will land
  differently per platform.

## Related

[43-goodput-economics](43-goodput-economics.md) ·
[57-economics-governance-big-picture](57-economics-governance-big-picture.md) ·
[08-kv-cache-economics](08-kv-cache-economics.md) · [35-agent-economics](35-agent-economics.md)

## Key takeaways

1. The goodput thesis holds at the business layer but decomposes to tokens/sec at the scheduler — OPEN.
2. Pricing KV, reservation, agents, speculation, caching, reasoning, cascades all have competing arguments.
3. Normalizing heterogeneous GPU capacity is unsolved.
4. Investigate with measurement, not assertion.
