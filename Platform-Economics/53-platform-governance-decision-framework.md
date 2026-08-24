# 53 — Platform Governance Decision Framework

`LAST_UPDATED: 2026-08-24` · Status: reference page

## 30-Second Explanation

When onboarding a tenant, ask a **fixed set of questions** and let their answers
select a concrete configuration — **service tier, GPU pool, model, quota,
budget, routing/data/monitoring policy**. This one-page framework turns a vague
"add a tenant" into a repeatable, auditable decision ([40-llm-platform-governance-model](40-llm-platform-governance-model.md)).

## The onboarding questions

Ask (and record) each:

1. **Who are they?** → tenant/business unit, owner, contact
   ([01-multi-tenant-llm-platform-overview](01-multi-tenant-llm-platform-overview.md)).
2. **What data will they process?** → classification →
   residency/isolation needs ([24-data-governance](24-data-governance.md)).
3. **Which models are needed?** → quality bar, model entitlements
   ([26-model-access-control](26-model-access-control.md), [25-model-governance](25-model-governance.md)).
4. **What SLO is required?** → tier ([16-llm-service-tiers](16-llm-service-tiers.md),
   [17-slo-economics](17-slo-economics.md)).
5. **How much traffic?** → throughput, concurrency
   ([31-capacity-planning](31-capacity-planning.md)).
6. **How much context?** → context budget ([38-long-context-economics](38-long-context-economics.md)).
7. **What budget?** → monthly $/token budget ([20-quota-engineering](20-quota-engineering.md),
   [22-budget-aware-routing](22-budget-aware-routing.md)).
8. **Local or cloud allowed?** → burst/routing policy ([24-data-governance](24-data-governance.md),
   [28-cloud-bursting-economics](28-cloud-bursting-economics.md)).
9. **Dedicated capacity required?** → pool choice ([02-multi-tenancy-models](02-multi-tenancy-models.md),
   [30-capacity-reservation](30-capacity-reservation.md)).
10. **What retention policy?** → telemetry/log retention
    ([13-tenant-metering](13-tenant-metering.md)).
11. **What compliance constraints?** → regulated data, residency, audit
    ([24-data-governance](24-data-governance.md), [55-governance-antipatterns](55-governance-antipatterns.md)).

## Then decide

| Decision | Driven by | Output |
|---|---|---|
| **Service tier** | SLO + budget (Q4, Q7) | bronze/silver/gold/platinum ([16](16-llm-service-tiers.md)) |
| **GPU pool** | isolation + residency (Q2, Q9) | shared/dedicated/cloud ([02](02-multi-tenancy-models.md)) |
| **Model** | quality + entitlements (Q3) | approved model set ([26](26-model-access-control.md)) |
| **Quota** | traffic + context (Q5, Q6) | token/concurrency caps ([20](20-quota-engineering.md)) |
| **Budget** | budget (Q7) | monthly budget → budget-aware routing ([22](22-budget-aware-routing.md)) |
| **Routing policy** | data class + cloud (Q2, Q8) | local/cloud/cascade rules ([24](24-data-governance.md), [11](11-economic-model-routing.md)) |
| **Data policy** | classification + compliance (Q2, Q11) | residency/retention/isolation ([24](24-data-governance.md), [23](23-tenant-security-isolation.md)) |
| **Monitoring** | tier + SLO (Q4) | dashboards/alerts ([42-multi-tenant-observability](42-multi-tenant-observability.md)) |

## Worked example (illustrative)

A tenant `acme/hr` answers: BU=HR; data=confidential PII; models=standard only;
SLO=GOLD (strict); traffic=moderate; context=≤32K; budget=$5k/mo; cloud=no;
dedicated=no; retention=90d; compliance=sovereign.

→ tier GOLD · local shared-protected pool · standard model set · token+concurrency
quota · $5k/mo budget → budget-aware local-only routing · confidential→local,
PII-classified, 90d retention, per-tenant cache/log isolation.

## Record & review

Store the answers + decisions as the tenant's **policy object** ([20](20-quota-engineering.md)),
and **review on change / quarterly** (data class, budget, models drift)
([32-demand-forecasting](32-demand-forecasting.md), [41-policy-exceptions](41-policy-exceptions.md)).

## Related

[40-llm-platform-governance-model](40-llm-platform-governance-model.md) ·
[50-multi-tenant-platform-case-studies](50-multi-tenant-platform-case-studies.md) ·
[20-quota-engineering](20-quota-engineering.md) ·
[57-economics-governance-big-picture](57-economics-governance-big-picture.md)

## Key takeaways

1. Ask the same 11 questions for every tenant — fixed, auditable process.
2. Answers map mechanically to tier, pool, model, quota, budget, routing, data, monitoring.
3. Record as a policy object and review on change.
4. The framework is what turns "add a tenant" from ad-hoc to governed.
