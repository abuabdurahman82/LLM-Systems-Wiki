# 18 — Tenant Fairness

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

**FIFO (first-in-first-out) is not fair.** A tenant that sends one low-latency
request behind another tenant that flooded the queue with a hundred batch jobs
would wait behind all of them. Fairness means each tenant gets a *share* of the
resource proportional to their entitlement over time — enforced with **quotas**,
**priority**, and **weighted fair queueing (WFQ)** — while still letting premium
tenants pay for an edge ([16](16-llm-service-tiers.md)). Fairness is measured
**across tenants over time**, not per request.

## The fairness primitives

| Primitive | What it does |
|---|---|
| **Tenant quota** | ceiling on what a tenant may consume ([20-quota-engineering](20-quota-engineering.md)) |
| **Request quota** | max requests per period (gameable by shape — see below) |
| **Token quota** | max tokens per period (shape-aware; better than request quota) |
| **Concurrency quota** | max in-flight requests (protects latency / memory) |
| **GPU-hour quota** | capacity-based entitlement |
| **Weighted fairness** | shares service proportional to a weight (WFQ) |

## Why FIFO fails

FIFO is *latency-fair* (everyone waits their turn) but *workload-unfair*: a big
tenant dominates service because it simply has more requests in the queue. The
result is the **noisy-neighbor ruin** of [19-noisy-neighbor](19-noisy-neighbor.md).
A small interactive tenant behind a big batch tenant sees its SLO destroyed even
though it "played fair."

## Weighted Fair Queueing (conceptual)

WFQ serves queues in proportion to weights, not arrival order. If tenant A has
weight 3 and tenant B weight 1, A is entitled to ~3× the service share. A
simple conceptual model is **share-based service over a window**:

```
service_share(tenant) ≈ weight(tenant) / Σ weights
```

Over any observation window, each tenant's delivered goodput converges to its
share. Premium tiers get higher weights ([16-llm-service-tiers](16-llm-service-tiers.md)).
Implementation lives in the *scheduling/routing* layer
([Inference/Production-Serving/13-multi-tenancy-fairness-priority](../Inference/Production-Serving/13-multi-tenancy-fairness-priority.md)),
and in admission + queue positioning ([21-admission-control-governance](21-admission-control-governance.md)).

## Workload classes and fairness policy

| Workload | Fairness need |
|---|---|
| **Small tenants** | protected from being starved by big ones; need *minimum share* |
| **Large tenants** | allowed to scale with their share, not *unlimited* |
| **Interactive** | latency SLO mandates admission + priority over batch |
| **Batch** | tolerate queueing; priority low, fill gaps |
| **Premium** | higher weight / reserved share ([16](16-llm-service-tiers.md)) |

## Anti-patterns

- **Request-only quotas** are gameable: a tenant can flood with *token-heavy*
  requests behind a low request-count. Enforce **token** and **concurrency**
  dimensions too ([20-quota-engineering](20-quota-engineering.md)).
- **Perfect fairness can still ruin latency** — a fair share of a saturated
  queue still queues; fairness must be paired with admission control
  ([21](21-admission-control-governance.md)).
- **Overbooking the premium edge** — selling more premium than headroom
  recreates noisy neighbors at the top tier.

## Measuring fairness

- Per-tenant goodput and **SLO attainment**: fairness ≈ *flat SLO attainment
  across tenants at equal weight* over a window
  ([42-multi-tenant-observability](42-multi-tenant-observability.md)).
- **Queue-delay attribution** — how much of tenant A's wait is caused by tenant B.

## Related

[19-noisy-neighbor](19-noisy-neighbor.md) · [20-quota-engineering](20-quota-engineering.md) ·
[21-admission-control-governance](21-admission-control-governance.md) ·
[16-llm-service-tiers](16-llm-service-tiers.md) ·
[Inference/Production-Serving/13-multi-tenancy-fairness-priority](../Inference/Production-Serving/13-multi-tenancy-fairness-priority.md)

## Key takeaways

1. FIFO is latency-fair but workload-unfair; big tenants starve small ones.
2. Fairness = proportional shares (WFQ) enforced at admission, queue, and cache.
3. Enforce token + concurrency quotas, not just request counts.
4. Fairness + admission control together, or latency still dies; measure SLO
   attainment per tenant.
