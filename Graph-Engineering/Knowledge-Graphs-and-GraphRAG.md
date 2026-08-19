# Knowledge Graphs & GraphRAG
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
A **knowledge graph (KG)** represents a corpus as *entities* (nodes) and
*relations* (edges): "Paper X cites Paper Y", "Person P works at Company C",
"Drug D interacts with Protein E". **GraphRAG** is the 2024+ retrieval paradigm
that builds such a graph over a corpus and *retrieves over the structure* (edges,
communities, walks) instead of — or in addition to — vector similarity. The
promise: multi-hop and corpus-level questions that flat RAG cannot answer.
The cost: you must *build and maintain* the graph, and the win is
task-dependent (the 2026 counterpoint: "Do We Still Need GraphRAG?",
arXiv:2604.09666 [F]).

## From RAG to GraphRAG (the lineage)
```
RAG (2020, arXiv:2005.11401 [F])          embed chunks → top-k by similarity
   ↓  "retrieval misses multi-hop + can't summarize the whole corpus"
Naive-IR upgrades (2023)                   Self-RAG (arXiv:2310.11511 [F]),
   RAPTOR (arXiv:2401.18059 [F])          tree-indexed recursive summarization
   ↓  "the tree is a *heuristic* structure; the corpus has *real* structure"
GraphRAG (Microsoft, arXiv:2404.16130 [F]) entities+relations via LLM extraction;
   community detection (Leiden) → per-community summaries → local & global search
   ↓  "GraphRAG is powerful but *expensive* (extraction + community summary)"
LightRAG (arXiv:2410.05779 [F])           dual-level (low/high) keywords + graph;
   cheaper index, fast incremental update
HippoRAG (arXiv:2405.14831 [F])           neurobiological: KG + "hippocampal"
   index (Personalized PageRank) → single-step, high-recall retrieval
HippoRAG 2 (arXiv:2502.14802 [F])         *continual*: non-parametric learning,
   no retraining as the corpus grows
```

