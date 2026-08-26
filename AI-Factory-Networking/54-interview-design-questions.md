# Interview & Design Questions (100 Q + Answers; 7 Design Exercises)
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: mirrors the section's research bank (DCQCN SIGCOMM'15, UEC 1.0, MRC, nccl-tests, IBTA); all [E] from the constants bank (2026-08-25).

## 30-Second Explanation
One hundred questions in four tiers — **20 Beginner, 30 Intermediate, 30 Advanced, 20
Architect Scenario** — followed by a separate **Answers** section, then **7 Design
Exercises** with solution sketches. The questions are written first and numbered
continuously 1–100 so you can quiz yourself without peeking. Answers are 2–6 sentences,
technically specific, and claim-tagged where they carry a load-bearing number (mostly
`[E]` from the constants bank). The design exercises are the "show me you can engineer"
capstone: scenario, requirements, then a reasoned solution sketch. Pair these with
the one-page mental model in [55-cheat-sheet.md](./55-cheat-sheet.md).

```text
100 QUESTIONS (four tiers)
  Tier 1  BEGINNER    (1-20)   "what is a QP / PFC / GUID-LID / incast..."
  Tier 2  INTERMEDIATE(21-50)  "DCQCN loop / WRED / ECMP entropy / rail..."
  Tier 3  ADVANCED    (51-80)  "credit-loop / MRC reorder / WAN AR time..."
  Tier 4  SCENARIO    (81-100) "4k-GPU fabric / PFC postmortem / 10k design..."
         + 7 DESIGN EXERCISES with solution sketches
         + ANSWERS to all 100 (claim-tagged [F]/[A]/[I]/[E])
```

## The Question Set

### Tier 1 — BEGINNER (1–20)
1. What is a Queue Pair (QP)?
2. How do credit-based flow control and PFC differ as lossless mechanisms?
3. What are GUID and LID in InfiniBand?
4. What wire traffic does a ring AllReduce move per rank (formula)?
5. What is the purpose of PFC?
6. Which UDP port does RoCEv2 use, and why does that matter for load balancing?
7. When is NVLink the right answer vs PCIe?
8. What is incast and why is it dangerous on a shallow-buffer network?
9. What are jumbo frames and why does RoCE want them?
10. What is the difference between RC, UC, and UD transports?
11. What problem does RDMA solve, and what are kernel bypass and zero-copy?
12. What is a GID and how does RoCE addressing differ from IB's LID?
13. What is an elephant flow?
14. What is a collective (AllReduce / AllGather)?
15. What is GPUDirect RDMA at a high level?
16. Why does tail latency matter more than average for AI training?
17. What is MTU, and what happens when two ends disagree?
18. What is a leaf-spine (Clos) topology and why do AI fabrics use it?
19. What is the difference between a NIC and an HCA?
20. Why can't AI just run on TCP?

### Tier 2 — INTERMEDIATE (21–50)
21. Describe the DCQCN congestion loop: roles, alpha, and CNP.
22. What are WRED thresholds (Kmin/Kmax/Pmax) and how do they interact with PFC?
23. Why is ECMP entropy a problem for RoCEv2, and what raises it?
24. What is a PFC watchdog?
25. What is rail optimization?
26. What does GPUDirect RDMA require at the host level (IOMMU, ACS, peermem, NUMA)?
27. Define algbw vs busbw and give the AllReduce relation.
28. What is a GID index, and how does it separate RoCEv1 from RoCEv2?
29. What is a P_Key, and how does it differ from a VLAN?
30. What are SL and VL in InfiniBand, and how are they mapped?
31. What is SHARP, and where does the reduction happen?
32. What is MRC (as a transport)?
33. What are UET PDCs and RUD?
34. What is LLR (link-level retransmission)?
35. How does UET's NSCC differ from DCQCN?
36. How long does it take to ship a 4K-token KV cache for 70B GQA at 50 GB/s? [E]
37. How long to write a 100B-parameter checkpoint including BF16 grads, and at what rate if
    the budget is 60 s? [E]
38. How do you size buffer/PFC headroom on a lossless port?
39. What is DSCP→TC mapping, and why is it load-bearing for RoCE?
40. Does RoCEv1 route across subnets? Does RoCEv2?
41. What are ECT and CE in ECN, and how are they set?
42. Why does RDMA want a (near-)lossless network (Go-Back-N)?
43. What is DCBX and what does it negotiate?
44. What is a CNP and which DSCP does it travel on by default?
45. How does NCCL choose between ring and tree?
46. What is oversubscription, and why is 1:1 preferred for the GPU backend?
47. What is a straggler, and how does it couple to percentiles?
48. What is GPUDirect Storage?
49. What does `NCCL_IB_HCA` control?
50. What is jitter, and why does it matter more than average latency?

### Tier 3 — ADVANCED (51–80)
51. How do you avoid a credit/pause loop (PFC deadlock) end-to-end?
52. What does adaptive routing's out-of-order delivery require of the end transport?
53. What is a "DC transport" and what extra machinery does it add over plain RoCE?
54. How can PFC deadlock, and how is it broken?
55. How do you set ECN and PFC thresholds so they don't fight?
56. How does MRC bound reordering (Max PSN Range)?
57. What do UET's MP_RANGE and SACK mechanisms solve?
58. How does incast recovery differ between PFC/DCQCN and UET-style approaches?
59. Time a ring AllReduce of 100 GB across 1,024 ranks at RTT 1 ms vs 10 ms. [E]
60. Quantify a +20% MoE routing skew hitting one node's dispatch NIC. [E]
61. What happens to MoE all-to-all when the fabric is 2:1 oversubscribed? [E]
62. What is a multi-plane failure domain, and why does rail isolation help?
63. Where is P_Key enforced vs 802.1Q VLAN?
64. What isolation does SR-IOV give an RDMA tenant (per-VF)?
65. How do you diagnose NCCL silently falling back to sockets?
66. What are the 1,024-GPU single-plane vs multi-plane design tradeoffs?
67. What is a 1.6T PHY and what FEC/line code does it use? [E]
68. Give the goodput-vs-throughput header math for RoCEv2.
69. Why does DCQCN start near alpha ≈ 1.0, and how does alpha converge?
70. What is head-of-line blocking, and how does PFC create it?
71. How does an ECN/PFC threshold misalignment cause pause storms?
72. Contrast RTT-based CC (TIMELY) with ECN-based CC (DCQCN).
73. What is a flowlet, and how does flowlet spraying fix ECMP imbalance?
74. How do you compute bisection bandwidth of a 2-tier Clos?
75. What is the networking need for sequence/context parallel (CP)?
76. How does disaggregated inference ship KV cache, and what is the timing budget?
77. When is a 400G or 800G NIC PCIe-bound? [E]
78. Where does SHARP reduce, versus endpoint NCCL reduction?
79. How does NCCL stripe across rails, and what breaks striping?
80. What is the PFC headroom arithmetic per link-direction?

