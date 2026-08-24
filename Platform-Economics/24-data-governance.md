# 24 — Data Governance

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

**Data governance decides, per piece of data, whether the model, the cloud, the
region, and the retention are permissible.** LLM platforms add a routing
dimension that classic data governance doesn't have: *which model and which
provider may see this data*. The core question is **data classification →
policy → routing** — and a policy like *"no cloud for confidential workloads"*
is a *policy choice, not a universal requirement*. You classify first, route second.

## Data classification dimensions

| Class | Examples | Implication |
|---|---|---|
| **Public / unrestricted** | public docs | any approved model, any pool |
| **Internal** | internal docs, code | internal models; cloud only if approved |
| **PII / personal** | names, emails, health, financial | strict handling, retention limits, residency |
| **Confidential** | business secrets, M&A, launch plans | local-only, audited |
| **Regulated** | PHI (HIPAA), payment (PCI), FERPA, etc. | specific controls, residency, no public cloud often |
| **Customer data** (in a SaaS) | tenants' own data | tenant-isolated, tenant-owned retention |

## Routing architecture

```
Prompt
  ↓
Data Classification      (detect PII/confidential via classifiers/DBLs)
  ↓
Policy
  ├── local model                 (allowed, stays on-prem)
  ├── approved cloud              (allowed, e.g. compliant region/provider)
  └── reject                      (not permitted anywhere)
```

The policy engine ([27-policy-as-code](27-policy-as-code.md)) turns
classification into a routing decision: confidential data → local model only;
regulated → approved cloud region with residency; nothing sensitive → full choice.

## Policy examples

**Example policy — "No cloud for confidential workloads":**
```
IF data_classification = confidential
THEN cloud_provider = prohibited
     model_scope      = local approved only
     retention        = 90 days, audited
```
> This is one valid policy for a sensitive enterprise/regulated tenant. It is a
> **design choice, not a universal rule** — a vendor handling public marketing
> text would reasonably allow cloud. Set it per tenant on the basis of their
> data classification and compliance obligations ([53-platform-governance-decision-framework](53-platform-governance-decision-framework.md)).

## Other governance dimensions

- **Training eligibility** — flag data that must never be used for fine-tuning.
- **Retention / deletion** — how long prompts/logs/embeddings are kept; right to
  be forgotten erasure flows
  ([13-tenant-metering](13-tenant-metering.md), [45-cost-of-failure](45-cost-of-failure.md)).
- **Data residency** — which regions/pools may hold a given class
  ([02-multi-tenancy-models](02-multi-tenancy-models.md) region tier).

## Multi-tenant wrinkle

In a SaaS, each **customer is a data domain**: tenant isolation ([23](23-tenant-security-isolation.md))
plus per-tenant classification and retention. A classification bug (missing PII)
can route confidential data to the wrong model — so classification itself needs
monitoring and tests ([Evaluation-Engineering/](../Evaluation-Engineering/README.md)).

## Related

[23-tenant-security-isolation](23-tenant-security-isolation.md) ·
[26-model-access-control](26-model-access-control.md) ·
[27-policy-as-code](27-policy-as-code.md) ·
[28-cloud-bursting-economics](28-cloud-bursting-economics.md) ·
[40-llm-platform-governance-model](40-llm-platform-governance-model.md)

## Key takeaways

1. Data governance = classification → policy → routing (which model, cloud, region).
2. "No cloud for confidential" is a policy choice, not a universal requirement.
3. Govern retention, deletion, training eligibility, and residency too.
4. In SaaS each customer is a data domain; a classification miss can leak.
