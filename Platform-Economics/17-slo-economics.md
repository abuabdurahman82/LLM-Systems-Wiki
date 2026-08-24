# 17 — SLO Economics

`LAST_UPDATED: 2026-08-24` · Status: core page · Queueing figures from
[scripts/economic_foundation.py](scripts/economic_foundation.py).

## 30-Second Explanation

**Reliability has a price.** A strict SLO (tight latency target, high
availability) forces you to hold back **reserved headroom** so that a demand
spike or a noisy neighbor can't violate the promise — and headroom is *idle
capacity you pay for*. The tighter the SLO, the lower the safe utilization, and
the higher the effective cost per token ([05-gpu-utilization-economics](05-gpu-utilization-economics.md)).
This page develops the **Cost of Reliability** and prices the redundancy
(N+1 / N+2 / multi-zone / multi-region) that availability SLOs demand.

## SLO dimensions for LLMs

- **TTFT SLO** — time to first token (prefill + queue).
- **TPOT SLO** — time per output token (decode).
- **E2E latency** — whole request.
- **Availability** — fraction of requests failing due to platform.
- **Success rate** — fraction completing without error.
- **Throughput** — work done / time.
- **Goodput** — work meeting the SLO / time ([43-goodput-economics](43-goodput-economics.md)).
See [Production-Operations/02-sli-slo-sla-for-llms](../Production-Operations/02-sli-slo-sla-for-llms.md).

## Strict SLO → headroom → lower utilization → higher cost

Queueing theory (from [05](05-gpu-utilization-economics.md)) gives the causal chain:

```
Stricter latency SLO
  → fewer requests may queue
  → lower safe utilization ρ (target e.g. 0.5–0.7 instead of 0.95)
  → more idle headroom
  → higher effective $/GPU-hr  (effective = nominal / utilization)
```

### Worked example (computed)

| ρ (safe util) | Effective $/GPU-hr | Relative to 70% |
|---|---|---|
| 0.50 | $2.98 | 1.40× |
| 0.70 | $2.13 | 1.00× |
| 0.90 | $1.66 | 0.78× |

With all else equal, the confidence to run at 70% vs 50% utilization cuts the
per-GPU-hour cost by **~29%** (a **1.40×** unit cost at 50% vs 70%). That's the
"cost of reliability" in its purest (utilization) form, and why strict SLOs are
expensive. Interactive chats with 500 ms TTFT targets must stay at lower ρ than
batch pipelines that tolerate hours of queueing
([09-batching-and-economics](09-batching-and-economics.md)).

## Cost of Reliability (framework)

$$\text{Cost of Reliability} = \underbrace{\text{Headroom cost}}_{\text{capacity held for SLO}} + \underbrace{\text{Redundancy cost}}_{\text{spare capacity/regions}} + \underbrace{\text{Operational cost}}_{\text{SLO engineering, monitoring, on-call}}$$

## Redundancy and its economics

| Redundancy | What it buys | Economic cost |
|---|---|---|
| **N+1** | tolerate 1 failure | +1 replica per N (≈ +1/N capacity) |
| **N+2** | tolerate 2 failures | +2/N |
| **Multi-zone** (AZ-redundant) | survive one zone failure | ~2–3× capacity or standing standby |
| **Multi-region** | survive region loss | ~2× capacity + geo complexity + egress |

Redundancy is a *multiplicative* availability tax: multi-region active-active
roughly doubles your hardware bill ([Production-Operations/36-multi-region-llm-reliability](../Production-Operations/36-multi-region-llm-reliability.md),
[37-disaster-recovery](../Production-Operations/37-disaster-recovery.md)). For many
internal LLM uses, **N+1 at one site** is the cost-effective default; multi-region
only pays for genuinely business-critical, region-spanning needs.

## SLO tiers price the reliability

This is why [16-llm-service-tiers](16-llm-service-tiers.md) exists: tenants who
demand strict SLOs pay for the headroom; tenants with weak SLOs ride the cheap
high-utilization capacity. Otherwise the reliability tax is silently socialized
across everyone ([15-llm-platform-pricing-models](15-llm-platform-pricing-models.md)).

## Related

[05-gpu-utilization-economics](05-gpu-utilization-economics.md) ·
[16-llm-service-tiers](16-llm-service-tiers.md) · [43-goodput-economics](43-goodput-economics.md) ·
[Production-Operations/02-sli-slo-sla-for-llms](../Production-Operations/02-sli-slo-sla-for-llms.md) ·
[32-demand-forecasting](32-demand-forecasting.md)

## Key takeaways

1. Strict SLO → lower safe utilization → higher effective cost per token.
2. Cost of Reliability = headroom + redundancy + operations.
3. N+1 is cheap; multi-region is roughly a 2× hardware tax — match to real need.
4. Price reliability via tiers so headroom isn't socialized across tenants.
