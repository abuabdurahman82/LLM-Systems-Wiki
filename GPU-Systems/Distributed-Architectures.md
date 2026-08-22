# Distributed LLM Inference Architectures — 11 Reference Topologies
`LAST_UPDATED: 2026-08-21 · Status: core page` · The "which topology fits which
workload" reference. The per-strategy mechanics live in `Tensor-Parallelism.md`,
`Pipeline-Parallelism.md`, `MoE-Expert-Parallelism.md`, `NCCL.md`; this page is the
decision layer on top. All [E] arithmetic is hand-derived from the STYLE-bank constants.

## 30-Second Explanation
An inference **deployment** is a choice of (a) how to split the model, (b) how to split
the requests, and (c) how the two fabrics (NVLink intra-node, RDMA inter-node) are used.
There are ~11 distinct topologies, from "one GPU" to "P/D-disaggregated multi-node MoE".
The single rule that picks among them: **put the latency-critical collective on the fast
fabric (NVLink), the bandwidth-tolerant collective on the slow fabric (RDMA), and the
request-split (DP) on the router.** Every topology below is annotated with its bottleneck
and when it wins.

```
single-GPU ─► TP-1node ─► TP-multinode ─► PP ─► DP-replicas ─► EP-MoE ─► TP+PP ─► TP+DP ─► TP+EP ─► TP+PP+DP+EP ─► P/D-disagg
  (1)          (2)          (3)          (4)      (5)           (6)        (7)      (8)     (9)       (10)          (11)
```

## The 11 architectures

> Each row: **what it is / when it wins / bottleneck / failure mode.** Full mechanics in
> the linked page.

### 1. Single GPU
- **What:** one model, one GPU; continuous batching inside the engine.
- **Wins:** model fits + modest concurrency. Cheapest possible.
- **Bottleneck:** HBM bandwidth (decode); capacity if KV grows.
- **Failure:** OOM on KV at high concurrency or long context → move to 2.
- → `Bandwidth-vs-Compute.md`, `../Inference/Continuous-Batching.md`.

### 2. Tensor-parallel, single node (TP ≤ 8, NVLink)
- **What:** split each layer's GEMMs across the node's GPUs; 2 AllReduce/layer.
- **Wins:** model barely/doesn't fit; need lower ITL; NVLink available. **The default.**
- **Bottleneck:** AllReduce time vs compute (fabric-bound if TP is high or S is large).
- **Failure:** TP too wide for the model size → AllReduce dominates and ITL rises.
- → `Tensor-Parallelism.md`, `Scale-Up-vs-Scale-Out.md`.

### 3. Tensor-parallel, multi-node (TP across nodes)
- **What:** TP group spans > 1 node; AllReduce crosses RDMA.
- **Wins:** only on **NVL72-class** NVLink domains (72 GPUs) where the "node boundary"
  is not a fabric boundary.
- **Bottleneck:** cross-node AllReduce at ~50 GB/s/link → ~18× slower than NVLink [E: 900/50].
- **Failure:** the classic mistake — TP over a slow fabric → ITL explodes. **Avoid** unless
  NVL72. → `Multi-Node.md`, `Topology.md`.

### 4. Pipeline parallelism (PP, cross-node)
- **What:** split layers into stages; P2P activations between stages; micro-batch pipeline.
- **Wins:** very large models; capacity split across nodes where NVLink isn't shared.
- **Bottleneck:** **bubble** `(p-1)/(m+p-1)`; stage latency adds to TTFT.
- **Failure:** imbalance (uneven FLOPs/stage) → bubble grows. → `Pipeline-Parallelism.md`.

### 5. Data-parallel replicas (+ router)
- **What:** N independent copies; a router balances **remaining work** across them.
- **Wins:** model fits; you need throughput/concurrency; each replica is a self-contained
  topology (usually TP within its node).
- **Bottleneck:** the router (hot-spotting if it balances connections, not work).
- **Failure:** prefix-cache fragmentation (shared prompt cold on most replicas).
  → `Load-Balancing.md`.

### 6. Expert-parallel MoE (EP)
- **What:** shard MoE experts across GPUs; AllToAll dispatch + combine per MoE layer.
- **Wins:** MoE models (DeepSeek, Mixtral, Qwen-MoE); far fewer activated params/token.
- **Bottleneck:** AllToAll under fabric pressure; hot experts.
- **Failure:** imbalance → one rank is the step-time ceiling. → `MoE-Expert-Parallelism.md`.

### 7. Hybrid TP + PP (the standard large-dense stack)
- **What:** TP within node (NVLink) for the latency-critical GEMMs; PP across nodes for
  capacity. The 2024+ default for a dense model that needs > 1 node.
- **Wins:** 70B–400B dense models on 2–8 nodes.
- **Bottleneck:** the **worse** of TP-AllReduce (intra) + PP-bubble (inter).
- **Failure:** TP group forced across a node boundary; PP stage mis-scaled.
  → `Multi-GPU.md`, `Pipeline-Parallelism.md`.

### 8. TP + DP
- **What:** each DP replica is a TP group; router spreads requests over replicas.
- **Wins:** model fits a TP-group (≤ a node); need both lower ITL (TP) and throughput (DP).
- **Bottleneck:** router; per-replica KV.
- **Failure:** too many TP-groups → each wastes fabric; too few → hot replicas.
  → `Load-Balancing.md`.

### 9. TP + EP (MoE on NVLink nodes)
- **What:** dense layers TP within node; MoE experts EP (AllToAll) — often within the same
  NVLink domain so the AllToAll is fast.
