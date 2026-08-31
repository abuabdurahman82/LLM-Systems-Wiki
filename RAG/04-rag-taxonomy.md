# A Taxonomy of RAG — 25+ Types Without False Mutual Exclusion
`LAST_UPDATED: 2026-08-29` · Status: core page · Paper anchors (RAG, Self-RAG, CRAG, Adaptive-RAG, RAPTOR, GraphRAG, HyDE, the RAG survey) verified against fetched arXiv abstracts on 2026-08-29; every classification below is engineering inference [I], not a standard.

## 30-Second Explanation
"Agentic RAG," "Hybrid RAG," "Graph RAG" and friends are not 25 competing products you must
choose between. Most labels name a *property* of one pipeline — how it retrieves, what it
indexes, how control flows, what persists between turns — and one production system routinely
carries five or six of these labels at once. Read this page as a feature matrix, not a menu:
pick the properties that address your *measured* failure modes (47), then assemble them. Only
the Naive -> Advanced -> Modular progression (05) behaves like a maturity ladder; every other
axis is a design dimension with trade-offs, not a milestone.

## Why the labels collide: properties, not species
The literature names RAG variants after whichever property the paper happened to contribute.
That makes the names read like species when they are really attributes. Say it explicitly:

- **"Agentic" is a control-flow property** — *who decides when and what to retrieve*
  (a fixed pipeline vs an agent loop with tools). Orthogonal to what is indexed.
- **"Hybrid" is a retrieval property** — *how candidates are matched* (lexical + dense +
  other signals fused). Orthogonal to how control flows or where knowledge lives.
- **"Graph" is an index property** — *how the corpus is structured for retrieval*
  (flat chunks vs entities, relations, community summaries). Orthogonal to everything else.

A retrieval system can therefore be **Modular + Hybrid + Graph-indexed + Agentic +
Conversational + Memory-augmented** simultaneously, and many enterprise systems in 2025-26
are exactly that stack. Treating the labels as mutually exclusive causes two real errors:
picking "Graph RAG" when the measured failure was ranking (14), or bolting on agents (24)
when the failure was chunking (10).

```
              WHAT EACH LABEL ACTUALLY NAMES

  control flow          retrieval strategy        index structure
  (who decides,         (how candidates           (how knowledge is
   when to retrieve)     are matched)               structured)
       |                      |                          |
  Agentic RAG           Hybrid RAG                Graph RAG
  Self-RAG              Multimodal RAG            Hierarchical RAG
  Corrective RAG        SQL / Structured RAG      Recursive RAG (tree)
  Adaptive RAG          Web RAG                   Knowledge-Graph RAG
  Multi-Agent RAG       Federated RAG             Multi-Index RAG
  Multi-Hop RAG         Real-Time RAG
  Recursive RAG              |                          |
       |                 memory / state            pipeline maturity
       |                 (what persists)           (how many stages)
       |                      |                          |
       +------ overlap   Conversational RAG        Naive RAG
        (most types span    Memory-Augmented       Advanced RAG
         two columns)       RAG                    Modular RAG
```

Multi-Hop RAG sits in two columns on purpose: it is a control-flow pattern (hop controller)
built on a retrieval strategy (query decomposition). The same is true of Recursive RAG.

## The 25+ types in one line each
Grouped by the property they are usually named after. Links go to the deep-dive pages.

**Named after pipeline maturity** (05):
1. **Basic / Naive RAG** — single pass: embed query, top-k chunks, stuff prompt, generate (03).
2. **Advanced RAG** — the same single pass with added stages: query rewrite, hybrid retrieval,
   filtering, reranking, compression, verification.
3. **Modular RAG** — the pipeline rebuilt as interchangeable, routable modules; a router picks
   per query which retrievers and generators run.

**Named after a retrieval property**:
4. **Hybrid RAG** — lexical (BM25) + dense vectors fused (RRF or weighted); often + more signals.
5. **Multimodal RAG** — retrieval and generation across text, images, tables, audio (31).
6. **Structured-Data RAG** — natural-language question -> query against tables/DBs, not text (30).
7. **SQL RAG** — the structured case where the "retriever" is a SQL engine; exact rows, no similarity.
8. **Web RAG** — the corpus is the live web via search APIs; freshness and spam replace ACLs (34).
9. **Federated RAG** — fan a query out to several independent parties' indexes without
   centralizing their data; merge ranked lists under each party's policy.
10. **Real-Time / Streaming RAG** — evidence flows continuously (feeds, tickets, telemetry);
    incremental indexing and streamed answers (35). Named after a *source/index* property
    (live feed), not a matching strategy — the table's "continuous ingest" cell is shorthand
    for that.

**Named after an index property**:
11. **Graph RAG** — retrieval over a graph of entities/relations (often with community
    summaries) to answer corpus-global questions [F] (arXiv:2404.16130) (28).
12. **Knowledge-Graph RAG** — the strict version: a curated KG is the index; entity linking,
    path traversal, structured queries (29).
13. **Hierarchical RAG** — multi-level index (chunk -> section -> doc -> summary); retrieve
    coarse first, then drill down (19).