### Tier 4 — ARCHITECT SCENARIO (81–100)
81. Choose a fabric for a 4,096-GPU training cluster.
82. Plan a RoCE migration from a legacy Ethernet DC.
83. What would you pilot for UET adoption in 2027?
84. Run a PFC storm postmortem.
85. Build the case for or against 2:1 oversubscription for an AI backend.
86. Split storage and compute fabrics — or not?
87. Design isolation for a multi-tenant GPU cloud.
88. Design the KV-transfer path for disaggregated inference.
89. Plan IB Subnet Manager disaster recovery.
90. Do capacity planning from a JCT SLO.
91. Compare the cost/ops model of IB vs Ethernet.
92. Manage vendor lock-in risk.
93. Choose rail vs flat for 1,024 GPUs.
94. Sketch a greenfield 10,000-GPU design.
95. Justify a hybrid IB + Ethernet DC.
96. Triage a performance regression.
97. Design a benchmarking methodology for a new cluster.
98. Set a fabric telemetry SLO.
99. Assess NCCL upgrade risk.
100. Plan an 800G migration.

---

## Answers

### Tier 1 answers (1–20)
1. **QP** — a Queue Pair is the basic endpoint of RDMA communication: one Send Queue + one
   Receive Queue (+ one associated Completion Queue/CQ), identified by a QPN locally. All
   RDMA ops (SEND/RECV, WRITE, READ, atomics) are posted as Work Requests into the QP and
   completed via CQEs. [A] [08-infiniband-queue-pairs.md](./08-infiniband-queue-pairs.md)
2. **Credits vs PFC** — InfiniBand uses per-VL credit flow control: a sender may only send
   frames for credits the receiver has granted, so loss is impossible by construction and
   the pause is end-to-end/arbitrary-fine. PFC (IEEE 802.1Qbb) is hop-by-hop per-priority
   *pause frames* on Ethernet, sent between adjacent switches/NICs; it buys losslessness but
   propagates back-pressure and can head-of-line-block / deadlock. [A] [10-infiniband-flow-control-and-qos.md](./10-infiniband-flow-control-and-qos.md),
   [18-data-center-bridging.md](./18-data-center-bridging.md)
3. **GUID/LID** — a GUID is a globally unique 64-bit identifier for a device/port (like a
   MAC); the LID is a 16-bit locally assigned address given by the Subnet Manager within a
   subnet and used for L2 forwarding. Subnet-local routing keys off LID; cross-subnet uses
   the GID/GID-based GRH. [A] [07-infiniband-addressing.md](./07-infiniband-addressing.md)
4. **Ring AllReduce** — traffic per rank = `2(n-1)/n × M` total over its two phases
   (reduce-scatter + all-gather); the `2(n-1)/n` factor is the bandwidth-efficiency tax, and
   `[E] busbw = algbw × 2(n-1)/n`. For n=8, 100 MB → `[E] 175 MB/rank`. [E] [33-collective-communication.md](./33-collective-communication.md)
5. **PFC purpose** — to make a lossless class-of-service: when a receive buffer is about to
   overflow, the upstream device is paused (XOFF) then resumed (XON) so no frames drop in
   that priority. This lets loss-sensitive RDMA (RC's Go-Back-N) run at full rate instead of
   collapsing on loss. [A] [18-data-center-bridging.md](./18-data-center-bridging.md), [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md)
6. **UDP 4791, fixed** — RoCEv2 encapsulates IB in UDP/IP and uses destination port 4791,
   which is the same for every flow; therefore ECMP/hashing sees (src ip, dst ip, src UDP
   port) only — the entropy must come from varying the *source* port per QP. `[E] 4791` [F:
   IANA/IBTA]. [16-roce-fundamentals.md](./16-roce-fundamentals.md), [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md)
7. **NVLink vs PCIe** — NVLink is the coherent high-bandwidth scale-up link on the GPU die
   (e.g. `[F: vendor]` H100 NVLink 4.0 ≈ 900 GB/s bidir), used within a node/domain; PCIe is
   the general-purpose I/O bus (`[E]` Gen5 x16 ≈ 63 GB/s one-way) through which NICs attach.
   Use NVLink for GPU↔GPU / intra-domain; PCIe for NIC (scale-out) and storage attach. [E][F]
   [02-ai-networking-taxonomy.md](./02-ai-networking-taxonomy.md), [37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md)
8. **Incast** — many-to-one traffic: N senders converge on one receiver's single link, which
   can absorb only its own line rate; the surplus queues in shallow buffers and drops, forcing
   Go-Back-N retransmit and tail-latency spikes. AI collectives (all-gather, AllToAll) are
   synchronized incast. [I][E] [17-why-roce-is-harder.md](./17-why-roce-is-harder.md), [33-collective-communication.md](./33-collective-communication.md)
9. **Jumbo frames** — MTU 9000 (vs 1500) frames amortize the fixed per-packet header and cut
   the PPS demand on switch/NIC. For RoCE `[E]` the 58 B header is ~3.87% of a 1500 B payload
   but ~1.42% at 4096 B payload — and PPS ceilings (`[E] 400GbE @9018B = 5.54 Mpps` vs `[E]
   32.94 Mpps @1518B`) favor big frames. [E] [41-physical-layer.md](./41-physical-layer.md), [16-roce-fundamentals.md](./16-roce-fundamentals.md)
10. **RC/UC/UD** — RC (Reliable Connection) is connected, in-order, ACKed, lossless-optimized
    (what training uses). UC (Unreliable Connection) is connected but no ACKs/reliability. UD
    (Unreliable Datagram) is connectionless and multicast-capable, good for things like
    MPI/control but not data transfer. [A] [04-rdma-operations-and-transports.md](./04-rdma-operations-and-transports.md)
11. **RDMA** — Remote Direct Memory Access lets one host read/write another's memory without
    the remote CPU; *kernel bypass* (verbs go straight to the HCA) and *zero-copy* (DMA
    directly from user buffers) remove the CPU from the data path, giving low latency and
    near-zero CPU per byte. [A] [03-rdma-fundamentals.md](./03-rdma-fundamentals.md)
12. **GID vs LID** — GID is a 128-bit address (an EUI-64 + subnet prefix) used in the GRH for
    cross-subnet routing; the LID is a 16-bit subnet-local L2 address. RoCE replaces the
    IB L2 with Ethernet: RoCEv1 rides the L2 frame (non-routable), RoCEv2 rides UDP/IP and
    uses IP addresses as its "GID-equivalent." [A] [07-infiniband-addressing.md](./07-infiniband-addressing.md),
    [16-roce-fundamentals.md](./16-roce-fundamentals.md)
13. **Elephant flow** — a long-lived, high-volume flow (a GPU collective is the canonical
    case). A few elephants can saturate a link and, hashed into ECMP, cause severe imbalance;
    AI fabrics are mostly elephant flows, unlike web'd mouse flows. [I] [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md)
14. **Collective** — a communication primitive across N ranks: AllReduce (reduce + broadcast
    result to all), AllGather (everyone gets everyone's data), ReduceScatter (reduce then
    scatter shards). NCCL implements these; the traffic math is in [33-collective-communication.md](./33-collective-communication.md).
15. **GPUDirect RDMA (GDR)** — allows a NIC to RDMA-read/write GPU memory directly
    (peer-to-peer over PCIe) without staging through host RAM/CPU, cutting latency and CPU
    usage. Requires the NIC on the GPU's PCIe tree and `nvidia-peermem`, with IOMMU/ACS
    disabled. [F: NVIDIA] [15-gpudirect-rdma-nccl-infiniband.md](./15-gpudirect-rdma-nccl-infiniband.md)
16. **Tail latency** — a synchronized training step waits for the *last* rank; the median
    hides one straggler. Provisions of +1 µs tail × `2(n-1)` ring steps × many AllReduces add
    milliseconds of step time, so tail (P99/P99.9), not average, drives JCT. [I]
    [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md)
17. **MTU** — maximum transmission unit; on mismatch a QP never establishes ("Invalid MTU") or
    frames drop. IB fabrics must agree on MTU (commonly 2048/4096), RoCE on 1500 or 9000.
    Verify both ends before trusting a benchmark. [I] [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md)
18. **Leaf-spine (Clos)** — a multistage topology where leaves connect hosts and every leaf
    wires to every spine, giving multiple equal-cost paths and non-blocking bisection. AI
    fabrics want `[E]` oversub = 1.0 (bisection ≥ inject) because synchronized collectives
    saturate the cut. [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md)
19. **NIC vs HCA** — a NIC (network interface card) is the generic Ethernet adapter; an HCA
    (Host Channel Adapter) is the InfiniBand-specific adapter implementing verbs (QP/CQ)
    directly in silicon. Modern RDMA Ethernet NICs (ConnectX, BlueField) are effectively
    HCA-class. [A] [37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md)
20. **Why not TCP** — TCP's in-kernel stack, per-byte CPU, ACK processing, and loss recovery
    (slow start) can't reach RDMA's near-line-rate low-CPU goodput; and AI needs µs tail
    latency. RDMA moves data in the HCA's silicon, freeing CPU for compute. [I][E]
    [03-rdma-fundamentals.md](./03-rdma-fundamentals.md)

### Tier 2 answers (21–50)
21. **DCQCN loop** — three roles: the *congestion point* (switch) WRED-marks ECN-CE on
    RoCE packets as queue depth crosses Kmin→Kmax; the *notification point* (receiver NIC)
    sends a CNP back to the sender; the *reaction point* (sender NIC) tracks **α** (fraction
    marked), and on CNP cuts rate multiplicatively by `(1 − α/2)`, additively recovering
    when no CNP arrives. α starts ~1.0 and converges as marking subsides. [A/F]
    [21-dcqcn.md](./21-dcqcn.md)
22. **WRED thresholds** — Kmin is where ECN marking starts, marking probability ramps
    linearly to Pmax at Kmax, *before* the queue hits the PFC XOFF threshold. If Kmax > PFC
    pause threshold, ECN never fires before pause → pause storms; if Kmin too low, premature
    throttling. They must be set with PFC *as the backstop*. [I][A] [20-ecn-wred.md](./20-ecn-wred.md)
23. **ECMP entropy** — RoCEv2's dst UDP port is fixed (`[E] 4791`), so ECMP hashes on
    (src/dst IP, src UDP port) and few distinct QPs produce few distinct hashes → many
    elephants collide on one member ("polarization"). Fixes: vary the per-QP UDP *source*
    port [F: mlx5dv_modify_qp_udp_sport], SL/hash seeds, flowlet/adaptive spraying. [A/I]
    [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md)
24. **PFC watchdog** — a vendor/switch feature that detects a pause asserted for too long (a
    stuck no-drop queue) and forcibly drops/disables the offender to break a pause storm. It
    is *not* an IEEE standard (PFC is 802.1Qbb; 802.1Qau = QCN, a different thing). [A]
    [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md)
25. **Rail optimization** — giving each GPU its own dedicated "rail" (plane of the fabric,
    e.g. GPU i → rail i), so intra-collective traffic from one rank never contends on shared
    up/downlinks. With K rails, bisection scales ×K and a rail failure degrades 1/K.
    [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md)
26. **GDR host prerequisites** — NIC must sit on the GPU's PCIe tree (same socket; check
    `nvidia-smi topo -m`), `nvidia-peermem` loaded, IOMMU off or pass-through, PCIe ACS
    disabled on the root/switch (or peer enabled), and sufficient BAR1. A GPU↔NIC `SYS`
    distance halves effective GDR. [F: NVIDIA] [15-gpudirect-rdma-nccl-infiniband.md](./15-gpudirect-rdma-nccl-infiniband.md),
    [37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md)