## The two GraphRAG search modes (arXiv:2404.16130 [F])
- **Local search** (entity-anchored): the query touches specific entities → walk
  the graph from the matched entities, pull their neighbors + related paragraphs.
  Best for *specific, grounded* questions ("what did paper X's authors later
  find?").
- **Global search** (community-anchored): the query asks about the *corpus as a
  whole* ("what are the main themes in these 500 papers?") → use the
  **pre-computed community summaries** (hierarchical, via graph partitioning —
  Leiden in the paper [F]) and map-reduce over them. This is the capability
  *no flat RAG has*: a question about the *whole* corpus, answered from a
  hierarchy of summaries, not from k chunks.
- **Cost asymmetry [F: paper's ablations + I]:** global answers cost far more
  (community summaries are pre-computed; extraction is the heavy step) — the
  paper itself reports GraphRAG's *global* QA at much higher per-query cost than
  baseline, with *better* answer quality on sense-making questions. The
  cost/benefit is the standing decision.

## Why edges beat vectors (the structural argument, hand-computable)
**The multi-hop failure of flat RAG [I + E: arithmetic]:**
- A multi-hop question needs *k* chunks connected by k−1 relations. If each hop's
  retrieval has hit-rate r per step, the flat-RAG chain succeeds with
  probability r^k *if each retrieved chunk is the only one needed per step* —
  but flat RAG retrieves by *similarity to the original query*, not to the
  intermediate answer, so the effective per-hop rate drops with k. At r=0.9:
  k=2 → 0.81; k=3 → 0.73; k=5 → 0.59 [E: 0.9^k].
- A graph retrieval follows *edges* (the relation IS the hop), so per-hop rate is
  the *edge precision* (often much higher — the edge was extracted to connect
  exactly these two entities). If edge precision is 0.95: k=5 → 0.77 [E:
  0.95^5=0.774]. The graph's edge-following is *the* mechanism that keeps
  multi-hop alive.
- **The "needle vs haystack-of-relations" point [I]:** vector search finds the
  chunk *similar to the query*; a graph finds the chunk *connected to the
  answer*. When the answer is 3 hops away, similarity decays (the 3rd-hop chunk
  isn't similar to the original query), but *connectivity* doesn't — that's the
  regime where GraphRAG wins.

## Building the KG (the pipeline, and where it breaks)
```
corpus → [chunk] → [LLM entity/relation extraction] → [entity resolution /
   dedup] → [graph DB (Neo4j / Kuzu / in-memory)] → [community detection] →
   [community summaries (LLM map-reduce)]
```
1. **Extraction quality is the ceiling.** LLM extraction produces *noisy*
   entities/edges (duplicates, near-duplicates, wrong relations). Entity
   resolution (deduping "OpenAI" vs "OpenAI Inc." vs "the company") is
   unsolved-at-scale and dominates error rates [I: consistent across
   GraphRAG-class systems].
2. **Extraction cost is the build cost.** The Microsoft pipeline runs an LLM
   call per chunk for extraction + per community for summaries — on a large
   corpus this is *days of LLM time* [I: order-of-magnitude; the paper's
   own cost section is the reference]. LightRAG's selling point is the cheaper,
   incrementally-updatable index [F: arXiv:2410.05779].
3. **Freshness.** A static KG goes stale the day the corpus changes. HippoRAG 2's
   contribution is *continual* index update without retraining [F:
   arXiv:2502.14802]; temporal-KG memory (Zep, arXiv:2501.13956 [F]) handles
   the *time* dimension (edge valid-intervals) — see
   `../Context-Engineering/Agent-Memory.md`.
4. **Edge confidence.** Not all edges are equal; a well-extracted edge and a
   guessed one should carry different weights (affects the PageRank-style
   walks). Production KGs tag edges with confidence/provenance [I].

## When GraphRAG helps vs hurts (the decision, [I] — evidence-informed)
- **Helps:** (a) multi-hop / "why" questions over a *domain* corpus; (b)
  *global sense-making* ("themes across the corpus"); (c) corpora with rich,
  *extractable* relations (scientific, enterprise-knowledge, legal).
- **Hurts / doesn't pay:** (a) single-hop factual lookup (flat RAG is cheaper
  and as good); (b) short or fast-changing corpora (build cost > value); (c)
  corpora where relations aren't extractable by LLMs (dense numeric/visual
  data).
- **The 2026 counterpoint [F: arXiv:2604.09666, "Do We Still Need GraphRAG?"]:**
  recent long-context + strong models close much of the gap on many tasks — the
  honest reading is that **GraphRAG's win is now narrower** (it's a *structure*
  play, not a universal upgrade), and the benchmark must be task-pinned before
  anyone declares the winner. [I: consistent with the paper's finding that the
  win is benchmark-dependent]
- **Hand rule [I]:** build the graph when the task is *multi-hop over a stable,
  relational corpus* and you can afford the extraction; otherwise flat RAG +
  good reranking, and revisit when the model gets weaker on *your* tasks.

## Related
`GNN-Basics.md` (the model layer over the same structure) ·
`Reasoning-Graphs.md` (search over graphs) · `Agent-Workflow-Graphs.md` (systems
as graphs) · `../RAG/README.md` (the baseline) ·
`../Context-Engineering/Agent-Memory.md` (Zep temporal KG) ·
`../Agents/Agent-Evaluation.md` (task-pinned benchmarking).

## Key Takeaways
GraphRAG = LLM-extracted KG + structure-aware retrieval (local entity walks,
global community summaries). It wins on *multi-hop* and *corpus-level* questions
where connectivity, not similarity, carries the answer — and it loses on
single-hop lookups and fast-changing corpora where the build cost dominates.
The 2026 state: narrower wins than the 2024 hype, and the decision is
per-task, not universal.
