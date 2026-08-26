# AI Networking Taxonomy
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: NVIDIA NVLink/NVL72 pages, UALink Consortium (200G 1.0 spec, Apr 2025), CXL Consortium, AMD MI300/MI350 docs, Lustre/WEKA docs; fetched 2026-08-25.

## 30-Second Explanation
An AI factory is **not one network**. It is five networks with five different SLOs, and
confusing them is the #1 source of both cost waste and outages:
**(1) scale-up** (rack/pod, sub-µs, NVLink/UALink/PCIe), **(2) scale-out backend**
(cross-rack, µs, IB/RoCE/UET — the one this section teaches in depth), **(3) front-end /
management** (K8s/Slurm/SSH/telemetry), **(4) storage** (parallel FS over RDMA Ethernet),
and **(5) DCI / multi-site** (long-haul, ms RTT — a different engineering problem).
The scale-up vs scale-out split is the most consequential: with NVL72, **the 72-GPU rack
is now the atomic unit of collective communication**, and "the backend fabric" only sees
rack-to-rack traffic. Designing either side without knowing the other's boundary is how
people end up buying 10× the fabric they need — or 0.1× what they need.

## The five domains, precisely
```text
┌─────────────────────────────────────────────────────────────────────────┐
│  RACK / POD (scale-up domain)                                           │
│  8× GPU (HGX) or 72× GPU (NVL72)  + NVLink/NVSwitch                     │
│  ┌─────────────┐  PCIe  ┌──────────────────┐                            │
│  │  CPU host(s)│◄──────►│  NICs (one/GPU)  │                            │
│  └─────────────┘        └──────────────────┘                            │
└──────────────┬───────────────────────┬───────────────────────┬─────────┘
     scale-out │ (IB/RoCE/UET)        │ front-end               │ storage
                ▼                     ▼                         ▼
        Leaf ─ Spine ─ Leaf     K8s/Slurm/telemetry      Lustre/WEKA/VAST/DDN
        (backend fabric)         (mgt fabric, L2/L3)       (RDMA Ethernet, 100-400G)
                │
                ▼  (optional, between sites)
         DCI: 400ZR/800G ZR, ms RTT, WAN-scale CC
```

### 2.1 Scale-up network (inside the domain)
| Interconnect | Status 2026-08 | Per-endpoint BW | World size | Notes |
|---|---|---|---|---|
| **NVLink 4 (H100)** | shipping | 900 GB/s bidir/GPU (18 links × 50 GB/s) [F: vendor spec] | 8 (HGX) / NVSwitch 7.2 TB/s | PAM4 100 Gb/s/lane [F] |
| **NVLink 5 (Blackwell)** | shipping | 1.8 TB/s bidir/GPU (18 × 100 GB/s) [F: vendor spec] | **NVL72: 72 GPUs, 130 TB/s aggregate** [F: vendor spec] | 130 TB/s ≈ 72 × 1.8 [E: reconcile] |
| **NVLink 6 (Vera Rubin)** | announced | 3.6 TB/s bidir/GPU [F: vendor spec — roadmap] | NVL72-class, 260 TB/s switch [A] | NOT shipping as of 2026-08 |
| **NVLink-C2C** | shipping | 900 GB/s chip-to-chip (Grace↔GPU) [F: vendor spec] | 1–2 chips | coherent, 450 GB/s per direction on GB200 [F] |
| **UALink 200G 1.0** | spec (Apr 2025); no silicon yet [F: consortium] | 800 Gb/s (= 100 GB/s) per x4 station (200 GT/s/lane) [E: 800 Gb/s ÷ 8] | up to 1,024 accelerators | open memory-semantic interconnect; first parts expected 2026/27 [A] |
| **AMD Infinity Fabric (xGMI)** | shipping | MI350X: 7 links × 128 GB/s ≈ 896 GB/s [F: vendor spec] | **8 GPUs (UBB8)** — NOT rack-scale [F] | rack-coherent scale-up comes via UALink-over-Ethernet (UALoE, MI400+) [A] |
| **PCIe 5.0 x16** | shipping | ~63 GB/s one-way [E] | per-host | P2P non-coherent; ACS/IOMMU caveats → [37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md) |
| **CXL 2.0/3.x** | early shipping (memory devices) | n/a (memory, not collectives) | host-centric | **memory expansion/pooling, NOT a collective fabric** [I: analysis — no primary "CXL cannot do collectives" statement exists] |

