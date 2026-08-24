# 29 — Local vs API Economics

`LAST_UPDATED: 2026-08-24` · Status: core page · Figures computed in
[scripts/economic_foundation.py](scripts/economic_foundation.py).

## 30-Second Explanation

The build-vs-buy question for LLM inference is **local (self-hosted) model vs
third-party API**. The two have different cost *shapes*: local is a **fixed
monthly cost** (capacity you pay for whether used) while API is **variable per
token**. The **break-even point** is the volume at which the fixed local cost
equals the variable API cost. Below it, API is cheaper; above it, local wins.
Crucially, the local-vs-API *per-token* comparison is only valid **at a given
utilization** — the idle tax decides the break-even ([04](04-capex-vs-opex-ai-platform.md),
[05](05-gpu-utilization-economics.md)).

## The comparison space

| Option | Cost shape | Pros | Cons |
|---|---|---|---|
| **Self-hosted model** | Fixed + marginal | data locality, no per-token premium, control | idle tax, ops, fixed |
| **OpenAI-style API** | Variable per token | zero infra, elasticity, latest models | per-token premium, data leaves, rate limits |
| **OpenRouter-style multi-provider API** | Variable; many providers | model choice, resilience | provider variability, still API premium |
| **Managed cloud endpoint** | Fixed + variable | managed, hybrid | less control than self-host |

## Break-even analysis

The classic formula:

$$\text{Break-even tokens} = \frac{\text{Fixed Monthly Cost}}{\text{API Cost/token} - \text{Local Marginal Cost/token}}$$

**Assumptions (state them — the number means nothing otherwise):**
- Fixed monthly cost = fully-loaded local fleet for a month (capacity held) .
- API cost/token = the metered provider price at a given request shape.
- Local marginal cost/token = compute-derived at a stated utilization.

### Worked example (computed)

Using the on-prem 8×H100 model at **~$25,314/mo fixed**:

| API baseline | API cost/req (@1500/500) | Break-even volume |
|---|---|---|
| gpt-4o-mini | $0.0005 | ~**48M req/mo** |
| GPT-4.1 | $0.0070 | ~**3.6M req/mo** |
| gpt-5.6-sol | $0.0225 | ~**1.1M req/mo** |

**Reading:** against a *cheap* API you need a huge volume for local to win; against
a *premium* API the break-even is far lower. The break-even shifts with your
utilization: at 20% utilization local is costlier per effective unit and the
break-even rises (you're paying the idle tax).

## Method & cautions [I]

1. Compute local **fully-loaded** cost, not just GPU purchase price
   ([04](04-capex-vs-opex-ai-platform.md)).
2. Run the comparison at **your real utilization**, not theoretical max
   ([05](05-gpu-utilization-economics.md)).
3. Add **non-cost** terms: data residency ([24-data-governance](24-data-governance.md)),
   latency, control plane, reliability of a third party.
4. Sensitivity: re-run when API prices or GPU costs change
   ([33-ai-finops](33-ai-finops.md)).

A **calculator** (local vs API vs hybrid scenarios) is in
[49-llm-platform-economic-simulator](49-llm-platform-economic-simulator.md), and
the reusable formula lives in [54-economics-formulas](54-economics-formulas.md).

## Related

[04-capex-vs-opex-ai-platform](04-capex-vs-opex-ai-platform.md) ·
[05-gpu-utilization-economics](05-gpu-utilization-economics.md) ·
[28-cloud-bursting-economics](28-cloud-bursting-economics.md) ·
[49-llm-platform-economic-simulator](49-llm-platform-economic-simulator.md) ·
[54-economics-formulas](54-economics-formulas.md)

## Key takeaways

1. Local = fixed; API = variable; the break-even is where they're equal.
2. Break-even tokens = Fixed monthly ÷ (API cost − local marginal cost).
3. Utilization decides the break-even; low utilization pushes you to API.
4. Add residency, latency, control, and provider risk to the pure-price view.
