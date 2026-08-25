# GPU & Network Architecture
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
GPU-to-GPU data movement happens over a **ladder of physical links** that differ by
roughly two orders of magnitude in bandwidth and a few orders in latency. Every
communication library in this section is, at its core, a *topology-aware path
finder* over that ladder: NVLink first, then PCIe, then the NIC — and the single
biggest architectural trick is **GPUDirect RDMA**, which lets the NIC DMA directly
to/from HBM, deleting the CPU's bounce buffers from the critical path.

## 1. The topology ladder
```text
GPU
 │
 ├── HBM                 (on-package DRAM; H100: 3.35 TB/s [F: H100 datasheet])
 │
 ├── NVLink              (GPU↔GPU; H100: 900 GB/s bidirectional aggregate [F])
 │
 ├── NVSwitch            (all-to-all within a tray/rack; NVLink4 domain, Hopper+)
 │
 ├── PCIe                (GPU↔host / GPU↔NIC; Gen4 ×16 ≈ 32 GB/s, Gen5 ×16 ≈ 64 GB/s [F: PCIe spec])
 │
 ├── NIC                 (ConnectX / EFA; NDR IB = 400 Gb/s = 50 GB/s line rate [F: Mellanox NDR])
 │
 ├── GPUDirect RDMA      (NIC↔HBM path, no host memory in the loop)
 │
 ├── InfiniBand / RoCE / EFA   (the fabric between nodes)
 │
 └── Remote GPU          (someone else's HBM)
```
Rough effective bandwidths (sustained, typical [I: measurements, vendor specs ±10%]):
HBM 3.35 TB/s → NVLink 900 GB/s → PCIe Gen5 64 GB/s → NDR IB 50 GB/s → 100 GbE
12.5 GB/s → 25 GbE 3.125 GB/s. A 4.0 GiB KV transfer therefore takes ~4.8 ms over
NVLink but ~88.7 ms over a 400 Gb/s link and ~343.6 ms over 100 GbE
[E: 4 GiB ÷ link bandwidth; matches the transfer table in
`../GPU-Systems/Prefill-Decode-Disaggregation.md`]. **The link choice is a 70×
decision** — that spread is what the rest of this section is about.

## 2. Two ways to cross the wire
CPU-mediated (the old default):
```text
GPU HBM → host DRAM (copy) → CPU copies → NIC DMA → network
                                   (2+ copies, host latency on every hop)
```
GPUDirect RDMA:
```text
GPU HBM ──► NIC ──► network ──► NIC ──► remote GPU HBM
        (DMA, zero host-memory copies; NIC drives the GPU's PCIe port)
```
Why eliminating the bounce buffer matters [F: NVIDIA GPUDirect RDMA docs]:
- **Bandwidth** — the host path serializes through DRAM bandwidth and two copies;
  GDR moves once, over the link's own capacity.
- **Latency** — no CPU cache-line walks, no page-table walks in the host kernel
  path; the NIC posts a WQE and DMAs.
- **CPU cycles** — the host stays free; critical for decode latency where the CPU
  otherwise spends its budget on copies.
Requirements: PCIe P2P capability, BAR sizing, IOMMU mapping (or ACS/IOMMU
disabled on the GPU's root), and the NIC visible on the right PCIe switch
([17 Troubleshooting](17-troubleshooting.md) covers "fell back to Socket").
GPUDirect **Storage** (GDS) is the NVMe analogue: SSD ↔ HBM with no host DRAM
bounce [F: NVIDIA GDS docs] — NIXL's `cuda_gds` backend is built on it
([07 NIXL Deep Dive](07-nixl-deep-dive.md)).

## 3. Multi-rail networking
Modern nodes put **one NIC per GPU** (rail-optimized topology):
```text
             GPU
              │
       ┌──────┴──────┐
       ▼             ▼
     NIC0           NIC1
      │               │
Fabric Rail A     Fabric Rail B
```
- **Rail-optimized**: GPU i talks to remote GPU i through NIC i; every flow stays
  within its rail, no rail-crossing at the switch — congestion is bounded by
  rail-local demand.
- **NIC affinity**: a GPU on a different PCIe switch than its "home" NIC pays a
  QD3/xGMI/PCIe-bridge hop; `NCCL_NET_GDR_LEVEL` / topology files let libraries
  prefer the local NIC.
- **GPU/NIC locality + NUMA**: PCIe root complex belongs to one CPU socket;
  registering memory on the far socket adds a UPI/QPI crossing.
- Libraries exploit this: NCCL assigns a net peer per channel and can run
  **nChannelsPerNetPeer** (>1) to parallelize across rails
  [F: NCCL ncclConfig_t docs, nChannelsPerNetPeer].

## 4. `nvidia-smi topo -m` and what the letters mean
```text
        GPU0  GPU1  NIC0  NIC1
GPU0     X    NV4  PIX   SYS
GPU1    NV4    X   SYS   PIX
```
- **NV#** — NVLink domain, # = link count (NV4 = 4 links; NV18 on H100 NVSwitch
  systems [F: nvidia-smi topo docs]).
