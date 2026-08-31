# RAG and Caching — Eight Cache Layers and How They Interact
`LAST_UPDATED: 2026-08-29` · Status: core page · Engineering-reasoning page; cache designs
and interaction patterns are engineering synthesis [I]; cost numbers derive from the
constants bank [E]; per-engine prefix/KV behavior lives in ../KV-Cache/ and is linked, not
re-derived here.

## 30-Second Explanation
A RAG stack is not one cache but eight, sitting at different layers: the query string, the
embedding, the retrieval result, the rerank scores, the raw documents, the prompt prefix,
the KV state of a live sequence, and — the risky one — the *semantics* of past Q&A. Each has
a different key, a different hit condition, and a different way of quietly returning wrong
answers. Two rules organize all eight: **order matters** (check cheap upstream caches
before doing expensive work: query -> retrieval -> semantic -> prefix), and **invalidation
must be tied to the artifact that changed** (a reindex invalidates retrieval results, not
embeddings; a corpus change invalidates semantic-cache hits, not query-cache entries for
identical strings — wait, identical strings are exactly the semantic hazard; see below).
Get keys and invalidation right and caching cuts both latency and bill; get them wrong and
users receive last month's confident answer to this month's question.

## The eight layers
```
                 WHERE EACH CACHE SITS IN THE REQUEST PATH

 query ──> [1 QUERY CACHE]      exact string -> final answer?
             │ miss
             v
           [2 EMBEDDING CACHE]   text -> vector (dedupe re-embeds)
             │
             v
           [3 RETRIEVAL CACHE]   query+params -> chunk ids+scores
             │ miss   (index gen N pinned in key)
             v
           [8 SEMANTIC CACHE]    embed; ANN over past Q&A?  (the risky layer —
             │ hit                checked only AFTER the exact-match layers so a
             │ miss               paraphrase-fuzzy hit never shadows an exact one)
             v
           [ RETRIEVER ] ──needs docs──> [5 DOCUMENT CACHE] (raw content)
             │
             v
           [4 RERANKING CACHE]   query+chunk-set -> scores
             │
             v
           [ PACK PROMPT ] ── shared prefix ──> [6 PREFIX CACHE] (serving engine)
             │
             v
           [7 KV CACHE]          per-sequence state during decode
             │
             v
           ANSWER ──> (write-backs: 1, 8)
```

1. **Query cache** — exact query string -> final answer. The cheapest possible hit: skip
   retrieval *and* generation. Only exact matches hit; typos and rephrasings miss (that is
   what layer 8 is for). Key: normalized query string (+ tenant, + params).
2. **Embedding cache** — text -> vector. Deduplicates re-embedding of repeated queries,
   cached documents, and re-indexed-but-unchanged chunks. Hit saves an embedding API call
   (~$0.00001-$0.00007 per 512-tok text at $0.02-$0.13 per 1M embedding tokens [E: bank
   rates]); vectors are deterministic for a fixed model+version, so entries survive corpus
   changes — invalidate only on embedding-model change.
3. **Retrieval cache** — query+params (k, filters, tenant, retriever config) -> chunk ids +
   scores. Skips search entirely on repeat queries. **Safe only under index version
   pinning**: the index generation must be part of the key, because otherwise a reindex
   makes cached results point at deleted or stale chunk ids [I].
4. **Reranking cache** — query + chunk-set (ids + versions) -> relevance scores. Cross-
   encoder reranking is the most expensive per-item step in the path [I: typical ranges,
   bank: rerank of 100 pairs ~200-1000 ms GPU] — worth caching whenever the same
   chunk-set recurs, e.g. paginated or filtered variations of one query.
5. **Document cache** — raw document content (and its parsed form) keyed by doc id +
   version. Not query-facing at all; it serves re-processing, citation expansion, parent
   fetching (18), and re-compression without re-fetching from source systems.
6. **Prefix cache** — KV/prompt-prefix reuse *inside the serving engine*: identical token
   prefixes (system prompt, few-shot block, template boilerplate) are prefilled once and
   reused across requests. This is a serving-engine property, not an application cache —
   design prompts so the static prefix is genuinely identical across requests
   (../KV-Cache/Prompt-and-Prefix-Caching.md).
