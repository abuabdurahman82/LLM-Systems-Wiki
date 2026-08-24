# Cache-Aware Routing — Prefix Locality as a First-Class Signal
`LAST_UPDATED: 2026-08-22` · Status: core page · Extends term 2/4 of
[03](03-estimating-remaining-work.md); engine-side mechanics in
`../../KV-Cache/README.md`.

## 30-Second Explanation
A prompt that shares a prefix with something a replica already cached is
*dramatically cheaper there*: a 3k prompt with a 2.4k hit costs 17 ms of
prefill instead of 85 ms [E]. Cache-aware routing sends requests where their
prefixes live. The two traps: the cache is **stateful and shared** (your
routing changes what gets cached and what gets evicted), and **locality
concentrates load** (the replica holding the hot prefix becomes a hot spot).

## Why it is a first-class signal
The prefix hit simultaneously reduces (a) this request's TTFT, (b) its share
of the queue, and (c) the replica's KV-write traffic (deep-dive §3.2). In
agentic and RAG workloads — system prompts, tool schemas, retrieved context —
hit rates of 50–90% are plausible [I, workload-dependent; measure]. That is
the regime where vendor-reported gains are largest: llm-d reports 3×
throughput and 2× TTFT vs round-robin with prefix-cache-aware routing, and
Dynamo reports 2× TTFT from KV-aware routing [F: vendor READMEs, see 14].

## The cache-value balance
Routing to a cache-warm replica *consumes* and *produces* cache value. The
per-request accounting on replica i:
```
ΔV_i = value_cached(r, i) − eviction_cost_i(r)
```
- **value_cached**: future prefill savings from the prefix this request
  leaves behind (zero for a one-off prompt; high for a shared system prompt).
- **eviction_cost**: spikes when free KV blocks are low — evicting a hot
  prefix to make room is a *cross-request* (and cross-tenant) tax
  [I: deep-dive §3.5].
A router that only reads "hit fraction" and ignores eviction pressure will
churn the cache it is trying to exploit.

## Hot-spotting and its fixes
The defining failure: one popular system prompt routes everything to its
holder until its KV pool fills. Mitigations, in order of operational cost:
1. **Replicate hot prefixes**: pin the top-K shared prefixes on every replica
   at deploy/warm-up time (they are few and known — agent system prompts,
   tool schemas). Turns cache locality from a routing constraint into a
   constant.
2. **Cap cache-driven placement**: cache term may only break ties within a
   load band (e.g. only if ERW gap < 20%), so locality never overrides a
   large load imbalance.
3. **Shard by tenant, not by prompt**: give each tenant a home set of
   replicas; cross-tenant eviction disappears (see 13).

## Session affinity ≠ cache affinity
Sticky sessions were the classic approximation. They are wrong twice: later
turns of a session may *diverge* from the cached prefix (branching agent
loops), and different sessions may *share* prefixes (same system prompt).
Route on measured prefix overlap (radix-tree longest-common-prefix on the
gateway side is O(prefix length) [I]), not on session identity.

## Tiered KV changes the math
With tiered KV (HBM → host DRAM → SSD → remote, e.g. Dynamo's KVBM [F]), a
"hit" may cost 10–100× different reload times depending on tier
[A: order-of-magnitude, measure per deployment]. The routing signal becomes
*hit tier*, not hit bit — a DRAM hit on replica A may be worse than an HBM
hit on replica B once decode-side load is priced in.

## 80/20
Pin your top shared prefixes on all replicas, then add a cache-hit tie-breaker
to your existing policy. That captures most of the TTFT win without a
cache-value accounting system.

## Failure modes
- **Stale hit claims**: replica evicted the prefix under pressure; router
  still routes for it → cold prefill *and* a wasted placement. Age out hit
  claims; subscribe to eviction events where the engine emits them.
- **Cache double-count**: scoring "hit bonus" on top of reduced prefill work
  (they are the same term — see [03](03-estimating-remaining-work.md)).
- **Privacy/tenant bleed**: shared-prefix caches can leak across tenants in
  principle; keep cache trees per-tenant where isolation matters (13).

## How to measure it
- Per-replica prefix-cache hit rate (engine metric) and its split by tenant.
- TTFT delta between hit and miss requests of the same prompt-length bucket.
- Eviction rate of hot prefixes (evictions of prefixes with hit rate > X).
- Load concentration: share of traffic on the top-1 prefix-holding replica.

## Related
[03-estimating-remaining-work](03-estimating-remaining-work.md) ·
[06-router-architectures](06-router-architectures.md) ·
[13-multi-tenancy-fairness-priority](13-multi-tenancy-fairness-priority.md) ·
`../../KV-Cache/README.md` · `../../KV-Cache/Eviction.md` ·
`../../Serving-Engines/SGLang.md` (RadixAttention) ·
`../Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md` §3.2/§3.5

## Key Takeaways
1. Prefix locality is often the *dominant* routing signal in agentic/RAG
   workloads — measure hit rate first.
2. The cache is shared state with externalities: account for eviction cost,
   not just hit benefit.
3. Locality concentrates load: pin hot prefixes and cap cache-driven
   placement to avoid hot spots.
