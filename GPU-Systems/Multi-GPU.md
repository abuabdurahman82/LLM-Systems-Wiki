# Multi-GPU LLM Systems — Why and How
`LAST_UPDATED: 2026-08-21 · Status: core page` · Parallelism deep dives in
`Tensor-Parallelism.md`, `Pipeline-Parallelism.md`, `MoE-Expert-Parallelism.md`; the
collectives in `NCCL.md`; the 11 reference topologies in `Distributed-Architectures.md`.

## 30-Second Explanation
You reach for multiple GPUs for **one of four reasons**, and each reason maps to a
**different parallelism strategy**:
```
Model doesn't fit one GPU  →  CAPACITY  →  Tensor Parallelism (TP) / Pipeline (PP)
One GPU too slow           →  THROUGHPUT →  more Tensor Cores (TP) or Data-Parallel replicas
Latency target too strict  →  LATENCY   →  TP (shrink per-token work) / speculative decode
Large concurrency          →  SERVING   →  Data-Parallel replicas + router (P/D pools)
```
The core trade: **every split across GPUs costs communication** (a collective op per
layer or per step). The faster the fabric (NVLink ≫ PCIe ≫ RDMA), the more you can
split. **Match the split to the fabric you actually have** — that is the whole discipline
of multi-GPU inference.

## The four problems, precisely
| Problem | Symptom | Fix | Cost |
|---|---|---|---|
| **Capacity** | OOM: weights (+KV) don't fit | TP (shrink weights/GPU) or PP (shrink layers/GPU) | collective per layer (TP) / P2P (PP) |
| **Throughput** | tok/s too low | TP (more Tensor Cores) or DP replicas (more GPUs in parallel) | TP: AllReduce; DP: router |
| **Latency** | ITL/TTFT too high | TP (less work per token) or speculative decode | TP: AllReduce per token |
| **Concurrency** | can't serve N simultaneous requests | DP replicas + router, or P/D disaggregation | router + KV transfer |

## The six parallelism dimensions (WHAT / WHY / HOW / WHEN / COMM / FAILURE)
> Deep dives: TP → `Tensor-Parallelism.md`, PP → `Pipeline-Parallelism.md`,
> EP → `MoE-Expert-Parallelism.md`. SP/CP/DP are summarized here.

### 1. Data Parallelism (DP)
- **WHAT:** replicate the model (or a TP-shard of it); each replica serves a different
  slice of the request stream.
- **WHY:** throughput + concurrency without any per-layer collective.
- **HOW:** N replicas + a router that balances remaining work (`Load-Balancing.md`).
- **WHEN:** the model **fits** in one (or TP-group) GPU and you just need more
  throughput / SLO headroom.
- **COMM COST:** ~0 per step (no gradient sync in inference); only router traffic +
  optional shared-KV/prefix sync.
- **FAILURE MODES:** hot-spotting (router sends long work to one replica), prefix-cache
  fragmentation (shared prefix is cold on most replicas).

### 2. Tensor Parallelism (TP)
- **WHAT:** split each layer's weight matrices across GPUs (col/row-parallel GEMM).
- **WHY:** capacity (weights ÷ TP) + latency (per-token work ÷ TP) + throughput
  (Tensor Cores ÷ TP).
- **HOW:** Megatron-style col/row-parallel linear layers; **2 AllReduce per layer**
  (one after attention, one after MLP) [F: Megatron-LM arXiv:1909.08053].
- **WHEN:** intra-node, NVLink. The default first split for a model that doesn't fit.
- **COMM COST:** AllReduce ×2/layer, **every step, every token** → latency-critical.
  ~900 GB/s NVLink needed.
- **FAILURE MODES:** cross-node TP (line-rate AllReduce over RDMA → latency blows up);
  TP=8 on a PCIe box (PCIe ~64 GB/s → AllReduce dominates).
- → `Tensor-Parallelism.md`.

