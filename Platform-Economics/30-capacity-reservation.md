# 30 — Reserved vs On-Demand Capacity

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

Capacity can be **reserved** (held for a tenant/tier regardless of use) or
**on-demand/shared** (pooled, assigned as work arrives), with **burst** as an
elastic overflow ([28-cloud-bursting-economics](28-cloud-bursting-economics.md)).
**Reservation improves predictability, SLO, and availability — but it lowers
utilization**, because reserved-but-idle capacity is a fixed cost with no work
on it ([04](04-capex-vs-opex-ai-platform.md), [17-slo-economics](17-slo-economics.md)).
The premium you pay for reservation is called the **Reservation Premium**, and
it is the price of not being preempted by other tenants.

## Capacity modes compared

| Mode | Definition | Predictability | Utilization | Cost profile |
|---|---|---|---|---|
| **Reserved GPU** | capacity held for a tenant/tier | highest | lowest (idle risk) | fixed, premium |
| **Shared GPU** | pooled capacity, assigned as used | medium | highest (pooling) | variable-ish, cheapest $/token |
| **Burst GPU** | elastic overflow to shared/cloud | medium | high | extra on overflow |
| **Cloud API** | metered external capacity | provider-controlled | n/a (metered) | variable per token |

## What reservation buys

- **Predictability** — capacity is there when you need it (no "we're out").
- **SLO** — no co-tenant noise on reserved capacity ([17](17-slo-economics.md), [19](19-noisy-neighbor.md)).
- **Availability** — guaranteed headroom under demand spikes.

## What it costs

Reserved capacity is **fixed cost at whatever utilization it actually runs**.
Reserving 10 GPUs for a tenant that uses 4 GPU-hours of work means paying for 10
units of headroom — the **Reservation Premium** is the difference between the
utilization-adjusted reserved price and the shared/on-demand price.

$$\text{Reservation Premium} = \text{cost of reserved-but-idle capacity}$$

The more reserved (vs shared) capacity a platform holds, the lower its average
pool utilization and the higher its effective $/token
([05-gpu-utilization-economics](05-gpu-utilization-economics.md)).

## Design guidance [I]

- **Reserve where SLO demands it** (GOLD/PLATINUM tiers, [16-llm-service-tiers](16-llm-service-tiers.md));
  keep the rest on shared for pooling.
- **Right-size reservation to the tenant's *predictable baseline***, and route
  volatility to burst/shared — don't reserve the peak.
- **Meter reservation separately from consumption** in showback so a tenant
  *sees* the cost of capacity they hold idle ([14-showback-chargeback](14-showback-chargeback.md)).
- **Cloud-side**, reserved instances/commitments are the provider equivalent —
  buy them only for steady, measurable base demand
  ([04](04-capex-vs-opex-ai-platform.md), [33-ai-finops](33-ai-finops.md)).

## Related

[16-llm-service-tiers](16-llm-service-tiers.md) ·
[17-slo-economics](17-slo-economics.md) ·
[28-cloud-bursting-economics](28-cloud-bursting-economics.md) ·
[05-gpu-utilization-economics](05-gpu-utilization-economics.md) ·
[33-ai-finops](33-ai-finops.md)

## Key takeaways

1. Reserved vs shared vs burst vs cloud is a predictability/utilization trade.
2. Reservation buys SLO, predictability, availability — at an idle cost.
3. Reservation Premium ≈ cost of reserved-but-idle capacity.
4. Reserve the baseline, route the volatility; meter reservation separately.