27. **algbw vs busbw** — algbw is raw algorithm throughput (messages bytes/sec the collective
    moves as orchestrated); busbw is the *effective per-GPU fabric bandwidth*, the number that
    says "how well the fabric is used." For AllReduce `[E] busbw = algbw × 2(n-1)/n`. [F:
    nccl-tests PERFORMANCE.md] [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md)
28. **GID index** — each GID (address) is found at an index in the port's GID table; index 0
    is typically RoCEv1 link-local (non-routable), a global/unicast index (e.g. 3) is
    RoCEv2. Using the wrong index breaks/hangs cross-subnet traffic. Exact indexes are NIC/
    config-specific (`NCCL_IB_GID_INDEX`, perftest `-x`). [I][A] [16-roce-fundamentals.md](./16-roce-fundamentals.md),
    [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md)
29. **P_Key vs VLAN** — both create isolation broadcast domains, but P_Key is enforced
    *end-to-end by the CA/NIC* (a port only passes traffic whose P_Key it holds, in the IB
    data plane), whereas an 802.1Q VLAN is a frame-tag enforced by switches. IB P_Keys are
    managed by the SM; VLANs by the Ethernet control plane. [A] [12-infiniband-routing-topology-partitions.md](./12-infiniband-routing-topology-partitions.md),
    [47-security-multitenancy.md](./47-security-multitenancy.md)
30. **SL/VL** — Service Level (SL) is a 4-bit QoS label a packet carries; it maps to a
    Virtual Lane (VL), a separate buffering/flow-control lane on a link carrying its own
    credit pool. SL→VL mapping (plus VL15 for management) lets one link carry isolated QoS
    classes. [A] [10-infiniband-flow-control-and-qos.md](./10-infiniband-flow-control-and-qos.md)
31. **SHARP** — Sharp/In-Network Aggregation reduces data *inside the switch* as it passes
    (e.g. AllReduce sum by the fabric), so endpoints ship less and the switch does the reduce.
    Cuts both bandwidth and latency versus endpoint-only NCCL. [14-sharp-in-network-reduction.md](./14-sharp-in-network-reduction.md)
32. **MRC** — Multi-Path Reliable Connection: an endpoint (NIC) transport built on RoCE RC
    that sprays every packet across many paths per connection, tolerating out-of-order
    delivery with bounded reordering (Max PSN Range) and SACK/NACK/trimmed-packet retransmit —
    application-transparent multipath. [A] [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md)
33. **UET PDCs and RUD** — PDCs are ephemeral/parallel datagram connections (connection state
    held on the sender, torn-down state on the receiver) enabling per-flow multipathing;
    RUD (Reliable Unordered Delivery) is the transport that delivers packets out-of-order to
    the receiver without a reorder buffer, turning packet spraying into a virtue. [F: UEC 1.0]
    [31-uetch-deep-dive.md](./31-uetch-deep-dive.md)
34. **LLR** — Link-Level Retransmission in UET: an intermediate switch retransmits a dropped
    packet on the same hop instead of the sender doing end-to-end Go-Back-N, hiding loss at
    the link layer and preserving end-to-end low latency. [F: UEC 1.0] [31-uetch-deep-dive.md](./31-uetch-deep-dive.md)