### 3. Pipeline Parallelism (PP)
- **WHAT:** split **layers** across GPUs; each stage holds a slice; activations flow P2P.
- **WHY:** capacity with **small** comm (only P2P between stages) → good across nodes.
- **HOW:** stage 0 = layers 0–19, stage 1 = layers 20–39, …; micro-batches pipeline the
  stages to hide the **bubble**.
- **WHEN:** very large models; multi-node when NVLink isn't available; combined with TP
  (TP within node, PP across nodes).
- **COMM COST:** P2P activations between stages (small, ∝ batch×d×b, not the full layer).
- **FAILURE MODES:** **pipeline bubble** (idle time unless micro-batch pipelining),
  stage imbalance (uneven layer splits → last stage idles).
- → `Pipeline-Parallelism.md`.

### 4. Sequence / Context Parallelism (SP/CP)
- **WHAT:** split the **sequence** (prompt) across GPUs; each holds K/V for a chunk.
- **WHY:** long-context KV that won't fit on one GPU.
- **HOW:** Ring Attention (rotate K/V chunks around a ring [F: arXiv:2310.01889]) or
  DeepSpeed-Ulysses (head-parallel via AllToAll [F: arXiv:2309.14509]).
- **WHEN:** ultra-long context (100k+) on many GPUs; the backbone of 1M+ context.
- **COMM COST:** AllToAll (Ulysses) per attention layer, or ring rotations (Ring
  Attention) → bandwidth-hungry.
- **FAILURE MODES:** fabric too slow for the AllToAll/ring; attention gather overhead at
  each layer.

### 5. Expert Parallelism (EP) — MoE only
- **WHAT:** split the **experts** across GPUs; each token is routed to its expert's GPU.
- **WHY:** MoE models have far more total params than activated; EP shards the experts.
- **HOW:** router picks top-k experts → **AllToAll dispatch** tokens to expert GPUs →
  expert GEMM → **AllToAll combine** back [F: DeepSeekMoE arXiv:2401.06066, Mixtral
  arXiv:2401.04088].
- **WHEN:** MoE (DeepSeek, Mixtral, Qwen-MoE, GPT-OSS). Wide EP + KV-aware placement.
- **COMM COST:** AllToAll (dispatch + combine) per MoE layer → the MoE bottleneck.
- **FAILURE MODES:** **expert imbalance** (hot experts over-subscribe one GPU),
  routing to a cold/far GPU, AllToAll under fabric pressure.
- → `MoE-Expert-Parallelism.md`.

### 6. Hybrid (the practical 2024+ stack)
- **WHAT:** compose them. **TP within node (NVLink) + EP/PP across nodes (RDMA) + DP via
  router** [I: standard practice; Megatron-Core, TRT-LLM, SGLang all expose these knobs].
- **WHY:** each dimension is best on a different fabric; compose to use the fast fabric
  for latency-critical collectives and the slow fabric for bandwidth-tolerant ones.

## Communication → hardware (the mapping)
| Collective | Used by | Best fabric |
|---|---|---|
| AllReduce | TP (2×/layer) | NVLink/NVSwitch (intra-node) |
| AllToAll | EP, CP | NVLink or fast RDMA (IB/RoCE) |
| P2P Send/Recv | PP stages | any (RDMA good cross-node) |
| AllGather | ZeRO-3/FSDP (training); param gather | NVLink/RDMA |
| KV transfer | P/D disaggregation | RDMA / NVL72 |

## Choosing the decomposition (decision flow)
```
Does the model fit on 1 GPU?
 ├─ yes → need more throughput/concurrency? → DP replicas (+ router). Need lower latency?
 │         → TP (intra-node) + spec decode.
 └─ no  → how big is the gap?
          ├─ small (2×)  → TP=2 (NVLink).
          ├─ medium      → TP=4/8 (NVLink, 1 node).
          └─ large (≥ node) → TP within node + PP across nodes. MoE? → EP across nodes.
             long context? → + CP/SP.
```
**Rule of thumb:** TP first (it's the latency-friendly split), PP second (it's the
capacity-friendly cross-node split), EP for MoE, DP to scale out, CP for long context.
Full "when does each architecture make sense": `Distributed-Architectures.md`.

