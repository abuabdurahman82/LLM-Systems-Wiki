# HyDE — Retrieving with a Hypothetical Answer

`LAST_UPDATED: 2026-08-30` · Status: core page · [F: arXiv:2212.10496
"Precise Zero-Shot Dense Retrieval without Relevance Labels" — Luyu Gao,
Xueguang Ma, Jimmy Lin, Jamie Callan; venue **ACL 2023** (Anthology
2023.acl-long.99), confirmed 2026-08-30. The "HyDE" name is this paper's
method (it is not the Distractor paper).]

## 30-Short Explanation
Questions and answers live in *different regions* of embedding space: "How do
I reduce KV cache pressure?" and "PagedAttention reduces KV waste by
allocating blocks on demand" embed poorly aligned, especially for
off-the-shelf / zero-shot encoders — contrastively trained dense retrievers
deliberately pull query–positive pairs together, so the gap is a training
property, not a geometry of language [F: the paper's zero-shot framing].
*answers* the question. **HyDE (Hypothetical Document Embeddings)** flips the
query: use an LLM to write a *hypothetical answer* to the question, and
retrieve with the embedding of *that* text instead of the question's.
Retrieval now matches answer-to-answer, where the geometry works. No
relevance labels needed — which is why it is a *zero-shot* technique.

## The mechanism
```
question: "How does PagedAttention reduce KV cache waste?"
   ↓ LLM (zero-shot, no corpus access, no labels)
hypothetical answer: "PagedAttention reduces KV cache waste by managing
   the cache in fixed-size blocks, allocating memory on demand and
   decoupling logical KV blocks from physical memory, cutting waste from
   60–80% to ~4%…"            (may be factually imperfect — that's fine)
   ↓ embed the hypothetical answer (same embedding model as the corpus)
   ↓ ANN over the corpus
   ↓ top-k documents (retrieved by answer↔document similarity)
   ↓ pack + LLM (the *question* is still what gets asked — only retrieval used the hypothesis)
```

Why it works [I: the geometry argument, consistent with the paper's
findings]: (a) the answer region of the embedding space is exactly where the
corpus documents live (documents *are* answers to some question); (b) a
hypothetical answer carries the *terms and structure* the real answer has
(even if the specific facts are wrong) — the lexical/semantic overlap is
about the *topic shape*, not the content; (c) it is zero-shot: no corpus, no
labels, no training — one LLM call at query time.

The paper's reported result [F: arXiv:2212.10496]: on MS MARCO and NQ
zero-shot retrieval, HyDE improves dense retrieval over embedding the
question directly, with gains largest when the question phrasing is far from
the document phrasing (the paraphrase gap) — and it works with the retriever
unmodified (the technique is entirely on the query side).

## When HyDE helps (and when it hurts)
**Helps** [I: from the mechanism]:
- **Paraphrase-heavy corpora** where question phrasing ≠ document phrasing
  (the gap 40 also attacks, from the other side).
- **Long-tail / novel questions** the embedding model under-covers.
- **As one branch of multi-query** (16): q_hyde + q_original retrieved in
  parallel, merged — the hypothesis's error is hedged by the original query's
  correctness.
**Hurts / fails** [I: the named failure modes]:
- **The hypothesis is confidently wrong in a *different* region**: the LLM
  writes a plausible-but-misleading answer (wrong mechanism, wrong
  entities) → retrieval goes to the *wrong neighborhood*, and worse than
  embedding the original question. Mitigation: merge with the original-query
  retrieval (16), and let the reranker (14) arbitrate — the reranker sees
  (real query, chunk), not (hypothesis, chunk), so it can reject
  hypothesis-attracted candidates.
- **Exact-token questions** (13's regime): "what does E0x1F mean?" — the
  hypothetical answer is unlikely to contain "E0x1F" verbatim; the sparse
  half is unaffected, the dense half is actively misled. Run HyDE *alongside*
  hybrid, not instead of it.
- **Cost/latency**: one extra LLM call per query (a generation, not a
  classification — order of a short answer, 44) on the *critical path*; at
  high QPS the break-even requires the recall gain to be real on *your* set
  (46).

## Design notes
1. **The hypothetical answer is discarded after retrieval** — it never enters
   the packed context (its possible inaccuracy would contaminate generation);
   only the retrieved chunks do. The *question* is still the prompt to the
   generator.
2. **Constrain the hypothesis** [I: the standard recipe]: instruct the LLM to
   write a *factual-sounding paragraph in the corpus's register*, "as if the
   document existed", without caveats/hedging (hedging words ("maybe",
   "probably") pull the embedding toward uncertainty, not toward the answer
   region).
3. **Length**: a paragraph (2–6 sentences), not a one-liner (too little
   signal) and not a page (drift). The paper's formulation is
   document-length-ish; production practice is shorter [I: tune on your set].
4. **Model choice**: the hypothesis generator must be strong enough that the
   hypothetical answer embeds *closer to real answer documents than the raw
   question embedding does*; below that bar, HyDE underperforms plain query
   embedding [I: the failure the ablation in 53 lab 10 checks].
5. **Composes with** (I): hybrid (the dense half uses the hypothesis, the
   lexical half uses the original — both halves stay honest), multi-query
   (one of the N queries *is* the HyDE query), contextual retrieval (40:
   complementary, not the same mechanism — HyDE fixes the *query side*
   (query↔doc phrasing asymmetry); contextual retrieval fixes the *doc side*
   (context-starved chunks). Both improve retrieval, but they attack different
   failure modes; use together when you have both problems).

## Key Takeaways
1. HyDE retrieves with an LLM-written *hypothetical answer* instead of the
   question — matching answer-to-answer where embedding geometry works.
2. Zero-shot by construction: no corpus access, no labels, one LLM call at
   query time [F: the HyDE paper, arXiv:2212.10496, ACL 2023 (Gao, Ma, Lin,
Callan)].
3. The hypothesis is discarded after retrieval — it must not reach the
   generator; the reranker sees the real query and can reject
   hypothesis-attracted candidates.
4. It fails when the hypothesis is confidently wrong in a different region —
   merge with original-query retrieval and let the rerank arbitrate.
5. Exact-token queries are its blind spot (13); run it alongside hybrid, not
   instead.

## Related
[15 query transformation](15-query-transformation.md) ·
[16 multi-query](16-multi-query-rag.md) · [13 hybrid](13-hybrid-rag.md) ·
[14 reranking](14-reranking.md) · [40 contextual retrieval](40-contextual-retrieval.md) ·
[46 golden datasets](46-rag-golden-datasets.md)
