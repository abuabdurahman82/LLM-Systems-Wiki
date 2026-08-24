# 15 — LLM Platform Pricing Models

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

Pricing is how the platform turns **cost** into **internal price**. Every scheme
has a strength and a **distortion** — an incentive it quietly creates. Pure
per-token pricing reflects variable cost but ignores reservation; flat
per-GPU-hour pricing rewards utilization but punishes bursty tenants; and every
flat scheme hides expensive shape differences ([06-token-economics](06-token-economics.md)).
Mature platforms use **hybrid pricing** that separates the fixed (capacity) part
from the variable (consumption) part and adds explicit quality/SLO surcharges.

## Pricing models compared

| Model | Strength | Distortion / weakness |
|---|---|---|
| **Per request** | Simple; matches a UX | Ignores token shape (a 1M-context request ≠ a 100-token one) |
| **Per input token** | Reflects prefill cost | Encourages prompt bloat unless cached tokens are cheaper |
| **Per output token** | Reflects decode cost | Punishes long answers, reasoning, verbose agents |
| **Per million tokens** | Human-readable, market-standard | Hides shape unless split in/out/cached |
| **Per GPU-hour** | Matches capacity cost | Rewards utilization but punishes idle/latent demand |
| **Per reserved GPU** | Matches the "we hold capacity for you" reality | Penalizes bursty tenants who need little reserved |
| **Per endpoint** | Simple for app owners | Ignores how much each endpoint consumes |
| **Per user** | Very simple | Completely decoupled from usage → runaway abuse |
| **Subscription** | Budget-predictable | Blunts usage sensitivity; over/under subscribed both distort |
| **Capacity reservation** | Predictability; SLO shield | You pay for idle if underused ([30](30-capacity-reservation.md)) |
| **Priority tier** | Monetizes SLO | Adds governance complexity ([16](16-llm-service-tiers.md)) |
| **Outcome-based** | Aligns to business value | Hard to define/meter "outcome"; risk moves to platform ([43](43-goodput-economics.md)) |

## The golden rule: price what you spend

The least-distorting internal price **mirrors the real cost**:
- separate **input / cached-input / output** (and reasoning) so agents and
  long-prompt tenants pay for what they actually consume
  ([06](06-token-economics.md), [07](07-prefill-decode-economics.md));
- treat **GPU-hour** as the *capacity* dimension, tokens as the *consumption*
  dimension, and keep them separate in the bill.

## Hybrid pricing model (recommended shape)

$$\text{Price} = \underbrace{R}_{\text{reservation}} + \sum_{\text{consumption}} \big(n_{\text{tokens}} \cdot p_{\text{type}}\big) + \underbrace{s}_{\text{premium SLO surcharge}}$$

Example (illustrative): a tenant pays
- **Monthly reservation** (capacity held for them, e.g. a share of a GPU pool),
- **+ token consumption** at input/cached/output rates,
- **+ a premium SLO surcharge** if they buy a GOLD/PLATINUM tier
  ([16-llm-service-tiers](16-llm-service-tiers.md)).

This separates "it costs us to hold capacity" from "it costs us to serve you,"
and lets tenants choose their cost/latency point on the frontier
([12-quality-cost-latency-frontier](12-quality-cost-latency-frontier.md)).

## Pricing anti-patterns

- **Flat per-token for all shapes** → subsidizes agents/long contexts.
- **Per-GPU-hour only** → tenants hoard GPU instead of using tokens; idle waste
  moves back to the platform ([34-ai-cost-waste](34-ai-cost-waste.md)).
- **Per-user flat** → decoupled from usage; the classic "free-for-all" trap.
- **Underpricing cached tokens to zero** → you give away the platform's biggest
  cost saver for nothing (though some platforms intentionally price cache to
  *drive* adoption — a deliberate choice, not an accident).

## Related

[03-llm-inference-unit-economics](03-llm-inference-unit-economics.md) ·
[14-showback-chargeback](14-showback-chargeback.md) ·
[16-llm-service-tiers](16-llm-service-tiers.md) · [46-gpuaas-pricing](46-gpuaas-pricing.md) ·
[54-economics-formulas](54-economics-formulas.md)

## Key takeaways

1. Every pricing model has a distortion; worst is being decoupled from real cost.
2. Mirror the cost: split input/cached/output; separate capacity from consumption.
3. Hybrid (reservation + consumption + SLO surcharge) is the robust default.
4. Price consciously: what you under-price, tenants will over-consume.
