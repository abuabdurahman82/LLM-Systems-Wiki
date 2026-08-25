# Troubleshooting
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.
NCCL variable list verified against the live 2.31.2 env page (fetched 2026-08-25).

## 30-Second Explanation
Most "NCCL is slow" incidents are one of five things: wrong transport
(socket instead of RDMA), broken GDR mapping, bad GPU↔NIC affinity, a sick
fabric (PFC/MTU/AR), or an algorithm/protocol mismatch. This page: the current
env-var toolkit (2.31), two canonical diagnoses, and the full decision tree.
**Do not present deprecated variables as current recommendations** — the list
below is the 2.31 snapshot; anything older (e.g. pre-2.14 CollNet tweaks,
legacy `NCCL_SOCKET_NTHREADS` defaults) needs the "since X" check first
[../GPU-Systems/NCCL.md; I: version-drift discipline].

## 1. The debugging variables (current, NCCL 2.31.2)
```bash
NCCL_DEBUG=INFO            # INFO|WARN|TRACE — logging level
NCCL_DEBUG_SUBSYS=NET,GRAPH,ENV   # filter by subsystem (NVLS, COLL, P2P, PROXY, …)
NCCL_DEBUG_FILE=nccl.log          # log destination
NCCL_SOCKET_IFNAME=eth0           # which interface for OOB/bootstrap + socket transport
NCCL_IB_HCA=mlx5_0,mlx5_2         # which IB HCAs to use (exclude bad ones)
```
Supporting knobs that a diagnosis will touch (all present in the 2.31 list
[F: env.html fetched 2026-08-25]):
- **Transport forcing/exclusion**: `NCCL_P2P_DISABLE`, `NCCL_SHM_DISABLE`,
  `NCCL_IB_DISABLE`, `NCCL_NET_GDR_LEVEL` (GDR locality preference),
  `NCCL_P2P_LEVEL`, `NCCL_P2P_PXN_LEVEL`, `NCCL_PXN_DISABLE`.
- **GDR/registration**: `NCCL_NET_GDR_READ`, `NCCL_DMABUF_ENABLE`,
  `NCCL_LOCAL_REGISTER`, `NCCL_GDRCOPY_ENABLE` (+ `NCCL_GDRCOPY_FLUSH_ENABLE`,
  `NCCL_GDRCOPY_SYNC_ENABLE`).
- **Channels/CTAs**: `NCCL_MIN_NCHANNELS`/`NCCL_MAX_NCHANNELS`,
  `NCCL_MIN_CTAS`/`NCCL_MAX_CTAS`, `NCCL_CTA_POLICY`.
- **Algo/proto overrides**: `NCCL_ALGO`, `NCCL_PROTO` (per-function grammar
  since 2.24 [05 §1]).
- **IB tuning**: `NCCL_IB_ADAPTIVE_ROUTING`, `NCCL_IB_TC`, `NCCL_IB_SL`,
  `NCCL_IB_GID_INDEX`, `NCCL_IB_QPS_PER_CONNECTION`, `NCCL_IB_MERGE_NICS`,
  `NCCL_IB_TIMEOUT`, `NCCL_IB_RETRY_CNT`, `NCCL_IB_PCI_RELAXED_ORDERING`,
  `NCCL_IB_CUDA_SUPPORT`.
- **NVLS/CollNet**: `NCCL_NVLS_ENABLE` (0/1/2; default 2),
  `NCCL_COLLNET_ENABLE` (legacy; `collnetEnable` in ncclConfig_t is the
  structured path), `NCCL_IGNORE_COLLNET_MISMATCH`.
