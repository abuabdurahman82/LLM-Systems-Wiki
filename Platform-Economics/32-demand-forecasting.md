# 32 — Demand Forecasting

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

Capacity planning ([31](31-capacity-planning.md)) is only as good as its demand
forecast. LLM demand is **bursty and seasonal** — it spikes by time of day,
weekly rhythm, product launches, model releases, batch jobs, and agent storms.
The critical discipline is to forecast in **percentiles (P50/P90/P95/P99)**, not
just the mean, because **provisioning only for average demand is how you run out
of capacity (or capacity runs you over the cliff) at exactly the wrong moment.**

## Demand drivers to model

- **Historical demand** — baseline from metering ([13-tenant-metering](13-tenant-metering.md)).
- **Business growth** — tenant onboarding, app rollout.
- **Time-of-day** — intraday peaks (the classic morning spike).
- **Weekly seasonality** — weekday vs weekend.
- **Product launches** — traffic jumps coinciding with releases.
- **Model releases** — better models attract *more* usage (and reasoning models
  multiply tokens, [35-agent-economics](35-agent-economics.md)).
- **Batch jobs** — scheduled bulk work adds predictable-but-large load.

## Percentiles, not mean

The mean hides the peak. A platform whose capacity equals average demand
saturates (queue explosion, [05-gpu-utilization-economics](05-gpu-utilization-economics.md))
every time demand passes its own average — which, for a bursty workload, is
*frequently*. Capacity should be provisioned to a **service-level percentile**
(P90–P99) that matches the SLO ([17](17-slo-economics.md)):

| Provision to | Covers | Risk if used as blind target |
|---|---|---|
| P50 (median) | typical day | saturates on any burst → latency/SLO break |
| P90 | most spikes | occasional breach in heavy weeks |
| P95 / P99 | near-worst | expensive headroom holds idle most of the time |
| P99 + redundancy | almost all | highest cost; justify by SLO |

>[I] Match the provisioning percentile to the *SLO severity*: interactive
> premium tenants → P99 + redundancy; batch best-effort → P50–P90
> ([16-llm-service-tiers](16-llm-service-tiers.md)). Do not provision everything
> at P99 — that's how you pay for idle hardware
> ([34-ai-cost-waste](34-ai-cost-waste.md), [05](05-gpu-utilization-economics.md)).

## Why average provisioning is dangerous

Concretely: if average demand is 100 and the SLO allows a short queue, capacity
at 100 works *only* if arrivals are steady. Real arrivals bunch — so at various
times demand hits 150, 200, 400. At capacity=mean, every such minute is a
saturation event: P99 latency explodes ([05](05-gpu-utilization-economics.md)) and
premium tenants breach SLO. Forecasting in percentiles plus holding
SLO-appropriate headroom is what keeps *goodput* high at acceptable cost
([43-goodput-economics](43-goodput-economics.md)).

## Closing the loop

Forecast → provision → measure actual vs forecast → **re-calibrate the forecast
weekly/monthly** against metered reality ([33-ai-finops](33-ai-finops.md),
[42-multi-tenant-observability](42-multi-tenant-observability.md)). A stale
forecast is as dangerous as no forecast.

## Related

[31-capacity-planning](31-capacity-planning.md) ·
[05-gpu-utilization-economics](05-gpu-utilization-economics.md) ·
[17-slo-economics](17-slo-economics.md) · [33-ai-finops](33-ai-finops.md) ·
[35-agent-economics](35-agent-economics.md)

## Key takeaways

1. Model time-of-day, weekly, launch, release, batch, and growth drivers.
2. Forecast in P50/P90/P95/P99 — not just the mean.
3. Provision to the percentile the SLO demands, not the average.
4. Re-calibrate forecasts against metered reality.
