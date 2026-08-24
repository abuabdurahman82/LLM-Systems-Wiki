# 40 — Zero to Hero: LLM Reliability & Production Ops

`LAST_UPDATED: 2026-08-23` · Status: learning path

A levelled route from zero to multi-region AI-platform SRE. Each level names the
concepts (→ page) and suggests practice (→ `Labs/`). Levels build on each other.

## LEVEL 0 — Linux, networking, basic monitoring
CPU/memory/disk, processes, TCP/IP, ports, SSH; `top`, `vmstat`, `netstat`;
what a request is. *Prereq for everything.*

## LEVEL 1 — SLI / SLO / SLA
Measure vs target vs contract; why availability ≠ useful answers
→ [02](02-sli-slo-sla-for-llms.md). Practice: error-budget calc ([Labs/10](Labs/10-calculate-an-error-budget.md)).

## LEVEL 2 — Prometheus / Grafana
Metrics scraping, queries, dashboards. → [20](20-llm-observability-stack.md);
lab [07](Labs/07-build-prometheus-dashboard.md).

## LEVEL 3 — LLM latency metrics
TTFT, TPOT/ITL, E2E; percentiles; the latency budget
→ [05](05-production-latency-debugging.md). Practice: [Labs/01](Labs/01-measure-ttft-and-tpot.md).

## LEVEL 4 — GPU monitoring
`nvidia-smi`, DCGM, DCGM Exporter; ECC/Xid/throttling
→ [10](10-gpu-reliability.md). Practice: [Labs/08](Labs/08-monitor-gpu-with-dcgm.md).

## LEVEL 5 — Queueing & capacity
λ, μ, ρ, Little's Law; sizing in tokens
→ [08](08-queueing-theory-for-llm-sre.md), [07](07-llm-capacity-planning.md).
Practice: [Labs/02](Labs/02-generate-concurrency.md), [Labs/03](Labs/03-create-an-overload-condition.md).

## LEVEL 6 — Autoscaling
Signals that matter (queue/KV/goodput), cold start, predictive vs reactive
→ [17](17-llm-autoscaling-reliability.md).

## LEVEL 7 — Distributed inference reliability
TP/PP/EP/DP failure footprints, straggler, NCCL
→ [11](11-distributed-inference-failures.md).

## LEVEL 8 — Release engineering
Shadow, canary, regression gates, error budgets
→ [25](25-model-release-engineering.md), [27](27-canary-deployment.md), [28](28-llm-regression-testing.md).
Practice: [Labs/11](Labs/11-canary-a-configuration-change.md).

## LEVEL 9 — Chaos & incident management
Safe chaos, incident roles, runbooks, postmortems
→ [29](29-chaos-engineering-for-llms.md), [30](30-llm-incident-response.md),
[31](31-production-runbooks.md), [32](32-blameless-postmortems.md).
Practice: [Labs/05](Labs/05-simulate-replica-failure.md), [Labs/09](Labs/09-simulate-retry-storm.md), [Labs/12](Labs/12-create-a-production-incident-and-postmortem.md).

## LEVEL 10 — Multi-region AI platform SRE
Active/active, DR (RTO/RPO), sovereignty, cost
→ [36](36-multi-region-llm-reliability.md), [37](37-disaster-recovery.md),
[33](33-cost-as-an-sre-signal.md).

## Suggested pace
Levels are roughly sequenced; you can start at 3 if you already run linux servers,
or 5 if you already run LLM inference. The 80/20 ([39](39-llm-sre-80-20.md)) is a
good "what matters most" companion at every level.

## Related

`README.md` · `39-llm-sre-80-20.md` · `41-the-reliable-llm-system.md` ·
`Learning-Path/Zero-to-Hero.md`
