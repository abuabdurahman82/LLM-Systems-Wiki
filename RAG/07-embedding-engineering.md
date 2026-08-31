# Embedding Engineering — Choosing and Tuning the Retrieval Model

`LAST_UPDATED: 2026-08-30` · Status: core page · Model facts verified against
model cards / vendor docs 2026-08-29; where a number is not yet pinned down,
it is marked UNVERIFIED rather than guessed.

## 30-Second Explanation
The embedding model is one of the highest-leverage choices in a RAG system:
every chunk and every query becomes a point in its space, and *no amount of
index tuning recovers a bad geometry*. Pick by (1) task (which questions you
must answer), (2) language (monolingual vs multilingual), (3) size/latency
budget, and (4) whether you need *more than dense* (sparse BM25, multi-vector).
Then: version-pin it, keep query and index on the **same** model, and re-embed
the whole corpus when you swap — mixing two models' vectors in one index is
silent retrieval rot (49).

## The model families

| Family | Example | Shape | Notes |
|---|---|---|---|
| Encoder (BERT-class) | **all-MiniLM-L6-v2** | 384-d, 22.7M params [F: 22,713,728 per the HuggingFace model metadata (total param count); config-based recompute lands 22.56M ≈ 0.7% off] | the classic lightweight default; Sentence-BERT lineage |
| Sentence encoders | **Sentence-BERT** (Reimers & Gurevych, arXiv:1908.10084, EMNLP 2019 [F]) | — | siamese BERT → sentence embeddings; the family's origin |
| Large instruct-tuned | **BGE-M3** (arXiv:2402.03216 [F]) | dense + sparse + multi-vector, 100+ languages, 8192 max ctx | one model, three retrieval modes (hybrid from a single source) |
| API embedders | OpenAI **text-embedding-3-large** | 3072-d, **$0.13 per 1M tokens** [F: OpenAI docs] | Matryoshka: truncatable to shorter dims; docs display 8192 max input tokens |
| ColBERT-class | ColBERT (arXiv:2004.12832, SIGIR 2020 [F]) | token-level late interaction | not a single vector — see 08 for the ANN treatment |
| Lexical (no model) | BM25 (06) | — | exact tokens; the hybrid half (13) |

## How to choose (the decision tree) [I: the structure is consensus; the
defaults are per family]

1. **Must it match exact tokens** (IDs, part numbers, code symbols)? → hybrid
   (13): dense + BM25. Exact matching of opaque alphanumeric tokens via dense
   embeddings is *unreliable* (a model that has seen similar codes can match
   them, but you cannot count on it) — only the lexical half of a hybrid
   guarantees it.
2. **Multilingual corpus?** → BGE-M3-class (100+ languages [F]) or
   vendor multilingual models; monolingual models degrade to keyword matching
   out of domain — this is the classic per-slice failure (56: "language/
   domain-routed retrieval").
3. **Latency budget / self-host?** → MiniLM-class (22.7M params [F]) on CPU;
   otherwise the API tier. The embedding call sits on the *query path* (per
   request) and on the *ingestion path* (per chunk) — 44 prices both.
4. **Long documents / long chunks?** → check the max-context of the *embedding*
   model, not just the LLM's. BGE-M3: 8192 [F]; OpenAI 3-large docs display
   8192 tokens [F]. Over-length chunks behave per vendor: most local encoder
   libraries (sentence-transformers, BGE-M3) *silently truncate* at
   max_seq_length, while API embedders (OpenAI) *reject* over-length input with
   an error [I: per-vendor behavior — check before relying on it; silent
   truncation and hard failure have very different failure signatures]. Either
   way, the geometry is now of *part of your chunk*.
5. **Need sparse + dense + multi-vector from one source?** → BGE-M3-class
   (multi-functionality [F]); otherwise two separate systems + RRF (13).

## The five embedding-model failure modes

1. **Query/doc asymmetry**: the model sees questions in training but the
   corpus is docs (or vice versa) → the two live in different corners of the
   space. Symptom: retrieval works on the training distribution and not on
   yours. Fix: a model trained for your phrasing pair, or query transformation
   (15).
2. **The paraphrase gap**: embedding distance ≠ answer distance when phrasing
   differs sharply. This is what HyDE (17) and contextual retrieval (40)
   attack from the two sides.
3. **Domain shift**: a general embedder on a legal/medical corpus → the
   geometry is a *general-language* geometry. Domain-tuned or in-domain
   fine-tuning is the fix; the detection is per-domain sliced recall (45/46).
4. **Version drift**: re-embedding with a new model version while old vectors
   remain in the index → two spaces, one index, no error raised. The index
   must be *version-stamped* (12, 49) and rebuilt on every model change.
5. **Dimension/quantization drift**: API models with Matryoshka dims (e.g.
   3-large documented at 256/1024/3072 points [F]) — mixing dims in one
   collection is a subtle bug; PQ/quantized storage adds an *approximation
   error on the ranking* (a systematic distance bias of order ‖x−x̂‖², not
   zero-mean noise) that a reranker (14) is exactly positioned to absorb.

## The operational rules

- **Pin the version**, write it into the index metadata (12): "retriever
  model + version + quant" is part of the index's identity.
- **Same model both sides**: query encoder = index encoder (06's asymmetry
  rule). An asymmetry experiment is a *deliberate* design choice, not a
  default.
- **Full re-embed on swap** — never partial; the index is the model's output,
  and a half-new index is two spaces. Cost: 44's ingestion line (embedding
  500M tokens ≈ $65 at $0.13/1M [F: 3-large tier] or ≈ $10 at the small-tier
  ~$0.02/1M [I: text-embedding-3-small-class pricing; the exact tier number was
  not re-fetched this pass — treat as order-of-magnitude]).
- **Measure recall on your golden set (46), not a benchmark**: BEIR-style
  zero-shot numbers (06) tell you the model is sane; only your corpus tells
  you it is right.
- **Cache embeddings of unchanged chunks** (42) — re-embedding a re-chunked
  corpus where 90% of chunks are byte-identical is wasted spend.

## Key Takeaways
1. The embedding model is a *design decision*, not a configuration: it fixes
   the geometry everything else runs on.
2. Default stack for most production RAG: dense (task-matched) + BM25 +
   cross-encoder rerank (13/14); MiniLM-class for cheap/local, BGE-M3-class
   for multilingual/hybrid, 3-large-class for API-tier.
3. Version-pin and re-embed the whole index on any model change — two
   vector spaces in one index is the most common silent retrieval failure.
4. Judge embeddings on *your* golden set's recall@k (45/46), never on
   benchmark rankings alone.

## Related
(selective list — inline refs also point at 42/46/56)
[06 IR foundations](06-information-retrieval-foundations.md) ·
[08 vector search](08-vector-search.md) · [10 chunking](10-chunking.md) ·
[12 metadata](12-metadata-engineering.md) · [13 hybrid](13-hybrid-rag.md) ·
[14 reranking](14-reranking.md) · [17 HyDE](17-hyde.md) · [40 contextual]
(40-contextual-retrieval.md) · [42 caching](42-rag-caching.md) ·
[44 economics](44-rag-economics.md) · [45 evaluation](45-rag-evaluation.md) ·
[46 golden datasets](46-rag-golden-datasets.md) · [49 multi-tenant]
(49-multi-tenant-rag.md) · [56 anti-patterns](56-rag-antipatterns.md)
