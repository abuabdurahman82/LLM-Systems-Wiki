# 04 — CAPEX vs OPEX for an AI Platform

`LAST_UPDATED: 2026-08-24` · Status: core page · Figures ILLUSTRATIVE, **2026-08**.

## 30-Second Explanation

You can get GPU compute five ways — **on-prem, colocation, private cloud,
public cloud GPU, managed inference API** — and they are really two economic
species: **CAPEX** (buy it, pay capital, depreciate, carry it even when idle)
and **OPEX** (rent it, pay as you use). The single most dangerous number in the
whole decision is **raw $/GPU-hour**, because it ignores utilization, lifespan,
and all the non-GPU cost. The number that matters is **Effective Cost per
Productive GPU Hour**.

## The five sourcing models

| Model | Primary cost type | Example economics |
|---|---|---|
| **On-prem GPUs** | CAPEX + fixed OPEX | Buy nodes, own them 3–5 yrs, you eat idle time. Best at *high, steady* utilization. |
| **Colocation** | OPEX-ish (rent space/power) + own HW | Rack your own GPUs in someone's DC; avoid building a DC, keep hardware control. |
| **Private cloud** | CAPEX + cloud-like control plane | An internal "cloud" over owned GPUs; adds orchestration OPEX. |
| **Public cloud GPU** | OPEX (on-demand/reserved/spot) | Rent GPUs; huge elasticity, premium price, no idle tax if you scale down. |
| **Managed inference API** | Pure OPEX per token | Rent the *model*, not the GPU; zero infra, highest per-token price. |

## CAPEX vs OPEX trade-offs

| Dimension | CAPEX (own) | OPEX (rent/API) |
|---|---|---|
| Upfront cash | High | None |
| Utilization risk | You own idle (waste) | You pay only for use (cloud) |
| Unit cost at high util | Low | Higher (cloud premium) |
| Unit cost at low util | High (idle tax) | Low |
| Elasticity | Low (fixed fleet) | High (scale on demand) |
| Hardware refresh | You own it (well/badly) | Provider's problem |
| Depreciation | Yes | No |
| Residual value | Yes (sell old GPUs) | No |
| Predictability | Fixed | Metered/variable |
| Data locality | Max | Provider-dependent |

## Cost components checklist

**CAPEX side:** hardware purchase, depreciation, residual value, refresh cycle,
financing/interest.

**OPEX side:** power, cooling (PUE), staff, licensing, software, support,
network/egress, rack/colocation fees, cloud premiums (on-demand > reserved > spot),
backup/DR, compliance.

> **[I]** A classic CFO trap: comparing an on-prem H100's *deprecated purchase
> price* against a cloud instance *rent* without adding staff, power, cooling,
> and the **idle tax**. When all costs are included, on-demand cloud looks
> expensive; but on-prem looks expensive too unless the fleet is well-utilized.

## Why $/GPU-hour is not enough

$ / GPU-hour is a **capacity price**, not an **output price**. Two identical
clusters at the same $/GPU-hr can have wildly different economics if one runs at
70% utilization and the other at 20%. The figure that governs the *business* is:

### Effective Cost per Productive GPU Hour

$$\text{Effective } \frac{\$}{\text{prod GPU-hr}} = \frac{\text{Annualized infrastructure cost}}{\text{Actual productive GPU hours delivered}}$$

where *productive* excludes idle, SLO-violating, and wasted time
([34-ai-cost-waste](34-ai-cost-waste.md)).

### Worked example (computed)

Using the fully-loaded on-prem H100 model from
[03](03-llm-inference-unit-economics.md) (8×H100 node ≈ $245k/3yr + power + ops):

| Utilization | Effective $/prod GPU-hr | vs nominal ($1.49 @100%) |
|---|---|---|
| 10% | **$14.90** | 10× |
| 20% | **$7.45** | 5× |
| 50% | **$2.98** | 2× |
| 70% | **$2.13** | 1.4× |
| 90% | **$1.66** | 1.1× |

**A fleet idling at 20% utilization is costing more per productive hour than
renting on-demand from AWS ($6.88).** Utilization is where ownership wins or
loses — which is exactly why [05](05-gpu-utilization-economics.md) exists.

## Depreciation, refresh, residual

- For inference, a 3–4 year life on H100-class GPUs is a reasonable planning
  assumption **[I]**; technical depreciation (obsolescence) often outruns book
  depreciation as newer silicon ships.
- Residual value of retired GPUs can offset refresh (sell old fleet to defray
  new one) but is uncertain — don't over-credit it **[A]**.
- **Reserved vs on-demand cloud** trades a fixed commitment for a discount; this
  is cloud-side "CAPEX-like" behavior ([30-capacity-reservation](30-capacity-reservation.md)).

## Decision heuristic [I]

1. **Steady, high, predictable utilization** → buy/own (CAPEX) or reserve.
2. **Bursty or uncertain demand** → on-demand + spot, or API.
3. **Cannot justify utilization** → don't own the GPU; rent the model (API).
4. **Sovereignty/confidential constraints** → on-prem/private, accept the cost
   of ownership ([24-data-governance](24-data-governance.md), [28](28-cloud-bursting-economics.md)).

## Related

[03-llm-inference-unit-economics](03-llm-inference-unit-economics.md) ·
[05-gpu-utilization-economics](05-gpu-utilization-economics.md) ·
[30-capacity-reservation](30-capacity-reservation.md) ·
[29-local-vs-api-economics](29-local-vs-api-economics.md) ·
[31-capacity-planning](31-capacity-planning.md)

## Key takeaways

1. Raw $/GPU-hr misleads; use Effective Cost per *Productive* GPU-Hour.
2. CAPEX buys low unit cost at high utilization and carries an idle tax at low.
3. OPEX buys elasticity at a premium.
4. Utilization, not sticker price, decides where ownership wins.