35. **NSCC vs DCQCN** — both are rate-based congestion controls, but DCQCN (RoCE) is binary
    ECN/CNP-signaled with multiplicative cut and additive recovery; UET's NSCC uses per-
    packet telemetry echoed to the sender for finer, faster rate updates, working over
    lossy-or-lossless fabrics without depending on PFC. [F: UEC 1.0] [32-uetch-congestion-and-in-network.md](./32-uetch-congestion-and-in-network.md),
    [21-dcqcn.md](./21-dcqcn.md)
36. **KV ship time** — 70B GQA KV for 4096 tokens is `[E] 1.25 GiB`; at `[E]` 50 GB/s (400G)
    that's `[E] 26.8 ms` (`[E]` bank row "KV 4096tok GQA @50GB/s"). Comfortably inside a
    ~10–30 ms decode window at one request, but the budget is `[E]`/model-dependent. [E]
    [35-training-vs-inference.md](./35-training-vs-inference.md)
37. **Checkpoint budget** — 100B params: Adam state `[E] 1.40 TB` + BF16 grads `[E] 0.2 TB`
    ≈ `[E] 1.60 TB` total; writing it in 60 s needs `[E] 26.7 GB/s ≈ 213,333 Gb/s` (bank rows
    "100B Adam ckpt", "+BF16 grads", "ckpt write in 60s"). That's *why* checkpoints are sharded
    across many parallel links and why rendezvous/all-gather during checkpointing matters. [E]
38. **Buffer/headroom sizing** — a lossless queue needs headroom ≥ bytes that arrive during
    one pause propagation round: roughly `[E]` link_rate × pause_delay. `[E]` a 1 µs pause at
    100 Gb/s is 12.5 KB; at 400 Gb/s it's 50 KB per link-direction (bank "PFC thr" rows), so
    headroom scales linearly with rate and distance. [E] [39-buffer-architecture.md](./39-buffer-architecture.md)
39. **DSCP→TC mapping** — RoCE packets carry a DSCP that the switch/NIC maps to a traffic
    class (TC) and hence a priority queue; that TC maps to a PFC-enabled priority and is where
    ECN marks and CNPs flow. If host and switch DSCP→TC disagree, PFC/ECN/CNP never align and
    the lossless design silently breaks. [A][F: vendor refs] [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md)
40. **RoCEv1 vs v2** — RoCEv1 rides a plain L2 Ethernet frame → single broadcast domain, not
    routable. RoCEv2 encapsulates IB in UDP/IP → L3-routable across subnets (and is what AI
    fabrics run). The `[E] 4791` UDP port is RoCEv2. [A] [16-roce-fundamentals.md](./16-roce-fundamentals.md)
41. **ECT/CE** — ECN marks packets with an ECT codepoint (ECN-Capable Transport) so a switch
    can mark them CE (Congestion Experienced) rather than drop, and the receiver echoes
    congestion. In DCQCN, marked packets trigger the receiver's CNP. [A] [20-ecn-wred.md](./20-ecn-wred.md)
42. **Lossless need** — stock RC retransmits Go-Back-N (no selective ACK): one drop forces a
    retransmit from the last acked PSN, so even small loss is amplified and throughput
    collapses. That's why RDMA wants PFC/credits to keep it lossless. [A][E] [17-why-roce-is-harder.md](./17-why-roce-is-harder.md)
43. **DCBX** — Data Center Bridging exchange (802.1Qaz) is the negotiation protocol by which
    NIC and switch agree on PFC priorities, ETS bandwidth allocation, and DCB parameters —
    mismatches here are a leading RoCE bring-up failure. [A] [18-data-center-bridging.md](./18-data-center-bridging.md)
44. **CNP** — Congestion Notification Packet, an RoCE control packet the receiver sends to the
    sender's QPN when it gets an ECN-marked packet; it carries the marked flow's identity. By
    default it rides a high DSCP (commonly 48) so it's never dropped/throttled. [F: vendor]
    [21-dcqcn.md](./21-dcqcn.md)
45. **NCCL ring vs tree** — NCCL models `{Ring,Tree,CollNet} × {LL,LL128,Simple}` per message
    size and picks the lowest estimated time; generally ring wins big messages (bandwidth-
    optimal), tree wins small messages / large node counts (log latency). There is no fixed
    hardcoded threshold (the old `NCCL_TREE_THRESHOLD` was removed). [F: NCCL issue #457]
    [33-collective-communication.md](./33-collective-communication.md)
46. **Oversubscription** — `oversub = inject / bisection`; >1.0 means the spine cut has less
    capacity than the hosts' total injection. Web DCs tolerate 4:1–10:1 (asynchronous flows),
    but synchronized AI collectives saturate the bisection every step, so GPU backends target
    `[E]` 1:1 (`[E]` bank Clos rows, all oversub 1.000). [E] [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md)
47. **Straggler + percentiles** — a straggler is the slowest rank in a step; since a
    collective blocks on the last finisher, the tail of the per-rank completion distribution
    *is* the step time. Stragglers come from imbalance, PFC head-of-line, or a slow leaf —
    all tail effects. [I] [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md)
48. **GPUDirect Storage (GDS)** — lets storage/NVMe DMA directly to GPU memory over RDMA
    (no CPU/host-RAM staging), speeding checkpoint load/save and data loading. It needs the
    same PCIe/NUMA conditions as GDR. [F: NVIDIA] [35-training-vs-inference.md](./35-training-vs-inference.md)
49. **NCCL_IB_HCA** — selects which HCA(s)/port(s) NCCL uses for network transport, e.g.
    `mlx5_0:1` (device:port) or a comma list for multi-rail. Wrong value → NCCL can't find IB
    and falls back to sockets (huge BW drop). [F: NCCL env docs] [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md)
50. **Jitter** — the variance/spread of latency (e.g. P99 − P50). High jitter means
    sometimes-slow ranks, which on a synchronized job produces straggler-driven step stalls
    even when the median is fine — hence tail/jitter, not average, is the metric. [I]
    [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md)

### Tier 3 answers (51–80)
51. **Avoid credit/pause loops** — keep buffer sizing such that PFC XOFF is asserted only
    transiently and never saturates; align ECN (end-to-end rate control) to act *before* PFC
    so the fabric lives on DCQCN and PFC is a backstop; and avoid cyclic buffer topologies
    where a pause can propagate into itself. On IB, credit flow control is per-VL and naturally
    acyclic. [I][A] [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md), [21-dcqcn.md](./21-dcqcn.md)
52. **Adaptive routing OOO** — spraying each packet down a different path breaks in-order
    delivery, which stock RC can't tolerate; the transport must add bounded reordering (MRC's
    Max PSN Range) or reorder-free semantics (UET RUD). Without it, OOO triggers reorder-
    buffer pressure or Go-Back-N. [A] [13-infiniband-congestion-adaptive-routing.md](./13-infiniband-congestion-adaptive-routing.md),
    [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md)
53. **DC transport** — a "datacenter transport" (MRC over RoCE, or UET) layers multipathing,
    bounded reordering, selective retransmission (SACK/NACK/trim), and per-packet telemetry on
    top of a base RDMA-like reliable connection — versus plain RoCE's single-path,
    in-order, Go-Back-N RC. It exists because connectivity without multipath control wastes
    fabric capacity. [A][F: UEC 1.0] [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md)
