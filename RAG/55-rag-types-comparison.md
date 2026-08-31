# RAG Types — Comparison Matrix

`LAST_UPDATED: 2026-08-29` · Status: core page · Synthesis page; the matrix is
an engineering synthesis [I] over this section's pages; pattern definitions
follow the survey lineage [F: 2312.10997] and the individual pattern papers
verified in the research bank 2026-08-29 ([F: 2310.11511 Self-RAG; 2401.15884
CRAG; 2403.14403 Adaptive-RAG; 2401.18059 RAPTOR; 2404.16130 GraphRAG]).

## 30-Second Explanation
Every RAG variant trades complexity for a specific capability: control,
structure, composition, or coverage. This matrix lines the types up on the
axes that matter when you pick one — retrieval style, reasoning load,
complexity/latency/cost, what it unlocks, and what it risks. The honest reading
is in the interpretation below: **accuracy potential is task-dependent, there
is no universal winner, and everything above the basic pipeline correlates
with cost through one mechanism — dynamic retrieval** [I]. Choose with the
decision tree (54); treat this page as the map of the space it chooses from.

## Legend
- **Low / Med / High** — relative scale across the rows of this matrix only
  (a "Med" latency here is high in absolute terms for a chat product).
- **Yes / No / Partial** — capability flags: Partial means conditional on
  configuration or a sub-variant.
- Cell values are qualitative engineering judgments [I], grounded in the cited
  pattern papers where tagged. "Cost" combines build (ingestion) + serving
  (per-query).

## The matrix

| RAG Type | Retrieval | Reasoning | Complexity | Latency | Cost | Accuracy Potential | Dynamic Retrieval? | Multi-Hop? | Graph? | Agent? | Best Use | Main Risk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Basic** (03) | Dense, single-shot top-k | Single LLM pass | Low | Low | Low | Low–Med | No | No | No | No | prototypes, small clean corpora | retrieval miss unrecoverable; no ranking quality |
| **Advanced** (05) | Hybrid + rerank pre/post LLM | Single pass, better-fed | Low–Med | Low–Med | Low–Med | Med | Partial | No | No | No | production text QA default | index/pipeline sync complexity |
| **Modular** (05) | Composable, interchangeable | Pipeline-orchestrated | Med | Med | Med | Med–High | Partial | Partial | Partial | Partial | teams iterating per stage | integration/ops surface grows |
| **Hybrid** (13) | Dense + lexical (BM25), fused | Single pass | Med | Low–Med | Low–Med | Med–High | No | No | No | No | IDs, codes, mixed vocabulary | fusion-weight tuning; index duality |
| **Self-RAG** (21) | On-demand, model-triggered | Self-critique tokens | Med–High | Med–High | Med | Med–High | Yes | Partial | No | No | factuality-critical QA | reflection quality bounds gains; training cost |
| **Corrective RAG** (22) | Evaluated, then corrected/refetched | Evaluator-gated generation | Med–High | Med–High | Med | Med–High | Yes | Partial | No | No | noisy-corpus robustness | evaluator errors propagate; web fallback cost |
| **Adaptive RAG** (23) | Routed by query complexity | Complexity-classified | Med–High | Low (simple) / High (complex) | Med (routable) | Med–High | Yes | Partial | No | No | mixed-traffic workloads | classifier errors mis-route; two pipelines to keep honest |
| **Agentic RAG** (24) | Tool-driven, iterative | LLM plans retrieval | High | High | High | High (task-dependent) | Yes | Yes | Partial | Yes | open-ended research tasks; dynamic plans | loop cost/latency; instability; eval difficulty |
| **Multi-Agent RAG** (25) | Distributed per agent | Inter-agent negotiation | Very High | Very High | Very High | High (task-dependent) | Yes | Yes | Partial | Yes | division-of-labor pipelines | coordination failures; cost blowups |
| **Graph RAG** (28) | Graph traversal over derived graph | Community/summary reasoning | High | Med–High | High (build-heavy) | High for global queries | Partial | Partial | Yes | No | corpus-level themes, entity questions | LLM graph-build cost; graph staleness |
| **Knowledge-Graph RAG** (29) | Curated KG lookups | Path/relation reasoning | High | Med | High | High if KG is good | Partial | Yes | Yes | No | domains with real ontologies | KG maintenance tax; coverage gaps |
| **Recursive RAG** (27) | Iterative, self-invoking | Recursive decomposition | High | High | High | High (task-dependent) | Yes | Yes | No | Partial | deeply nested document structures | recursion depth/cost control |
| **Multi-Hop RAG** (26) | Chained, intermediate queries | Stepwise composition | Med–High | High | Med–High | High for bridge questions | Yes | Yes | No | No | bridge/comparison questions | error compounds per hop |
| **RAPTOR / Hierarchical** (20/19) | Tree-level (summaries + leaves) | Abstraction-aware | High | Med | High (ingest) | High for global/long-doc | No | Partial | Partial (tree) | No | long-document holistic questions | summarization cost; lossy abstractions |
| **Conversational** (32) | History-aware rewriting | Turn-conditioned | Med | Med | Med | Med | Partial | No | No | No | support/chat over corpus | coreference rewrites fail → drift |
| **Memory** (33) | Corpus + memory store | Personalized, stateful | Med–High | Med–High | Med–High | Med–High | Yes | Partial | No | Partial | long-running assistants | memory pollution; privacy surface |
| **Multimodal** (31) | Cross-modal embedding | Vision+text synthesis | High | Med–High | High | Task-dependent | Partial | No | No | No | screenshots, diagrams, scanned docs | modality gap; caption quality bounds |
| **SQL/Structured** (30) | Text-to-SQL / semantic layer | Query planning + synthesis | Med–High | Med | Med | High on governed data | Partial | No | Partial | Partial | metrics, warehouses, BI questions | SQL errors; schema drift; authz |
| **Web** (34) | Live search API | Source triage | Med | High | Med–High (per-query) | Freshness-high, noise-high | Yes | Partial | No | Partial | ever-changing public knowledge | noise; rate limits; reproducibility |
| **Federated** (36) | Multi-source, multi-owner | Result consolidation | Very High | High | High | Coverage-high, consistency-low | Yes | Partial | Partial | Partial | orgs with siloed/regulated sources | inconsistent quality; ACL complexity |

