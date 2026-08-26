# GPUDirect RDMA & NCCL over InfiniBand
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: NVIDIA NCCL environment & troubleshooting docs, NVIDIA GPUDirect/kernel docs (nvidia-peermem), perftest man pages, section constants bank; performance extrapolations marked [I]; fetched 2026-08-25.

## 30-Second Explanation
This page has two halves that together explain how a GPU's data actually reaches an
InfiniBand wire. **(a) GPUDirect RDMA (GDR)** lets the NIC DMA **directly to/from GPU memory
(VRAM)**, skipping the CPU and host-RAM bounce. Without it, gradient data must be copied
GPU→host memory→NIC (two extra DMA passes and the CPU/northbridge as a middleman). With GDR,
the NIC maps the GPU's registered buffer over PCIe and moves bytes straight in or out of HBM.
It needs `nvidia-peermem`, a large enough GPU BAR1 mapping, and careful PCIe/NUMA placement
[F: NVIDIA kernel/NCCL troubleshooting docs]. **(b) NCCL over IB** is the collective layer on
top: NCCL discovers the topology (P2P / shared-memory / network), picks a **NET plugin**, binds
to the right **HCA (and GID index, Service Level)**, and runs ring/tree collectives over the
IB verb transport. The full path is
**PyTorch → torch.distributed → NCCL → NCCL NET → verbs (libibverbs) → ConnectX HCA → IB fabric**.
Cross-read [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md) for the software side; this page is the
hardware/data-path side.

## Part (a) — GPUDirect RDMA

### The path problem, before and after
```text
Traditional (no GDR):                     GPUDirect RDMA:
  GPU --PCIe--> host RAM --PCIe--> NIC      GPU ──PCIe──► NIC   (direct DMA)
  (copy 1)   (copy 2)                       one DMA pass, no host bounce
  CPU orchestrates BOTH copies              NIC registers GPU VA, DMAs to/from HBM
```
Without GDR each inter-node message costs **two extra memcpy DMA passes through host RAM**
and puts the CPU/northbridge in the data path — roughly doubling PCIe traffic and adding
latency [I: standard analysis from NVIDIA GDR docs]. GDR cuts both.

### BAR mappings and nvidia-peermem
For a third-party device (the NIC) to DMA to GPU memory, the GPU's memory must be **mapped into
PCIe BAR space** (a window the GPU exposes via its **BAR1**), and the NVIDIA kernel module must
grant the NIC peer access. That is the job of the **`nvidia-peermem`** / `peer-memory` kernel
module: it works with the GPU driver to expose GPU memory as a peer-DMA target, which the NIC
driver then registers. Without `nvidia-peermem` loaded, GDR cannot engage and NCCL falls back
to the through-host path. [F: NVIDIA kernel/nvidia-peermem docs]

### Memory registration of the GPU VA
As with any RDMA, the buffer must be **registered** (pinned + DMA addresses built) before the
NIC can touch it. With GDR, NCCL registers the **GPU virtual address**: the NIC obtains a
stable device/peer mapping into HBM rather than into host RAM. That registration is the "once
and reuse" step NCCL performs at init (see [03-rdma-fundamentals.md](./03-rdma-fundamentals.md)). [F: NVIDIA/NCCL practice]

### PCIe locality + NUMA + IOMMU constraints
GDR only reaches line rate when the pieces are co-located:
- **PCIe locality**: the NIC should sit on the **same PCIe switch / root complex (or at least
  the same CPU socket) as the GPU** it exchanges with. A GPU-NIC pair marked `SYS` in
  `nvidia-smi topo -m` (different NUMA nodes) drags data across QPI/UPI and halves effective
  GDR bandwidth even though "GDR is on" [I: NUMA-distance reasoning].
