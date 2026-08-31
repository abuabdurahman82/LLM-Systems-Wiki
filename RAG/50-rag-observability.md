# RAG Observability — Tracing the Evidence Pipeline

`LAST_UPDATED: 2026-08-29` · Status: core page · Practice page; thresholds are
starting points [I] to be tuned per product, not standards; metric definitions
align with 45 and standard IR (06). Framework facts (RAGAS citation/
faithfulness metrics) [F: 2309.15217, verified in research bank 2026-08-29].

## 30-Second Explanation
Evaluation (45) tells you how good the system is on the golden set;
observability tells you what it is doing *right now*, for *this* query, and
why. The unit of RAG observability is not a span around "the LLM call" — it is
the **evidence pipeline**: which query went in, what the retrievers returned
with which scores, what the reranker kept and dropped, what the context packed,
and what the model answered with which citations. The golden rule: **you cannot
improve what you cannot trace end-to-end, and every answer must be reproducible
from its trace** — query + index version + parameters → the same chunks.

## The monitoring table
Alert thresholds are [I] starting points — tune to your SLOs and traffic; p50/p99
definitions are standard (06's latency-literacy carries over).

| Metric | Unit | Why it matters | Alert threshold [I] |
|---|---|---|---|
| Retrieval latency p50 / p99 | ms | the user-perceived "search is slow" signal; p99 spikes usually mean filtered-search or segment issues (49) | p99 > 300 ms sustained |
| Embedding latency | ms per call | it prefixes *every* request; spikes cascade into total latency; batch-vs-realtime regressions show here | p99 > 50 ms (API) / > 20 ms (local) |
| Reranking latency | ms per batch | cross-encoders are the pipeline's latency budget hog (14) — a model swap doubles this silently | p99 > 1000 ms GPU / > 5 s CPU |
| Generation latency (TTFT) | ms to first token | perceived responsiveness; prefill grows with context tokens (44) | TTFT p95 > 2 s |
| Generation latency (e2e) | ms end-to-end | full-answer time; drives streaming design and UX | p95 > 15 s for long answers |
| Top-k used | count (distribution) | drift in k silently changes cost *and* quality (44); catches config drift between services | any request with k outside [3, configured_max] |
| Retrieval score distribution | cosine/dot (histogram) | drifting score floors = index or model drift; the "usable evidence" gate depends on it | top-1 score p50 shifts > 0.05 week-over-week |
| Index hit rate | % queries with ≥1 usable-evidence chunk (above score floor) | queries with zero usable evidence are pre-failures — L2/L1 incidents waiting to be triaged (47) | < 90% of queries, or any tenant < 80% |
| Context tokens packed | tokens per request | the dominant cost lever (44) and the L4-failure sensor (47); saturation means truncation is happening | p95 > 85% of model budget |
| Citation success rate | % cited chunks that actually support their claim (judge-checked) | faithfulness in production, not just eval (45); low values mean grounded-contract erosion (47 L6) | < 90% sampled |
| Retrieval failure rate | % queries where expected/known evidence missing (sampled audits) | the honest L2 number; golden-set recall does not cover production distribution shift | > 5% on audited sample |
| Vector DB latency + load | ms p50/p99; CPU/mem/QPS | the shared-infrastructure health signal; multi-tenant noisy neighbors show up here (49) | p99 > 100 ms or saturation > 80% |

Pair every system metric with a **quality metric sampled from production** (45):
a weekly audited sample scored for faithfulness and citation success is what
turns dashboards from uptime theater into quality instrumentation [I].

## The trace: one request, end to end

```
USER ──► QUERY REWRITE ──► RETRIEVER(S) ──► RERANKER ──► CONTEXT ──► LLM ──► RESPONSE
            │                   │                │             │          │          │
 log:       │                   │                │             │          │          │
 raw query ●                   │                │             │          │          │
 rewritten ●  rewriter id,     │                │             │          │          │
 history      latency          │                │             │          │          │
              variants (16) ●  per-retriever:  ● model id +  ● chunk ids ● model id, ● answer text,
              ● embedding      k requested,     version       ● prompt hash  params,   citations,
                model +        k returned,      ● per-chunk   ● token      ● TTFT,    abstain flag
                version        scores,          score in/out,   tokens      e2e ms   ● sampled
              ● embed latency  chunk ids,       dropped-by-   ● dedup/               judge score
                (50 ms)        index version    rerank list     packed                (45)
                (50 ms)        ● ANN ms         ● rerank ms     (5120 tok)
                               (5 ms)           (400 ms)        (5120 tok)
```

**What to log at each hop** [I] — the fields that make the trace diagnostic:

| Hop | Log fields | The question it answers later |
|---|---|---|
| Query rewrite | raw query, rewritten query, history ids, rewriter version, variants emitted, latency | did the rewriter change the intent? (47 L1) |
| Query embedding | embedding model + version, embedding latency, vector checksum | same model as the index? (07) |
| Retriever (per source: BM25, dense, web, SQL) | k requested, k returned, chunk ids with scores, retriever params, index version, latency | what did the corpus offer, and from which index build? (47 L2) |
| Reranker | model + version, score in/out per chunk id, **dropped-by-rerank list with both scores**, final order, latency | did ranking keep or lose the evidence? (47 L3) |
| Context assembly | final chunk ids in order, tokens packed, dedup decisions, truncation events, parent expansion, prompt hash | what did the model actually see? (47 L4) |
| LLM | model id, prompt hash, temperature/sampling, TTFT, e2e latency, tokens in/out | what was asked, of what, at what cost? (44) |
| Response | answer text, cited chunk ids, abstain flag, sampled judge scores (faithfulness, citation success) | was the answer grounded and checkable? (47 L6) |

Two fields deserve names: the **dropped-by-rerank list** is the single most
useful diagnostic artifact in the whole trace — it is exactly the L2/L3 boundary
(47), and it is what you diff against expected evidence when someone reports a
miss (45). The **prompt hash** ties a response to the exact evidence set and
template version that produced it — when a regression appears, the hash splits
"template changed" from "retrieval changed" in one query.

## The golden rule: reproducibility from the trace
**Every answer must be reproducible from its trace** [I]: given
(query text + query-rewrite config) × (index version) × (retriever/reranker
parameters) × (context template version), replaying the pipeline returns the
same chunks in the same order. This is a property you build, not hope for:

- **Version everything the trace references**: index build id, embedding model
  version, reranker version, prompt template version (50/51). An un-versioned
  cache or index invalidates every historical trace (42).
- **Store enough to replay**: the rewritten query, full parameters, and the
  chunk ids — not the whole corpus, just the pointers.
- **Replay as a first-class operation**: "show me this answer's chunks today"
  catches staleness (index moved), drift (model swapped), and nondeterminism
  (k changed) in one command [I].
- **Reproducibility is also the audit story** (48, 49): "why did the system
  show this to this user" must be answerable from the stored trace alone,
  months later.

## What observability buys, layer by layer
The trace is the localization instrument for 47's taxonomy [I]:

| Layer (47) | Trace artifact that convicts it |
|---|---|
| L1 query | raw vs rewritten diff; zero-hit lex queries |
| L2 retrieval | retriever chunk ids + scores; index version; empty/we low-score results |
| L3 ranking | dropped-by-rerank list; recall@k curve from logged scores |
| L4 context | tokens packed, truncation events, dedup decisions |
| L5 reasoning | sampled judge scores on multi-hop subsets; evidence-order A/Bs |
| L6 generation | citation success rate; empty-context ablation on sampled queries |

Operationally this closes the loop the evaluation page opened: the golden set
(46) is built *from* production traces — every L2 miss audited in production
becomes a labeled case, every L6 hallucination becomes a faithfulness test case
(45 → 46 → 47). Observability without evaluation has no ground truth;
evaluation without observability has no production coverage [I].

## A worked trace (illustrative)
One request, annotated with typical magnitudes [I: latency values are the
constants-bank typical ranges, not measurements]:

```
trace_id=req_8f31            tenant=acme-corp          index_version=ix-2026-08-24.3
raw_query="what changed in the refund policy for EU customers last quarter?"
rewrite  -> "EU refund policy changes Q2 2026"          rewriter=v3   12 ms
           + variant: "refund policy EU amendment 2026" (multi-query, 16)
retrieve -> BM25: k=50, 8 hits, top score 14.2          4 ms
           dense: model=e5-v2, k=50, 50 hits, top 0.81  6 ms
           fused (RRF): 64 unique chunk ids             1 ms
rerank   -> cross-encoder v5: 64 pairs in, top 12 out  410 ms
           dropped_by_rerank[0] = c_5521 (fused 0.019 -> ce 0.11)
context  -> kept 10 chunk ids, dedup -2, packed 4864 tok, prompt_hash=ph_9c2
generate -> model=m-70b-instruct t=0.2  TTFT 640 ms     e2e 3.9 s
response -> 2 citations [c_1180 s4.2, c_0912 s1], abstain=false
sampled  -> judge: faithfulness 0.94, citation_support 1/2 claimed verified
```

Read it as the 47 taxonomy in motion: the interesting row here is
`dropped_by_rerank[0]` — a chunk the fused retriever ranked well that the
cross-encoder rejected. If a user disputes this answer, that is the first field
the on-call inspects (47's L2/L3 boundary), and the prompt hash `ph_9c2` makes
the exact evidence set replayable.

## Alert wiring: from threshold to action
A threshold without a runbook is decoration [I]. Minimum wiring per alert class:

| Alert fires | First move (47 layer) | Escalation |
|---|---|---|
| Index hit rate drops | L2 — check ingestion dead-letter queue and latest index version | page retrieval owner if a connector failed |
| Retrieval score distribution shifts | L2 — embedding model or index drift; check last deploy of the encoder | freeze deploys; replay golden set (45) |
| Context tokens packed at saturation | L4 — truncation is shipping | raise budget or enable compression (41) |
| Citation success rate falls | L6 — grounded contract erosion or context pollution | sample traces; check prompt-template version drift |
| Vector DB p99 spike with one hot tenant | shared-infra noisy neighbor (49) | apply per-tenant quotas; consider partitioning |

## Implementation notes
- **Sampling with full-fidelity hot paths**: log 100% of failures, slow queries,
  and low-index-hit queries; sample the healthy remainder [I]. Traces are cheap;
  the retrieval+rerank score payload is the part worth keeping complete.
- **Retention budgeting**: keep full traces 30–90 days [I], then aggregate —
  the golden set and audit extracts (46) are what persist long-term, not raw
  chunk payloads.
- **PII and tenancy in traces** (49, 48): traces inherit document sensitivity —
  store chunk ids and scores rather than chunk text where policy requires, and
  scope trace access by tenant.
- **Dashboards mirror the layers**, not the org chart: one panel per hop with
  its metric from the table above; the 47 incident table tells on-call which
  panel to open [I].
- **Correlation ids end to end**: one request id from the front door through
  LLM completion; every hop log carries it (50/51 architecture contract).

## Key Takeaways
1. The unit of RAG observability is the evidence pipeline trace, not the LLM
   span — query → retrievers → reranker → context → LLM → response, with fields
   logged per hop.
2. Golden rule: every answer is reproducible from its trace (query + index
   version + params → same chunks); this requires versioning everything the
   trace references.
3. The dropped-by-rerank list and the prompt hash are the two highest-leverage
   artifacts — they localize ranking failures and tie answers to exact evidence.
4. Monitor cost-and-quality together: context tokens packed is simultaneously
   the dominant cost lever (44) and the truncation sensor (47).
5. Observability and evaluation are one loop: production audits feed the golden
   set, golden-set metrics set the alert thresholds (45 ↔ 50).

## Related
[45 evaluation — the metric stack feeding these dashboards](45-rag-evaluation.md) ·
[51 production reference architecture — where the trace store lives](51-production-rag-reference-architecture.md) ·
`../Production-Operations/README.md` · [47 failure modes — what the trace localizes](47-rag-failure-modes.md) ·
[42 RAG + caching — cache invalidation and trace validity](42-rag-caching.md) ·
[44 RAG economics — the cost fields in every trace](44-rag-economics.md)
