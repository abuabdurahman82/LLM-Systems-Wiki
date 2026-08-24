# 05 — GPU Utilization Economics

`LAST_UPDATED: 2026-08-24` · Status: core page · Figures computed in
[scripts/economic_foundation.py](scripts/economic_foundation.py).

## 30-Second Explanation

Because the GPU bill is mostly **fixed** (you own or rent the capacity whether
or not it works), utilization converts that fixed bill into units of *useful
output*. Going from **20% to 70% utilization** can cut effective cost per token
roughly **3.5×**. But there is a second, subtler truth: **100% utilization is
economically wrong for interactive inference**, because as utilization
approaches saturation, queueing latency climbs to infinity. The economic
optimum sits at moderate utilization — high enough to amortize the fixed cost,
low enough to hold back the latency that arrives with saturation.

## Utilization converts fixed cost into output price

From [04](04-capex-vs-opex-ai-platform.md), the fully-loaded on-prem H100 fleet:

| Utilization | Effective $/prod GPU-hr | Relative |
|---|---|---|
| 20% | $7.45 | 3.5× the 70% figure |
| 70% | $2.13 | baseline |
| 95% | $1.57 | 0.74× |

A platform running at 20% pays **~3.5× more per productive GPU-hour** than one
at 70%. At low utilization you might as well have rented from a hyperscaler on
demand — which is the crux of [29-local-vs-api-economics](29-local-vs-api-economics.md).

## Why maximum utilization is (usually) wrong for interactive

Interactive inference has **latency SLOs**. The relationship between utilization
and latency is governed by **queueing theory**. For a single-server queue the
**traffic intensity** is:

$$\rho = \frac{\lambda}{\mu}$$

where $\lambda$ is arrival rate and $\mu$ is service rate. As $\rho \to 1$
(utilization → 100%), the average queue length and waiting time **blow up to
infinity**. Under an M/M/1 model with a 0.5 s service time, the P99 **sojourn**
(wait + service) time (computed, `Ts·ln(100)/(1−ρ)`) does this:

| ρ (utilization) | P99 sojourn (≈) |
|---|---|
| 0.20 | ~2.9 s |
| 0.50 | ~4.6 s |
| 0.70 | ~7.7 s |
| 0.80 | ~11.5 s |
| 0.90 | ~23 s |
| 0.95 | ~46 s |

> ⚠️ **M/M/1 is a simplification** (single server, exponential service). A
> continuous-batching, multi-GPU engine differs (finite batch slots, correlated
> arrivals, multiple servers) — treat the table as an **order-of-magnitude
> illustration of the ρ→latency relationship, not a precise SLA predictor**.

The knee is unmistakable: **past ~70% utilization, tail latency stops being
"a bit worse" and becomes qualitatively broken** for an interactive SLO.
See [Production-Operations/08-queueing-theory-for-llm-sre](../Production-Operations/08-queueing-theory-for-llm-sre.md)
and [Inference/Production-Serving/04-queueing-theory-80-20](../Inference/Production-Serving/04-queueing-theory-80-20.md).

## Utilization vs goodput

Raising utilization *without* meeting the SLO doesn't produce value — saturated
GPUs emit *slow* tokens that violate the service promise. So the metric that
matters is **goodput**: throughput that satisfies the SLO and quality bar
([43-goodput-economics](43-goodput-economics.md)). A GPU at 100% utilization with
bad P99 is producing *dead on arrival* output.

## The economic optimum ≠ maximum utilization

The platform total-cost curve is a **U shape**:

- **Low utilization** → high fixed-cost-per-unit (you paid for the GPU, got little).
- **High utilization** → high latency → SLO violations → retries, lost trust,
  dead work → effective cost rises again.

The **economic sweet spot** sits between the two — typically somewhere in the
**50–80%** band for interactive, depending on the SLO and arrival variance,
and higher (85–95%+) for batch/preemptible work that tolerates queueing
([09-batching-and-economics](09-batching-and-economics.md),
[32-demand-forecasting](32-demand-forecasting.md)).

$$
\text{Economic optimum} \;\ne\; \max(\text{utilization})
$$

Rather, it maximizes **SLO-compliant output per dollar**:

$$\max \; \frac{\text{goodput}}{\text{cost}} \quad \text{s.t. latency SLO}$$

## Multi-tenant wrinkle

In a shared platform each tenant's SLO adds a **reserved headroom requirement**
that cap utilization for the *pool*, not just a single stream
([17-slo-economics](17-slo-economics.md)). The pool's safe utilization ceiling
is set by the strictest tenant SLO and the arrival-variance of the *noisiest*
tenant ([19-noisy-neighbor](19-noisy-neighbor.md)) — which is why you cannot
push a multi-tenant pool as hard as a single-tenant batch queue.

## Related

[04-capex-vs-opex-ai-platform](04-capex-vs-opex-ai-platform.md) ·
[17-slo-economics](17-slo-economics.md) · [19-noisy-neighbor](19-noisy-neighbor.md) ·
[43-goodput-economics](43-goodput-economics.md) ·
[09-batching-and-economics](09-batching-and-economics.md)

## Key takeaways

1. Utilization converts fixed GPU cost into output price; 20%→70% is ~3.5× / token.
2. Queueing theory: tail latency explodes as ρ→1 — 100% utilization is unusable
   for interactive work.
3. Too much utilization = SLO violations = dead output = higher effective cost.
4. The economic optimum is a U-curve minimum (moderate utilization), not a maximum.
