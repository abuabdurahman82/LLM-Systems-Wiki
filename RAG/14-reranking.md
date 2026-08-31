# Reranking — From Recall to Precision

`LAST_UPDATED: 2026-08-29` · Status: core page · Latency/cost ranges are [I];
model families referenced generically (research bank confirms the specific
systems in 09/52).

## 30-Second Explanation
The first-stage retriever (ANN or BM25) optimizes **recall at speed**: cheap
similarity that casts a wide net. The reranker optimizes **precision at cost**:
a more expensive model that scores each (query, chunk) pair *jointly* and
reorders the net's catch. The canonical shape:

```
Retriever (hybrid, 13)
   ↓ top-100 candidates
Reranker (cross-encoder)
   ↓ top-10
LLM
```

Retrieval recall and ranking precision are different jobs: the retriever asks
"is this document *near* the query?"; the reranker asks "does this document
*actually answer the query?*". The reranker is where "near" becomes "about
this" — and a meaningful share of the end-to-end retrieval quality gain comes
from the reranking stage [I: the consistent result across retrieval engineering
practice; Anthropic's "Introducing Contextual Retrieval" post (Sep 19, 2024)
measures this: retrieval failure 5.7% → 2.9% with contextual hybrid, → 1.9%
adding a reranker — so in that data the retrieval side contributes the larger
share of the measured reduction (−2.8 pp vs −1.0 pp) and full numbers are on
40; the reranker is the *last mile* that a retrieval miss cannot fix].

## Cross-encoder rerankers (the workhorse)
A **cross-encoder** takes (query, document) as a *single concatenated
sequence* and outputs one relevance score; every interaction between query
tokens and document tokens is visible to the model (full attention across the
pair). That is strictly more expressive than bi-encoder (embedding) matching,
and strictly more expensive: one forward pass *per pair*, so 100 candidates =
100 forward passes [I: the cost structure that makes reranking the "expensive
half" of retrieval].

Properties:
- **Pointwise, scale-free scoring**: no vector-space geometry involved — each
  (query, document) pair is scored *independently* [I]. This is why
  cross-encoders are also the natural *fusion* alternative to RRF (13): score
  the merged candidate set directly.
- **Latency**: 100 pairs on a local GPU ≈ 200–1000 ms; on CPU ≈ 1–5 s
  [I: ranges, not measurements — your model size decides]. This is the
  dominant retrieval-latency term in most pipelines (43).
- **Top-k only**: a cross-encoder cannot be pre-computed over a corpus (the
  query is one half of every pair) — it is inherently a *second-stage* model.
  That is the entire reason the two-stage architecture exists.
- **Models**: the BGE-reranker / ms-marco cross-encoder family (MiniLM- and
  Electra-based MS MARCO cross-encoders in sentence-transformers) and the
  2024–26 "rerank API" services (Cohere-class, vendor APIs) [I: family
  descriptions; specific system capabilities confirmed in 09/52].

## LLM-as-reranker (the expensive cousin)
Use the generator LLM itself to rank candidates: "Given this query, which of
these 10 documents is most relevant? Respond with the ids in rank order."
- **Why it's tempting**: no separate model; the LLM's world knowledge and
  instruction-following make it a *semantic judge*, not a pattern matcher;
  can rank with *reasoning* ("doc 3 is about the 2024 version, the query asks
  about current behavior" — a judgment a cross-encoder can make but less
  reliably).
- **Why it's usually wrong as the default reranker**: 100 candidates × a
  reasoning model = seconds of latency and real money per query [I: cost is
  10–100× a cross-encoder on the same pairs]; non-determinism without
  temperature control; and it is the *same model* that will generate the
  answer, so its ranking biases correlate with its generation biases.
- **Where it belongs**: low-QPS, high-stakes, *small candidate sets*
  (rank the top-10 from a cross-encoder, not the top-100); and as the
  *verification* pass (45), where the judgment task differs from ranking.

## Late interaction (ColBERT-class) as a "light rerank"
Late-interaction models (ColBERT-class, arXiv:2004.12832 [F: verified in
research bank]) compute *token-level* embeddings and score a pair by
MaxSim over token similarities — more interaction than bi-encoder, far cheaper
than cross-encoder. Production pattern [I]: use late interaction as the
*first-stage* retriever (or a first-stage that partially replaces the
bi-encoder), and keep the cross-encoder for the final top-50→top-10. The
"late interaction as reranker" configuration is a legitimate middle tier when
cross-encoder latency is the bottleneck.

## Heuristic reranking (the underrated baseline)
Before buying any model, the heuristics that move quality for free [I:
standard practice]:
1. **Recency**: within a score tie-band, prefer newer chunks (stale-info
   mitigation, 47) — sort by (relevance band, date desc).
2. **Source trust tier** (36/48): primary > secondary > web.
3. **Diversity / dedup**: drop near-duplicates (same content, different
   chunks) so the top-10 is 10 *distinct* pieces of evidence (41).
4. **Source/format bias correction**: some retrievers systematically under-rank
   certain source types (tables, appendices) — a per-type boost, measured on
   the golden set (46). (Distinct from *position* bias — list-position
   effects, which is a failure mode of listwise LLM rerankers: 47.)
5. **Length/structure priors**: chunks with explicit headings answering the
   query's terms ("§4.2 Results: …") get a small boost [I: the head-coverage
   property from 10, as a score].