## Hardware impact
Every split **divides** either weights (TP/PP/EP) or KV (CP) or requests (DP) across
GPUs, and **adds** a collective on the fabric. The fabric is the constraint:
- **NVLink/NVSwitch (intra-node):** ~900 GB/s H100, 72-GPU domain on NVL72 → TP up to
  8, even 72, with low latency.
- **PCIe:** ~64 GB/s → TP is painful; prefer DP or PP.
- **RDMA (IB/RoCE):** ~50 GB/s/link × N links → PP/EP/CP/P-D, not TP.
`Multi-Node.md` + `Scale-Up-vs-Scale-Out.md` + `Topology.md` cover the fabric in depth.

## Inference impact
- **TP:** ITL ÷ TP (roughly, until the AllReduce dominates); TTFT ÷ TP.
- **PP:** adds stage latency + bubble; throughput-friendly, latency-penal.
- **EP:** MoE expert time ÷ EP, until AllToAll dominates.
- **DP:** throughput × N replicas (router-bound); no per-request latency change.
- **CP:** long-context KV ÷ CP; attention time depends on fabric.

## Example [E, method]
A 27B model, BF16 ≈ 50.3 GiB, won't fit on a 40 GB A100. Options:
- **TP=2 on 2×A100 (NVLink):** weights ÷ 2 ≈ 25 GiB/GPU → fits. ITL ÷ 2 (ideal), but
  2× AllReduce/layer over NVLink.
- **PP=2 across 2 nodes (RDMA):** layers ÷ 2 → ~25 GiB/GPU; P2P between stages; adds a
  stage bubble.
- **DP=1** (no split): OOM. Not an option.
TP=2 is the better latency choice (NVLink); PP=2 is the better cross-node choice (small
comm). **The fabric decides.** [E: method]

## Failure modes (system-level)
- **TP across nodes:** AllReduce per layer over RDMA → latency collapses. Keep TP
  intra-node.
- **EP hot-expert:** one expert gets 3× the tokens → its GPU is the bottleneck. (Fix:
  expert placement, capacity factors, `MoE-Expert-Parallelism.md`.)
- **PP imbalance:** uneven layer split → last stage idles → bubble. (Fix: balance
  FLOPs/stage.)
- **DP hot-spot:** router overloads one replica. (Fix: balance remaining work,
  `Load-Balancing.md`.)
- **Wrong topology:** GPUs on the wrong PCIe/NVLink path → NCCL halves throughput.
  (`Topology.md`.)

## How to measure it
- **ITL/TTFT vs TP/PP/EP degree** (the sweep; `Labs.md` Lab 18/19).
- **Collective time vs compute time** (Nsight Systems shows the NCCL kernels on the
  timeline; if they're a large fraction → comm-bound).
- **Per-GPU HBM BW util + fabric util** (DCGM) — balanced across the group?
- **Bubble fraction** for PP (stage idle time / total).
- **NCCL benchmark** (NCCL's `all_reduce_perf`) to characterize the fabric itself.

## Related
`Tensor-Parallelism.md` · `Pipeline-Parallelism.md` · `MoE-Expert-Parallelism.md` ·
`NCCL.md` · `Multi-Node.md` · `Scale-Up-vs-Scale-Out.md` · `Topology.md` ·
`Distributed-Architectures.md` · `../Distributed-Inference/README.md` ·
`../Networking/README.md` · `../Hardware/README.md`.

## Key Takeaways
1. **Four problems → four fixes:** capacity→TP/PP, throughput→TP/DP, latency→TP/spec,
   concurrency→DP/P-D.
2. **Every split costs a collective**; match the split to the fabric (NVLink for TP,
   RDMA for PP/EP/CP).
3. **The 2024+ default:** TP intra-node + EP/PP across nodes + DP via router.
4. **No single best parallelism** — it's a function of model size, MoE-vs-dense,
   context length, concurrency, and the fabric.
