# Vector Search — Exact, Approximate, and the ANN Trade-Off

`LAST_UPDATED: 2026-08-29` · Status: core page · Algorithmic descriptions are
standard; FAISS default parameters and library facts are cross-checked against the
research bank (`/tmp/rag-research/B-ir-embeddings-dbs.md`).

## 30-Second Explanation
Vector search answers: given query vector **q**, find the k most similar of N
vectors. **Exact k-NN** computes similarity against every vector — O(N·d) per
query, correct, and too slow past ~100K vectors. **Approximate nearest
neighbor (ANN)** builds an index that trades a controlled amount of recall for
orders of magnitude in speed. The design axes: **recall** (did I find the true
neighbors?), **latency** (per query), **memory** (index footprint), **build
time**, and **update cost** (how expensive are inserts/deletes). HNSW is the
default workhorse; IVF+PQ is the memory-saver; flat is the baseline/audit tool.

## Exact nearest neighbor
Brute force: for each of N vectors compute ⟨q, v⟩ (or ‖q−v‖²) and keep the top
[E: for N=1M, d=1024 that is 1e9 multiply-accumulates per query — a single
modern GPU handles ~1e11–1e12 MAC/s, so GPU exact search is ~1–10 ms (and is
memory-bound anyway: 3.8 GiB of vectors read at ~2 TB/s ≈ 2 ms); CPU is
~100× slower [I: rough estimate], i.e. seconds]. Flat indexes (FAISS
`IndexFlat*`) store raw vectors and scan everything. (pgvector has no index by
default — an un-indexed `vector` column is exactly such a scan; its `ivfflat`/
`hnsw` options are ANN indexes, covered below.) Use exact search when: N is small (<~100K),
vectors change constantly (no index to maintain), or you need a ground truth to
measure ANN recall against.

## The ANN problem and its metrics
ANN structures skip most of the space. Recall@k = (true top-k ∩ returned top-k)
/ k, measured against exact search on a probe set. Production ANN recall is
typically 0.90–0.99 [I: engineering experience, not a universal constant] —
and the number that matters downstream is the *system's* retrieval recall@k on
real queries (45), because the ANN layer's small recall loss compounds with the
retriever's relevance errors.

## HNSW — the hierarchical navigable small world
A layered graph. Bottom level: every vector connected to up to **M** neighbors
(up to **2M** at level 0 — `M_max0 = 2M`, the cap in the HNSW paper and the
reference implementations; upper levels cap at M) via a *heuristic* neighbor
selection, so the graph is a pruned kNN graph. Upper levels: a coarser subset,
each level holding ~**1/M** of the nodes of the one below (level assignment
P(level ≥ k) = M^−k, from mL = 1/ln M). Search: enter at the top-level entry
point, greedy-walk to the best node, drop down a level, repeat; at level 0 run
beam search with width `ef`.

```
level 2:   o ─────── o        (~N/M² nodes, long edges)
                \     /
level 1:   o ── o ── o ── o   (~N/M nodes)
                 \ | /
level 0:  o-o-o-o-o-o-o-o-o   (all N nodes, up to 2M edges each)
```

Parameters: **M** (degree cap at upper levels; level 0 allows up to 2M; higher
M = more memory + more recall per search) and **efConstruction** (beam width
while building the graph; higher = better graph, slower build) and at query
time **efSearch** (beam width during search; must be ≥ k). In FAISS, M is
caller-supplied (no built-in default); the HNSW search state defaults to
efSearch=16 [F: faiss source (HNSW.h/HNSW.cpp), checked 2026-08-30]; the
M=32/efConstruction=400 pair sometimes quoted is a *practical* configuration,
not a FAISS default [UNVERIFIED as a "default"].

**Why it works:** the layered structure gives logarithmic-scale *funneling* —
the top levels get you near the answer in few hops, the bottom levels refine it.
Empirically it beats most alternatives at high recall with moderate memory
[I: standard result across FAISS benchmarks; no single universal winner].

**Memory model** [E, machine-verified] — N=1M, float32, average-case degree M
(the level-0 cap is 2M, so a worst-case graph is up to 2× these figures —
average degree is well below the cap in practice):
| dim | vector bytes | M=32 graph (avg) | M=16 graph (avg) | overhead (M=32, avg) |
|---|---|---|---|---|
| 384 | 1.43 GiB | ~122 MiB (+~1 MiB upper) | ~61 MiB | ≈ 8.4% |
| 1024 | 3.81 GiB | ~122 MiB (+~1 MiB upper) | ~61 MiB | ≈ 3.1% |

