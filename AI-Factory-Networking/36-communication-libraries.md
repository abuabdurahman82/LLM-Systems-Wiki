# Communication Libraries — the Software Stack Map
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: NCCL/RCCL docs, MPI/UCX/UCC/NVSHMEM/NIXL documentation, libfabric/OFI; fetched 2026-08-25.

## 30-Second Explanation
The bytes an AI job moves are decided by a **stack of communication libraries**, not by
the transport alone. The framing is: **frameworks → distributed library → collective/
transport library → provider/abstraction → wire (IB/RoCE/UET)**. The same GPU app
(`PyTorch/JAX/… → torch.distributed`) reaches the wire through **NCCL** (CUDA collectives),
**RCCL** (AMD analogue), **MPI**, or **UCC**, each of which either talks to a **provider**
(**UCX**, **OFI/libfabric**, or raw **verbs**) or uses in-network offload (**SHARP/**
**INC** plugins) — and because these libraries select a *transport provider at runtime*,
**the same workload can run on InfiniBand or RoCE (or UET) without code changes**. This
page maps who sits where and, crucially, **which library moves which bytes** — the
practical question for a fabric engineer deciding where a bottleneck really lives. The
fabric side is in the rest of this section; the GPU-centre of the NCCL internals is
[../GPU-Communication/04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md).

## The full stack map
```text
   Frameworks (callers):        PyTorch        JAX        TensorFlow
                                     │            │            │
   Distributed layer:             torch.distributed (gloo / nccl / mpi backends)
                                     │
   Collective / message libs:    NCCL · RCCL · MPI · UCC · NVSHMEM · NIXL
                                     │                  │
   Providers / abstractions:  UCX ─ OFI libfabric ─ verbs(ibverbs)   ← select at runtime
                                     │                  │
   Wire:                 InfiniBand ─ RoCEv2 ─ UET ─ (also TCP/shm for UCX/NCCL)
```
Every layer above "wire" is a **fat, replaceable plug-in point** — which is the whole
point of the map [I]: the workload is written once, and the transport is chosen
underneath.

## Where each library sits and what it owns

| Library | Owner / nature | Domain | What it "owns" |
|---|---|---|---|
| **NCCL** | NVIDIA, CUDA collectives | collective | AllReduce/AllGather/…, **topology-aware** scheduling, GPU↔GPU data path, built-in IB/RoCE transport (+ NET plugin extension point for non-IB networks like EFA) |
| **RCCL** | AMD, ROCm | collective | the AMD analogue of NCCL; collectives over ROCm + RoCE/IB |
| **MPI** | standard (OpenMPI/MPICH…) | message passing | point-to-point + collectives semantics; **IB/RoCE verbs or TCP** via PML/BTL, MCA tuning |
| **UCX** | open-source (transport abstraction) | transport | abstracts **verbs/TCP/shared-memory**; shared-memory + network, used by OpenMPI/UCC |
| **UCC** | open-source (UCX consortium) | collective optimizer | collective ops **over UCX/MPI**, algorithm scheduling |
| **NVSHMEM** | NVIDIA, PGAS | one-sided | **PGAS** (partitioned global address space) over IB/RoCE; fine-grained one-sided put/get |
| **NIXL** | NVIDIA | KV-cache movement | KV-cache transfer for inference (see [../GPU-Communication/README.md](../GPU-Communication/README.md)) |
| **libfabric/OFI** | OFA (open) | provider API | **UEC's northbound API**; provider model over verbs/RoCE/IB |
| **SHARP plugin** | NVIDIA | in-network offload | hook to offload reduction into SHARP switches (see ./32 INC) |
| **vendor plugins** | per vendor | integration | NIC-pinned transports, GDR, topology XML |

## The five backbone libraries, in focus

**NCCL** — "NVIDIA Collective Communications Library": the CUDA collective engine. It is
**topology-aware** (it builds a hardware topo from PCIe/NVLink/NIC and plans ring/tree/
NVLS), lives entirely on the GPU data path, and reaches the network through a **NET
plugin**; transports include **IB (verbs), RoCE, and TCP/Socket** fallback, plus `P2P`
(NVLink/PCIe) and SHM inside the node [F: NCCL docs]. Env knobs like `NCCL_NET`,
`NCCL_IB_HCA`, `NCCL_ALGO`, `NCCL_PROTO` pick provider+algorithm (./33's measurement).
**RCCL** is the same idea for AMD/ROCm [F: RCCL docs].

**MPI** — the message-passing standard (OpenMPI/MPICH). It owns **message semantics**
(point-to-point + collective "MPI_*" ops) and reaches hardware via BTL/PML; OpenMPI
commonly sits MPI **over UCX (OFI/verbs) or TCP**, tuned through the MCA parameter space
[F: OpenMPI docs]. MPI is the HPC ancestral path NCCL and friends grew out of; UET's HPC
profile targets MPI/OpenSHMEM (see ./31) [I].

**UCX** — the transport-abstraction layer above verbs: it multiplexes **shared-memory,
TCP, and RDMA (IB/RoCE)** behind one API so upper layers (OpenMPI, UCC, some NCCL paths)
do not hard-code a wire choice [F: UCX docs]. **UCC** sits above UCX as a *collective
optimizer* — it picks algorithm/transport per size, the software broker for the collective
decisions discussed in ./33 [F: UCC docs].

**NVSHMEM / NIXL** — the one-sided and inference movers. **NVSHMEM** is a **PGAS** model
(partitioned global address space) over **IB/RoCE** for **fine-grained one-sided** put/get
and atomics — the load/store-style access that dense-AI fabric peers to NVLink semantics
[F: NVSHMEM docs]. **NIXL** is NVIDIA's **KV-cache movement** library for inference — the
software that executes the KV ships of [./35-training-vs-inference.md](./35-training-vs-inference.md)
(see [../GPU-Communication/README.md](../GPU-Communication/README.md)) [F: NVIDIA; I].

**libfabric/OFI** — the OpenFabrics provider API and, importantly, **UEC UET's northbound
API (libfabric v2.0)**. Its **provider model** (one API, many providers: verbs, sockets,
UET) is exactly why UET can slot in without changing application code [F: UEC spec-update
blog; OFI]. The UET **FEP** maps onto libfabric; the UET **INC** collective API is
`fi_collective()` (./32) [F: spec].

## In-network offload hooks
- **SHARP** (NVIDIA) and **UEC INC** (./32) let a *switch* do the reduction. From the
  software view these are **plugins**: the library detects the capability and routes the
  reduce into the switch (NVIDIA SHARP via NCCL/SHARP plugin; UEC INC via `fi_collective()`)
  instead of the host [F: NVIDIA; UEC].
- **Vendor plugins**: NVIDIA/AMD/Arista/etc. ship NIC-pinned providers and topology files
  (e.g. `topo.xml` for NCCL) so the library's algorithm plan matches the physical rail
  [I].

## Which library moves which bytes
| Bytes being moved | Typical owner | Wire it drives |
|---|---|---|
| Gradients / params (training) | **NCCL** (or RCCL) | IB/RoCE via NET plugin |
| Activations across TP/PP ranks | **NCCL / MPI** (or UCC) | IB/RoCE |
| MoE token dispatch/combine | **NCCL alltoall / DeepEP / UCC** | IB/RoCE (AllToAll, ./34) |
| MPI workloads / OpenSHMEM | **MPI / NVSHMEM** | IB/RoCE verbs (or TCP) |
| KV-cache ship (inference) | **NIXL** | IB/RoCE, latency-sensitive |
| Legacy / storage fabric | **verbs / libfabric** direct | RoCE / IB / UET |

## How the same workload runs on IB or RoCE via the plugin layer
Because the collective libraries ≥ UCX never hard-code a wire, **the transport is a free
choice below the API** [F/A]:
```text
   Same NCCL app
     └─ NCCL_NET=IB      → verbs on InfiniBand (NDR)   ─┐
     └─ NCCL_NET=RoCE    → RoCEv2 over Ethernet         ┼ same busbw target [E]
     └─ UET provider     → libfabric/UET (early gear)  ─┘
```
The performance changes (§3–4 of this section), but the *code* does not — which is exactly
UEC's selling point ("migrate with no code changes" via libfabric) [F: UEC]. Practical
takeaway [I]: when a job is "slow on IB vs RoCE," the difference is almost never the
library — it is the *provider + topology + CC configuration* underneath, which is what the
rest of this section teaches you to measure and tune (./44).

## Lab — see the stack in action
```
# Which transport did a run actually pick?
NCCL_DEBUG=INFO <your job> 2>&1 | grep -i "Using network"   # 'IB' vs 'Socket' vs 'RoCE'
mpirun --mca pml ucx ...                                     # MPI over UCX (not raw verbs)
# Confirm the transport abstraction: run all_reduce_perf with NCCL_NET=IB vs =Socket
# and watch busbw collapse on Socket → proves the IB provider is the fast path [E/A]
```
*Expect:* with `NCCL_NET=IB` the NET subsys logs the HCA/GID and busbw near the
`0.95 × link` line [E], and with `Socket` an order-of-magnitude drop [I: the classic
fallback symptom].

> **Where this fits.** The fabric side these libraries drive: [./31-uetch-deep-dive.md](./31-uetch-deep-dive.md),
> [./32-uetch-congestion-and-in-network.md](./32-uetch-congestion-and-in-network.md); what
> they execute: [./33-collective-communication.md](./33-collective-communication.md) and
> [./34-moe-all-to-all.md](./34-moe-all-to-all.md); measurement:
> [./44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md);
> GPU-side internals: [../GPU-Communication/04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md)
> and [../GPU-Communication/README.md](../GPU-Communication/README.md).

## Key Takeaways
1. The software stack is **frameworks → distributed layer → collective/transport library → provider/abstraction → wire (IB/RoCE/UET)**; every layer above the wire is a replaceable plug-in point. [I]
2. Because the collective libraries (and UCX) select a transport **provider at runtime**, the same workload runs on InfiniBand, RoCE, or UET **with no code change** — UEC's "migrate with no code changes" selling point via libfabric. [F]
3. **NCCL** is the CUDA collective engine: topology-aware, entirely on the GPU data path, reaching the net through a **NET plugin** (IB verbs / RoCE / TCP); **RCCL** is the AMD/ROCm analogue; **MPI** owns message semantics over BTL/PML. [F]
4. **libfabric/OFI is UET's northbound API (v2.0)** — its provider model is why UET can slot in under existing apps; UET INC surfaces as `fi_collective()`; SHARP/INC are in-network offload plugins. [F]
5. When a job is "slow on IB vs RoCE," the cause is almost never the library — it is the **provider + topology + congestion-control configuration** underneath, which is what you measure and tune. [I]

## Related
- [33-collective-communication.md](./33-collective-communication.md) — the primitives these libraries execute.
- [34-moe-all-to-all.md](./34-moe-all-to-all.md) — AllToAll paths (NCCL alltoall / DeepEP / UCC).
- [31-uetch-deep-dive.md](./31-uetch-deep-dive.md) — the UET provider these libraries may select.
- [35-training-vs-inference.md](./35-training-vs-inference.md) — the workloads whose bytes these libraries move.
- [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md) — NCCL internals in depth.
- [55-cheat-sheet.md](./55-cheat-sheet.md) — quick reference across the section.

## References
- NCCL docs / RCCL docs — topology-aware collectives, NET plugin, env knobs (NCCL_NET/ALGO/PROTO) [F].
- OpenMPI/MPICH docs — PML/BTL and MCA tuning [F].
- UCX / UCC docs — transport abstraction and the collective optimizer [F].
- NVSHMEM / NIXL docs — PGAS one-sided model and KV-cache movement [F].
- libfabric/OFI + UEC spec-update blog — provider model and UET northbound API [F].
- [E] AFN constants bank — `busbw ≈ 0.95 × link` target used in the LAB check (busbw = algbw × 2(n-1)/n normalizes to link at saturation).
