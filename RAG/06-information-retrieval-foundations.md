# Information Retrieval Foundations — The 20% of IR You Need for RAG

`LAST_UPDATED: 2026-08-29` · Status: core page · Classic IR results (TF-IDF,
BM25, cosine) are standard textbook material; paper attributions are confirmed in
the research pass (02) and tagged accordingly.

## 30-Second Explanation
Retrieval is the discipline of ranking documents by relevance to a query. It
predates LLMs by decades and gives you three tools: (1) **lexical matching** —
find documents containing the query's terms (TF-IDF, BM25); (2) **dense
matching** — find documents *semantically* close to the query (embeddings +
nearest-neighbor); (3) **ranking math** — cosine, dot product, rank fusion.
RAG is what happens when you put an LLM at the end of one of these rankers.
Master this page and you can read every retrieval paper in 02.

## Documents, queries, and the relevance problem
A **corpus** is a set of *documents* (for RAG: your chunks, pages, or records).
A **query** is a user request. The retriever's job: produce a ranked list of
corpus documents by estimated relevance. There is no single correct answer —
relevance is a relation between query and document that the system must
*estimate*. That framing matters: it is why evaluation uses graded relevance
(45/46) and why "is the right doc in the top-k" is a measurable question.

## Term frequency, inverse document frequency, TF-IDF
- **TF(t, d)**: how often term *t* appears in document *d*. A doc that says
  "vector" 40 times is more likely about vectors than one that says it once.
- **DF(t)**: how many documents contain *t*. "the" appears in ~100% of docs —
  high DF, no signal. "HNSW" appears in few docs — rare, high signal.
- **IDF(t)** = log(N/DF(t)) (classic form; the `log((N−DF+0.5)/(DF+0.5)+1)`
  variant is the Lucene/Elasticsearch implementation — the +1 keeps the term
  non-negative, the original Robertson formulation omits it): down-weights
  ubiquitous terms, up-weights rare ones.
- **TF-IDF weight** = TF × IDF: a term's importance in a doc *for this corpus*.
  TF-IDF is a per-document term-weighting scheme — the foundation, not a
  complete ranker (it says nothing about normalizing for document length).

Intuition: TF-IDF answers "which terms in this document are *unusually*
prominent *here*?" Dense retrieval later answers a different question — "which
documents mean *roughly the same thing* as this query?" — which is why neither
alone is sufficient and hybrid search (13) works.

## BM25 — the workhorse lexical ranker
BM25 scores a document *d* against query terms *q* as a sum over terms:

```
score(d, q) = Σ_t IDF(t) · (tf(t,d)·(k1+1)) / (tf(t,d) + k1·(1 − b + b·|d|/avgdl))
IDF(t)      = log( (N − df(t) + 0.5) / (df(t) + 0.5) + 1 )
```

The two knobs: **k1** (term-frequency saturation: how much extra weight a term
gets for appearing again — default k1=1.2) and **b** (length normalization:
how strongly short/long docs are favored — default b=0.75). These defaults are
the conventional Elasticsearch/Lucene/OpenSearch settings [F: vendor docs,
confirmed in research pass].

**Worked example** [E, machine-verified] — 3-doc corpus, query "vector database",
k1=1.2, b=0.75:

```
d1 = "vector database"                       (len 2)
d2 = "vector search vector index"            (len 4)
d3 = "database replication"                  (len 2)
avgdl = 8/3 ≈ 2.67, N = 3, df(vector)=2, df(database)=2   (log = natural log,
the Lucene convention; log₂/log₁₀ would give different constants)
IDF(vector) = IDF(database) = log((3−2+0.5)/(2+0.5)+1) = log(1.6) ≈ 0.4700

score(d1) = 0.4700·((1.2+1)·1)/(1 + 1.2·(1−0.75+0.75·2/2.67)) ·2 terms
          ≈ 1.047
score(d2) ≈ 0.567   score(d3) ≈ 0.524
```

d1 wins: it contains *both* query terms and is short (its length factor
0.8125 < 1 means no length penalty vs. an average doc). Note what
BM25 *cannot* do: "How do I store embeddings?" matches a document containing
"embeddings" by exact token — not by meaning.