- **IOMMU**: an enabled IOMMU can block/un-perform peer DMA (NCCL troubleshooting lists IOMMU as
  a GDR blocker); IOMMU must be off (or the platform's peer-DMA path supported) for clean GDR.
- **ACS**: PCIe ACS (Access Control Services) at the root/switch can gate P2P;
  `nvidia-smi topo -p2p` exposes P2P capability, and ACS can be disabled per-device
  (`setpci ... ECAP_ACS+0x6.w=0000`) — an HPC, not production-hobby, step [F: NVIDIA NCCL
  troubleshooting doc].

### `nvidia-smi topo -m` — good vs bad
```text
GOOD (GDR-friendly, same NUMA):           BAD (GDR penalty, different NUMA):
        | NIC0 | NIC1 |                        | NIC0 | NIC1 |
 GPU0   | NODE | PIX  |                   GPU0 | SYS  | SYS  |
 GPU1   | PIX  | NODE |                   GPU1 | SYS  | SYS  |
```
Labels (from NVIDIA NCCL/`nvidia-smi` doc [F]):
`NODE` = NVLink (best); `PIX` = same PCIe switch; `PXB` = across PCIe switches (multi-hop to a
CPU); `PHB` = same NUMA via root port (crosses CPU); `SYS` = different NUMA / SMP interconnect
(worst, no P2P). GPU↔NIC `NODE`/`SYS` is the GDR-quality tell: keep a GPU's NIC on the same
socket.

### Bandwidth / latency impact [I]
Because GDR removes one host bounce, per-transfer PCIe traffic roughly halves and latency drops
by the duration of one extra DMA. Concretely: a 400-Gb/s (50 GB/s) NIC doing full-rate GPU↔GPU over
IB is only realizable with GDR — the through-host path would need ~2× the PCIe bandwidth on the
host bus and adds serialize/deserialize latency. Exact ratios are config-dependent; the *cause*
(bounce removal) is the reliable claim. [I: derived from the path diagram; no universal measured
constant — UNVERIFIED as a number.] The empirical test: `ib_write_bw -c` (CUDA/GDR) vs the same
without `-c` (host buffer) — a large GDR gap means GDR isn't engaging [I, perftest usage].

## Part (b) — NCCL over IB

### Topology discovery: P2P / SHM / NET
At init NCCL maps each GPU's reachability and picks the best transport per pair:
```text
P2P   — NVLink/PCIe peer DMA between GPUs (fastest, intra/within-pod)
SHM   — shared memory via host (for GPUs that can't P2P but share a host)
NET   — network transport (IB/RoCE) for inter-node, and for intra-node when N>
        PCIe paths won't scale; GDR makes NET go straight GPU→NIC
```
NCCL scores these and assigns each connection its best transport; `NCCL_DEBUG=INFO` prints the
topology it detected [F: NCCL docs; [I] behavior].

### NET plugin & transport selection
NCCL loads a **NET plugin** (e.g. `libnccl-net.so` / the IB plugin) that provides
`ncclNet_*` send/recv primitives over verbs. It then picks, per device: which **HCA** to use
(`NCCL_IB_HCA`, e.g. `mlx5_0:1`), the **GID index** (`NCCL_IB_GID_INDEX`, for RoCEv2 often 3 —
a user-set index into the HCA's GID table, **not** auto-negotiated), and the **Service Level** `NCCL_IB_SL` (default SL 0; the SM maps
SL→VL). A wrong GID index is a classic RoCEv1(client)→RoCEv2 hang. [F: NCCL env docs; [I] from
troubleshooting]

### Rings / trees / channels
NCCL builds **channels** (parallel data paths), each an ordered set of ranks; over channels it
runs **ring** (bandwidth-optimal, `2(n−1)/n` [E: bank]) or **tree** (latency-friendly) collectives,
choosing per message size by its internal model. Rings→rails: on a rail-optimized fabric
`NCCL_CROSS_NIC=0` keeps one channel on one NIC/rail. [F: NCCL docs; [E] bank]

### Multi-rail & GDR on/off behavior
- **Multi-rail**: multiple HCAs per node → multiple channels, each pinned to its own NIC/rail,
  so aggregate = N × 400G rather than one link [F].
- **GDR on**: NET transport DMAs GPU→NIC directly (`NCCL_NET_GDR_LEVEL` threshold; `...GDR_READ`
  for read-based GDR). **GDR off**: NET bounces through host RAM — works, but destroys
  bandwidth/latency vs on (see Part (a)). [F: NCCL env docs]

### The full trace
```text
PyTorch          (model/data-parallel step calls collective)
  └─► torch.distributed (dist.all_reduce)          # framework API
        └─► NCCL        (ncclAllReduce)            # collective library: builds channel,
              └── topology: P2P / SHM / NET         #  picks ring vs tree, registers MRs
                    └── NCCL NET plugin (ncclNet_*) #  transport abstraction
                          └── verbs (libibverbs): ibv_post_send, ibv_poll_cq
                                └── ConnectX HCA (QP, doorbell, DMA engine)
                                      └── IB fabric (LRH header, credits, switches) → wire
```
Every hop down adds a header/queue boundary; the EQ is where GDR and HCA selection plug in.

## Hand calculation (example)
Inter-node ring AllReduce, n=8 nodes, M=100 MB, NDR400 (50 GB/s/NIC) [E: bank]:
per-rank wire traffic = 2·(7/8)·100 MB = **175 MB/rank**; transfer ≈ 175 MB/50 GB/s = **3.5 ms**
+ 14·α. With GDR the 175 MB comes straight out of HBM per hop; without GDR, each hop also
crosses host RAM → more PCIe passes and higher latency [I]. (Full collective math:
[33-collective-communication.md](./33-collective-communication.md).)

## Failure modes
- GDR not engaging: no `nvidia-peermem`, IOMMU on, ACS blocking, NIC on a different NUMA socket
  (`SYS` in topo -m) → busbw collapses though the link is healthy.
- Wrong GID index (RoCEv1 vs v2) → cross-subnet hang.
- NCCL fell back to sockets (`NCCL_DEBUG=INFO NET` shows "Socket" not IB) → wrong HCA/plugin.
- `packet_seq_err`/`out_of_sequence` rising → congestion/AR issue (see ./13).

## How to measure it
`ib_write_bw -c` vs without `-c` (GDR on/off, perftest); `nvidia-smi topo -m` for locality;
`NCCL_DEBUG=INFO` (`DEBUG_SUBSYS=NET`) to see transport/HCA/GID chosen; `nccl-tests` busbw to
confirm the fabric delivers. → [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md).

## Key Takeaways
1. GDR = NIC DMAs straight to/from GPU HBM, skipping the host bounce [F].
2. Needs `nvidia-peermem`, GPU BAR1 mapping, IOMMU/ACS handling, and co-located PCIe/NUMA [F: [I]].
3. `nvidia-smi topo -m` `NODE`/`SYS` is the GDR-quality tell [F].
4. NCCL: discover (P2P/SHM/NET) → NET plugin → HCA/GID/SL → ring/tree over verbs.
5. Full path: PyTorch → torch.distributed → NCCL → NET → verbs → ConnectX → IB.

## Related
- [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md) — NCCL software model, workloads (cross-section).
- [03-rdma-fundamentals.md](./03-rdma-fundamentals.md) — verbs object model, memory registration.
- [13-infiniband-congestion-adaptive-routing.md](./13-infiniband-congestion-adaptive-routing.md) — NCCL_IB_ADAPTIVE_ROUTING on the fabric.
- [16-roce-fundamentals.md](./16-roce-fundamentals.md) — the GID index matters for RoCEv2 GDR too.
- [12-infiniband-routing-topology-partitions.md](./12-infiniband-routing-topology-partitions.md) — rail-optimized multi-NIC context.
- [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md) — nccl-tests busbw + perftest GDR check.

## References
- NVIDIA NCCL troubleshooting (IOMMU/ACS/gpu_troubleshooting): docs.nvidia.com/deeplearning/nccl/user-guide/docs/troubleshooting/gpu_troubleshooting.html [F].
- NVIDIA NCCL env vars (HCA/GID/SL/GDR/CROSS_NIC): docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html [F: NCCL docs].
- `nvidia-smi topo` labels + perftest `-c`: docs.nvidia.com + manpages.ubuntu.com/manpages/noble/man1/ib_write_bw.1.html [F]; [I] interpretation.
- nvidia-peermem / peer-memory: NVIDIA GPU-direct kernel docs [F].
- [E] ring AllReduce `2(n−1)/n·M`, NDR400=50 GB/s from the section constants bank (computed 2026-08-25).
