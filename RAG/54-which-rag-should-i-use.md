# Which RAG Should I Use? — A Decision Tree

`LAST_UPDATED: 2026-08-29` · Status: core page · Decision-guidance page; the
tree is engineering judgment [I]; pattern definitions follow this section's
pages and the survey lineage [F: 2312.10997, verified 2026-08-29]. The matrix
companion is 55; the anti-pattern list is 56.

## 30-Second Explanation
Start from your *data* and your *questions*, not from a technique you want to
try. The tree below walks the actual decision: structured data → SQL RAG;
relationships between entities → graph RAG; one retrieval pass insufficient →
multi-hop/agentic; exact tokens matter → hybrid; non-text content → multimodal;
ever-changing knowledge → web/real-time; long conversations → memory-aware RAG;
inconsistent quality → corrective/self/adaptive control patterns. For most
enterprise text corpora the answer is unglamorous and correct: **hybrid
retrieval + reranker + metadata filtering, done well, before any exotic
pattern** [I].

## The decision tree

```
                          ┌─────────────────────────────────────┐
                          │ What does the data actually look    │
                          │ like, and what do the questions     │
                          │ actually ask?                       │
                          └──────────────┬──────────────────────┘
                                         ▼
        ┌────────────────────────────────────────────────────────────────┐
        │ Q1 Do you have structured data? (tables, warehouses, metrics)  │
        └───────┬───────────────────────────────────────────────┬────────┘
             YES▼                                               ▼NO
   SQL/Structured RAG (30)                                          ▼
        ┌────────────────────────────────────────────────────────────────┐
        │ Q2 Do relationships matter? (multi-entity, "how are X and Y    │
        │    connected", global themes)                                  │
        └───────┬───────────────────────────────────────────────┬────────┘
             YES▼                                               ▼NO
   Graph/KG RAG (28/29)                                             ▼
        ┌────────────────────────────────────────────────────────────────┐
        │ Q3 Does one retrieval step suffice? (or does answering need    │
        │    evidence from several dependent lookups?)                   │
        └───────┬───────────────────────────────────────────────┬────────┘
              NO▼                                               ▼YES
   Multi-Hop / Agentic RAG (26/24)                                  ▼
        ┌────────────────────────────────────────────────────────────────┐
        │ Q4 Is lexical matching critical? (IDs, error codes, part       │
        │    numbers, SKUs, exact phrases)                               │
        └───────┬───────────────────────────────────────────────┬────────┘
             YES▼                                               ▼NO
   Hybrid retrieval (13)                                            ▼
        ┌────────────────────────────────────────────────────────────────┐
        │ Q5 Do documents contain images/tables/diagrams?                │
        └───────┬───────────────────────────────────────────────┬────────┘
             YES▼                                               ▼NO
   Multimodal RAG (31)                                              ▼
        ┌────────────────────────────────────────────────────────────────┐
        │ Q6 Does knowledge change constantly? (news, prices, statuses)  │
        └───────┬───────────────────────────────────────────────┬────────┘
             YES▼                                               ▼NO
   Real-Time/Web RAG (35/34)                                        ▼
        ┌────────────────────────────────────────────────────────────────┐
        │ Q7 Are conversations long-running? (state, preferences, prior  │
        │    turns matter)                                               │
        └───────┬───────────────────────────────────────────────┬────────┘
             YES▼                                               ▼NO
   Conversational/Memory RAG (32/33)                                ▼
        ┌────────────────────────────────────────────────────────────────┐
        │ Q8 Is retrieval quality inconsistent across queries?           │
        └───────┬───────────────────────────────────────────────┬────────┘
                 ▼
   Corrective/Self/Adaptive patterns (22/21/23)
```

### Rationale per branch
- **Q1 YES → SQL/Structured RAG (30).** If the truth lives in tables, forcing
  it through text chunks loses the joins, aggregations, and freshness the
  warehouse already provides. Text-to-SQL over governed schemas keeps
  precision; vector retrieval over database *documentation* complements it.
- **Q2 YES → Graph/KG RAG (28/29).** Questions like "which suppliers of X are
  also certified for Y?" or "what are the main themes across the corpus?" are
  queries over structure, not similarity — the GraphRAG paper shows vector
  retrieval fails on exactly this global-query class [F: 2404.16130]. Note the
  build cost: an LLM-constructed graph index is a major ingestion investment;
  earn it (28).