```text
Scale-up example — the NVL72 domain:

  GPU ─┐
  GPU ─┤
  ...  │
  GPU ─┤── NVSwitch trays (9 trays × 2 NVSwitch5 ASICs, 130 TB/s) [F]
  GPU ─┤
  GPU ─┘
        1 NVLink switch hop to any GPU in the rack; all-to-all, non-blocking;
        P2P atomics + symmetric memory (NVSHMEM over NVLink)
```
**Why it differs from scale-out:** scale-up is *memory-semantic* (load/store/atomic,
symmetric HBM, sub-µs, credit/P2P flow control, no routing), sized at ~1.8–3.6 TB/s
per endpoint; scale-out is *message-semantic* RDMA (verbs, µs, routed, ~50–100 GB/s per
port). The ratio is 20–70× — which is why tensor parallelism lives on scale-up and data
parallelism on scale-out, and why "NVLink replaces the backend" is a myth (see
[50-ai-networking-myths.md](./50-ai-networking-myths.md)). [I: standard]

### 2.2 Scale-out / backend network
The GPU↔GPU fabric across racks. Carries: NCCL/RCCL collectives, MPI/SHMEM,
tensor-parallel (rarely, cross-domain), expert-parallel all-to-all, pipeline activations,
data-parallel gradients, and — for disaggregated inference — KV-cache movement.
Technologies: **InfiniBand** (NDR400/XDR800), **RoCEv2** (100–800GbE), **UET**
(spec 1.0, 2025; early silicon), plus cloud-proprietary (EFA/SRD). → Parts B–E of this
section.

```text
GPU Server
   │
NIC / HCA / SuperNIC          (one per GPU, rail-optimized)
   │
Leaf
   │
Spine
   │
Leaf
   │
NIC / HCA
   │
GPU Server
```

### 2.3 Front-end / management network
Kubernetes/Slurm control plane, SSH, APIs, telemetry export, container registry,
provisioning, DNS/DHCP. **Always separate** from the backend: (a) a backend congestion
event must never take down the plane you use to debug it; (b) management traffic is
asynchronous and latency-tolerant → cheap, oversubscribed L2/L3; (c) blast-radius
isolation (a bad K8s update cannot wedge the fabric). Typical: 25–100 GbE per node,
separate VRF/VLAN or physically separate switch set. [I: standard practice]

### 2.4 AI storage network
Dataset streaming (TB/s aggregate reads), checkpoints (bursts, see numbers below),
model/optimizer state, log aggregation. Technologies: **NFS** (fine for small clusters;
metadata-bound at scale), **parallel filesystems** (Lustre, GPFS/Spectrum Scale, BeeGFS,
WEKA, VAST, DDN EXAScaler, PowerScale OneFS), object stores (cold data).
Fabric: 100–400GbE with RDMA where the FS supports it; **GPUDirect Storage** moves data
NIC↔GPU HBM directly (kernel-bypass + registered memory + P2P) → [37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md).
Checkpoint math [E: constants bank]: a 100B-param model's Adam state (BF16 weights +
FP32 master + FP32 m/v + BF16 grads) ≈ **1.6 TB**; writing it in 60 s needs **~27 GB/s
(213 Gb/s)** of *aggregate* storage fabric — one 400GbE link group, and that's before
the ZeRO sharding (÷1024 ranks → 1.56 GB/rank, but all ranks write *simultaneously*:
incast on the storage fabric). This is why storage gets its own fabric (or its own
plane) with sized buffers. [I: standard design consequence]

