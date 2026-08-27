# Prompt & Prefix Caching (KV Reuse)
`LAST_UPDATED: 2026-08-26` · Status: deep-dive page

## 30-Second Explanation
If request N shares a prefix with a request that already ran, the shared K,V for that
prefix are already sitting in HBM — you can **skip recomputing them** on prefill. A
3k-token prompt with a 2.4k prefix hit costs ~17 ms of prefill instead of ~85 ms [E:
see Production-Serving/08]. This page is about *how* shared prefixes are found, stored,
and reused: the mechanism stack (hash-based APC, radix-tree RadixAttention, LCP matching),
granularity, and cache-as-a-service.

## Terminology — don't conflate the four
1. **KV cache** (per-request, transient): saves recompute *within one* generation.
2. **Prefix caching** (structural reuse): saves prefill *across* requests sharing a prefix.
   The reuse unit is the *prefix* (contiguous leading tokens), found structurally.
3. **Prompt caching** (product term, e.g. Anthropic/OpenAI APIs): exposes the same
   mechanism as a pricing/API feature — "cache the system prompt, pay less for reused input"
   [F: Anthropic prompt caching docs; OpenAI prompt caching docs]. Engine-wise it *is*
   prefix caching; the API term adds billing/tokenizer semantics.
4. **Semantic/context caching** (agent memory, RAG store): a *content-addressed* reuse of
   retrieved context — distinct mechanism, see `Context-Engineering/Agent-Memory.md` and
   `RAG/`. Not this page.
[I: the taxonomy; 1–2 grounded in [F] engine docs, 3 in [F] vendor API docs.]

## The mechanism stack (increasingly structural)
### 1. Hash-based APC (Automatic Prefix Caching) — vLLM [F: docs]
- Hash the token stream; match a shared **prefix hash** → block list. Physically shares
  the paged blocks via refcounts (→ `Paged-KV-Cache.md`).
- Granularity: *longest token-prefix match*. Two prompts differing at token 500 share
  blocks [1..499] only.
- Cheap, deterministic, exact (token-identical prefixes). Does not exploit tokenizer-
  invariant structure beyond exact match.

### 2. RadixAttention — SGLang [F: SGLang blog; Serving-Engines/SGLang.md]
- Store prefixes in a **radix tree** (trie) of tokens/blocks; reuse is *structural*: any
  request whose tokens walk the same tree path shares KV with any other that walked it.
- Supports eviction of individual tree nodes (LRU on the tree) and prioritizes the
  most-recently-used common prefixes — so a multi-turn conversation keeps its recent
  shared trunk hot.
- Vendor-reported 5×-class speedups on shared-prefix workloads (labeled vendor claim).
- Why 64-wide blocks pair well here: fewer, larger tree nodes → less bookkeeping
  (→ `Paged-KV-Cache.md` block-size trade-off).

### 3. LCP matching (the routing side)
Radix-tree **longest-common-prefix** length is the metric a router uses to decide *where*
to send a request ("this replica already holds the longest shared prefix") →
`Inference/Production-Serving/08-cache-aware-routing.md` and
`Inference/Production-Serving/09-pd-disaggregated-routing.md`. Router caches must be kept
honest (age out hit claims).

## Hit granularity & why it matters
A "cache hit" is not binary — it is a **fraction of the prompt** reused:
```
effective prefill = (1 − hit_fraction) · S
```
- **[E]** 2400/3000 = 80% shared: prefill runs on 600 tokens, ~5× less prefill work,
  ~5× less TTFT from prefill — this is the 85→17 ms example.
- Agentic/RAG hit rates of 50–90% are plausible [I, workload-dependent; measure] where
  system prompts, tool schemas, and retrieved chunks are large and stable.
- The *value is in the prefix*, so prompt *order* matters enormously: keep the stable
  system prompt, tool schemas, and shared RAG chunks at the **front** of the message; only
  the tail (per-turn variation) should vary, or the shared trunk shrinks. This is exactly
  "stable-prefix engineering" — `Harness-Engineering/Context-Management.md`.

## Cache-as-a-service / connectors
- **LMCache** [F: LMCache docs] — an open KV-cache-as-a-service layer: stores KV across
  GPU/CPU/disk, and pairs with the vLLM/SGLang `Connector` abstraction for *disaggregated /
  distributed* cache sharing (`Distributed-KV-Cache.md`).
- **vLLM connectors** — NixlConnector (UCX+GDS), LMCache, Mooncake, FlexKV, Offloading,
  Multi [F: vLLM disagg docs] → the transfer half of reuse.
- **Dynamo KVBM** [F: README] and **llm-d tiered prefix cache** [F: README] — platform-
  level cache managers with hit-rate instrumentation.

## How to measure
- Per-replica prefix-cache hit rate (engine metric) and its split by tenant.
- TTFT delta between hit vs miss of the same prompt-length bucket.
- **Measured in this wiki:** `Labs/Lab-13` executed 2026-08-17 — **8.7× TTFT cold→warm on
  an 8k identical prefix**, cached-prefix processing ~17.6k tok/s vs ~2.0k cold [E].

## Failure modes
- **Hit-rate illusion:** a high block-hit rate with low prefix-value (short shared run)
  overstates benefit → track *reused-token fraction*, not block hits.
- **Prompt-order fragility:** moving a stable chunk after a varying one silently kills the
  shared prefix (see above).
- **Stale routing claims:** replica evicted the prefix; router still sends work there
  (`Hierarchical-Offloading.md` eviction interplay; `Inference/Production-Serving/08-cache-aware-routing.md`).
- **Tenant bleed:** shared cache across tenants can leak in principle → per-tenant trees
  where isolation matters.
- **Cost accounting:** caching is only a win when the prefix is *actually reused*; a
  pay-per-unique-prefix pricing model can invert the economics
  (`Platform-Economics/08-kv-cache-economics.md`).

## Related
`Architecture-Overview.md` · `Paged-KV-Cache.md` (the blocks being shared) ·
`Distributed-KV-Cache.md` (sharing across nodes) · `README.md` ·
`Inference/Production-Serving/08-cache-aware-routing.md` (routing on the hit) ·
`Harness-Engineering/Context-Management.md` (stable-prefix engineering) ·
`Serving-Engines/vLLM.md` (APC) · `Serving-Engines/SGLang.md` (RadixAttention) ·
`Labs/Lab-13` (measured, [E]).

## Key Takeaways
1. Prefix caching replaces prefill FLOPs with a lookup; benefit scales with *reused-token
   fraction*, not binary hits.
2. Hash-APC (exact, simple) vs radix-RadixAttention (structural, evictable) are the two
   real mechanisms; LCP is the routing signal on top.
3. Prompt ordering is a silent killer — keep stable content first or the shared trunk dies.
