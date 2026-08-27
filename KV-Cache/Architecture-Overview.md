# KV-Cache Architecture: The Unified Model
`LAST_UPDATED: 2026-08-26` · Status: core anchor page for the caching knowledge area

## 30-Second Explanation
Treat the KV cache as **one distributed, tiered, shared memory object** that every
request reads and mutates. Each request's KV starts empty (or as a *shared prefix*),
grows one token at a time, and occupies paged blocks that may be shared, moved between
machines, spilled to slower tiers, trimmed, and routed on. Prefill/decode disaggregation
is the special case where that object must physically *move* at the phase boundary.
Everything that makes serving fast is an operation on this object.

## Why a single mental model
The KV cache is the only stateful object in stateless LLM serving. The system software
layer — engines, routers, disaggregated platforms — exists largely to manipulate it:

| Operation | Engine | System cost it trades |
|---|---|---|
| Allocate | PagedAttention / vLLM blocks | HBM capacity |
| Share | prefix cache (APC / radix) | prefill recompute (FLOPs + TTFT) |
| Move | P/D connectors, NIXL, LMCache | fabric bandwidth |
| Tier | hierarchical offload | CPU/SSD capacity ⇄ NVLink/PCIe latency |
| Trim | eviction / compression | quality (attention mass) |
| Route | KV-aware router | placement correctness ("where is my prefix") |

[F-sourced to the engine/document set cited across the section: vLLM, SGLang, Dynamo,
llm-d, Mooncake; [I] for the unifying framing itself.]

## The two pillars (PART-1 framing)
**Pillar A — the caching stack** (leaf pages of `KV-Cache/`): how KV is stored, shared,
compressed, trimmed, tiered.
**Pillar B — disaggregated inference** (already deep in the wiki): pitting compute-bound
prefill against bandwidth-bound decode on separate pools, joined by a KV-transfer fabric.
They meet at one point: **the KV transfer**. Pillar B is impossible without Pillar A's
ability to serialize, address, and re-locate the cache.

→ Pillar B lives at `Inference/Prefill-Decode-Disaggregation.md`,
`GPU-Systems/Prefill-Decode-Disaggregation.md`,
`Inference/Deep-Dives/pd-disaggregation-deep-dive-2026-08-17.md`,
`Distributed-Inference/Overview.md`. This page does not re-derive it; it maps the
boundary and cross-links.

## The object model
- **Granularity:** a *block* (vLLM 16 tokens / SGLang 64 [F: docs]) is the allocatable,
  addressable, shareable, movable unit — the KV analogue of a cache line / a memory page.
- **Identity:** a prefix is identified by a hash (APC) or a tree path (RadixAttention);
  a *block ID list* is the key the router and transfer layer operate on.
- **Addressing:** block table per request (the "page table"); shared blocks refcounted.
- **Location:** each block sits at a (tier, node, rank) — that tuple is the *placement*.

## The reuse stack (levels of caching)
Distinct mechanisms, often conflated:
1. **KV cache** (per-request, transient) — saves recompute *within* one generation.
2. **Prefix / prompt cache** (cross-request, structural) — saves prefill *across*
   requests sharing a prefix (system prompt, tool schemas, RAG chunks).
3. **Hierarchical cache** (cross-tier, capacity) — keeps more prefixes resident by
   spilling to CPU/SSD instead of evicting.
4. **Distributed / replicated cache** (cross-node) — keeps a prefix reachable from
   more than one compute node.
→ depth: `Prompt-and-Prefix-Caching.md`, `Hierarchical-Offloading.md`,
`Distributed-KV-Cache.md`.

## Cache economics in one line
A cache hit replaces `~S·d` prefill FLOPs and its latency with a **lookup + (maybe)
transfer**. The value of a prefix = (prefill saved) − (memory/eviction opportunity cost).
The economics are worked out in `Platform-Economics/08-kv-cache-economics.md` and the
router-facing version in `Inference/Production-Serving/08-cache-aware-routing.md`.

## Decision map (which page to read)
- "How big is my KV and will it fit?" → `README.md` memory equation + `Paged-KV-Cache.md`.
- "Why is my TTFT high on repeated prompts?" → `Prompt-and-Prefix-Caching.md` (hit rate
  first, then mechanism).
- "Should I split prefill/decode?" → Pillar B pages (`Inference/Prefill-Decode-Disaggregation.md`, `GPU-Systems/Prefill-Decode-Disaggregation.md`).
- "KV overflows HBM — offload or evict?" → `Hierarchical-Offloading.md` vs `Eviction.md`.
- "Which replica should serve this request?" → `Inference/Production-Serving/08-cache-aware-routing.md`.

## Failure modes (cross-cutting)
- **Cache double-count:** scoring "hit bonus" on top of reduced prefill work — same term
  twice (`Inference/Production-Serving/08-cache-aware-routing.md`).
- **Stale hit claims:** replica evicted the prefix but the router still routes for it.
- **Offload cliff:** a spill-to-SSD "hit" is 10–100× slower to reload than an HBM hit
  (`Hierarchical-Offloading.md`).
- **Transfer > payoff:** moving KV costs more than the prefill it replaces on slow fabric
  (`Inference/Prefill-Decode-Disaggregation.md` break-even).
- **Quality silently lost:** aggressive eviction drops attention sinks / heavy hitters
  (`Eviction.md`).
- **Tenant bleed:** a shared prefix cache can leak context across tenants where isolation
  matters (`Inference/Production-Serving/13-multi-tenancy-fairness-priority.md`).

## Related
`Paged-KV-Cache.md` · `Prompt-and-Prefix-Caching.md` · `Distributed-KV-Cache.md` ·
`Hierarchical-Offloading.md` · `Eviction.md` · `Inference/Prefill-Decode-Disaggregation.md` ·
`Inference/Production-Serving/08-cache-aware-routing.md` · `Distributed-Inference/Overview.md` ·
`Platform-Economics/08-kv-cache-economics.md`.

## Key Takeaways
1. One mental model: the KV cache is a distributed, tiered, shared, paged memory object.
2. Caching and disaggregation meet at the KV-transfer point — that is the hard engineering.
3. Most serving performance work is a manipulation of this one object; diagnose by asking
   *which operation* (allocate/share/move/tier/trim/route) is the bottleneck.