54. **PFC deadlock** — PFC is hop-by-hop and reversible; two lossless priorities pausing each
    other across a cyclic buffer allocation can reach a global pause where no link progresses.
    It's broken by the PFC watchdog (force-drop the offender), by buffer/priority design that
    keeps pauses acyclic, and by UET's optional/no-PFC designs. [A] [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md)
55. **ECN/PFC interplay** — set WRED Kmin/Kmax *below* the PFC XOFF threshold so ECN marks
    and DCQCN slows the sender before the queue overflows; leave PFC headroom as the backstop
    only for the residual burst. Kmax ≫ XOFF ⇒ pause storms; Kmin ≪ ⇒ throttled throughput.
    [I][A] [20-ecn-wred.md](./20-ecn-wred.md), [21-dcqcn.md](./21-dcqcn.md)
56. **MRC bounded reorder** — the receiver keeps a PSN window (Max PSN Range) and delivers
    in-order to the app while tolerating out-of-order arrival within that window; gaps are
    filled via SACK-based selective retransmit, so spraying is bounded and controlled rather
    than unbounded buffering. [A] [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md)
57. **UET MP_RANGE / SACK** — MP_RANGE lets a receiver acknowledge a range of PSNs instead of
    only the highest contiguous one, and SACK enables selective retransmission of just the
    lost packets — both are what make reliable packet-spraying practical over lossy links
    without Go-Back-N cost. [F: UEC 1.0] [31-uetch-deep-dive.md](./31-uetch-deep-dive.md)
58. **Incast recovery** — PFC/DCQCN recover incast by rate-reducing senders on CNP (ECN) and
    pausing on PFC, with residual loss paid in Go-Back-N; UET recovers with selective
    retransmit (LLR hides link loss) plus rate control, so the lost-packet penalty is per-
    packet, not a full rewind — meaning less tail latency under incast. [I][F: UEC 1.0]
    [32-uetch-congestion-and-in-network.md](./32-uetch-congestion-and-in-network.md)
59. **WAN AllReduce** — a 100 GB ring AllReduce across 1,024 ranks: at RTT 1 ms → `[E] t =
    18.0 s` (lat 2.0 s + BW 16.0 s); at RTT 10 ms → `[E] t = 36.4 s` (lat 20.5 s + BW 16.0 s)
    (bank "WAN ring AR" rows). The 10× RTT adds 18.4 s of pure latency — WAN collectives are
    RTT-dominated, not BW-dominated, which is why DCI is a different engineering problem. [E]
    [35-training-vs-inference.md](./35-training-vs-inference.md)
60. **MoE skew** — uniform dispatch is `[E] 250k tok/node` (bank "MoE skew" row: 32 experts / 8
    nodes, top-8); a +20% all-skew concentrates `[E] +80%` onto one node → its inbound NIC
    absorbs an outsized incast burst while others idle, spiking the combine AllToAll tail. [E]
    [34-moe-all-to-all.md](./34-moe-all-to-all.md)
61. **MoE vs oversub** — at `[E]` 2:1 oversubscription (bank "1024 GPU 1:2 oversub": inject
    6.4 TB/s vs bisection 3.2 TB/s), the *all-to-all* (no reduction saving) dispatch saturates
    the shallow cut; every byte is a distinct flow, so the 2× cut adds ~2× queueing to the
    expert NIC's incast. AllToAll needs 1:1 more than AllReduce does. [E][I] [34-moe-all-to-all.md](./34-moe-all-to-all.md)
62. **Multi-plane failure domain** — each rail/plane is its own fabric, so a switch/plane
    failure strands only its 1/K of GPUs (rail isolation), and a shared-spine failure can't
    black-hole the whole cluster; planes also isolate blast radius of ECMP imbalance. The cost
    is more switches and harder cross-plane traffic. [I] [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md)
63. **P_Key vs VLAN enforcement** — P_Key is enforced by the *endpoint CA* (the NIC refuses
    non-members), giving host-level isolation the switch can't override; a VLAN tag is a
    switch-enforced frame label. For RDMA tenancy you want P_Key (or VF/VLAN + QoS) so the
    *data plane* at the NIC enforces isolation. [A] [47-security-multitenancy.md](./47-security-multitenancy.md)
64. **SR-IOV tenancy** — a VF is a carved slice of the physical function (its own QPs, its own
    doorbells, its own bandwidth share); with per-VF P_Key/QoS an SR-IOV NIC gives a tenant a
    hardware-isolated RDMA endpoint, sharing the PF's wire. Isolation quality depends on
    enforcing P_Key + rate limits per VF. [F: NVIDIA/SR-IOV docs] [48-kubernetes-slurm.md](./48-kubernetes-slurm.md),
    [47-security-multitenancy.md](./47-security-multitenancy.md)
65. **Fallback diagnosis** — run with `NCCL_DEBUG=INFO NCCL_DEBUG_SUBSYS=NET`; a healthy run
    logs "Using network: IB"/its HCA, a fallback logs "Using network: Socket". Check
    `NCCL_IB_HCA`, `NCCL_NET`, GID index, driver plugin, and that the IB iface is Active —
    each can silently force the TCP path (order-of-magnitude BW drop). [F: NCCL env docs]
    [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md)
66. **1,024-GPU single-plane vs multi-plane** — one big `[E]` 1:1 Clos (bank row: 128 NICs,
    32 leaves + 32 spines, 6.4 TB/s bisection) is simple but a spine loss hits everyone and
    scaling is hard; multi-rail (8×400G, 8 planes, `[E]` 51.2 TB/s total) uses smaller
    commodity switches, isolates failures to 1/K, and lets one collective stripe 8 paths — at
    the cost of more switches and cross-plane routing for inter-plane traffic. [E][I]
    [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md), [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md)
67. **1.6T PHY / FEC** — 1.6T (1600 Gb/s) ports use PAM4 + a robust FEC and line codes
    designed for 200 Gb/s/lane (the bank has `[E] 1600 Gb/s = 200.0 GB/s`); FEC (e.g.
    `[F: 802.3df]` KP4/RS-FEC on 800G and up) trades line overhead for BER required over PAM4
    links. Exact 1.6T FEC is `[F: vendor/802.3df spec]`. [41-physical-layer.md](./41-physical-layer.md)
68. **Goodput math** — RoCEv2 carries `[E] 58 B` fixed header/packet, so payload % = 1 −
    58/payload: `[E]` ~96.1% at 1500 B (3.87% overhead), ~98.6% at 4096 B payload (1.42%),
    22.66% overhead at 256 B. Goodput = throughput × payload fraction (before CC/contention).
    [E] [43-network-bandwidth-calculations.md](./43-network-bandwidth-calculations.md)
69. **α convergence** — DCQCN starts α near `[F: vendor] 1.0` (so the first CNP triggers a
    big cut), then decrements/increments α by a small `g` per update interval: no CNP ⇒ α
    drops toward 0 (aggressive recovery), CNP ⇒ α rises (more conservative). Steady α reflects
    the equilibrium marking rate the switch's WRED is emitting. [F: vendor]/[I]
    [21-dcqcn.md](./21-dcqcn.md)
70. **HOL blocking** — in a FIFO queue, a slow/blocked head packet (or, with PFC, a paused
    priority) holds up unrelated traffic behind it on the same port/priority. PFC creates HOL
    because a pause on one priority can stall the whole link's egress for that class. [A][I]
    [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md), [39-buffer-architecture.md](./39-buffer-architecture.md)
