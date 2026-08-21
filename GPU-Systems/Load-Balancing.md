# LLM Load Balancing — Balance Remaining Work, Not Requests
`LAST_UPDATED: 2026-08-21 · Status: core page` · Connects to engine schedulers
(`vLLM.md`, `SGLang.md`) and the P/D split (`Prefill-Decode-Disaggregation.md`).

## 30-Second Explanation
The naive router is **least-connections**: send the next request to the replica with the
fewest in-flight requests. That is **wrong for LLMs**, because LLM requests are
**extremely unequal in remaining work** — a request with a 4k-token prompt and 500-token
output is ~100× the work of a 64-token prompt / 32-token output. Least-connections treats
them as equal and will overload the replica that happens to be serving the long one.
The right principle: **do not balance requests; balance remaining work.** Route each
request to the replica where its *predicted* remaining compute (prefill + decode + KV
pressure) is lowest, accounting for prefix-cache hits and current batch state.

## What
A **router / load balancer** sits in front of N inference replicas (which may be
single-GPU, TP groups, or P/D-disaggregated pools) and assigns each incoming request to
one of them. The goal is to maximize **goodput** (req/s at the SLO) and minimize
**P99 TTFT/ITL**, not just mean throughput.

## Why least-connections is insufficient
Three reasons:
1. **Work is unequal and unknown in advance.** Prompt length and output length vary by
   100×. A "connection" is not a unit of work.
2. **The two phases differ.** Prefill (TTFT) is compute-bound and bursty; decode (ITL)
   is bandwidth-bound and long-lived. A replica can be "idle" (few connections) but
   bandwidth-saturated by long decodes.
3. **Prefix cache is stateful.** A request that hits the replica's prefix cache is cheap;
   the same request on a cold replica is expensive. Least-connections ignores the cache
   hit → sends cache-warm work to a cold replica.

## How — route on remaining work
Define a **cost estimate** for request *r* on replica *j*:
```
cost(r, j) = w_p · max(0, prompt_len(r) − prefix_hit(r,j))   # prefill work remaining
           + w_d · predicted_output_len(r)                  # decode work
           + w_kv · kv_pressure(j)                          # KV cache headroom
           + w_q · queue_depth(j)                            # current queue
           + w_m · model_mismatch(r, j)                     # wrong model/adapter/GPU
```
Route to `argmin_j cost(r, j)`. The weights `w_*` are tuned to your SLO (TTFT-weighted
vs ITL-weighted). Each term:
- **`prompt_len − prefix_hit`:** the *remaining* prefill work after the shared prefix is
  served from cache. A 4k prompt with a 3.9k cache hit → only 100 tokens of prefill.
  This is the single biggest correction to naive routing.
- **`predicted_output_len`:** estimated via a cheap predictor (past output-length
  distribution, model-size routing, or a small LLM-judge). Long outputs bind decode
  bandwidth for longer.
- **`kv_pressure`:** the replica's current KV cache utilization (`gpu_cache_utilization`).
  High pressure → new requests will be queued or evicted.
- **`queue_depth`:** the number of requests already admitted.
- **`model_mismatch`:** 0 if the replica serves the right model/adapter/GPU; ∞ otherwise.

## When
- **Multiple replicas** (DP) or a **P/D pool** (separate prefill and decode pools).
- **Heterogeneous fleet:** different models, adapters, GPU types → the router must match.
- **Agentic workloads:** many short requests with shared prefixes → prefix-aware routing
  matters most (`SGLang.md` RadixAttention).
- **Long-context service:** KV pressure dominates → route to the replica with most KV
  headroom.

## Hardware impact
Routing changes **which GPU(s) do the work**, so it shifts load onto specific SMs/HBM.
Good routing keeps HBM BW util balanced across replicas (no hot GPU) and keeps the
prefix cache **warm** on the replica that will actually use it.

## Inference impact
- **TTFT:** prefix-aware routing → warm prefill → lower TTFT on repeated prompts.
- **ITL / P99:** balancing remaining work → no replica is overloaded with long decodes →
  lower P99 ITL.
- **Goodput:** routing that respects SLOs → more req/s at the P99 target.
- **KV utilization:** routing that respects KV headroom → fewer OOMs/evictions.

## Example [E, method]
Two replicas, each a TP=2 H100 pair, serving a 27B FP8 model.
- Request A: prompt 4096, predicted output 512, system prompt 3.9k shared.
- Request B: prompt 256, predicted output 32.
- Replica 1: `prefix_hit(A)=3.9k` (warm), `kv_pressure=0.4`, `queue=3`.
- Replica 2: `prefix_hit(A)=0` (cold), `kv_pressure=0.7`, `queue=1`.

**Least-connections** sends A to replica 2 (queue 1 < 3) — the **wrong** choice: A is
cold there (4096 prefill tokens) and replica 2 is KV-pressured.
**Remaining-work** cost:
- `cost(A,1) = w_p·100 + w_d·512 + w_kv·0.4 + w_q·3`  (only 100 prefill tokens, warm)
- `cost(A,2) = w_p·4096 + w_d·512 + w_kv·0.7 + w_q·1` (4096 prefill, cold, KV-pressured)
→ route A to **replica 1** (warm, cheap). Route B (trivial) to replica 2 (idle). Result:
A's TTFT is ~40× lower and replica 2's KV pressure stays manageable. [E: method]

## Failure modes
- **Bad output-length predictor:** systematically over/under-estimates → misroutes.
  (Fix: calibrate per-model/per-intent; use conservative upper bound for SLOs.)
- **Stale prefix-cache state:** the router thinks a prefix is warm but the replica evicted
  it (under KV pressure) → the request is actually cold. (Fix: subscribe to eviction
  events; re-estimate on miss.)
- **Hot-spotting:** a popular system prompt routes everything to one replica → that
  replica's KV fills. (Fix: pin shared prefixes across replicas or sharding the cache.)
- **No model/adapter match check:** routes a 70B request to a 7B replica → 404/quality
  disaster. (Fix: hard-match on model id first.)

## How to measure it
- **P99 TTFT/ITL** before/after the router (the SLO metrics).
- **Prefix-cache hit rate** per replica (engine metric).
- **KV utilization distribution** across replicas (should be balanced, not hot-spotted).
- **Goodput at SLO** (req/s where P99 ITL < target).
- **Routing decision log:** for a sample of requests, was the chosen replica the
  `argmin` of cost? (Audit the router's own decisions.)

## Connection to engine schedulers
The router is the **first-level scheduler** (across replicas); the engine's internal
scheduler (`vLLM.md` / `SGLang.md`) is the **second-level scheduler** (within a replica,
deciding which requests run this step, chunked-prefill, continuous batching). Good
systems make these **co-design**: the router feeds the engine a queue that the engine's
batcher can absorb without thrashing. SGLang's **cache-aware scheduling** and vLLM's
**KV-aware routing** are this co-design in practice.

## Related
`Prefill-Decode-Disaggregation.md` · `vLLM.md` · `SGLang.md` ·
`../Inference/Continuous-Batching.md` · `../KV-Cache/README.md` · `Case-Studies.md` ·
`Diagnostics.md`.

## Key Takeaways
1. **Balance remaining work, not requests.** A request is not a unit of work.
2. The four routing signals: **remaining prefill (after prefix hit), predicted output
   length, KV pressure, queue depth** (+ model/adapter/GPU match).
3. **Prefix-aware routing** is the biggest single correction to least-connections.
4. The router (L1) and the engine scheduler (L2) should be **co-designed**.