14. **Recursive RAG (index side)** — recursively embed/cluster/summarize into a tree, retrieve
    across abstraction levels (RAPTOR) [F: arXiv:2401.18059] (20). Distinct from the
    *retrieval-side* recursive variant (iterative loop over its own output — the "Recursive"
    row below): same name, two mechanisms.
15. **Multi-Index RAG** — several purpose-built indexes (per domain, per doc type, per
    embedding model) queried in parallel or sequence, then merged.

**Named after a control-flow property**:
16. **Agentic RAG** — an agent loop decides whether/what/where to retrieve; retrieval is a
    tool call among others (24).
17. **Self-RAG** — the generator itself decides when to retrieve and critiques its own drafts
    via learned reflection tokens [F: arXiv:2310.11511] (21).
18. **Corrective RAG (CRAG)** — a lightweight evaluator grades retrieval quality; on failure,
    correct the query or fall back to web search [F: arXiv:2401.15884] (22).
19. **Adaptive RAG** — route by predicted query complexity: no retrieval, single pass, or
    iterative multi-step [F: arXiv:2403.14403] (23).
20. **Multi-Hop RAG** — decompose the question into hops; each hop's result seeds the next
    retrieval until the evidence chain closes (26).
21. **Multi-Agent RAG** — specialized retrieval agents (per source or domain) coordinated by
    an orchestrator that merges their findings (25).

**Named after a memory/state property**:
22. **Conversational RAG** — carries session history; rewrites follow-ups ("Who created it?")
    into standalone queries ("Who created PagedAttention?") (32).
23. **Memory-Augmented RAG** — retrieves from persistent agent/user memory stores alongside
    the document corpus; two evidence pools in one context (33).

**Named after a source/breadth property**:
24. **Domain-Specific RAG** — every layer tuned for one domain (biomed, legal, code):
    vocabulary, chunking, embedding model, eval set (37).
25. **Long-Context RAG** — retrieve a few *large* units into a 100k+ window and reason over
    whole documents; trades ranking for reading (39).

**A few more you will meet** (property-flavored, no full row below): **parent-child RAG**
(small chunks retrieve, big parents generate, 18), **HyDE** (retrieve with a hypothetical
generated document) [F: arXiv:2212.10496] (17), **contextual retrieval** (prepend
chunk-specific context at indexing) (40), **code RAG** (AST/function-level units, 38).

## The 8-dimension classification table
One row per type; short cells. The dimensions are defined by the column headers; see the next
section for why several of them are orthogonal.

| Type | Retrieval strategy | Reasoning strategy | Knowledge source | Index type | Control flow | Memory | Validation | Generation pattern |
|---|---|---|---|---|---|---|---|---|
| Basic/Naive | dense top-k | single pass | private corpus | vector | fixed | none | none | one-shot cited |
| Advanced | hybrid | staged pipeline | private corpus | vector+lexical | fixed stages | none | rerank + verify | one-shot cited |
| Modular | routed per source | composition | corpus+DB+API+web | per-source mix | router | optional | per-module gates | composed answer |
| Hybrid | lexical+dense fused | single pass | private corpus | hybrid index | fixed | none | rerank | one-shot cited |
| Agentic | tool calls, on demand | plan-act-observe | any tool reachable | any | agent loop | task scratchpad | tool self-checks | multi-step |
| Graph | graph walk / community | synthesize over graph | corpus-derived graph | graph | fixed or agent | none | path provenance | cited synthesis |
| Self-RAG | model-gated, on demand | self-critique | private corpus | vector | reflection loop | none | self-critique tokens | reflection-gated |
| Corrective | retrieve, evaluate, fallback | corrective branch | corpus + web | vector + search | evaluator branch | none | retrieval evaluator | retry / requery |
| Adaptive | complexity-routed | route then retrieve | corpus (+ web) | any | complexity router | none | route-fit check | matched to complexity |
| Recursive | iterative retrieval loop | recursive refinement | corpus + summaries | tree/hybrid | loop until done | none | sufficiency check | iterative |
| Multi-Hop | decomposed hops | chain evidence | corpus | vector / KB | hop controller | scratchpad | hop coverage check | chain-of-evidence |
| Conversational | rewritten query | turn-local | private corpus | vector | fixed + rewriter | session | rerank | turn-wise |
| Memory-Augmented | dual corpus+memory | merge two evidences | corpus + memory store | vector + store | fixed / router | persistent | provenance labels | state-aware cited |
| Multimodal | cross-modal dense | single or agent pass | text+image+audio | multimodal index | fixed / agent | none | modality-fit check | cited, incl. images |
| Structured-Data | NL -> structured query | translate + execute | DBs / tables | relational | fixed | none | execute + validate rows | table-grounded |
| SQL RAG | text-to-SQL | translate + execute | relational DB | relational | fixed / agent | schema cache | execution result | table-grounded |
| Knowledge-Graph | entity link + path | traverse relations | curated KG | triple store | fixed / agent | entity cache | path validation | path-grounded |
| Web | search API + fetch | fetch-extract-read | live web | external index | fixed / agent | none | source-quality gate | cited URLs |
| Federated | fan-out query | merge ranked lists | N remote corpora | per-party | coordinator | none | per-party ACL | merged cited |
| Hierarchical | coarse-to-fine | navigate levels | corpus | tree/summary | staged | none | level-fit check | cited from level |
| Long-Context | few large units | whole-evidence read | corpus | vector (docs) | fixed | none | lost-middle handling | long-form synthesis |
| Domain-Specific | tuned per domain | domain pipeline | domain corpus | domain index | fixed / agent | domain rules | domain eval set | domain format |
| Multi-Index | parallel per-index | merge / dedupe | many corpora | N indexes | dispatcher | none | cross-index dedupe | merged cited |
| Multi-Agent | per-agent sources | coordinate / debate | partitioned corpora | per-agent | orchestrator | shared blackboard | agent cross-checks | negotiated answer |
| Real-Time/Streaming | continuous ingest | stream-aware | live feeds | incremental | event-driven | windowed | freshness checks | streamed tokens |

