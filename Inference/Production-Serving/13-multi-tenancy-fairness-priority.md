# Multi-Tenancy, Fairness & Priority
`LAST_UPDATED: 2026-08-22` · Status: core page · The social layer on top of
[03](03-estimating-remaining-work.md) (scoring) and
[10](10-admission-control-and-overload.md) (admission).

## 30-Second Explanation
Pure latency-optimal routing starves small tenants: a tenant sending one
request into a pool saturated by another tenant's agentic fan-out would get
the worst of every queue. Production routers therefore add a **fairness
dimension**: per-tenant shares of pool capacity, enforced at admission and in
queue position — while keeping the per-request ERW placement within the
tenant's allowed set.

## The three fairness surfaces
1. **Admission (L0/L1)**: per-tenant quotas in *tokens* (RPM *and* TPM —
  a request-count quota is gameable by prompt length, see 02). LiteLLM's
  RPM/TPM virtual keys are the L0 version of this [F: gateway config in the
  running example].
2. **Queue position (L1)**: weighted fair queueing across tenants — each
  tenant's queued tokens get service proportional to their share, so one
  tenant's burst delays itself, not others. llm-d implements a flow-control /
  fairness stage in its EPP pipeline [F].
3. **Cache (L1/L2)**: prefix caches are shared state with cross-tenant
  externalities — tenant A's long-context storm can evict tenant B's hot
  system prompt. Mitigate with per-tenant cache trees or per-tenant replica
  home sets (08); open problem in the deep-dive §9.

## Priority vs fairness
They solve different problems and compose:
- **Fairness** is horizontal: tenants with equal shares get equal service
  *quality* over time.
- **Priority** is vertical: request classes (interactive > batch) get
  different SLO targets and admission thresholds, *within and across*
  tenants.
A clean implementation: tenant shares decide whose *queue token* goes first;
priority class decides the SLO the admission check uses (10). GIE exposes
"serving priority" per model for exactly this class separation [F].

## SLO classes
Define a small set (2–4) of classes with explicit TTFT/TPOT targets, e.g.
`interactive` (TTFT 500 ms), `standard` (2 s), `batch` (best-effort). Routing
uses the class as a filter+weight (03's `w_slo` term); admission uses it as
the deadline; autoscaling reports goodput per class (11, 12). Per-class pools
are the extreme version (full isolation, worst utilization); shared pools
with per-class admission thresholds are the usual compromise.

## The agentic wrinkle
Agents violate the tenant-as-stationary-stream assumption: one agent run is a
*correlated burst* of requests (fan-out, retries, long outputs) with heavy
shared prefixes. Fair policies that ignore this either throttle a single
agent run mid-task (breaking latency expectations within the run) or let one
run starve the pool. Practical answer: quota at the *run* level (token budget
per agent run), plus cache-aware placement that keeps a run's shared prefix
warm (08), plus per-run concurrency caps
(`../../Agents/Agent-Loops-and-Reasoning-Strategies.md`).

## 80/20
Per-tenant TPM quotas at the gateway + a weighted-fair-queue on queued tokens
at the router + per-tenant cache namespaces. That trio covers the noisy-
neighbor failures that actually happen.

## Failure modes
- **Quota gaming via shape**: RPM-only quotas let a tenant multiply load with
  long prompts/outputs; enforce token budgets.
- **Starvation by ERW**: pure latency scoring always prefers the biggest
  pending workload's best placement; without fairness weights, small tenants'
  P99 degrades as big tenants grow.
- **Cache bleed**: cross-tenant prefix sharing is a correctness/privacy risk
  in multi-tenant prefix caches; isolate per tenant where required.
- **Priority inversion via preemption**: engines preempting low-priority
  running work to admit high-priority requests can livelock if admission is
  too permissive (10).

## How to measure it
- Per-tenant goodput and SLO attainment (fairness = flat attainment across
  tenants at equal shares).
- Queue-delay attribution: how much of tenant A's wait is caused by tenant
  B's tokens ahead of it.
- Cross-tenant eviction events on hot prefixes.

## Related
[10-admission-control-and-overload](10-admission-control-and-overload.md) ·
[08-cache-aware-routing](08-cache-aware-routing.md) ·
[12-observability-and-slos](12-observability-and-slos.md) ·
`../../Agents/Multi-Agent-Systems.md` ·
`../Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md` §3.6/§9

## Key Takeaways
1. Latency-optimal ≠ fair: add tenant shares at admission and in the queue,
   or small tenants starve.
2. Quotas in tokens, not requests; priority classes as admission deadlines.
3. The prefix cache is a fairness surface too — isolate it per tenant.
