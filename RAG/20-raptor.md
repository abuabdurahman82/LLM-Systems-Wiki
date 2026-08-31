# RAPTOR — Recursive Summarization as a Retrieval Tree

`LAST_UPDATED: 2026-08-29` · Status: core page · [F: arXiv:2401.18059 "RAPTOR:
Recursive Abstractive Processing for Tree-Organized Retrieval", ICLR 2024 —
title/ID/venue confirmed this pass against arXiv; author list deferred to the
research bank's final record (first authors per the paper's arXiv record)].
Code: github.com/parthsarthi03/raptor [F: official repo, "The official
implementation of RAPTOR" — verified via GitHub API 2026-08-30].

## 30-Second Explanation
Flat retrieval retrieves *chunks*; a corpus-level question ("what are the
main themes across these 500 incident reports?") has no answer in any single
chunk. **RAPTOR** builds a tree: recursively **cluster** the chunk
embeddings, **summarize** each cluster with an LLM, embed the summaries, and
repeat until one root. The result is a retrieval index with *multiple levels
of abstraction* — leaves are the original chunks, internal nodes are
LLM-generated summaries of their children. Retrieval samples from *multiple
levels at once* (a chunk and its section summary and its chapter summary in
one context), which is what makes corpus-level and long-context questions
answerable [F: the paper's core mechanism; verified against arXiv:2401.18059].

## The construction (precisely)
```
level 0:  [chunk] [chunk] [chunk] … [chunk]        (the corpus, embedded)
   ↓ soft-cluster the embeddings (each chunk may join more than one cluster)
level 1:  [summary of cluster A] [summary of cluster B] …   (LLM summaries, embedded)
   ↓ soft-cluster again
level 2:  [summary of cluster A'] [summary of cluster B'] …
   ↓
…
root:     [summary of the whole corpus]
```
Three design choices, each with a consequence [F: per the paper]:
1. **Soft clustering** (a chunk can belong to multiple clusters at a level):
   topics in real corpora overlap; hard partitioning would force a chunk into
   one "parent" and lose the others. Cost: some duplication up the tree.
2. **Summarization, not extraction**: the internal node is a *generated*
   abstraction (an LLM reads the cluster's chunks and writes the summary),
   not a picked excerpt. The summary can carry information no single chunk
   states verbatim (the cross-chunk synthesis the question requires).
3. **Recursive depth**: the process repeats until one node — the depth is
   data-dependent (RAPTOR's trees are typically ~5 levels for long
   documents/corpora [I: typical shape; the paper's figures show it]).

## The retrieval (how the tree is used)
At query time, RAPTOR does *not* walk the tree top-down (that would be the
hierarchical routing of 19). Instead it **samples**: retrieve at multiple
levels simultaneously (each level is its own ANN index over its nodes'
embeddings), take top-k candidates from several levels, and pack them
together — leaves for detail, mid-levels for section context, top-levels for
the "gist" [F: the multi-level sampling, per the paper]. The context that
reaches the LLM thus contains *both* the specific evidence and the
abstractions that frame it — the two failure classes (detail-without-context,
context-without-detail) are attacked in one pass.

Contrast with 19's routing variant (route coarse, then search fine within the
matched region): RAPTOR's sampling is *parallel across levels*; routing is
*sequential down the tree*. Both are "hierarchical RAG" (19's umbrella);
RAPTOR is the sampling instantiation with LLM-summaries as the internal
nodes.

## The paper's reported results (carefully)
[F: arXiv:2401.18059]: RAPTOR improves long-document QA and corpus-level
sensemaking over flat chunk-retrieval baselines, with the gains concentrated
in the *multi-hop and corpus-wide* question regimes — exactly where flat
retrieval is structurally weak (26's task class). The paper also reports the
costs: index construction is an LLM-heavy offline job (one summary call per
cluster per level — for a large corpus, order of *thousands* of LLM calls at
construction, 44's ingestion line item), and the tree's value depends on the
summarizer's quality (a weak summarizer propagates errors up the tree).

What the paper does **not** claim [I: the anti-overclaim discipline, 56's
"GraphRAG when relationships don't matter" neighbor]: RAPTOR is not a general
replacement for flat retrieval. For single-hop, well-phrased questions over a
well-chunked corpus, flat hybrid + rerank (13/14) is cheaper to build and
usually competitive — the tree pays its construction cost on the question
classes that need abstraction.

## Cost and maintenance (the honest engineering accounting) [I, bank-based]
- **Construction**: LLM summary calls = (clusters × levels). A 10K-chunk
  corpus at ~4 clusters/level × ~4 levels ≈ 16K summary calls — at a
  few-hundred-token-in/100-token-out shape, that is a *substantial* one-time
  LLM bill (44: order of the contextual-retrieval line item, ~$10³ scale,
  depending on model/pricing [E: the bank's per-M pricing applies]).
- **Storage**: the tree adds text (summaries) + vectors at every level;
  roughly 2–3× the leaf index in *text*, less in vectors (summaries are
  short) [I].
- **Updates**: a chunk change invalidates its ancestors (19's maintenance
  argument, sharpest here — the summaries are *generated*, so touching one
  chunk means regenerating its cluster's summary and everything above).
  Practical systems rebuild levels in batches, pinned by index version (51).
- **Query cost**: multi-level sampling = several ANN calls + a larger packed
  context (the abstraction levels add tokens) — the per-query cost is above
  flat retrieval's.

## Failure modes
1. **Summarizer error propagation**: a wrong summary at level 1 frames every
   retrieval that samples that level; the error is *in the index*, not in one
   answer (47: ingestion-layer failure, made structural). Mitigation:
   summarize with a strong model; spot-check summary faithfulness at build
   (an ingest-audit variant, 11).
2. **Over-abstraction**: too much recursion buries the detail — the top
   levels become "the corpus is about X" platitudes that retrieve for
   everything and answer nothing (the 10 dilution problem, at the
   corpus level). The depth is a tunable with the same trade-off as chunk
   size.
3. **Soft-clustering duplication**: duplicated content across clusters →
   duplicated summaries → redundant context (41's dedup problem, one level up).
4. **Stale abstractions**: after corpus updates, the summaries describe the
   *old* corpus — the version discipline (12/51) must cover internal nodes,
   not just leaves.
5. **The "flat is enough" regime**: applying RAPTOR to a corpus whose
   questions are all single-hop pays the construction bill for a capability
   the task never uses (54's cost-ladder argument, made concrete).

## Key Takeaways
1. RAPTOR = recursive clustering + LLM summarization → a retrieval tree with
   abstraction levels [F: arXiv:2401.18059, ICLR 2024].
2. Retrieval samples *across levels* (detail + framing in one context) — the
   mechanism that answers corpus-level and multi-hop questions (26).
3. It is the *abstraction-retrieval* branch of hierarchical RAG (19);
   routing is the other branch; the patterns compose.
4. The cost is construction-time LLM bill + update invalidation + query-time
   multi-level sampling — earned only on the question classes that need
   abstraction.
5. Summarizer quality is a *structural* quality factor: errors propagate up
   the tree into the index itself.

## Related
[19 hierarchical](19-hierarchical-rag.md) · [18 parent-child](18-parent-child-rag.md) ·
[28 graph RAG (the sibling abstraction approach)](28-graph-rag.md) ·
[26 multi-hop](26-multi-hop-rag.md) · [44 economics](44-rag-economics.md) ·
[10 chunking](10-chunking.md) · `../Graph-Engineering/Knowledge-Graphs-and-GraphRAG.md`
