# 07 — LLM Capacity Planning

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

Capacity planning for LLMs is **token-work budgeting**, not request counting.
You start from users and translate demand down to *GPU-seconds*: users →
requests/sec → tokens/sec → GPU requirement. Requests/sec alone cannot size a
system, because a request's cost is dominated by its token counts and context
length.

## Why requests/sec is insufficient

**Example:** `100 req/sec × 50 output tokens` is *not* remotely equivalent to
`100 req/sec × 2,000 output tokens`. The second is **40×** the decode work. Same
request count, wildly different GPU need. Similarly a 10k-token prompt costs far
more prefill than a 500-token prompt. `[I]` arithmetic.

## The planning chain

```
users (concurrent, DAU)
   ↓
requests/sec (arrival rate λ)
   ↓
tokens/sec
   = requests/sec × (input tokens/request + output tokens/request)
   ↓
GPU requirement (compute-seconds + KV memory), given:
   GPU throughput (tokens/sec it can serve)
   KV capacity (blocks available on the GPU/engine)
   TTFT target
```

## The sizing inputs

| Input | Why | How it moves GPU need |
|---|---|---|
| **Arrival rate** | base load | linear in requests/sec |
| **Input tokens/request** | prefill compute + KV growth | long prompts cost more prefill; drive prefix-cache reuse |
| **Output tokens/request** | decode compute | output length is often the dominant term via TPOT |
| **Prompt length distribution** | tail events matter | a 100k-token prompt can stall batching |
| **Concurrency** | in-flight requests = KV + batch pressure | sets KV footprint and queue behavior |
| **TTFT target** | how much queueing is tolerated | stricter TTFT ⇒ more peak headroom (see [08](08-queueing-theory-for-llm-sre.md)) |
| **GPU throughput** | tokens/sec the hardware+engine sustain | efficiency lever (quantization, batching) |
| **KV capacity** | how many tokens can be held resident | caps concurrency × context before eviction/OOM |

## Compute-side estimate (illustrative)

A rough `[I]`/`[A]` starting model:

```
GPU-required ≈
   (input_token_rate   × prefill_FLOPs_weight)
 + (output_token_rate  × decode_weight)
 + KV_memory_for_concurrency × context_length
```

Exact values depend on model size, precision, batch efficiency, and engine
overheads — **do not treat the constants as facts**; calibrate them from your
own [E] measurements (see `GPU-Systems/Inference-Engines.md`,
`Inference/Roofline.md`). Use the `Labs/` calculators to fit your hardware.

## Operationally

1. **Characterize your real distributions** (prompt length, output length,
   concurrency) — the mean hides the tails that define your peak.
2. **Plan for goodput, not peak throughput** ([03](03-goodput-vs-throughput.md)).
3. **Model the TTFT constraint** — capacity that can't meet P95 TTFT is
   capacity in the wrong shape.
4. **Track KV capacity as a hard resource** — concurrency × longest context is
   bounded by KV blocks ([12](12-kv-cache-reliability.md)).
5. **Revisit on every change** — quantization, engine upgrade, prompt changes,
   and model swap all move the constants.

## Simple calculator (conceptual)

```
input_tok_rate   = req_per_sec × mean_input_tokens
output_tok_rate  = req_per_sec × mean_output_tokens
kv_tokens_needed = max_concurrency × max_context_length

# Is decode a bandwidth problem?
decode_bw_headroom = gpu_bandwidth_bytes_per_sec / (bytes_per_token_output)
```

Again `[I]`: plug in your numbers and hardware.

## Related

`03-goodput-vs-throughput.md` · `08-queueing-theory-for-llm-sre.md` ·
`12-kv-cache-reliability.md` · `17-llm-autoscaling-reliability.md` ·
`Inference/Production-Serving/11-autoscaling-and-capacity-planning.md`

## Key takeaways

1. Plan in **tokens and KV bytes**, not requests.
2. `100 req/s × 50 tok` ≪ `100 req/s × 2000 tok`.
3. The chain: users → req/s → tokens/s → GPU requirement.
4. Calibrate constants from your own [E] measurements; watch the tail, not the mean.
