# 23 — Tenant Security Isolation

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

In a multi-tenant LLM platform, **isolation is not just about the GPU** — it is
about *every surface where one tenant's state could reach another's*: identity,
network, compute, memory, storage, logs, vector databases, **the KV/prompt
cache**, model adapters, secrets, and API keys. LLM platforms add **novel
isolation surfaces** (cache, RAG, adapters) that classic multi-tenancy doesn't
cover, and a leak on any of them can be a serious data breach. ([I] The security
baseline for LLM systems generally is covered by Wiki `Safety/`; here we focus on
the *cross-tenant* dimension.)

## Isolation surfaces

| Surface | What must be isolated | LLM-specific risk |
|---|---|---|
| **Identity** | per-tenant authN/authZ, keys, tokens | key confusion across tenants |
| **Network** | tenant-segmented paths (zero-trust, mTLS) | cross-tenant lateral movement |
| **Compute** | GPU/CPU tenancy ([02-multi-tenancy-models](02-multi-tenancy-models.md)) | side-channel / resource bleed |
| **Memory** | no cross-tenant process sharing of sensitive buffers | dump/remnant memory |
| **Storage** | weights, datasets, checkpoints, object stores | data at rest exposure |
| **Logs / telemetry** | who may read whose logs | cross-tenant log leakage |
| **Vector databases (RAG)** | per-tenant namespaces/filters | RAG retrieval leaking another tenant's documents |
| **KV cache** | per-tenant cache trees/namespaces | cache hit serving another tenant's prompt context |
| **Prompt cache** | same as KV cache | prompt-prefix leakage |
| **Model adapters** | per-tenant LoRA/adapter bindings | adapter confusion (A's adapter served to B) |
| **Secrets** | per-tenant secret stores | shared creds / vault path confusion |
| **API keys** | per-tenant scoped keys | one tenant impersonating another |

## Specific LLM leakage risks

- **Cache leakage** — if the prefix/KV cache isn't namespaced, tenant A's request
  could hit tenant B's cached prompt context (both a privacy and a correctness
  issue). Mitigate with per-tenant cache namespaces ([08](08-kv-cache-economics.md)).
- **Log leakage** — telemetry that logs prompt/response content must be separated
  per tenant under retention policy ([24-data-governance](24-data-governance.md)).
- **RAG leakage** — a shared vector DB without tenant filters can return another
  tenant's documents; enforce tenant scoping in every query ([37-rag-economics](37-rag-economics.md)).
- **Adapter confusion** — with multi-LoRA serving, a bug could bind the wrong
  tenant's adapter; validate model/adapter/tenant binding at request time.
- **Session confusion** — mixing tenants' conversation state in a shared store.

## Principles [I]

1. **Default deny + per-tenant namespace** everywhere (cache, RAG, storage, logs).
2. **Data sensitivity drives isolation** — confidential tenants get hard
   isolation, not soft ([02](02-multi-tenancy-models.md), [24-data-governance](24-data-governance.md)).
3. **Don't log prompt content by default**; if you must, redact and scope it.
4. **Verify the binding** (tenant→model→adapter→cache namespace) on every request.

## Related

[08-kv-cache-economics](08-kv-cache-economics.md) ·
[24-data-governance](24-data-governance.md) · [26-model-access-control](26-model-access-control.md) ·
[47-kubernetes-multi-tenancy](47-kubernetes-multi-tenancy.md) ·
[Safety/](../Safety/README.md)

## Key takeaways

1. Isolation spans identity, network, compute, memory, storage, logs, RAG, cache,
   adapters, secrets — not just the GPU.
2. The KV/prompt cache and RAG DB are *novel* LLM leak surfaces; namespace them per tenant.
3. Watch cache leakage, log leakage, RAG leakage, adapter confusion, session confusion.
4. Data sensitivity should determine isolation level; bind tenant→model→cache at request time.
