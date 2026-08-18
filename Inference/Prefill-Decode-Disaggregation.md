# Prefill/Decode Disaggregation
`LAST_UPDATED: 2026-08-17` · Status: core page (deepened 2026-08-17 with primary-source + Python-verified break-even model; full report: `queries/pd-disaggregation-deep-dive-2026-08-17.md`)

## 30-Second Explanation
Run prefill and decode on **different GPU pools**: prefill GPUs process prompts
in parallel (compute-bound); decode GPUs stream tokens (HBM-bandwidth-bound);
the KV cache is **transferred** prefill→decode once over the fabric instead of
being re-read from the same HBM forever. Each pool gets its own roofline
operating point, its own SLO (TTFT vs TPOT), and independent scaling.

## The pipeline
```
Request → KV-aware router → Prefill pool (compute K,V, first token)
      → KV transfer (RDMA/NVLink; GPUDirect) → Decode pool (paged KV, continuous batch) → stream
```
DistServe's 5-stage lifecycle (measurement template [F: DistServe §6.3]):
prefill-queuing → prefill-execution → **transmission** → decoding-queuing → decoding-execution.

## Why it matters (first principles)
- Prefill AI ≈ d/b (compute-bound on H100 for S≥512); decode B=1 AI ≈ 1.0 (HBM-bound),
  recovers only at batch knee B* (≈15 for 8B, ≈52 for 70B at 8k ctx, BF16 KV [E]).
- Colocation ⇒ **interference**: prefill steps stall decode steps (ITL/TPOT spikes) and
  running decodes delay new prompts (TTFT inflation). Chunked prefill trades TTFT for
  TPOT but "cannot eliminate the interference" [F: DistServe §2.2].
- **KV-aware routing/scheduling** becomes first-class: place decode where the KV landed
  (or send KV to the idlest decode; schedule prefill where the prefix is already cached)
  [F: Mooncake, Dynamo, llm-d].

## Break-even: when does the network cancel the win? (2026-08-17 model, [E])
Two independent regimes — both must hold:
1. **Per-request (TTFT)**: t_transfer/t_prefill. 10 GbE: 1.6–1.8× (worse than the prefill
   itself) at S≤16k; 100 GbE: 13–16% at S=4k, 7–10% at S=128k; 400 GbE: ≤4%.
   "Invisible" (≤10%) needs ~128 Gb/s at S=4k, ~63 Gb/s at S=128k — no commodity
   Ethernet reaches it at short S; longer prompts make the *ratio* better (prefill ~S²,
   KV ~S) but the absolute penalty stays large on slow fabrics.
2. **Sustained (aggregate)**: demand = λ·KV(1−hit) must fit the fabric. RAG-class
   (16–64k ctx) at ~10 rps needs 200–400 GbE unless FP8 KV + prefix hits cut demand ≥2×.
   100 GbE saturates at ~10 rps of 16k-context workloads → **aggregate oversubscription
   is the real failure mode, not the per-request ratio**.

Bottom line [I: model + DistServe/Splitwise evidence]: disaggregation wins when both
TTFT+TPOT SLOs bind and load is high; it loses on ≤10 GbE cross-node (TTFT inverts vs
colocated chunked prefill), on short-prompt/high-reuse workloads without KV-aware routing,
and on tokens/$ with loose SLOs. vLLM docs: disagg "does NOT improve throughput" [F].

