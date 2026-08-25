# Distributed Inference — Overview (Cluster Layer: Platforms, P/D, KV Transfer)
`LAST_UPDATED: 2026-08-24 · Status: core page (section landing)` · This section covers
the **cluster layer** of LLM serving: coordinating many engine instances across nodes —
routing, prefill/decode disaggregation, KV-cache state at cluster scale, and the two
platforms that implement it (**NVIDIA Dynamo**, **llm-d**).

Scope map inside this section:
- `README.md` — the *parallelism dimensions* (TP/PP/DP/CP/EP and their collectives)
- **this page** — what "distributed" adds on top: the cluster layer, the networking
  stack, KV-transfer physics, P/D break-even, cluster metrics
- `NVIDIA-Dynamo.md` · `llm-d.md` — the two platform deep dives
- `Dynamo-vs-llm-d.md` — the head-to-head (same-layer rivalry)
- Single-instance engine internals: `Serving-Engines/Engine-Landscape.md` and
  `GPU-Systems/`

## 30-Second Explanation
An inference engine (vLLM/SGLang/TRT-LLM, `Serving-Engines/Engine-Landscape.md`) makes
*one serving instance* fast. Distributed inference makes *a fleet* fast. That requires
five jobs no engine does alone:
1. **Route** — pick which replica/pool handles this request (load-aware, KV-aware).
2. **Place** — put prefill and decode on different GPU pools so each runs at its own
   roofline optimum (P/D disaggregation).
3. **Move** — transfer the KV cache from prefill GPU to decode GPU without re-prefilling
   (KV transfer over NVLink/RDMA).
4. **Scale** — size the pools to the SLO, not to a static replica count.
5. **Fail** — migrate in-flight requests when a worker dies without losing the user's
   stream.

The two platforms in this section are the same-layer rivals that do these five jobs:
**NVIDIA Dynamo** (open-source, Rust core, NVIDIA-datacenter gravity, v1.4.x line) and
**llm-d** (CNCF Sandbox, Kubernetes-native, vendor-neutral accelerator matrix, v0.8).
Both sit *above* engines — they orchestrate vLLM/SGLang/TRT-LLM instances; neither
executes model math itself [F: both READMEs, 2026-08-24].

## The Scale Ladder (where "distributed" begins)
```
L0  single GPU, one engine instance            → no cluster problem
L1  multi-GPU node (TP/EP/PP within node)      → NVLink fabric, engine-internal
                                                 (`Distributed-Inference/README.md`)
L2  multi-node, one logical instance           → NCCL over RDMA; PP/EP cross-node
                                                 (`GPU-Systems/Multi-Node.md`)
L3  many replicas, same model                  → DP + router (load/cache-aware)
                                                 (`GPU-Systems/Load-Balancing.md`)
L4  P/D-disaggregated pools                    → this section: KV transfer +
                                                 KV-aware routing + pool scaling
                                                 (NVIDIA-Dynamo.md, llm-d.md)
```
L0–L2 are *model-parallelism* problems (one model, many GPUs); L3–L4 are
*serving-systems* problems (many requests, many instances, one SLO contract). The
vocabulary differs: at L0–L2 you talk about AllReduce/AllToAll and bubble time; at
L3–L4 you talk about TTFT/ITL SLOs, KV hit rate, routing quality, and goodput/$.

## The Networking Stack (PART 27)
```
GPU ── NVLink (intra-node, P2P HBM↔HBM)
   └── NVSwitch (intra-node all-to-all; NVL72 = 72-GPU domain)
        └── NIC (ConnectX / BF-3 class)
             ├── InfiniBand (lossless, low-latency, HPC fabric)
             └── RoCE v2 (RDMA over converged Ethernet; PFC/ECN tuning territory)
                  └── remote GPU (RDMA read/write, GPUDirect)
```
- **NCCL** is the collective library (AllReduce/AllGather/AllToAll/P2P) both intra-node
  and inter-node; TP's 2×AllReduce-per-layer rides on it [F: `GPU-Systems/NCCL.md`].
