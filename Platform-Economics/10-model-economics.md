# 10 — Model Economics

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

Different model *classes* have radically different cost structures — not just
"big = expensive," but *different* because of **active parameters, KV-cache
footprint, parallelism, and inference-time behavior**. The economically correct
model unit is **cost per successful answer** (or per good request), not cost per
token: a cheap weak model that needs retries or cascades can end up more
expensive than a pricey strong one that answers right the first time
([11-economic-model-routing](11-economic-model-routing.md),
[43-goodput-economics](43-goodput-economics.md)).

## Model classes and their economics

| Model class | Weights memory | Active params | KV cache | Compute | Latency | Parallelism | Net traffic |
|---|---|---|---|---|---|---|---|
| **Small dense** (≤8B) | Small, fits 1 GPU | All params | Small | Low | Low | None/single GPU | Low |
| **Large dense** (70B+) | Large, needs multi-GPU TP | All params **always** | Large | High every token | High | TP/PP required | High (all-reduce per step) |
| **MoE** (sparse) | Huge (all experts) | Only routed experts | Depends | Lower than dense of same size | Medium | EP/TP | High (expert routing traffic) |
| **Reasoning** (test-time compute) | Model-size-dependent | Depends | Very large (long thinking) | Can be 10–100× a pass | High | Same | High (long output) |
| **Multimodal** | + encoders | + encoder passes | Context-depend | + encode/decode | Medium-High | Varies | High (image/audio bytes) |

Key economics takeaway: **a large *dense* model pays its full weight on every
token**; an **MoE** pays for a fraction of its params but carries memory +
routing traffic; a **reasoning** model multiplies compute by test-time thinking
— which from a *cost* view is "many more output tokens" ([35-agent-economics](35-agent-economics.md)).
Model mechanics live in [Model-Architectures/](../Model-Architectures/README.md)
and [Distributed-Inference/](../Distributed-Inference/README.md).

## Cost per successful answer beats cost per token

Two models serve the same task:

- **Model W (weak/cheap):** $0.0004/request, but succeeds only 70% of the time.
  Expected cost per *success* ≈ $0.0004 / 0.70 ≈ **$0.00057** plus the cost of
  retries and user friction.
- **Model S (strong/pricey):** $0.002/request, succeeds ~98%.
  Expected cost per success ≈ $0.002 / 0.98 ≈ **$0.00204**.

Weak is still cheaper *here* — but the ledger changes once you include **the cost
of a failure** (user re-prompt, downstream error, support call). See
[45-cost-of-failure](45-cost-of-failure.md) and
[43-goodput-economics](43-goodput-economics.md). The general principle:

$$\text{Cost per Successful Answer} = \frac{\text{Cost per attempt}}{\text{Success rate}} \;+\; \text{failure-attributable cost}$$

**A "cheap" weak model with many retries can be more expensive than a strong
model that answers once** — which is exactly the case for **cascade routing**
in [11-economic-model-routing](11-economic-model-routing.md).

## Model economics feed the platform

- **Hardware requirement** decides which GPU pool a model can join
  ([46-gpuaas-pricing](46-gpuaas-pricing.md)).
- **Cost per answer** feeds router scoring ([22-budget-aware-routing](22-budget-aware-routing.md)).
- **Model governance** records cost + approved uses per model
  ([25-model-governance](25-model-governance.md)).

## Related

[11-economic-model-routing](11-economic-model-routing.md) ·
[Model-Architectures/Mixture-of-Experts](../Model-Architectures/Mixture-of-Experts.md) ·
[Distributed-Inference/](../Distributed-Inference/README.md) ·
[43-goodput-economics](43-goodput-economics.md) · [25-model-governance](25-model-governance.md)

## Key takeaways

1. Cost scaling across model classes is driven by active params, KV, parallelism, and test-time compute — not just parameter count.
2. Large dense models pay full weight per token; MoE pays fraction + routing traffic; reasoning pays many hidden output tokens.
3. Measure cost per *successful answer*, not per token — retries undermine "cheap" models.
4. Model economics drive GPU-pool placement, router scoring, and governance.