## The design space at a glance
Where each type spends its complexity — build time (ingestion) vs query time
(serving) — which is the axis the cost interpretation below turns on [I]:

```
             spends complexity AT BUILD          spends complexity AT QUERY
             (amortized per request)             (paid every request)
          ┌──────────────────────────────┬─────────────────────────────────┐
 static   │ Advanced/Hybrid (05, 13)     │ Basic (03)                      │
 pipeline │ RAPTOR trees (20)            │                                 │
          │ Graph/KB indexes (28/29)     │                                 │
          ├──────────────────────────────┼─────────────────────────────────┤
 dynamic  │ Adaptive routing tables (23) │ Self-RAG reflection (21)        │
 control  │ Federated source catalogs 36 │ CRAG re-retrieval loops (22)    │
          │                              │ Multi-Hop chains (26)           │
          │                              │ Agentic / Multi-Agent (24, 25)  │
          └──────────────────────────────┴─────────────────────────────────┘
 quadrant 1: pay once, serve many        quadrant 4: most flexible, most
   — the production sweet spot             expensive per query and per failure
```

## Reading the matrix [I]

**The complexity/accuracy Pareto is real but flatter than it looks.** Moving
from Basic to Advanced (hybrid + rerank) buys the largest single quality jump
per unit of complexity — that is why it is the enterprise default (54). Beyond
it, the curve splits: pattern-control types (Self/Corrective/Adaptive) buy
robustness more than peak accuracy; structural types (Graph, RAPTOR) buy
*specific question classes* the others cannot answer at all; compositional
types (Multi-Hop, Agentic) buy coverage of harder questions at the price of
per-hop error compounding. Past rung 0, every gain is conditional on the
failure it targets being present in *your* traffic — which is why the tree
insists on measured failures first (45/47).

