# Distributed KV Cache (Sharded & Disaggregated)
`LAST_UPDATED: 2026-08-26` · Status: deep-dive page · Pair with the disaggregation chapter:
`Inference/Prefill-Decode-Disaggregation.md` and
`Inference/Deep-Dives/pd-disaggregation-deep-dive-2026-08-17.md` (do not duplicate).

## 30-Second Explanation
Once serving spans machines, the KV cache stops being a per-GPU local buffer and becomes
a **distributed object**: its blocks live on different ranks/nodes (TP-sharding), and at
a prefill/decode phase boundary the whole thing must *move* from one GPU pool to another
over a fabric. This page covers the three ways KV goes distributed — **sharded (parallel),
disaggregated (moved), replicated (copied)** — plus the transfer physics that dominates
all of them. The transfer *economics* and break-even are in the disaggregation chapter;
here we own the object-model and the mechanism.

## 1. Sharded KV (parallel, no movement needed)
Under **Tensor Parallel (TP)** the KV heads are sharded across the TP group: each of T
ranks holds `h_kv/T` heads, i.e. `1/T` of the KV (→ `GPU-Systems/Tensor-Parallelism.md`).
- **This is not "distributed cache" in the sharing sense** — it is the model's own
  layout; every request's full KV is assembled across the group, no redundant copies.
- With FP8 KV and GQA, sharded KV is small enough that TP is often the *cheapest* way to
  give a single request a long context.
- **KV as TP-final-gather:** when a request finishes decode it already has its full KV
  across the TP ranks; *any* engine handoff must gather or re-shard it
  (`GPU-Communication/08-nixl-kv-cache-transfer.md`).

## 2. Disaggregated KV (moved at the phase boundary)
Prefill and decode run on separate pools; the KV must transfer P→D once per request
(`Inference/Prefill-Decode-Disaggregation.md`):
```
request → Prefill GPU[KV grows to S] → KV transfer → Decode GPU[reads it for the whole decode]
```
- **The transfer unit is the paged block** (→ `Paged-KV-Cache.md`); the receiver re-hosts
  the block IDs in its own block table.
- **Physics table [E] — moving 4 GiB (8B @32k, BF16 KV):**
  | Fabric | time |
  |---|---|
  | NVLink (~900 GB/s) | ~4.8 ms |
  | PCIe5 x16 (~55 GB/s) | ~78 ms |
  | 100 GbE (~48.4 GB/s eff) | ~88.7 ms |
  | 25 GbE (~3 GB/s eff) | ~1.45 s |
  | 10 GbE (~1.2 GB/s eff) | ~3.6 s |
  (16 GiB = 128k: NVLink ~19 ms · PCIe5 ~312 ms · 100 GbE ~355 ms · NVMe Gen4 ~2.45 s — [E]).
- **The aggregate constraint is the real failure mode:** the fabric must carry
  `λ · KV · (1 − hit)` in steady state, not just one request (`Inference/Prefill-Decode-Disaggregation.md`)
  and `GPU-Communication/08-nixl-kv-cache-transfer.md`).
- **Mechanisms:** vLLM/SGLang/TRT-LLM `Connector` abstraction (NixlConnector UCX+GDS,
  LMCache, Mooncake, FlexKV, Offloading, Multi [F: vLLM docs]); NIXL as the transport
  (`GPU-Communication/07-nixl-deep-dive.md`); GPUDirect RDMA avoids host copies
  (`AI-Factory-Networking/15-gpudirect-rdma-nccl-infiniband.md`).

## 3. Replicated / shared cache (copied for locality)
To make a hot prefix reachable from multiple compute nodes (avoid routing everything to
one hot spot), blocks are **copied** (replicated), not migrated:
- **Pin hot prefixes** (agent system prompts, tool schemas) on every replica at warm-up —
  turns locality from a routing constraint into a constant
  (`Inference/Production-Serving/08-cache-aware-routing.md`).
- **Radix tree as a distributed index:** Dynamo's "global radix tree registry" and llm-d's
  KV indexer track *which node holds which prefix* so a router can address it
  (`Distributed-Inference/NVIDIA-Dynamo.md`, `Distributed-Inference/llm-d.md`).
- Replication trades HBM for hit-locality: each extra copy of a hot prefix costs memory
  but removes fabric round-trips for a *fraction* of requests.

## Distributed / cluster KV stores (the systems layer)
Beyond engine-internal transfer, KV is increasingly a **cluster-wide service**:
- **Mooncake** (Moonshot, FAST'25 Best Paper): KVCache-centric architecture — P/D clusters
  + a cluster-wide CPU/DRAM/SSD **context pool** + a Conductor global scheduler +
  GPUDirect-RDMA transfer. Cache-aware prefill scheduling; +75% requests / up to 525% in
  long-ctx sims (vendor-reported) [F: arXiv:2407.00079]. → the canonical blueprint for
  "KV is a distributed resource".
- **Dynamo KVBM** (multi-tier GPU→CPU→SSD→remote) and **llm-d tiered prefix cache /
  KV indexer** — platform-level distributed cache managers [F: READMEs, see
  `Distributed-Inference/`].
- These blur the line between "offload" (`Hierarchical-Offloading.md`) and "distributed",
  which is correct: **tiering IS distribution across storage classes.**

## Consistency & failure
- **Synchronous vs async snapshots:** disaggregated handoff needs the KV *present* before
  decode starts (pull model is simplest); replicated copies can be pro-active
  (`Production-Operations/11-distributed-inference-failures.md`).
- **Partial-transfer failure:** P dies mid-transfer → decode has a partial prefix →
  preemption + re-fetch policy (`Inference/Prefill-Decode-Disaggregation.md` open problems;
  `Production-Operations/12-kv-cache-reliability.md`).
- **Cache poisoning / tenant bleed** across a shared distributed cache
  (`Production-Operations/12-kv-cache-reliability.md`).

## Related
`Architecture-Overview.md` · `Paged-KV-Cache.md` (block = transfer unit) ·
`Prompt-and-Prefix-Caching.md` (what gets shared/replicated) ·
`Hierarchical-Offloading.md` (tiering = distribution across storage classes) ·
`Inference/Prefill-Decode-Disaggregation.md` (the economics) ·
`GPU-Communication/08-nixl-kv-cache-transfer.md`(transfer physics) ·
`Distributed-Inference/Overview.md` · `GPU-Systems/Tensor-Parallelism.md` (sharding).

## Key Takeaways
1. Three modes: sharded (no movement), disaggregated (moved), replicated (copied) — know
   which one your system does.
2. The transfer unit is the paged block; the fabric must carry steady-state
   `λ·KV·(1−hit)`, not one request.
3. Tiering and distribution are the same problem seen from different storage classes.

## Note — part of the "PART 1" disaggregated-inference pillar
The full disaggregated-inference treatment (break-even, routing, deployment decision
tree) is deliberately kept in `Inference/Prefill-Decode-Disaggregation.md` and
`Inference/Deep-Dives/pd-disaggregation-deep-dive-2026-08-17.md`; this page is the
cache-object view of the same pillar.