71. **Pause storms** — if Kmax (ECN) sits above the PFC XOFF threshold, the queue hits pause
    *before* ECN marks, so PFC fires constantly and the sender never gets an end-to-end rate
    signal — the fabric spends all its time pausing (a "storm"). Aligning Kmax < XOFF fixes
    it; too-low Kmin instead throttles prematurely. [I][A] [20-ecn-wred.md](./20-ecn-wred.md), [21-dcqcn.md](./21-dcqcn.md)
72. **RTT vs ECN CC** — TIMELY drives rate purely from NIC-observed RTT gradients (no switch
    feedback); DCQCN drives rate from ECN-CE marks relayed via CNP. TIMELY is simpler (no
    switch support) but reacts to queueing indirectly; DCQCN leverages explicit switch
    feedback. HPCC uses in-band telemetry for the most precise control. [A] [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md)
73. **Flowlet spraying** — bursty flows naturally have gaps; splitting a long flow *at its
    gaps* into "flowlets" lets a load balancer re-hash each flowlet to a different member,
    giving per-burst spreading without per-packet reordering at the receiver. Fixes ECMP
    imbalance from a few elephants. [A] [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md)
74. **Bisection BW** — for a 2-tier symmetric Clos, bisection = S × U × BW_up (spine count ×
    uplinks/spine × uplink BW); oversub = inject/bisection. For balanced radix R with S=L,
    bisection = L×(R/2)×BW, and 1:1 ⇔ oversub 1.0. [E] [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md)
75. **CP / seq-parallel networking** — context/sequence parallel shards the KV/attention
    across ranks; implementations either rotate K/V via AllToAll (stresses the fabric like
    EP) or pass chunks point-to-point (ring attention, P2P-dominated). Both want low latency
    and no incast hotspots. [I] [33-collective-communication.md](./33-collective-communication.md), [34-moe-all-to-all.md](./34-moe-all-to-all.md)
76. **KV shipping budget** — prefill GPUs must ship KV to decode GPUs each generation, and it
    must fit inside the decode step time or decode starves. `[E]` GQA-70B 4K tokens = 1.25 GiB
    → 26.8 ms at 50 GB/s; on slower uplinks or large batches it becomes a real serialization
    cost, so designs size the KV path or co-locate. [E] [35-training-vs-inference.md](./35-training-vs-inference.md)
77. **PCIe ceiling** — `[E]` PCIe 5.0 x16 ≈ 63 GB/s one-way: a `[E]` 400G NIC (50 GB/s) fits
    with headroom, but a `[E]` 800G NIC (100 GB/s) is capped at ~63 GB/s on Gen5 x16 — it
    needs PCIe Gen6 (ConnectX-8 x16 Gen6 is 800G) or two Gen5 links. An "800G NIC at 63%"
    result is a PCIe-neck, not a fabric problem. [E] [43-network-bandwidth-calculations.md](./43-network-bandwidth-calculations.md)
78. **SHARP vs endpoint reduce** — NCCL reduces in the endpoint (each rank reduces, then
    totals via ring/tree); SHARP reduces *in the switch* while packets transit, so a rank
    sends shards and the fabric returns the reduced result — cutting both bytes shipped and
    latency for AllReduce. [A] [14-sharp-in-network-reduction.md](./14-sharp-in-network-reduction.md)
79. **NCCL rail striping** — NCCL uses multiple HCAs/NIC ports for one collective when it sees
    them (multi-rail), striping QPs across rails to multiply effective busbw; broken when
    `NCCL_IB_HCA` pins one rail, rails share a spine, or the fabric isn't actually multi-plane
    — the result is busbw stuck at one rail's worth. [I][F: NCCL env] [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md),
    [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md)
80. **PFC headroom** — lossless headroom must absorb one pause round-trip of traffic: `[E]`
    1 µs pause @100G = 12.5 KB, @400G = 50 KB per link-direction (PFC threshold bank rows);
    multiply by pause delay × rate across the hop (propagation + switch latency). Undersized
    headroom → drops despite "lossless"; oversized → wasted buffer. [E] [39-buffer-architecture.md](./39-buffer-architecture.md)

### Tier 4 answers (81–100)
81. **4,096-GPU fabric** — pick IB (NDR/XDR, SHARP, credit-lossless) or a tuned RoCE/multi-rail
    Ethernet: whatever your ops team can run and your vendor supports at 1:1 bisection. A
    1,024-GPU build is the per-plane unit; 4,096 GPUs = 4 planes or one big radix-64/128 Clos
    (`[E]` 32,768-GPU math scales linearly). Decide on SHARP value, OOO/multipath tolerance,
    and ops model — see the decision tree. [E][I] [49-design-decision-tree.md](./49-design-decision-tree.md)
82. **RoCE migration** — inventory flows, enable PFC on a RoCE priority + DCB/DSCP mapping,
    set WRED ECN below PFC, add jumbo MTU, enable per-QP UDP-sport entropy, then roll one
    rack as a pilot measuring `[E]` busbw vs the IB baseline before cutting over; keep a
    fallback TCP path during the window. [I][E] [23-roce-lossless-fabric-design.md](./23-roce-lossless-fabric-design.md)
83. **UET pilot 2027** — pilot on a *disaggregated/storage* or new-rack segment first (not the
    live training cut), validating silicon availability, NSCC/LLR behavior under incast, and
    ROCE-parity busbw; adopt only where UET silicon is real and SLO-tested — `[I]` UET is
    spec/early-silicon as of 2026-08-25. [F: UEC][I] [30-ultra-ethernet-consortium.md](./30-ultra-ethernet-consortium.md)
84. **PFC storm postmortem** — collect PFC/ECN/CNP counters (`ethtool -S`, switch counters),
    correlate the pause-triggering priority with the traffic class and timestamp, find whether
    Kmax > PFC threshold or a burst exceeded headroom; fix thresholds, add per-VF/tenant QoS,
    then re-run the incast test. [I] [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md), [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md)
85. **Oversub justification** — for the *GPU backend* the case for 2:1 is weak: synchronized
    collectives saturate the bisection (`[E]` 2:1 = 6.4 inject / 3.2 bisection), adding ~2×
    queueing per step; 1:1 is the standard. 2:1 is defensible only for storage/management or a
    strictly rate-limited control plane. For all-to-all (MoE) it's even worse. [E][I]
    [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md)
86. **Storage + compute split** — keep them separate: backend is 1:1 lossless RDMA optimized
    for collectives; storage can tolerate 4:1–10:1 and uses GPUDirect Storage over 100–400GbE.
    Mixing them couples SLOs and lets storage bursts create PFC/queueing noise against
    training. [I][E] [02-ai-networking-taxonomy.md](./02-ai-networking-taxonomy.md), [35-training-vs-inference.md](./35-training-vs-inference.md)
87. **Multi-tenant GPU cloud** — isolate per tenant with P_Key (IB) or VLAN+per-VF QoS/RoCE
    priority (Ethernet), enforce rate limits per VF, dedicate rails or carve planes, and
    namespace the SM; use SR-IOV shared-device plugins for density. `[E]` the 2:1-plan failure
    mode is tenants' all-to-all hitting a shared 2:1 cut — isolate or over-provision it. [I]
    [47-security-multitenancy.md](./47-security-multitenancy.md), [48-kubernetes-slurm.md](./48-kubernetes-slurm.md)
