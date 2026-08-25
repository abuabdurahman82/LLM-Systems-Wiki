# GPU Communication & Data Movement for Distributed LLM Systems
`LAST_UPDATED: 2026-08-25` · Status: core section

> **From FLOPS to Bytes: the communication stack under distributed LLMs.**
> A first-principles, systems-engineering-grade handbook for the communication
> layers that decide whether a multi-GPU LLM cluster is fast — NCCL (collectives
> + P2P), NIXL (inference data movement), UCCL (portable collective/P2P/EP), and
> the transports underneath (GPUDirect RDMA, InfiniBand / RoCE / EFA). Verified
> against primary sources on 2026-08-25 (NCCL 2.31.2, NIXL v1.4.0, UCCL main +
> OSDI'26, DeepEP V2, llm-d v0.5) — see
> [21 References & Research](21-references-and-research.md).

## The one-sentence version
**Distributed AI performance is frequently determined not just by FLOPS, but by
how efficiently data moves between GPUs.** This section maps that movement,
teaches the libraries that perform it, and gives you the decision + benchmarking
+ troubleshooting toolkit to pick and run the right stack for a production LLM
system.

## The organizing taxonomy (the spine)
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
Three branches, one cross-cutting workload (expert parallelism). The layers
**complement each other rather than merely compete** — a production serving
stack runs all three at once.

## Reading order
### Foundations
- `01-why-communication-matters.md` — why one GPU isn't enough; the time budget
  (compute + comm + sync + memory movement); the taxonomy; where this section
  sits in the wiki.
- `02-collective-communication-fundamentals.md` — the seven collectives (diag +
  I/O + volume + LLM use), P2P, the `T ≈ α + nβ` cost model, the parallelism→
  collective map.
- `03-gpu-network-architecture.md` — the physical topology ladder, GPUDirect
  RDMA vs CPU-mediated, multi-rail, `nvidia-smi topo -m`, the fabric quick-map.

### The primary libraries
- `04-nccl-deep-dive.md` — NCCL architecture, ranks/comm/channels, init
  sequence, algorithms, protocols, transports, network path, advanced features
  (NVLS/SHARP/GIN/GDA/CFT/NCCL-EP), version gates.
- `05-nccl-algorithms-transport.md` — ring vs tree vs NVLS; Simple/LL/LL128;
  per-peer transport selection; channels/CTAs; the 4.0 GiB ≈ 4.8 ms NVLink vs
  ≈ 344 ms 100 GbE reference.
- `06-nccl-rdma-sharp.md` — RDMA is a transport NCCL uses; SHARP/NVLS
  in-network reduction; GDA/GIN; failure modes; decision summary.
- `07-nixl-deep-dive.md` — NIXL is *not* "another NCCL"; the agent + NB/SB API;
  core concepts; lifecycle; memory hierarchy; NIXL+UCX; NIXL+UCCL; NIXL+Dynamo.
- `08-nixl-kv-cache-transfer.md` — the KV handoff: size math (4.0 GiB @ 32k),
  transfer-time table, KV-aware routing (h=0.9 → 34.4 ms), async overlap, why
  not NCCL Send/Recv.
- `09-uccl-deep-dive.md` — UCCL origins/status (UC Berkeley/Davis, OSDI'26),
  the three components, the software-transport philosophy, adoptions.
- `10-uccl-collective-p2p-ep.md` — UCCL-Tran/P2P/EP in detail; the NIXL+UCCL
  complementarity; DeepEP vs UCCL-EP head-to-head.
- `11-ucx-rccl-ucc-nvshmem-deepep.md` — the adjacent libraries (UCX, RCCL, UCC,
  NVSHMEM, DeepEP, MSCCL++, MPI, libfabric, GDR/GDS, SHARP/NVLS) + the UCC≠UCCL
  trap.

### The workloads
- `12-training-communication.md` — the multi-node training stack; per-
  parallelism communication; training-vs-inference comm table.
- `13-distributed-inference-communication.md` — the three inference streams;
  TP serving; the engine-by-engine comm map (vLLM/SGLang/TRT-LLM/Dynamo/llm-d,
  verified).
- `14-moe-communication.md` — why MoE changes network design; dispatch/combine;
  GPU-driven/IBGDA; DeepEP vs UCCL-EP; the large-MoE-cluster architecture.
- `15-nccl-vs-nixl-vs-uccl.md` — the comparison matrix; three questions / three
  answers; the layer diagram; which layer moves the bytes; the six
  misconceptions.

### The toolkit
- `16-performance-benchmarking.md` — micro vs app benchmarks; the battery;
  algbw/busbw/goodput/scaling efficiency; small vs large messages; compute/comm
  overlap; the network deep-dive (IB/RoCE PFC/ECN/DCQCN/EFA); multi-rail;
  topology; the four practical architectures.
- `17-troubleshooting.md` — the current (2.31.2) NCCL env-var toolkit; the two
  canonical diagnoses (Socket-instead-of-RDMA; below line rate); the full
  decision tree; NIXL/UCCL-side symptoms.
- `18-architecture-decision-guide.md` — the decision tree; the scenario matrix
  with the *why*; the 8 decision factors; anti-patterns; the Central-Question
  architecture answered.
- `19-practical-labs.md` — nccl-tests (1/2/8-GPU + 2-node MPI), reading the
  output; the NIXL two-node lab + NIXLBench/KVBench; the UCCL lab; the fair
  benchmark methodology.
- `20-one-page-cheat-sheet.md` — the one-page cheat sheet; the complete e2e
  communication map; the ten zero-to-hero ideas; the glossary.
- `21-references-and-research.md` — the dated source set; the stability
  classification; the provenance audit (seed claims CONFIRMED/CORRECTED/
  UNVERIFIED); "Verified as of 2026-08-25".

## How to use it
- **Learning the topic from scratch** → read 01→03, then 04→06 (NCCL), then
  07→08 (NIXL), then 09→10 (UCCL), then 11, then the workloads (12–14), then
  15, then the toolkit (16–19).
- **Picking a stack for a fleet** → jump to [18](18-architecture-decision-guide.md).
- **Something is slow** → jump to [17](17-troubleshooting.md).
- **You need a defensible number** → [16](16-performance-benchmarking.md) +
  [19](19-practical-labs.md) + [21](21-references-and-research.md).

## Cross-links (non-duplication)
- `../GPU-Systems/NCCL.md` — the house NCCL deep-dive (algorithms on NVLink, the
  4.8 ms reference). This section covers the *stack around* it.
- `../GPU-Systems/{Topology.md, Scale-Up-vs-Scale-Out.md, Multi-Node.md}` —
  topology and scale physics.
- `../GPU-Systems/{Tensor-Parallelism.md, Pipeline-Parallelism.md,
  MoE-Expert-Parallelism.md, Prefill-Decode-Disaggregation.md}` — workload-side
  detail.
- `../Distributed-Inference/{Overview.md, NVIDIA-Dynamo.md, llm-d.md}` — the
  Dynamo/llm-d landscape.
- `../Networking/README.md` — the networking primer (RDMA/IB/RoCE/SHARP/GDR).
- `../KV-Cache/README.md` — KV-cache architecture & offloading.

## Verification & status
- All fast-moving facts verified against primary sources **2026-08-25** (see
  [21](21-references-and-research.md)).
- `[E]` numbers machine-computed this session; vendor numbers labeled
  project-reported, never independent.
- Section provenance audit: 17 CONFIRMED, 2 CORRECTED (line-rate convention; the
  4.8 ms label), 1 taxonomy warning upheld.
