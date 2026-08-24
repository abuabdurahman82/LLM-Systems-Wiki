# 16 — LLM Service Tiers

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

Not every tenant needs the same latency, availability, isolation, or price.
**Service tiers** formalize a small set of service grades (and their price
points) so tenants self-select their cost/latency/quality point on the frontier
([12-quality-cost-latency-frontier](12-quality-cost-latency-frontier.md)) instead of
forcing one grade for everyone. The tiers below are **illustrative**, not an
industry standard — name and tune them to your platform.

## Example tiers

### BRONZE — best effort
- **Latency:** no guarantee (best effort)
- **Availability:** best effort
- **Priority:** lowest
- **Capacity:** shared pool, preemptible
- **Isolation:** soft (shared GPU)
- **Cost:** lowest price
- **Support:** self-service
- **Model access:** small/approved models only

### SILVER — standard business
- **Latency:** reasonable (e.g. TTFT < 2 s)
- **Availability:** moderate (e.g. 99.5%)
- **Priority:** normal
- **Capacity:** shared with quota
- **Isolation:** soft with per-tenant quota
- **Cost:** standard
- **Support:** standard ticketing
- **Model access:** standard approved models

### GOLD — priority
- **Latency:** strict (e.g. TTFT < 500 ms)
- **Availability:** high (e.g. 99.9%)
- **Priority:** high
- **Capacity:** reserved capacity
- **Isolation:** soft-but-protected (policed vs noisy neighbors)
- **Cost:** premium
- **Support:** priority
- **Model access:** premium+standard models

### PLATINUM — dedicated
- **Latency:** strictest
- **Availability:** highest (e.g. 99.95%)
- **Priority:** highest
- **Capacity:** dedicated capacity
- **Isolation:** hard (dedicated GPU/node as required)
- **Cost:** highest
- **Support:** 24×7 premium
- **Model access:** any approved model incl. high-end reasoning

> ⚠️ Concrete SLO values here are **illustrative placeholders** — set real
> numbers from your own SLO budget ([17-slo-economics](17-slo-economics.md)).

## What each tier encodes

| Dimension | BRONZE | SILVER | GOLD | PLATINUM |
|---|---|---|---|---|
| Latency SLO | none | standard | strict | strictest |
| Availability target | best-effort | moderate | high | highest |
| Priority | lowest | normal | high | highest |
| Capacity | shared | shared+quota | reserved | dedicated |
| Isolation | soft | soft | protected | hard |
| Cost | low | standard | premium | highest |
| Support | self-svc | ticketing | priority | 24×7 |
| Model access | small only | standard | premium+ | any approved |

## Tiers → mechanics

Each tier maps onto real platform knobs:
- **Priority** → admission thresholds + queue weighting
  ([18-tenant-fairness](18-tenant-fairness.md), [21-admission-control-governance](21-admission-control-governance.md)).
- **Reserved/dedicated capacity** → pool assignment
  ([30-capacity-reservation](30-capacity-reservation.md), [02-multi-tenancy-models](02-multi-tenancy-models.md)).
- **Model access** → entitlement policy
  ([26-model-access-control](26-model-access-control.md)).
- **Price** → surcharge in the pricing model
  ([15-llm-platform-pricing-models](15-llm-platform-pricing-models.md)).

## Economics of tiers

Tiers let the platform **segment demand** so high-SLO (gold/platinum) tenants
pay for the spare capacity their guarantees require
([17-slo-economics](17-slo-economics.md)) instead of the cost being socialized
across everyone. Done well, tiering *increases* both utilization (bronze fills
the gaps) and revenue-per-unit (premium pays for headroom).

## Related

[12-quality-cost-latency-frontier](12-quality-cost-latency-frontier.md) ·
[17-slo-economics](17-slo-economics.md) · [15-llm-platform-pricing-models](15-llm-platform-pricing-models.md) ·
[18-tenant-fairness](18-tenant-fairness.md) · [30-capacity-reservation](30-capacity-reservation.md)

## Key takeaways

1. Service tiers segment demand so tenants choose their cost/latency/quality point.
2. Tiers are illustrative, not standard — design for your own SLOs and prices.
3. Map each tier to real knobs: priority, capacity, isolation, model access, price.
4. Tiers let high-SLO tenants pay for their headroom instead of socializing it.