- **Q3 NO (one step doesn't suffice) → Multi-Hop / Agentic RAG (26/24).** If
  answering requires finding A to learn how to find B (bridge questions,
  decomposition), single-pass retrieval cannot collect the evidence chain —
  iterative retrieval with intermediate queries is the fix (26), with an agent
  loop when the *plan* itself must be dynamic (24).
- **Q4 YES → Hybrid retrieval (13).** Dense embeddings blur exactly the tokens
  that must match exactly; BM25 keeps them sharp, and RRF fusion gives you
  both [F: RRF, Cormack et al., verified in research bank]. Error codes, part
  numbers, and names are where pure-dense systems bleed recall.
- **Q5 YES → Multimodal RAG (31).** Screenshots, engineering diagrams, scanned
  tables, and figures carry evidence text extraction destroys; retrieve across
  modalities or pair caption retrieval with the original image.
- **Q6 YES → Real-Time/Web RAG (35/34).** When the answer's half-life is hours,
  no index refresh cadence saves you; retrieval-at-query-time from the live
  web or streams is the only fresh source. Accept the latency and reliability
  costs; cache with short TTLs (42).
- **Q7 YES → Conversational/Memory RAG (32/33).** Long threads need history
  compression, entity resolution across turns, and a memory store; otherwise
  every third question silently becomes Q1-failure-shaped (47).
- **Q8 (inconsistent quality) → Corrective/Self/Adaptive (22/21/23).** If the
  baseline works most of the time but fails unpredictably, add *control*: CRAG
  evaluates retrieval quality and triggers corrective actions (retrieval
  refinement, web fallback) [F: 2401.15884]; Self-RAG makes the model
  retrieve on demand and critique its own evidence support [F: 2310.11511];
  Adaptive-RAG routes by question complexity — simple queries skip the heavy
  machinery [F: 2403.14403].

## The default answer for most enterprise cases [I]
**Hybrid retrieval (13) + cross-encoder reranker (14) + metadata filtering
(12), evaluated on a golden set (45/46) — before any exotic pattern.**

This trio addresses the three failure classes that dominate real deployments:
vocabulary mismatch (hybrid), ordering and context pollution (rerank), and
scope/access/freshness (metadata). Everything else — graphs, agents, RAPTOR
trees, multi-agent swarms — is a rung *above* this default, and each rung must
be justified by a measured retrieval failure the default could not fix (45/47).
It is the same order the reference architecture builds in (51) and the same
one the survey literature's Advanced-RAG pattern describes [F: 2312.10997].

## When NOT to use RAG
RAG is the answer to "large, changing, heterogeneous corpus, cited answers."
Outside that envelope, simpler tools win [I]:

| Situation | Better tool | Why |
|---|---|---|
| Small, stable fact set (a few hundred facts, rarely changing) | fine-tune, or just put the facts in the system prompt (39) | retrieval infrastructure buys nothing; context fits; a frozen fact set doesn't need freshness |
| Exact lookup with a known key ("status of order 12345") | API / SQL call (tool use) | deterministic systems answer deterministically; RAG adds probabilistic machinery to a precise problem |
| Public, fast-changing knowledge | plain web search tool | the web's index is already built; crawling it into your vector DB duplicates it worse |
| Computation, not knowledge ("what's 17.5% of 240,000") | code/calculator tool | no retrieval solves arithmetic; the corpus is irrelevant |
| The model already knows it, cold | nothing | retrieving common knowledge wastes latency and risks distractors crowding out the model's own correct prior (56) |

The meta-rule: RAG earns its complexity when knowledge is *external*,
*large*, *changing*, and *citable*. Drop any of those properties and reconsider.

## The cost ladder
Each rung adds latency, cost, and operational surface — climb only when
measured retrieval failures justify it (45/47) [I]:

```
 rung 5  Multi-agent / graph+agent hybrids (25)      weeks of build; hardest to debug
 rung 4  Agentic / multi-hop loops (24, 26)          multiple LLM turns per query
 rung 3  Graph indexes (28/29), RAPTOR trees (20)    LLM-priced ingestion, slow reindex
 rung 2  Corrective/Self/Adaptive control (22/21/23) extra eval passes; routing logic
 rung 1  HyDE / multi-query / parent-child (17/16/18) +1 LLM call or index complexity
 ─────────────────────────────────────────────────────────────────────────────────
 rung 0  Hybrid + reranker + metadata filtering      the default; earned by default
         (13+14+12) + evaluation (45/46)
```

Rules of the ladder [I]:
1. **You must name the failure before climbing** — "recall@10 is 0.62 on the
   multi-hop slice and the failure mode is bridge questions" earns rung 3/4;
   "answers feel off" does not.
2. **Climbing is additive and reversible** — keep rung 0 intact underneath;
   every rung above should be toggleable per query (Adaptive-RAG is this
   principle industrialized [F: 2403.14403]).
3. **Re-measure after climbing** — a rung that doesn't move its justifying
   metric comes back off (56: agents and GraphRAG are the two most common
   unjustified climbs).
4. **Cost scales superlinearly with rungs** — more LLM calls per query, more
   ingestion LLM pricing, more failure surface; the economics pages (44,
   ../Platform-Economics/37-rag-economics.md) quantify each step.

## Key Takeaways
1. Choose by data shape and question shape, not by technique novelty: the tree
   routes on eight questions about your corpus and your queries.
2. The enterprise default is hybrid retrieval + reranker + metadata filtering
   (13+14+12) with evaluation wired in (45/46) — start there [I].
3. Structured data → SQL RAG; entity relationships and global themes → graph
   RAG; dependent lookups → multi-hop/agentic; exact tokens → hybrid [F:
   2404.16130 for the graph-question class].
4. Know the exits: small stable fact sets, exact lookups, and pure computation
   are better served by prompts, APIs, and tools than by retrieval.
5. The cost ladder is earned rung by rung — each climb must be justified by a
   measured retrieval failure and re-verified after the climb (45/47).

## Related
[55 types comparison matrix — the full design space](55-rag-types-comparison.md) ·
[47 failure modes — the evidence that justifies climbing](47-rag-failure-modes.md) ·
[45 evaluation — how you measure before and after](45-rag-evaluation.md) ·
[13 hybrid retrieval](13-hybrid-rag.md) · [14 reranking](14-reranking.md) ·
[12 metadata engineering](12-metadata-engineering.md) ·
`../Graph-Engineering/Knowledge-Graphs-and-GraphRAG.md`
