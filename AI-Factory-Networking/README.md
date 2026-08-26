# AI Networking: From RDMA to Gigascale Fabrics
`LAST_UPDATED: 2026-08-26 · Status: core section` · Claims tagged `[F]/[A]/[I]/[E]/UNVERIFIED`.
Section-level verified constants: see the [E] constants bank used across all pages (computed 2026-08-25).

> **What this section is.** An engineering-grade, zero-to-hero handbook of the networks that
> connect GPUs and accelerators: why AI traffic breaks classical Ethernet assumptions, the
> complete RDMA mental model, InfiniBand from PHY to Subnet Manager, RoCEv2 and lossless
> Ethernet (PFC/ECN/DCQCN), the major vendor AI-Ethernet fabrics (Spectrum-X, Arista Etherlink,
> Cisco, Juniper, merchant/Broadcom, cloud designs), the Ultra Ethernet/UET open transport,
> collective-communication workloads (training, MoE, disaggregated inference), fabric design
> mathematics (Clos/rail/multi-plane), performance measurement, troubleshooting, and
> production architecture.
>
> **Relationship to sibling sections:** `../GPU-Communication/` covers the *software* side of
> data movement (NCCL, NIXL, UCCL, NVSHMEM). This section covers the *fabric* side: the wires,
> the switches, the transports, the congestion control, and the topology math. Read
> [01-why-communication-matters.md](../GPU-Communication/01-why-communication-matters.md) first for the workload motivation,
> then come here. [README.md](../Networking/README.md) is the one-page primer.

## 30-Second Explanation
An AI cluster is a **synchronous, east-west, elephant-flow** machine. Thousands of GPUs
execute the same collective at the same instant; if any one of them waits on a packet,
every GPU sits idle — so **tail latency**, not average bandwidth, decides Job Completion
Time [I: standard systems argument]. Classical data-center Ethernet was built for
asynchronous, north-south, loss-tolerant TCP; AI traffic inverts every one of those
assumptions. The three answers to that mismatch are: **InfiniBand** (purpose-built lossless
fabric with credit flow control), **RoCEv2** (RDMA carried in UDP/IP over engineered
"lossless" Ethernet with PFC + ECN/DCQCN), and **Ultra Ethernet/UET** (a clean-slate
RDMA-inspired transport designed for multipathing, telemetry, and lossy-or-lossless
operation). On top sits the same software stack (NCCL/RCCL/MPI), the same topologies
(rail-optimized leaf-spine), and the same tuning problems (congestion, ECMP imbalance,
tail latency) — which is why this section teaches the fabric layer independently of the
communication library.