- **RDMA** moves KV: the remote DMA semantics mean the decode GPU's NIC writes
  straight into HBM — no host-copy on the critical path.
- **GPUDirect RDMA** is the specific feature that makes the above true on NVIDIA
  hardware (NIC ↔ HBM direct); GPUDirect Storage extends the same idea to disk for
  weight/KV tiering [I: standard NVIDIA stack; verify per driver].
- **Fabric class sets the P/D ceiling.** Bandwidth table (same one used by
  `Inference/Prefill-Decode-Disaggregation.md`):

| Path | Bandwidth | Notes |
|---|---|---|
| shared memory (same host) | ~100+ GB/s | cheapest; same-node P/D |
| NVLink | 600 GB/s peak A100, ~900 H100 | intra-node; the production answer on slow fabrics [F: DistServe] |
| PCIe 5.0 x16 | ~55 GB/s | host bounce |
| RDMA 10/25/100/200/400 GbE | 1.0 / 3.0 / 11.9 / 23.8 / 48.4 GB/s (95% eff [A]) | cross-node standard; GPUDirect avoids host copies [F: NVIDIA] |

**Why P/D creates a new data-movement problem**: colocated serving never moves KV
between GPUs — it grows in place. Disaggregated serving moves it *once, per request,
over the fabric*, and that transfer is on the TTFT critical path. The transfer volume
is the whole sequence's KV (see next section), so fabric bandwidth becomes an SLO
variable, not an ops detail.

## KV Transfer Deep Dive (PART 28)
```
Prefill GPU                      Decode GPU
 K,V for S tokens ──RDMA/NVLink──▶ paged KV blocks
```
**Data volume** — the same formula as everywhere (`KV-Cache/README.md`):
```
KV bytes = 2 × layers × kv_heads × head_dim × S × bytes_per_element
```
Worked [E] (hand-verify; same model as `Inference/Prefill-Decode-Disaggregation.md`):
example model L=32, h_kv=8, d_h=128, BF16 → **128 KiB/token**
[2·32·8·128·2 B = 131,072 B]. At S = 32,768: KV = 32,768 × 131,072 B = **4 GiB**
= 4.295×10⁹ B. Transfer time = bytes / fabric BW:

| Fabric | BW | 4 GiB transfer | TTFT penalty character |
|---|---|---|---|
| NVLink H100 (≈900 GB/s peak) | 900 GB/s | **≈ 4.8 ms** [E] | invisible |
| RDMA 400 GbE | 48.4 GB/s | **≈ 89 ms** [E] | noticeable on tight TTFT SLOs |
| RDMA 100 GbE | 11.9 GB/s | **≈ 361 ms** [E] | dominates short-prompt TTFT |
| RDMA 25 GbE | 3.0 GB/s | **≈ 1.43 s** [E] | worse than re-prefilling short prompts |
| RDMA 10 GbE | 1.0 GB/s | **≈ 4.3 s** [E] | disagg non-viable for most SLOs |

Prefix hit rate *h* multiplies transfer by (1−h) — only uncached tokens cross the
wire: at h=0.9 the 100 GbE case above drops to **≈ 36 ms** [E: 361×0.1]. This is the
arithmetic core of why **KV-aware routing and prefix-tiering are not features but
prerequisites** of disaggregated serving: without cache awareness, every request pays
the full transfer. The full break-even model (per-request ratio + sustained
aggregate-oversubscription regime, with the failure-mode taxonomy) is
`Inference/Prefill-Decode-Disaggregation.md` §Break-even — Python-verified 2026-08-17.

