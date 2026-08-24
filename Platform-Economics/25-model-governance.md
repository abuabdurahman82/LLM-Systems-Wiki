# 25 — Model Governance

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

A platform that lets anyone deploy any model is asking for cost, security, and
legal trouble. **Model governance** runs every model through a **lifecycle** —
request → evaluation → approval → registry → deployment → monitoring →
re-evaluation → retirement — and records a fixed set of metadata about it. The
result is a **model registry** that is both the *catalog* of what may be served
and the *source of truth* for entitlements ([26-model-access-control](26-model-access-control.md)),
cost ([10-model-economics](10-model-economics.md)), and hardware placement.

## Model lifecycle

```
Request
  ↓
Evaluation      (quality, safety, security, cost benchmark)
  ↓
Approval        (who approves: see [40-llm-platform-governance-model](40-llm-platform-governance-model.md))
  ↓
Registry        (metadata record; versioned)
  ↓
Deployment      (to approved pools/deps)
  ↓
Monitoring      (quality, latency, cost, safety in prod)
  ↓
Re-evaluation   (on new evidence / newer models / pricing change)
  ↓
Retirement      (off-ramp: traffic cutover, deletion)
```

## The model record

For each model the registry should capture:

| Field | Purpose |
|---|---|
| model owner | who to contact / accountable |
| license | legal constraint (open-weights vs commercial) |
| version | exact artifact |
| provider / source | where it came from |
| training source (where known) | transparency / provenance |
| security review | vulnerability/red-team status |
| evaluation score | quality evidence ([Evaluation-Engineering/](../Evaluation-Engineering/README.md)) |
| approved use cases | what it may be used for |
| prohibited uses | what it must not be used for |
| context limit | max tokens |
| cost | $/token or $/request basis ([10](10-model-economics.md)) |
| hardware requirement | GPU pool / min memory for placement |
| deployment date | when it went live |
| retirement date | planned/actual end |

## Why this feeds everything

- **Access control** ([26](26-model-access-control.md)) reads *approved use cases / prohibited uses*.
- **Routing** ([11](11-economic-model-routing.md)) reads *cost* and *quality*.
- **Placement** ([46-gpuaas-pricing](46-gpuaas-pricing.md)) reads *hardware requirement*.
- **Procurement/legal** reads *license* and *training source*.
- **Retirement** is scheduled, avoiding zombie models serving stale/expensive
  hardware ([55-governance-antipatterns](55-governance-antipatterns.md): "no retirement process").

## Governance notes [I]

- **Who approves** is a governance decision ([40](40-llm-platform-governance-model.md)) —
  separate the *technical* gate (evaluation) from the *policy* gate (approval).
- **Monitor in prod**, not just pre-deploy: quality/cost drift triggers
  re-evaluation ([Production-Operations/24-quality-observability](../Production-Operations/24-quality-observability.md)).
- **Version artifacts immutably** — "model:latest" in a registry is a liability;
  pin versions for reproducibility and retirement.

## Related

[26-model-access-control](26-model-access-control.md) ·
[40-llm-platform-governance-model](40-llm-platform-governance-model.md) ·
[10-model-economics](10-model-economics.md) ·
[Evaluation-Engineering/](../Evaluation-Engineering/README.md) ·
[55-governance-antipatterns](55-governance-antipatterns.md)

## Key takeaways

1. Run models through a governed lifecycle: request → eval → approve → register → deploy → monitor → re-eval → retire.
2. The registry record (owner, license, cost, limits, uses, dates) powers access, routing, placement, and legal.
3. Separate technical evaluation from policy approval.
4. Never strand a model in production without a retirement path.