- **Wins:** MoE on an 8-GPU or NVL72 node; AllToAll stays on NVLink.
- **Bottleneck:** AllToAll + dense-TP AllReduce on the same fabric.
- **Failure:** EP forced onto RDMA when NVLink would have been fast enough.
  → `MoE-Expert-Parallelism.md`, `Scale-Up-vs-Scale-Out.md`.

### 10. TP + PP + DP + EP (the full multi-node MoE stack)
- **What:** the composition: TP intra-node, PP across nodes for capacity, EP for experts,
  DP across replicas for concurrency. The DeepSeek-V3-class deployment.
- **Wins:** frontier MoE (hundreds of billions of params) at high concurrency.
- **Bottleneck:** every collective at once; topology placement is make-or-break.
- **Failure:** a single slow node serializes the whole PP+EP mesh.
  → `Multi-Node.md`, `Cross-Layer-Optimization.md`.

### 11. Prefill/decode disaggregation (P/D split)
- **What:** prefill on a **compute-optimized** pool; decode on a **bandwidth-optimized**
  pool; the KV is transferred between them.
- **Wins:** mixed prefill/decode workloads; long prompts; strict TTFT **and** ITL SLOs.
- **Bottleneck:** **KV transfer** over the fabric (RDMA/NVL72) — the new hot spot.
- **Failure:** transfer latency > the compute it saves; KV placement wrong → recompute.
  → `Prefill-Decode-Disaggregation.md`.

## Choosing among them (the decision tree)

```
How big is the model (in GiB, at your dtype)?
├─ fits on 1 GPU (incl. KV headroom) ──► (1) single-GPU + continuous batching
└─ does not fit
    ├─ fits a TP-group on 1 NVLink node ──► (2) TP single-node
    │      need more throughput/concurrency? ──► (8) TP + DP
    │      MoE? ──► (9) TP + EP
    ├─ needs > 1 node
    │      dense?  ──► (7) TP + PP  (or (10) with DP/EP)
    │      MoE?    ──► (10) TP + PP + EP (+ DP)
    │      NVL72 domain?  ──► (3) multi-node TP becomes viable
    └─ long-context / huge-KV
          ──► add (CP/SP, see Multi-GPU.md §4) and consider P/D split
Mixed prefill+decode, strict dual SLOs, long prompts ──► (11) P/D disaggregation
```

**Two cross-cutting rules:**
1. **Never put TP across a slow fabric** (rule out 3 on IB/RoCE; it's only sane on
   NVL72). TP ⇒ NVLink.
2. **P/D disaggregation is a scheduling + KV-placement decision as much as a network
   one** — it moves the bottleneck from the GPU to the fabric (see `Cross-Layer-Optimization.md`).

## The 2026 practical defaults [I: synthesis of the linked pages]
| Situation | Topology |
|---|---|
| 7B–70B dense, fits a node | **TP single-node** (+ DP for scale) |
| 70B–400B dense | **TP (intra) + PP (inter)** |
| any MoE | **TP + EP**, AllToAll on the fastest fabric you have |
| high-concurrency chat, fits a node | **DP replicas** + KV-aware router |
| long prompts, dual SLO | **P/D disaggregation** |
| 1M+ context | **TP + CP/SP** |

## Example [E, hand-derived]
A 6.5B-class dense model, BF16 ≈ 13 GB weights. On an 8×H100 (NVLink, ~3.35 TB/s
HBM each, 80 GB HBM):
- **Single GPU (1):** fits (13 GB weights + KV < 80 GB). Decode ceiling ≈ BW/weights ≈
  3.35e12 / 13e9 ≈ **257 tok/s** at B=1 (upper bound, before attention/KV) — but you
  only have one GPU's throughput.
- **TP=8 (2):** weights/GPU ≈ 1.6 GB; 8× the Tensor Cores; but 2× AllReduce/layer over
  NVLink. ITL drops; you pay fabric. Usually **overkill** for 6.5B — TP=2 or DP is
  enough.
- **DP=8 replicas (5):** 8× request throughput, each self-contained; router balances
  remaining work. Best for **concurrency** at this size.
[All [E]: weights/dtype = 6.5B × 2 B; ceiling = HBM-BW ÷ weight-bytes.]

## How to measure "is this topology right?"
- **TTFT and ITL per topology** at fixed concurrency (the sweep; `Labs.md` Lab 18/20).
- **Collective-vs-compute ratio** in Nsight Systems: if NCCL kernels are > ~30% of step
  time, the split is too wide for the fabric.
- **Bubble fraction** (PP) and **AllToAll time** (EP) — the two topology-specific taxes.
- **KV-transfer time** (P/D): if it's > ~10% of decode time, disaggregation is not
  paying. → `Perf-Experiment-Template.md`.

## Related
`Multi-GPU.md` · `Tensor-Parallelism.md` · `Pipeline-Parallelism.md` ·
`MoE-Expert-Parallelism.md` · `NCCL.md` · `Multi-Node.md` · `Scale-Up-vs-Scale-Out.md` ·
`Topology.md` · `Prefill-Decode-Disaggregation.md` · `Load-Balancing.md` ·
`Cross-Layer-Optimization.md` · `../Distributed-Inference/README.md` · `../Networking/README.md`

## Key Takeaways
1. **11 topologies = 3 knobs:** model split (TP/PP/EP/CP), request split (DP), and
   prefill/decode split (P/D). Compose them.
2. **TP ⇒ NVLink; PP/EP/CP ⇒ can cross nodes; DP ⇒ router.** Match the split to the fabric.
3. **The default large-dense stack is TP (intra) + PP (inter).** The default MoE stack adds EP.
4. **Every extra split adds a collective** — measure the collective-vs-compute ratio before
   declaring the topology a win.
5. **P/D disaggregation moves the bottleneck to the fabric** (KV transfer) — budget for it.