## Retrieval recall vs ranking precision — the division of labor
| | Retriever | Reranker |
|---|---|---|
| Optimizes | recall@100 (don't miss it) | precision@10 (put the right one on top) |
| Cost per candidate | ~free (pre-computed embeddings) | O(1) model forward per pair |
| Can miss | yes — that's the failure the reranker *cannot* fix | n/a — it only reorders what it was given |
| Failure visible as | right doc not in top-100 | right doc in top-100 but ranked 30th and cut |

The operational consequence [I]: **if your reranker is great but you still
fail, the retriever missed the document — add retrieval capacity (hybrid,
better embedder, more k, query transformation 15/16/17). If the document is in
the candidate set but not in the context, the ranker cut it — improve the
ranker or the k.** The reranker cannot recover a retrieval miss; it can only
reorder what survived. (The mirror of 41's compression risk: a reranker
threshold that is too aggressive *is* a ranking failure, 47.)

## Cost/latency implications (the numbers that matter)
- The reranker is the **most expensive *per-query* retrieval stage** (100
  forward passes vs the retriever's pre-computed lookup) and the
  **dominant pre-LLM latency term** [I: ms retrieval + 200ms–1s rerank vs
  ~0ms fusion]. Corpus *embedding* is more expensive in total but it is a
  one-time ingestion cost (07), not a per-query stage.
- **Candidate count is the knob**: top-100→10 is the conventional shape;
  top-50→10 halves rerank cost for a small recall cost (measure it, 53 lab 4);
  top-200→20 buys recall for 2× rerank cost.
- **Local vs API**: a local cross-encoder (or the vendor's) at your QPS vs a
  per-call API — the break-even is QPS × candidate count × API price vs the
  GPU you would otherwise idle (44; `../Platform-Economics/`).
- **Batching**: rerank requests naturally batch (100 pairs = one batch);
  engines that batch cross-encoders get near-GPU-saturated throughput [I].

## Key Takeaways
1. Two stages, two jobs: retriever = recall at speed; reranker = precision at
   cost. The reranker cannot recover what the retriever missed.
2. Cross-encoder (query, chunk) joint scoring is the workhorse; top-100→top-10
   is the conventional funnel.
3. LLM-reranking is for small sets / high stakes; as a default reranker it is
   the wrong cost/latency point and the same-model bias problem.
4. Heuristic re-ranking (recency, trust tier, dedup, type boosts) is free
   quality — do it before buying anything.
5. Candidate count is the rerank cost knob; tune it on your golden set (53).

## Related
[13 hybrid](13-hybrid-rag.md) · [41 compression](41-context-compression.md) ·
[44 economics](44-rag-economics.md) · [53 lab 4](53-rag-labs.md) ·
[08 vector search (recall)](08-vector-search.md)
