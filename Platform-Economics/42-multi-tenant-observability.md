# 42 — Multi-Tenant Observability

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

A multi-tenant platform must be **observable across tenants, not just across
machines**. The same raw metrics are sliced by **tenant, model, GPU, endpoint,
region, and service tier** — and different audiences need different dashboards:
the **tenant** cares about their own cost/SLO; the **platform** team owns the
pool; **FinOps** owns allocation; **executives** own the business summary. This
is the feedback layer that turns metering ([13-tenant-metering](13-tenant-metering.md))
into decisions ([33-ai-finops](33-ai-finops.md), [34-ai-cost-waste](34-ai-cost-waste.md)).

## Dashboard dimensions

Slice every metric by:

- **tenant** (the accounting boundary, [01](01-multi-tenant-llm-platform-overview.md))
- **model** (which model is doing the work, [10](10-model-economics.md))
- **GPU / pool** (hardware view, [46-gpuaas-pricing](46-gpuaas-pricing.md))
- **endpoint** (the serving boundary)
- **region** (residency / geo)
- **service tier** (bronze/silver/gold/platinum, [16-llm-service-tiers](16-llm-service-tiers.md))

## Metrics

- **Requests** (rate, per tenant/model)
- **Tokens** (in / out / cached / reasoning — [06](06-token-economics.md))
- **GPU utilization** (per pool, [05](05-gpu-utilization-economics.md))
- **Cost** (per tenant/model/pool — the FinOps view)
- **TTFT / TPOT** (latency, [17](17-slo-economics.md))
- **P95 / P99** (tail)
- **Errors** (failure rate)
- **Cache hit rate** ([08](08-kv-cache-economics.md))
- **Queue time** (congestion)
- **SLO compliance** (goodput share, [43](43-goodput-economics.md))

## The four dashboards

### Tenant Dashboard
Shows a tenant their own consumption, cost, SLO attainment, and budget remaining —
the self-service view that drives showback/chargeback ([14](14-showback-chargeback.md))
and lets tenants self-correct before their budget breaks.

### Platform Dashboard
Cross-tenant pool health: GPU utilization, queue depth, SLO attainment per tier,
noisy-neighbor signals ([19-noisy-neighbor](19-noisy-neighbor.md)), replica health,
capacity margins ([31-capacity-planning](31-capacity-planning.md)).

### FinOps Dashboard
Allocation and cost: $/tenant, $/model, $/GPU-hr, spend vs budget, waste signals
([34-ai-cost-waste](34-ai-cost-waste.md)), reservations utilization
([30-capacity-reservation](30-capacity-reservation.md)), cloud API spend.

### Executive Dashboard
One-screen business summary: total spend, value delivered (good requests),
tier mix, budget variance, top tenants/models, trend — for the Business Owner in
[40](40-llm-platform-governance-model.md).

## Operations hygiene [I]

- **Decouple billing-grade metering from sampling** — never sample what you
  charge ([13](13-tenant-metering.md)).
- **Label discipline** — consistent dimension names or allocations break.
- **High cardinality** → event store + rollups, not a flat, sparsely-tagged bucket.
- Tie to alerting per the observability practice in
[Production-Operations/20-llm-observability-stack](../Production-Operations/20-llm-observability-stack.md).

## Related

[13-tenant-metering](13-tenant-metering.md) ·
[33-ai-finops](33-ai-finops.md) · [43-goodput-economics](43-goodput-economics.md) ·
[19-noisy-neighbor](19-noisy-neighbor.md) ·
[Production-Operations/21-production-dashboard](../Production-Operations/21-production-dashboard.md)

## Key takeaways

1. Slice all metrics by tenant, model, GPU, endpoint, region, tier.
2. Track requests, tokens, GPU util, cost, TTFT/TPOT, P95/99, errors, cache, queue, SLO.
3. Build four views: tenant, platform, FinOps, executive.
4. Keep label discipline; never sample billing-grade metering.
