# 14 — Showback vs Chargeback

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

Once you meter ([13](13-tenant-metering.md)), you face a governance choice:
**tell** tenants what they consumed (**showback**) or **financially push** the
cost onto them (**chargeback**). Showback is low-friction and builds cost
awareness; chargeback changes behavior by making consumption hit a budget.
Most organizations are wise to run **showback before chargeback** — you need a
trusted, accepted cost allocation before you make it a line on someone's P&L.
The five-stage maturity ladder below is the standard pathway.

## Definitions

- **Showback** — report to each tenant what they consumed (tokens, GPU-hours,
  $ attributed) without moving money.
- **Chargeback** — *allocate* the cost to the tenant financially (a real
  internal charge, budget line, or invoice).

| Mode | Money moves? | Behavior change | Friction | When to use |
|---|---|---|---|---|
| **No chargeback** | No | None (tragedy of the commons) | Lowest | Accidental; never a plan |
| **Showback** | No | Awareness → incidental optimization | Low | Start here; build trust |
| **Soft chargeback** | Soft budget / notional | Moderate | Medium | Encourage, tolerate overrun |
| **Hard chargeback** | Real budget line/hard | Strong | High | Mature, accountable orgs |
| **Internal marketplace** | Real + choice | Strongest | Highest | Optimized, price-driven |

## Organizational consequences

- **No chargeback** → tenants treat GPUs as free → unbounded demand, over-large
  models, idle clusters => the classic failure of
  [55-governance-antipatterns](55-governance-antipatterns.md) (#1 "unlimited free access").
- **Showback** → tenants see their cost → often enough to right-size without
  fighting (visible cost is the cheapest governor).
- **Hard chargeback** → tenants optimize, but platform team faces pushback and
  needs a *defensible cost-allocation model*; disputes over methodology are the
  #1 friction.
- **Internal marketplace** → tenants choose among siibs/options; requires good
  prices ([15-llm-platform-pricing-models](15-llm-platform-pricing-models.md)) and
  trust; high design effort.

## Maturity model (Levels 0–5)

| Level | Name | What exists | Key enabler |
|---|---|---|---|
| **0** | Free-for-all | Nothing; shared keys, no attribution | — |
| **1** | Metered | Per-tenant consumption recorded ([13](13-tenant-metering.md)) | metering schema |
| **2** | Showback | Consumption reported to tenants | attribution + dashboards |
| **3** | Budget enforcement | Tenants constrained to budgets ([20](20-quota-engineering.md)) | quota/budget engines |
| **4** | Chargeback | Cost financially allocated to tenants | defensible cost model |
| **5** | Dynamic economic optimization | Prices steer to more efficient models/pools in real time | closed-loop router + prices ([22](22-budget-aware-routing.md)) |

Most organizations live at 0–2 and *should* target 3 before 4: **enforce budgets
before you charge money**, so tenants aren't surprised by an invoice they never
agreed to.

## Designing a defensible allocation

- **Allocate at the tenant** (accounting boundary from [01](01)). Don't allocate
  at user level.
- **Publish the methodology**: how $/token, $/GPU-hr, and overhead markups are
  computed ([03](03-llm-inference-unit-economics.md),
  [54-economics-formulas](54-economics-formulas.md)).
- **Separate infrastructure** (reserved) from consumption (variable) so tenants
  see the difference ([30-capacity-reservation](30-capacity-reservation.md)).
- **Review cadence** — allocation models rot as prices and usage change.

## Related

[13-tenant-metering](13-tenant-metering.md) · [15-llm-platform-pricing-models](15-llm-platform-pricing-models.md) ·
[20-quota-engineering](20-quota-engineering.md) · [33-ai-finops](33-ai-finops.md) ·
[40-llm-platform-governance-model](40-llm-platform-governance-model.md)

## Key takeaways

1. Showback = tell; chargeback = allocate money. Different governance weights.
2. Run showback before chargeback — method must be trusted before it's financial.
3. Maturity: 0 free → 1 metered → 2 showback → 3 budget → 4 chargeback → 5 optimization.
4. A defensible, published allocation model is the precondition for chargeback.
