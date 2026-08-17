# Prefill/Decode Disaggregation — Deep Dive
`DRAFT v2 (post-evaluation)` · 2026-08-17 · Claim tags: [F] fact (primary source cited) · [A] engineering assumption · [I] inference · [E] computed & Python-verified this session (model in /tmp/disagg/model2.py; formulas per roofline-formula-bank conventions). Units: GB = 10⁹ B, GiB = 1024³ B; GB/s = 10⁹ B/s.

---

## 1. The hypothesis, stated as a testable claim

**H0:** Separating prefill and decode onto different GPU pools improves (a) utilization, (b) latency predictability (P99 TTFT and ITL/TPOT), and (c) cluster economics (goodput per dollar) — *relative to monolithic colocated continuous-batching serving*.

H0 is **conditionally true**: it holds when the workload is SLO-bound on *both* TTFT and TPOT, load is sustained, and the inter-node fabric can carry sustained KV transfer demand. It can be *false* on short-prompt/high-reuse workloads, on ≤10 GbE fabrics, at low utilization, or when the objective is raw tokens/$ with loose SLOs. §9–§11 quantify the boundary. No unconditional winner is claimed.

---

## 2. Why prefill and decode have opposite hardware characteristics

First principles (all [E] unless noted):

| | Prefill | Decode |
|---|---|---|
| Work | One pass over S prompt tokens (parallel) | 1 new token per step, GEMV-heavy |
| FLOPs | 2·N·S + L·d·S(S+1) (causal attn) | 2·N per token (weights) |
| Arithmetic intensity (AI) | ≈ d/b (d=4096, BF16 → ~2048) → **compute-bound** on H100 (ridge ≈ 295) [F: formula bank] | 2/b ≈ 1.0 (BF16) at B=1 → **HBM-bandwidth-bound**; only recovers compute at large batch B |
| Optimal batch | Large S fills the GPU: a single 512-token prefill of a 13B model already makes an A100 near compute-bound [F: DistServe §3.1] | Must batch toward the knee B* to amortize the weight stream; B* ≈ 15 (8B, 8k ctx, BF16 KV) and ≈ 52 (70B) where KV read traffic = weight traffic [E] |
| Dominant SLO | TTFT | TPOT/ITL (per-token) |
| Memory | KV *written* (and read by attention) | KV *read every step* (grows O(S) per step) |
| Parallelism sweet spot | Intra-op (TP) for latency, NVLink-hungry [F: DistServe] | Larger batch, KV-capacity-hungry; inter-op/PP tolerable |

Key empirical facts:
- Compute has scaled far faster than HBM: H100 vs A100 = 3.43× compute, 1.64× HBM bandwidth, 1.75× power [F: Splitwise Table I]. Decode's bottleneck (memory) is the dimension that *didn't* scale → decode underuses newest GPUs; this is the economic seed of phase splitting [F: Splitwise].
- Splitwise's characterization (production traces, A100/H100): token generation "does not require the compute capability of the latest GPUs, and can be run with lower power and cost" [F: arXiv:2311.18677].
- Colocated, the two phases **interfere**: a prefill step is much longer than a decode step; batching them means decode steps wait (ITL/TPOT spikes) and new prompts wait for running decodes (TTFT inflation) [F: DistServe §2.1–2.3]. Chunked prefill *trades* TTFT for TPOT but "cannot eliminate the interference" [F: DistServe §2.2].

---

## 3. Monolithic vs disaggregated — the complete data path

### 3.1 Monolithic (colocated continuous batching)
```
Request → router → GPU pool:
  step = [prefill chunk of new req(s)] ++ [decode steps of running reqs]
  → sample → stream tokens; KV never leaves the GPU
```
- Single scheduler, one KV pool (HBM). Wins: zero KV movement, weights resident once, simple routing (least-loaded). Loses: interference (§2), coupled resource/parallelism planning, tail ITL spikes from chunked prefill; vLLM docs: "Disaggregated prefill DOES NOT improve throughput" — so for a colocated engine the disagg win is SLO decoupling + tail control, not raw throughput [F: vLLM docs/features/disagg_prefill].

