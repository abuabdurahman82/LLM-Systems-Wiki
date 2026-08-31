# RAG and Inference Engineering — How Retrieval Shapes Prefill, KV, and Batching

`LAST_UPDATED: 2026-08-29` · Status: core page · The inference-side numbers
reuse the wiki's canonical KV constant (128 KiB/token ≈ 7B-class GQA fp16,
`../KV-Cache/`); engine features are [I: vendor docs] unless marked.

## 30-Second Explanation
RAG changes the *shape* of LLM inference: the prompt is no longer "question"
but "question + ~5.5K–26K tokens of retrieved context" (the page's worked
examples: 10 chunks ≈ 5.5–6K, 50 chunks ≈ 26K), which means every RAG
request is a **prefill-heavy** request. That single fact drives TTFT, KV cache
pressure, batching behavior, and cost. The serving engines (vLLM/SGLang/
TensorRT-LLM — `../Serving-Engines/`) already have the machinery (continuous
batching, paged KV, prefix caching); RAG's job is to use it deliberately:
order the context for prefix-cache hits, size k for the KV budget, and treat
TTFT as the first-class RAG latency metric.

## The shape change: prefill-heavy workloads
A plain chat request: ~1K prompt tokens, 1–2K generation. A RAG request:
[E: 10×512-tok chunks + question + system ≈ 5.5K–6K input tokens; 50 chunks ≈
26K input tokens] — ~5.5–6× the prefill at 10 chunks and ~26× at 50 chunks vs
the ~1K chat prompt, ~the same generation. Consequences:
1. **TTFT is dominated by prefill** [I: standard prefill/decode analysis —
   `../Inference/The-Life-of-a-Token.md`]: at 5K input, most of the first-token
   latency is the prefill GEMM pass over the context; doubling k roughly
   doubles TTFT (until batching effects kick in).
2. **Prefill is compute-bound, decode is memory-bound** (Roofline,
   `../Inference/Roofline.md`): RAG workloads shift the server's bottleneck
   *toward compute* — often under-utilizing the memory bandwidth that decode
   would have used. A RAG server and a chat server need different capacity
   shapes [I].
3. **TTFT is the RAG SLO**: for interactive retrieval, users feel prefill, not
   decode. A "fast" RAG system with 3s TTFT feels slow; a chat system with 3s
   ITL feels broken — different SLOs, same engine.

## KV cache pressure from context
[E: at the bank's 128 KiB/token convention (≈ 7B-class GQA fp16; a 70B-class
model is ~320 KiB/token fp16, so scale the MiB figures ~2.5×): 5,120-tok
context ≈ 640 MiB of KV per sequence; 25,600-tok (50 chunks) ≈ 3.1 GiB
(3,200 MiB) per sequence.]
- A ~3.1 GiB KV per request means ~25 concurrent such sequences per 80 GiB of
  *KV budget* — context length is a **concurrency budget**, not just a quality
  knob [E: 80 GiB / 3.1 GiB ≈ 25, KV-only ceiling]. **This is a KV ceiling,
  not achievable single-card concurrency**: a 70B-class model's weights alone
  (~35–40 GB INT4, ~70 GB INT8, ~140 GB fp16) don't leave room for 25
  sequences on one 80 GB card; real concurrency = (card memory − weights −
  activations) / per-sequence KV, i.e. single digits to low teens even
  quantized [I: order-of-magnitude].
- Paged KV (`../KV-Cache/Paged-KV-Cache.md`) makes this manageable at the
  block level; the planning problem is unchanged: k × chunk size × concurrency
  must fit the tier (HBM → DRAM → NVMe, `../KV-Cache/Hierarchical-Offloading.md`).
- **Long-context ≠ RAG**: stuffing 1M tokens (39) turns one request into a
  ~122 GiB KV allocation at the 128 KiB/token convention [E: 1e6 × 128 KiB =
  128,000,000 KiB ≈ 122.1 GiB binary] — the moment
  you understand why "just use the long context" has an economics section
  (44).

