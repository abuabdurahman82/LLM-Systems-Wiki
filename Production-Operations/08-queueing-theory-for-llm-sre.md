# 08 — Queueing Theory for LLM SRE (the useful 80/20)

`LAST_UPDATED: 2026-08-23` · Status: operational page

> This is the operator's 80/20: the handful of queueing results that explain most
> production latency/capacity behaviour. The deeper treatment lives in
> `Inference/Production-Serving/04-queueing-theory-80-20.md`.

## 30-Second Explanation

Queueing theory is why "keep the GPU at 100%" and "keep P99 low" fight each
other. Demand arrives unevenly; when a resource is nearly full, even a tiny
extra load can explode waiting time. Understanding the three parameters below
explains most overload behaviour.

## The three variables

- **λ** = arrival rate (requests per unit time) — your *traffic*.
- **μ** = service rate (requests per unit time the server can process) — your *capacity*.
- **ρ** = **utilization** = λ / μ — how busy the server is.

## The critical insight: ρ → 1

```
ρ = λ / μ
As ρ approaches 1, mean waiting time grows dramatically (→ ∞ as ρ → 1)
```

For a classic M/M/1 queue, mean time in system W = 1/(μ − λ) = 1/(μ(1−ρ))
`[F]`/`[I]` (standard queueing result). At ρ = 0.5 the queue is tiny; at
ρ = 0.9 a small *increase* in arrival doubles or worse the mean wait. This is
the mathematical reason an LLM platform that runs GPUs at 99% can suddenly fall
off a latency cliff when traffic nudges up.

## Little's Law

Little's Law: **L = λW** — the number of things in the system (L) equals the
arrival rate (λ) times the average time each spends there (W).

Implications:

| Quantity | Little's Law reading |
|---|---|
| GPU utilization | high ρ means high L (work resident) but *also* high W (wait) |
| Queue depth | directly the L that users feel as TTFT/queueing delay |
| Tail latency | driven by W distribution; rises steeply as ρ→1 |
| Autoscaling | you must add capacity (raise μ) *before* ρ hits the cliff |
| Admission control | reject (drop λ) when ρ is too high → protects W (see [13](13-overload-protection.md)) |

## Why "keep GPUs at 100%" conflicts with "P99 must be low"

Running every GPU at ~100% utilization means ρ ≈ 1. At ρ ≈ 1, waiting time is
unbounded and tail latency balloons — requests pile in an unbounded queue. A
latency SLO therefore *requires* leaving headroom: you must **under-utilize the
GPUs** (keep ρ meaningfully below 1) or shed load, trading some utilization for
bounded P99. There is no free lunch: utilization and tail latency pull in
opposite directions.

This is exactly why **goodput** ([03](03-goodput-vs-throughput.md)) matters —
a GPU at 100% with terrible latency serves mostly *bad* requests.

## Operational rules of thumb (`[I]`)

1. Watch **queue depth** as the leading indicator, because it moves before ρ
   looks alarming.
2. Leave headroom under strict TTFT SLOs (lower ρ target).
3. Add capacity **predictively** before busy periods rather than reactively
   after ρ ≈ 1 ([17](17-llm-autoscaling-reliability.md)).
4. Use admission control to cap λ when ρ is too high ([13](13-overload-protection.md)).

## Related

`07-llm-capacity-planning.md` · `13-overload-protection.md` ·
`17-llm-autoscaling-reliability.md` · `Inference/Production-Serving/04-queueing-theory-80-20.md`

## Key takeaways

1. ρ = λ/μ; as ρ → 1, waiting time explodes.
2. Little's Law L = λW links utilization, queue depth and latency.
3. 100% GPU utilization and low P99 are fundamentally in tension.
4. Manage ρ with queue-depth signals, predictive scaling, and admission control.
