# 36 — Multi-Region / Multi-Site LLM Reliability

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

Multi-region adds *regional independence* so a single site's failure doesn't take
the service down. For LLMs this is harder than for stateless web apps: models are
**heavy and expensive to replicate**, KV/session state may be **regional**, and
data sovereignty can **prohibit** cross-region routing. Trade-offs must be
explicit.

## Topologies

| Topology | Reading | LLM implications |
|---|---|---|
| **Active/active** | all regions serve traffic simultaneously | needs model replicas + router with cross-region health + cache/session handling |
| **Active/passive** | standby region takes over on failure | cheaper; must handle failover latency + state promotion |

## The hard parts

| Challenge | Why it's hard for LLMs |
|---|---|
| **Model weights** | replicating multi-hundred-GB weights to every region is expensive and slow |
| **GPU capacity** | each region needs real GPU capacity (capacity planning per region, [07](07-llm-capacity-planning.md)) |
| **KV state** | a session's prefix cache lives on one replica; cross-region move is costly ([12](12-kv-cache-reliability.md)) |
| **Sessions** | multi-turn state is regional → session affinity or state sync |
| **RAG state** | vector DB/index per region; freshness consistency ([35](35-rag-sre.md)) |
| **Data sovereignty** | legal/regulatory limits on where data (prompts/outputs) can be processed |
| **Latency** | routing to the wrong/heavy region adds T_network ([05](05-production-latency-debugging.md)) |
| **Cost** | duplicating capacity is expensive ([33](33-cost-as-an-sre-signal.md)) |

## Design decisions (`[I]`)

1. **What is replicated vs regional?** Weights usually replicate (with care); KV
   and sessions often stay regional; indexes replicate with freshness SLOs.
2. **Routing policy** — route by user region (sovereignty + latency), with
   failover to another region only when the local one is down and sovereignty
   allows ([16](16-routing-failure-modes.md), [15](15-model-fallback-and-resilience.md)).
3. **Data location rules** — enforce at the gateway: where may this request's
   content be processed? (sovereignty gate before routing).
4. **Regional failover** — declare RTO/RPO per artifact ([37](37-disaster-recovery.md));
   a passive region must be *proven* to actually serve (chaos-test the failover,
   [29](29-chaos-engineering-for-llms.md)).
5. **Cost trade-off** — active/active × N regions × model size is real; decide
   what *must* be multi-region vs what is acceptable single-region with good DR.

## Related

`15-model-fallback-and-resilience.md` · `16-routing-failure-modes.md` ·
`37-disaster-recovery.md` · `12-kv-cache-reliability.md` · `35-rag-sre.md`

## Key takeaways

1. Multi-region gives regional independence but is expensive and hard for LLMs.
2. Active/active serves everywhere; active/passive fails over.
3. Hard parts: weights, GPU capacity, KV/sessions, RAG state, sovereignty, latency, cost.
4. Decide what replicates vs stays regional; enforce sovereignty at the gateway;
   prove failover under chaos.
