# 37 — Disaster Recovery

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

Disaster recovery answers: **what must be recoverable, how fast (RTO), and with
how much loss (RPO)?** The counterintuitive LLM-specific truth: **GPU compute is
easy to replace; state and artifacts are not.** A DR plan that can re-provision
GPUs but has lost the prompts, adapters, indexes, and eval sets is not recoverable.

## The core terms

| Term | Definition |
|---|---|
| **RTO** (Recovery Time Objective) | how long until service is restored |
| **RPO** (Recovery Point Objective) | how much data loss is acceptable on recovery |

Both are *your* choices (cost trade-off): tighter RTO/RPO cost more to sustain.

## What must be recoverable

| Artifact | Why it matters | DR concern |
|---|---|---|
| **Model weights** | the core asset | versioned/backed up; re-download or image-snapshot |
| **Configuration** | engine/router/harness config | version-controlled, reproducible |
| **Prompts / system prompts** | behaviour lives here | version-controlled like code ([25](25-model-release-engineering.md)) |
| **LoRA adapters** | fine-tuned behaviour | store with weights + metadata |
| **Vector indexes** | RAG correctness | rebuildable OR snapshot; freshness SLO ([35](35-rag-sre.md)) |
| **Logs** | audit + postmortem + eval input | retained, restorable ([23](23-llm-tracing.md)) |
| **Evaluation datasets** | quality gates & root-causing | versioned, contamination-free ([28](28-llm-regression-testing.md)) |
| **Routing policies** | placement/eligibility | version-controlled |

## The asymmetry

```
GPU compute  — replaceable (provision new nodes)
State        — may NOT be replaceable (prompts, adapters, indexes, eval sets, logs)
```

A disaster plan centered only on "spin up GPUs again" fails if the *state* the
system needs to be correct is gone. Back up the artifacts above to a location
that survives the region/site failure ([36](36-multi-region-llm-reliability.md)).

## DR practice (`[I]`)

1. **Inventory artifact → owner → backup target → RPO/RTO.**
2. **Version everything** (weights, config, prompts, indexes, policies, eval sets).
3. **Test recovery, not just backup** — restore into a scratch environment and
   run regression gates ([28](28-llm-regression-testing.md)); a restore you
   haven't tested is a hope.
4. **Declare RTO/RPO per artifact** and by severity tier (hot for config/prompts,
   warm for weights, etc.).
5. **Chaos-test DR** — simulate a site loss ([29](29-chaos-engineering-for-llms.md))
   and measure actual RTO/RPO vs declared.
6. **Logs/eval/data sovereignty** applies at rest/restore too ([36](36-multi-region-llm-reliability.md)).

## Related

`28-llm-regression-testing.md` · `29-chaos-engineering-for-llms.md` ·
`35-rag-sre.md` · `36-multi-region-llm-reliability.md`

## Key takeaways

1. RTO = time to restore, RPO = acceptable loss — your explicit choices.
2. GPU compute is replaceable; state and artifacts may not be.
3. Recover models, config, prompts, adapters, indexes, logs, eval sets, routing policies.
4. Test the *restore*, version everything, and chaos-test actual RTO/RPO.