## Research & systems lineage
- **DistServe** (Zhong et al. 2024, **OSDI'24**, arXiv:2401.09670) [F] — goodput-optimal
  P/D split; joint TTFT/TPOT SLO optimization; bandwidth-aware placement (high vs
  **low node-affinity** — the low-affinity algorithm co-locates P/D on one node to move KV
  over NVLink when cross-node bandwidth is slow; counter-intuitive naming); pull-based KV.
  7.4× more requests or 12.6× tighter SLO; transmission <0.1% of latency, >95% of
  transfers <30 ms on a 25 Gb/s cross-node testbed; 2.1× goodput on a 13B (1.6 vs 3.3
  rps/GPU at 2P:1D). Explicit open risk: fault propagation between pools.
- **Splitwise** (Patel et al., Microsoft, 2024, arXiv:**2311.18677**) [F] — first
  phase-splitting system; H100 prompt pool / A100 token pool (heterogeneous economics:
  compute scaled 3.43× vs HBM 1.64× A100→H100 [F: Table I]); KV over IB overlapped with
  prompt compute. 1.4× throughput at 20% lower cost, or 2.35× at same cost/power.
- **Mooncake** (Moonshot AI, **FAST'25 Best Paper**, arXiv:2407.00079) [F] — production
  Kimi platform; KVCache-centric: P/D clusters + cluster-wide CPU/DRAM/SSD "context pool";
  Conductor global scheduler; cache-aware prefill scheduling; prediction-based early
  rejection under overload; GPUDirect-RDMA Messenger. Up to 525% throughput (long-ctx
  sims); +75% requests in production. TransferEngine now ships inside vLLM (KV connector),
  SGLang (E/P/D + P2P weights), TRT-LLM.
- **vLLM disaggregated prefill/decode** [F: vLLM docs/features/disagg_prefill] — 2 instances
  + Connector abstraction (NixlConnector w/ UCX+GDS, LMCache, Mooncake, FlexKV, Offloading,
  Multi); scheduler+worker connectors; async send/recv. Stated benefit: independent
  TTFT/ITL tuning + tail-ITL control; explicitly **no throughput gain**.
- **NVIDIA Dynamo** (ai-dynamo, 2025–) [F: README] — orchestration *above* SGLang/TRT-LLM/
  vLLM: P/D pools, KV-aware router, KVBM multi-tier KV (GPU→CPU→SSD→remote), NIXL transfer,
  LLM-aware autoscaling, E/P/D multimodal split. Vendor: 2× TTFT via KV-aware routing
  (Baseten, Qwen3-Coder 480B).
- **llm-d** (Red Hat/Google/NVIDIA/Intel/AMD, K8s-native, 2025–) [F: README] — P/D pools as
  K8s workloads; KV-aware leader election; tiered prefix cache; predicted-latency
  scheduling; wide-EP+P/D for giant MoE. Vendor: up to 70% higher tok/s (GPT-OSS on B200,
  AWS); 13.9× with hierarchical KV offload @250 concurrent.
- **TRT-LLM / SGLang** [F: docs/blogs] — production-hardened P/D (TRT-LLM cache
  transmission incl. Mooncake backend; SGLang PD + E/P/D; 96×H100 DeepSeek deployment).

## KV transfer — the physics
| Path | Bandwidth | Notes |
|---|---|---|
| shared memory (same host) | ~100+ GB/s | cheapest; same-node P/D |
| NVLink | 600 GB/s peak A100, ~900 H100 | intra-node; the production answer on slow fabrics [F: DistServe] |
| PCIe 5.0 x16 | ~55 GB/s | host bounce |
| RDMA (RoCE / IB) | 1.0 / 3.0 / 11.9 / 23.8 / 48.4 GB/s @ 10/25/100/200/400 GbE (95% eff [A]) | cross-node standard; GPUDirect avoids host copies [F: NVIDIA] |

KV size = `2·L·h_kv·d_h·S·b`. GQA models: 8B = 128 KiB/token → 16 GiB @128k;
70B (L=80) = 320 KiB/token → 40 GiB @128k (BF16) [E]. Prefix hit rate h multiplies the
transfer by (1−h): 70B @32k on 100 GbE: 0%→902 ms, 50%→451 ms, 90%→90 ms [E].

## Bottlenecks & open problems
1. **Sustained KV demand > fabric** (aggregate, not per-request) — the #1 disagg failure
   mode on ≤100 GbE with RAG-class workloads [E: model; §break-even above].
2. **KV-aware routing** — send request to the decode pool with most free KV / cache
   overlap; Mooncake's context pool + Dynamo router are the templates [F].
3. **Failure domains** — P or D dies mid-transfer → preemption & KV re-fetch; cross-pool
   fault propagation is an explicit open risk [F: DistServe §4.3].
4. **Economics** — two pools cost more hardware; win shows in SLO attainment (P99
   TTFT/TPOT) and goodput/$, not raw throughput [F: vLLM docs; I: model].
5. **KV transfer as tail-latency source** — RoCE PFC storms / ECN / NIC saturation add
   variance colocated serving doesn't have; pull-models + early rejection bound it [F].

## Related
`Inference/Continuous-Batching.md` · `Networking/README.md` (RDMA, GPUDirect) ·
`KV-Cache/README.md` · `Distributed-Inference/README.md` ·
`Inference/Inference-Optimization.md` ·
`Inference/Deep-Dives/pd-disaggregation-deep-dive-2026-08-17.md` (full report + evaluator adjudication)

## Key Takeaways
Disaggregation = decoupling two roofline regimes + two SLOs. The split is easy; the hard
parts are **KV transfer** (fabric ≥ sustained λ·KV(1−hit)) and **KV-aware scheduling**.
10 GbE cross-node is a non-starter for TTFT; ≥100 GbE + KV-aware routing is the viable
disagg regime; same-node NVLink P/D pairs are the answer on slow fabrics.