**"Dynamic Retrieval?" correlates with cost through one mechanism: the loop.**
Every Yes in that column means retrieval decisions are made *at query time by
an LLM or evaluator* — decide-to-retrieve (Self-RAG), evaluate-then-refetch
(CRAG), route-then-run (Adaptive), plan-then-act (Agentic). Each decision point
is another model call, another latency segment, another nondeterminism source,
and another thing to evaluate. That is the causal chain: dynamic retrieval →
more LLM invocations per query → higher p99 latency, higher per-query cost,
harder evaluation. Static-pipeline types (Basic, Advanced, Hybrid, RAPTOR)
spend their complexity at *ingestion* time instead, which amortizes; that is
the fundamental build-vs-query cost split (44).

**Accuracy potential is task-dependent — read that column per row, per task.**
GraphRAG's own motivation is that vector RAG *fails* on global, corpus-level
questions while remaining excellent on local factual ones [F: 2404.16130];
dense retrieval beats BM25 on semantic QA yet loses on exact-token matching
(13's raison d'être); Adaptive-RAG's contribution is precisely that no single
strategy dominates across question complexity [F: 2403.14403]. "High" in the
accuracy column means "high *for the tasks in its Best Use cell*", not
universally. There is no universal winner — pick by decision tree (54), verify
on your golden set (45/46), and treat any claim of a best overall RAG type as
marketing [I].

- **Complexity has a ledger too.** The design-space diagram above shows why two
  types with similar accuracy potential can differ 10× in operating cost:
  RAPTOR pays its complexity at build (recursive summarization priced once per
  corpus [F: 2401.18059 describes the recursive embedding-clustering-summarizing
  construction]), while Agentic RAG pays a similar total in LLM calls *per
  query*. Same quality ambition, opposite cash-flow shape — and the query-time
  shape also concentrates its cost in your p99, not your ingestion batch (44).

| | Complexity spent at build | Complexity spent at query |
|---|---|---|
| **Cost profile** | amortized; spikes only on reindex | linear in LLM calls per request; concentrates in p99 latency and per-query spend (44) |
| **Failure profile** | a bad build degrades everyone uniformly and detectably (45) | nondeterminism per query; harder to eval, needs trace-level diagnosis (50) |
| **Representatives** | Advanced/Hybrid (05, 13), RAPTOR (20), Graph/KB indexes (28/29) | Self/Corrective/Adaptive (21/22/23), Multi-Hop (26), Agentic/Multi-Agent (24/25) |

**Two columns quietly gate production-readiness: Complexity and Main Risk.**
The types with Very High complexity (Multi-Agent, Federated) also carry the
vaguest failure signatures — when they misanswer, you get 47's six layers
*plus* coordination layers on top. This is why the anti-pattern page (56) lists
"agents when simple retrieval suffices" and "GraphRAG when relationships don't
matter" as two of the most common self-inflicted wounds: the matrix's
High-accuracy rows tempt teams into High-complexity rows without the measured
failures to justify the climb (54's cost ladder).

## Key Takeaways
1. The matrix is a trade-space map, not a leaderboard — every High in accuracy
   is paid for in complexity, latency, or build cost [I].
2. Dynamic retrieval is the cost engine: loop-based types (Self/Corrective/
   Adaptive/Agentic) move model calls from ingestion to query time (44).
3. Structural types (Graph, RAPTOR, KG) unlock question classes similarity
   cannot answer at all [F: 2404.16130] — but only pay off when those
   questions exist in your traffic.
4. Accuracy potential is conditional: match the row's Best Use to your corpus
   and questions via the decision tree (54), then verify on the golden set
   (45/46).
5. The Pareto frontier for most teams: Advanced/Hybrid rows below, Agentic
   rows above — with Adaptive routing as the honest way to occupy both ends
   [F: 2403.14403].

## Related
[54 which RAG should I use — the selection procedure](54-which-rag-should-i-use.md) ·
[05 naive vs advanced vs modular](05-naive-advanced-modular-rag.md) ·
[47 failure modes](47-rag-failure-modes.md) · [56 anti-patterns](56-rag-antipatterns.md) ·
`../Graph-Engineering/Knowledge-Graphs-and-GraphRAG.md` ·
[44 RAG economics](44-rag-economics.md)
