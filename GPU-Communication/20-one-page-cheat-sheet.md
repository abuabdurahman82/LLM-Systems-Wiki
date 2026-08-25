# One-Page Cheat Sheet (and Glossary)
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## The cheat sheet
```text
NCCL
Purpose: GPU collectives (NVIDIA) + P2P
Think: AllReduce / the 2(N−1)/N ring

NIXL
Purpose: inference data movement (heterogeneous mem/storage)
Think: KV Cache Transfer / agent + buffer lists

UCCL
Purpose: flexible GPU communication across vendors/fabrics
Think: Collectives + P2P + Expert Parallel (NCCL-API drop-in)

UCX
Purpose: communication transport framework
Think: Transport abstraction (RDMA/SHM/TCP)

NVSHMEM
Purpose: GPU one-sided communication (PGAS)
Think: put/get/atomics from inside a kernel

DeepEP
Purpose: MoE expert-parallel communication (NVIDIA-first)
Think: Token dispatch/combine, NCCL Gin (V2), 0-SM modes
```
The three-primary-rule: **NCCL does the in-layer collectives, NIXL moves the
KV, UCCL/DeepEP do the EP — all at once, over GDR on IB/RoCE/EFA.**
([15 NCCL vs NIXL vs UCCL](15-nccl-vs-nixl-vs-uccl.md))

## The complete end-to-end LLM communication map
```text
                        LLM SYSTEM
                            │
          ┌─────────────────┼──────────────────┐
          │                 │                  │
       Training          Inference            MoE
          │                 │                  │
          ▼                 ▼                  ▼
        NCCL              NCCL              UCCL-EP / DeepEP
          │                 │                  │
          │              NIXL                  │
          │                 │                  │
          │            UCX / UCCL              │
          └─────────────┬───┴──────────────────┘
                        │
                       RDMA
                        │
                 GPUDirect RDMA
                        │
           ┌────────────┼─────────────┐
           ▼            ▼             ▼
     InfiniBand       RoCEv2          EFA
           │
           ▼
        Network
           │
      SHARP / ECN /
   Adaptive Routing etc.
```
Every layer: application (the workload) → communication layer (choreography:
collectives / KV agent / EP kernels) → transport (RDMA/verbs/libfabric/TCP/EFA)
→ hardware offloads (GDR, IBGDA/GDA, SHARP, NVLS) → physical fabric
(NVLink/PCIe/IB/RoCE/EFA). The bottom moves the bytes; the top decides
what/where/how ([15 §4](15-nccl-vs-nixl-vs-uccl.md)).

## Zero-to-hero: the ten core ideas
1. Distributed AI requires efficient GPU communication — performance is
   frequently set by data movement, not FLOPS.
2. Collectives describe group communication patterns (the seven shapes;
   AllReduce = ReduceScatter + AllGather).
3. NCCL is central to NVIDIA GPU collective communication (collectives *and*
   P2P; topology-aware; NVLink/PCIe/network).
4. NCCL operates across NVLink, PCIe, and network fabrics — transport
   selection is per-peer, per-size.
5. GPUDirect RDMA removes unnecessary CPU memory copies (HBM↔NIC DMA).
6. Training and inference generate different communication patterns (step-
   cadence gradient sync vs per-token collectives + per-request KV + dynamic EP).
7. Disaggregated inference creates a new KV-cache movement problem (bulk,
   asymmetric, dynamic, heterogeneous).
8. NIXL targets this broader inference data-movement problem (agent + plugin
   backends; not "another NCCL").
