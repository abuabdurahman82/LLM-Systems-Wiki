# Multi-Query RAG — Retrieval as a Set, Not a Point

`LAST_UPDATED: 2026-08-29` · Status: core page · Cost math from the constants
bank; pattern claims [I].

## 30-Second Explanation
A single query is a *point probe* into the corpus: it retrieves what is
similar to that one phrasing. **Multi-query retrieval** turns the probe into a
*set*: the LLM generates N distinct queries for the same question (different
phrasings, aspects, perspectives), each retrieves independently, and the
results are merged, deduplicated, reranked, and packed. The bet: the union of
N neighborhoods is a better approximation of "everything relevant" than any
one neighborhood [I: the standard motivation — recall gain; the cost and
failure analysis below is the reason it is a tool, not a default].

## The pipeline
```
original question
   ↓ LLM: "generate N different queries that together cover this question"
   ↓ q1, q2, …, qN   (N = 2–5 typical; the recommended shape below is 3–5)
   ↓ parallel retrieval (each q_i → its own top-k_i, usually the same k_i)
   ↓ merge (union of candidate sets; a chunk hit by several q_i gets credit)
   ↓ deduplicate (identical/near-identical chunks; keep the best-scoring copy, 41)
   ↓ rerank (one cross-encoder over the merged set, 14)
   ↓ pack top-k final
   ↓ generate
```

## What the recall gain actually is
The mechanism [I]: different queries hit different *phrasing regions* of the
corpus. "Why is inference slow?" hits performance docs; "how to speed up
tokens per second" hits optimization docs; "inference latency troubleshooting"
hits runbooks. One query retrieves one region; N queries retrieve the union.
The gain is largest for:
- **Ambiguous/broad questions** (the question covers several sub-topics)
- **Lexically heterogeneous corpora** (the same fact is phrased differently in
  different docs — a support KB written by many authors)
- **Long-tail queries** (the one exact phrasing in the corpus may not be the
  user's phrasing)
The gain is *smallest* for precise, well-phrased queries over homogeneous
corpora — where a single good retriever + reranker is already near the
ceiling [I: the reason multi-query is a pattern you earn with a golden set
(46), not a default you buy].

## The costs (all of them, itemized)
| Cost | Scale | Notes |
|---|---|---|
| LLM generation of N queries | 1 LLM call (shared across N) | cheap with a small model; the queries must be *distinct* (a degenerate rewriter produces N paraphrases of one query — zero union) |
| Retrieval | N× the retrieval work | still ms-scale per call; parallelizable [I] |
| Embedding (if per-query) | N embed calls | batchable/local, cheap |
| Reranking | over the *merged set — up to N×k_i candidates | the real cost term: worst case 5×100 = up to 500 pairs → 500 cross-encoder passes ≈ 1–5 s at 100 pairs ≈ 0.2–1 s GPU [I]. Under the page's recommended shape (k_i = 20–50, merged top-100) the rerank sees ≤ 100 pairs ≈ 0.2–1 s — so the multi-second tail is exactly what you avoid by capping the merge |
| Context | duplicate/overlapping evidence | merge quality determines whether the packed context is N× informative or N× redundant (41) |
| Latency | parallel retrieval + sequential rerank | the rerank is the serial tail [I] |

The design consequence: multi-query *raises k* (more candidates) at every
downstream stage — the funnel (03) widens. The right shape is usually
**N=3–5 queries × k_i=20–50 → merge → dedup → rerank top-100 → top-10** [I:
the conventional production shape; tune on your set, 53 lab 9].

## Merge and dedup policy
- **Merge by union with cross-query credit**: a chunk returned by 2 of 5
  queries is *evidence of robustness* — it is not noise from one phrasing.
  Many systems boost cross-hit chunks (a "hit-count" tiebreaker, 14's
  heuristics) [I].
- **Dedup is semantic, not string-based** [I]: near-duplicate chunks (same
  section, overlapping windows — 10's overlap) must collapse to one; the
  embedding-similarity threshold (typically 0.90+ cosine on chunk embeddings)
  is the cheap detector.
- **Cross-query contradiction**: if two queries retrieve *conflicting*
  statements (doc A says X, doc B says ¬X, both top-k), the packer should
  *surface both with provenance*, not silently average them (36's trust-tier
  composition; 47's contradictory-context failure).
- **Ordering after merge**: re-score the merged set with the reranker
  (14) — do not trust any single query's ANN order for the final top-k.

## When multi-query is the wrong tool
- **The question is precise and the retriever is good** — you are paying N×
  for a few points of recall you don't need; the reranker already does the
  per-pair work that matters [I].
- **Latency-critical paths** — the serial rerank tail (above) breaks a 200 ms
  SLO; the structured/short-context paths (30) avoid it entirely.
- **As a substitute for query understanding** — if the *one* right query is
  the problem (coreference, typo, underspecification), fix the query (15/32)
  before multiplying it; multi-query over a bad query is N bad queries.
- **When the evidence is in one place** — single-source, single-phrasing
  corpora (a wiki where every article is consistently titled): the union adds
  duplicates, not coverage.

## Key Takeaways
1. Multi-query trades N× retrieval+rerank cost for the *union* of query
   neighborhoods — the recall lever for ambiguous questions.
2. The rerank tail is the real cost: merge → dedup → rerank-top-100 keeps the
   funnel sane [I: N=3–5 × k=20–50].
3. Cross-hit chunks are robustness signals; dedup must be semantic.
4. Multi-query over a bad query is N bad queries — query understanding first
   (15/32).
5. It is earned by a golden set (46), not adopted by default; ablate it
   (45/53 lab 9).

## Related
[15 query transformation](15-query-transformation.md) · [14 reranking](14-reranking.md) ·
[41 compression/dedup](41-context-compression.md) · [44 economics](44-rag-economics.md) ·
[53 lab 9](53-rag-labs.md)
