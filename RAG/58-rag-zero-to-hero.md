# Zero to Hero — Ten Levels of RAG Competence

`LAST_UPDATED: 2026-08-29` · Status: core page · Curated learning path mapped to the
section's pages; level definitions are editorial framing [I], page links are the
section's verified content.

## 30-Second Explanation
RAG competence is not "used a vector database once" — it is a ladder from *what a
corpus is* to *running a secure, evaluated, cost-bounded production system*. This
page defines eleven levels (0–10), each with the concepts to know, one hands-on
milestone that proves you can do it, and the section pages that teach it. Work the
milestones, not just the reading: each level's self-test tells you whether you are
ready to climb.

## The ladder

```
L0  documents, search, LLMs ............ what problem are we solving
L1  embeddings + basic RAG ............. the naive pipeline works
L2  chunking, metadata, BM25 ........... the units and fields of retrieval
L3  hybrid search + reranking .......... the workhorse production stack
L4  query transformation, HyDE ......... fix the query, not the index
L5  hierarchical / recursive / multi-hop  retrieval with structure and loops
L6  Graph RAG, knowledge graphs ........ retrieval over relationships
L7  Self / Corrective / Adaptive ....... retrieval that judges itself
L8  agentic + multi-agent RAG .......... retrieval as a tool under policy
L9  multimodal, structured, federated .. beyond plain-text single-source
L10 production: architecture, eval, security, economics ............ ship it
```

## LEVEL 0: Documents, search, LLMs
**Concepts to know.** What a corpus is (the document collection you will index);
how web search works at a high level (crawl → index → rank → results — retrieval is
an old, solved-ish discipline you are extending); what an LLM can and cannot know:
it knows only its training snapshot, cannot cite it, and cannot see your private
data (01).
**Hands-on milestone.** Take ten documents, write three questions per document by
hand, and try to answer them with a plain chatbot — record exactly where it fails
(stale facts, missing private data, no provenance). That failure list is your
requirements document.
**Read:** 01-why-rag-exists.md · 02-rag-history.md (background)
**You know this when:** you can explain why retraining is not the default answer to
"the model doesn't know our docs," and can name the three properties retrieval
gives that weights cannot: freshness, provenance, deletion.

## LEVEL 1: Embeddings, vector search, basic RAG
**Concepts to know.** Embeddings map text to vectors so "similar meaning" becomes
"nearby point"; vector search returns nearest neighbors; basic RAG = chunk → embed
→ index → embed query → top-k → prompt → LLM (03, 07, 08).
**Hands-on milestone.** Build the naive pipeline over ~100 documents with an
off-the-shelf embedding model and no reranker; get real answers with citations for
at least half your test questions, and note every failure.
**Read:** 07-embedding-engineering.md · 08-vector-search.md · 03-basic-rag-pipeline.md
**You know this when:** you can explain cosine similarity to a colleague, build the
pipeline from scratch in an afternoon, and can name what it misses (exact terms,
multi-part questions, document structure).

## LEVEL 2: Chunking, metadata, BM25
**Concepts to know.** The chunk is the retrieval unit — size and boundaries are a
design decision (10); metadata (source, date, section, ACL, version) is what makes
enterprise scoping possible (12); BM25 is the lexical scoring baseline every dense
method is compared against (06).
**Hands-on milestone.** Take your Level-1 index and (a) implement two chunking
strategies and measure recall@10 for both, (b) attach metadata and add one filter
(e.g., only current-version docs), (c) add a BM25 baseline over the same chunks.
**Read:** 10-chunking.md · 12-metadata-engineering.md · 06-information-retrieval-foundations.md
**You know this when:** you can defend a chunk size with a measurement instead of a
blog post, and your retrieval can already say "only documents this user may see."

## LEVEL 3: Hybrid search, reranking
**Concepts to know.** Hybrid retrieval fuses lexical and dense candidate lists (13);
a cross-encoder reranker reorders a small candidate set so prompt slots go to the
best evidence (14) — recall stage and precision stage are different jobs.
**Hands-on milestone.** Add hybrid retrieval (e.g., RRF fusion) plus a reranker to
your Level-2 system; produce one before/after table with recall@k, MRR, and
end-to-end answer quality on your test set.
**Read:** 13-hybrid-rag.md · 14-reranking.md
**You know this when:** you can explain in one sentence what the retriever optimizes
versus what the reranker optimizes, and your before/after table shows which queries
each stage fixed.

## LEVEL 4: Query transformation, multi-query, HyDE
**Concepts to know.** The user's raw query is usually a bad search query (15);
multi-query RAG generates several query variants to broaden recall (16); HyDE
retrieves against a hypothetical answer document instead of the question (17).
**Hands-on milestone.** Take the ten queries your Level-3 stack fails on; apply
rewriting, multi-query, and HyDE; record which technique recovers which failure and
what latency each adds.
**Read:** 15-query-transformation.md · 16-multi-query-rag.md · 17-hyde.md
**You know this when:** you reach for query transformation as the *first* fix for
recall problems — before touching k, the embedder, or the architecture.

## LEVEL 5: Hierarchical / Recursive / Multi-Hop RAG
**Concepts to know.** Hierarchical RAG retrieves over summaries and sections, not
just flat chunks (19); recursive RAG iterates retrieval as a loop (27); multi-hop
questions chain evidence where hop one defines hop two (26); RAPTOR-style trees
organize corpus structure explicitly (20).
**Hands-on milestone.** Implement one multi-hop path on questions your one-shot
system fails (e.g., decompose → retrieve → reformulate → retrieve → answer) and
quantify the recall gain on the multi-hop subset.
**Read:** 19-hierarchical-rag.md · 27-recursive-rag.md · 26-multi-hop-rag.md · 20-raptor.md
**You know this when:** you can classify any question by hop count and explain why
one-shot retrieval structurally cannot serve a two-hop question.