9. UCCL spans collectives, P2P, and specialized expert-parallel communication
   (portable across vendors/fabrics; OSDI'26).
10. Modern AI systems increasingly *combine* multiple communication
    technologies rather than relying on one library (NCCL + NIXL + EP in one
    cluster).

Learner path: beginner → collectives → GPU topology → NCCL → RDMA →
distributed-inference communication → NIXL → UCCL → select & troubleshoot
stacks → design communication for large LLM clusters.

## Glossary
- **rank** — a participant's index `[0, nranks)` in a communicator
  (process + device + comm).
- **communicator** — the group handle a collective runs in (pinned ranks,
  transports, channels).
- **collective** — a group operation with a defined input/output per
  participant (AllReduce, AllGather, …).
- **P2P** — point-to-point communication (Send/Recv; Put/Get one-sided).
- **RDMA** — remote direct memory access: kernel-bypass, zero-copy DMA over the
  fabric.
- **GPUDirect RDMA** — NIC↔HBM DMA with no host-memory bounce.
- **GPUDirect Storage** — NVMe↔HBM DMA (cuFile); NIXL's GDS backend.
- **NIC** — network interface card (the host's fabric endpoint).
- **HCA** — host channel adapter (the IB NIC).
- **QP** — queue pair: the RDMA connection abstraction (send/recv queues + CQs).
- **CQ** — completion queue: where posted work reports done/error.
- **memory registration** — pinning + mapping a region so the NIC can DMA it
  (yields an rkey).
- **rkey** — remote key: the token a one-sided RDMA op needs to reach a remote
  registered region.
- **NVLink** — GPU↔GPU point-to-point link (H100: 900 GB/s aggregate).
- **NVSwitch** — the all-to-all GPU fabric within a tray/rack (NVLink domain).
- **NVLS** — NVLink SHARP: in-domain collective offload to the NVSwitch
  (NVLink4/Hopper+; `NCCL_NVLS_ENABLE`).
- **SHARP** — in-network reduction on IB switches (the inter-node cousin of NVLS).
- **InfiniBand** — the lossless, adaptive-routing RDMA fabric.
- **RoCE** — RDMA over Converged Ethernet (needs PFC/ECN/DCQCN tuning).
- **EFA** — AWS Elastic Fabric Adapter: SRD (lossy-tolerant, adaptive routing),
  GDA offload.
- **UCX** — Unified Communication X: the transport-abstraction framework
  (RDMA/SHM/TCP/GPU).
- **NIXL** — NVIDIA Inference Xfer Library: agent + buffer lists + plugin
  backends for heterogeneous inference data movement.
- **NCCL** — NVIDIA Collective Communications Library: topology-aware GPU
  collectives + P2P.
- **RCCL** — AMD's NCCL-equivalent collective library.
- **UCCL** — UC Berkeley/Davis GPU communication stack: UCCL-Tran (collectives,
  NCCL-API), UCCL-P2P, UCCL-EP (≠ UCC).
- **NVSHMEM** — OpenSHMEM-based PGAS: one-sided GPU communication from kernels.
- **AllReduce** — everyone ends with the reduction of everyone's buffer.
- **AllGather** — everyone ends with the concatenation of everyone's slice.
- **ReduceScatter** — everyone ends with the reduced result, partitioned.
- **All-to-All** — every rank sends a slice to every other (MoE dispatch/combine).
- **expert parallelism** — experts live on different GPUs; tokens route between
  them (all-to-All).
- **tensor parallelism** — a layer's GEMMs split across GPUs; AllReduce/
  AllGather inside the layer.
- **pipeline parallelism** — layers split across stages; Send/Recv at
  boundaries.
- **prefill** — the compute-bound pass over the prompt (produces KV).
- **decode** — the memory-bound pass, one token at a time.
- **KV cache** — the per-token key/value tensors (128 KiB/token for the
  canonical 8B-GQA model [E]); the P/D handoff payload.
- **disaggregated inference** — prefill and decode on different workers; KV
  crosses the fabric between them (NIXL's design target).

## Related
[01 Why Communication Matters](01-why-communication-matters.md) ·
[18 Architecture Decision Guide](18-architecture-decision-guide.md) ·
[21 References](21-references-and-research.md)

## References
- Glossary terms verified against the same 2026-08-25 primary-source set as
  [21](21-references-and-research.md); [E] numbers inherit this section's
  machine-checked compute (128 KiB/token, 4.0 GiB @ 32k, 2(N−1)/N factors).
