# Hierarchical KV Cache & Offloading (Tiered KV)
`LAST_UPDATED: 2026-08-26` · Status: deep-dive page

## 30-Second Explanation
When the KV for long/in-flight contexts doesn't fit in HBM, you have two levers: *evict*
(drop it — lose quality, `Eviction.md`) or *offload* (move it to a slower tier — CPU DRAM,
NVMe, remote) and **prefetch it back on demand**. Hierarchical caching keeps far more
"cold-ish" prefixes resident than HBM alone, at the price of a slower-then-refast reload.
The tiers, in order: GPU HBM → host CPU DRAM → NVMe/PCIe SSD → remote (another node).
Each tier is captured by (capacity, bandwidth, latency); offloading is the strategic
decision of *where* each prefix/block lives and *when* it moves.

## The tier budget [E, from the verified constants]
Moving 16 GiB (8B @128k) of KV between tiers (see `Distributed-KV-Cache.md` for the method):
| Tier | ~bandwidth | 16 GiB move |
|---|---|---|
| HBM (resident) | ~3.35 TB/s (H100) | — (that's just reads) |
| NVLink (∼900 GB/s) | 900 GB/s | ~19 ms |
| CPU DRAM (DDR5 dual) | ~90 GB/s | ~191 ms |
| PCIe5 x16 | ~55 GB/s | ~312 ms |
| NVMe Gen4 SSD | ~7 GB/s | ~2.45 s |
| 100 GbE (remote) | ~48 GB/s | ~355 ms |

**Read the table as latency classes, not exact numbers [I]:** HBM↔DRAM is sub-second;
DRAM↔SSD is seconds; remote adds fabric RTT. A "hit" that lives on SSD is 10–100× slower
to bring back than an HBM hit — so tier lookup is *hit-tier-aware*, not hit-bit-aware
(`Inference/Production-Serving/08-cache-aware-routing.md`).

## Why offload instead of evict
- **Eviction is irreversible** (quality loss; `Eviction.md`). Offload preserves the KV,
  so a later turn in the same long agent session can restore it verbatim.
- **Agentic / multi-turn reality:** each turn of a long session re-touches the same
  trunk + recent history; that working set is *temporarily* huge but *persistently*
  small. Offloading lets the whole session stay resident across tiers.
- **Cost:** offload spends HBM and fabric bandwidth; eviction spends quality. The break
  point is "will this prefix be needed again within a horizon cheaper than re-prefill?" —
  that's a reuse-prediction question (see `Eviction.md` learned/2026 work).

## The offload+prefetch pattern
1. **Write-behind / aging:** as HBM pressure rises, cold blocks migrate toward CPU/SSD
   (LRU-with-sinks, or radix-node priority — see `Prompt-and-Prefix-Caching.md`).
2. **Lookahead prefetch:** predict the prefix the *next* request will touch and start
   bringing it up before it's needed — the **OasisKV-style lookahead** [preprint,
   UNVERIFIED-quality] and FlexGen-class offline generation [F: arXiv:2303.06864].
3. **Block granularity** (→ `Paged-KV-Cache.md`): you move whole blocks; partial
   residency (blocks present in some tiers, absent in others) is handled by the same
   block-level sparsity the attention kernel already supports.

## Production systems to know
- **Mooncake context pool** [F: arXiv:2407.00079, FAST'25] — the canonical hierarchical
  cache: P/D clusters backed by a cluster-wide CPU/DRAM/SSD pool; prefill schedules to
  wherever a prefix is resident (see `Distributed-KV-Cache.md`).
- **Dynamo KVBM** [F: README] — multi-tier KV (GPU→CPU→SSD→remote) as a managed block
  manager with hit-rate instrumentation (`Distributed-Inference/NVIDIA-Dynamo.md`).
- **llm-d hierarchical KV offload** [F: README] — vendor-reported **13.9× with
  hierarchical KV offload @250 concurrent** (labeled vendor claim).
- **SGLang hierarchical KV** [F: docs] and **vLLM Offloading connector** [F: vLLM disagg
  docs] — engine-level hooks for any backend.
- **FlexGen** [F: arXiv:2303.06864] — the classic bandwidth-latency trade for KV/weight
  offload, still the reference for the throughput-vs-offload analysis.

## When it helps vs. hurts [I]
Helps: long-context agent sessions, high concurrency with a heavy shared-prefix working
set, RAG caches, serving on memory-constrained accelerators.
Hurts: latency-critical streaming where a spin-up-from-SSD misses deadline; short-lived
requests whose prefixes never recur (offload overhead with zero reuse); fabrics/NVMe too
slow relative to re-prefill (recompute is sometimes cheaper than the round-trip).

## Failure modes
- **Offload cliff:** SSD "hit" reload ~seconds → TPOT/TTFT spike; must be masked by
  lookahead prefetch or the routing must price hit *tier*.
- **Thrashing at the cool boundary:** prefixes flip between HBM and DRAM; watch tier
  migration rate, not just hit rate.
- **Consistency across tiers:** a block updated on GPU while a stale copy sits on DRAM —
  need an invalidation/protocol (same family as `Distributed-KV-Cache.md` consistency).
- **Tenant bleed / security:** spilled KV on shared SSDs must respect the same isolation
  as HBM (`Production-Operations/12-kv-cache-reliability.md`).

## Related
`Architecture-Overview.md` · `Paged-KV-Cache.md` (block = spill unit) ·
`Distributed-KV-Cache.md` (tiering = distribution across storage classes) ·
`Eviction.md` (the quality-costing alternative) ·
`Inference/Production-Serving/08-cache-aware-routing.md` (hit-tier-aware routing) ·
`GPU-Systems/Memory-Hierarchy.md` (capacity/latency/BW per level) ·
`Distributed-Inference/NVIDIA-Dynamo.md` · `Inference/Prefill-Decode-Disaggregation.md`.

## Key Takeaways
1. Offload trades bandwidth/latency for capacity and *reversibility* — eviction trades
   quality; pick by reuse-horizon prediction.
2. Surface the tier in routing: price hit *tier*, not hit *bit* (SSD ≠ HBM).
3. Mask slow reloads with lookahead prefetch; watch tier-migration thrash.
