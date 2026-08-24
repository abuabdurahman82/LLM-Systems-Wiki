# 22 — Budget-Aware Routing

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

A router that ignores money will happily spend a tenant's entire budget on the
premium model by noon. **Budget-aware routing** adds a *cost constraint* to the
routing decision ([11-economic-model-routing](11-economic-model-routing.md)): given
a tenant's remaining monthly budget and each option's cost, the router chooses
the model/pool that maximizes value *subject to not blowing the budget*. The
decision is formalized as a **utility function** — quality value minus cost,
latency, and risk penalties — and the router is configured to downgrade or burst
as the budget drains.

## Example (illustrative)

A tenant has **$2,000 remaining** this month; a request can run on:

| Option | Quality | Latency | Cost |
|---|---|---|---|
| Local small model | low-med | fast | **$0.01** |
| Local large model | med-high | medium | **$0.07** |
| Cloud reasoning | high | variable | **$0.40** |

The router weighs quality vs cost vs latency vs privacy. With a tight budget,
most requests route **local-small**; hard ones escalate to **local-large** or
**cloud** only when the budget can bear it and policy permits ([24-data-governance](24-data-governance.md)).

## Utility model (illustrative decision model)

$$\text{Utility} = \underbrace{\text{Quality Value}}_{\text{task benefit}} - \underbrace{\text{Cost Penalty}}_{\text{price × budget pressure}} - \underbrace{\text{Latency Penalty}}_{\text{SLO pressure}} - \underbrace{\text{Risk Penalty}}_{\text{privacy / policy risk}}$$

> ⚠️ This is an **illustrative decision model**, not a standard or a physical
> law. The exact weights are platform-specific and should be tuned with evals and
> real cost data ([12-quality-cost-latency-frontier](12-quality-cost-latency-frontier.md)).

The **budget pressure term** rises as the remaining budget falls, so the router
progressively prefers cheaper options — a smooth version of "we're running low,
shift to small model." When budget hits zero, admission control takes over and
rejects/downgrades ([21-admission-control-governance.md](21-admission-control-governance.md)).

## Multi-constraint routing

Budget-aware routing composes with every other constraint the router already
honors:

- **Quality** floor — never route a high-stakes request to a too-weak model.
- **Latency** SLO — never pick the option that misses the deadline.
- **Privacy/policy** — never route confidential data to cloud
  ([24-data-governance](24-data-governance.md), [26-model-access-control](26-model-access-control.md)).
- **Model entitlement** — tenant may only see approved models ([26](26-model-access-control.md)).

## Governance & metering

- The **budget** is the governance lever (who set it, who raises it —
  [40-llm-platform-governance-model](40-llm-platform-governance-model.md)).
- The router must **meter** every decision (chosen option + cost + why) so
  budget disputes are resolvable ([13-tenant-metering](13-tenant-metering.md)).

## Related

[11-economic-model-routing](11-economic-model-routing.md) ·
[12-quality-cost-latency-frontier](12-quality-cost-latency-frontier.md) ·
[20-quota-engineering](20-quota-engineering.md) ·
[24-data-governance](24-data-governance.md) ·
[26-model-access-control](26-model-access-control.md)

## Key takeaways

1. Add cost/budget as a first-class router input, not an afterthought.
2. Utility = quality − cost − latency − risk (illustrative model).
3. Budget pressure grows as funds drain, nudging toward cheaper options.
4. Compose budget awareness with quality, SLO, privacy, and model-entitlement rules.