### 2.5 AI data-center interconnect (multi-site)
Different problem class entirely: **RTT is ms, not µs; loss is real; bandwidth is the
scarce resource, not the design variable.** 400G-ZR (IEEE 802.3df, 400 Gb/s over a single
fiber, duplex pair, ~120 km reach [F: 802.3df]) and 800G-class ZR optics for cluster↔cluster; PAM4 at 200 Gb/s
per lane. Why LAN-scale RDMA ≠ WAN RDMA: a RoCE retransmission over 1 ms RTT costs ~100×
what it costs over 10 µs; CC windows must span ms-scale RTT; FEC + distance eat BW.
Multi-site *training* (FSDP sync over WAN) is latency-dominated: a 100 GB ring AllReduce
over 100 GbE with n=1024 ranks at 1 ms RTT ≈ 18.0 s (2.0 s latency + 16.0 s bandwidth) vs
10 ms RTT ≈ 36.4 s (20.5 s + 16.0 s) [E: constants bank WAN rows]
— i.e. WAN sync turns steps into tens of seconds; multi-site today is mainly *inference* (cheap
capacity) and *checkpoint replication*, not synchronized training. [I: standard]

## Design rules that follow
1. **Never share the backend and front-end fabric** (logical minimum; physical preferred).
2. **Storage gets its own buffers**: checkpoint incast must not PFC-stall the training
   fabric even if they share a switch chassis (separate TCs/queues, separate buffers).
3. **Scale-up world size sets the parallelism plan**: TP inside NVL72; EP/PP/DP across it.
   The fabric design must match that split, not fight it. → [33-collective-communication.md](./33-collective-communication.md)
4. **DCI is a planning item, not a tuning item**: RTT, not CC parameters, sets the
   outcome. → [49-design-decision-tree.md](./49-design-decision-tree.md)
5. **Telemetry must cross all five domains**: a backend P99 spike is often a storage
   checkpoint burst on a shared switch, or a front-end telemetry collector's own traffic.
   → [40-network-telemetry.md](./40-network-telemetry.md)

## How to measure which domain is which
`nvidia-smi topo -m` (scale-up/PCIe topology), `ibstat`/`rdma link` (scale-out),
`ip link`/`ss` (front-end/storage), `ethtool` on the DCI uplinks (optics, BER/FEC
counters). One command per domain — and when a symptom appears, the first job is
identifying *which* domain it lives in. → [55-cheat-sheet.md](./55-cheat-sheet.md) (command groups).

## Key Takeaways
1. Five domains, five SLOs; the backend is the only one where tail latency is the KPI.
2. NVL72 made the 72-GPU rack the atomic collective unit; scale-out now spans racks.
3. UALink 1.0 (800 Gb/s = 100 GB/s per x4 station, 1024 endpoints) is the open scale-up challenger — spec-only
   silicon status as of 2026-08; AMD's rack-coherent scale-up arrives via UALoE (announced).
4. CXL is memory, not collectives; PCIe P2P is non-coherent with real caveats.
5. Storage and DCI are separate engineering problems with separate math.

## Related
- [01-why-ai-networking-is-different](./01-why-ai-networking-is-different.md) — the traffic properties these domains must absorb.
- [15-gpudirect-rdma-nccl-infiniband](./15-gpudirect-rdma-nccl-infiniband.md) — how the scale-out NICs talk to the scale-up world.
- [38-rail-optimized-multi-plane](./38-rail-optimized-multi-plane.md) — the scale-out topology patterns.
- [03-gpu-network-architecture](../GPU-Communication/03-gpu-network-architecture.md) — physical topology ladder.
- [Hardware/README](../Hardware/README.md) — the silicon the domains are built from.
- [55-cheat-sheet](./55-cheat-sheet.md) — one command per domain.

## References
- NVIDIA NVLink page, GB200 NVL72 page, NVLink-C2C page [F: vendor spec, fetched 2026-08-25].
- UALink Consortium: 200G 1.0 spec overview + roadmap (April 2025 / April 2026) [F].
- CXL Consortium: 2.0/3.0 spec summaries [F].
- AMD MI350X/MI355X product pages [F: vendor spec].
- [E] constants from the section bank (computed 2026-08-25).