**Why KV-transfer latency can be critical**: it sits *serially* between prefill and
first decode token (TTFT = prefill + transfer + queue), it scales linearly with S
(prefill scales ~S² in compute), and it is *exactly the traffic a router can avoid*
by placing decode next to the cached KV — the three reasons Dynamo/llm-d both build
KV-aware routing as a first-class component [F: both READMEs].

## P/D Disaggregation (PART 26)
```
Collocated (traditional)                Disaggregated
┌────────────────────────┐              ┌──────────┐    KV transfer    ┌──────────┐
│ GPU pool               │              │ prefill  │ ────────────────▶ │ decode   │
│  prefill + decode mix  │              │ pool     │  (RDMA/NVLink)    │ pool     │
└────────────────────────┘              └──────────┘                   └──────────┘
 one SLO compromise                      two SLOs, two roofline regimes
```
First-principles (roofline, `Inference/Roofline.md`):
- **Prefill** ≈ compute roof: prompt tokens processed in parallel; AI ≈ d/b, high for
  S≥512. Prefill GPUs want compute density.
- **Decode** ≈ bandwidth roof at low batch: each token streams all weights (+KV) from
  HBM; batch B* amortizes weight traffic until KV/activation traffic dominates.
- Colocation forces one pool to run at both regimes — prefill steps stall decodes
  (ITL spikes), decodes delay new prompts (TTFT inflation). Chunked prefill trades the
  interference but "cannot eliminate it" [F: DistServe §2.2, via the P/D page].

**P:D ratio is a tuning dimension, not a constant.** Worked [E] expectation (H100-SXM
specs: BF16 dense ≈ 990 TFLOPS [F: spec], HBM ≈ 3.35 TB/s [F: spec]; example 8B BF16
model, 8.4×10⁹ params = 16 GB weights):
- prefill 4,096-token prompt: 2·8.4×10⁹·4096 ≈ 6.88×10¹³ FLOP → ÷ 990 TFLOPS ≈ **70 ms**
- decode 1 token, B=1: 16×10⁹ B ÷ 3.35×10¹² B/s ≈ **4.8 ms** (+KV reads; KV grows with
  context — at 32k context the example model adds ~4.3 GB of KV reads/token-class
  traffic, so B=1 is far from the real operating point)
- one 4k→512 request ≈ 0.070 s prefill : 2.45 s decode ≈ **work ratio ~1:35**
So for *chat-shaped* workloads (short prompt, long output) one prefill GPU can feed
several decode GPUs (P:D < 1:1 in prefill:decode direction, i.e. more D GPUs); for
*RAG-shaped* workloads (32k+ prompts, short outputs) the ratio inverts toward
P:D ≥ 1:1. The ratios to sweep (1:1, 1:2, 1:4, 2:4, 2:8) are *experiments*, not
settings — the optimum is where both pool utilizations hit ~100% at your SLO
[I: standard practice; consistent with DistServe's bandwidth-aware placement].

**When disagg helps / when it doesn't** (from the P/D page's verified model + evidence):
- Helps: both TTFT and ITL SLOs bind; high sustained load; long contexts; fast fabric
  (≥100 GbE cross-node, or NVLink same-node); KV-aware routing present.
- Doesn't: ≤10 GbE cross-node (transfer inverts TTFT vs colocated chunked prefill);
  short-prompt/high-reuse traffic without cache awareness; loose-SLO tokens/$
  objectives (disagg costs extra hardware — the win is SLO attainment, not throughput
  [F: vLLM docs state disagg does NOT improve throughput]).
- Vendor evidence (context-specific, [F: vendor/partner claims, not wiki-lab results]):
  Dynamo "2× TTFT, KV-aware routing, Qwen3-Coder 480B" (Baseten) and "7× throughput
  per GPU, DeepSeek R1, GB200 NVL72" (InferenceX) [F: ai-dynamo README]; llm-d "up to
  70% higher tok/s, GPT-OSS on B200" (AWS) and "13.9× throughput with hierarchical KV
  offload @250 concurrent, 4×H100" [F: llm-d README]. Treat each as the cited
  workload's result, not a class statement.

