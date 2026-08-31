# Hierarchical RAG — Indexing the Whole Structure

`LAST_UPDATED: 2026-08-29` · Status: core page · RAPTOR specifics in 20 (paper
verified in the research bank); structural patterns [I] elsewhere.

## 30-Second Explanation
Flat retrieval treats the corpus as a bag of chunks. **Hierarchical RAG**
indexes the corpus at *multiple levels of abstraction* — document, chapter,
section, paragraph, chunk — and routes the query down the structure: start
coarse (which document/section is this about?), then fine (which chunk
answers it?). The two motivations: (1) some questions are *about the whole*
("what are the main themes across these 200 incident reports?") and no
single chunk answers them — you need summaries that cover more than one
chunk; (2) routing coarse-to-fine is cheaper and more robust than one-shot
top-k on a 10M-chunk index [I: the two uses are distinct; "hierarchical RAG"
is the umbrella for both].

## The structure
```
Corpus
  Document
   ├── Chapter / big section (level 3)
   │    ├── Section (level 2)
   │    │    ├── Subsection / paragraph (level 1)
   │    │    │    ├── chunk (level 0)   ← embedded at every level
   │    │    │    └── chunk
   │    │    └── ...
   │    └── ...
   └── ...
```
Each level carries its own index: level-0 chunks (the leaf, what 03/10 build)
and levels 1–3 *summaries or representative vectors* of the level below.
RAPTOR (20) is the research archetype: recursively *cluster* the leaf
embeddings, *summarize each cluster* with an LLM, embed the summaries, and
repeat — building a tree where internal nodes are LLM-generated abstractions,
not just structural excerpts.

## The two usage patterns
**1. Routing (coarse-to-fine).** The query first retrieves at level 2
(sections), then only searches *within* the top-m sections' level-0 chunks.
```
query → ANN(level-2 summaries) → top-m sections
      → constrained ANN(level-0, within those sections) → top-k chunks
```
Benefits [I]: the fine-grained search is over a *subset* (smaller ANN,
higher effective recall per candidate), and the coarse pass is a cheap
pre-filter that catches "wrong part of the corpus" errors early. Cost: two
ANN passes + the maintenance of the intermediate indexes.

**2. Abstraction retrieval (the "whole-corpus" question).** For corpus-level
questions, the *summaries themselves* are the retrievable objects: retrieve
level-2/level-3 summaries (and their child chunks for detail) instead of any
single chunk. This is where RAPTOR-style tree retrieval and GraphRAG's
community summaries (28) meet: both say "the answer to 'what is this corpus
about' is not in one chunk, it is in a *summary of many chunks*" [I: the
shared insight; the implementations differ — RAPTOR is unsupervised
clustering+summarization, GraphRAG adds the entity/relation graph and
Leiden communities (28/29)].

## Building the hierarchy
| Level content | How it's made | Cost |
|---|---|---|
| Level 0 (chunks) | 10's chunking | parse + embed |
| Level 1 (paragraph/subsection summaries) | structural excerpt (first paragraphs + headings of the unit) **or** LLM summary | structural: free; LLM: one summarization call per unit + embed the summary |
| Level 2 (section summaries) | LLM summarization of level-1 units (RAPTOR: recursive) | the LLM pass dominates — for a 1M-chunk corpus, RAPTOR-style construction is a *major* ingestion budget line (44) |
| Level 3 / root (chapter, corpus summary) | LLM summarization of level-2 units | same; the tree is usually 2–3× the leaf index in text, less in vectors (summaries are short) [I] |

**RAPTOR-specific** [F: arXiv:2401.18059 — authors/venue/code confirmed in the
research bank; deep dive in 20]: recursive soft clustering (embedding
clustering with overlap so a chunk can sit in more than one cluster at a
level), LLM summary per cluster, repeat until one node. The tree is built
*offline*; retrieval walks the tree, sampling nodes at multiple levels and
packing them together. The paper's reported gains are primarily on
long-context / multi-document QA (QuALITY, NarrativeQA) [F: abstract; full
paper checked 2026-08-30] plus single-document results on a 20-story QASPER
subset [F: § of the paper] — i.e. the regime where flat retrieval is
structurally weak.

## Maintenance: the hierarchy is a liability in motion
- **Corpus changes**: a doc update invalidates its leaf chunks *and* every
  ancestor summary that covered it. Structural hierarchies (level-1 = excerpt)
  are cheap to rebuild; LLM-summarized levels are not [I: the standing
  maintenance argument — summary-level indexes lag the leaf index by
  construction].
- **Index versioning** (51): the hierarchy is part of the index artifact; a
  half-rebuilt tree is worse than no tree (routing through a stale summary
  points at deleted content).
- **When the hierarchy is wrong**: if the corpus has no real structure (flat
  logs, tickets), a forced hierarchy is *invented* structure — the summaries
  may be coherent but the routing gains evaporate. The structure must be the
  corpus's, not the index's [I].

## Hierarchical vs related patterns
| | Hierarchy (this page) | Parent-child (18) | RAPTOR (20) | GraphRAG (28) |
|---|---|---|---|---|
| Levels | 3–5, document structure | 2 (child/parent) | recursive, data-driven | entities/relations/communities |
| Internal nodes | structural excerpts or LLM summaries | none (the parent is the raw section) | LLM cluster summaries | entity nodes + community summaries |
| Query path | route down, or retrieve at the abstract level | retrieve child, return parent | sample the tree | graph traversal + vector |
| Build cost | low–high (summaries) | low | high (recursive LLM) | high (LLM extraction + communities) |
| Sweet spot | large structured corpora; "which section" routing | enterprise docs | corpus-level sensemaking | relational/corpus-level sensemaking |

## Key Takeaways
1. Hierarchical RAG indexes *abstraction levels*, not just chunks; some
   questions (corpus-level) are only answerable at the summary level.
2. Two distinct uses: coarse-to-fine *routing* (cheap pre-filter, subset
   search) and *abstraction retrieval* (summaries as retrievable objects).
3. RAPTOR (20) is the research archetype — recursive clustering + LLM
   summaries; its gains are on long-context/multi-document QA plus a
   single-document (QASPER-subset) result.
4. Summary-level indexes are a *maintenance liability*: every doc update
   invalidates ancestors; version the whole tree (51).
5. The structure must be the corpus's: forced hierarchies over flat corpora
   buy cost, not quality.

## Related
[03 pipeline](03-basic-rag-pipeline.md) · [10 chunking](10-chunking.md) ·
[18 parent-child](18-parent-child-rag.md) · [20 RAPTOR](20-raptor.md) ·
[28 graph RAG](28-graph-rag.md) · [29 KG RAG](29-knowledge-graph-rag.md) ·
[44 economics](44-rag-economics.md) · [51 production (index versioning)](51-production-rag-reference-architecture.md)
