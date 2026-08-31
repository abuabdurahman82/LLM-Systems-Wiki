# Real-Time / Streaming RAG — When the Corpus Never Stops Moving

`LAST_UPDATED: 2026-08-29` · Status: core page · Engineering-reasoning page;
stream-system patterns are [I] unless a system is cited.

## 30-Second Explanation
Most RAG corpora change on the order of days-to-weeks (a doc gets updated);
real-time corpora change on the order of *milliseconds-to-minutes*: logs,
metrics, market data, security events, news, IoT telemetry, operational
databases. The failure mode they expose: **the index is a snapshot, and "the
last 5 minutes" may not be in it at all**. Streaming RAG makes freshness a
first-class, measured property: every chunk carries the time it was true, and
the pipeline decides per query whether retrieval must see the stream.

## What "real-time" means, precisely
| Source class | Cadence | "The answer" is | Retention |
|---|---|---|---|
| Logs | continuous, high-rate | recent events matching a predicate | seconds → hours (hot), longer (cold) |
| Metrics | continuous, sampled | current/recent values + trends | short (aggregated) |
| Market data | tick-level | last trade/quote | seconds → historical |
| Security events | event-driven | active incidents, IOC matches | incident lifetime |
| News | bursts | the current story | days (fast decay) |
| IoT | continuous | latest device state | sliding window |
| Operational DBs | transactional | committed state (not "recent changes") | forever (it is the DB) |

Note the last row: operational databases are *always current* — querying them
is not "streaming RAG", it is structured RAG (30). Streaming RAG is for
**event streams that are too high-volume to query directly and too fast to
batch-reindex**.

## The architecture
```
Event streams (logs, metrics, market, events)
   ↓ Ingestion (Kafka-class topic / ingest API)
   ↓ Windowed chunking (per-event, per-minute window, per-incident)
   ↓ Embedding (fast embedding model — latency budget here, not at query time)
   ↓ Index with TTL (add + expire; or tiered: hot vector store + cold archive)
   ↓ Query:
   │    recent-window?  → query the HOT tier (last N minutes) — or the stream store directly
   │    older?          → query the archive/index
   ↓ Merge + time-aware rerank (newer ≠ better, but "as of now" matters)
   ↓ LLM (answer with "as of <timestamp>")
```

The two design axes:
1. **Hot/cold split**: a small, fast, expiring hot tier for "the last N
   minutes" plus a durable cold index for history. Most production streaming
   RAG is this [I]. N is set by the question class: "what changed in the last
   hour?" needs a hot tier of ≥1h; "why did latency spike at 09:32?" needs the
   cold index + a stream-store lookup.
2. **Query the store vs query the index**: for very fresh data, skip the vector
   index entirely and run a predicate query over a *query-capable* stream layer
   (ksqlDB/Flink/SIEM-class, fed by the Kafka topic — a raw topic is an
   append-only log and does not answer predicates) — that is structured
   retrieval (30) and has no embedding latency.
   The vector index is for *semantic* search over the recent past ("events that
   look like last Tuesday's incident").

## Freshness, TTL, and cache invalidation
- **TTL per chunk class**: news chunks expire in hours (data retention: days —
  the retrievability TTL is the shorter one); log chunks in minutes;
  config docs in days. Expiration is a metadata field, not a rebuild (12) —
  but expired vectors stay physically present in the ANN index until
  compaction/eviction prunes them, so a hot tier also needs that step
  (degraded latency/recall over accumulated dead vectors).
- **Freshness as a measured SLI**: "the p99 age of evidence served" — the gap
  between event time and when a query can retrieve it. For incident response
  that SLI is seconds; for market data it is microseconds (which is when you
  stop using LLM-mediated RAG and use the data system directly [I]).
- **Cache invalidation is by event time**: any answer cached at time T is stale
  the moment the stream advances past T for the relevant scope — the retrieval
  cache key must carry the stream position (offset/watermark), not just the
  query string (42).
- **Incremental indexing**: append-only updates, no rebuilds; the ANN index's
  update path (08: HNSW online inserts) is what makes this tractable.
  Rebuilds are a last resort (corpus-wide re-embedding) with a rebuild budget
  [I].

## Failure modes specific to the streaming case
1. **Index lag**: the query arrives before the event is indexed → "not found"
   for a true event. Mitigate with the hot tier + store-query fallback;
   report "as of T" rather than pretending.
2. **Backfill gaps**: pipeline downtime loses a window; events that never got
   embedded are un-searchable *via the vector index* until backfilled from the
   stream store / cold archive (the raw events are retained, so semantic
   searchability is recoverable, not permanently lost). Mitigate with
   store-query over the gap + an ingestion-lag metric (50).
3. **Storms**: an incident generates 1000× the normal event rate; embedding
   throughput saturates. Backpressure: sample/downstream-prioritize (security
   events > debug logs), shed semantic indexing for hot-window predicate
   queries, scale embedding workers [I].
4. **Time confusion in generation**: the LLM mixes "current" and "historical"
   evidence. Always pack timestamps into chunks ("[2026-08-29 14:02 UTC]") and
   instruct the model on as-of semantics [I].
5. **TTL too long**: stale-but-present evidence gets cited as current. The
   failure is the mirror of #1 — the answer is in the index but was true 3 days
   ago and the user assumed "now".

## Key Takeaways
1. Real-time RAG is for event streams that are too fast to batch-reindex and
   too high-volume to query directly; operational DBs are just structured RAG.
2. Hot/cold tiering + time-scoped retrieval is the standard architecture [I];
   "as of T" must be a property of every answer.
3. Freshness is an SLI (p99 evidence age) and ingestion lag is an alert.
4. Caches key on stream position, not just query string — or you serve stale
   evidence (42).
5. Storms break embedding throughput: backpressure, sampling, and store-query
   fallback are the survival kit.

## Related
[30 structured data](30-structured-data-rag.md) · [34 web RAG (news)](34-web-rag.md) ·
[42 caching](42-rag-caching.md) · [50 observability](50-rag-observability.md) ·
[47 failure taxonomy](47-rag-failure-modes.md) · `../Inference/Continuous-Batching.md`
