# Implementation 01 — Distributed KV: How the Cluster Holds the Paged Object
`LAST_UPDATED: 2026-08-26 · Status: implementation page (PART 2 series)` · Concept + physics
in `KV-Cache/Distributed-KV-Cache.md` (the three modes: sharded / moved / replicated) and
`KV-Cache/Paged-KV-Cache.md` (the block). This page owns the **implementation**: the data
structures and owners by which Dynamo, llm-d and the engines actually hold a distributed KV.

## 30-Second Explanation
A distributed KV cache is not one big store — it is **many small paged blocks, each with
an *identity* (a block ID / prefix path) and a *placement* `(tier, node, rank)`, plus an
index that says which block is where**. The three modes are three placement policies:
*sharded* (each block exists once, distributed by tensor layout — no copies; a logical
block's shards span the TP ranks), *moved* (a block relocates at a phase boundary — P/D),
*replicated* (a hot block is copied to N locations for locality). Everything else the
platform does — routing, offload, transfer — reads this placement index.

## The object model, implemented
From `KV-Cache/Architecture-Overview.md` (PART 1), the four primitives:
- **Block** = the allocatable/addressable unit (vLLM 16 tokens, SGLang 64 [F: docs]).
- **Block table (per request)** — the KV analogue of a memory page table: maps logical
  sequence position → physical block(s). Owned by the engine (`KV-Cache/Paged-KV-Cache.md`).
- **Placement tuple** `(tier, node, rank)` — *where* each block physically lives. This is
  the object the *platform* layer adds on top of the engine's local block table
  (`KV-Cache/Architecture-Overview.md` object model).
- **Identity** — a prefix is identified by hash (APC) or tree path (RadixAttention); the
  block-ID list is the key the router and transfer layer operate on.

## Who owns what (the split of ownership)
| Primitive | Owned by engine (in-process) | Owned by platform (cluster) |
|---|---|---|
| Block allocation / paged table | vLLM/SGLang/TRT-LLM scheduler | — |
| Placement index (which block on which (tier,node,rank)) | local block table only | **Dynamo KVBM / global radix registry; llm-d KV indexer** (`05-global-kv-state.md`) |
| Reference counting of shared blocks | in-engine refcount | replicated-index refcount (`03-kv-aware-routing.md` locality) |
| Movement decisions | P/D connectors (`NIXL`) | Dynamo router/KVBM; llm-d Router (`06-nixl-transfer.md`) |

The engine keeps KV **locally correct** for one instance; the platform keeps a **cluster
map** so routing and movement can be decided anywhere. That split (local block table vs
global placement index) is the single most important implementation fact here.

## Sharded KV, implemented (the TP case)
Under Tensor Parallelism each rank holds `h_kv/T` heads → `1/T` of the KV
(`GPU-Systems/Tensor-Parallelism.md`). Implementation note that matters:
- **No platform involvement**: this is the model's own layout, assembled across the TP
  group on every forward pass. It is "distributed" in the physical sense but not a
  *shared cache* — no redundant copies, no routing against it.
- **TP-final-gather is where platforms enter**: a request's KV is spread across T ranks
  (TP-sharded); *any* engine→engine handoff (prefill→decode, or turn→turn KV move) must
  gather or re-shard it first. This is a
  concrete NIXL transfer shape (`GPU-Communication/08-nixl-kv-cache-transfer.md` §1).

## Moved KV, implemented (P/D — the handoff)
```
request → Prefill[ KV grows to S across its ranks ] → (1−h) blocks transfer → Decode[ re-hosts block IDs ]
```
- **Transfer unit is the paged block** — the receiver re-hosts the block IDs in its own
  block table; it does not re-run prefill (`KV-Cache/Distributed-KV-Cache.md` §2).
- **The (1−h) discount is a placement fact, not an optimization**: blocks already
  resident on the decode side (prefix hit) are *not* in the transfer's block list. The
  router's job is to maximize h so the moved set shrinks (`03-kv-aware-routing.md`).
- **Steady-state demand is the real constraint**: the fabric must carry
  `λ · KV · (1−h)` per second. [E] this session: at **λ=1000 req/s, 4 GiB avg, h=0.8**
  the aggregate is **≈ 859 GB/s — 17× a single 400 GbE (50 GB/s) link**, i.e. many links
  or a big h. This is why h (routing quality) is a *capacity* variable, not a latency nicety.

## Replicated KV, implemented (locality copies)
- **Pin hot prefixes** (agent system prompts, tool schemas) on every replica at warm-up —
  turns locality from a routing constraint into a constant
  (`Inference/Production-Serving/08-cache-aware-routing.md`).
- Replication costs HBM per copy; pays by removing fabric round-trips for the fraction of
  traffic that hits it. The replication decision is an *index policy* (`05-global-kv-state.md`).

## Memory/placement table [E — computed this session from canonical 128 KiB/token]
How many concurrent long-context sessions a tier holds is *the* placement economics:
| Tier | capacity (example) | 8B-GQA @ 256k-context sessions (32 GiB/session [E]) |
|---|---|---|
| GPU HBM | ~80 GiB usable | **~2 sessions** GPU-only |
| CPU DRAM | ~512 GiB | **~16 sessions** (offload extends ~8×) |
| NVMe / remote | TB+ | hundreds (GDS/object-store tier; reload cost, `02` page) |

The jump from ~2 (HBM, no distribution) to 16+ (CPU) to hundreds (NVMe/remote) is the
entire economic case for tiering/distributing the cache — and the reason both platforms
ship it as a first-class component (`02-offload-and-tiering.md`).

## Failure / consistency surfaces (implementation-relevant)
- **Partial-transfer failure**: P dies mid-handoff → decode has a partial prefix →
  re-fetch policy (`Production-Operations/12-kv-cache-reliability.md`).
- **Placement-map staleness**: the index says a block is on node X but X evicted it —
  the routing/offload failure modes of `05-global-kv-state.md`.
- **Tenant bleed** across a shared distributed cache (`Production-Operations/12-…`).

## Related
`04-pd-orchestration.md` (the handoff as a control loop) · `05-global-kv-state.md` (the
placement index) · `06-nixl-transfer.md` (the movement) · `02-offload-and-tiering.md` ·
`03-kv-aware-routing.md` · `KV-Cache/Distributed-KV-Cache.md` ·
`KV-Cache/Paged-KV-Cache.md` · `KV-Cache/Architecture-Overview.md` ·
`GPU-Systems/Tensor-Parallelism.md` · `Inference/Prefill-Decode-Disaggregation.md`

## Key Takeaways
1. Distributed KV = paged blocks + a **placement tuple `(tier,node,rank)`** + a cluster
   index; the engine owns the local block table, the platform owns the placement map.
2. The three modes are three placement policies — sharded (once, no copies), moved
   (P/D handoff), replicated (locality copies); know which one a system is doing.
3. Steady-state demand is `λ·KV·(1−h)`; [E] at 1000 req/s / 4 GiB / h=0.8 it is ~859 GB/s,
   so **routing quality is fabric capacity** — the implementation link between routing and
   networking.
