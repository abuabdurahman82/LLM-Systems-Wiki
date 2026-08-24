# 44 — Energy & Sustainability Economics

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

GPU compute is **power-hungry**, and energy is a real line item and a
sustainability obligation. The physical stack is **GPU power → rack power →
cooling → building (PUE)**. The meaningful metrics are **performance/watt**,
**cost/token**, and **energy/token** — and they don't always move together.
This page models the energy cost but is careful **not to make unsupported
sustainability claims** (avoid unverified carbon/greenhouse numbers).

## The power/cooling stack

- **GPU power** — TDP × utilization (a GPU draws a fraction of TDP depending on
  load).
- **Rack power** — GPUs + CPUs + networking + PSU losses.
- **Cooling** — heat removal (air or liquid).
- **PUE** (Power Usage Effectiveness) — total facility power ÷ IT power. PUE=1.35
  means 35% extra for cooling/power delivery.

$$\text{Facility power} = \text{IT power} \times \text{PUE}$$

## Energy economics

$$\text{energy per token} = \frac{\text{GPU power (W)} \times \text{time for the token}}{\text{tokens}}$$

Efficient inference (batching, caching, quantization) reduces **seconds per
token across the fleet**, which reduces *both* cost/token and energy/token
([09-batching-and-economics](09-batching-and-economics.md),
[08-kv-cache-economics](08-kv-cache-economics.md)).

### Worked sketch (computed, illustrative)
An H100 at ~700 W GPU TDP, 8× = 5.6 kW IT per node, × PUE 1.35 and ~$0.08/kWh:
power works out to **≈ $0.07 / GPU-hr at full power draw — roughly 5% of the
~$1.49/GPU-hr fully-loaded nominal** computed in
[scripts/economic_foundation.py](scripts/economic_foundation.py). So energy is a
real but *minority* share of the fully-loaded bill; capex + staff dominate.
(**Illustrative** — depends on load, PUE, electricity rate.)

## Trade-offs (often in tension)

| Metric | Want to… | Tension |
|---|---|---|
| **Performance/watt** | compute per energy | better hardware does this structurally |
| **Cost/token** | lowest $ | sometimes lowest-cost ≠ lowest-energy (spot/old silicon) |
| **Energy/token** | lowest energy | caching/batching lower both, but not always |

>[I] Generally, the levers that cut cost per token (better utilization, caching,
> batching, right-sized models) also cut energy per token — the alignment is
> usually good, but **verify per case** rather than assume; don't report
> energy/carbon benefits without measurement.

## Sustainability discipline [I]

- Report **energy** you can **measure**; treat **carbon intensity** as
  `UNVERIFIED` unless tied to a documented, dated source + grid intensity.
- Don't invent "greener than X" claims; state PUE, kWh, and assumptions.
- **Data residency** (which grid a region uses) can dominate the carbon story —
  relevant to [24-data-governance](24-data-governance.md) region choice.

## Related

[04-capex-vs-opex-ai-platform](04-capex-vs-opex-ai-platform.md) ·
[05-gpu-utilization-economics](05-gpu-utilization-economics.md) ·
[09-batching-and-economics](09-batching-and-economics.md) ·
[Hardware/](../Hardware/README.md) · [03-llm-inference-unit-economics](03-llm-inference-unit-economics.md)

## Key takeaways

1. Energy cost runs GPU → rack → cooling → PUE; facility power = IT × PUE.
2. Track performance/watt, cost/token, and energy/token — they don't always align.
3. Batching, caching, and right-sizing usually cut both cost and energy per token.
4. Report only measured energy; treat carbon claims as UNVERIFIED unless sourced.
