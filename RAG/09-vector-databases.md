# Vector Databases — The Storage Layer Under Retrieval

`LAST_UPDATED: 2026-08-30` · Status: core page · Licenses/versions/index
support verified against GitHub API + vendor docs on 2026-08-29/30.

## 30-Second Explanation
Every production vector store is the same three layers: **an ANN index
(08), storage + filtering, and an API**. The index choice (HNSW vs IVF vs
DiskANN) is *invisible behind the API* — which is exactly why the real
differences live in **filtering semantics, hybrid search, ops, and the
license/ops model**, not in the raw ANN numbers. "Which vector DB" is a
question about your corpus's *shape* (filter-heavy? hybrid? single-node?),
not about whose benchmark bar is highest.

## The stack, per system (verified 2026-08-29/30)

| System | License [F] | Indexes [F] | Distinguishing traits [F] |
|---|---|---|---|
| **pgvector** (v0.8.6 tag) | PostgreSQL (BSD-style, per-repo) | HNSW + IVFFlat; `halfvec`/`bit`/`sparsevec` types | lives *inside* Postgres — relational filters + vectors in one query; the "we already run Postgres" default |
| **Qdrant** | Apache-2.0 | HNSW (payload-filterable traversal) | filter-as-first-class: the HNSW walk respects the payload filter during search; RRF/DBSF hybrid |
| **Milvus** | Apache-2.0 | HNSW, IVF, FLAT, SCANN, DiskANN | the most index options; GPU variants; the "big data lake for vectors" |
| **Weaviate** | **BSD-3-Clause** (not Apache) | HNSW | hybrid BM25+vector with an `alpha`-weighted blend (not RRF); modules (vectorizers as plugins) |
| **Pinecone** | proprietary | (managed) | serverless; sparse + dense; the "zero-ops managed" tier |
| **Vespa** | Apache-2.0 | HNSW + BM25 (native hybrid) | large-scale real-time search + ML in one engine; attribute-filterable |
| **Chroma** | Apache-2.0 | hnswlib 0.8.2 + usearch | embedded-first: `pip install`, in-process; the prototyping default |
| **Elasticsearch / OpenSearch** | **Elastic tri-license: AGPLv3 + SSPL v1 + Elastic License 2.0** (source in LICENSE.txt); OpenSearch Apache-2.0 | HNSW (dense_vector) + BM25; RRF (rank_constant default 60); ELSER `.elser_model_2` sparse | you're extending an *existing* search stack; hybrid = built-in RRF (ES/OpenSearch); OpenSearch also offers score-normalization fusion |
| **FAISS** | MIT | HNSW / IVF / PQ (+ IVFPQ, IVFSQ) | a *library*, not a service: the index math reference (arXiv:1702.08734, "Billion-Scale Similarity Search with GPUs" — Johnson, Douze, Jégou; IEEE Trans. Big Data 2021 [F: arXiv API + dblp 2026-08-30]); persistence is file serialization only (`write_index`/`read_index` [F: source]), no metadata filtering, no service layer |

## The axes that actually differ

**1. Filtering.** This is where vector stores diverge most. "Find me vectors
WHERE tenant_id = 42 AND access_level ≥ 3" can be:
- **pre-filter** (filter → then ANN walk): precise, but an over-selective
  filter can starve the ANN graph → recall collapses *silently*;
- **post-filter** (ANN top-k → then filter): fast, but the *true* top-k may
  have been filtered out of the candidates → under-recall;
- **filtered traversal** (Qdrant-class): the filter is part of the HNSW
  walk itself — the middle path, at a cost per filtered hop [I: the
  cost/recall trade-off is the whole design space; measure on your filters].
Multi-tenant systems (49) live or die on this axis.

**2. Hybrid search.** BM25 + dense, fused (13): Elasticsearch and OpenSearch
ship RRF with `rank_constant` default 60 [F: vendor docs, ES + OpenSearch
blog]; Qdrant offers RRF/DBSF fusion [F: vendor docs]; Weaviate's hybrid is an
`alpha`-weighted BM25+vector blend, not RRF [F: vendor docs]; pgvector brings
the lexical half via Postgres FTS (`ts_rank`-based — *not* BM25; true BM25 in
Postgres needs e.g. ParadeDB pg_search or an external retrieval half) and you
fuse in the app; Vespa does both natively. The fusion is *your* design decision
in most systems (13).

**3. Scale model.** Single node in RAM (Chroma, small pgvector) → sharded
(Milvus, Vespa, Elasticsearch clusters) → serverless (Pinecone). 08's memory
math decides which tier: N=1M × 1024-d float32 = 3.81 GiB of *vectors alone*
[E] — a laptop RAM question today, a cluster question at 100M.

**4. Ops surface.** pgvector = "one more Postgres extension" (you already
have the HA/backup/ACL story). Dedicated stores = one more stateful service
(each with its own sharding story). The right answer tracks your *existing*
stack, not the benchmark.

## The decision pattern [I: the shape, not a ranking]

- **Already on Postgres + moderate corpus + relational filters dominate** →
  pgvector (0.8.x [F]) — HNSW for the vector path, SQL for everything else.
- **Filters are the product** (multi-tenant, per-tenant ACLs) → Qdrant-class
  filtered traversal, or Vespa.
- **Already on Elasticsearch** → dense_vector + RRF; the hybrid half is free.
- **Need the most index options / GPU / lake-scale** → Milvus.
- **Zero-ops managed** → Pinecone (accept the proprietary tier).
- **Prototype / embedded / in-process** → Chroma.
- **Index math reference / custom system** → FAISS (library; you own the
  persistence and filtering).

## What "the same ANN" does NOT mean
Two stores with "HNSW" will measure differently on: filtered recall, update
paths (pgvector HNSW is append-friendly but rebuild-on-change is the honest
ops mode [I]), persistence format, and hybrid fusion. Benchmark claims about
"a vector database" without naming the filter shape, update pattern, and
hardware are not comparable (56: "benchmark without protocol").

## Key Takeaways
1. The ANN index is commoditized behind the API; the differentiators are
   filtering semantics, hybrid fusion, scale model, and ops.
2. License/ops reality (verified 2026-08-30): pgvector 0.8.x, Weaviate
   BSD-3, Qdrant/Milvus/Vespa/Chroma Apache-2.0, Pinecone proprietary, FAISS
   MIT.
3. Pick on *corpus shape + existing stack*, not ANN microbenchmarks.
4. Every "default parameter" claim is a system claim: e.g. Elasticsearch and
   OpenSearch both default RRF `rank_constant` to 60 [F: vendor docs]; FAISS's
   M is caller-supplied [F: source], efSearch defaults to 16 [F: HNSW.h].

## Related
[06 IR foundations](06-information-retrieval-foundations.md) ·
[07 embedding engineering](07-embedding-engineering.md) ·
[08 vector search & ANN](08-vector-search.md) · [12 metadata](12-metadata-engineering.md) ·
[13 hybrid](13-hybrid-rag.md) · [44 economics](44-rag-economics.md) ·
[49 multi-tenant](49-multi-tenant-rag.md) · [51 reference architecture]
(51-production-rag-reference-architecture.md)