- **PIX/PXB** — PCIe: same switch / crossing switches — P2P capable, GDR-friendly.
- **PHB/NUMA** — through host bridge, same/other socket — GDR works but slower.
- **SYS** — inter-socket (UPI/QPI) — the last place you want your NIC to be.
Rule of thumb: `GPU → local NIC` (PIX) is preferred over
`GPU → CPU socket → PCIe → remote-NUMA NIC` (SYS) — every extra level is roughly
a 2–4× bandwidth haircut [I: measured P2P degradation patterns].

## 5. The fabric side (IB / RoCE / EFA) — quick map, full treatment in [06]
- **InfiniBand (NDR/XDR)** — lossless by design, adaptive routing in the switch,
  native GDR; SHARP offload available [F: NVIDIA IB docs].
- **RoCEv2** — RDMA over Ethernet; needs PFC/ECN/DCQCN tuned to be lossless-ish;
  cheaper fabric, more operational state [I: standard DC fabric practice].
- **AWS EFA** — SRD (scalable reliable delivery): lossy-tolerant, no PFC, adaptive
  routing inside the ENI stack; GDA offload path supported [F: AWS EFA docs].
NCCL exposes all three through the same transport selection; NIXL/UCCL reach EFA
via libfabric/UCX backends ([11 UCX/RCCL/UCC/NVSHMEM/DeepEP](11-ucx-rccl-ucc-nvshmem-deepep.md)).

## 6. Why topology decides which library features matter
- NVLink-domain collectives → NVLS/NVLink SHARP offload is available
  ([06 NCCL + RDMA + SHARP](06-nccl-rdma-sharp.md)).
- Multi-rail IB/RoCE → multi-NIC channels, PXN, GDR level tuning.
- EFA-only (cloud) → GDA/SRD paths; NVLS and IB-only features absent
  [I: feature-gating by fabric].
Topology discovery is therefore a library *input*, not a detail: NCCL auto-discovers
at `ncclCommInitRank` ([04](04-nccl-deep-dive.md)), and the whole troubleshooting
section ([17](17-troubleshooting.md)) is "which rung of the ladder did we end up
on?".

## Key Takeaways
1. Five rungs, ~70× bandwidth spread: HBM → NVLink → PCIe → NIC → fabric.
2. GPUDirect RDMA deletes host bounce buffers: one copy, DMA-driven, CPU out of
   the hot path.
3. Rail-optimized topologies pair GPU i with NIC i; affinity is a first-order perf
   variable, not a sysadmin nicety.
4. `nvidia-smi topo -m` letters (NV#/PIX/SYS) predict performance before you run
   a single benchmark.
5. Fabric choice (IB vs RoCE vs EFA) gates which library features exist at all.

## Related
[03 predecessor: 02 Collectives](02-collective-communication-fundamentals.md) ·
[05 NCCL Algorithms & Transport](05-nccl-algorithms-transport.md) ·
`../GPU-Systems/Topology.md` · `../GPU-Systems/Multi-Node.md`

## References
- NVIDIA GPUDirect RDMA — https://docs.nvidia.com/cuda/gpudirect-rdma/ (fetched 2026-08-25) [F]
- NVIDIA GPUDirect Storage — https://docs.nvidia.com/gds/ (fetched 2026-08-25) [F]
- H100 datasheet; Mellanox NDR/XDR line rates — vendor pages [F]
- `nvidia-smi` topology documentation (topo -m) [F]
- `../GPU-Systems/Topology.md`, `../GPU-Systems/Scale-Up-vs-Scale-Out.md` (internal)