88. **KV-transfer design** — size the prefill→decode path so KV transfer < decode step time
    (`[E]` GQA-70B 4K = 1.25 GiB → 26.8 ms at 50 GB/s); choose GQA/sharded KV to cut bytes,
    co-locate or use a fast discrete link, and treat KV as a separate priority class so
    decode isn't starved by training. [E][I] [35-training-vs-inference.md](./35-training-vs-inference.md),
    [Prefill-Decode-Disaggregation.md](../Inference/Prefill-Decode-Disaggregation.md)
89. **IB SM DR** — run redundant SMs (OpenSM/UFM) with master/slave and heartbeat failover;
    persist the SM database (LIDs, partitions, routes) to recover a fixed fabric; test
    failover by killing the master and confirming LID/routing re-converge without a full
    fabric flap. [I] [11-infiniband-subnet-manager.md](./11-infiniband-subnet-manager.md)
90. **Capacity from JCT SLO** — invert the SLO: budget step time = compute + communication; with
    comm = collective time (`[E]` AllReduce = 2(n-1)/n·M/B + 2(n-1)α), solve for the per-link
    B and bisection that meet JCT, validate with a benchmark sweep, then size leaves/spines to
    match — headroom for incast is the safety margin. [E][I] [33-collective-communication.md](./33-collective-communication.md)
91. **Cost/ops IB vs Ethernet** — IB buys proven lossless + SHARP + adaptive routing but is
    vendor-concentrated and has its own SM ops; Ethernet broadens vendor choice and reuses DC
    ops but needs PFC/ECN/DCQCN tuning and has worse out-of-box behavior. Model TCO across
    switches + NICs + expert-hours + failure cost, per scale. [I] [49-design-decision-tree.md](./49-design-decision-tree.md)