## MoE Serving at Cluster Scale (PART 29)
```
token → router (gate) → expert selection → AllToAll dispatch → expert GEMM → AllToAll combine
```
- The MoE bottleneck is **AllToAll** (dispatch+combine every MoE layer) — the same
  collective as CP, and the reason wide-EP demands the fastest fabric available
  (`Distributed-Inference/README.md` §5).
- **Expert placement** determines which GPUs hold which experts; balanced placement
  keeps every GPU busy, hot experts become network hot-spots.
- **Load balancing**: token-level routing is data-dependent — imbalance is intrinsic;
  systems add expert replication or aux-loss-free balancing (training-side) and, at
  the serving side, *request-level* placement (route requests whose token
  distributions overlap onto the same expert pool) [I: standard 2025 practice].
- **Fabric importance**: intra-node NVLink (or NVL72 NVSwitch domain) makes wide-EP
  cheap; cross-node wide-EP lives or dies on RDMA bandwidth — the 16×16 B200
  llm-d wide-EP result (≈50k cluster tok/s, ~3.1k per GPU [F: llm-d README blog])
  and Dynamo's NVL72-class results are both fabric-first achievements.
- Engine-level EP: vLLM/SGLang/TRT-LLM all ship expert-parallel paths
  (`Serving-Engines/Engine-Mega-Comparison.md` MoE row); the platforms layer adds
  *where* the expert pools live and *which request* goes where.

## KV-Aware / Prefix-Aware Routing (the L3–L4 brain)
Two routing signals dominate (full treatment:
`Inference/Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md` and
`Inference/Production-Serving/08-cache-aware-routing.md`,
`09-pd-disaggregated-routing.md`):
1. **KV cache overlap** — how much of this request's prefix is already cached on which
   replica. Sending it there saves prefill compute and (in P/D) the KV transfer.
   Dynamo's router: "routes based on worker load and KV cache overlap" [F: README];
   llm-d's: "prefix-cache and load-aware balancing, including experimental
   predicted-latency-based scheduling" [F: README].
2. **Remaining work** — estimated decode length + queue depth; balance *work*, not
   *requests* (a 512-out request is 512× the work of a 10-out request at the same
   TTFT).
The measurable outputs: **KV hit rate, prefix reuse fraction, per-pool utilization,
routing quality (share of requests sent to the cache-optimal worker)**. These are the
cluster-level metrics that explain platform-level TTFT/ITL wins.

## Cluster Benchmark Metrics (PART 25)
Single-engine benchmarks measure TTFT/ITL/throughput/memory/GPU-util
(`GPU-Systems/Perf-Experiment-Template.md`). Platform-level benchmarks add:
| Metric | Why |
|---|---|
| cluster throughput (total tok/s, req/s) | the objective |
| per-GPU throughput (tok/s/GPU) | the efficiency-normalized objective |
| TTFT / ITL P50/P95/P99 | the SLO contract |
| **KV cache hit rate** | the cache-aware routing dividend |
| **prefix reuse fraction** | workload-shape indicator; explains hit rate |
| routing quality | share of requests placed on cache-optimal worker [I: definition] |
| load distribution (variance across workers) | imbalance = wasted capacity |
| P/D pool utilization | both pools ≈100% ⇒ ratio right |
| prefill/decode utilization separately | the two regimes' separate ceilings |
| **KV transfer latency** (P50/P95) | the new disagg variable (PART 28) |
| inter-node bandwidth utilization | oversubscription early warning |
| scaling efficiency | tok/s/GPU at N nodes vs 1 node (sublinearity = comm overhead) |
| goodput at SLO | req/s where P99 TTFT < T AND P99 ITL < T — the real objective |

