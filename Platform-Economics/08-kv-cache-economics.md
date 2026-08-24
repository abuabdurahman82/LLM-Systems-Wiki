# 08 — KV Cache Economics

`LAST_UPDATED: 2026-08-24` · Status: core page · Economics from
[scripts/economic_foundation.py](scripts/economic_foundation.py).

## 30-Second Explanation

The **KV cache is an economic resource, not just a performance trick.** It
*consumes* scarce GPU memory (capacity, placement flexibility, concurrency
headroom) but *saves* prefill compute, latency, and energy on repeat prefixes.
The net value of the cache is **avoided prefill cost minus the memory
opportunity cost** — and it is only worth keeping a token cached if that
balance is positive. In a multi-tenant platform the cache is also **shared
state with cross-tenant externalities**: one tenant's cache-busting storm can
evict another tenant's hot prefix.

## KV cache as consume/save

**Consumes realistically:**
- GPU **memory** per active token (per layer, per head).
- **Placement flexibility** — the cache pins batches and complicates scheduling.
- **Concurrency headroom** — memory used for KV is memory not available for more concurrent requests.

**Saves when reused:**
- **Prefill compute** — a cache hit skips recomputing the prefix.
- **Latency** — TTFT drops dramatically on a warm prefix.
- **Energy** — less compute per request.

The full mechanics (memory equation, paged caching, PagedAttention, eviction,
offload) live in [KV-Cache/](../KV-Cache/README.md); here we price it.

## Prefix / session caching terms

- **Prefix caching** — cache shared prompt prefixes across requests.
- **Session caching** — keep a conversation's KV warm between turns.
- **Cache hit rate** — fraction of input tokens satisfied from cache; the master lever.
- **Cache eviction** — dropping cached KV under memory pressure (LRU/prefix-aware).
- **Cache fragmentation** — memory scattered such that free blocks can't serve new prefixes.
- **KV offload** — moving cold KV to CPU/disk to free GPU memory.
- **Shared prefix reuse** — many requests share a system prompt; caching it amortizes prefill across all.

## Conceptual cache value model

$$\text{Cache Value} = \text{Avoided Prefill Cost} \;-\; \text{Memory Opportunity Cost}$$

### Worked illustration (computed — self-hosted)

- Avoided prefill at 20% util: **$0.20 / 1M cached tokens**
- Memory opportunity cost: **$0.15 / 1M** (illustrative; the GPU memory
  otherwise usable for concurrent work)
- Cache hit rate 0.6 → net cache value ≈ **$0.03 / 1M requests when hit**.

> **Self-host prefill is *cheap*, so self-host caching's $ value is small but
> latency value is large.** For **cloud APIs** the same hit is worth far more in
> cash because *avoided* billed input is expensive: e.g. GPT-4.1 cached input is
> **$0.50 vs $2.00** fresh (dated 2026) — a **75% input-token discount**. The
> economics of caching are therefore **context-dependent**: self-host = latency +
> utilization win; API = direct money win. Both share the same conceptual formula.

## Multi-tenant cache governance

Because the cache is shared memory:
- **Cross-tenant eviction**: tenant A's long, novel prompts can evict tenant B's
  hot system prompt ([19-noisy-neighbor](19-noisy-neighbor.md),
  [23-tenant-security-isolation](23-tenant-security-isolation.md) for the *leakage* risk).
- **Isolation**: separate cache trees / namespaces per tenant where privacy or
  fairness demands it.
- **Reward caching** in the price model (cheaper cached tokens) so tenants
  *want* stable prefixes rather than churning them
  ([15-llm-platform-pricing-models](15-llm-platform-pricing-models.md),
  [13-tenant-metering](13-tenant-metering.md)).

## Related

[KV-Cache/](../KV-Cache/README.md) · [07-prefill-decode-economics](07-prefill-decode-economics.md) ·
[19-noisy-neighbor](19-noisy-neighbor.md) ·
[Inference/Production-Serving/08-cache-aware-routing](../Inference/Production-Serving/08-cache-aware-routing.md) ·
[34-ai-cost-waste](34-ai-cost-waste.md)

## Key takeaways

1. KV cache consumes memory / placement / concurrency; it saves prefill, latency, energy.
2. Cache Value = Avoided Prefill − Memory Opportunity Cost (conceptual model).
3. Self-host: cache is mostly a *latency + utilization* win; cloud API: it is a
   *direct $* win (cheaper cached input).
4. In multi-tenancy the cache is shared state — govern eviction and isolation
   per tenant.
