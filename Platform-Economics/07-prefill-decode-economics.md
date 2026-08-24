# 07 — Cost of Prefill vs Decode

`LAST_UPDATED: 2026-08-24` · Status: core page · Economics derived in
[scripts/economic_foundation.py](scripts/economic_foundation.py).

## 30-Second Explanation

Every request has two cost halves with **different physics**: **prefill**
(process the prompt) is **compute-intensive**; **decode** (generate the reply) is
**memory-bandwidth-intensive**. A simplified request-cost model splits them, and
that split explains why *long prompts* and *long outputs* and *short-but-many*
workloads all cost differently — and why agentic workloads (many decode tokens +
repeated calls) are the most expensive shape of all.

## The two phases

| Phase | Operation | Bound by | Cost scales with |
|---|---|---|---|
| **Prefill** | process all input tokens in parallel attention | compute (FLOPs) | ~prompt length × layers |
| **Decode** | emit output tokens one step at a time, re-reading weights | memory bandwidth | ~output length × weights size |

The distinction is central to inference optimization
([Inference/Inference-Optimization.md](../Inference/Inference-Optimization.md)) and more
obviously to the pairing architectures that isolate them
([Inference/Prefill-Decode-Disaggregation.md](../Inference/Prefill-Decode-Disaggregation.md)).

## Simplified request cost model

$$\text{Request Cost} \approx \underbrace{C_{\text{prefill}}}_{\text{compute}} + \underbrace{C_{\text{decode}}}_{\text{bandwidth}} + \underbrace{C_{\text{KV residency}}}_{\text{memory}} + \underbrace{C_{\text{scheduling}}}_{\text{overhead}} + \underbrace{C_{\text{network}}}_{\text{move data}}$$

where:

- $C_{\text{prefill}}$ — attention FLOPs for the prompt (compute-bound).
- $C_{\text{decode}}$ — bandwidth-bound token generation (output-dominated).
- $C_{\text{KV residency}}$ — GPU memory held for the session's KV cache
  ([08](08-kv-cache-economics.md)).
- $C_{\text{scheduling}}$ — queueing, admission, routing overhead
  ([21](21-admission-control-governance.md)).
- $C_{\text{network}}$ — moving prompt, tool/RAG payloads, and output.

### Worked example (computed)

~70B dense model on H100; prefill 30k tok/s, decode 25k tok/s (illustrative):

| Utilization | Prefill $/1M | Decode $/1M |
|---|---|---|
| 20% | $0.07 | $0.08 |
| 70% | $0.02 | $0.02 |

Decode is costlier per token here *even though* its nominal rate looks high —
reflecting its bandwidth-bound nature; the gap widens sharply for reasoning
models with hidden output and for long single-stream decodes (unbatched).

## What each request shape costs

| Shape | Dominant cost | Why |
|---|---|---|
| **Long prompt, short output** | Prefill | huge attention, small decode |
| **Short prompt, long output** | Decode (+ KV residency) | many bandwidth-bound tokens, standing KV |
| **Short prompt, short output** | Scheduling + fixed overheads | per-request overhead dominates — efficient only with batching ([09](09-batching-and-economics.md)) |
| **Agentic workload** | Decode ×N + repeated prefill | many calls, hidden reasoning/planning tokens, tool round-trips ([35](35-agent-economics.md)) |
| **Long context sessions** | Prefill + KV residency | memory held across many turns ([38](38-long-context-economics.md)) |

## Implications

- **Long prompts** are expensive because prefill is compute-bound; **cache the
  repeated prefix** to make them cheap ([08](08-kv-cache-economics.md)).
- **Long outputs** are expensive because decode is bandwidth-bound *and* holds KV;
  cap `max_tokens` (a runaway agent's #1 cost driver, [34-ai-cost-waste](34-ai-cost-waste.md)).
- **Dozens of short requests** become cheap *only* with continuous batching
  amortizing the fixed overhead, which is exactly the lever in
  [09-batching-and-economics](09-batching-and-economics.md).
- **Agentic workloads** multiply decode + re-prefill; their cost is dominated by
  the *calls × output* term, not the visible "one question" — this is why agents
  need their own metering and budgets ([35-agent-economics](35-agent-economics.md)).

## Related

[06-token-economics](06-token-economics.md) · [08-kv-cache-economics](08-kv-cache-economics.md) ·
[09-batching-and-economics](09-batching-and-economics.md) ·
[38-long-context-economics](38-long-context-economics.md) ·
[Inference/The-Life-of-a-Token.md](../Inference/The-Life-of-a-Token.md)

## Key takeaways

1. Prefill is compute-bound; decode is bandwidth-bound — they need separate cost models.
2. Request cost ≈ prefill + decode + KV residency + scheduling + network.
3. Long prompts hurt in prefill; long outputs hurt in decode + KV; short ones
   hurt in fixed overhead.
4. Agentic workloads are the most expensive shape — many calls × output tokens.
