# 35 — RAG Reliability (RAG SRE)

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

RAG makes answers depend on *fresh, correctly retrieved* context. Its failure
modes are mostly **silent** — the system answers confidently from missing, stale,
or wrong documents. RAG SRE is about freshness, retrieval, grounding, and the
data pipeline, with their own SLOs.

## RAG failure modes

| Mode | What it is | Effect |
|---|---|---|
| **Index freshness** | index lags the source data | answers from old info |
| **Retrieval latency** | lookup too slow | adds to T_total ([05](05-production-latency-debugging.md)) |
| **Missing documents** | correct doc not retrieved | hallucination / wrong answer |
| **Bad embeddings** | embedding drift/mismatch | poor recall |
| **Vector DB availability** | store down/slow | outage, error, fallback needed |
| **Chunking regressions** | chunking change breaks retrieval | recall/grounding loss |
| **Reranker failures** | reranker broken/slow | order/quality degradation |
| **Grounding quality** | answer not supported by context | hallucination despite retrieval |

## The three SLO planes (`[I]`)

| SLO plane | What it targets | Example (illustrative `[A]`) |
|---|---|---|
| **Data pipeline SLO** | index freshness/latency | "documents reflected in index within X of publish" |
| **Retrieval SLO** | lookup speed + availability | "P95 retrieval latency < Y, recall > threshold on eval set" |
| **Quality SLO** | groundedness of final answers | "groundedness ≥ Z on eval set" |

Grounding is *the* output SLO: even with fast, available retrieval, a RAG system
can answer ungrounded if retrieval missed the right context.

## Operational practice (`[I]`)

1. **Monitor freshness** — index lag vs source, last-update timestamps, age of
   served docs.
2. **Monitor retrieval** — latency, recall on a labeled eval set
   (`Evaluation-Engineering/RAG-Evaluation.md`), vector-DB health.
3. **Monitor grounding** — judge/checks that answers stay within retrieved context
   ([24](24-quality-observability.md)).
4. **Alert on pipeline stalls** — an index that stops updating is silent until
   someone notices stale answers ([22](22-alerting-strategy.md)).
5. **Version the index & embedding** — so a retrieval regression is attributable
   and rollback-able ([25](25-model-release-engineering.md)).
6. **Plan for vector-DB outage** — RAG fallback (replica/fresher index/context-less)
   with declared degradation ([15](15-model-fallback-and-resilience.md), [13](13-overload-protection.md)).
7. **Watch for poisoning** — validate/trust source of indexed content
   ([09](09-llm-failure-taxonomy.md)).

## Related

`05-production-latency-debugging.md` · `13-overload-protection.md` ·
`24-quality-observability.md` · `RAG/README.md` ·
`Evaluation-Engineering/RAG-Evaluation.md` · `Labs/12-create-a-production-incident-and-postmortem.md`

## Key takeaways

1. RAG failures are mostly silent — wrong/stale/missing context behind confident answers.
2. Track index freshness, retrieval latency/recall, and grounding quality.
3. Separate SLOs: data pipeline, retrieval, quality(grounding).
4. Version the index/embedding; plan for vector-DB outage with fallback.