7. **KV cache** — per-sequence attention state during decode. Not a cross-request cache in
   the application sense; it exists per live sequence and its economics (paged allocation,
   eviction, reuse within a session) are the KV-Cache section's subject
   (../KV-Cache/Paged-KV-Cache.md). RAG interacts with it through context length: every
   cached-at-the-app-layer token you *don't* put in the prompt is KV memory you don't
   allocate [E: 5,120 tok ≈ 640 MiB at 128 KiB/token].
8. **Semantic cache** — embed the query, ANN-search *past questions and answers*, return a
   stored answer when similarity exceeds a threshold. The only layer that hits on
   *paraphrases* — and the only one that can return a confidently wrong answer
   *even with correct keys and invalidation* (fuzzy-match error); every other layer
   goes wrong only when its invalidation is missed.

## The layers side by side
| Layer | Key | Hit condition | Invalidation trigger | Risk if wrong |
|---|---|---|---|---|
| Query cache | exact query string (+tenant) | byte-identical (normalized) question | corpus change, policy change, TTL | stale exact answer to a still-asked question |
| Embedding cache | text + embedding model+version | same text, same model | embedding model swap | silent vector-space mismatch |
| Retrieval cache | query+params+**index generation** | same query, same params, same index gen | reindex (bump generation), filter/config change | chunk ids that no longer exist / are stale |
| Reranking cache | query + chunk-set ids+versions | same query against same chunk set | chunk set changes, reranker model swap | scores from an older chunk set reused |
| Document cache | doc id + version | same document version | source doc update, re-parse | reprocessing against old content |
| Prefix cache | token prefix hash (engine-side) | identical leading tokens | any change to the shared prefix text | (low) wasted memory; mismatch = miss, not error |
| KV cache | sequence/session id (engine-side) | tokens already in the live sequence | session end, eviction | n/a at app layer (engine correctness) |
| Semantic cache | query embedding (+tenant+corpus version) | ANN similarity above threshold | corpus version, tenant, TTL, threshold change | **wrong answer to a paraphrased question** |

## Order matters: the lookup chain
The layers are not alternatives; they fire in a specific order, cheapest-first [I]:

```
  query cache  ->  retrieval cache  ->  semantic cache  ->  prefix cache
  (exact string,   (skip search,      (paraphrase hits,    (engine reuses
   zero risk)       pinned index gen)  correctness risk)    prefill; always on)
```
Rationale: a query-cache hit is free and exactly correct, so check it first. A retrieval-
cache hit skips search but still pays generation, so it precedes the semantic cache — you
do not want a paraphrase-fuzzy hit to shadow an exact-match hit that is strictly more
correct. The prefix cache is not chosen at all; it engages automatically whenever the packed
prompt shares a prefix with other requests, which is why prompt layout (static system block
first, volatile evidence last) is a caching decision made at template-design time (43).

Interaction subtlety [I]: app-layer caching and prefix caching multiply. If the semantic
cache misses but the retrieval cache hits, you still pay generation — and generation is
where the prefix cache earns its keep by skipping prefill of the static template block. At
at $3/1M input, an 8k-token shared system+template prefix is ~$0.024 per request of prefill
that prefix caching removes or heavily discounts for repeat shapes — on metered APIs
cached-prefix input tokens are billed at a discount, not zero; full elimination holds only
for self-hosted engines that reuse stored KV without recompute [E: derived; vendor
caching-pricing models].

## The semantic-cache correctness hazard
Semantic caching trades a small correctness risk for a large latency/cost win — the only
cache layer where a *hit can be wrong without an invalidation miss* (fuzzy match), [I]:

- **Near-duplicate, different intent or version.** "What is the 2025 refund window?" and
  "What is the refund window?" embed as near-identical. If the corpus changed between the
  cached answer and now — or the cached answer was generated for a different tenant with
  different policy documents — the hit serves last quarter's policy to this quarter's
  question, with no citation mismatch to warn anyone.
- **Tenancy leakage.** User A's session stores an answer containing A-specific data; user
  B's paraphrase lands inside the similarity threshold. That is a data-leak incident, not a
  cache bug (49).
- **Threshold is not truth.** Similarity measures surface form; two questions can be 0.94
  similar and have different answers ("does plan X include SSO?" before vs after the plan
  changed).

