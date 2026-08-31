# Production RAG — Reference Architecture

`LAST_UPDATED: 2026-08-29` · Status: core page · Integration page: every
component links to its deep-dive page; design rationales are [I] unless marked.

## 30-Second Explanation
Production RAG is not a pipeline, it is a *system*: one query path, one
ingestion path, and the cross-cutting machinery that makes both trustworthy
(policy, evaluation, observability, cache, tenancy). The reference architecture
below is the union of everything this section covers — read it as a checklist
for "what must exist", then follow the links for *how*.

## The query path (the system everyone asks about)
```
                        USERS
                          │
                        API GW (authn, rate limits, quotas)
                          │
                         IAM (identity + scope; the security subject)
                          │
                     Query Processor (normalize, language, session ctx, 32)
                          │
                 ┌────────┴─────────┐
                 ▼                  ▼
            Query Router       Policy Engine (ACL scope, trust tier,
            (54/36: which        cost class, answer policy)
             sources?)              │
        ┌──────────┬──────────┐     │
        ▼          ▼          ▼     │
      BM25      Vector DB   Knowledge Graph ──┐
      (13)      (08/09)     (28/29)           │
        │          │          │               │
        └──────────┼──────────┘───────────────┘
                   ▼
            Candidate Merge (cross-source, 36)
                   │
                Reranker (14)
                   │
          Context Compressor / Selector (41, 12 filters)
                   │
                  LLM (43: stable prefix order, prefix-cache-friendly)
                   │
                Verifier (citation check, policy check, 45)
                   │
                Response (answer + verifiable citations + as-of stamps)
                   │
            Citations / Observability store (50: full trace)
```

Component notes [I: each is a decision, not a given]:
- **Query Router** (54/36): source selection per query; the "when NOT to
  retrieve" exit (54) lives here — a router that can answer "no retrieval
  needed" is cheaper than one that always fans out.
- **Policy Engine**: executes the retrieval-time ACLs (48/49) — the single
  most audited component; its decisions are logged per query (50).
- **Three retrievers** shown as the common case; in practice 2 (BM25 +
  vector) is the 80/20 default (13), the graph is optional (28), and any of
  them can be an API/SQL/web source (30/34) — the merge is what makes it
  federated (36).
- **Verifier**: a second, cheap LLM pass or rule-based check on
  citations/entailment (45); on, by default, for high-stakes domains;
  off (cost) for low-stakes.

## The ingestion path (the system nobody sees until it breaks)
```
Sources (docs, DBs, streams, web)
   │
   ├─ Connector layer (per source: parser, schema, stream, robots/terms)
   │
   Trust / Security Pipeline (48)
   │   scan → classify → stamp (tenant, owner, version, rights) → dedup
   │
   Structural Extraction (11: tables, figures, layout, code AST)
   │
   Chunking (10) + Metadata (12) + optional Contextual Enrichment (40)
   │
   Embedding (07: model per language/domain; cache re-embeds, 42)
   │
   Index build/update (08/09: HNSW default; versioned index — see below)
   │
   Ingest Audit (11: 20-doc sample fidelity check) + canary docs (45)
   │
   Index promotion (blue/green: the query path never sees a half-built index)
```

**Index versioning** is the production detail that separates a toy from a
system [I: standard practice]: the index is an *immutable, versioned artifact*
(`index-v47, built 2026-08-29T04:00Z, corpus-snapshot S-881`). The query path
pins a version; reindexing builds v48 in the background; cutover is atomic.
Why: (a) a mid-reindex query must not see half the corpus; (b) "what did the
system know on date T" is answerable (audit, 47); (c) cache invalidation is by
index version (42); (d) evaluation runs against a pinned version (45/46).

## Cross-cutting subsystems
| Subsystem | Role | Deep-dive |
|---|---|---|
| **Evaluation** | golden sets, canaries, per-layer metrics; gates index/model changes | 45, 46 |
| **Observability** | per-query trace (query→chunks→scores→dropouts→prompt→answer), SLIs (TTFT, evidence age, hit rate) | 50 |
| **Caching** | query / embedding / retrieval / semantic layers, keyed by index version + tenant | 42 |
| **Model routing** | cheap model for routing/rewriting, strong model for generation; verifier model | 43, `../Platform-Economics/11-economic-model-routing.md` |
| **Multi-tenancy** | per-tenant filters/indexes, quotas, metering | 49 |
| **Security** | trust pipeline, ACLs, canaries, output DLP | 48 |
| **Economics** | per-stage cost, cost-class routing, ingestion budgets | 44 |
| **Failure handling** | the six-layer taxonomy, alerts per layer, degraded-mode answers ("no evidence found" is a valid answer) | 47 |

## Degraded modes (what "RAG down" should mean)
- **Retriever down**: answer from parametric knowledge *explicitly labeled as
  ungrounded*, or refuse. Never silently fall back to ungrounded answers while
  still citing (48's citation-manipulation threat, mirrored).
- **Reranker down**: ship ANN-ordered top-k with a smaller k (14's fallback).
- **Index stale**: serve with an as-of stamp; if the staleness exceeds the SLO
  for that source class (35), say so in the answer.
- **Verifier down**: for high-stakes, degrade to "citation unverified" labels;
  for low-stakes, serve.
The design principle [I]: *every component has a defined, labeled
degradation* — "the system failed loudly and told you what it did not check"
beats "the system failed silently and cited something plausible".

## Build order (the pragmatic sequence)
1. Baseline pipeline + golden set + retrieval metrics (03, 45, 46).
2. Hybrid + rerank + metadata filters (13, 14, 12).
3. Versioned index + observability + cache (42, 50).
4. Security/tenancy (48, 49) — *before* broad rollout, not after.
5. Exotic patterns (graphs, agents, agentic) — each justified by measured
   retrieval failures from the set above (54, 47).
The anti-pattern is building 5 before 1–4 [I: the recurring enterprise story —
an agent + GraphRAG pilot with no golden set and no retrieval metrics].

## Key Takeaways
1. Production RAG = query path + ingestion path + cross-cutting subsystems;
   the ingestion path (versioned index) is where most outages actually live.
2. The index is an immutable, versioned artifact; cutover is atomic; caches
   and evaluations pin to versions.
3. Policy enforcement is at retrieval time, in the engine (48/49) — the query
   path's security is the retrieval path's security.
4. Every component has a labeled degraded mode; "no evidence" is a valid,
   useful answer.
5. Build order is baseline → hybrid+rerank → versioning/observability →
   security → exotic patterns, each justified by measured failures.

## Related
[50 observability](50-rag-observability.md) · [45 evaluation](45-rag-evaluation.md) ·
[48 security](48-rag-security.md) · [49 tenancy](49-multi-tenant-rag.md) ·
[44 economics](44-rag-economics.md) · [47 failures](47-rag-failure-modes.md) ·
`../Production-Operations/README.md`
