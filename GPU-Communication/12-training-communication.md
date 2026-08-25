# Training Communication
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
Distributed training is the *original* communication workload: every step,
every rank, synchronizes gradients or sharded parameters. The stack that won is
**NCCL over NVLink intra-node + GPUDirect RDMA over IB/RoCE inter-node** — and
it still is, for NVIDIA fleets [../Networking/README.md; I]. This page maps
each parallelism strategy to its dominant communication and why the training
communication shape differs from inference's.

## 1. The canonical multi-node training stack
```text
8× GPU Node
      │
     NCCL
      │
    NVLink
      │
     NIC
      │
InfiniBand
      │
     NIC
      │
8× GPU Node
```
Layer-by-layer:
- **Application** — PyTorch DDP/FSDP or Megatron-style 3D parallelism
  (TP × PP × DP) [../Training-Engineering/Parallelism.md].
- **NCCL** — collectives engine; every `dist.all_reduce` lands here.
- **NVLink/NVSwitch** — intra-node; TP is deliberately kept inside the NVLink
  domain ([../GPU-Systems/Scale-Up-vs-Scale-Out.md]).
- **NIC (one per GPU, rail-optimized)** — inter-node; GPUDirect RDMA mapping
  makes HBM↔NIC zero-copy ([03](03-gpu-network-architecture.md)).
- **InfiniBand/RoCE** — the fabric; IB for lossless + adaptive routing + SHARP;
  RoCE when Ethernet fabric is the constraint ([16](16-performance-benchmarking.md)).

## 2. What each parallelism strategy moves
```text
GPU0 ─ Gradient
GPU1 ─ Gradient
GPU2 ─ Gradient
GPU3 ─ Gradient
          │
          ▼
       AllReduce
          │
          ▼
Synchronized gradients
```
| Strategy | Communication | Volume/step | Notes |
|---|---|---|---|
| **DDP** | AllReduce (grads) | 2× model-size (FP16 grads) | ring or tree; SHARP/NVLS offload helps at high N ([06](06-nccl-rdma-sharp.md)) |
| **FSDP / ZeRO-1** | ReduceScatter (grads) + AllGather (params) | ~2× model-size total | two complementary collectives per step [02 §2.5] |
| **ZeRO-3** | AllGather params just-in-time + ReduceScatter grads | model-size gathered × per-use | more frequent, smaller collectives; communication/compute overlap is the whole game |
| **Tensor Parallel** | AllReduce ×2/layer (attn out + MLP out) | small (activation-sized) per op, **every layer, every micro-batch** | latency-bound; must live on NVLink ([../GPU-Systems/Tensor-Parallelism.md]) |
| **Pipeline Parallel** | Send/Recv activations (fwd) + grads (bwd) at stage boundaries | activation-sized, *infrequent* | bubble fraction is the cost model; comm hides in pipelining (1F1B) [../GPU-Systems/Pipeline-Parallelism.md] |
| **Expert Parallel** | All-to-All dispatch + combine | token-sized, dynamic | [14 MoE Communication](14-moe-communication.md) |
| **Context/Sequence Parallel** | AllGather / P2P (ring attention KV blocks) | KV-block sized | [02 §4](02-collective-communication-fundamentals.md) |

Worked sizes [E]: a 7B model in FP16 has 14 GB of grads; DDP AllReduce moves
~28 GB equivalent through the ring (2(N−1)/N × 14 GB ≈ 28 GB at N≥8 [E:
factor 1.75+]) — at 50 GB/s inter-node effective, ~0.56 s of *pure gradient
traffic* per step — this is why 100k-GPU jobs spend their engineering budget
on the collective path ([../Training-Engineering/Scaling-1-to-10k.md]).

## 3. Why training comm ≠ inference comm (the table from the user's PART 17)
| Requirement | Training | Inference |
|---|---|---|
| Gradient AllReduce | Very high | Low (absent) |
| Tensor Parallel communication | High | High |
| KV transfer | Low | **Very high in disaggregated inference** |
| Expert All-to-All | High for MoE | High for MoE |
| Storage movement | Checkpoints | KV/cache/model loading |
| Dynamic topology | Moderate | **High** (elastic pools, scale-to-zero) |
| Elasticity | Moderate | **High** |

The consequence: the ecosystem split. Training standardized on NCCL+IB early
(2016–2020); inference's *new* traffic — bulk KV handoff, tiered KV, EP on
heterogeneous fleets — is what NIXL/UCCL/Dynamo exist for
([13 Distributed Inference Communication](13-distributed-inference-communication.md)).
Both directions are true at once in a MoE serving cluster: in-layer TP
collectives (NCCL) + KV movement (NIXL) + EP (UCCL-EP/DeepEP)
([15](15-nccl-vs-nixl-vs-uccl.md)).

## 4. Synchronization & overlap
- **Gradient accumulation** reduces AllReduce frequency (every K steps) — a
  comm/throughput trade [I].
- **Bucketing** (DDP) merges many small grads into one large AllReduce — the
  α + nβ argument applied: fewer, bigger messages beat many small ones
  [02 §3; F: PyTorch DDP docs].
- **Comm/compute overlap** — FSDP/ZeRO-3 overlap AllGather of the *next* layer
  with GEMM of the *current* one; NCCL's CUDA-stream semantics + streams in the
  framework make this the default [05 §6; I].
- **SHARP/NVLS** — when the fabric/switch does part of the reduction, the
  unoverlapped comm time shrinks further ([06](06-nccl-rdma-sharp.md)).

## 5. Failure modes (training-flavored)
- **One slow rank** → the whole AllReduce waits; straggler = whole cluster
  stalls (collective = synchronous by definition).
- **NCCL timeout/hang** — a rank died mid-collective; the remaining ranks
  block until the watchdog (`NCCL_TIMEOUT`/framework timeout) fires
  [../Networking/README.md; I].
- **Wrong transport selected** — socket instead of RDMA: 10–100× slower
  inter-node; see [17](17-troubleshooting.md).
- **Checkpoint I/O contention** — all ranks write to the same storage at the
  same instant → storage-bound stall; spread/striped writes, or NIXL-GDS-style
  tiered movement for the hot path [I: standard practice; 07 §5].

## Key Takeaways
1. Training comm = gradient sync at step cadence: DDP/FSDP AllReduce &
   ReduceScatter/AllGather + TP AllReduce inside every layer.
2. The 7B-DDP number to remember: ~28 GB of ring traffic/step → ~0.56 s at
   50 GB/s [E] — communication is a *first-order step-time term*, not noise.
3. TP belongs on NVLink, DP on the fabric, PP on Send/Recv — the placement
   discipline is the design.
4. Training and inference have different comm shapes (table above); that
   difference is *why* the NIXL/Dynamo/UCCL layer exists.
5. Synchronization is a failure amplifier: one straggler stalls the collective.

## Related
[13 Distributed Inference Communication](13-distributed-inference-communication.md) ·
[14 MoE Communication](14-moe-communication.md) ·
`../Training-Engineering/Parallelism.md` · `../GPU-Systems/Distributed-Architectures.md`

## References
- PyTorch DDP/FSDP docs [F: pytorch.org/docs/stable, fetched 2026-08-25]
- NCCL docs (collectives, NVLS, SHARP/CollNet) [F]
- `../Training-Engineering/Scaling-1-to-10k.md`, `../GPU-Systems/Scale-Up-vs-Scale-Out.md` (internal)