### 3.2 Disaggregated P/D
```
Request → global router (KV-aware)
   → PREFILL pool: run prompt through model (compute K,V for all S positions;
     first token out) → KV cache now resides in prefill GPU HBM (or CPU/DRAM tier)
   → KV TRANSFER: block-wise copy, layer-by-layer or bulk, over the fabric
     (shared mem / NVLink / PCIe / RDMA), ideally async & pipelined with the
     next prefill job
   → DECODE pool: allocate KV blocks, verify, admit into continuous batch →
     stream tokens until EOS
```
Complete per-request data path (DistServe's 5-stage decomposition, which I use as the measurement template [F: DistServe §6.3]):
1. **Prefill queuing** — wait in prefill pool
2. **Prefill execution** — compute-bound
3. **Transmission** — KV bytes across fabric
4. **Decoding queuing** — wait for KV capacity on decode GPU
5. **Decoding execution** — memory-bound, batched

Properties:
- **Pull vs push**: DistServe uses *pull* (decode instance fetches KV when it has room; prefill HBM acts as a queuing buffer) to avoid decode-side memory overload under bursts [F: DistServe §4.3].
- **KV-aware routing**: router picks (i) prefill instance with shortest queue / best prefix-hit, (ii) decode instance where the KV should land (most free KV capacity / cache overlap) [F: DistServe §4.3; Mooncake cache-aware prefill scheduler; Dynamo router]. Dynamo's router is advertised for "KV-aware routing to avoid redundant prefill computation — 2x faster TTFT" (Qwen3-Coder 480B, Baseten) [F: Dynamo README, vendor-reported].
- **Cache locality** becomes a *placement* decision: with a shared KV tier (Mooncake's CPU/DRAM/SSD "context pool"; llm-d's tiered prefix cache), the router can schedule so that decode starts where the KV already is, or schedule the prefill where the prefix is cached — eliminating both redundant prefill *and* long transfers [F: Mooncake §3; llm-d README].
- **Failure domains grow**: a decode-instance fault mapped to many in-flight prefills "could potentially cripple the entire service" — fault propagation is an explicit open risk in DistServe [F: DistServe §4.3].

---

## 4. KV-cache transfer: the physics and the fabrics

**KV size** (the single most important number; [E] via `2·L·h_kv·d_h·S·b`):

| Model | KV/token | S=4k | S=16k | S=64k | S=128k |
|---|---|---|---|---|---|
| 8B (L=32, GQA 8×128) BF16 | 128 KiB | 0.50 GiB | 2.0 GiB | 8.0 GiB | 16 GiB |
| 8B FP8 | 64 KiB | 0.25 | 1.0 | 4.0 | 8.0 |
| 70B (L=80, GQA 8×128) BF16 | 320 KiB | 1.25 | 5.0 | 20 GiB | 40 GiB |
| 70B FP8 | 160 KiB | 0.62 | 2.5 | 10 | 20 |

Sanity vs literature: DistServe's "OPT-66B, 512-token request ≈ 1.13 GB" [F] — verified OPT-66B architecture (L=64, 72 MHA heads, d_h=128; HF config fetched 2026-08-17): K+V @512 tokens FP16 = 2·64·72·128·512·2 B = 1.208 GB = 1.125 GiB [E]. So the paper's "1.13 GB" is the **full K+V** figure under loose GB≈GiB rounding. Their "11.3 GB/s = 90 Gbps at 10 rps" is ~0.9× my exact recompute (1.208 GB × 10 rps = 12.1 GB/s = 97 Gbps [E]) — same order, consistent with the rounding.

**Fabric hierarchy** [F: vendor specs; DistServe/Splitwise cite the 25–50 GB/s per-GPU-pair IB class]:
- Same-host shared memory: ~100+ GB/s (cheapest, same-node P/D)
- NVLink: 600 GB/s peak A100, ~900 GB/s H100 x8 (DistServe calls transfer over intra-node NVLINK "negligible") [F]
- PCIe 5.0 x16: ~55 GB/s practical host-bounce
- **RDMA over Ethernet (RoCE / 10–400 GbE)**: kernel-bypass, zero-copy; RoCE needs lossless config (PFC/ECN) or it degrades; 100 GbE ≈ 11.9 GB/s effective [A: 95% of line rate]
- **InfiniBand NDR/HDR**: lossless + adaptive routing out of the box; 400 Gb NDR ≈ 48.4 GB/s effective [A]
- **GPUDirect RDMA**: NIC DMA directly in/out of GPU HBM, no host bounce — removes two copies and host CPU from the path; the default for production KV transfer (DistServe uses NCCL cross-node; Mooncake's Messenger is explicitly GPUDirect-RDMA; vLLM NixlConnector uses UCX/GDS backends; Dynamo ships NIXL) [F: DistServe §5; Mooncake §; vLLM docs; Dynamo README]

**Transfer time** = KV_bytes / BW + RTT (handshake + setup ≈ 0.3 ms [A]). Table ([E]; BF16; 10 GbE = 1.0 GB/s … 400 GbE = 48.4 GB/s effective):

| KV | 10 GbE | 25 GbE | 100 GbE | 200 GbE | 400 GbE | PCIe5 | NVLink |
|---|---|---|---|---|---|---|---|
| 0.5 GiB (8B, 4k) | 537 ms | 179 | 45 | 23 | 11 | 10 | ~2 |
| 2.0 GiB (8B, 16k) | 2.15 s | 0.72 | 181 | 90 | 45 | 39 | 7.5 |
| 8.0 GiB (8B, 64k) | 8.6 s | 2.9 | 722 | 361 | 178 | 157 | 29 |
| 16 GiB (8B, 128k) | 17.2 s | 5.7 | 1.44 s | 0.72 | 0.36 | 0.31 | 58 |
| 5.0 GiB (70B, 16k) | 5.4 s | 1.79 | 452 | 226 | 111 | 98 | 18 |
| 40 GiB (70B, 128k) | 43 s | 14.3 | 3.61 s | 1.8 s | 0.89 | 0.78 | 144 |

**Prefix reuse slashes it**: at 70B, S=32k, BF16 on 100 GbE: 0% hit → 902 ms; 30% → 632; 50% → 451; 70% → 271; 90% → 90 ms [E]. KV-aware routing + shared cache tier is therefore *load-shaping* for the fabric, not a nicety.

---

## 5. Architectures and systems

| System | What it does | Key evidence |
|---|---|---|
| **DistServe** (Zhong et al., PKU/StepFun/UCSD, OSDI'24, arXiv:2401.09670) [F] | Goodput-optimal P/D split; joint TTFT+TPOT SLO optimization; bandwidth-aware placement (high vs low node-affinity variants); FCFS + pull-based KV; prefill batch shaping to saturate GPU | 7.4× more requests or 12.6× tighter SLO vs vLLM/DeepSpeed-MII at >90% attainment; transmission <0.1% of total latency even for OPT-175B; >95% of transfers <30 ms on a **25 Gb/s cross-node** testbed (NVLink same-node placement) [F] |
| **Splitwise** (Patel et al., Microsoft, 2024, arXiv:2311.18677) [F] | First phase-splitting system; cluster-level scheduler (CLS) + machine-level (MLS); heterogeneous pools (H100 prompt / A100 token); KV transfer over IB, **overlapped with prompt computation** | 1.4× throughput at 20% lower cost, or 2.35× at same cost/power [F: abstract] |
| **Mooncake** (Moonshot AI, FAST'25 Best Paper, arXiv:2407.00079) [F] | Production Kimi platform; KVCache-centric: disaggregated prefill/decode clusters + cluster-wide CPU/DRAM/SSD KV pool ("context pool"); Conductor global scheduler; cache-aware prefill scheduling; prediction-based early rejection under overload; GPUDirect-RDMA "Messenger" | Up to 525% throughput (long-context sims); +75% requests in production under SLOs [F] |
| **NVIDIA Dynamo** (ai-dynamo, 2025–) [F: README] | Orchestration layer *above* SGLang/TRT-LLM/vLLM: disaggregated P/D pools, KV-aware router, multi-tier KV (KVBM: GPU→CPU→SSD→remote), NIXL KV transfer, LLM-aware autoscaling, multimodal Encode/Prefill/Decode (E/P/D), K8s gateway plugin | 2× TTFT via KV-aware routing (Baseten, Qwen3-Coder 480B); Dell+PowerScale NIXL "19× faster TTFT" (vendor) [F: README] |
| **llm-d** (Red Hat/Google/NVIDIA/Intel/AMD, K8s-native, 2025–) [F: README] | P/D pools as K8s workloads; KV-aware leader election; tiered prefix cache (CPU/disk); predicted-latency scheduling; wide-EP + P/D for giant MoE | "Up to 70% higher tokens/sec with P/D disaggregation vs standard vLLM — GPT-OSS on B200 (AWS)"; 10–30% throughput gain on MI300X (Oracle); 13.9× with hierarchical KV offload at 250 concurrent [F: README] |
| **vLLM disagg** [F: docs] | 2 instances + Connector abstraction (NixlConnector w/ UCX+GDS, LMCache, Mooncake, FlexKV, Offloading, Multi); scheduler+worker connectors; LookupBuffer (insert/drop_select); async send/recv; prompt-token-id reuse to skip re-tokenization; third-party connectors for production | Doc-stated benefit: independent TTFT/ITL tuning + tail-ITL control; **explicit: "Disaggregated prefill DOES NOT improve throughput"** [F] |
| **TensorRT-LLM / SGLang** | Production-hardened P/D (TRT-LLM cache transmission; SGLang PD + E/P/D disagg with Mooncake backend; 96×H100 DeepSeek deployment) [F: docs/blogs] | — |

Pattern across all of them: the *split* is easy; the differentiators are (1) the KV transfer engine (NIXL / Mooncake TransferEngine / NCCL), (2) KV-aware global scheduling, (3) multi-tier KV (HBM→DRAM→SSD→remote), (4) overload handling (rejection, early decode, preemption).

---

## 6. Does the network cancel the advantage? (quantitative answer)

Two regimes, both computed [E] (H100, MFU_prefill=0.45 [A], TP eff 0.9 [A], prefill FLOPs = 2·N·S + L·d·S(S+1)):

**Regime 1 — per-request TTFT penalty.** Ratio t_transfer / t_prefill:

| Fabric | 8B S=4k | 8B S=128k | 70B S=4k | 70B S=128k |
|---|---|---|---|---|
| 10 GbE | 1.59 | 0.79 | 1.84 | 1.16 |
| 25 GbE | 0.53 | 0.26 | 0.61 | 0.39 |
| 100 GbE | 0.13 | 0.07 | 0.15 | 0.10 |
| 400 GbE | 0.03 | 0.02 | 0.04 | 0.02 |

Bandwidth where transfer is "invisible" (≤10% / ≤20% of prefill time; [E], units Gb/s = 8×10⁹ B/s): at S=4k: 128 / 64 Gb/s; S=16k: 116 / 58; S=64k: 86 / 43; S=128k: 63 / 32 Gb/s (8B; 70B needs ~15–18% more at short S). Note the counterintuitive result: **longer prompts make the ratio *better*** (prefill grows ~S² with attention while KV grows ~S), but the *absolute* TTFT penalty stays large on slow fabrics (16k prompt on 10 GbE adds 2.15 s — worse than the 1.48 s prefill itself). No commodity Ethernet fabric reaches "≤10% of prefill" at S=4k; 100 GbE lands at 13–16% (4k) improving to 7–10% (128k), and 400 GbE makes it ≤4% everywhere.

Cross-check vs reality: DistServe measured transmission <0.1% of latency and >95% of requests <30 ms even on 25 Gb/s cross-node, because it *colocated P/D pairs on one node and moved KV over NVLink* [F]. My model: 0.5 GiB over 300 GB/s NVLink ≈ 2 ms + overhead — consistent [E].

**Regime 2 — sustained aggregate demand.** This is where a slow fabric *does* cancel the advantage: demand = λ·KV_per_request must fit the fabric or transfers queue.

| Workload | demand | 10 GbE | 25 GbE | 100 GbE | 200 GbE | 400 GbE |
|---|---|---|---|---|---|---|
| 8B chat 10 rps @4k | 5.4 GB/s | 537% ✗ | 179% ✗ | 45% ✓ | 23% | 11% |
| 8B RAG 10 rps @16k | 21.5 GB/s | ✗ | ✗ | 180% ✗ | 90% ~ | 44% ✓ |
| 70B RAG 1 rps @64k | 21.5 GB/s | ✗ | ✗ | 180% ✗ | 90% ~ | 44% ✓ |

So: on **10 GbE disaggregation is net-negative on TTFT** for these models (transfer ≥ prefill at S≤16k, and demand oversubscribes the link at any non-trivial RPS); on **100 GbE it is viable but RAG@10rps saturates it** — you need 200–400 GbE, or FP8 KV (halves demand), or a tiered cache (removes traffic via prefix hits), or same-node NVLink pairs. This is exactly the failure mode the user asked about, and it's real: the per-request ratio looks fine, the *aggregate* oversubscribes.

**Decode-side numbers** ([E], H100 pool, BF16 KV, 8k avg context, corrected step model: t_step = (W + B·S·kv_tok)/HBM):
- 8B (TP1): B=1 → ITL 5.1 ms; B=32 → 15.0 ms (2.1k tok/s agg); B=128 → 45.8 ms (2.8k tok/s); knee B*≈15
- 70B (TP4): B=1 → 10.7 ms; B=32 → 16.9 ms; B=128 → 36.1 ms; B*≈52

The decode pool's value proposition: run big batches *without any prefill stalls* → stable P99 ITL; the prefill pool runs at full MFU with no decode interleaving.

**TTFT head-to-head** ([E]; colocated = chunked prefill, 1024-token chunks interleaved behind running decode batch; disagg = exclusive prefill + transfer):

| Case | colocated (dec B=128) | disagg @100 GbE | disagg @10 GbE |
|---|---|---|---|
| 8B, S=1k | 128 ms | 94 ms ✓ | 217 ms ✗ |
| 8B, S=4k | 513 ms | 383 ms ✓ | 875 ms ✗ |
| 8B, S=16k | 2051 ms | 1664 ms ✓ | 3631 ms ✗ |
| 70B, S=4k | 863 ms | 842 ms ~ | 2071 ms ✗ |
| 70B, S=16k | 3452 ms | 3531 ms ~ | 8449 ms ✗ |

Break-even (TTFT-only view): **~100 GbE breaks even around S≈4k and wins as S grows**; **10 GbE never wins on TTFT** for these models (it loses by 2–4× at 4k–16k). The TPOT/goodput win (§2, DistServe's 2.1× on a 13B: colocated 1.6 rps/GPU vs 3.3 rps/GPU at 2:1 P:D [F]) is independent of fabric quality and is what keeps disaggregation ahead even when TTFT is comparable.

---

## 7. When disaggregation is WORSE than colocated (the evaluator's brief)

Ranked by how defensible each claim is:

1. **Slow fabric (≤10 GbE) + medium prompts**: transfer > prefill; TTFT 2–4× worse than chunked-prefill colocated; sustained demand oversubscribes the link → queuing. Quantified above [E]. Mitigation: co-locate P/D pairs on one node and move KV over NVLink — this is DistServe's low-node-affinity placement algorithm (Alg. 2), which exists precisely for clusters whose cross-node bandwidth is too slow (their testbed: 25 Gb/s cross-node [F]; naming is counter-intuitive: "low node affinity" = the cluster has low inter-node bandwidth, hence same-node co-location).
2. **Short prompts + high prefix reuse**: transfer cost is a *fixed* adder that is largest in relative terms at short S (8B S=1k @10 GbE: transfer = 134 ms vs 82 ms prefill, ratio 1.63 [E]), and colocated prefix caching reuses KV *locally for free* — a disaggregator without KV-aware routing pays to move context that a colocated pool would already have in cache. KV-aware routing (Dynamo's 2× TTFT claim [F: vendor]) is what recovers this.
3. **Low utilization / small fleets**: both pools must hold headroom; at low load the P pool or D pool idles while the other works — colocated flexes one pool across both phases. [I: standard queuing argument; DistServe's gains are stated at the system's max SLO-compliant rate, i.e., high utilization]
4. **Raw-throughput objective with loose SLOs**: vLLM's doc note — disagg does not improve throughput [F]; if SLOs are loose, colocated continuous batching is simpler and equally fast on tokens/$.
5. **Heterogeneous-hardware economics unavailable**: Splitwise's cost win assumes a cheap decode pool (A100-class) [F]; if all GPUs are the newest generation, that leg of the economics disappears, leaving only the interference/TTFT leg.
6. **Operational & failure-cost overhead**: two fleets, P:D ratio planning, routing complexity, cross-instance fault propagation ("a fault in a single decoding instance mapped to multiple prefill instances could potentially cripple the entire service" [F: DistServe §4.3]), and KV in transit as a new failure state (DistServe lists preemption/fault-tolerance as future work).
7. **Memory-footprint coupling**: each P replica and D replica holds its own (TP-sharded) weight copy; a minimal disaggregated replica = P replica + D replica. For big models where P+D don't co-fit on one node (DistServe's 175B example: 2×350 GB > 8×80 GB [F]), the GPU count per replica rises.
8. **KV transfer as a new tail-latency source**: RDMA congestion (RoCE PFC storms, ECN blackholes) and NIC saturation add a variance source that colocated serving simply doesn't have; Mooncake's early-rejection and DistServe's pull-model exist precisely to bound it [F].

---

## 8. Experiments to run (and telemetry)

**Design principles**: pin model+precision+GPU+engine versions, clocks, warm-up, CUDA-graph batch coverage, arrival process, prefix-overlap level, sampling params; report P50/P90/P99 and goodput (requests/s meeting *both* SLOs at ≥90% attainment), never averages [A: methodology per DistServe §6].

- **E1 — Model calibration**: microbench prefill-only and decode-only at S∈{1k,4k,16k,64k}, B∈{1..256}; measure MFU, HBM utilization; validate §6 numbers within ~2% (DistServe's simulator-vs-system error was <2% [F]).
- **E2 — Colocated vs disagg A/B**: same GPU budget split both ways; Poisson arrivals at increasing λ; sweep SLO strings (TTFT×TPOT); measure goodput curve, P99 TTFT, P99 ITL, queue depths per pool, GPU SM/HBM utilization per pool. Hypothesis: disagg goodput ≥ 1.5× at S≥4k with both SLOs active (DistServe-style) [I: H1].
- **E3 — Fabric sweep**: disagg at 10/25/100/200/400 GbE (token-bucket caps on a single physical NIC); record transfer CDF, TTFT, NIC utilization, RDMA retransmits, PFC pause counters (RoCE); locate the break-even from §6 table; expect 10 GbE to invert TTFT in favor of colocated [I: H2].
- **E4 — Prefix-reuse sweep** (0–90% overlap, agent-style multi-turn): colocated+APC vs disagg+KV-aware routing; measure prefill FLOPs avoided and transfer bytes avoided; expect disagg+KV-aware ≥ colocated at ≥50% overlap, disagg-naive < colocated at ≥70% overlap [I: H3].
- **E5 — Overload/rejection**: push λ past capacity; compare queueing (colocated) vs prediction-based early rejection (Mooncake-style); measure rejected-vs-SLO-violated mix and tail TTFT [I: H4].
- **E6 — Tail stability under bursts**: gamma-burst arrivals; ITL P99/P999 for chunked-prefill colocated vs disagg; expect disagg to flatten P99 at the cost of a small P50 ITL increase when the decode pool runs small [I: H5].

**Telemetry (recommended, all per-pool + aggregate)**:
- Latency: TTFT P50/P90/P99; ITL/TPOT P50/P90/P99 (per request *and* per batch); end-to-end latency; per-stage breakdown (DistServe's 5 stages)
- KV transfer: bytes, time, achieved GB/s, RTT; RDMA retransmission rate; PFC pause frame count; ECN marks; NIC queue length; GPUDirect vs host-bounce share
- Fabric: per-NIC bandwidth utilization (% of line), NVLink link utilization, fabric queue occupancy
- GPUs: SM activity %, DRAM/HBM bandwidth %, power (DCGM); per-pool "busy fraction"
- Queues: waiting queue depth per pool (vLLM `num_requests_waiting`), KV pool utilization: HBM cache util (`gpu_cache_utilization`), DRAM/SSD tier fill %, block allocation latency
- Cache: prefix hit rate, KV reuse rate, transfer-avoided-by-cache bytes
- Economics: goodput (rps meeting both SLOs @ attainment target), requests/$, P:D load ratio, autoscaler actions, rejection rate
- Ops: transfer failures/timeouts, in-flight KV orphaned by crashes, failover events

---

## 9. Break-even analysis (summary)

1. **Per-request (TTFT)**: transfer ≤10% of prefill needs ≈128 Gb/s at S=4k, ≈116 at 16k, ≈86 at 64k, ≈63 at 128k (8B; 70B ≈15% more at short S [E]). 100 GbE sits at 13–16% for S≤16k and 7–12% for S≥64k; 400 GbE is ≤4% everywhere; **25 GbE cross-node adds 26–53% of prefill time (S=4k→128k) — marginal, acceptable only with TTFT slack; same-node NVLink P/D pairs are the production answer**; **10 GbE is not viable cross-node for TTFT**.
2. **Sustained**: fabric must carry λ·KV(1−hit_rate). RAG workloads (16–64k context) at 10 rps need ≥200 GbE unless FP8 KV + prefix hits cut demand by ≥2× [E].
3. **Goodput (the real break-even)**: even where TTFT is a wash, disaggregation removes interference; DistServe measured 2.1× goodput on a 13B with *only* 25 Gb/s cross-node [F]. Expect disagg to be the cheaper choice whenever *both* TTFT and TPOT SLOs are active and load is high; expect it to lose on tokens/$ for short-prompt, loose-SLO, low-reuse workloads on commodity fabric [I: H6 — to be confirmed by E2/E3].
4. **Economics leg**: heterogeneous pools add up to 1.4×/−20% cost (Splitwise [F]) — only when an older, cheaper decode GPU generation is available.
5. **Negative break-even exists**: on 10 GbE, TTFT break-even is never crossed for 8B/70B at S≤128k [E] — colocated chunked prefill wins on latency and disagg adds only TPOT stability.

## 10. Deployment decision tree

```
Q1: Are both TTFT and TPOT SLO-active and binding (interactive chat, agentic, RAG with latency SLAs)?
 ├─ No (loose SLOs, throughput-maximization) → colocated continuous batching + chunked prefill +
 │    prefix caching. (vLLM: disagg doesn't raise throughput [F].) Consider Splitwise-style
 │    heterogeneous pools only if a cheap decode-gen fleet exists [F: economics leg].
 └─ Yes:
 Q2: Workload shape?
 ├─ Short prompts (S ≲ 2k) + high prefix reuse (agents, multi-turn)
 │    → colocated + APC / KV-aware routing within one pool (transfer adder is worst in relative
 │      terms; local cache reuse is free). Revisit if SLOs get tighter (DistServe-style gains grow
 │      with SLO strictness [I: H7]).
 ├─ Medium/long prompts (S ≥ 4k), moderate reuse
 │    → Q3: fabric?
 └─ Long context (S ≥ 32k) / RAG-heavy / overload-prone
      → disaggregate + multi-tier KV (CPU/SSD pool) + early rejection + KV-aware routing
        [F: Mooncake pattern; llm-d tiered prefix cache]
Q3: Inter-node fabric between P and D pools?
 ├─ ≥100 GbE RDMA (IB, or RoCE tuned lossless, GPUDirect/NIXL) → disaggregate; place freely;
 │    transfer adds 7–16% of prefill time (≤4% on 400 GbE) [E].
 ├─ 25–50 GbE → disaggregate with P/D pairs co-located on the same node; KV over NVLink
 │    [F: DistServe's low-node-affinity algorithm (Alg. 2) — their 7.4× results were measured
 │    on a 25 Gb/s cross-node testbed using exactly this pattern].
 └─ ≤10 GbE → colocate (or same-node NVLink P/D pairs). Cross-node disagg inverts TTFT [E].
Q4 (post-deploy): telemetry gate — if P:D ratio drift > 20% from plan, or fabric utilization
   > 60% sustained, or P99 TTFT > 1.5× plan → re-plan (DistServe replanning cycle [F]) or
   re-tier KV.
```

## 11. Unverified hypotheses (to be decided by experiments, not asserted)

- **H1**: disagg goodput ≥ 1.5× colocated at S≥4k when both SLOs active (E2).
- **H2**: 10 GbE cross-node disagg inverts TTFT vs colocated for 8B/70B at S≤16k (E3).
- **H3**: naive disagg (no KV-aware routing) is slower than colocated+APC at ≥70% prefix overlap (E4).
- **H4**: early rejection beats unbounded queueing on P99 TTFT under >100% capacity load (E5).
- **H5**: disagg flattens ITL P99 under bursty arrivals (E6).
- **H6**: on tokens/$ for short-prompt loose-SLO workloads, colocated is cheaper (E2/E3).
- **H7**: DistServe-style gains grow monotonically with SLO strictness (E2 SLO sweep).

## 12. Sources (fetched & retained in /tmp/disagg, 2026-08-17)

- DistServe — arXiv:2401.09670, OSDI'24 (PDF md5 5c936c…, 18 pp)
- Mooncake — arXiv:2407.00079, FAST'25 Best Paper (PDF md5 0721cf…); README (md5 371cb9…) incl. FAST'25 links, vLLM/SGLang/TRT-LLM integrations
- Splitwise — arXiv:2311.18677 (PDF md5 efdc63…); NOTE: my wiki page cited 2311.18698 — wrong, corrected here
- vLLM docs/features/disagg_prefill.md (md5 38ad39…) — connector list, "does not improve throughput" note
- Dynamo README (md5 102e66…), llm-d README (md5 6ea91f…) — feature tables, vendor benchmarks
- Hardware constants: roofline-formula-bank.md (H100 495 TFLOPS BF16-dense, 3.35 TB/s HBM3)

---

## 13. Evaluator adjudication (independent reviewer: deepseek-v4-flash-0731 @ 10.1.1.51:8888)

Two-pass adversarial review of this draft. Findings, each re-verified by me before I
acted on it. **Net: 5 accepted, 2 refuted** (refutations documented, kept visible).

| # | Evaluator flag | My re-verification | Ruling |
|---|---|---|---|
| 1 | "Invisible bandwidth" figures off by 8 (should be 128 Gb/s, not 16 Gb/s, at S=4k) | Recomputed: I had printed Gb/s where the number was actually GB/s. 8B S=4k: ≤10% needs 16 GB/s = 128 Gb/s. **Confirmed my error.** | **ACCEPTED** — all Gb/s figures re-expressed; §6/§9 corrected. |
| 2 | "100 GbE makes transfer effectively free for all prompt lengths" overstated | Recomputed ratios: 100 GbE = 13.4% (8B 4k) → 6.7% (128k). Not "free" at short S. | **ACCEPTED** — reworded to "13–16% at S≤16k, 7–12% at S≥64k". |
| 3 | OPT-66B "1.13 GB is K-only, L=96" — wrong | Verified OPT-66B from HF config: **L=64, 72 MHA heads, d_h=128**. K+V @512 FP16 = 1.208 GB = 1.125 GiB. So "1.13 GB" is full K+V under loose GB≈GiB rounding; my "L=96, K-only" reading was wrong. | **ACCEPTED** — corrected with the verified architecture. |
| 4 | "low-node-affinity = same-node NVLink" mislabel | DistServe §4.2: "Low Node-Affinity Cluster … colocate prefill and decoding on the same node, utilizing the NVLINK" (for clusters with limited cross-node BW). **My label was actually correct**; the evaluator's "high-affinity = same-node" reading is the reverse of the paper. | **REFUTED** — kept, but added a clarifying note that the naming is counter-intuitive ("low node affinity" = low inter-node bandwidth ⇒ same-node co-location). |
| 5 | DistServe 2.1× / 1.6 vs 3.3 rps / 90 Gbps — "verify" | Cross-checked against DistServe §1 & §3.3: 1.6 rps/GPU colocated vs 10 rps total ÷ 3 GPUs = 3.3 rps/GPU (2:1 P:D) = 2.1×. "90 Gbps to render overhead invisible" is quoted verbatim from the paper. | **ACCEPTED** (verified correct as cited). |
| 6 | "70B Regime-1 rows are wrong: 1.84/1.16 should be 0.46/0.29" (evaluator claimed 70B used N≈16.5B, 4× too fast) | Root cause: **the evaluator computed 70B prefill at TP=1** (200.475 TFLOPS effective). My draft labels the model "70B (TP=4)" and divides by 4 (801.9 TFLOPS effective). At TP=4: t(4k)=0.73 s → ratio 1.84; t(128k)=36.9 s → ratio 1.16 — **exactly my table**. The evaluator's "physically impossible, attention-only > 37 s" is true only at TP=1. | **REFUTED** — my numbers are correct for TP=4; the evaluator's "4× error" is its own TP=1 assumption. (I confirmed the 8B row, which the evaluator also flagged, is TP=1 and matches exactly.) |

Pass-1 additionally mis-read the 8B S=1k TTFT row (thought transfer used 0.5 GiB); I had
used the correct 0.125 GiB for S=1k — that was a transient evaluator misread, self-resolved
in its own trace. Pass-2 confirmed all of §4 KV tables, §6 Regime-2 demand table, and the
decode-side ITL numbers to within rounding.

**Residual known gaps:** H1–H7 remain unverified experimental hypotheses (labelled as such);
the MFU=0.45 / TP-eff=0.9 / 95%-line-rate / 0.3 ms RTT are stated [A] assumptions, not
measurements; vendor benchmark numbers (Dynamo 2×, llm-d 70%, Dell 19×, Mooncake 525%/75%)
are tagged vendor-reported and not independently reproduced.
