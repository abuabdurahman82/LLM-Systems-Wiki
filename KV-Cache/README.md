# KV-Cache & Caching Architecture
`LAST_UPDATED: 2026-08-26` · Status: core section + deep-dive knowledge area (PART 1: Disaggregated Inference + LLM Cache)

## 30-Second Explanation
The KV cache stores, for every processed position, the Key and Value vectors of every
layer. It turns decode from O(S²) recompute into O(1) append + O(S) read — and becomes the
dominant HBM consumer at long context / high concurrency. Everything in serving that is
"fast" — prefill avoidance, prefix reuse, disaggregated prefill/decode, cache-aware routing —
is really an operation on *this one memory object*. This section is the knowledge area that
owns that object end to end: how it is stored (**paged**), shared (**prompt/prefix caching**),
moved (**distributed & disaggregated**), tiered (**hierarchical offload**), trimmed
(**eviction**), quantized (**KV compression**), and routed on (**KV-aware routing**).

## The Memory Equation (the one to remember)
```
KV bytes = 2 · L · B · h_kv · d_h · S · b
```
- L = layers · B = batch · h_kv = KV heads (GQA/MQA reduce this) · d_h = head dim ·
  S = context · b = bytes per KV element (2 BF16 / 1 FP8-INT8).
- [E] L=32, h_kv=8, d_h=128, b=2: **128 KiB / token** → S=4096→0.5 GiB · S=8192→1.0 GiB ·
  S=32768→4.0 GiB · S=131072→16 GiB.
- [E] 70B-class (L=80, h_kv=8): **320 KiB / token** → 32k→10 GiB · 128k→40 GiB.

## Why It Exists
Without it, each decode step would recompute K,V for all prior tokens: O(S²) total.
The cache makes step t cost O(S) reads only. Trade: HBM capacity and bandwidth. See
`Inference/The-Life-of-a-Token.md` (the full forward path the cache feeds).

## The Cache Life-Cycle (the knowledge-area map)
Every optimization is an operation on the cache. The pages in this section each own one:

| Life-cycle step | What it is | Where it lives |
|---|---|---|
| **Allocate / store** | fix KV capacity, shape, tensors | `Paged-KV-Cache.md` (paging, block tables) |
| **Share (prefix/prompt)** | reuse K,V for repeated prefixes | `Prompt-and-Prefix-Caching.md` |
| **Move (disaggregate)** | transfer KV prefill→decode | `Distributed-KV-Cache.md` + `Inference/Prefill-Decode-Disaggregation.md` |
| **Tier (offload)** | spill KV to CPU/SSD/remote | `Hierarchical-Offloading.md` |
| **Trim (evict)** | drop low-value tokens | `Eviction.md` |
| **Compress (quantize)** | shrink b from 2→1 bytes | this README §KV Quantization |
| **Route on (KV-aware)** | send work where its prefix lives | `Inference/Production-Serving/08-cache-aware-routing.md` · `Inference/Production-Serving/09-pd-disaggregated-routing.md` |

## Deep-Dive Pages (this section)
- `Architecture-Overview.md` — the unified mental model: the cache as a distributed,
  tiered, shared memory object; the two-pillar framing (caching stack ↔ disaggregated
  inference); decision map.
- `Paged-KV-Cache.md` — PagedAttention mechanics; block pools & tables; fragmentation;
  shared blocks; block-size trade-offs.
- `Prompt-and-Prefix-Caching.md` — the reuse stack: hash-based APC vs radix-tree
  RadixAttention vs LCP matching; hit granularity; prompt vs prefix vs KV;
  cache-as-a-service (LMCache, vLLM connectors).
- `Distributed-KV-Cache.md` — KV as a first-class distributed object: sharded (parallel)
  KV, disaggregated P→D transfer, replication, distributed KV stores.
- `Hierarchical-Offloading.md` — tiered KV (GPU→CPU DRAM→NVMe→remote); offload + prefetch;
  bandwidth/latency budget per tier; Mooncake context pool, Dynamo KVBM, SGLang hierarchical KV.
- `Eviction.md` — attention-based & learned pruning (SWA, streaming, H2O, SnapKV, PyramidKV…).

