# Implementation 02 — Offload & Tiering: The Tier-Migration Control Loop
`LAST_UPDATED: 2026-08-26 · Status: implementation page (PART 2 series)` · Concept + physics
(per-tier bandwidth/latency, the offload-vs-evict decision) in `KV-Cache/Hierarchical-Offloading.md`
and `KV-Cache/Eviction.md`. This page owns the **implementation**: the control loop that
decides which blocks sit in which tier and moves them — as built by Dynamo's KVBM, llm-d's
hierarchical offload path, and the engine connectors.

## 30-Second Explanation
Offloading is not a batch data dump — it is a **continuous migration control loop**:
(1) watch HBM pressure, (2) pick cold blocks to age toward CPU/SSD, (3) issue write-behind
moves at block granularity, (4) predict the next request's prefix and prefetch it back up
(5) without stalling the hot path. Dynamo's **KVBM** and llm-d's **tiered KV offload** are
the two platform-class implementations; both sit on top of engine connectors and move
blocks with NIXL/GDS.

## The tier problem, stated in implementation terms
```
        hot:  GPU HBM     (resident, ~2 long-context sessions [E, 01 page])
        warm: CPU DRAM    (offload extends to ~16 sessions [E])
        cool: local NVMe  (+10-100×)   ← GDS backend moves disk↔HBM directly, no host bounce
        cold: remote/object store (S3/Azure)  ← Dynamo 1.0 storage-tier offload
```
The control loop must answer three questions a "dump it to disk" batch job gets wrong:
1. **Which blocks age out?** (eviction candidate selection — LRU-with-sinks, radix-node
   priority, or learned reuse; `KV-Cache/Eviction.md`)
2. **When to move them?** (bandwidth budget — don't starve the fabric the KV handoff needs)
3. **When to bring them back?** (prefetch decision — a cold SSD "hit" that isn't prefetched
   is a 10–100× slower reload than an HBM hit, `KV-Cache/Hierarchical-Offloading.md` offload-cliff)

## Dynamo KVBM — the implemented control loop
From the current main README [F, fetched 2026-08-26]: "**KVBM** … offloads KV cache across
GPU → CPU → SSD → remote storage [to] extend[ ] effective context length beyond GPU memory."
Implementation facts:
- **Ownership**: KVBM is a platform component (Dynamo) with per-backend support — README
  feature matrix: **KVBM ✅ TensorRT-LLM, ✅ vLLM, 🚧 SGLang** [F: README].
- **Object model**: blocks are addressable cluster-wide; a decode worker can *pull* a block
  from another node's tier instead of re-prefilling (`Distributed-Inference/NVIDIA-Dynamo.md` §KVBM).
- **1.0 additions**: storage-tier offload (S3/Azure) + **global KV events** for cluster-wide
  cache visibility [F: README "New in 1.0"] — that is, the tier-migration decisions are
  observable as events, feeding routing (`05-global-kv-state.md`).
- **Why migration, not just placement**: because a block's hotness changes over a
  conversation (trunk always hot, recent turns hot, old turns cool) the system must *move*
  blocks between tiers in both directions — the write-behind/aging part of the model in
  `KV-Cache/Hierarchical-Offloading.md` §offload+prefetch.

## llm-d — the tiered prefix cache implementation
README [F, v0.8, fetched 2026-08-26]: tiered offloading "to CPU or disk … with precise
global indexing of the KV cache state" — i.e. **offload and index are the same feature**:
- The **KV offloading** module is a tiered storage hierarchy (CPU, SSD) (`Distributed-Inference/llm-d.md` §Advanced
  Patterns). Documented result: **13.9× hierarchical-KV-offload throughput @250 concurrent vs
  GPU-only (4× H100)** [F: README, vendor-adjacent].
- The offloaded state is tracked by the **global KV index** — offload without an index
  would strand blocks ("where did I put your prefix?"); llm-d couples them so routing can
  find offloaded blocks (`05-global-kv-state.md`).
- vLLM-native **CPU-memory tiering** path (v0.4 news) + engine connectors [F: README].

## The engines' offload connectors (the floor beneath both platforms)
vLLM's disagg connector ecosystem and TRT-LLM's cache transmission include offload-class
paths (NIXL/Mooncake connectors; LMCache) (`Inference/Prefill-Decode-Disaggregation.md`
§research lineage). Platform offloading **orchestrates** these; the engine executes the
per-connector KV move (NIXL `post` = async, one block list).

## When offload is the right lever (implementation judgment) [I]
- **Right**: long agent sessions with a working set that is temporarily huge but
  persistently small (each turn re-touches trunk + recent history); RAG caches; concurrency
  heavy enough that the ~2-HBM-sessions ceiling [E] binds but CPU (16) does not.
- **Wrong**: short-lived requests with no reuse (offload overhead, zero dividends);
  latency-critical streaming where a from-SSD reload misses the ITL SLO; fabrics/NVMe slower
  than re-prefilling (`KV-Cache/Hierarchical-Offloading.md` §when-it-hurts).

## Failure modes (implementation surfaces)
- **Offload cliff**: SSD reload ~seconds → TPOT/TTFT spike; must be masked by lookahead
  prefetch or the router must price hit-*tier* (`Inference/Production-Serving/08-cache-aware-routing.md`).
- **Tier-migration thrash**: prefixes flip HBM↔DRAM; watch migration rate, not hit rate.
- **Cross-tier consistency**: block updated on GPU while a stale copy sits on DRAM → an
  invalidation protocol is required (same family as distributed-KV consistency).
- **Tenant bleed** on shared SSDs (`Production-Operations/12-kv-cache-reliability.md`).

## Related
`01-distributed-kv.md` (placements across tiers) · `05-global-kv-state.md` (offload feeds the
index) · `06-nixl-transfer.md` (the moves use NIXL/GDS) · `04-pd-orchestration.md` ·
`03-kv-aware-routing.md` (prices hit tier) · `KV-Cache/Hierarchical-Offloading.md` ·
`KV-Cache/Eviction.md` · `KV-Cache/Distributed-KV-Cache.md` ·
`GPU-Communication/07-nixl-deep-dive.md` (GDS backend) ·
`Inference/Production-Serving/08-cache-aware-routing.md`

## Key Takeaways
1. Offloading is a **continuous migration control loop** (watch → age → write-behind →
   prefetch), not a batch dump — that loop is the implementation.
2. Dynamo KVBM (✅TRT-LLM/✅vLLM/🚧SGLang) and llm-d (tiered prefix cache + global index)
   are the two platform implementations; both move blocks with NIXL-class connectors.
3. Offload is the capacity lever: HBM holds ~2 long-context sessions [E], CPU ~16, NVMe
   hundreds — the whole economic case for tiering.
