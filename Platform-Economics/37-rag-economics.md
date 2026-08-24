# 37 — RAG Economics

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

RAG shifts cost from *generation* to *retrieval*, and the full RAG pipeline has
a cost line of its own: **embedding, vector storage, retrieval, reranking,
context expansion, generation, and cache reuse**. The counterintuitive lever is
that **better retrieval lowers total cost** — by shrinking the context you stuff
into the model, reducing generation retries, and cutting hallucinations
([36-evaluator-economics](36-evaluator-economics.md),
[45-cost-of-failure](45-cost-of-failure.md)). Cheap-but-sloppy retrieval can be
*more* expensive overall once you count the re-prompts and bad answers.

## RAG cost components

| Component | What it costs | Lever |
|---|---|---|
| **Embedding** | encode each doc & query | cache embeddings, dedupe, reuse ([34](34-ai-cost-waste.md)) |
| **Vector storage** | index + storage per doc | tier by access; prune stale |
| **Retrieval** | query the index | caching repeated queries |
| **Reranking** | re-rank a candidate set | only when retrieval is noisy |
| **Context expansion** | retrieved docs packed into the prompt → prefill/KV cost ([07](07-prefill-decode-economics.md)) | **retrieve less, retrieve better** |
| **Generation** | the model call itself | better input → fewer retries |
| **Cache reuse** | caching embeddings/retrieval/answers | reuse to avoid recompute ([08](08-kv-cache-economics.md)) |

## The central economic lever

$$\text{Total RAG cost} \approx \text{Retrieval cost} + \text{Context cost} + \text{Generation cost} + \text{Failure/retry cost}$$

Better retrieval **reduces** the last three even if it increases the first:

- **Smaller context** → less prefill + KV ([38-long-context-economics](38-long-context-economics.md)).
- **Fewer retries** → fewer generation calls ([36-evaluator-economics](36-evaluator-economics.md)).
- **Fewer hallucinations** → fewer expensive failure outcomes ([45](45-cost-of-failure.md)).

So the economic optimum is usually **"retrieve the minimum context that answers
the question well"** — which is a quality/retrieval engineering target, not a
cost-cutting instinct ([Evaluation-Engineering/RAG-Evaluation](../Evaluation-Engineering/RAG-Evaluation.md)).

## Multi-tenant RAG costs

- Per-tenant retrieval/vector-cost *allocation* needs tenant scoping in metering
  ([13-tenant-metering](13-tenant-metering.md)).
- **RAG leakage** is a security surface — tenant-scoped retrieval is mandatory
  ([23-tenant-security-isolation](23-tenant-security-isolation.md)).
- Caching retrieval **results per tenant** is both an economic and a privacy
  good (don't serve tenant A's cached answer to tenant B).

## Related

[08-kv-cache-economics](08-kv-cache-economics.md) ·
[38-long-context-economics](38-long-context-economics.md) ·
[RAG/](../RAG/README.md) · [23-tenant-security-isolation](23-tenant-security-isolation.md) ·
[34-ai-cost-waste](34-ai-cost-waste.md)

## Key takeaways

1. RAG cost = embedding + storage + retrieval + rerank + context + generation + cache.
2. Better retrieval *lowers* total cost via smaller context, fewer retries, fewer hallucinations.
3. Retrieve the minimum context that answers well.
4. Scope retrieval/caching per tenant for cost allocation and privacy.