## Batching, prefix caching, and RAG context ordering
Three serving mechanisms that interact with RAG design:
1. **Continuous batching** (`../Inference/Continuous-Batching.md`): requests
   join/leave the batch every step; RAG's long prefills create *stragglers* —
   a 26K-token prefill in a batch of short requests slows the whole batch's
   step time. Engines mitigate (chunked prefill, prefill/decode separation);
   the design consequence: **batch RAG traffic deliberately** (QPS smoothing,
   separate prefill pools — `../Inference/Prefill-Decode-Disaggregation.md`)
   rather than mixing it with interactive chat.
2. **Prefix caching** (`../KV-Cache/Prompt-and-Prefix-Caching.md`): the system
   prompt + stable instructions are the *stable prefix* of every RAG request.
   **Context ordering is a cache decision** [I: the underused one]: put the
   fixed instruction block first, then retrieved chunks in a *stable,
   deterministic order* (by chunk id, not by retrieval score), so repeated
   chunks across queries hit the prefix cache. A measured 8.7× TTFT
   cold→warm for an identical 8K prefix exists in this wiki (Lab 13,
   `../Inference/`) — RAG with repeated system blocks is the same shape. This
   TTFT reduction is *conditionally free*: the chunk-level cache hits only
   materialize when chunk sets actually overlap across queries (otherwise only
   the instruction block is shared), and chunk-id ordering can trade against
   relevance ordering (most-relevant-first vs lost-in-the-middle, 39/46) —
   measure the combined effect on your set.
3. **Chunked prefill / P-D disaggregation**: long RAG prefills can be chunked
   across steps or moved to a prefill pool; the RAG system's k choice interacts
   directly with these knobs [I: engine-specific — verify against
   `../Serving-Engines/Engine-Landscape.md`].

## The cost side (per-request physics)
[E: recompute from the canonical constant]: prefill of 5,120 tokens ≈ 5,120 ×
128 KiB ≈ 640 MiB of KV written once, read on every decode step; the compute
side is one forward pass over 5,120 tokens (O(N²) attention over the context
for the standard full-attention models — the reason 50-chunk contexts are not
just "5× the tokens", the attention FLOPs grow with N² over the prompt).
Practical rule [I]: **context token budget and KV budget are the same number
seen from two directions** — set k from the latency SLO, check it against the
KV concurrency budget, and re-check at the next model class — KV/token is
architecture-dependent (layers, GQA KV-head count, head dim, dtype), not a
function of parameter count alone; "a 30B model has ~half the KV/token" is
the kind of claim to verify for your specific model, not assume [I].

## RAG's place in the inference stack
```
RAG request
   → embed + retrieve + rerank (ms-scale, CPU/GPU, not the LLM)
   → prompt assembly (instruction block FIRST, then chunks, stable order)
   → serving engine: continuous batch + paged KV + prefix cache
   → prefill (compute-bound, dominates TTFT)
   → decode (memory-bound, KV grows)
   → answer + citations
```
The retrieval stack's latency (embed + ANN + rerank, 08/14) is usually *small*
against prefill [I: ms vs seconds] — the optimization priority in most
production systems is (1) context size, (2) prefix-cache-friendly ordering,
(3) prefill pool sizing, and only then (4) retrieval latency. That ordering is
reversed in latency-critical low-context systems (structured RAG, 30: the
database round-trip *is* the latency).

## Key Takeaways
1. RAG makes requests prefill-heavy: TTFT becomes the SLO; prefill is
   compute-bound, decode memory-bound.
2. Context tokens are KV: at 128 KiB/token, 5.12K tok ≈ 640 MiB and 25.6K tok
   ≈ 3.1 GiB per sequence [E] — k is a concurrency budget.
3. Order the prompt for the prefix cache: instructions first, chunks in stable
   order — conditionally-free TTFT reduction when chunk sets overlap.
4. Batch RAG traffic deliberately (chunked prefill / P-D separation) — long
   prefills straggle mixed batches.
5. Optimization priority: context size → prefix ordering → prefill pools →
   retrieval latency; reversed when retrieval dominates (30).

## Related
[44 economics](44-rag-economics.md) · [42 caching](42-rag-caching.md) ·
[50 observability](50-rag-observability.md) ·
`../Inference/The-Life-of-a-Token.md` · `../Inference/Continuous-Batching.md` ·
`../KV-Cache/Prompt-and-Prefix-Caching.md` · `../Serving-Engines/Engine-Landscape.md`