(Level 0 graph ≈ N×M×4 bytes at average degree M; upper levels ≈ N×4×Σ_k(1/M)ᵏ —
for M=32 that's ~1 MiB, i.e. ~0.8% of the level-0 graph.)

**Update cost:** inserts are online-friendly (no rebuild); deletions are
*logical* (tombstones) until compaction — a churning corpus needs a compaction
policy. This is why HNSW is the default choice for production vector stores.

## IVF — inverted file clustering
Partition the space into **nlist** Voronoi cells (k-means centroids). Search:
compute distance to all centroids (cheap: nlist ≪ N), pick the **nprobe**
closest cells, exact-scan only their members. nprobe is the recall/latency dial.
IVF alone is coarse (cell boundaries cut true neighbors); it is usually
*combined* with PQ:

## Product Quantization (PQ) — compressing the vectors
Split a d-dim vector into **m** sub-vectors of dim d/m (the PQ "subquantizer
count" m — not the HNSW M above); train a small k-means codebook per
sub-vector; store each vector as m 1-byte sub-centroid ids.
[E: d=1024, m=32 subquantizers × 8 levels → 32 bytes/vector vs 4096 bytes
float32 = 128× compression; 1M vectors: 3.8 GiB → 0.03 GiB.] Distance between
compressed vectors uses precomputed lookup tables (ADC) — fast, but recall
drops vs exact (typical: -1 to -3 points recall depending on sub-quantizer
count) [I]. PQ shines when the corpus doesn't fit in RAM; note the quantization
error is an *approximation bias on the ranking* (reconstruction error, not
zero-mean noise: estimated distances carry a systematic positive bias of order
‖x−x̂‖²), which is exactly where a reranker
(14) can recover lost precision.

**IVF-PQ** = IVF's coarse partition + PQ's compact storage: the classic
"billion vectors on one box" recipe, at the cost of the lowest recall class of
the popular algorithms [I].

## ScaNN / DiskANN and the others
- **DiskANN** (Microsoft — PVLDB 2019 "A New Scaling Approach to Nearest
  Neighbor Search", Subramanya et al. [F: venue PVLDB 2019 vol.12 confirmed
  2026-08-30; no arXiv version on the primary record]):
  graph index over *disk-resident* vectors; one SSD, billion-scale, RAM holds
  PQ-compressed vectors (used to navigate the graph) plus a cache of hot full
  vectors — the "too big for RAM" answer.
- **ScaNN** (Google, arXiv:1908.10396 [F: verified in research bank]):
  anisotropic vector quantization — quantizes for *directional* accuracy
  (cosine) rather than reconstruction; strong recall/latency on CPU.
- **Flat/GPU exact** (FAISS GPU `IndexFlat*`): exact; the audit baseline.
  (FAISS GPU's `IndexIVFPQ`/`IndexIVF*` are *approximate* — do not use them as
  a recall ground truth.)
Do not assume these are equivalent: different quantization objectives, memory
models, and sweet spots [I].

## The trade-off table
| Algorithm | Recall (typical @ 0.9+) | Latency | Memory | Build | Updates | Sweet spot |
|---|---|---|---|---|---|---|
| Flat exact | 1.0 | O(N·d) — slow | raw | none | free | small N; ground truth |
| HNSW | high | ~ms | +~3–8.5% graph (avg degree; up to ~2× at the 2M cap) | moderate | online OK | the default (09) |
| IVF | medium | fast-ish | raw + centroids | k-means cost | incremental add; periodic retrain | medium N, stable corpus |
| IVF-PQ | lower | fast | ~100× smaller | moderate | incremental add; periodic retrain | huge N, RAM-limited |
| DiskANN | high-ish | SSD-bound | RAM: PQ vectors + cache | moderate | append-optimized | billion-scale on 1 box |
| ScaNN | high | fast (CPU) | quantized | moderate | rebuild | CPU serving, cosine |

Cell values are qualitative [I: standard positioning from vendor docs; see 09].

## Connect to vector databases
Every production vector DB is "index + storage + API": HNSW (Qdrant, Milvus,
pgvector, Weaviate, Pinecone, Chroma), IVF/PQ variants (Milvus, FAISS-backed),
DiskANN (Milvus). The index choice is invisible behind the API — which is why
09 compares systems on *filtering, hybrid search, tenancy, ops*, not on the
graph algorithm they all mostly share. And recall: an ANN index with 0.98
recall is *necessary but not sufficient* — the retriever's relevance errors
dominate end-to-end quality (45).

## Key Takeaways
1. Exact search is the audit baseline; ANN is a recall/latency/memory trade,
   not a quality improvement.
2. HNSW (M + efConstruction/efSearch) is the default; IVF-PQ is the memory
   answer; DiskANN is the disk answer.
3. Deletions are logical in graph indexes — plan compaction for churning
   corpora.
4. PQ quantization error degrades ranking; reranking (14) is the recovery
   stage, not the index.
5. Measure *system* retrieval recall on real queries, not probe-set ANN recall.

## Related
[09 vector databases](09-vector-databases.md) · [14 reranking](14-reranking.md) ·
[06 IR foundations](06-information-retrieval-foundations.md) ·
[42 caching](42-rag-caching.md) · `../Inference/Roofline.md` (why exact search
becomes memory-bound)