- **Newer (2.28–2.31)**: `NCCL_GIN_PLUGIN`, `NCCL_RMA_PLUGIN`,
  `NCCL_SYM_GIN_KERNELS_ENABLE`, `NCCL_RUNTIME_CONNECT`,
  `NCCL_MULTI_RANK_GPU_ENABLE` (2.30, experimental), RAS
  (`NCCL_RAS_ENABLE`, `NCCL_RAS_ADDR`, `NCCL_RAS_TIMEOUT_FACTOR`),
  `NCCL_MNNVL_ENABLE` (Multi-Node NVLink, Blackwell-era),
  `NCCL_PROFILER_PLUGIN`, `NCCL_TOPO_FILE`/`NCCL_TOPO_DUMP_FILE`.
- **Topology**: `nvidia-smi topo -m`, and `NCCL_TOPO_DUMP_FILE` to capture
  NCCL's own discovered graph for comparison.

> Deprecation watch: variables move between releases (the 2.31 page is the
> authority; the 2.28 archive page still shows the older set). When a variable
> you're reading about in a blog post is *absent* from the 2.31 list, treat the
> blog as stale [I: version-drift rule; F: 2.31 vs 2.28 env pages].

## 2. Canonical diagnosis #1: "NCCL is using Socket instead of RDMA"
Symptom: `NCCL INFO Using network Socket` in the logs, inter-node busbw in the
single-digit GB/s.
```text
1. Is the fabric up?        ibstat / ibdiagnet (IB) · ethtool/switch counters (RoCE)
2. Is the HCA visible?      NCCL_IB_HCA set to the right device names?
3. Does GDR map?            NCCL INFO "DMA-BUF is available" / GDR checks pass?
                            (IOMMU/ACS, BAR1 size: `cat /proc/driver/nvidia/...`,
                            lspci bar sizing)
4. Is the NIC on the right rail?  nvidia-smi topo -m → want PIX/PXB, not SYS
5. Is the socket path a fallback for OOB only?  NCCL_SOCKET_IFNAME correct?
```
Fixes in order: correct `NCCL_IB_HCA`, enable GDR (`NCCL_NET_GDR_LEVEL`),
disable ACS/IOMMU on the GPU root, size BARs, move the workload to
rail-local NICs [03 §4; I: GDR failure lore].

## 3. Canonical diagnosis #2: "NCCL bandwidth much lower than NIC line rate"
Symptom: socket/IB transport *is* selected, but busbw ≪ line rate (e.g. 20
GB/s on a 400 Gb rail).
```text
1. algbw vs busbw confusion?  busbw = algbw × 2(N−1)/N [E: 1.75 @ N=8]
                              — you may be reading algbw and expecting line rate.
2. Protocol?                 NCCL_DEBUG=INFO shows the chosen (algo, proto);
                              wrong proto at your message size → pin NCCL_PROTO
                              for the size regime [05 §4].
3. Algorithm?                ring vs tree vs NVLS for your N/topology
                              [05 §1].
4. Channels?                 NCCL_MIN/MAX_NCHANNELS — too few can't fill the
                              rail; too many steal SMs [05 §6].
5. GDR?                      host bounce (SHM path) instead of HBM↔NIC →
                              GDR level / DMA-BUF / IOMMU [§2 steps].
6. Affinity?                 GPU→NIC SYS instead of PIX → 2–4× haircut [03 §4].
7. Multi-rail?               Is only 1 of 8 NICs being used?
                              NCCL_MAX_NCHANNELS / nChannelsPerNetPeers [03 §3].
8. Fabric?                   RoCE: PFC storms / ECN mis-tune; IB: adaptive
                              routing off; MTU mismatch (512 vs 4096);
                              NIC counter drops (ethtool -S / port counters).
9. NUMA?                     Registration on the far socket (UPI hop) [16 §7].
10. NVLS off?                On NVLink4, missing "NVLS" in INFO logs →
                              NCCL_NVLS_ENABLE semantics [06 §3].
```

