# Hybrid RAG — Lexical + Dense, and How to Fuse Them

`LAST_UPDATED: 2026-08-29` · Status: core page · BM25/dense behavior per 06;
RRF defaults cross-checked with the research bank
(`/tmp/rag-research/B-ir-embeddings-dbs.md`).

## 30-Second Explanation
Sparse (BM25) retrieval finds *exact tokens*; dense (embeddings) finds
*meaning*. They fail in opposite directions: BM25 scores "embedding
recommendations" and "how to store vectors" at zero (no shared tokens), while a
dense model can rank a document that never says "E0x1F" above the one that does
(rare tokens carry little training signal). **Hybrid retrieval runs both
retrievers and fuses the two ranked lists** — the result is usually better than
either alone, and it is the 80/20 default for serious corpora [I: the
consistent engineering consensus; measured in lab 3, 53].

## Why exact keywords matter (the cases dense-only loses)
- **Product names / part numbers**: "SKU-88421" — the exact string is the
  answer; its embedding is a coin-flip neighborhood [I].
- **Error codes**: "E0x1F", "0x80070005", "CVE-2024-3094" — rare, exact,
  high-stakes; dense models almost never saw them in training.
- **IPs / hostnames / identifiers**: infrastructure questions live on exact
  tokens.
- **Legal clauses**: "Section 12(b)(iii)" — a citation is an exact string with
  exact meaning; a paraphrase is a different clause.
- **IDs in general**: order numbers, ticket numbers, employee IDs, commit SHAs.
The pattern: **the rarer and more load-bearing the token, the more dense
retrieval under-serves it** — while BM25's IDF makes rare tokens its *strongest*
signal (06). Conversely, the paraphrase case ("how do I speed up my queries"
vs "query performance tuning") is where dense wins and BM25 gives zero.

## The two retrievers, precisely
```
query ──┬─→ BM25 (inverted index) ──→ ranked list L1 (score: BM25)
        └─→ embedding → ANN (HNSW)  ──→ ranked list L2 (score: cosine)
                    │
                    ▼
              score fusion (below)
                    │
                    ▼
              fused top-k → reranker (14) → context
```
Notes: (a) both lists are usually top-50–100 *before* fusion (more than the
final k, so the fusion has candidates); (b) the two score scales are
incommensurable (BM25 scores are unbounded; cosine is [−1,1] in general and
[0,1] for non-negative embeddings, as most text-embedding models produce) —
which is exactly why *rank-based* fusion is the default.

## Score fusion
**Reciprocal Rank Fusion (RRF)** — the default [F: Cormack, Clarke & Büttcher,
"Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning
Methods", SIGIR 2009; standard constant k=60 — venue confirmation in research
pass]:

```
RRF(d) = Σ over lists L of  1 / (k + rank_L(d))
```

Worked example [E: machine-verified] with k=60, two lists:
| doc | ranks | RRF |
|---|---|---|
| A | 1, 3 | 1/61 + 1/63 = **0.032266** |
| B | 2, 1 | 1/62 + 1/61 = **0.032522** |
| C | 5 (list 1 only) | 1/65 = **0.015385** |
| D | 7, 4 | 1/67 + 1/64 = **0.030550** |

B beats A — being #1 in one list and #2 in the other outweighs #1+#3. The
constant k=60 *deliberately flattens* the top ranks (rank 1 scores 0.016393
vs rank 2's 0.016129 — a 1.6% gap [E]): RRF rewards *agreement between the
two lists* over *any single list's top-1*. That is the property you want when
the two lists are genuinely complementary [I: the reason the flattening is a
feature, not a bug — see the "when RRF hurts" note].

**Alternatives** [I: standard practice; no universal winner]:
- **Linear score combination** (α·norm(BM25) + (1−α)·norm(cosine)):
  tunable (α), but requires score normalization and is sensitive to corpus
  score distributions; used when you have labeled data to fit α on.
- **Convex combination with learned weights**: a small model learns the fusion
  from relevance labels — more moving parts, pays off only with enough labeled
  queries.
- **Retrieval-set union** (keep the union of both top-ks, let the *reranker*
  decide): the lazy-but-effective variant — skip fusion math, hand the merged
  candidate set to a cross-encoder (14). Works well when the reranker is
  cheap/local; the reranker's pairwise scoring is scale-free by construction.
- **Vendor built-ins**: Elasticsearch RRF (`rank_constant` default 60) and
  Qdrant (RRF among its fusion options) implement this; Weaviate hybrid is
  an alpha-weighted BM25+vector *score* blend, not RRF; OpenSearch added
  native RRF in 2.19 (Feb 2025) [F: vendor docs/blogs — ES + OpenSearch blog,
  2026-08-30].

## When hybrid hurts
- **Pure paraphrase corpora** (consumer Q&A, support tickets where exact
  tokens rarely matter): the BM25 list is mostly noise; dense-only with a
  better embedder may be equal or better [I: measure on your set (46) — the
  "hybrid is better" claim is a *default*, not a law].
- **Tiny corpora**: with N < ~10K chunks, exact search is cheap enough that a
  well-chosen single retriever + reranker is simpler for equivalent quality
  [I].
- **Bad BM25 configuration**: stop-word/ stemming misconfigured for your
  language makes the sparse list adversarial; fix the sparse side first.
- **Cost-sensitive latency**: two retrievers ≈ 2× retrieval work (usually still
  ms-scale, so rarely a real constraint — the reranker is the latency item, 14).

## Production notes
- **Run both lists at top-100, fuse, take top-50 into the reranker** [I: the
  conventional shape — more than the final k at every stage; the funnel is the
  design].
- **Metadata filters apply per list** (12): the same tenant/classification
  predicate on the BM25 side and the vector side; hybrid does not relax ACLs.
- **Log both lists** (50): when a query fails, you need to know *which*
  retriever missed — the two lists' disagreement is diagnostic (one-hit
  documents are usually the right documents; documents ranked high in *only
  the sparse* list are the exact-token saves; high in *only the dense* list are
  the paraphrase saves).
- **Freshness**: BM25 re-indexing is cheaper than re-embedding (08/09) — in a
  streaming corpus (35), the lexical side is often the *fresher* half.

## Key Takeaways
1. Sparse and dense fail in opposite directions; the complementarity is the
   whole argument for hybrid.
2. RRF (k=60) is the default fusion: rank-based, scale-free, and deliberately
   flattening — it rewards cross-list agreement.
3. The practical shape: top-100 per list → fuse → top-50 → cross-encoder
   rerank → top-10 → context (03's funnel, with the two retrievers up top).
4. Log both lists: which retriever missed is half of every retrieval
   post-mortem (47/50).
5. "Hybrid is better" is a default, not a law — your domain set decides (46,
   37).

## Related
[06 IR foundations](06-information-retrieval-foundations.md) ·
[14 reranking](14-reranking.md) · [12 metadata filtering](12-metadata-engineering.md) ·
[09 vector DBs (hybrid support)](09-vector-databases.md) · [53 lab 3](53-rag-labs.md)
