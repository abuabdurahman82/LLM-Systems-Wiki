# Lab 12 — Create a Production Incident & Postmortem

`LAST_UPDATED: 2026-08-23` · `Status: lab` · Paired with [30-llm-incident-response](../30-llm-incident-response.md), [32-blameless-postmortems](../32-blameless-postmortems.md)

## Goal
Manufacture a **bounded, synthetic incident**, run the response loop, and write a
**blameless postmortem** — without touching real services.

## Why
Incident muscle only grows by drilling; a cheap fake incident beats an expensive
real one ([29](../29-chaos-engineering-for-llms.md), [30](../30-llm-incident-response.md)).

## Method — a scripted synthetic scenario
1. Stand up a synthetic endpoint that, after N seconds, **degrades** (TTFT ×3)
   and later emits a GPU-style OOM (`[I]` synthetic — no real GPU involved).
2. Have a dashboard/alert catch it (reuse Lab 7 exporter with a TTFT spike).
3. Assign roles: Incident Commander, Operations, Comms, SME.

### Response loop (30)
- **Detect**: TTFT SLO burn alert fires.
- **Triage**: queue↑? KV↑? GPU event? (correlate signals, [04](../04-llm-golden-signals.md)).
- **Mitigate**: route around the bad replica / shed / fallback ([13](../13-overload-protection.md), [15](../15-model-fallback-and-resilience.md)).
- **Recover**: restore, verify **quality too** ([24](../24-quality-observability.md)).
- **Learn**: postmortem below.

### Postmortem template (32)
```markdown
# Incident <ID> — <Title>
## Summary
## Impact (users/requests/SLO/cost/duration)
## Timeline (timestamped)
## Detection (which alert/dashboard)
## Root cause
## Contributing factors
## What worked / What failed
## Corrective actions (owner + date)
## Prevention
```

## Interpretation
- Practice **mitigate before root-cause** ([30](../30-llm-incident-response.md)).
- In the postmortem, note **both axes**: infra (TTFT/GPU) and, if applicable,
  quality — remember system-health ≠ answer-quality ([24](../24-quality-observability.md)).
- Blameless: fix the system, not the person ([32](../32-blameless-postmortems.md)).

## Safety
100% synthetic — no real workloads or GPUs; keep all "incidents" local and 
labelled as drill (`[I]` synthetic). Do **not** run this against production-like
services without explicit confirmation.