Mitigations [I]:
1. **Key enrichment** — fold corpus/index version + tenant + ACL scope into the semantic
   cache key (and the query/retrieval keys). A reindex that bumps the generation then
   invalidates semantic hits for free.
2. **Scope discipline** — use semantic caching only over *stable public corpora*: FAQ
   bodies, product docs, API references — material where a slightly older answer is still
   materially true. Never over per-user or fast-moving data.
3. **Hybrid guard** — on a semantic hit, optionally re-verify cheaply: confirm the stored
   answer's citation set still exists in the current index generation before serving.
4. **Threshold + review** — high threshold, sampled human review of hits vs misses (50),
   and always log the matched question alongside the served answer for auditability.

## Stale answers after reindex
Any cache that stores *derived* artifacts (answers, retrieval results, rerank scores) can
serve a pre-reindex world. The engineering answer is **invalidation by index generation**
[I]: every derived artifact carries (or is keyed by) the index generation it was built
from; a reindex publishes generation N+1 and every cache keyed to N misses en masse.
Corollaries: never let the retrieval cache key omit the generation; query-cache entries
survive a reindex only if the answer semantics are pinned to a doc version that did not
change; semantic caches must either key on generation or accept stale-window risk with a
TTL shorter than your reindex cadence. Embedding and document caches are the exceptions —
their artifacts (vectors, raw text) are version-of-the-input, not version-of-the-index.

## What caching saves [E]
From the constants bank (@ $3/$15 per 1M in/out; derivation re-run in-session, matches the
bank's $0.0153 (truncated form of $0.01536) + $0.0075 ≈ $0.023 for a 10-chunk request):

- A **query-cache or semantic-cache hit** skips retrieval and generation: saves ≈ $0.023
  per hit (5,120 input tok ≈ $0.0154 + 500 generated tok ≈ $0.0075), plus the full
  generation latency. At 30% hit rate over 10k requests/day that is ≈ $70/day [I: linear
  scaling].
- An **embedding-cache hit** on a 512-tok query saves an embedding call ≈ $0.00001-$0.00007
  [E: $0.02-$0.13 per 1M tok applied to 512 tok] — small per call, but ingestion-time
  dedup across re-chunked corpora is where it pays (44).
- A **retrieval-cache hit** skips search + fetch (ms-scale latency [I]) and, with a
  reranking-cache hit, the 200-1000 ms GPU rerank [I: bank latency ranges].
- A **prefix-cache hit** removes repeated prefill of the shared template prefix:
  ~$0.024 per request for an 8k-tok shared prefix [E: derived], and proportionally less
  TTFT — the prefill story continues in 43 and ../KV-Cache/Prompt-and-Prefix-Caching.md.
- Compression interacts: every token the compressor removes (41) is a token no cache layer
  ever has to move again — caching and compression attack the same bill from both ends (44).

## Key Takeaways
1. Eight layers: five application-layer artifacts (answers, vectors, search results,
   scores, raw document text) + two engine-internal mechanisms (prefix, KV) — each with
   its own key and invalidation.
2. Order the lookup chain cheapest-first and most-exact-first: query -> retrieval ->
   semantic -> prefix; do not let fuzzy layers shadow exact ones.
3. The semantic cache is the only layer that can be *wrong on a hit*: key it with corpus
   version + tenant, or restrict it to stable public corpora.
4. Reindexing must invalidate by index generation — anything derived from the old index
   (retrieval results, rerank scores, cached answers) is stale the moment N+1 ships.
5. Caching is an economics tool as much as a latency tool [E]: ~$0.023 saved per full-hit
   request, ~$0.024 of prefill per request for an 8k-tok shared prefix — see 44 for the
   full bill.

## Related
[44 economics (the full bill)](44-rag-economics.md) ·
[43 inference engineering (prefill, TTFT)](43-rag-inference-engineering.md) ·
[41 compression (fewer tokens to cache)](41-context-compression.md) ·
[03 basic pipeline](03-basic-rag-pipeline.md) · [49 multi-tenant RAG](49-multi-tenant-rag.md) ·
`../KV-Cache/Prompt-and-Prefix-Caching.md` · `../KV-Cache/Paged-KV-Cache.md` ·
`../Inference/Continuous-Batching.md` · `../Serving-Engines/vLLM.md`