92. **Vendor lock-in** — reduce risk by keeping the *software* abstracted (NCCL/UCC/MPI over
    verbs), standardizing on an open control plane where possible, and evaluating at least two
    viable fabric vendors before commit; accept that NIC↔ASIC↔control-plane hairiness is the
    real lock-in surface (RoCE's multi-vendor base helps on Ethernet). [I] [24-vendor-landscape.md](./24-vendor-landscape.md)
93. **Rail vs flat @1k** — multi-rail wins for training: `[E]` 8×400G rail = 8 parallel planes,
    51.2 TB/s total, failure isolation to 1/K, and NCCL stripes across them (Lab 15); flat
    single-fabric is simpler but a spine loss hits everyone. Choose rail for performance/
    isolation, flat only if you need fewer switches and single-fabric ops. [E][I]
    [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md)
94. **10k-GPU greenfield** — compose `[E]`-verified plane math: radix-64/128 high-radix spines,
    rail-optimized multi-plane (each plane a 1:1 Clos), 1:1 bisection, separate storage + Mgmt
    + front-end fabrics, telemetry (PFC/ECN/CNP + INT) on everything, and an SM-redundant IB
    control plane (or tuned RoCE). Plan for 3-tier/multi-plane at this scale. [E][I]
    [52-reference-architectures.md](./52-reference-architectures.md), [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md)
95. **Hybrid IB + Ethernet** — legitimate: IB (or dedicated RoCE) for the backend collectives,
    standard Ethernet for storage/front-end/management, stitched at the islands you must
    cross; keep their SLOs from coupling (separate fabrics, `[E]`-sized independently). Only
    justify the second ops model if the workloads genuinely diverge. [I][E]
    [02-ai-networking-taxonomy.md](./02-ai-networking-taxonomy.md)
96. **Regression triage** — diff hardware/versions (NCCL, driver, OFED, firmware), re-run the
    metric stack in order ([44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md) goes NIC→collective→JCT),
    watch counters for a new CC/PFC/ECMP problem, and bisect config changes — most regressions
    trace to a rolling upgrade, a threshold drift, or a topology change. [I] [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md),
    [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md)
97. **Benchmark methodology** — freeze the metric stack (perftest BW+lat, nccl-tests busbw at
    fixed sizes, a real-step JCT), a control workload, and one reference fabric; run N repeats,
    report medians *and* tails; and always validate invariance (GID, GDR, rail count, MTU)
    before trusting a number. [I][E] [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md)
98. **Fabric telemetry SLO** — define what you must *always* see: per-port PFC/ECN/CNP counters
    and per-uplink utilization sampled at sub-second, with tail-latency/jitter exposed per
    collective; set alert thresholds on pause storms and imbalance rather than averages, and
    require INT/streaming telemetry at scale. [I] [40-network-telemetry.md](./40-network-telemetry.md)
99. **NCCL upgrade risk** — upgrading NCCL can change algorithm/protocol selection (ring vs
    tree, LL128, NVLS) and silently alter busbw; mitigate with a pinned regression suite
    (nccl-tests busbw + a real step), staging on a test partition, and keeping a rollback
    image — check `[F: NCCL env]` defaults changed between versions. [I] [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md)
100. **800G migration** — 800G ports need PCIe Gen6 NICs (`[E]` an 800G NIC is 100 GB/s, past
    63 GB/s Gen5 x16), so the NIC, the switch (radix drops per lane count), and the optics all
    change together; migrate in planes (per-rail) keeping 400G rails live, validate `[E]`
    busbw against line rate at large messages, and confirm PFC/ECN threshold math scales to
    the new per-µs bytes (`[E]` 400G 1 µs = 50 KB headroom, scales up). [E][I]
    [41-physical-layer.md](./41-physical-layer.md)

---

## Design Exercises (scenario + requirements + solution sketch)

### Exercise 1 — 64-GPU research cluster
**Scenario:** a university ML lab wants a 64-GPU (8 nodes × 8 GPU) cluster for small-model
training and experimentation, lowest reasonable cost/ops, Ethernet background.
**Requirements:** ≥1:1 effective bisection for collectives, GDR, existing Ethernet ops
comfort, telemetry.
**Solution sketch:** a single 8-GPU-node × 800G-RoCE leaf-spine (or a small IB NDR fabric).
Use a leaf-spine with radix-8 leaves/spines (`[E]` 64 GPU ≈ 8 NICs, 1:1 at radix 8). RoCEv2
with PFC+DCQCN, jumbo MTU, per-QP UDP-sport entropy, and one leaf + N spines (`[E]` the bank's
rail math: at this scale a single switch may suffice since E ≤ switch radix — verify oversub).
Justify materials: 64 GPUs is small enough that a tuned RoCE fabric meets `[E]` busbw ≈
0.95 × link (the ring's busbw saturates at link rate, normalized by `2(n-1)/n × algbw`),
with lower TCO and reuse of Ethernet ops. [E][I]

### Exercise 2 — 512-GPU enterprise AI factory
**Scenario:** a company stands up a 512-GPU production training fabric with an SLO on
AllReduce busbw per GPU.
**Requirements:** 1:1 at the bisection, GDR, NIC↔GPU affinity, multi-rack placement.
**Solution sketch:** 64 nodes × 8 GPU, 1×400G/NIC (or rail-optimized 2×400G). Build a 1:1
Clos (`[E]` 512 GPU ≈ 64 NIC endpoints → leaves/spines per the bank's radix-8 math, oversub
1.000), rail-confirmable. Pin NIC to the GPU's NUMA node (`nvidia-smi topo -m` ≤ PXB), enable
GDR, set jumbo + PFC + DCQCN thresholds below PFC. Validate with nccl-tests busbw ≥ `[E]`
~0.95 × 2(n-1)/n × 400G. Reasoning: enterprise → prioritize RoCE's broad ops model and 1:1
bisection that the SLO math demands. [E][I]

### Exercise 3 — 4,096-GPU training cluster
**Scenario:** Frontier-scale training (multi-100B LLM) on 4,096 GPUs.
**Requirements:** 1:1 bisection, minimal step time (tail), SHARP or equivalent, fault isolation.
**Solution sketch:** rail-optimized multi-plane IB NDR/XDR: 4,096 = 512 nodes × 8 GPU; build
and validate a 512-GPU plane first, then replicate to K planes (`[E]` the per-plane Clos math
from the bank scales linearly — 1,024 GPU plane = 32 leaves + 32 spines, 6.4 TB/s), giving
`[E]`-verified total bisection = K × plane. Use SHARP for in-network AllReduce, SM-redundant
IB, and `[E]`-size the checkpoints (1.6 TB/60 s ⇒ ~26.7 GB/s of write bandwidth must be
available). Reasoning: at this scale IB's proven credit-lossless + adaptive routing + SHARP
and the rail isolation of planes justify its ops cost. [E][I]

### Exercise 4 — convert existing Ethernet DC to RoCE
**Scenario:** a cloud/data-center operator must carry GPU training on an existing multi-rack
Ethernet DC (no PFC today, 1500 MTU).
**Requirements:** lossless RoCEv2 without forklift changing the whole DC, staged rollout.
**Solution sketch:** enable PFC on a dedicated RoCE priority (e.g. priority 3) on the
training racks only (not global), add DCB/DCBX + DSCP→TC mapping, bump to jumbo MTU on the
RoCE VLAN, set WRED ECN Kmin→Kmax below the PFC threshold, and enable per-QP UDP-sport
entropy. Pilot one rack measuring `[E]` busbw vs the same hosts on IB/TCP; overlap with a
fallback TCP path during cutover. Reasoning: segmented QoS lets RoCE exist beside lossy
traffic; alignment of DSCP↔TC↔PFC-priority is the make-or-break. [I][E]

### Exercise 5 — multi-tenant GPU cloud
**Scenario:** a provider sells GPU instances; tenants must not interfere; some run inference,
some training, some MoE all-to-all.
**Requirements:** per-tenant isolation, no cross-tenant PFC/bandwidth coupling, density.
**Solution sketch:** SR-IOV (or shared-device plugin) giving each tenant isolated VFs with
per-VF rate limits and QoS priority; P_Key (IB) or VLAN+per-VF isolation (Ethernet); carve
rails/planes so a tenant's all-to-all (`[E]` MoE dispatch) can't incast a neighbor; put all
collectives on a 1:1 plane and storage on an oversubscribed separate fabric. Reasoning:
without per-VF QoS a single tenant's incast/PFC storm spills into neighbors — enforce at the
NIC (P_Key/VF) and the plane. [E][I]

### Exercise 6 — networking for MoE training
**Scenario:** a many-expert (e.g. 32-expert) MoE model on a node cluster; dispatch is
all-to-all and skewed.
**Requirements:** tolerate all-to-all incast and dispatch skew without tail blowup; 1:1 for
the expert NICs.
**Solution sketch:** choose node-limited routing (bound each token to a small expert-node
subset) to keep dispatch within reachable nodes; keep the bidirectional expert-swap at 1:1
(`[E]` a 2:1 cut multiplies all-to-all queueing); account for skew — `[E]` a +20% skew loads
one node's NIC to ~+80% (bank "MoE skew"), so size expert-node ingress headroom and/or spread
experts to even dispatch. Reasoning: all-to-all does no reduction, so it's congestion-bound
not byte-optimal; both 1:1 and skew-absorbing buffers matter. [E][I]

### Exercise 7 — networking for disaggregated inference
**Scenario:** prefill GPUs and decode GPUs are physically separate; KV must move between them
each generation at high QPS.
**Requirements:** KV transfer < decode step time; no starvation of decode by training/other
traffic; scale with batch/length.
**Solution sketch:** use GQA/sharded KV to minimize per-token bytes (`[E]` GQA-70B = 0.33 MB/
token vs MHA ~2.6 MB/token; 4K tokens = 1.25 GiB → `[E]` 26.8 ms at 50 GB/s), put KV shipping
on a dedicated high-priority class over a fast link so it fits inside the `[E]` decode window,
co-locate prefill+decode where the KV volume dominates, and shard KV across many links for
large batches. Reasoning: the KV path is latency-critical serialization — give it priority,
fewer bytes, and enough aggregate `[E]` bandwidth to beat the decode budget. [E][I]

---

## Key Takeaways
1. The 100 questions ladder from "what is a QP" to a 10k-GPU fabric call; answers are
   claim-tagged with the bank's `[E]` numbers where load-bearing.
2. The recurring themes: tail latency drives JCT, lossless + CC alignment (ECN below PFC)
   is the RoCE crux, and all-to-all (MoE/disaggregation) is congestion-bound, not byte-optimal.
3. `[E]` anchors to remember: KV 4K · GQA = 26.8 ms @ 50 GB/s; checkpoint = 1.6 TB → 26.7 GB/s
   in 60 s; WAN AllReduce = 18.0 s @1 ms RTT vs 36.4 s @10 ms; MoE +20% skew ⇒ +80% on one node;
   2:1 oversub ⇒ 6.4 vs 3.2 TB/s.
4. Design exercises couple the math to the ops decision: every sketch pins bisection, rail
   isolation, threshold alignment, or KV budget back to a bank `[E]`.
5. Answers that assert a vendor silicon or spec figure are marked `[F: vendor/spec]` or `[I]` —
   never stated as independent fact. [T]

## Related
- [55-cheat-sheet.md](./55-cheat-sheet.md) — the one-page model the questions test.
- [49-design-decision-tree.md](./49-design-decision-tree.md), [52-reference-architectures.md](./52-reference-architectures.md) — the design answers in full.
- [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md), [53-learning-labs.md](./53-learning-labs.md) — the how-to counterpart.
- [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md), [README.md](../Training-Engineering/README.md).

## References
- Section constants bank `[E]` (computed 2026-08-25): KV 4096tok GQA @50GB/s = 26.8 ms; 100B
  Adam ckpt 1.40 TB; +BF16 grads 1.60 TB; ckpt write in 60s 26.7 GB/s = 213333.3 Gb/s; WAN ring
  AR RTT=1ms t=18.0 s / RTT=10ms t=36.4 s; MoE skew; 1024 GPU 1:2 oversub (ov 2.000); 1600 Gb/s =
  200.0 GB/s; PFC thr @100G/1us 12.5 KB, @400G/1us 50 KB; busbw relation; Clos rows. [E]
- Research bank: DCQCN (Zhu et al., SIGCOMM'15, DOI 10.1145/2785956.2787484) [A]; UEC 1.0 [F];
  MRC (OpenAI/arXiv 2606.18170) [A]; nccl-tests PERFORMANCE.md [F]; NCCL issue #457 [F];
  routing/topology/telemetry pages cited inline.