## Dense retrieval and why "semantic" is a different problem
A **dense retriever** embeds query and documents into a single vector space and
compares geometry instead of tokens. "embedding similarity" and "vector
database index" are both downstream of this one idea: represent text as a
point, relevance as closeness.

Two properties distinguish dense from sparse:
1. **Paraphrase invariance**: "How do I store embeddings?" and "vector store
   recommendations" land near each other; BM25 scores them low — the only
   shared token is the incidental "store".
2. **No exact-match guarantee**: a rare exact token (error code `E0x1F`, part
   number `SKU-88421`, an IP) can embed *less* similar to itself in another doc
   than a semantically related doc. Dense models are trained on meaning, not
   symbol identity.

This asymmetry — dense wins on paraphrase, sparse wins on exact tokens — is the
entire argument for hybrid retrieval (13).

## Cosine similarity, dot product, inner product
For vectors **a**, **b**:
- **Dot product** ⟨a,b⟩ = Σ aᵢbᵢ. Scales with vector magnitude: doubling **a**
  doubles the score.
- **Cosine similarity** = ⟨a,b⟩ / (‖a‖·‖b‖) ∈ [−1, 1] for non-negative vectors
  effectively [0,1]. **Scale-invariant**: [E] a=[1,0,0,0], b=[0.5,0.5,0,0] →
  a·b=0.5, ‖b‖=√0.5≈0.7071, cos=0.5/0.7071≈0.7071; c=2a → cos=1.0 while the
  dot product doubled (2 vs 1).
- **Inner product** on *unit-normalized* vectors = cosine. This is why embedding
  pipelines normalize: once vectors are unit-length, dot-product ANN search is
  exactly cosine search, and the HNSW index can be built with plain L2 or IP
  semantics.

Practical consequences [I]:
- Compare **cosine** when vector norms are uncontrolled (raw model outputs).
- **Normalize then dot-product** in the index — fastest exact semantics.
- **L2 (Euclidean) distance** after normalization is a monotone function of
  cosine (‖a−b‖² = 2 − 2cos for unit vectors), so ANN indexes using L2 or IP on
  normalized vectors rank identically; they differ only in score scaling.

## Nearest-neighbor search
"Find the k most similar vectors" is the **k-NN** problem. Exact k-NN over N
vectors is O(N·d) per query — fine for N < ~100K, dead for N = 10M. The
approximate nearest neighbor (ANN) trade-off — recall vs latency vs memory —
is the subject of `08-vector-search.md` (HNSW, IVF, PQ). The IR point to carry
forward: **recall < 1.0 is normal** in ANN, and the *ranking quality* of the
retrieval system (retrieval recall@k on real queries, 45) is the number that
matters, not the ANN recall on synthetic probes.

## Sparse vs dense — the decision table
| | Sparse (BM25/TF-IDF) | Dense (embeddings) |
|---|---|---|
| Signal | exact token overlap + rarity | semantic proximity in vector space |
| Query "E0x1F error" | strong (exact token) | weak (rare token, no training signal) |
| Query "how to speed up my queries" | weak (synonym gap) | strong (paraphrase) |
| Freshness | immediate (reindex term stats) | requires re-embedding |
| Cost at query time | very cheap (inverted index) | one embed call + ANN search |
| Interpretability | high (see which terms matched) | low (vector space) |
| Typical role | precision anchor for exact tokens | recall workhorse for meaning |

## Key Takeaways
1. Retrieval = ranking corpus docs by estimated relevance; TF-IDF weights terms,
   BM25 turns them into a document score with two standard knobs (k1, b).
2. Sparse and dense retrieval answer *different* questions (exact tokens vs
   meaning); hybrid gets both (13).
3. Cosine = dot product on normalized vectors; normalize everything and use
   dot-product semantics in the index.
4. ANN recall < 1 is normal; measure the *system's* retrieval recall@k on your
   real queries, not the index's probe recall.
5. Every RAG architecture in this section is a ranker + a context packer; this
   page is the ranker's foundation.

## Related
[07 embedding engineering](07-embedding-engineering.md) · [08 vector search](08-vector-search.md) ·
[13 hybrid retrieval](13-hybrid-rag.md) · [45 evaluation](45-rag-evaluation.md) ·
`../Transformer/` (where embedding models come from)
