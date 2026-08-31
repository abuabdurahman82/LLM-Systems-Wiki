# Graph RAG (the Category) — LLM-Built Graphs as a Retrieval Index

`LAST_UPDATED: 2026-08-30` · Status: core page · [F: arXiv:2404.16130 "From
Local to Global: A Graph RAG Approach to Query-Focused Summarization"
(Edge, Trinh, Cheng, et al., 2024) — paper verified this pass; "ECAI 2025"
UNVERIFIED — multiple secondary sources cite it as ECAI 2025 (Bologna,
Oct 25–30), but no ECAI proceedings entry was findable as of 2026-08-30.
Official repo:
github.com/microsoft/graphrag [F: verified via GitHub API 2026-08-30, MIT,
~35.7k stars]. Official docs: microsoft.github.io/graphrag (query modes:
Local / Global / DRIFT Search) [F: verified 2026-08-29].]

## 30-Second Explanation
Vector retrieval answers "which chunk is most like this?" — it is
*query-shaped*. **Graph RAG inverts the index**: an LLM walks the corpus and
builds a *knowledge graph* (entities + relationships + claims), then writes
**community summaries** bottom-up (small community → its summary → parent
community → … → the top-level communities). Global questions — "what are
the main themes across this 500-page corpus?" — have no single matching
chunk; they are answered by map-reduce *over the community summaries at one
level* (each summary → a partial answer → reduce), which the hierarchy makes
cheap. The cost model inverts too: **pay at index time (LLM graph-build),
save at query time** — the paper's 9×–43× fewer tokens is measured *against
re-reading the full corpus text* [F: 2404.16130]; the win against the
vector-RAG baseline is in answer quality (comprehensiveness/diversity), with
the token tradeoff level-dependent, not a flat 9–43× [F].

## The construction (the Microsoft pipeline)

```
corpus (chunks)
  ↓ LLM extract: entities + relationships + claims per chunk
knowledge graph (typed entities, weighted edges, claims attached)
  ↓ hierarchical community detection (Leiden over the graph)
  ↓ LLM summarize each community (bottom-up, with parent rollups)
community report tree:  [community] → [parent] → … → [top-level communities
(C0 — the paper's global mode maps over these; several, not one "root")

GLOBAL query  → map-reduce over the community reports at ONE chosen
                level: map each report → a partial answer, reduce the
                partials → the final answer (the paper's global mode maps
                over root-level C0 reports; the library lets you pick the
                community level)
LOCAL query   → the original graph around the query's entities (the
                "graph-aware version of one-shot RAG")
DRIFT         → global-first: the community reports expand the query into
                sub-questions / intermediate answers, which then drill
                down into local entity-anchored searches per sub-question
```

## The two query regimes (the design's point)

| Regime | Question shape | Mechanism | Why vector retrieval fails it |
|---|---|---|---|
| **Global** (corpus-level sensemaking) | "What are the top themes? What do the incident reports *together* say?" | map-reduce over community reports | no single chunk contains the answer; top-k retrieval returns *similar-looking* chunks, not *corpus coverage* |
| **Local** (entity-anchored) | "What happened in the 2025 outage, and what else does the corpus say about its root cause?" | graph neighborhood of matched entities + their chunks | vector retrieval can do it, but the graph finds *related-but-differently-phrased* evidence |

The paper's result [F: 2404.16130, abstract]: for global sensemaking over
~1M-token corpora, graph-built community summaries yield substantially more
comprehensive and diverse answers than the conventional (vector) RAG
baseline — a quality win. The token figure is a different measurement:
~9×–43× fewer tokens *per global query vs. re-reading the full corpus text*
(that is the "map the summaries instead of the source" saving; the
quality-vs-RAG result is stated without that cost framing).

## The economics (the honest version)

- **Build is the cost**: an LLM entity-extraction pass over the *whole
  corpus* + per-community summarization. For a stable corpus it is paid
  once; for a churning corpus it is a reindex tax (44). This is why the
  anti-pattern is "GraphRAG unearned" (56): if your questions are all
  local, the build cost buys you nothing (54's decision tree says the same).
- **Query is the saving**: global queries stop re-reading the corpus; the
  summary tree is the cache of *understanding* (42's caching idea, at
  corpus scope).
- **Staleness is structural**: the graph summarizes *what the corpus said
  when it was built*; a corpus that changed since the build is answering
  yesterday's question. Version the graph with the corpus (51).

## When to reach for it (and when not to)

**Reach**: corpus-level questions are a real workload (reports, incident
archives, research corpora); the corpus is stable enough to amortize the
build; the entity/relationship structure of the content is meaningful
(domains with real structure: orgs, systems, cases, citations).

**Do not reach**: the workload is exact-token or entity-lookup shaped (that
is BM25 + rerank, 13/14); questions are single-hop local (one-shot RAG
already answers them); the corpus churns weekly (rebuild cost dominates, 44);
you need answers with *fresh* data (a graph is a snapshot, 35).

## Variants in the category [I: the taxonomy shape; per-variant detail in the
named papers]

- **Microsoft GraphRAG** (2404.16130) — the reference: community reports +
  global/local/drift modes; LLM-built.
- **LightRAG** (arXiv:2410.05779, "Simple and Fast RAG" — Gao et al., 2024
  [F: title/id verified via arXiv API 2026-08-30]) — the cheap fast variant:
  flat key-value index over entities/relations (no Leiden community tree),
  dual-level (low/high-granularity) retrieval; markedly lower build cost,
  coarser structure. (Earlier drafts called this "LightGraphRAG"; the
  established name is **LightRAG**).
- **GraphRAG surveys** — Peng et al. arXiv:2408.08921 (2024) and Zhang et
  al. arXiv:2501.13958 (2025) map the space: graph-based retrieval + graph
  reasoning [F: both verified this pass].
- **KG-RAG (29)** — the *strict* version: the graph is **curated, not
  LLM-built**; the index is a real knowledge graph (ontologies, typed
  relations) and retrieval is *path/relation* search. The difference is the
  build cost *and* the trust level: a curated KG is an asset you maintain;
  an LLM-built graph is a derived index you rebuild.

## Related
[04 taxonomy](04-rag-taxonomy.md) · [19 hierarchical](19-hierarchical-rag.md) ·
[20 RAPTOR](20-raptor.md) (the non-graph twin: same "multi-level summaries"
idea, clusters instead of entities) · [24 agentic](24-agentic-rag.md) ·
[29 KG-RAG](29-knowledge-graph-rag.md) · [37 domain-specific](37-domain-specific-rag.md) ·
[44 economics](44-rag-economics.md) · [54 decision tree](54-which-rag-should-i-use.md) ·
[56 antipatterns](56-rag-antipatterns.md)
