# 40 — Platform Governance Model (Organization)

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

An LLM platform needs **clear ownership**, or every hard question (who approves
models? who sets quotas? who owns cost?) gets answered by whoever yells
loudest. This page defines the **roles** and uses **RACI** (Responsible /
Accountable / Consulted / Informed) to assign the governance questions that
recur throughout this section. The role set is illustrative — tailor to your
org — but *someone must own each decision or it goes ungoverned.*

## Possible roles

| Role | Responsibility |
|---|---|
| **AI Platform Team** | run the platform: capacity, scheduling, serving, metering, availability |
| **Security** | isolation, vulnerability, access, audit ([23](23-tenant-security-isolation.md)) |
| **FinOps** | cost visibility, allocation, optimization, forecasting ([33-ai-finops](33-ai-finops.md)) |
| **Data Governance** | classification, retention, residency ([24-data-governance](24-data-governance.md)) |
| **Legal** | contracts, licenses, compliance, provider approval |
| **Application Team** | the tenant's app that consumes the platform; owns its usage/budget |
| **Model Risk** | evaluate/approve models for risk ([25-model-governance](25-model-governance.md)) |
| **Architecture** | platform design, tenancy, routing, reference architecture ([48](48-enterprise-multi-tenant-llm-platform.md)) |
| **Business Owner** | owns the platform budget and its business value |

## RACI on the recurring governance questions

| Decision | R (does it) | A (owns it) | C (consulted) | I (informed) |
|---|---|---|---|---|
| **Who approves models?** | Model Risk | Platform + Model Risk | Application Owner, Security | Business Owner |
| **Who sets quotas?** | Platform (from demand) | FinOps/Business Owner | Application Team | all tenants |
| **Who owns costs?** | FinOps | Business Owner | Platform | tenants ([14](14-showback-chargeback.md)) |
| **Who approves cloud providers?** | Security/Architecture | Legal + Business | Data Governance | all |
| **Who can override policies?** | Platform (break-glass) | Business Owner (governed) | Security, Model Risk | audit log |
| **Who owns incidents?** | Platform SRE | Platform | Application, Security | stakeholders ([Production-Operations/30-llm-incident-response](../Production-Operations/30-llm-incident-response.md)) |
| **Who retires models?** | Platform | Model Risk | Application owners | all ([25](25-model-governance.md)) |

>[I] Two rules make RACI usable: (1) exactly one **A** per decision (a shared-A is
> an unowned-A); (2) **overrides are auditable** — a business owner can overturn
> a policy decision, but it logs and follows the exception workflow
> ([41-policy-exceptions](41-policy-exceptions.md)).

## Why governance organization matters to economics

Cost sustainability is an *ownership* problem as much as a math problem
([14-showback-chargeback](14-showback-chargeback.md)): if nobody **owns** the
budget, nobody *caps* the spend, and the platform becomes the unbounded-money pit
of [55-governance-antipatterns](55-governance-antipatterns.md). Clear RACI on
quotas, budgets, and model approval is what turns the technical machinery in the
rest of this section into a governed business.

## Related

[41-policy-exceptions](41-policy-exceptions.md) ·
[14-showback-chargeback](14-showback-chargeback.md) ·
[25-model-governance](25-model-governance.md) ·
[53-platform-governance-decision-framework](53-platform-governance-decision-framework.md) ·
[40-llm-platform-governance-model](40-llm-platform-governance-model.md)

## Key takeaways

1. Every hard question needs an owner, or it goes ungoverned.
2. Define roles (platform, security, FinOps, data, legal, app, model-risk, architecture, business).
3. RACI: exactly one accountable owner per decision; overrides logged and governed.
4. Economic sustainability is an ownership problem — someone must own the budget.