## 4. The decision tree
```text
Low NCCL Performance
       │
       ├── Correct NIC?
       │      (NCCL_IB_HCA, right device, fabric up: ibstat/switch counters)
       │
       ├── GPUDirect enabled?
       │      (GDR mapping: IOMMU/ACS, BAR size, "DMA-BUF available" in logs;
       │       NCCL_NET_GDR_LEVEL; NCCL_DMABUF_ENABLE)
       │
       ├── Correct GPU/NIC affinity?
       │      (nvidia-smi topo -m: PIX/PXB not SYS/NUMA; rail-local)
       │
       ├── IB/RoCE healthy?
       │      (IB: ibdiagnet, adaptive routing; RoCE: PFC/ECN/DCQCN counters,
       │       no PFC storms; MTU consistent 4096 both ends)
       │
       ├── MTU correct?
       │      (mismatched MTU → silent fragmentation/pacing loss)
       │
       ├── Multi-rail configured?
       │      (all NICs used? NCCL_MAX_NCHANNELS, nChannelsPerNetPeers)
       │
       ├── PCIe bottleneck?
       │      (PCIe gen/width vs NIC speed; GDR path through the right switch;
       │       C2C/PCIe topology on the platform)
       │
       ├── NUMA mismatch?
       │      (registration/memory on NIC's socket; NCCL_IGNORE_CPU_AFFINITY
       │       off by default — keep it)
       │
       ├── Congestion?
       │      (ECN marks, PFC pause counters, hot rail; consider spraying/CC:
       │       UCCL-Tran, adaptive routing)
       │
       └── Wrong algorithm/protocol?
              (NCCL_DEBUG=INFO → (algo, proto) per op; pin NCCL_ALGO/NCCL_PROTO
               per size regime; NVLS/CollNet when hardware present)
```
Reading it top-down: *transport first, then geometry, then fabric, then
software choice* — because each lower rung caps the higher ones
[../Networking/README.md; I: the ladder argument of 03].

## 5. NIXL / UCCL-side symptoms (quick map)
- **NIXL**: transfer stuck in `INPROG` → check backend selection (the agent
  picked the wrong plugin), metadata exchange (ETCD/KV reachable?),
  notification support (`supportsNotif()`); register the right memory type
  (VRAM vs DRAM vs FILE) [07 §3–4; F: NIXL BackendGuide].
- **NIXLBench numbers don't match the app** → micro vs app gap: setup
  overhead, chunking, overlap [16 §1].
- **UCCL-Tran on the wrong NIC class** → wrong sub-project (rdma vs efa vs
  afxdp); check the sub-README's supported matrix [09 §6; F].
- **EP hotspots** → model-level imbalance, not a transport fault; move to
  capacity factors / flow control before touching the fabric
  [14 §7; ../GPU-Systems/MoE-Expert-Parallelism.md].

## Key Takeaways
1. Five root causes cover most incidents: wrong transport, broken GDR, bad
   affinity, sick fabric, wrong algo/proto.
2. The 2.31 env list is the authority; treat pre-2.31 blog advice as possibly
   stale (version-drift rule).
3. "Socket instead of RDMA" → HCA visibility → GDR mapping → affinity, in
   that order.
4. "Below line rate" → first check the algbw/busbw confusion, then protocol,
   channels, GDR, rail usage, fabric health.
5. Work the tree top-down: transport → geometry → fabric → software choice;
   lower rungs cap higher ones.

## Related
[05 NCCL Algorithms & Transport](05-nccl-algorithms-transport.md) ·
[06 NCCL + RDMA + SHARP](06-nccl-rdma-sharp.md) ·
[16 Performance Benchmarking §6–8](16-performance-benchmarking.md) ·
`../GPU-Systems/Diagnostics.md`

## References
- NCCL 2.31.2 env page (full variable list fetched 2026-08-25; since-versions
  for NVLS/CollNet/PXN/MultiRank; 2.31 GIN/RMA/MNNVL/RAS additions)
  — https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html [F]
- NCCL 2.31.2 troubleshooting/logging pages (NET/GIN/RMA plugin log lines,
  DMA-BUF, topology examples) [F]
- NIXL BackendGuide (backend selection, notifications, mem types) [F]
- `../Networking/README.md` (fabric health: PFC/ECN/AR; internal)
