# Contextual Retrieval — Fixing the Query-Doc Gap at Index Time

`LAST_UPDATED: 2026-08-30` · Status: core page · The Anthropic "Introducing
Contextual Retrieval" post (Sep 19, 2024,
anthropic.com/news/contextual-retrieval) is the public origin of the name
[F: post fetched and verified 2026-08-30]; mechanism claims [I].

## 30-Second Explanation
The deepest mismatch in RAG is between *how the question is phrased* and
*how the evidence is phrased* — and most chunks are phrased for **readers who
already know the document**, not for a retriever meeting them cold. A chunk
that says "The throughput increased by 27%" is *unretrievable*: it has no
subject ("throughput of what? in which experiment?"). **Contextual retrieval**
attacks the gap at *index time*: every chunk is augmented with LLM-generated
context ("In the vLLM speculative-decoding experiment (§4.2), the 7B model's
throughput increased by 27% vs the baseline…"), and the *contextualized* chunk
is embedded and indexed. The retriever finally sees the chunk the way a
searcher would phrase it.

## The problem, precisely
The failure class is **self-reference without referent** [I: the 10 "head
coverage" property, as a retrieval failure]:
- Pronouns: "it", "the model", "we" — the antecedent is in another chunk.
- Ellipsis: "The throughput increased by 27%" — no subject, no conditions.
- Section-relative: "As noted above, the failure rate halved" — "above" is
  3 chunks back.
- Jargon without definition in-chunk: domain terms assume the reader's context
  (37).
The embedding of such a chunk is a *directionless average* — it sits between
the topics it touches and matches weakly to all of them (10's dilution, at the
single-chunk level). Query-time fixes (15/16/17) enrich the *question*; this
enriches the *answer-side* — and it is done once, offline, so the query path
pays nothing for it.

## The two ingredients (each separable)
**1. Contextual chunk description (CCD).** For each chunk: the LLM sees the
**full document** (with the chunk marked in place) plus the chunk, and writes
a short, succinct description situating the chunk within the overall document
[F: the post's prompt — it supplies `{{WHOLE_DOCUMENT}}` + `{{CHUNK_CONTENT}}`,
verified against the post text 2026-08-30; this is also what makes the
prompt-caching economics below work]. The chunk text is
*preserved* (citations must point at the original, not the description); the
description is *prepended* for embedding.

**2. Contextual embedding (CCE).** The embedding is computed over
`description + original chunk` instead of the bare chunk. This is what makes
the retrieval improve — the description moves the chunk's embedding into the
region where *questions about it* live. (You can run CCD without CCE — the
description is also useful at pack time, as context for the LLM — but all
published gains include CCE; the description's standalone contribution was not
measured in the post.)

**Optional third: contextual BM25.** The description's words are also indexed
for the lexical side (13) — the description typically adds the exact terms a
question would use ("vLLM", "speculative decoding", "throughput"), which
strengthens the sparse half of hybrid [I: the post's hybrid configuration].

## The pipeline (where it fits)
```
INGESTION (offline):
document → chunk (10) → [CCD: LLM generates per-chunk description]
                         → embed(description + chunk)  [CCE]
                         → index vectors + BM25 over description+chunk
QUERY (unchanged):
query → hybrid (13) → rerank (14) → pack → LLM
```
The query path is *structurally identical* to 03/13 — contextual retrieval
changes only what was stored. That is its production appeal: no new runtime
complexity, no new latency; the entire cost moves to ingestion.

## The quality gain (as published) [F: Anthropic post, Sep 19 2024 — top-20
retrieval failure rates on their test corpora]
- **Contextual embeddings alone: −35%** failure (5.7% → 3.7%).
- **Contextual embeddings + contextual BM25: −49%** (5.7% → 2.9%).
- **+ reranking on top of that: −67%** (5.7% → 1.9%).
These are *failure-rate* reductions on retrieval@20, not answer-quality
numbers [I: the step from retrieval to answer is not measured there].

## The cost side (the honest accounting)
- **The one-time LLM pass**: with Claude 3 Haiku, the full-document prompt
  (the chunk's parent document is the reused cached prefix across that
  document's chunks — prompt caching is what makes the figure cheap), the
  one-time cost to generate contextualized chunks is **$1.02 per
  million document tokens** [F: the post's headline figure, Sep 19 2024 —
  recompute at your model's per-M pricing *with the caching assumption*;
  without it the number is materially higher]. The description
  is ~50–100 tokens per chunk; this is a corpus-version line item (paid once,
  re-earned per reindex on churning corpora, 35).
- **The embed pass is unchanged** (same chunk count; the description adds
  ~50–100 tokens of input per chunk — negligible against embedding cost).
- **Storage grows modestly**: the description is stored alongside the chunk
  (a few hundred bytes each); the vector count is unchanged.
- **The LLM pass dominates** the one-time bill; the post's figure is
  Haiku-priced. Re-computing it at your model's per-M pricing is the
  production number [I: scale it, don't re-measure it].

## Quality: what it buys, and what it doesn't
Buys [I: the mechanism, consistent with the post's reported direction]:
- **Paraphrase coverage**: the description is written to situate the chunk in
  retrieval terms (the post asks for "a short succinct context to situate this
  chunk"), so the chunk embeds closer to where questions embed — the direct
  attack on the query-doc phrasing gap [I: question-style phrasing specifically
  is not claimed by the post].
- **Head coverage**: "it" gets an antecedent *in the stored text* — 10's
  self-sufficiency property, enforced at index time.
- **Hybrid synergy**: the description's exact terms strengthen the lexical
  half (13).
Does *not* buy:
- **Facts absent from both the chunk and its document context** —
  contextualization repackages what the document says, it does not infer new
  content; a chunk whose document lacks the answer stays unanswerable (47).
  (It *does* routinely surface facts the bare chunk lacked — the document
  context supplies them: "the §4.2 experiment" is a fact the chunk itself did
  not state.)
- **Staleness** — the description is as fresh as its chunk version (12's
  versioning discipline applies to descriptions too).
- **A replacement for chunking quality** — a chunk that mixes two topics gets
  a description that hedges between them; the 10 problem remains.

## Interaction with the other query-side patterns
- **HyDE (17)** is the query-time twin: HyDE embeds a *hypothetical answer*,
  contextual retrieval embeds a *described chunk*; both close the same gap
  from opposite sides, and they compose (a HyDE query searches contextualized
  chunks) [I: the composition is sound — both operate on the embedding space;
  measure the combined effect on your set (46)].
- **Parent-child (18)** supplies the "surrounding paragraphs" that CCD uses as
  context — the patterns share the document-structure substrate.
- **Compression (41)**: the description is *metadata for retrieval*, not
  context for the answer — pack the original chunk (plus, optionally, a short
  description header), not the full CCD text.

## Key Takeaways
1. Contextual retrieval fixes the query-doc phrasing gap at *index time*:
   LLM-generated per-chunk description, embedded with the chunk.
2. The query path is unchanged — all cost moves to ingestion (one-time,
   per corpus version; $1.02 per M document tokens at the post's Haiku
   pricing [F]).
3. It composes with hybrid (descriptions add the exact terms the sparse half
   wants) and with HyDE (same gap, opposite side).
4. It is rephrasing, not inference — it cannot create facts the chunk lacks,
   and it does not fix bad chunking.
5. Stable corpora amortize the LLM bill over every query; churning corpora
   must re-earn it per reindex — the adoption test is corpus churn, not just
  quality.

## Related
[10 chunking](10-chunking.md) · [13 hybrid](13-hybrid-rag.md) · [15 query
transformation](15-query-transformation.md) · [17 HyDE](17-hyde.md) ·
[41 compression](41-context-compression.md) · [44 economics](44-rag-economics.md) ·
[46 golden datasets](46-rag-golden-datasets.md)