## The three questions this section answers
1. **What is on the wire?** — packet formats for InfiniBand, RoCEv2, and UET; header
   overhead [E]; flow control (credits vs PFC vs UET's optional CBFC/RCCC); congestion
   control (IB mechanisms, DCQCN, TCC, UET NSCC/RCCC). → Pages 03–04, 07–18, 25–27.
2. **How is the fabric built?** — Clos/fat-tree mathematics, rail-optimized and
   multi-plane topologies, oversubscription, scale-up vs scale-out, storage and DCI. →
   Pages 02, 19–24.
3. **How do you run it?** — benchmarking (perftest, nccl-tests, busbw/algbw),
   troubleshooting decision trees, K8s/Slurm integration, security, and the decision
   frameworks (when IB / when RoCE / when UET). → Pages 26–31, 28–31.

## The one-sentence taxonomy
```text
Scale-up (inside the rack/pod):
    NVLink/NVSwitch · NVL72 domain · UALink · Infinity Fabric · PCIe · CXL (context)
        → coherent-ish, P2P, ~1.8–3.6 TB/s per GPU, sub-µs, no routing
Scale-out (across racks):
    InfiniBand (NDR400/XDR800) · RoCEv2 (100/200/400/800GbE) · UET (emerging)
        → RDMA, leaf-spine, 50–100 GB/s per port, µs-scale, routed
Front-end / management:
    Kubernetes, Slurm, SSH, telemetry, DNS/DHCP, registry — separated from the backend
Storage:
    Lustre/GPFS/WEKA/VAST/DDN over 100–400GbE RDMA; GPUDirect Storage
DCI / multi-site:
    400ZR/800G ZR long-haul; WAN-scale RDMA is a different engineering problem
```

## Reading order
### Part A — Foundations (read first)
- [01 Why AI networking is different](./01-why-ai-networking-is-different.md) — the
  compute→network→JCT causal chain; AI vs traditional DC traffic; the vocabulary
  (stragglers, incast, elephant flows, low entropy, tail latency).
- [02 AI networking taxonomy](./02-ai-networking-taxonomy.md) — scale-up vs scale-out vs
  front-end vs storage vs DCI; NVLink/NVL72/UALink; leaf-spine sketch.
- [03 RDMA fundamentals](./03-rdma-fundamentals.md) — kernel bypass, zero-copy, PD/MR/QP/
  CQ/WQE/CQE, memory registration, the complete operation lifecycle.
- [04 RDMA operations & transports](./04-rdma-operations-and-transports.md) — SEND/RECV,
  RDMA WRITE/READ/WRITE-IMM, atomics; one-sided vs two-sided; RC/UC/UD/DC; IB vs RoCE vs
  iWARP.

### Part B — InfiniBand (the reference fabric)
- [05 InfiniBand architecture](./05-infiniband-architecture.md) — layers, node types,
  verbs→HCA→fabric path.
- [06 InfiniBand speed generations](./06-infiniband-speed-generations.md) — SDR→XDR,
  per-lane rates, encodings, 400G/800G.
- [07 InfiniBand addressing](./07-infiniband-addressing.md) — GUID/LID/GID, LRH vs GRH,
  routing within and across subnets.
- [08 InfiniBand queue pairs](./08-infiniband-queue-pairs.md) — QP states, SQ/RQ/CQ,
  doorbells, inline data, BlueFlame.
- [09 InfiniBand packet format](./09-infiniband-packet-format.md) — LRH/GRH/BTH/RETH/AETH/
  DETH/ICRC/VCRC, opcodes, header sizes.
- [10 InfiniBand flow control & QoS](./10-infiniband-flow-control-and-qos.md) — credit-based
  flow control, virtual lanes, SL/VL mapping, VL15.
- [11 InfiniBand subnet manager](./11-infiniband-subnet-manager.md) — OpenSM/UFM, LID
  assignment, discovery, SM failover, MAD/SMP/GMP.
- [12 InfiniBand routing, topology & partitions](./12-infiniband-routing-topology-partitions.md)
  — MinHop/Up-Down/DFSSSP, fat tree/Dragonfly/rail, P_Key partitioning.
- [13 InfiniBand congestion control & adaptive routing](./13-infiniband-congestion-adaptive-routing.md)
- [14 SHARP: in-network reduction](./14-sharp-in-network-reduction.md)
- [15 GPUDirect RDMA & NCCL over InfiniBand](./15-gpudirect-rdma-nccl-infiniband.md)

### Part C — RoCE & lossless Ethernet
- [16 RoCE fundamentals](./16-roce-fundamentals.md) — RoCEv1 vs v2, UDP:4791, the full
  packet, why routable.
- [17 Why RoCE is harder than ordinary Ethernet](./17-why-roce-is-harder.md) — retransmit
  cost, incast, microbursts, pause storms.
- [18 Data Center Bridging: PFC, ETS, DCBX](./18-data-center-bridging.md)
- [19 Why PFC can be dangerous](./19-why-pfc-is-dangerous.md) — storms, deadlock, watchdog.
- [20 ECN & WRED](./20-ecn-wred.md)
- [21 DCQCN: the RoCE congestion control](./21-dcqcn.md) — full control loop + parameters.
- [22 RoCE CC landscape & load balancing](./22-roce-cc-and-load-balancing.md) — TIMELY/HPCC/
  Swift, ECMP entropy, MRC, adaptive routing, reordering.
- [23 RoCE lossless fabric design](./23-roce-lossless-fabric-design.md) — the reference
  architecture: L3 leaf-spine + BGP + PFC + ECN + jumbo + rail.

### Part D — Vendors
- [24 Vendor landscape: who makes what](./24-vendor-landscape.md) — switch/ASIC/NIC/DPU/
  fabric roles; Broadcom merchant silicon; HPE/Dell/SONiC/AMD/Intel/Marvell.
- [25 NVIDIA Spectrum-X](./25-nvidia-spectrum-x.md) — SuperNIC, MRC, TCC, rail/multi-plane.
- [26 Arista Etherlink & EOS AI](./26-arista-etherlink.md)
- [27 Cisco AI Ethernet (Nexus/Silicon One)](./27-cisco-ai-ethernet.md)
- [28 Juniper AI fabric & Apstra](./28-juniper-ai-fabric.md)
- [29 Cloud AI fabrics: AWS EFA, Google TPU, Microsoft](./29-cloud-ai-fabrics.md)

### Part E — Ultra Ethernet / UET
- [30 Ultra Ethernet Consortium: why & what](./30-ultra-ethernet-consortium.md)
- [31 UET transport deep-dive](./31-uetch-deep-dive.md) — PDCs, spraying, RUD/ROD/RUDI,
  optional CBFC, lossy/lossless, LLR, profiles.
- [32 UET congestion control & in-network collectives](./32-uetch-congestion-and-in-network.md)

### Part F — Workloads, design, operations
- [33 Collective communication & parallelism](./33-collective-communication.md) — the seven
  primitives, ring AllReduce step-by-step, the parallelism→traffic table.
- [34 MoE and all-to-all](./34-moe-all-to-all.md)
- [35 Training vs inference networking; disaggregated inference](./35-training-vs-inference.md)
- [36 Communication libraries map](./36-communication-libraries.md) — NCCL/RCCL/MPI/UCX/UCC/
  NVSHMEM/NIXL/libfabric placement in the stack.
- [37 NIC, HCA, SuperNIC & DPU; GPU-to-NIC topology](./37-nic-hca-supernic-dpu.md)
- [38 Rail-optimized & multi-plane fabrics](./38-rail-optimized-multi-plane.md)
- [39 Buffer architecture](./39-buffer-architecture.md)
- [40 Network telemetry](./40-network-telemetry.md)
- [41 Physical layer: DAC/AOC/fiber, PAM4, FEC, 400/800/1.6T](./41-physical-layer.md)
- [42 Clos/fat-tree design mathematics](./42-clos-fat-tree-math.md) — formulas + worked
  examples 32→32,768 GPUs [E].
- [43 Network bandwidth calculations](./43-network-bandwidth-calculations.md)
- [44 Performance metrics & benchmarking](./44-performance-metrics-benchmarking.md)
- [45 Troubleshooting RDMA & InfiniBand](./45-troubleshooting-rdma-infiniband.md)
- [46 Troubleshooting RoCE & NCCL](./46-troubleshooting-roce-nccl.md) — symptom→cause→
  validation→remediation tables.
- [47 Security & multi-tenancy](./47-security-multitenancy.md) — P_Key, VLAN/VRF, SR-IOV,
  exposing RDMA to tenants safely.
- [48 Kubernetes & Slurm for AI fabrics](./48-kubernetes-slurm.md)
- [49 Design decision tree & when-to-choose](./49-design-decision-tree.md) — IB vs RoCE vs
  UET, with the full comparison table.
- [50 AI networking myths](./50-ai-networking-myths.md) — ten common misconceptions,
  refuted with the numbers.
- [51 Complete packet journeys](./51-complete-packet-journeys.md) — one gradient chunk,
  three fabrics: InfiniBand, RoCEv2, UET.
- [52 Reference architectures](./52-reference-architectures.md) — 32 / 256 / 1,024-GPU
  designs, four fabric options compared.
- [53 Learning labs](./53-learning-labs.md) — 16 hands-on labs, beginner→advanced.
- [54 Interview & design questions](./54-interview-design-questions.md) — 100 questions +
  answers; 7 architecture exercises with solutions.
- [55 Cheat sheet & final architecture](./55-cheat-sheet.md)
- [EVALUATION — evaluator pass & adjudication](./EVALUATION.md)

## Section-level claims to keep straight (recurring conventions)
- **GB/s = bytes** (10^9), **Gb/s = bits** (10^9); ×8 to convert. The constants bank states
  units per row; carry the unit into your text.
- **IB nominal port rates:** NDR400 = 4×100 Gb/s = 400 Gb/s = 50.0 GB/s; XDR800 =
  4×200 Gb/s = 800 Gb/s = 100.0 GB/s (per-lane IBTA rates [F: IBTA]; ×4 lanes [E]).
  IB line codes: 8b/10b (SDR/DDR/QDR), 64b/66b (FDR/EDR), PAM4 256b/257b + RS-FEC
  (HDR/NDR/XDR) — **not** 128b/132b, which is an Ethernet line code [F: IBTA/Wikipedia].
- Header overhead [E] (denominator = payload bytes, stated once for the whole section):
  RoCEv2 = 58 B/packet (14+20+8+12+4) → 22.66% at 256 B, 1.42% at 4 KB;
  IB within-subnet = 24 B/packet (LRH 8 + BTH 12 + ICRC 4) → 9.38% at 256 B.
- Ring AllReduce wire traffic per rank = 2·(n−1)/n · M [E]; AllGather = (n−1)/n · M.
- busbw(AllReduce) = algbw × 2(n−1)/n [E] (nccl-tests *definition*); at ring saturation a
  healthy ring's busbw ≈ **0.95 × link (× rails)** — the *target*, not `2(n−1)/n × link`
  (that product would exceed the link itself).
- Production/announced/roadmap distinctions: anything UET-flavored is **spec/early-silicon**
  as of 2026-08-25 unless a vendor page says otherwise [F: UEC + vendor announcements].
