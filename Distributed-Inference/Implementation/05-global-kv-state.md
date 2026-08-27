# Implementation 05 — Global KV State: KVBM & the Cluster-Wide Index
`LAST_UPDATED: 2026-08-26 · Status: implementation page (PART 2 series) · the substrate every
other implementation page reads from` · Concept (object model, addressing, identity) in
`KV-Cache/Architecture-Overview.md` and `KV-Cache/Distributed-KV-Cache.md`. This page owns
the **implementation** of the cluster-wide KV map: who owns it, how it stays current, and
how consistency/staleness are handled — Dynamo's **KVBM + global radix registry** and
llm-d's **event-driven global index**.

## 30-Second Explanation
Every routing, offload, and P/D decision reads the answer to one question: *which block of
this request's prefix is on which (tier, node, rank)?* That answer lives in a **cluster-wide
KV map**. The two implementations build it differently: **Dynamo** keeps a **router-owned
global radix-tree registry** (its control plane owns the state); **llm-d** assembles a
**global index from engine-emitted KV events** on Kubernetes (the platform aggregates what
the engines report). Both must answer the same consistency question: *how fresh is my map?*

## Why a global map is the substrate
Without it, routing cannot know where a prefix lives (→ fleet re-prefills the same system
prompt), offload cannot find spilled blocks (→ stranded cache), and P/D cannot pick the
(c1−h) transfer set. The map is read by `03-kv-aware-routing.md`, written by
`02-offload-and-tiering.md` and `06-nixl-transfer.md`, and consumed by
`04-pd-orchestration.md`. It is *the* structure that upgrades a collection of engines into
a distributed inference platform.

## Dynamo — KVBM + the registry (implementation)
From current README + design docs [F, fetched 2026-08-26]:
- **KVBM (KV Block Manager)** — "offloads KV cache across GPU → CPU → SSD → remote storage"
  [F: README]. It manages the tiered *store*; per-backend support ✅TRT-LLM/✅vLLM/🚧SGLang
  [F: README]. Blocks are addressable cluster-wide — a decode worker can pull a block from
  another node's tier.
- **Global radix-tree registry** — the router's cache-state index for hit-rate scoring
  (`03-kv-aware-routing.md`). It is the structural cousin of SGLang's in-process radix cache,
  lifted to the cluster (`GPU-Systems/SGLang.md`).
- **1.0**: storage-tier offload (S3/Azure) + **global KV events** for cluster-wide cache
  visibility [F: README]. The KVBM's tier migrations are emitted as events that keep the
  routing state fresh — i.e. the write path of the map.
- So Dynamo's map is **router-owned**: the control plane (Rust) holds the registry; the
  KVBM is the store it describes. Both are in-project artifacts.

## llm-d — the event-driven global index (implementation)
From README (v0.8) + v0.9 docs [F, fetched 2026-08-26]:
- **Mechanism**: "precise global indexing of the KV cache state" via "**event-driven tracking
  of cache state across all model servers** (vLLM KV-cache events → global index)" [F: v0.9
  docs]. The index is *assembled from what the engines report*, not held by a router.
- **Consumers**: the EPP's KV-cache-affinity score (`03-kv-aware-routing.md`) and the tiered
  offload module (`02-offload-and-tiering.md`) both read the index. **Offload and index are
  coupled**: offloaded blocks are tracked globally so routing can find them.
- **Descriptors**: the same structural idea as Dynamo's registry, with a different owner
  and plumbing — "the difference: llm-d's index is assembled from **engine-emitted events on
  K8s**, Dynamo's is a **router-owned registry in its own control plane**"
  (`Distributed-Inference/llm-d.md` §KV-cache state; `Distributed-Inference/Dynamo-vs-llm-d.md`).

## Consistency & staleness — the cross-cutting implementation problem
Both maps are **eventually consistent** views of a moving state (blocks being allocated,
evicted, offloaded every moment). Implementation surfaces:
- **Window of staleness**: between a worker evicting a block and the event reaching the map,
  routing may send a request expecting a hit → re-prefill. The cost = the re-prefill the map
  failed to avoid. Frequency of events / TTL of entries trades freshness for overhead.
- **Dynamo's escape hatch**: `--no-router-kv-events` prediction-based mode — estimate cache
  state instead of tracking it, at the cost of drift [F: README].
- **Synchronous vs async snapshots**: P/D handoff needs KV *present* before decode starts;
  replicated copies can be proactive (`KV-Cache/Distributed-KV-Cache.md` §consistency).
- **Two owners, two failure profiles [I]**: a router-owned registry fails when the router
  is wrong/stale but needs no event pipeline; an event-driven index fails when the event
  pipeline is delayed/dropped but never guesses on its own.

## What the map must record (checklist, both platforms)
For each block/prefix: **identity** (hash or radix path) · **placement** `(tier,node,rank)`
· **refcount/replication** (how many copies) · **timestamp/version** (for staleness) ·
**tier** (HBM vs CPU vs SSD vs remote — for hit-tier-aware decisions, `02` page).
Dynamo's radix registry + KVBM and llm-d's index both encode this; the *granularity of
identity* (per-block vs per-prefix) is a real perf trade-off (finer = more accurate scoring,
more index traffic).

## Failure modes (implementation surfaces)
- **Stale hit claims** → re-prefill storm the map failed to prevent (the core staleness cost).
- **Stranded offloaded blocks** — index loses a block's location after a restart →
  cache unreachable; needs index durability/replay (llm-d active-active HA [F: README] is
  one control-plane answer).
- **Index traffic overhead** at cluster scale — every block event hits the map; a naive
  design becomes a bottleneck (why Dynamo makes events *optional* via prediction mode).

## Related
`01-distributed-kv.md` (placements) · `03-kv-aware-routing.md` (consumer) ·
`02-offload-and-tiering.md` (writer/consumer) · `04-pd-orchestration.md` (consumer) ·
`06-nixl-transfer.md` (writer) · `KV-Cache/Architecture-Overview.md` (object model) ·
`KV-Cache/Distributed-KV-Cache.md` (consistency) ·
`Inference/Production-Serving/08-cache-aware-routing.md` ·
`GPU-Systems/SGLang.md` (in-engine radix cousin) · `Production-Operations/12-kv-cache-reliability.md`

## Key Takeaways
1. The cluster-wide KV map is **the substrate**: every other implementation page reads or
   writes it. Without it there is no platform, just engines.
2. Two ownership models: **Dynamo = router-owned global radix registry + KVBM store**;
   **llm-d = event-driven global index assembled from engine KV events** [F: both].
3. Both maps are **eventually consistent** — staleness is the central implementation cost;
   Dynamo exposes a prediction-mode `--no-router-kv-events` escape hatch [F].
4. Record identity, placement, refcount, timestamp, tier per block; the identity granularity
   (block vs prefix) is a real accuracy-vs-traffic trade-off.
