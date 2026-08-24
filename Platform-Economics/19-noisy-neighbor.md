# 19 — The Noisy Neighbor Problem

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

The **noisy neighbor** is the canonical multi-tenant failure. One tenant floods
the shared pool with heavy work and **silently destroys the latency, memory, and
SLO of every other tenant**, because they all share the same GPU, the same queue,
and the same KV cache. It is not malice — it's the natural result of unconstrained
resource sharing, and it is the *single best argument* for the whole
admission/quota/priority machinery in this section.

## The failure example

- **Tenant A:** 100 concurrent 100K-token requests (a bulk summarization batch).
- **Tenant B:** an interactive chatbot needing 500 ms TTFT.

Without controls, Tenant A:
1. **consumes the queue** — B's requests sit behind A's hundred;
2. **consumes the KV cache** — A's 100 long contexts evict/starve B's working set
   ([08-kv-cache-economics](08-kv-cache-economics.md));
3. **destroys Tenant B's latency** — B's P99 blows past its SLO
   ([05-gpu-utilization-economics](05-gpu-utilization-economics.md)).

This is exactly the "latency-optimal ≠ fair" failure described in
[Inference/Production-Serving/13-multi-tenancy-fairness-priority](../Inference/Production-Serving/13-multi-tenancy-fairness-priority.md).

## Control inventory

| Control | Layer | What it stops |
|---|---|---|
| **Queue isolation** | Router/scheduler | A's burst not lining up in front of B (WFQ, [18](18-tenant-fairness.md)) |
| **Tenant concurrency limits** | Admission | A can't hold 100 in flight ([21](21-admission-control-governance.md)) |
| **Token budgets** | Quota | A's total consumption capped ([20-quota-engineering](20-quota-engineering.md)) |
| **Priority** | Scheduler | B's interactive class jumps A's batch ([16](16-llm-service-tiers.md)) |
| **Memory quotas** | Engine/scheduler | A can't monopolize KV/memory |
| **Separate pools** | Placement | heavy/noisy tenants isolated to their own GPU pool ([02](02-multi-tenancy-models.md)) |
| **Rate limiting** | Gateway | brakes on request rate at the edge |

## Design guidance [I]

- **Detect** noisy behavior (per-tenant queue-consumption, KV-consumption, P99
  impact on neighbors) — you can't police what you don't see
  ([42-multi-tenant-observability](42-multi-tenant-observability.md)).
- **Prefer shaping to isolation** at first (concurrency + token limits are cheap);
  graduate to **separate pools** for genuinely anti-social or premium tenants
  ([02](02-multi-tenancy-models.md), [16](16-llm-service-tiers.md)).
- **Cache is a noise surface too** — tenant A's churn evicts tenant B's hot
  prefix; per-tenant cache namespaces protect it ([08](08-kv-cache-economics.md),
  [23](23-tenant-security-isolation.md)).

## Lab

The noisy-neighbor mechanism is reproduced in a safe local environment in
[Labs/lab-06-simulate-noisy-neighbor](Labs/lab-06-simulate-noisy-neighbor.md),
and the fairness controls are built in
[Labs/lab-07-weighted-fair-scheduling](Labs/lab-07-weighted-fair-scheduling.md).

## Related

[18-tenant-fairness](18-tenant-fairness.md) · [20-quota-engineering](20-quota-engineering.md) ·
[21-admission-control-governance](21-admission-control-governance.md) ·
[08-kv-cache-economics](08-kv-cache-economics.md) ·
[Inference/Production-Serving/13-multi-tenancy-fairness-priority](../Inference/Production-Serving/13-multi-tenancy-fairness-priority.md)

## Key takeaways

1. Unconstrained sharing lets one tenant's burst destroy everyone's SLO.
2. The noisy neighbor consumes queue, KV, and latency all at once.
3. Fix with queue isolation, concurrency/token limits, priority, memory quotas,
   and (last resort) separate pools.
4. Detect it with per-tenant observability before it becomes a pager storm.
