# 29 — Chaos Engineering for LLMs

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

Chaos engineering *safely simulates* failures to learn, before a real incident,
how the system degrades and how operators respond. The goal is not to break
things for fun — it is to **verify hypotheses with bounded blast radius,**
controlled rollback, and full observability.

## What to safely simulate

| Experiment | Simulates | Risk profile |
|---|---|---|
| Kill a replica | replica/instance loss | low — verify failover ([16](16-routing-failure-modes.md)) |
| Kill a GPU worker | worker/rank loss | medium — distributed inference ([11](11-distributed-inference-failures.md)) |
| Network delay | added latency | low—medium — tail behaviour |
| Network partition | split brain/fabric loss | higher — do in staging or with guard |
| Slow storage | index/checkpoint stall | medium |
| Vector DB outage | RAG source down | low ([35](35-rag-sre.md)) |
| Tool outage | tools unavailable | low ([34](34-agent-sre.md)) |
| Model provider outage | downstream API down | low — exercises fallback ([15](15-model-fallback-and-resilience.md)) |
| KV failure / exhaustion | KV pressure | medium ([12](12-kv-cache-reliability.md)) |
| High traffic | overload | medium — do with admission control on ([13](13-overload-protection.md)) |

## Rigor per experiment

For each, define:

- **Hypothesis** — what you expect to happen (e.g. "router fails over to fallback
  within X s, goodput holds").
- **Blast radius** — how far the failure can spread; bound it (single node, staging,
  synthetic traffic only).
- **Expected behaviour** — observable signals that show the system behaving per design.
- **Observability** — which metrics/traces prove the hypothesis ([20](20-llm-observability-stack.md)).
- **Rollback / abort** — the exact button to stop the experiment and restore.

## Safety rules

> **Never recommend destructive experiments against production without controls.**

1. **Start in staging / with synthetic traffic.**
2. **Bound blast radius** — one pod, one node, one dip; never a blind cluster-wide outage.
3. **Guardrails on** — admission control, fallback, circuit breakers active so the
   experiment tests the system, not destroys it.
4. **Define the abort condition** — if X signal breaches (SLO, error spike), stop.
5. **Run in maintenance windows** with on-call present.
6. **Home-lab warning:** do **not** interfere with existing production-like
   home-lab services without explicit confirmation (see `Labs/` front-matter).

## Related

`13-overload-protection.md` · `15-model-fallback-and-resilience.md` ·
`30-llm-incident-response.md` · `31-production-runbooks.md` ·
`Labs/05-simulate-replica-failure.md`

## Key takeaways

1. Chaos verifies hypotheses about failure, under bounded blast radius and with rollback.
2. Every experiment needs hypothesis, blast radius, expected behaviour, observability, rollback.
3. Start in staging; keep admission/fallback/circuit breakers on.
4. Never run uncontrolled destructive experiments on production; respect home-lab boundaries.
