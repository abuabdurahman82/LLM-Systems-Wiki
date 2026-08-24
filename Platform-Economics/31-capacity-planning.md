# 31 — Capacity Planning

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

**Capacity planning turns demand into hardware.** From tenant demand, arrival
rates, token shapes, concurrency, SLOs, model mix, growth, and seasonality, you
derive **how many GPUs, replicas, and how much headroom, network, power, and
storage** to provision. The dangerous failure is planning for *average* demand —
bursts and SLOs force you to hold headroom, so capacity is set by the **P90/P99
demand and the SLO**, not the mean ([32-demand-forecasting](32-demand-forecasting.md),
[17-slo-economics](17-slo-economics.md)).

## Inputs

| Input | Example | Why |
|---|---|---|
| tenant demand | requests/day per tenant | baseline load |
| arrival rate | λ requests/sec | queueing ([05](05-gpu-utilization-economics.md)) |
| tokens/request | in + out per request | throughput demand |
| prompt length | avg + tail | prefill cost ([07](07-prefill-decode-economics.md)) |
| output length | avg + tail | decode cost, latency |
| concurrency | peak in-flight | memory + batch size ([09](09-batching-and-economics.md)) |
| SLO | TTFT/TPOT/avail | sets headroom + redundancy ([17](17-slo-economics.md)) |
| model mix | small:large:reasoning | aggregate throughput per class ([10](10-model-economics.md)) |
| growth | %/mo | forward provisioning |
| seasonality | time-of-day/weekly | peak provisioning |

## Outputs

- **GPU count** per pool (model-relevant: a 70B needs TP etc., [10](10-model-economics.md)).
- **Replica count** per endpoint (to meet SLO and absorb failures, N+1).
- **Headroom** — the fraction held back for bursts and SLO
  ([17](17-slo-economics.md), [05](05-gpu-utilization-economics.md)).
- **Network** — NVLink/IB/compute network + model-serve + egress.
- **Power / cooling** — racks, PUE, circuit capacity ([44-energy-and-sustainability](44-energy-and-sustainability.md)).
- **Storage** — weights, KV offload, logs, RAG, checkpoints.

## A simple capacity-planning model

Per model class, GPUs needed ≈

$$\text{GPUs} = \frac{\text{peak throughput needed (tok/s)}}{\text{throughput per GPU at target utilization}} \times \text{replication factor}$$

where:
- peak throughput = P99 demand × avg tokens/sec ([32](32-demand-forecasting.md)),
- throughput per GPU is measured on your engine ([Serving-Engines/](../Serving-Engines/README.md)),
- target utilization is the safe ρ for your SLO ([05](05-gpu-utilization-economics.md)),
- replication = N+1 etc. ([17](17-slo-economics.md)).

### Worked sketch (illustrative/derived)

If peak demand is **50k tok/s** aggregate decode, a GPU sustains ~25k tok/s at
your target ρ=0.7 with N+1 → `50k / (25k·0.7) · (1 + 1/N_eff)` ≈ 3–4 GPUs for the
decode floor, plus separate prefill/queue factor. **This is a worked sketch, not
a universal formula** — the real numbers come from your measured throughput and
your SLO, not from a made-up constant. The point is the *method*
([49-llm-platform-economic-simulator](49-llm-platform-economic-simulator.md)).

## Capacity planning vs FinOps

Capacity planning is the *physical* side; **FinOps** ([33-ai-finops](33-ai-finops.md))
ensures you don't over-provision to hide from the planning math. Budgets,
reservations, and right-sizing ([34-ai-cost-waste](34-ai-cost-waste.md)) close
the loop: plan → provision → measure utilization → re-plan.

## Related

[32-demand-forecasting](32-demand-forecasting.md) ·
[05-gpu-utilization-economics](05-gpu-utilization-economics.md) ·
[17-slo-economics](17-slo-economics.md) · [33-ai-finops](33-ai-finops.md) ·
[49-llm-platform-economic-simulator](49-llm-platform-economic-simulator.md) ·
[Production-Operations/07-llm-capacity-planning](../Production-Operations/07-llm-capacity-planning.md)

## Key takeaways

1. Capacity = f(demand, throughput, target utilization, replication).
2. Plan for P90/P99 + SLO headroom, not the average.
3. Model mix matters — different model classes need different throughput math.
4. Close the loop: plan → provision → measure → re-plan (FinOps).