## LEVEL 6: Graph RAG, knowledge graphs
**Concepts to know.** When answers depend on relationships between entities, an
explicit graph is a better retrieval substrate than pairwise similarity (28, 29);
GraphRAG trades extraction and maintenance cost for structure-aware retrieval —
the category and its lineage are covered deeply in
../Graph-Engineering/Knowledge-Graphs-and-GraphRAG.md.
**Hands-on milestone.** Extract entities/relations for one bounded subdomain, answer
five relationship questions ("who is affected by X?") both by vector search and by
graph traversal, and compare correctness and cost.
**Read:** 28-graph-rag.md · 29-knowledge-graph-rag.md
**You know this when:** you can name the query classes where a graph beats vector
search — and the maintenance bill that justifies it only for those classes [I].

## LEVEL 7: Self / Corrective / Adaptive RAG
**Concepts to know.** Self-RAG makes the model critique whether retrieved evidence
supports generation (21); Corrective RAG detects bad retrieval and triggers a fix
(web search, re-query) (22); Adaptive RAG chooses the retrieval strategy per query
difficulty (23) — retrieval acquires judgment.
**Hands-on milestone.** Add one gate to your pipeline: an evidence-relevance check
that routes weak retrievals to a corrective action; measure precision gain against
the added latency and cost.
**Read:** 21-self-rag.md · 22-corrective-rag.md · 23-adaptive-rag.md
**You know this when:** your system can *detect* that its own retrieval failed, and
you know the measured rate at which that detection is right [I].

## LEVEL 8: Agentic and Multi-Agent RAG
**Concepts to know.** Agentic RAG treats retrieval as a tool the model decides to
call, with planning and stopping criteria (24); multi-agent RAG splits roles
(planner, searcher, verifier) across cooperating agents (25); agent loop mechanics
live in ../Agents/Agent-Loops-and-Reasoning-Strategies.md.
**Hands-on milestone.** Wrap your retriever as a tool and let an agent decide when
and what to retrieve on a task set where the fixed pipeline underperforms; compare
quality, latency, and token cost against Level-5's loop.
**Read:** 24-agentic-rag.md · 25-multi-agent-rag.md
**You know this when:** you can state, with numbers, when agency pays for itself —
and when a static pipeline is the better engineering answer [I].

## LEVEL 9: Multimodal / Structured / Federated RAG
**Concepts to know.** Corpora are not only text: images, tables, and audio need
multimodal retrieval (31); databases and spreadsheets need structured-data access
with exact semantics (30); no single index holds everything — federated RAG routes
and merges across sources (36); conversational state (32), memory (33), the live
web (34), real-time streams (35) extend the source model.
**Hands-on milestone.** Extend your system to two source types at once — e.g., a
document index plus one SQL table — with routing that picks the right source per
query and merges results into one citation list.
**Read:** 31-multimodal-rag.md · 30-structured-data-rag.md · 36-federated-rag.md ·
33-memory-rag.md · 34-web-rag.md · 35-realtime-rag.md
**You know this when:** you can design source routing for a mixed corpus and
articulate why a table lookup must not be "embedded and vector-searched" [I].

## LEVEL 10: Production RAG architecture, evaluation, security, economics
**Concepts to know.** The reference architecture: ingestion, retrieval, packing,
generation, feedback (51); evaluation as a two-layer discipline (45, and
../Evaluation-Engineering/RAG-Evaluation.md); security and tenancy as retrieval-time
concerns (48, 49); per-request economics — every chunk is prefill cost (44).
**Hands-on milestone.** Take any system you built above and add: a golden dataset
with regression runs (46), retrieval+generation metric dashboards, ACL-enforced
retrieval for two roles, and a documented per-request cost at your production k.
**Read:** 51-production-rag-reference-architecture.md · 45-rag-evaluation.md ·
48-rag-security.md · 49-multi-tenant-rag.md · 44-rag-economics.md · 50-rag-observability.md
**You know this when:** you can defend the system's quality, security posture, and
per-request cost with dashboards a non-author can audit — the definition of
production [I].

## Suggested order
Levels are mostly sequential — each level's milestone assumes the previous one's
artifacts (the same growing project is the fastest path). Two exceptions [I]:
**Level 9 can be entered from Level 3** (a working hybrid+rerank stack is enough to
add structured and multimodal sources), and Level 0–1 can be compressed by readers
who already ship LLM features. Whatever the order, do not skip Level 2 or Level 10:
chunking/metadata and evaluation/security are where production quality actually
lives (57).

## Key Takeaways
1. Competence is demonstrated by milestones on one growing project, not by pages read.
2. Levels 1–4 (embed → chunk/metadata → hybrid+rerank → query transformation) cover the 80% of everyday RAG work (57).
3. Levels 5–8 add structure and judgment — each must be justified by measured failures of the simpler stack (54).
4. Level 9 widens the source model; it can be entered early from Level 3.
5. Level 10 is not optional: architecture, evaluation, security, and economics are what make a RAG system production rather than a demo (51, 45, 48, 44).

## Related
- The principles this ladder teaches: 57-rag-80-20.md
- Start here for foundations: 01-why-rag-exists.md · 03-basic-rag-pipeline.md
- Choose-your-architecture companion: 54-which-rag-should-i-use.md · 55-rag-types-comparison.md
- Hands-on labs and experiment matrix: 53-rag-labs.md
- Adjacent sections: ../Context-Engineering/Context-Budget.md · ../Agents/Tool-Use.md · ../Evaluation-Engineering/RAG-Evaluation.md · ../Learning-Path/80-20-LLM-Guide.md
