# Cheat Sheet & Final Architecture
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
One-page mental model for the whole section; all [E] numbers from the section constants bank (2026-08-25).

## 30-Second Explanation
This page compresses the section into a single mental model: **five network domains, three
fabric answers, one software stack, six design numbers, and ten command groups.** If you
remember nothing else, remember the shape: *scale-up is coherent and local, scale-out is
RDMA over leaf-spine, and the job runs at the speed of its slowest rank.*

## The one-page mental model
```text
AI NETWORKING

Scale-up (rack/pod, sub-µs)
├── NVLink / NVSwitch (NVL72: 72-GPU domain, 1.8 TB/s/GPU, 129.6 TB/s aggregate [E])
├── NVLink-C2C (Grace↔GPU chiplet link)
├── UALink (open scale-up, emerging — spec 1.0/1.1; no shipping volume as of 2026-08 [F: UALink consortium])
├── Infinity Fabric (AMD MI300/MI350 rack)
└── PCIe / CXL (context: expansion, not collectives)

Scale-out (cross-rack, µs, RDMA)
├── InfiniBand
│   ├── Native RDMA · credit flow control (lossless by construction)
│   ├── LID/GID addressing · Subnet Manager control plane
│   ├── Adaptive routing · P_Key · SHARP in-network reduction
│   └── NDR400 → XDR800 (50 → 100 GB/s/port [E])
│
├── RoCEv2
│   ├── RDMA in UDP/IP over Ethernet (UDP 4791; 58 B header overhead [E])
│   ├── PFC (per-priority pause) + ECN/WRED + DCQCN
│   ├── Rail-optimized multi-plane leaf-spine, jumbo MTU
│   └── Vendor fabrics: Spectrum-X, Etherlink, Nexus, Juniper, merchant TH4/TH5
│
└── Ultra Ethernet / UET (spec 1.0, June 2025 [F: UEC spec cover])
    ├── Clean-slate RDMA-inspired transport (ephemeral PDCs; spraying + reassembly)
    ├── Multipathing by design · NSCC/RCCC congestion control · optional CBFC
    ├── LLR link-level retransmission · lossy-or-lossless
    └── libfabric/OFI endpoint; silicon early (2026: pre-volume [I: status])

Front-end / management (separated)
    Kubernetes · Slurm · SSH · telemetry · registry · DNS/DHCP

Storage (separated, can be oversubscribed)
    Lustre / GPFS / WEKA / VAST / DDN over 100–400GbE RDMA · GPUDirect Storage

DCI / multi-site (different problem class)
    400ZR / 800G ZR · WAN-scale: RTT-dominated, not BW-dominated
```

## The six design numbers to remember [E — constants bank]
| Quantity | Value |
|---|---|
| NDR400 port | 4 × 100 Gb/s (PAM4, 256b/257b) = 400 Gb/s = 50.0 GB/s |
| XDR800 port | 4 × 200 Gb/s = 800 Gb/s = 100.0 GB/s |
| RoCEv2 header | 58 B (22.66% at 256 B payload; 1.42% at 4 KB) |
| IB header (subnet) | 24 B (9.38% at 256 B payload) |
| Ring AllReduce wire/rank | 2·(n−1)/n · M (n=8, 100 MB → 175 MB; 3.53 ms at 50 GB/s) |
| 1,024-GPU 1:1 Clos (400G, radix 8) | 32 leaves + 32 spines; bisection 6.4 TB/s |

## The ten command groups
```text
# 1. RDMA state            rdma link; rdma resource; ibstat
# 2. IB fabric             ibdiagnet; ibnetdiscover; perfquery -G <port>
# 3. IB counters           perfquery -x -G  # symbols, link_downed, local/remote phys errors
# 4. IB partitions         P_Key via UFM/OpenSM (not a CLI one-liner — SM API)
# 5. RDMA throughput       ib_write_bw -d mlx5_0 -F -S 10   (F: force, S: size in MB… see perftest man)
# 6. RDMA latency          ib_write_lat / ib_read_lat (same flags)
# 7. NCCL throughput       all_reduce_perf -b 8 -e 8G -f 2 -g 8
# 8. NCCL diagnostics      NCCL_DEBUG=INFO NCCL_DEBUG_SUBSYS=NET <job>
# 9. GPU/NIC topology      nvidia-smi topo -m
#10. Eth/RoCE counters     ethtool -S <nic>   (PFC/ECN/CNP/drop counters)
```
Full labs: [53-learning-labs.md](./53-learning-labs.md).

