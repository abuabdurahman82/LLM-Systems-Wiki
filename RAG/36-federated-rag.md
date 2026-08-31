# Federated RAG — One Query Across Many Heterogeneous Sources

`LAST_UPDATED: 2026-08-29` · Status: core page · Engineering-reasoning page;
routing patterns are [I] unless a system is cited.

## 30-Second Explanation
An enterprise question ("why did the EU release slip and what's the customer
impact?") rarely lives in one place: the answer needs the project tracker
(SQL), the postmortem (wiki/vector), the customer emails (mail), the pricing
sheet (spreadsheet), and possibly the public release notes (web). **Federated
RAG** is a router + per-source retrieval + evidence composition: one query,
many source-specific retrievers, one merged evidence set, one answer with
per-source citations. It is the architectural answer to "the corpus is not one
corpus, it is twenty".

## The architecture
```
Query
   ↓ Router (per-query source selection: which sources can answer this?)
   ├─ HR index        (vector, people/department scoping)
   ├─ Engineering index (vector + code-aware, 38)
   ├─ CRM             (API / structured, 30)
   ├─ Wiki            (vector, internal docs)
   ├─ SQL / warehouse (text-to-SQL, 30)
   └─ Web             (public record, 34)
   ↓ Per-source retrieval (each with its own ACL, schema, freshness, cost)
   ↓ Candidate merge (dedup across sources, cross-source near-duplicates)
   ↓ Federated ranking (one relevance + trust score across heterogeneous scores)
   ↓ Composition (which sources' evidence is load-bearing; conflict handling)
   ↓ LLM (answer + per-source citations)
```

The hard part is not the retrieval — it is **the merge**. Scores from six
sources are not comparable (BM25 scores, cosine similarities, API relevance
hits, SQL result counts all live on different scales); the router's decision is
irreversible for that query; and the policy engine (below) must have veto power
over *which* source is even consulted.

## Source selection: the router
Per query, the router answers "which sources can plausibly answer this?"
[I: patterns]:
- **Intent-based**: classify the question type (people / technical / customer /
  factual / public) against source descriptors; cheap, works when source
  boundaries are clean.
- **Learned router**: train a small model on (query → sources-used) labels
  from your golden set (46); needed when boundaries blur.
- **Fan-out**: retrieve from *all* sources, let the merge decide. Maximally
  robust, maximally costly — fine for low-QPS internal tools, insane for a
  public chatbot [I].
- **Hierarchical**: cheap router first, escalate on miss (the corrective
  pattern, 22, applied to sources).

Routing failure is a distinct failure mode: the right source was *not
consulted* — undetectable by per-source retrieval metrics, visible only as
"answer is plausible but incomplete" (47: query-layer failure).

## Policy, tenancy, and source trust
Federated RAG is where policy becomes executable:
- **Per-source ACLs**: the user's identity fans out to each source *with that
  source's own authorization* (the CRM checks CRM ACLs; the HR index checks HR
  ACLs). A document the user can see in the wiki but not in the CRM must be
  filtered by the CRM's engine, not by a shared vector index's metadata (12,
  49).
- **Source-trust tiers**: primary sources (issuer, system of record) >
  secondary (wiki summaries) > untrusted (web, external feeds). On
  contradiction, the composition step resolves by tier, and *surfaces the
  conflict* rather than silently picking [I: the standing practice for
  high-stakes domains].
- **Per-source freshness policy**: the CRM is live (structured, 30); the wiki
  is versioned; the web is "as fetched" (34). The answer's citations must make
  the as-of semantics visible ("per CRM as of 14:02, per wiki v3, per web fetch
  13:58").

## Federated ranking
Merging heterogeneous scores, in increasing order of sophistication [I]:
1. **Concatenate**: top-k per source, interleave. Works when per-source quality
   is already calibrated; ignores cross-source scale.
2. **Min-max / quantile normalization** per source, then weighted sum. The
   weights are a product decision (trust tier, freshness) — make them explicit
   and logged (50).
3. **A cross-source reranker**: a model that sees (query, chunk, source-name,
   source-trust, age) and re-scores — the only option that handles
   cross-source near-duplicates and redundancy ("the same fact, three places").
4. **LLM composition as the final judge**: for low-QPS, let the LLM see all
   candidates and pick — expensive but interpretable, and it produces the
   conflict report for free.

## When federation is worth it
- The question class genuinely spans sources (the postmortem example above).
- You already have the sources, each with clean APIs/ACLs; federation is
  *composition*, not new data engineering.
- The alternative — one giant unified index — fails on ACLs (per-source
  authorization models differ), freshness (CRM is live, docs are not), and
  cost (you'd re-embed the CRM nightly).
It is *not* worth it for: single-corpus products (build one pipeline, 03),
or when the router would fan out to 5 sources for 90% of queries (the fan-out
cost is the federation tax [I] — measure it before shipping, 44).

## Key Takeaways
1. Federated RAG = router + per-source retrieval + cross-source merge; the
   merge is the hard part.
2. Authorization fans out *per source, in each source's engine* — a shared
   metadata filter is not a substitute for per-source ACLs (48/49).
3. Trust tiers + as-of citations are what make multi-source answers auditable;
   conflicts should be surfaced, not silently resolved.
4. Routing failures (right source not consulted) are invisible to per-source
   metrics — evaluate them end-to-end (45/47).
5. Fan-out is a cost tax: measure before shipping; route when boundaries are
   clean.

## Related
[30 structured](30-structured-data-rag.md) · [34 web](34-web-rag.md) ·
[38 code](38-code-rag.md) · [48 security](48-rag-security.md) ·
[49 tenancy](49-multi-tenant-rag.md) · [54 decision tree](54-which-rag-should-i-use.md)
