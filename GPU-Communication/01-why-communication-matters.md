# Why Communication Matters
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
A single GPU cannot hold or serve most frontier LLMs: parameters, KV cache, activations,
and optimizer states exceed any one HBM stack, and even when they fit, one device's
FLOPs saturate long before demand. So modern systems spread work across GPUs — and the
instant you do, **performance is no longer determined by FLOPS alone, but by how
efficiently data moves between GPUs** [I: standard systems argument]. This section maps
the whole stack — collectives (NCCL/RCCL/UCCL), point-to-point data movement
(NIXL), expert-parallel communication (UCCL-EP/DeepEP), and the transports underneath
(RDMA, GPUDirect, IB/RoCE/EFA) — and how to pick, benchmark, and debug them.

## 1. Why one GPU is not enough
The "1 GPU vs 8 GPUs vs 1000 GPUs" framing:

```text
1 GPU
 │
 ├── Compute          (FLOPs, fixed)
 └── HBM              (memory capacity, fixed; ~80 GB on H100 [F: NVIDIA H100 datasheet])

8 GPUs
 │
 ├── Compute          (8× FLOPs)
 ├── HBM              (8× capacity)
 └── GPU↔GPU communication becomes critical  (NVLink/PCIe)

1000 GPUs
 │
 └── Network communication can determine cluster efficiency  (IB/RoCE/EFA)
```