## Tensor Shapes & Tensor Parallelism
Per layer per request: `K [h_kv, S, d_h]`, `V [h_kv, S, d_h]`. Under **TP**, KV heads are
sharded across the TP group (each rank holds `h_kv/TP` heads) — the standard layout.
Served **paged**: a pool of fixed-size blocks (vLLM default 16 tokens; SGLang 64 [F: docs])
+ per-request block tables; block pool + radix/hashing index for prefix sharing
(`Attention/README.md` for the taxonomy, `GPU-Systems/Tensor-Parallelism.md` for the shard).

## Paged KV Management
Virtual-memory analogy [F: Kwon et al. 2023, SOSP, arXiv:2309.06180]. Near-zero
fragmentation; dynamic block reallocation; shared blocks for shared prefixes; block
tables consumed by attention kernels (FlashInfer/TRT-LLM-GEN/FlashMLA all support paged
KV [F: vLLM docs]). Deep dive: `Paged-KV-Cache.md`.

## Prefix Caching / Reuse
- **Hash-based APC** (vLLM): prefix hash → block list; physically shares paged blocks via
  refcounts [F: vLLM docs].
- **RadixAttention** (SGLang): radix tree over prefixes; sharing defined structurally by
  the program; 5×-class speedups on shared-prefix workloads (vendor-reported [F: SGLang blog]).
- **LCP matching**: radix-tree longest-common-prefix is the metric routers use to
  *route* for a cached prefix (deep dive: `Prompt-and-Prefix-Caching.md`; routing use:
  `Inference/Production-Serving/08-cache-aware-routing.md`).
- Effect depends on hit rate — benchmark must pin overlap (`Labs/Lab-13`, executed
  2026-08-17: **8.7× TTFT cold→warm on an 8k identical prefix** [E]).

## KV Quantization
b=1 (FP8/INT8) halves KV bytes → 2× decode bandwidth headroom and 2× capacity for
concurrency. Trained/quantized variants exist (FP8 KV in Hopper/Blackwell stacks [F:
vLLM `--kv-cache-dtype`]); quality at FP8 is near-lossless in most evals [I: common
finding, workload-dependent]. Deep dive on the broader memory-optimization space:
`GPU-Systems/Memory-Optimizations.md`.

## KV Offloading (hierarchical)
Moving stale KV to CPU/SSD and prefetching on demand (Mooncake context pool [F: FAST'25],
Dynamo's KVBM multi-tier [F: README], SGLang hierarchical KV [F: docs], FlexGen-class
[F: arXiv:2303.06864]). Useful when KV ≫ HBM; cost is PCIe/NVLink bandwidth + latency
spikes. Deep dive: `Hierarchical-Offloading.md`.

## Distributed / Disaggregated KV
Prefill/decode split ⇒ KV must **move** from prefill GPUs to decode GPUs: shared memory
(same host) → NVLink → RDMA (InfiniBand/RoCE) → NVL72 fabrics. Network becomes the
bottleneck; see `Distributed-KV-Cache.md`, `Inference/Prefill-Decode-Disaggregation.md`
(the P/D model), `GPU-Communication/08-nixl-kv-cache-transfer.md` (the transfer physics),
`GPU-Communication/13-distributed-inference-communication.md`.

## KV Compression / Pruning
Per-token importance scores → keep K% of tokens: `Eviction.md` (SWA, StreamingLLM sinks,
H2O, SnapKV, PyramidKV, learned 2026-era: DistillCache/RippleKV/CommitKV/SPECTRA, all
preprints — re-verify before citing).

## Related
`Inference/The-Life-of-a-Token.md` · `Inference/Roofline.md` ·
`Inference/Inference-Optimization.md` · `Inference/Continuous-Batching.md` ·
`Inference/Prefill-Decode-Disaggregation.md` · `GPU-Systems/Prefill-Decode-Disaggregation.md` ·
`GPU-Systems/Memory-Hierarchy.md` (per-level capacity/latency/BW) ·
`Model-Architectures/Attention-Head-Designs.md` (GQA/MQA shrink h_kv, **MLA shrinks ~85×** —
see `Context-Engineering/Context-Budget.md`) · `Quantization/README.md` · `Labs/Lab-2` ·
`Distributed-Inference/Overview.md` · `GPU-Communication/08-nixl-kv-cache-transfer.md`.

## Key Takeaways
1. `2·L·B·h_kv·d_h·S·b` is the serving budget equation.
2. Paging made it usable; prefix caching made it shared; quantization made it cheap;
   disaggregation made it *movable*; hierarchical tiers made it *spillable*.
3. At ≥32k context or high concurrency, KV — not weights — is often the HBM constraint.
