# Naive, Advanced, and Modular RAG — The Three Stages of Maturity
`LAST_UPDATED: 2026-08-29` · Status: core page · The Naive/Advanced/Modular paradigm split
and arXiv:2312.10997 verified against the fetched paper abstract on 2026-08-29 [F]; the
maturity ladder interpretation and cost claims are engineering inference [I] plus bank
constants [E].

## 30-Second Explanation
The RAG survey literature (Gao et al., arXiv:2312.10997) popularized a three-paradigm
progression — Naive RAG, Advanced RAG, Modular RAG [F: arXiv:2312.10997] — and it survives
because it maps to how real systems actually grow: a single retrieve-stuff-generate loop,
then that same loop with quality stages bolted on, then the loop broken apart into routable
modules when sources, policies, and query types multiply. Each stage exists because the
previous one has a *measured* failure it cannot fix. "Naive" is not an insult: a working
naive pipeline beats a misconfigured advanced one, and the ladder is a diagnosis tool, not a
badge. This page defines the three stages, names the failure each stage buys off, and gives
the maturity table for locating your own system.

## Stage 1 — Naive RAG
The baseline pipeline of 03, unchanged. One retriever, one pass, no post-processing:
```
            NAIVE RAG (baseline; see 03)

  Query ──> [ Embed ] ──> [ Dense top-k ] ──> [ Stuff prompt ]
                                                │
                                     Answer <── [ LLM ]

  stages: 3 · control flow: fixed, one pass · validation: none
```
What it adds: nothing — it *is* the baseline (03). What it delivers: fast to build, cheap,
works surprisingly well on a clean, single-source corpus with well-phrased questions.
Failure modes it exposes (each names its fix page): semantic-mismatch on exact-token queries
(13), ANN order ≠ relevance order (14), 20 chunks stuffed where 5 would do (41), no idea
whether retrieval even hit (45), conversation follow-ups that break ("Who created it?" — 32).

## Stage 2 — Advanced RAG
Same single-pass skeleton; quality stages inserted before and after retrieval:
```
                     ADVANCED RAG

  Query ──> [ Query Rewrite ]                    (15, 32: coref, expand)
              │
              v
        [ Hybrid Retrieval ]                   (13: BM25 + dense, RRF)
              │
              v
        [ Filtering ]                          (12: metadata, ACLs, dedupe)
              │
              v
        [ Reranking ]                          (14: cross-encoder on top-100)
              │
              v
        [ Compression ]                        (41: prune/extract to budget)
              │
              v
        [ Generate ] ──> [ Verification ] ── grounded answer?
              │                     │no
              └── retry / requery <-┘      (45: faithfulness, citation check)
```
What each added stage buys, mapped to the failure it addresses:

| Added stage | Failure mode it addresses | Page |
|---|---|---|
| Query rewrite | coreference/underspecified queries retrieve nothing ("it", "that error") | 15, 32 |
| Hybrid retrieval | dense-only misses exact tokens: error codes, IDs, product SKUs | 13 |
| Filtering | wrong-tenant, stale, or duplicate chunks reach the prompt | 12, 49 |
| Reranking | ANN score order puts the best chunk at rank 7 | 14 |
| Compression | 4 useful chunks buried in 20 of noise; prefill cost [E] | 41 |
| Verification | plausible-but-ungrounded answers ship to users | 45, 47 |

The skeleton is still one pass on the happy path: one retrieval event, one generation
(the verification gate above may trigger a retry/requery, so the *actual* path can loop).
Multi-source questions,
mixed data types, and per-source policies do not fit, no matter how good the stages are.
That limit is what forces stage 3.

## Stage 3 — Modular RAG
The pipeline is dissolved into interchangeable modules with a router deciding, per query,
which ones run and in what order:
```
                       MODULAR RAG

                     ┌────────────┐
        Query ──────>│   Router   │──── intent? source? cost? complexity?
                     └─────┬──────┘
       ┌──────────┬────────┼─────────┬──────────┬──────────┐
       v          v        v         v          v          v
  [vector     [ SQL ]  [ graph ]  [ web ]  [ API/     [ memory ]
   search ]                          tools ]   store ]
       │          │        │         │          │          │
       └────┬─────┴────┬───┴────┬────┴─────┬────┴────┬─────┘
            v                                       │
   [ composition / reasoning ]  <── per-source results,
            │                              evidence + provenance
            v
        [ LLM ] ──> composed, cited answer
```
What it adds over Advanced: routing by intent and cost, per-source retrievers with per-source
policies, and a composition step that can merge evidence from a document index, a live SQL
query, a graph walk, and the web in one answer. Note the router can also decide to run
*none* of the retrievers — a chit-chat or arithmetic query should not pay retrieval tax [I].

## Why modular RAG is increasingly the enterprise default [I]
This is an engineering-consensus inference from what enterprise deployments must do, not a
measured adoption statistic:

