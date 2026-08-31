# Knowledge-Graph RAG — Retrieval as Path and Relation Search

`LAST_UPDATED: 2026-08-30` · Status: core page · The Graph-Engineering
section carries the KG mechanics; this page is the *retrieval-system* view:
how a curated KG plugs into a RAG pipeline and when it beats the LLM-built
graph of 28.

## 30-Second Explanation
**KG-RAG is the strict end of the graph-RAG spectrum**: instead of an LLM
*deriving* a graph from the corpus (28), the index is a **curated knowledge
graph** — real entities, typed relations, ontologies, maintained as a data
asset. Retrieval is then not "nearest chunk" but **path search and relation
queries**: find the entities the question names, walk the typed relations,
and fetch the *evidence* (text chunks) attached to the entities/edges on the
path. The KG is the *routing layer*; the text chunks are still the evidence.

## Why a curated KG, and not an LLM-built one

| | LLM-built graph (28) | Curated KG (this page) |
|---|---|---|
| Build | LLM extraction over the corpus, at index time | human/pipeline-curated asset, maintained |
| Trust level | derived index — wrong when the LLM misreads | data asset — wrong only when the KG is stale/wrong |
| Schema | loose, whatever the LLM extracts | ontology: typed entities, typed relations, constraints |
| Retrieval | community reports (global) + neighborhood (local) | **path/relation traversal** (structured queries) |
| Cost shape | reindex tax on churn (44) | maintenance tax on the *ontology* (the asset) |
| Fails when | the content lacks real structure; churn kills the amortization | the domain lacks a stable ontology; curation can't keep up |

The decision is about the **domain's structure**: if the content genuinely
is entities-and-relations (orgs/cases/genes/compounds/contracts), the KG is
*the data*, and RAG without it is re-learning it with an LLM on every build.

## The pipeline shape

```
question
  ↓ entity + relation recognition (LLM or NER)
match entities in the KG (the "anchor" step — precision matters here)
  ↓ path / relation search over the ontology
     (typed walks: e.g. incident → component → owner-team)
selected subgraph + attached evidence chunks (the claims/notes on entities & edges)
  ↓ hybrid with text retrieval (13): the KG path is one ranked list,
     the dense/BM25 retrieval another; fuse (RRF or learned, 13)
context pack (41): subgraph facts + top evidence chunks, ordered by path
  ↓ LLM → answer citing the path (provenance = the walked relations)
```

Two design consequences:
1. **The answer cites a *path*, not a chunk** — provenance is structural
   ("incident A → component B → team C"), which is the auditability win
   over vector retrieval (50).
2. **The KG list and the text list are fused, not merged**: a path match
   says "these entities are *related*"; a text match says "these chunks are
   *similar*". They disagree often; the fusion (13) is the design decision.

## The two KG-RAG failure modes (the ones that are KG-specific)

- **Anchor miss**: the question names the entity in a phrasing the KG does
  not alias → no path, no retrieval, and the text side never gets the
  structured signal. Fix: an alias layer + fallback to text retrieval when
  anchor confidence is low (the hybrid is the safety, 13).
- **Ontology drift**: the KG's relation types stop matching how the content
  actually organizes (new systems, new org shapes) → paths exist but are
  *the wrong paths*. This is the KG version of staleness (35/47); the
  detection is a periodic "does a human-crafted path answer these golden
  questions" audit (46).

## When it wins over 28's LLM-built graph

- The domain has a **stable, maintained ontology** (regulatory, scientific,
  legal, enterprise-asset) — curation is already happening; RAG should use
  the asset, not re-derive it.
- **Provenance/audit is a requirement**: "why did the system say that" must
  be a traceable path, not a summary.
- Queries are **relation-shaped** ("all components owned by team X that were
  involved in 2025 incidents") — structured walks are exact *with respect to
  the KG's correctness and completeness* [I: exactness is conditional on the
  asset being current — see ontology drift, 35/47]; vector retrieval is
  approximate regardless.

And when it does *not*: the domain's structure is looser than the ontology
(the LLM-built graph of 28 fits better), or the "KG" is a marketing label
for a flat table (then it is just structured-data RAG, 30).

## Related
[04 taxonomy](04-rag-taxonomy.md) · [13 hybrid + fusion](13-hybrid-rag.md) ·
[28 GraphRAG (category)](28-graph-rag.md) · [30 structured-data RAG](30-structured-data-rag.md) ·
[35 realtime/freshness](35-realtime-rag.md) · [37 domain-specific](37-domain-specific-rag.md) ·
[41 context compression](41-context-compression.md) · [44 economics](44-rag-economics.md) ·
[45 evaluation](45-rag-evaluation.md) · [46 golden datasets](46-rag-golden-datasets.md) ·
[47 failure modes](47-rag-failure-modes.md) · [50 observability](50-rag-observability.md) ·
`../Graph-Engineering/Knowledge-Graphs-and-GraphRAG.md` (the KG mechanics deep dive)
