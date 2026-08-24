# 06 — Token Economics

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

Not all tokens are equal. **Input, output, cached, reasoning, speculative,
embedding, and multimodal tokens each consume different compute, memory, and
bandwidth**, so a price that charges *one flat rate per token* distorts the
economics: output tokens are typically many times costlier to produce than
input tokens, and cached inputs are nearly free. Understanding *which* token is
*costing what* is the difference between a sound internal price and a pricing
model that silently subsidizes expensive work.

## Token taxonomy

| Token type | What it is | Compute profile | Cost driver |
|---|---|---|---|
| **Input tokens** | prompt you send | prefill (compute) | attention over context — compute-bound |
| **Output tokens** | generated reply | decode (bandwidth) | memory-bandwidth-bound, per step |
| **Cached input tokens** | prompt prefix found in cache | ~none (KV reused) | storage/memory, nearly zero compute |
| **Reasoning tokens** | hidden "thinking" before answer | decode-like, can be a large fraction | output-like cost ([35](35-agent-economics.md)) |
| **Speculative tokens** | draft tokens for speculative decoding | cheap draft + verify | amortized, can be rejected |
| **Rejected speculative tokens** | drafts the target model rejected | wasted verify work | pure waste if you paid for them ([34](34-ai-cost-waste.md)) |
| **Embedding tokens** | input to an embedding model | prefill-like | cheap per token but high volume (RAG) |
| **Multimodal tokens** | image/audio/video tokens | encoder + sequence | encoder cost, large inputs ([39](39-multimodal-economics.md)) |

## Why 1 input token ≠ 1 output token

The transformer's two phases have different cost physics (full treatment in
[07-prefill-decode-economics](07-prefill-decode-economics.md)):

- **Prefill** (input) is **compute-bound**: it processes the whole prompt in
  parallel attention. Cost scales with ~context length × layers.
- **Decode** (output) is **memory-bandwidth-bound**: tokens are produced one at
  a time, repeatedly reading the model weights. This is why providers charge
  **3–5× more per output token than per input token** — a reflection of the
  real cost, not just convention. [F] OpenAI-style output/input ratios (e.g.
  GPT-4.1 `$8/$2`, gpt-5.6-sol `$30/$5` per 1M, dated 2026) encode this.

## Cost components that a flat per-token price hides

- **Prefill cost** — attention compute for the whole prompt, dominant for long contexts.
- **Decode cost** — bandwidth-bound generation, dominant for long outputs.
- **KV-cache cost** — memory the model must hold for the session; a long context
  is a *standing memory reservation*, not a one-time cost
  ([08-kv-cache-economics](08-kv-cache-economics.md), [38-long-context-economics](38-long-context-economics.md)).
- **Long-context cost** — super-linear attention and memory (at least ×2 for key/value in every layer).
- **Reasoning-model cost** — the model may emit many *hidden* tokens before the
  visible answer; those are output-like and costly.

## Why per-token pricing can distort internal economics

When an internal platform prices flat per token, it creates **arbitrage**:

- A tenant that sends **huge prompts** gets prefill-heavy traffic priced as if it
  were cheap average traffic.
- A tenant running **agentic/reasoning workloads** (many hidden output tokens,
  repeated calls) undercharges for what is actually expensive decode work
  ([35-agent-economics](35-agent-economics.md)).
- Nobody is incentivized to use **caching** because cached tokens aren't
  rewarded in the price, even though they'd save the platform real prefill work.

**[I]** Pricing that *separates input / cached-input / output* (mirroring the
compute reality) both reflects cost and *steers* tenant behavior toward
cache-friendly, low-waste usage — the hallmarks of an economically sound
internal price ([15-llm-platform-pricing-models](15-llm-platform-pricing-models.md)).

## Related

[07-prefill-decode-economics](07-prefill-decode-economics.md) ·
[08-kv-cache-economics](08-kv-cache-economics.md) ·
[15-llm-platform-pricing-models](15-llm-platform-pricing-models.md) ·
[38-long-context-economics](38-long-context-economics.md) ·
[11-economic-model-routing](11-economic-model-routing.md)

## Key takeaways

1. Token ≠ token: input, output, cached, reasoning, speculative, and multimodal
   tokens have fundamentally different real costs.
2. Output tokens are memory-bandwidth-bound and cost several × input tokens.
3. Cached inputs are nearly free — caching is a first-class economic lever.
4. Flat per-token pricing hides and rewards expensive workloads; price by token
   *type* to reflect cost and steer behavior.
