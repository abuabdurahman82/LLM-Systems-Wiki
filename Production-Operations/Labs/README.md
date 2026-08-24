# Production Operations Labs — Safe Hands-On Reliability Practice

`LAST_UPDATED: 2026-08-23` · Status: labs index

12 hands-on labs that exercise SRE & production-ops skills for LLM systems using
**safe synthetic workloads**. They pair with the pages:
`Production-Operations/01`–`41`.

## ⚠️ Safety first

- **Do NOT interfere with existing production-like home-lab services** (the
  Hermes agent's serving models, the Wiki's evaluator models, or any workload you
  did not create for these labs) **without explicit confirmation.**
- Use **synthetic/loop-back workloads**, private ports, and local-only clients.
- Prefer read-only checks before any mutating step.
- Where a lab touches a real endpoint it says so and requires you to opt in.

## The labs

| # | Lab | Skill | Page |
|---|---|---|---|
| 1 | [Measure TTFT and TPOT](01-measure-ttft-and-tpot.md) | latency measurement | 05 |
| 2 | [Generate concurrency: 1/2/4/8/16](02-generate-concurrency.md) | load + plotting | 04/05 |
| 3 | [Create an overload condition safely](03-create-an-overload-condition.md) | overload + ρ | 08 |
| 4 | [Implement admission control](04-implement-admission-control.md) | admission | 13 |
| 5 | [Simulate replica failure](05-simulate-replica-failure.md) | failover | 16/29 |
| 6 | [Test model fallback](06-test-model-fallback.md) | fallback | 15 |
| 7 | [Build a Prometheus dashboard](07-build-prometheus-dashboard.md) | observability | 20/21 |
| 8 | [Monitor GPU with DCGM](08-monitor-gpu-with-dcgm.md) | GPU telemetry | 10/20 |
| 9 | [Simulate a retry storm](09-simulate-retry-storm.md) | retries | 14 |
| 10 | [Calculate an error budget](10-calculate-an-error-budget.md) | error budgets | 02/06 |
| 11 | [Canary a configuration change](11-canary-a-configuration-change.md) | canaries | 25/27 |
| 12 | [Create a production incident & postmortem](12-create-a-production-incident-and-postmortem.md) | incident mgmt | 30/32 |

## Suggested order

01 → 02 → 10 (measurement + budgets), then 03 → 04 → 09 (overload/retries), then
05 → 06 (failover/fallback), then 07 → 08 (observability), then 11 → 12 (release
+ incident).

## Tools you'll use

Python `httpx`/`requests` + standard lib; `curl`; optionally `locust`/`hey` for
load; docsify-local or Grafana for dashboards; DCGM/dcgm-exporter where GPUs are
present. All samples are synthetic and self-contained.

## Provenance

Labs use synthetic data; any `[E]` numbers you produce on *your* box are yours.
Interpretations are `[I]`. No fabricated benchmark or product numbers.
