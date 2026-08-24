# 27 — AI Policy as Code

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

**Governance that lives in documentation gets ignored; governance encoded as
machine-enforceable policy gets executed.** Policy-as-code applies engines like
**OPA (Rego)**, **Gatekeeper**, **Kyverno**, or bespoke policy services to the
AI platform so that "which model, which cloud, how much context, what budget,
where the data may go" are **deterministic, versioned, tested rules**, not human
judgment calls at request time. This is the enforcement backbone for every
governance rule in this section ([24](24-data-governance.md),
[25](25-model-governance.md), [26](26-model-access-control.md)).

## What policies govern

- **Which models are allowed** (per role/tenant) — [26](26-model-access-control.md).
- **Which tenants can use cloud models** — [24](24-data-governance.md), [28](28-cloud-bursting-economics.md).
- **Maximum context** — bound expensive long-context ([38-long-context-economics](38-long-context-economics.md)).
- **Maximum output tokens** — cap decode/agent blowup ([34-ai-cost-waste](34-ai-cost-waste.md)).
- **Budget** — enforce consumption ceilings ([22-budget-aware-routing](22-budget-aware-routing.md)).
- **GPU pools / regions** — residency and isolation ([02](02-multi-tenancy-models.md)).
- **Logging / retention** — what's recorded, how long ([13-tenant-metering](13-tenant-metering.md), [24](24-data-governance.md)).

## Example conceptual policy (OPA-style Rego pseudocode)

```rego
# "Confidential data must never reach a cloud provider."
deny[reason] {
    input.data_classification == "confidential"
    input.route.provider_type == "cloud"
    reason := "confidential data cannot be routed to cloud"
}
```

This is a **conceptual** illustration — real Rego differs; the point is the
declarative *if → then* shape:
```
IF data_classification = confidential
THEN cloud_provider = prohibited
```

## Benefits & cautions

- **Reviewable & versioned** — a policy change is a code review + rollout, not a
  mempire edit; audit-friendly.
- **Fast & deterministic** — consistent enforcement, low latency.
- **Testable** — policies can be unit-tested with sample requests
  ([Evaluation-Engineering/](../Evaluation-Engineering/README.md)).
- **Caution [I]:** policy evaluation must be **fast and fail-safe** — a slow
  policy call on the hot path hurts latency; a policy that errors (fails open)
  is as dangerous as one that fails closed. Decide the failure mode deliberately.

## Where it plugs in

Policy-as-code sits in the **policy engine** block of the admission/routing
architecture ([21-admission-control-governance](21-admission-control-governance.md),
[48-enterprise-multi-tenant-llm-platform](48-enterprise-multi-tenant-llm-platform.md)),
and for Kubernetes-native workloads composes with **Gatekeeper/Kyverno**
([47-kubernetes-multi-tenancy](47-kubernetes-multi-tenancy.md)).

## Related

[21-admission-control-governance](21-admission-control-governance.md) ·
[24-data-governance](24-data-governance.md) · [26-model-access-control](26-model-access-control.md) ·
[41-policy-exceptions](41-policy-exceptions.md) ·
[47-kubernetes-multi-tenancy](47-kubernetes-multi-tenancy.md)

## Key takeaways

1. Encode governance as versioned, testable, machine-enforced policy — not prose.
2. Policies govern models, cloud use, context/output caps, budgets, pools, regions, logging.
3. Declarative if→then rules (e.g. confidential → no cloud) are the core pattern.
4. Policy must be fast and its failure mode (open vs closed) deliberate.
