# 26 — Model Access Control

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

**Not every user should reach every model.** Model access control decides *who
may call which model*, using **RBAC** (roles → permissions) and **ABAC**
(attributes → policies). It is the enforcement side of model governance
([25-model-governance](25-model-governance.md)) and the practical gate that
keeps cheap-fast models on the everyday path, premium reasoning models on the
high-value path, and experimental models away from production.

## Example entitlement matrix (illustrative)

| Population | Allowed models |
|---|---|
| **General employees** | small approved models |
| **Developers** | coding models |
| **Research team** | experimental models |
| **Sensitive workloads** | local models only (per data class, [24](24-data-governance.md)) |
| **Premium applications** | high-end reasoning models |

This is a role-shaped example; the *same matrix* can be expressed as attributes.

## RBAC vs ABAC

- **RBAC** — roles carry permissions (*"Developer" may call `code-model`*).
  Simple, but coarse: high sensitivity varies within a role.
- **ABAC** — decisions from **attributes**, so policy is fine-grained and
  combinable:

| Attribute | Example values |
|---|---|
| `tenant` | acme/eng, acme/hr |
| `department` | engineering, legal |
| `data_classification` | public, internal, confidential ([24](24-data-governance.md)) |
| `environment` | dev, test, prod |
| `model_risk_class` | low, medium, high ([25](25-model-governance.md)) |
| `budget` | remaining monthly budget ([22](22-budget-aware-routing.md)) |

A policy might be: *"allow `reasoning-model` only when `department=research` OR
(`model_risk_class=high` AND `environment=prod` AND `budget>threshold`)."*

## Enforcing at the router

The access check runs alongside routing and admission
([21-admission-control-governance](21-admission-control-governance.md),
[22-budget-aware-routing](22-budget-aware-routing.md)):

```
tenant request → resolve attributes → evaluate access policy → if denied:
   reject  |  downgrade to an allowed cheaper model  |  escalate to approver
```

**Downgrade** (offer the best *allowed* model) is usually kinder than reject.

## Governance notes [I]

- Access control must be **materialized per request** from current attributes,
  not cached blindly (budget and data class change).
- **Audit** every allow/deny/downgrade for accountability
  ([42-multi-tenant-observability](42-multi-tenant-observability.md)).
- Compose with **policy-as-code** for reviewability
  ([27-policy-as-code](27-policy-as-code.md)).
- **Exceptions** must flow through the governed workflow
  ([41-policy-exceptions](41-policy-exceptions.md)), not ad-hoc config.

## Related

[25-model-governance](25-model-governance.md) ·
[24-data-governance](24-data-governance.md) · [27-policy-as-code](27-policy-as-code.md) ·
[22-budget-aware-routing](22-budget-aware-routing.md) ·
[40-llm-platform-governance-model](40-llm-platform-governance-model.md)

## Key takeaways

1. Gate which users/apps reach which models; not everyone gets every model.
2. RBAC is simple; ABAC (attributes) is fine-grained and composes.
3. Evaluate access per request from current attributes (budget, data class).
4. Prefer downgrade-to-allowed over hard reject; audit all decisions.