**The throughput-latency knee** (from single-engine, applies per-pool): the
concurrency at which throughput stops growing and tail latency starts compounding.
At cluster scale there are *two knees* (prefill pool and decode pool) plus a *fabric
knee* (KV-transfer demand > bandwidth — the aggregate-oversubscription failure mode
in the P/D page). Finding all three is the content of a platform benchmark [I].

## The Two Platforms (pointers)
- **`NVIDIA-Dynamo.md`** — components (frontend, router, planner, KVBM, workers),
  Rust core, two routing topologies (Dynamo-native vs Gateway API + EPP), P/D,
  KVBM tiers, ModelExpress, K8s operator, key results, deployment paths.
- **`llm-d.md`** — K8s-native architecture (Gateway API, router, tiered prefix cache,
  P/D, wide-EP, autoscaling, batch gateway), CNCF governance, accelerator matrix,
  well-lit paths, performance highlights.
- **`Dynamo-vs-llm-d.md`** — the full comparison table + philosophical difference
  (vendor OSS Rust core vs CNCF K8s-native) + when each wins.

## Key Takeaways
1. Distributed inference = five cluster jobs (route, place, move, scale, fail) on top
   of engine instances; the two platforms in this section (Dynamo, llm-d) are the
   same-layer implementations of those five jobs [F: both READMEs, 2026-08-24].
2. **KV transfer is the new physics**: bytes = 2·L·h_kv·d_h·S·b; at 100 GbE a 32k
   context of the example model costs ~361 ms [E] — serial, S-linear, and avoidable
   by cache-aware routing (×(1−h) discount).
3. P/D disaggregation wins when both SLOs bind + fast fabric + cache awareness; it
   loses on ≤10 GbE cross-node and loose-SLO throughput objectives; P:D ratio is a
   per-workload experiment (work-ratio intuition: ~1:35 prefill:decode for
   4k→512 chat on H100 [E]).
4. MoE at scale is an AllToAll problem: wide-EP is fabric-first (NVLink/NVL72
   intra-domain; RDMA inter-node), and platforms add request-level expert-pool
   placement on top of engine EP.
5. Benchmark the platform with cluster metrics (hit rate, routing quality, pool
   utilization, transfer latency, goodput-at-SLO) — single-engine tok/s says nothing
   about the cluster layer.

## Related
`README.md` (parallelism dimensions) · `NVIDIA-Dynamo.md` · `llm-d.md` ·
`Dynamo-vs-llm-d.md` · `Inference/Prefill-Decode-Disaggregation.md` (break-even model +
research lineage: DistServe/Splitwise/Mooncake) ·
`Inference/Deep-Dives/pd-disaggregation-deep-dive-2026-08-17.md` ·
`Inference/Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md` ·
`Inference/Production-Serving/08-cache-aware-routing.md` ·
`Inference/Production-Serving/09-pd-disaggregated-routing.md` ·
`Networking/README.md` (RDMA/GPUDirect) · `GPU-Systems/Multi-Node.md` ·
`GPU-Systems/NCCL.md` · `GPU-Systems/Load-Balancing.md` · `GPU-Systems/Distributed-Architectures.md`
· `Serving-Engines/Engine-Landscape.md` · `KV-Cache/README.md`

## References
- ai-dynamo/dynamo README (main, v1.4.x; fetched 2026-08-24) + docs.nvidia.com/dynamo
  [F].
- llm-d/llm-d README v0.8 (fetched 2026-08-24) + llm-d.ai docs [F].
- Bandwidth figures: NVIDIA spec sheets + DistServe testbed (inherited from
  `Inference/Prefill-Decode-Disaggregation.md`, Python-verified 2026-08-17) [F/E].
- H100-SXM specs (990 TFLOPS BF16 dense, 3.35 TB/s HBM): NVIDIA datasheet [F].
- No arXiv citations introduced on this page (Dynamo/llm-d are repo/docs-cited per
  the citation bank; P/D research IDs live in the P/D page's reference list).