Reading examples: Agentic RAG is defined by columns 6 (control flow = agent loop)
and 3 (reasoning = plan-act-observe); its retrieval, source, and index columns are
"any" — that is the whole point. Hybrid RAG differs from Basic in the retrieval,
index, and validation columns (dense→fused, vector→hybrid, none→rerank).
Conversational and Memory-Augmented differ in nearly every column — memory
(session vs persistent) is the *defining* difference, not the only one.

## Which dimensions are orthogonal (and which correlate)
Independent dimensions — you can set them one at a time:
- **Index type** (vector / hybrid / graph / tree / relational / N indexes) is orthogonal to
  **control flow** (fixed / router / loop / orchestrator): any index works under any control.
- **Retrieval strategy** is *largely* orthogonal to **memory**: hybrid matching works
  identically in a stateless API and a chat session — but some strategies (query
  rewriting for coreference, item 22) only exist *because* there is session memory.
- **Validation** is nearly orthogonal: any pipeline can add an evaluator gate (45) — with
  the exception noted below (exact-query pipelines validate by execution, not a gate).
- **Knowledge source** correlates with *index type* but is not determined by it — a KG can be
  stored in a triple store *or* materialized as text chunks in a vector index.

Dimensions that correlate strongly (choosing one pulls the others):
- **Control flow = agent loop** practically implies **memory >= scratchpad** (the loop needs
  state) and pushes **generation** toward multi-step.
- **Retrieval = exact query (SQL/structured)** implies **validation = execute the query** —
  the executor is the ground truth, which similarity-based systems lack.
- **Source = live feed** implies **index = incremental** and freshness checks in validation.

## How to use the taxonomy: pick by problem, not by label
1. Start from the measured failure mode (47): retrieval miss, ranking noise, multi-source
   questions, multi-turn drift, staleness, cost.
2. Map failure to property: ranking noise -> hybrid + reranker (13, 14); multi-hop questions
   -> decomposition control flow (26); heterogeneous sources -> modular routing (05);
   conversation -> session memory + rewriting (32); staleness -> incremental/web (35, 34).
3. Stack properties deliberately: "hybrid retrieval + graph index + adaptive routing +
   provenance-labeled memory" is one coherent system, not four products. Cost is a property
   too: a stuffed 20-chunk context at ~512 tok/chunk is ~10,240 input tokens ≈ $0.031 of input
   per request at $3/1M [E: assumes ~512-token chunks; at 256-tok chunks ≈ $0.015, at 1,024-tok
   ≈ $0.061] before any generation, so stack only what a measured failure demands (41, 44).
4. Beware same-property synonyms: Graph RAG (28) vs Knowledge-Graph RAG (29) differ in how
   curated the graph is; Multi-Index vs Federated differ in *who owns* the indexes.
5. The decision tree (54) and comparison matrix (55) operationalize this page.

## Key Takeaways
1. Most RAG "types" are properties (retrieval / index / control flow / memory / maturity),
   not mutually exclusive species; one system usually combines five or six labels.
2. Agentic = control-flow property, Hybrid = retrieval property, Graph = index property.
3. Only Naive -> Advanced -> Modular (05) is a maturity ladder; the rest are design choices
   with trade-offs and no universal winner.
4. Classify by dimension when diagnosing: name which column is failing before adding modules.
5. Use the property matrix to compose; use measured failures (47) and the decision tree (54)
   to choose — never pick a label because it is fashionable.

## Related
[03 basic pipeline](03-basic-rag-pipeline.md) · [05 naive/advanced/modular](05-naive-advanced-modular-rag.md) ·
[21 Self-RAG](21-self-rag.md) · [23 Adaptive RAG](23-adaptive-rag.md) ·
[24 agentic RAG](24-agentic-rag.md) · [28 Graph RAG](28-graph-rag.md) ·
[54 decision tree](54-which-rag-should-i-use.md) · [55 comparison matrix](55-rag-types-comparison.md) ·
[47 failure modes](47-rag-failure-modes.md) · `../Graph-Engineering/Knowledge-Graphs-and-GraphRAG.md`
