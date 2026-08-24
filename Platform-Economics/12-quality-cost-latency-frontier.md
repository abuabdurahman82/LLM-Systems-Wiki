# 12 — The Quality / Cost / Latency Frontier

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

Serving is governed by a **three-way (really six-way) trade-off**:
**quality, latency, cost** — and, in production, **reliability, privacy, and
energy**. There is rarely one "best" model; there are **best models for a given
constraint**. A Pareto frontier separates the choices you'd ever pick (can't
improve one axis without hurting another) from the dominated ones (worse on
every axis — never choose). The platform's job is to *choose the right point on
the frontier per tenant, per request*, which is the heart of
[11-economic-model-routing](11-economic-model-routing.md) and
[16-llm-service-tiers](16-llm-service-tiers.md).

## The trade-off space

- **Quality** — correctness / benchmark / task success. Better models cost
  more and are slower ([10-model-economics](10-model-economics.md)).
- **Latency** — TTFT + TPOT + E2E; better/rarer models and higher utilization
  push latency up ([05-gpu-utilization-economics](05-gpu-utilization-economics.md)).
- **Cost** — $/request, $/successful task
  ([03-llm-inference-unit-economics](03-llm-inference-unit-economics.md)).

Add the production axes:

- **Reliability** — availability/SLO headroom (spare capacity costs money) ([17](17-slo-economics.md)).
- **Privacy** — local vs cloud changes permissible options ([24](24-data-governance.md)).
- **Energy** — performance/watt vs cost/token vs energy/token ([44](44-energy-and-sustainability.md)).

## Pareto frontier examples (conceptual)

```
quality
  ↑                  ·  best for "need the best answer"
  │              ·
  │          ·      <-- Pareto frontier (non-dominated)
  │      ·
  │  ·
  └──────────────────────────→ cost
     dominated region (worse cost AND worse quality — never pick)
```

Every dot *on* the frontier is "best" for *some* constraint: the cheap model for
a budget-constrained batch job, the premium reasoning model for a high-stakes
answer, the mid model for the everyday interactive load. A router's scoring
function picks the frontier point whose weighted utility is highest for the
request at hand ([22-budget-aware-routing](22-budget-aware-routing.md)).

## "Best model" is relative

- **Best for cost** (budget-bound): smallest that meets quality bar.
- **Best for latency** (interactive SLO): fastest that meets quality bar.
- **Best for quality** (high-stakes, budget-insensitive): strength first.
- **Best for privacy**: local-only approved models ([24](24-data-governance.md)).

A platform that answers "which model?" with *one* answer is leaving most of the
frontier's value on the table. A platform that routes to the right point per
request captures it ([11](11-economic-model-routing.md)).

## Cautions

- **Frontiers drift**: model prices, quality, and GPU costs change; the router's
  cost/quality tables must be refreshed ([34-ai-cost-waste](34-ai-cost-waste.md)).
- **Hidden third axis**: a "cheap fast" model that needs retries moves cost up
  and latency up — evaluate *per successful task*, not per token
  ([43-goodput-economics](43-goodput-economics.md)).
- **Multi-tenant coupling**: what's on the frontier for a single request may not
  be reachable when a tenant's budget/model entitlement is exhausted
  ([26-model-access-control](26-model-access-control.md)).

## Related

[11-economic-model-routing](11-economic-model-routing.md) ·
[16-llm-service-tiers](16-llm-service-tiers.md) · [22-budget-aware-routing](22-budget-aware-routing.md) ·
[43-goodput-economics](43-goodput-economics.md) ·
[Evaluation-Engineering/](../Evaluation-Engineering/README.md)

## Key takeaways

1. Serving is a quality × latency × cost (× reliability × privacy × energy) frontier.
2. There is rarely one best model — there are best models *per constraint*.
3. Pick the frontier point with the highest weighted utility per tenant/request.
4. Re-evaluate as prices, quality, and capacity drift; judge per successful task.