The memory math for the canonical GQA model (Llama-3.1-8B-class: `L=32` layers,
`H_kv=8` KV heads, `d_h=128`, FP16 — the same geometry used by
`../GPU-Systems/Prefill-Decode-Disaggregation.md`'s "27B-class" example) at
32k context [E: this section's canonical example]:

| Quantity | Value | Derivation |
|---|---|---|
| KV per token | 128 KiB | 2·32·8·128·2 B |
| KV @ 32k context | **4.0 GiB** | 128 KiB × 32768 |
| KV @ 1M context | 122.07 GiB | 128 KiB × 1,048,576 [E] |

- **GPU memory capacity** — weights + KV + activations + batch state must fit HBM;
  KV alone is 4.0 GiB per request at 32k context for an 8B GQA model [E].
- **Parameter count** — a 70B model at FP16 is ~140 GB of weights: 2× H100-80GB at
  minimum; at 4-bit quant, 4B-class weights fit in one, 70B-class needs 2 [E].
- **KV-cache size** — grows linearly with context and batch; this is the dominant
  memory term at serving time and the payload that P/D disaggregation moves
  ([08 NIXL for KV-Cache Transfer](08-nixl-kv-cache-transfer.md)).
- **Activation memory** — attention material and MLP intermediates scale with batch ×
  sequence; long prefills can need tens of GB transiently [I].
- **Optimizer states** — mixed-precision training keeps master FP32 weights + FP32
  momentum + variance ≈ 16 bytes/param, so 7B params need ~112 GB of optimizer state
  before a single bit of weight [E: 7e9×16 B = 112 GB].
- **Distributed training / distributed inference** — both split work across GPUs for
  capacity *and* throughput; the split creates communication on every step / every
  token [F: PyTorch DDP docs].
- **Mixture-of-Experts** — routing tokens to experts on other GPUs makes
  communication data-dependent and irregular ([14 MoE Communication](14-moe-communication.md)).
- **Prefill/decode disaggregation** — different compute regimes run on different
  machines; the KV cache must cross the fabric between them
  ([13 Distributed Inference Communication](13-distributed-inference-communication.md)).

## 2. The time budget
```text
Total Job Time
      =
Compute Time
+
Communication Time
+
Synchronization Time
+
Memory/Data Movement Time
```
On a well-tuned node, compute and communication overlap; what you observe is the
*unoverlapped* remainder plus synchronization. Two consequences:
1. **Collectives on the critical path** (TP AllReduce inside every layer) add directly
   to per-token latency — see [08](08-nixl-kv-cache-transfer.md) for a worked estimate.
2. **Bulk movement off the critical path** (KV transfer to a waiting decode worker,
   checkpoint writes) only matters to the extent bandwidth × setup overhead exceeds
   the work it buys.

## 3. The organizing taxonomy (this section's spine)
Not everything in this section is a "collective communication library". The taxonomy
this section uses throughout:

```text
                    Distributed AI Communication
                              │
       ┌──────────────────────┼───────────────────────┐
       │                      │                       │
   Collectives            Point-to-Point        Memory/Data
       │                  Communication           Movement
       │                      │                       │
     NCCL                  NCCL Send/Recv            NIXL
     RCCL                     UCCL                  UCX
     UCC                      UCX                   GDS
     MSCCL++                  NIXL                  libfabric
     UCCL                     NVSHMEM               UCCL
       │                      │
       └──────────── Expert Parallel ────────────────┘
                     DeepEP / UCCL-EP
```

Three branches, one cross-cutting workload class (expert parallelism). The layers
**complement each other rather than merely compete**:

```text
Application / Framework
        │
        ▼
vLLM / SGLang / TensorRT-LLM / Dynamo
        │
        ├──────── Collective operations ───────► NCCL
        │
        ├──────── KV-cache transfer ───────────► NIXL
        │                                        │
        │                                        ▼
        │                                 UCX / UCCL / GDS
        │
        └──────── MoE Expert Parallel ─────────► UCCL-EP / DeepEP
                                                  │
                                                  ▼
                                          RDMA / IB / RoCE
```

A production serving stack literally runs all three branches at once: TP collectives
inside each layer (NCCL), KV-cache handoff between prefill and decode workers (NIXL
over UCX/UCCL), and expert dispatch/combine for MoE layers (UCCL-EP or DeepEP) —
[15 NCCL vs NIXL vs UCCL](15-nccl-vs-nixl-vs-uccl.md) formalizes this.

## 4. Where this section fits in the wiki
- `../GPU-Systems/NCCL.md` — house NCCL deep-dive (algorithms, NVLink paths, the
  4.8 ms 32MB AllReduce number); this section covers the *stack* around it.
- `../GPU-Systems/Topology.md`, `../GPU-Systems/Scale-Up-vs-Scale-Out.md`,
  `../GPU-Systems/Multi-Node.md` — topology and scale physics.
- `../GPU-Systems/MoE-Expert-Parallelism.md`,
  `../GPU-Systems/Prefill-Decode-Disaggregation.md` — workload-side detail.
- `../Distributed-Inference/Overview.md` — Dynamo/llm-d landscape.
- **Naming trap:** UCCL (UC Berkeley/Davis GPU stack, this section) ≠ UCC
  (Unified Collective Communication, the OpenHPC/LLNL `ucc` collective layer) —
  both appear in the taxonomy on purpose; see
  [11 UCX/RCCL/UCC/NVSHMEM/DeepEP](11-ucx-rccl-ucc-nvshmem-deepep.md).

## Key Takeaways
1. One GPU runs out of HBM, then of FLOPs, then of everything — distribution is a
   memory story before it is a compute story.
2. Distributed AI performance is frequently determined not just by FLOPS, but by how
   efficiently data moves between GPUs.
3. The three-branch taxonomy (Collectives / P2P / Memory-Data Movement + EP) is what
   stops you from mislabeling NIXL or UCCL as "just another NCCL".
4. Layers complement: one serving cluster runs NCCL + NIXL + EP communication
   simultaneously, over the same RDMA fabric.
5. Total job time = compute + communication + synchronization + memory movement;
   every tool in this section attacks one of those terms.

## Related
[02 Collective Communication Fundamentals](02-collective-communication-fundamentals.md) ·
[03 GPU Network Architecture](03-gpu-network-architecture.md) ·
[18 Architecture Decision Guide](18-architecture-decision-guide.md)

## References
- PyTorch Distributed (DDP) docs — https://pytorch.org/docs/stable/distributed.html (fetched 2026-08-25)
- NVIDIA H100 datasheet (80 GB HBM3, 3.35 TB/s) — https://www.nvidia.com/en-us/data-center/h100/ [F]
- `../GPU-Systems/NCCL.md` (internal cross-link)