1. **Heterogeneous sources are the norm.** The question "what is the refund policy for
   order #1234?" needs policy *documents*, order status from the *orders database*, and
   possibly today's *carrier API*. No single index holds all three; stage-2 hybrids assume
   one homogeneous corpus.
2. **Per-source policies and ACLs.** Documents, DBs, and web results carry different access
   rules, retention rules, and tenancy. Modular routing enforces authorization *at the
   source boundary* — security before evidence reaches the model (48, 49). Per-chunk ACL
   metadata *can* express tenant visibility on a merged index, but the source boundary is
   where enforcement is strongest: the disallowed chunk never enters retrieval/prefill at
   all.
3. **Routing saves cost.** Most queries are answerable by the cheap path (lexical search,
   cached answer, or no retrieval at all); only complex ones justify graph walks or agent
   loops (23). A router that sends 70% of traffic to the cheap retriever cuts blended cost
   toward ~70% under a linear model as the cheap path's own cost approaches zero [I: linear
   cost model, see 44].
4. **Composition handles multi-source answers.** When evidence comes from three systems,
   something must reconcile conflicts, dedupe, attach provenance per claim, and cite each
   source correctly. That is a composition/reasoning step, not a prompt stuffed with 20
   chunks from one index.

The trade-off: modularity adds moving parts — routing misfires, per-module evaluation burden,
operational surface (50). A single-source corpus with homogeneous traffic may genuinely be
better as a well-tuned stage-2 pipeline. Modular earns its complexity, it does not assume it.

## Provenance of the three-paradigm split
The Naive RAG / Advanced RAG / Modular RAG progression was popularized by the survey
"Retrieval-Augmented Generation for Large Language Models: A Survey" (Gao et al.,
arXiv:2312.10997), whose abstract states it "offers a detailed examination of the
progression of RAG paradigms, encompassing the Naive RAG, the Advanced RAG, and the Modular
RAG" [F: arXiv:2312.10997, abstract verified from fetched copy 2026-08-29]. House note (03):
the terms are survey vocabulary, not a standard — treat them as a maturity lens, not a
specification.

## Maturity table: when you are in each stage
| Signal in your system | Stage | First moves |
|---|---|---|
| One corpus, one embedding model, top-k stuffed into the prompt, no eval | Naive | build a golden eval set (46); measure recall@k + faithfulness (45) |
| You added hybrid or a reranker because ranking complaints were measured | Advanced (early) | add metadata filtering + ACLs (12) before more retrieval tricks |
| Retrieval quality is decent but answers still wrong on multi-part questions | Advanced (mid) | query transformation (15), compression (41), verification gate (45) |
| Questions span documents + DBs + APIs; a merged index keeps going stale | Modular | split per-source retrievers; add a router (23) and composition step |
| Per-team access rules differ by source; compliance asks "who saw what" | Modular | enforce ACLs at the source boundary (48, 49), provenance per claim |
| Bill is dominated by over-retrieval on trivial queries | Modular | route by complexity/cost (23); cache at every layer (42) |
| You are weighing agents/graphs but have no eval set | *not a stage issue* | stop; build 46 first — complexity must be earned (54) |

Cost note [E, from the constants bank @ $3/$15 per 1M in/out]: 10 chunks x 512 tok =
5,120 input tok ≈ $0.0154 input + 500 generated tok ≈ $0.0075 → ≈ $0.023/request; 50
chunks is ~5x the input cost (≈ $0.077 input ≈ $0.084/request total). Advanced-stage additions (rerank,
compression) buy quality per request; modular-stage routing is the lever that stops you
paying advanced-stage prices for queries that do not need them.

## Key Takeaways
1. Naive -> Advanced -> Modular is a maturity ladder, the one axis in this handbook that
   behaves like a progression rather than a design dimension (04).
2. Advanced RAG inserts quality stages into one pass — rewrite, hybrid, filter, rerank,
   compress, verify — each fixing a specific measured failure (13, 14, 41, 45).
3. Modular RAG replaces the fixed pipeline with routing + per-source retrievers +
   composition; heterogeneous sources, per-source ACLs, and cost routing are the drivers [I].
4. Modularity is the enterprise default for heterogeneous estates [I: engineering-consensus
   inference, not a measured adoption statistic], but a tuned stage-2 pipeline can be the
   right end state for a single homogeneous corpus — complexity earned.
5. Locate your stage by signals, not ambition: no eval set means you are not ready to leave
   Naive regardless of what modules you plan to bolt on (46).

## Related
[03 basic pipeline](03-basic-rag-pipeline.md) · [04 taxonomy](04-rag-taxonomy.md) ·
[13 hybrid retrieval](13-hybrid-rag.md) · [14 reranking](14-reranking.md) ·
[23 Adaptive RAG (routing)](23-adaptive-rag.md) · [41 compression](41-context-compression.md) ·
[45 evaluation](45-rag-evaluation.md) · `../Platform-Economics/37-rag-economics.md`
