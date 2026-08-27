# Distributed Inference — Implementation Layer (PART 2: how the systems really work)
`LAST_UPDATED: 2026-08-26 · Status: section landing` · This is **PART 2** of the
Disaggregated-Inference + Distributed-Infrastructure series. **PART 1** (in `KV-Cache/`)
built the *conceptual* model: the KV cache as a distributed/tiered/shared/paged object
(allocate → share → move → tier → trim → route), plus distributed KV, offload, and
cache-centric serving. **This sub-area owns the *implementation* layer**: the concrete
data structures, control loops, and wiring by which **NVIDIA Dynamo**, **llm-d**, and
**NIXL** actually realize those concepts.

Scope map (this section `Distributed-Inference/`):
- `Distributed-Inference/README.md` — the parallelism dimensions (TP/PP/DP/CP/EP) and their collectives
- `Distributed-Inference/Overview.md` — the five cluster jobs, KV-transfer physics, P/D break-even, cluster metrics
- `Distributed-Inference/NVIDIA-Dynamo.md` · `Distributed-Inference/llm-d.md` — the two platform deep dives (capability surface)
- `Distributed-Inference/Dynamo-vs-llm-d.md` — the head-to-head (same-layer rivalry)
- **`Implementation/` (this area)** — *how* the five jobs are built: distributed-KV,
  offload/tiering, KV-aware routing, P/D orchestration, the global KV state, and NIXL transfer

## 30-Second Explanation
PART 1 said *what* a distributed serving system must do to the KV object. PART 2 says
*how Dynamo, llm-d and NIXL do it in code*: which component owns each operation, what
data structure backs it, and what control-loop picks fire when. The through-line: **a
distributed inference platform is a distributed cache manager with a router and a
scheduler bolted on** — every one of its five jobs is an operation on the KV object,
implemented by a named component that holds the state and a control loop that reads it.

## The mapping (PART-1 concept → this area's implementation page)
| PART-1 concept (`KV-Cache/`) | Implementation page | Concrete mechanism |
|---|---|---|
| Distributed KV cache (`KV-Cache/Distributed-KV-Cache.md`) | `01-distributed-kv.md` | block tables + placement tuple (tier,node,rank); sharded vs moved vs replicated |
| Hierarchical offload (`KV-Cache/Hierarchical-Offloading.md`) | `02-offload-and-tiering.md` | the tier-migration control loop, write-behind/aging, prefetch, eviction signals |
| KV-aware / prefix routing (`KV-Cache/Prompt-and-Prefix-Caching.md` + `Inference/Production-Serving/08-…`) | `03-kv-aware-routing.md` | radix registry vs event-driven index; hit*fraction* scoring; the (1−h) transfer discount |
| P/D disaggregation (`Inference/Prefill-Decode-Disaggregation.md`) | `04-pd-orchestration.md` | pool roles/variants, two-endpoint selection, KV handoff protocol, Planner sizing |
| KVBM / global index (`KV-Cache/Architecture-Overview.md` object model) | `05-global-kv-state.md` | who owns the cluster KV map, how it stays current, consistency/staleness |
| KV transfer (`GPU-Communication/07-nixl-deep-dive.md`, `08-…`) | `06-nixl-transfer.md` | NIXL buffer lists, agent/registration, backends, one-sided semantics, overlap |

## Non-duplication contract
- The *concepts* and their **physics/economics** live in `KV-Cache/`,
  `Inference/Prefill-Decode-Disaggregation.md`, `Distributed-Inference/Overview.md`, and
  `GPU-Communication/08-nixl-kv-cache-transfer.md`. Implementation pages cross-link and
  surface those; they **never re-derive the math**.
- The *capability surface* of Dynamo/llm-d lives in `Distributed-Inference/NVIDIA-Dynamo.md` / `Distributed-Inference/llm-d.md` /
  `Distributed-Inference/Dynamo-vs-llm-d.md`. Implementation pages assume the capability exists and go one
  level down: *which component, which structure, which loop, which config flag*.
- [E] numbers reuse the canonical constants bank (128 KiB/token for the 8B-GQA example;
  4 GiB @ 32k; NVLink 900 GB/s / PCIe5 55 GB/s / 100 GbE 11.9 GB/s effective) so the
  tables agree with every sibling page — computed this session, no drift.

## How to read
As an inference/infra engineer, read a PART-1 concept page for the *physics*, then its
implementation page here for the *wiring*, then `Distributed-Inference/NVIDIA-Dynamo.md` / `Distributed-Inference/llm-d.md` for the
*capability and results*. Start with `05-global-kv-state.md` (the substrate every other
implementation page reads from), then `06-nixl-transfer.md` (the movement), then the
routing/offload/P-D control loops (`03`, `02`, `04`).

## Related
`Distributed-Inference/NVIDIA-Dynamo.md` · `Distributed-Inference/llm-d.md` · `Distributed-Inference/Dynamo-vs-llm-d.md` · `Distributed-Inference/Overview.md` ·
`KV-Cache/Architecture-Overview.md` · `KV-Cache/Distributed-KV-Cache.md` ·
`KV-Cache/Hierarchical-Offloading.md` · `KV-Cache/Prompt-and-Prefix-Caching.md` ·
`GPU-Communication/07-nixl-deep-dive.md` · `GPU-Communication/08-nixl-kv-cache-transfer.md` ·
`Inference/Prefill-Decode-Disaggregation.md` · `Inference/Production-Serving/08-cache-aware-routing.md`

## Key Takeaways
1. A distributed inference platform **is** a distributed cache manager + router +
   scheduler: five jobs, five control loops, all reading/writing one KV object.
2. Each implementation page names the **owning component** (Dynamo router/KVBM/Planner;
   llm-d EPP/index/offloader/WVA; NIXL agent) — that is the implementation content.
3. Never re-derive the physics here: every number cross-refs the canonical bank so the
   wiki stays in agreement.