## The three-way fabric decision (compressed)
| Question | InfiniBand | RoCEv2 | UET |
|---|---|---|---|
| Max mature HPC/AI performance today? | **yes** — proven, credit-lossless, adaptive routing, SHARP | high — after PFC/ECN/CC tuning | not yet at scale (spec, early silicon) |
| Need the Ethernet ops model? | no (SM, own tools) | **yes** | yes (Ethernet ecosystem) |
| PFC fundamental? | no (credits) | yes (engineering) | no (optional CBFC; lossy-capable) |
| Multipath? | adaptive routing (vendor) | ECMP (+MRC/spray, vendor) | **design core** (spray + reassembly) |
| Ecosystem risk | concentrated (NVIDIA) | broad, multi-vendor | broad, consortium-governed |
| When to pick | large synchronized training, HPC, SHARP value, IB ops expertise | Ethernet DC, multi-vendor, cloud, converged | new designs targeting open transport; watch vendor roadmaps [I: guidance] |

Full comparison: [49-design-decision-tree.md](./49-design-decision-tree.md).

## The final architecture (software over fabric)
```text
                 AI APPLICATION
                      │
       PyTorch / JAX / TensorFlow
                      │
           NCCL / RCCL / MPI / UCC
                      │
       ┌──────────────┼──────────────┐
       │              │              │
   InfiniBand       RoCEv2           UET
       │              │              │
   IB Transport     UDP/IP/ETH      UET (UDP 4793, PDC)
       │              │              │
   IB HCA (CX-7/9)  Ethernet NIC   UET NIC (early)
       │              │              │
   IB Fabric        AI Ethernet    Ultra Ethernet
  (Quantum/XDR)    (Spectrum-X,    (consortium fabric,
                     TH4/TH5, ...)  emerging)
```
Every layer above the wire is the **same verbs/collective model** — that is the whole
point of RDMA's existence: the fabric is swappable, the software is not. [I: standard]

## The five failure questions (troubleshooting spine)
1. **Which transport is actually running?** (NCCL log: NET/IB vs NET/Socket vs SHM) →
   [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md)
2. **Is the NIC–GPU pair local?** (`nvidia-smi topo -m`; SYS = cross-socket) →
   [37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md)
3. **Is the link at full speed/encoding?** (ibstat Speed/PhysicalState; ethtool Speed)
4. **Is congestion visible?** (PFC/ECN/CNP counters, queue occupancy) →
   [40-network-telemetry.md](./40-network-telemetry.md), `./45`–`./46`
5. **Is the path balanced?** (per-ECMP-member counters; per-rail NCCL busbw) →
   [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md)

## Key Takeaways
1. Five domains (scale-up, scale-out, front-end, storage, DCI) — never mix their SLOs.
2. Three fabrics (IB / RoCEv2 / UET) — same verbs, different loss & multipath philosophy.
3. Six numbers (port BW, header overhead, ring formula, Clos math) carry 80% of design.
4. Ten command groups carry 80% of daily ops.
5. Fabric choice = workload × ops model × vendor risk — the decision tree in [49-design-decision-tree.md](./49-design-decision-tree.md).

## Related
- [01-why-ai-networking-is-different.md](./01-why-ai-networking-is-different.md) — the "why" behind every box above.
- [49-design-decision-tree.md](./49-design-decision-tree.md) — the full decision framework.
- [51-complete-packet-journeys.md](./51-complete-packet-journeys.md) — the one chunk of gradient, three ways.
- [20-one-page-cheat-sheet.md](../GPU-Communication/20-one-page-cheat-sheet.md) — the software-side cheat sheet.
- [README.md](../Networking/README.md) — the one-page primer.

## References
- UEC Specification v1.0 (June 11, 2025) [F: ultraethernet.org spec].
- [E] all figures from the section constants bank (computed 2026-08-25).
- Command references: perftest (ofa), nccl-tests, ibdiagnet (NVIDIA), rdma(8) man.
