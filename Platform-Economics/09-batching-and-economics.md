# 09 — Continuous Batching & Economics

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

**Continuous batching** (in-flight / disaggregated scheduling inside the engine —
VLLM/SGLang/TensorRT-LLM) packs many requests' decode steps into one GPU pass,
which is *the* reason inference utilization and aggregate throughput rise and
cost/token falls. But the same lever that lowers cost shifts the trade-off:
larger batches raise **aggregate throughput** while degrading **per-request
latency (TTFT/TPOT)** and **per-tenant fairness**, and they increase **memory
pressure** (KV). The lesson: **lowest cost/token is not the same as best
service.** Batching is optimized *for a target SLO*, not to a minimum cost.

## What continuous batching buys

- Higher **GPU utilization** (fills idle compute/bandwidth between steps).
- Higher **aggregate throughput** (tokens/second across all requests).
- Lower **cost/token** (amortize the fixed GPU cost over more work).

The mechanics live in
[Inference/Continuous-Batching.md](../Inference/Continuous-Batching.md). This page
prices the trade.

## What it costs

| Dimension | Effect of aggressive batching |
|---|---|
| **TTFT** | Rises — a new request waits while the batch drains toward a scheduling point. |
| **Per-user latency** | Rises — your request shares each decode step with many others (TPOT degrades). |
| **Fairness** | Worse — a big tenant's tokens can crowd out a small tenant's tokens in the same batch. |
| **Memory pressure** | Higher — every in-flight request holds KV ([08](08-kv-cache-economics.md)). |

The engineering tension is worked in
[Inference/Production-Serving/07-scheduling-inside-the-engine](../Inference/Production-Serving/07-scheduling-inside-the-engine.md)
and [01-production-serving-overview](../Inference/Production-Serving/01-production-serving-overview.md).

## Batch size, concurrency, latency, SLO

The chain is causal: **more concurrency → bigger batches → higher throughput →
lower cost/token, but higher tail latency (TTFT + TPOT) → more SLO violations**
for interactive tenants. The key is that the *engine* controls batch
composition at a fine grain (add/remove sequences per step), and the *router /
admission layer* controls how many tenants' work can enter the same pool
([21-admission-control-governance](21-admission-control-governance.md)).

**[I] Economic framing:** batching is a *free-parameter knob* on the
cost-utilization-latency frontier ([12-quality-cost-latency-frontier](12-quality-cost-latency-frontier.md)).
You don't crank it to max; you set it so that **goodput is maximized within the
SLO** ([43-goodput-economics](43-goodput-economics.md), [17-slo-economics](17-slo-economics.md)).

## Multi-tenant wrinkle

Aggressive pooling is great for **cost** but is exactly the mechanism by which
**noise propagates**: one tenant's 100 concurrent long requests join a batch and
degrade every other tenant's interactive latency
([19-noisy-neighbor](19-noisy-neighbor.md)). Multi-tenant platforms therefore
blend batching with **per-tenant concurrency limits**, **priority**, and
**admission thresholds** (fairness machinery in
[Inference/Production-Serving/13-multi-tenancy-fairness-priority](../Inference/Production-Serving/13-multi-tenancy-fairness-priority.md)).

## Related

[Inference/Continuous-Batching.md](../Inference/Continuous-Batching.md) ·
[05-gpu-utilization-economics](05-gpu-utilization-economics.md) ·
[19-noisy-neighbor](19-noisy-neighbor.md) · [43-goodput-economics](43-goodput-economics.md) ·
[21-admission-control-governance](21-admission-control-governance.md)

## Key takeaways

1. Continuous batching is the main utilization/cost lever in modern inference.
2. It pushes throughput up but TTFT/TPOT, unfairness, and memory pressure up too.
3. Lowest cost/token ≠ best service; optimize batch policy for the SLO.
4. Aggressive pooling is how noisy neighbors propagate — pair batching with
   per-tenant concurrency and priority controls.
