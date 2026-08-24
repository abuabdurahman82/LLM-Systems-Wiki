# 03 — The Unit Economics of LLM Inference

`LAST_UPDATED: 2026-08-24` · Status: core page · All figures ILLUSTRATIVE, dated
**2026-08** (see [scripts/economic_foundation.py](scripts/economic_foundation.py)).

## 30-Second Explanation

Inference economics start from **cost per GPU-hour**, then convert that into
**cost per token, per request, per session, per tenant**. The naive
*left-over division* (`Total platform cost ÷ useful tokens`) understates the
true cost because it ignores idle capacity, availability overhead, and the fact
that not every GPU-hour is *productive*. The mature unit is **fully loaded cost
per useful SLO-compliant token** — see [43-goodput-economics](43-goodput-economics.md).

## Start at cost per GPU-hour

Buying an H100 buys *time*, so every other metric starts there.

- **On-prem, fully loaded, ILLUSTRATIVE:** an 8×H100 node at ~$245k capex over
  3 years, plus power/cooling/ops, works out to **≈ $1.49 / GPU-hr at 100%
  utilization** — but **≈ $7.45/GPU-hr at 20%** and **≈ $2.13 at 70%**
  (computed; [04-capex-vs-opex-ai-platform](04-capex-vs-opex-ai-platform.md)).
- **Cloud on-demand, dated 2026-07/08, US:** AWS **$6.88**/GPU-hr, Azure
  **$6.98**, GCP **$11.06**, neoclouds **$2.99–3.99**, spot ~**$2.30**
  ([F] provider/aggregator price lists; see [04](04-capex-vs-opex-ai-platform.md)).

> ⚠️ These are **illustrative reference points with a stated date**, not live
> quotes. Cloud prices change; always re-verify before relying on them.

## Deriving downstream cost units

From GPU-hour and model throughput you derive every other unit:

```
cost_per_token = ???
```

The **first-pass (incomplete)** definition is:

$$\text{Cost per token} = \frac{\text{Total platform cost}}{\text{Useful tokens generated}}$$

Why incomplete: the numerator buries idle capacity, replication, availability
overhead, and non-GPU costs; the denominator counts only *useful* tokens and
ignores quality/SLO failures ([43](43-goodput-economics.md)). The rest of the
section replaces it with a fully-loaded, allocation-aware model.

### Worked example (computed in economic_foundation.py)

Assume a ~70B dense model on H100 with (illustrative) prefill **30k tok/s/GPU**
and aggregate decode **25k tok/s/GPU** under continuous batching:

| Utilization | $/GPU-hr (on-prem, full load) | Prefill $/1M | Decode $/1M |
|---|---|---|---|
| 20% | **$7.45** | $0.07 | $0.08 |
| 70% | **$2.13** | $0.02 | $0.02 |
| 95% | **$1.57** | $0.01 | $0.02 |

So for a `1500 in / 500 out` request: **≈ $0.0001/req at 20% util**, **≈ $0.00004/req
at 70%**, **≈ $0.00003 at 95%** — vs OpenAI-style APIs at the same shape:
gpt-4o-mini **$0.0005/req**, GPT-4.1 **$0.0070/req**, gpt-5.6-sol **$0.0225/req**
(dated 2026).

> **[I]** A subtle and honest result: **self-hosting is only cheaper than a
> third-party API per request at meaningful scale.** The per-token *marginal*
> cost is low, but you pay the node's **fixed** cost whether or not it works
> ([04](04-capex-vs-opex-ai-platform.md)). At low utilization the idle tax
> dominates; the economic case for owning GPUs is utilization- and
> volume-dependent ([05](05-gpu-utilization-economics.md),
> [29-local-vs-api-economics](29-local-vs-api-economics.md)).

## The unit-economics ladder

| Unit | Definition | Used for |
|---|---|---|
| **$/GPU-hr** | fully-loaded cost of a GPU for an hour | capacity; foundation of everything |
| **$/token** | cost to produce one token | per-token metering |
| **$/1M tokens** | scaled, human-readable token cost | pricing headers, benchmarking |
| **$/request** | tokens × rate + fixed overhead per request | request-tier prices, auto-scaling |
| **$/session** | sum of requests in a (multi-turn) session | conversation/agent economics |
| **$/successful task** | cost to reach a *quality-passing* outcome (incl. retries/routing) | goodput economics ([43](43-goodput-economics.md)) |
| **$/tenant** | a tenant's total allocated consumption over a period | showback/chargeback ([14](14-showback-chargeback.md)) |
| **$/model** | cost of one model's replicas + its share of the pool | model P&L, routing ([10](10-model-economics.md)) |
| **$/endpoint** | cost of one serving endpoint | endpoint chargeback |

## Fully loaded cost

The "headline" $/GPU-hr hides the full bill. **Fully loaded cost** includes:

```
GPU cost (purchase or rent)
+ CPU cost (hosts, control plane)
+ RAM
+ storage (weights, cache, logs, checkpoints)
+ network (fabric, NICs, bandwidth, egress)
+ licenses / software (OS, drivers, engines, CUDA libs)
+ power
+ cooling (PUE)
+ operations (staff, on-call)
+ support (vendor, internal help desk)
+ software (observability, security, registry, FinOps tooling)
+ idle capacity (reserved headroom for the SLO)
+ replication (N+1/N+2, multi-zone)
+ availability overhead (chaos, DR, standby)
```

**Fully Loaded Cost per Productive GPU-Hour** therefore is:

$$\text{Effective } \frac{\$}{\text{GPU-hr}} = \frac{\text{Annualized total platform cost}}{\text{Actual productive GPU hours delivered}}$$

The denominator is the lever: raising utilization (and lowering the
availability/idle tax) is what separates a cheap platform from an expensive one.

## Why this matters for multi-tenancy

Every downstream page in this section leans on these units:
- Quotas and budgets need a price per unit ([20-quota-engineering](20-quota-engineering.md)).
- Showback needs cost per tenant ([14](14-showback-chargeback.md)).
- Pricing maps internal cost to internal price ([15-llm-platform-pricing-models](15-llm-platform-pricing-models.md)).
- Routing compares cost per option ([11-economic-model-routing](11-economic-model-routing.md)).

## Related

[04-capex-vs-opex-ai-platform](04-capex-vs-opex-ai-platform.md) ·
[05-gpu-utilization-economics](05-gpu-utilization-economics.md) ·
[06-token-economics](06-token-economics.md) ·
[54-economics-formulas](54-economics-formulas.md) ·
[Inference/Inference-Optimization.md](../Inference/Inference-Optimization.md)

## Key takeaways

1. Everything derives from fully-loaded $/GPU-hr, not the sticker price of a GPU.
2. $\frac{Total}{Tokens}$ is too naive — it hides idle, availability, and quality failures.
3. Utilization dominates effective per-token cost: 20% vs 70% util is ~3.5× per token.
4. Self-hosting only meaningfully beats cheap APIs *at sufficient utilization*.
