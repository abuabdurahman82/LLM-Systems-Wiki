# RAG Economics — The Cost Decomposition of Every Request

`LAST_UPDATED: 2026-08-29` · Status: core page · All [E] numbers from the
machine-verified constants bank (2026-08-29); per-tenant/metering economics
deliberately live in `../Platform-Economics/37-rag-economics.md` (link, not
duplicate).

## 30-Second Explanation
A RAG request costs money in two distinct places: **ingestion** (once per
corpus update: parse + embed + index) and **query** (per request: embed +
retrieve + rerank + context tokens + generation). The query path is where
retrieval design shows up as *dollars*: each chunk you pack is prefill tokens,
KV cache, and attention cost. A robust heuristic: **retrieving fewer,
better chunks is usually cheaper *and* better** — the context is a budget, and
the reranker (14) is the mechanism that lets you shrink it without losing
quality.

## The cost decomposition
Per request (query path), additive [E: machine-verified where a number is
shown; model pricing is illustrative at $3/$15 per 1M in/out unless stated]:

| Stage | Cost driver | Illustrative value |
|---|---|---|
| Query embedding | 1 embed call (~100 tok) | ≪$0.001 (batched/local) [I] |
| Retrieval (ANN) | index compute; ms-scale | ≪$0.001 [I] |
| Reranking | cross-encoder over 50–100 pairs | ≪$0.001 if local/GPU [I]; more if API |
| **Context (input tokens)** | k chunks × chunk tokens | 10×512 tok = 5,120 tok → **$0.0154** (the bank's $0.0153 is the truncated form of $0.01536) |
| **Generation** | answer tokens (~500) | 500 tok → **$0.0075** |
| Verification (if any) | a second LLM pass (judge) | same order as generation |

→ **≈ $0.023/request at 10 chunks; ≈ $0.084 at 50 chunks** [E] — a 5× context
delta that is the single most leveraged cost knob in the whole system, because
it is *entirely under retrieval design* (k, chunk size, compression — 41).

Ingestion path, per 1M documents [E]: parsing (CPU, format-dependent),
embedding 500M tokens → **$65 at $0.13/1M, $10 at $0.02/1M** (model-dependent),
index build (HNSW: ~10% memory overhead on vectors, 08) + storage
(1M×384d float32 = 1.43 GiB raw). Contextual retrieval (40) adds an LLM pass
per chunk: **~$9,216 for 1M chunks** at $3/$15 [E] — the single largest
ingestion line item when used.

## The quality/length/cost frontier
Three knobs, one trade-off [I: the frontier is task-dependent; the direction
is the robust part]:

```
context tokens
   ↑
   │           · quality ceiling (everything relevant is in context)
   │        ··
   │      ···  ← most RAG systems live here: enough context to answer,
   │    ····     not enough to dilute attention or blow the budget
   │  ·····
   │ ·····  ← small-k zone: cheap, fast, but retrieval-miss-dominated
   └────────────────────────→ retrieval precision
```

- **More context** buys robustness to retrieval imprecision (if the right
  chunk is anywhere in the 20, the LLM may still find it) but pays in
  prefill/KV/cost and buys *less* the longer the context gets (attention
  dilution, lost-in-the-middle — `../Context-Engineering/`), so the curve
  flattens then bends down [I: consistent with long-context behavior
  literature].
- **Better retrieval** (hybrid + rerank, 13/14) moves you *left* on the curve:
  same quality at a smaller k. This is why the 80/20 advice is "rank better,
  pack less" — the reranker pays for itself in context tokens.
- **Compression** (41) moves you down-left: same evidence, fewer tokens.

## Why "fewer better chunks" wins most of the time
The arithmetic is not subtle [E, from bank]: going from 50 to 10 chunks at
512 tok each cuts $0.0614/request at $3/$15 (40 fewer chunks × 512 tok =
20,480 input tok; generation is unchanged and therefore not counted) — at
1M requests/month that is
~$61K/month of input tokens, *before* counting the latency (TTFT) and
quality (less dilution) gains. The cost of the reranker that makes 10 chunks
enough is orders of magnitude smaller. The exception classes [I]: (a)
multi-hop/agentic patterns that *need* broad recall (26/27) — there k is
information, not padding; (b) high-stakes domains where you deliberately
over-retrieve and let the model check (the cost is the price of auditability);
(c) cheap models + expensive retrieval errors, where over-retrieval is the
cheaper hedge.

## Where the money actually goes (system view)
At scale, the ranking of cost lines is usually [I: typical enterprise RAG;
verify with your own per-stage cost breakdown (50)]:
1. **Context tokens** (input) — retrieval design decides it.
2. **Generation tokens** — prompt verbosity and answer length decide it.
3. **Ingestion** (embedding + contextual enrichment) — corpus size and update
   cadence decide it; amortized over queries.
4. **Verification/judge passes** — if you run LLM-as-judge on every answer,
   it is a full extra generation line (45).
The operational consequence: **cost observability must be per-stage** (50),
because "RAG is expensive" is not an actionable diagnosis — "the context
median is 14K tokens because the router over-fetches" is.

## Key Takeaways
1. Two cost domains: ingestion (amortized) and query (per request); retrieval
   design lives almost entirely in the query domain.
2. Context tokens are usually the dominant query cost (at the page's ~500-tok
   answer; at ≥1,024 output tokens, generation ties or exceeds the 10-chunk
   context cost); 10 vs 50 chunks is a 5× input
   cost delta [E].
3. Reranking + compression let you buy quality with fewer tokens — "fewer
   better chunks" is the common-sense economics heuristic (the exception
   classes above are where it inverts).
4. Contextual retrieval and LLM judge passes are the big *line items* —
   budget them explicitly.
5. Cost observability is per-stage (50); tenant-level economics are
   `../Platform-Economics/37-rag-economics.md`.

## Related
[43 inference engineering](43-rag-inference-engineering.md) ·
[41 compression](41-context-compression.md) · [14 reranking](14-reranking.md) ·
[50 observability](50-rag-observability.md) ·
`../Platform-Economics/37-rag-economics.md` · `../Inference/The-Life-of-a-Token.md`
