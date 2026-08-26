# Complete Packet Journeys: One Gradient, Three Fabrics
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: IBTA/RDMA header sizes, NCCL env docs, IETF Fast-CNP (RoCEv2), UEC spec 1.0 / author paper (arXiv:2508.08906) for UET PDS/SES/NSCC/LLR; header-overhead math computed [E]; fetched 2026-08-25.

## 30-Second Explanation
This page follows **one 1 MB gradient chunk** produced by a ring **AllReduce** through three fabrics — **InfiniBand**, **RoCEv2**, **Ultra Ethernet Transport (UET)** — as numbered vertical journeys. Each hop annotates the headers added, the latency class, and which hardware does the work. The lesson: the *application-facing* story is identical in all three (NCCL posts a send, the NIC DMAs GPU memory, the peer DMA-writes into its GPU), but the *wire* differs sharply — IB is **lossless-by-credits** with tiny 24 B headers; RoCEv2 is **lossless-by-PFC policy** with 58 B UDP/IP headers and faces an ECMP entropy problem; UET is **lossy-by-design** with per-packet spraying, receiver reassembly, and ACK-carried congestion feedback. The closing table quantifies the difference (header overhead [E], loss model, path behavior, CC feedback).

## The shared application frame (all three)
```text
PyTorch step -> gradient ready -> NCCL ring AllReduce -> this 1 MB chunk
is one ring segment sent from GPU-A to GPU-B (next rank in the ring).
1 MB chunk [E, arithmetic]:
  IB        @ 4096 B payload  -> ~245 packets   (1e6/4096 = 244.1)
  RoCEv2    @ 8942 B payload  -> ~112 packets   (1e6/8942 = 111.8)
  UET (jumbo) @ ~9k payload   -> ~112 packets
serialization time [A: 1 MB ÷ link]:
  0.8 Tb/s (800GbE=100 GB/s) -> ~10 us ; 400GbE/NDR400 (50 GB/s) -> ~20 us
```
Chunk flow, application-level (assume **Simple** NCCL protocol = sender RDMA-writes the reduced chunk to the peer): `reduce on A -> post send -> NIC DMAs from A's HBM -> wire -> peer NIC DMAs into B's HBM -> completion on A & B`. **[F/I]**

---

## JOURNEY 1 — InfiniBand (lossless by credits)

### Numbered vertical trace
```text
STEP  WHAT HAPPENS                         HEADERS / MECHANISM          LATENCY CLASS / HARDWARE
 1    PyTorch backward produces the grad   (in GPU HBM)                 compute (µs-scale)
 2    NCCL AllReduce: this chunk is the    ring step k                  app/collective
      reduced segment for neighbor B
 3    NCCL posts a WR (work request) via   ibv_post_send -> WQE on QP    ~1 us, software; QP in RTS
      verbs; the WQE references a GPU-                                 (Ready-To-Send) state
      resident buffer (registered, mkey)
 4    HCA picks the WQE; issues a GPUDirect DMA READ                      NIC + PCIe; GPUDirect
      of 1 MB from GPU-A HBM across PCIe                                 (GDR) avoids host copy
 5    HCA segments into ~245 x 4096B pkts  per pkt: LRH(8)+BTH(12)+      NIC segmentation; headers [E]
                                           ICRC(4) = 24 B/hdr           IB hdr = 24 B [E: bank]
 6    HCA sends to port; leaf switch       LID forwarding via LFT;       switch; ~100s ns link latency
      forwards by LID (not IP!)           per-VL CREDIT check
 7    leaf -> spine (or adaptive routing)  SL->VL map; credits           switch cut-through ~ns
 8    spine -> destination leaf            LID forward                   switch
 9    destination leaf -> remote HCA       LID forward, credit check     switch->NIC
10    remote HCA CREDIT-BUFFERS packet,    BTH consume; DMA WRITE        NIC receives loss-free (credits)
      then GPUDirect DMA-WRITE 1 MB        into remote GPU HBM
      into GPU-B HBM                                                    
11    HCA posts CQE; ACK generated        AETH/ACK up the reverse path   NIC completion
12    NCCL sees completion; fire next ring step                          collective
```
### What happens per hop — annotate
- **Hop 4–5 (HCA):** the RDMA Read/WRITE semantics mean the NIC drives PCIe DMA both from (read) and into (write) GPU memory — **GPUDirect RDMA** removes the host bounce; `nvidia-peermem` must be loaded / ACS disabled or GDR silently turns off [F: NVIDIA].
- **Hop 6 (leaf):** IB switches forward by **LID** from the **LFT (forwarding table)** programmed by the **Subnet Manager (SM/OpenSM/UFM)**; the per-VL **credit** gate is what makes it lossless — a congested egress advertises zero credit and the sender stalls, backpressure propagates to the HCA. **[F]**
- **Hop 7:** with **adaptive routing** (Quantum switches + ConnectX-5+ OOO), the switch may spray per-packet across paths and the HCA re-orders — the only OOO you see in native IB comes from AR; regular in-order routing needs no reorder. **[F: vendor]**
- **Hop 10:** the receiver's credit guarantee means packets are **never dropped** (only HOQ-timeout deliberate drops exist) [F]; the NIC **DMA-writes straight into remote HBM** — the payload never touches host memory.
- **Hop 11:** the **CQE** (completion queue entry) tells NCCL the WQE finished; **AETH** ACKs flow back for the RC reliability state.

### Latency classes
1 MB is bandwidth-not-latency-bound: **serialization ~20 µs @ NDR400 (50 GB/s)** dominates per-hop **~100s ns** cut-through [E]/[I]. The messages are ms-scale? No — ~20 µs. **[A]** The point of the journey is *where* the 20 µs lives and that it is **credit-controlled (lossless) the whole way**.

---

## JOURNEY 2 — RoCEv2 (lossless by PFC policy, UDP/IP, ECMP)

### Numbered vertical trace
```text
STEP  WHAT HAPPENS                          HEADERS / MECHANISM            LATENCY / HARDWARE
 1-4  SAME as IB (PyTorch->NCCL->WQE->QP)   same software path            same
 5    HCA segments ~112 x 8942B pkts; adds  per pkt: Eth(14)+IPv4(20)+     RoCEv2 hdr = 58 B [E: bank]
      UDP/IP encap                          UDP(8)+BTH(12)+ICRC(4) = 58 B
 6    leaf classifies by DSCP->priority     RoCE DSCP 26->prio 3 (PFC)    switch; ECN capable
 7    leaf -> spine: ECMP hashes the 5-tuple dst-port 4791 + src-port      entropy problem (page 22)
 8    spine forwards to chosen leaf         5-tuple path (one per flow)    switch
 9    [congestion] switch WRED-marks ECN    K-min<K-max below PFC XOFF     switch marks ECN-CE [F]
10    receiver NIC sees ECN; sends CNP      CNP (DSCP 48, reverse path)    side-traffic on control class
11    sender NIC cuts rate (DCQCN)          rate*(1-a/2) per CNP           NIC CC in hardware
12    [if ECN too slow] PFC XOFF on prio 3  pause frame -> headroom (~50KB @400G/µs [E])  backstop
13    remote HCA DMA-WRITE into GPU-B HBM   BTH consume; GPUDirect          lossless so no retransmit
14    CQE -> NCCL completion -> next step   (or NIC/DLB reorder if spraying)
```
### Where RoCEv2 differs from IB
- **Encap:** RoCEv2 rides **UDP/IP** (dst port **4791**), which is what makes it routable and ECMP-able — and it is exactly the dst-port fixity (+few QPs) that creates the **entropy/polarization** problem [F: IETF Fast-CNP; Meta]. See [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md).
- **Losslessness is policy, not physics:** no credits — a drop would trigger RC **Go-Back-N**, so PFC + ECN must prevent drops. **ECN (steps 9–11) is the primary control loop** (end-to-end, slow-but-safe); **PFC (step 12) is a backstop** only when ECN hasn't caught up. The single biggest tuning rule: **ECN K-max < PFC XOFF** ([23-roce-lossless-fabric-design.md](./23-roce-lossless-fabric-design.md) §5).
- **CNP side-traffic:** congestion feedback travels as **CNP packets on a separate high-priority DSCP (48)** back to the sender — this is control-plane side-traffic the IB journey does not have (IB ACKs ride the data path). **[F]**
- **Reordering:** with plain ECMP each flow follows one path → no reorder needed. With **DLB per-packet spray or MRC/UET-style multipath**, packets arrive OOO and the **receiver NIC re-orders before the RDMA engine** (the whole reason MRC exists) [F/A].

---

## JOURNEY 3 — Ultra Ethernet Transport (UET: lossy by design, per-packet spray)

### Numbered vertical trace
```text
STEP  WHAT HAPPENS                            HEADERS / MECHANISM         LATENCY / HARDWARE
 1    PyTorch -> NCCL/CCL -> libfabric v2.0   same app intent, new API    collective
 2    UET FEP (NIC) creates an ephemeral      **PDC** established 0-RTT;   connectionless, NO
      Packet Delivery Context (PDC)           first packet carries state   QP handshake [F: UEC]
 3    NIC segments ~112 pkts; per pkt:        Eth(14)+IPv4(20)+UDP(8)+  UET std hdr = 98 B [E]
      EV (entropy value) set per packet       PDS(12)+SES(44); TSS(+28)  (PDS 12/SES 44 [F: bank])
 4    leaf forwards; **per-packet spray**     each pkt's EV picks a path   switch (ECMP+egress ECN only)
 5    spine: equal-cost paths, no pinning     EV varies per packet ->      different pkts of the SAME
                                              **different paths**          chunk take different routes
 6    receiver FEP **RUD reassembles**        64-bit SACK bitmap per PDC;  NIC: zero-copy DDP, NO
      out-of-order packets                    no reorder buffer needed     reorder buffer [F]
 7    [marginal link] **LLR** retransmits      hop-by-hop, sequence in      fixes corruption in ~1 us,
      a corrupt frame on that one link        preamble; ~1 us link RTT     not end-to-end [F]
 8    receiver ACKs: CACK + 64-bit SACK       NSCC reads ECN+RTT from      ACK-carried telemetry
      (congestion data echoed to sender)      the ACKs (no CNP packet)     -> no separate CNP [F]
 9    sender NSCC adapts window per CCC       blend of RTT (multi-bit) +   sender-based CC, mandatory
                                              ECN (single-bit), 4-case     on every UET NIC [F]
10    receiver DMA-writes into GPU-B HBM      Direct Data Placement        lossy-friendly: drops OK,
                                              (zero-copy)                  handled by RUD + LLR
11    completion: message-id tagged, next ring step                         collective
```
### Where UET reframes everything
- **Connectionless:** no QP, no handshake — an ephemeral **PDC** is created **0-RTT** by the first packet. Scale cost of connection state disappears. **[F: UEC]**
- **Spray with zero-copy reassembly:** **RUD (Reliable Unordered Delivery)** deliberately delivers out-of-order; the receiver reassembles via a **per-PDC bitmap** and **Direct Data Placement (zero-copy)** into GPU memory — **no reorder buffer**. Per-packet **EV** (entropy value, in the UDP-source-port slot) drives path selection, so one chunk fans across all equal-cost paths. **[F]**
- **Loss model:** UET is **designed for best-effort/lossy** networks — a drop is handled by **RUD/SACK** end-to-end and **LLR** hop-by-hop (a corrupt frame on a marginal link is retransmitted at that link in ~1 µs instead of costing an end-to-end RTT). PFC/CBFC are optional, not required. **[F]**
- **CC feedback:** **NSCC** is sender-based and reads **both ECN and RTT from the ACKs** — there is **no dedicated CNP packet**; congestion telemetry rides back inside normal ACKs. **RCCC** (receiver credits) is optional for incast. **[F]**
- **The contrast to own:** this is the open, UEC-standard analogue to NVIDIA Spectrum-X's spray+TCC ([25-nvidia-spectrum-x.md](./25-nvidia-spectrum-x.md)) and to Meta's no-DCQCN PFC+co-tuning case ([24-vendor-landscape.md](./24-vendor-landscape.md)).

---

## Comparison table (the three journeys)
| Dimension | InfiniBand | RoCEv2 | UET |
|---|---|---|---|
| Header overhead @4096B payload | **0.59 %** (24 B) [E] | 1.42 % (58 B) [E] | **2.39 %** (98 B) [E*] |
| Header overhead @8942B payload | 0.27 % (24 B) [E] | **0.65 %** (58 B) [E] | 1.10 % (98 B) [E*] |
| Payload→packets (1 MB) | ~245 @4KB | ~112 @8942B | ~112 @9k |
| Loss model | **lossless by credits** [F] | **lossless by PFC+ECN policy** [F] | **lossy by design**, RUD+LLR [F] |
| Path behavior | LID fwd; AR optional spray | ECMP 5-tuple; DLB/MRC spray options | **per-packet EV spray** across all EC paths [F] |
| Reordering | none (AR needs HCA OOO) [F] | none w/ ECMP; NIC reorder w/ spray [F/A] | **receiver reassembles, zero-copy, no reorder buffer** [F] |
| CC feedback | BECN/credits (rare) [I] | **ECN-CE + CNP packet** (DCQCN) [F] | **NSCC: ECN+RTT inside ACKs**; RCCC credits optionally [F] |
| Connection model | QP + handshake (RC) [F] | QP + handshake (RC) [F] | **connectionless ephemeral PDC, 0-RTT** [F] |
| Packet-size driver | 4096B MTU max [F] | jumbo 9k (8942B payload) [F] | jumbo ~9k typical [I] |
| Extra control traffic | AETH ACKs on data path | **CNP on separate DSCP** (side-traffic) [F] | ACK-carried telemetry, no CNP [F] |

\* UET overhead values (98 B = Eth14+IPv4(20)+UDP8+PDS12+SES44, matching the RoCEv2 58 B which also includes the 20 B IPv4) are **[E]** computed this session from the [F] header sizes in the constants bank (PDS 12B/16B RCCC, SES 44/32/20B, TSS +12/+16B ICV); a TSS-secured packet adds +28 B (→ 126 B, 3.08 % @4096B). Native-IP mode replaces the 8 B UDP with a 4 B entropy field (94 B, 2.30 % @4096B).

## How to measure it on your own cluster
```text
IB   : ib_read_bw/ib_write_bw (-c for GPUDirect); ibqueryerrors; credit via HOQ/port counters
RoCE : ethtool -S (pfc_xoff_rx, np_cnp_sent, rp_cnp_ignored, out_of_sequence); nccl-tests busbw
UET  : libfabric fi_pingpong; watch SACK/CACK counters and LLR retransmits on the NIC  [A: tooling TBD by vendor]
```
**Rule of thumb [A]:** healthy single-rail AllReduce busbw should be ~0.9–0.95× link (the ring-busbw saturation; [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md)); if far below, suspect entropy (RoCE ECMP) or GDR-not-engaged, not the transport.

## Cross-links
- [09-infiniband-packet-format.md](./09-infiniband-packet-format.md) — full IB header/opcode map for Journey 1.
- [16-roce-fundamentals.md](./16-roce-fundamentals.md) — RoCEv2 packet layout behind Journey 2.
- [23-roce-lossless-fabric-design.md](./23-roce-lossless-fabric-design.md) — the lossless policy (PFC/ECN) Journey 2 depends on.
- [31-uetch-deep-dive.md](./31-uetch-deep-dive.md) — UET PDC/RUD/NSCC/LLR internals for Journey 3.
- [32-uetch-congestion-and-in-network.md](./32-uetch-congestion-and-in-network.md) — NSCC/RCCC + in-network collectives.
- [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md) — ECMP entropy + MRC for Journey 2's path choices.
- [25-nvidia-spectrum-x.md](./25-nvidia-spectrum-x.md) / [24-vendor-landscape.md](./24-vendor-landscape.md) — the closed-loop and open alternatives.
- [55-cheat-sheet.md](./55-cheat-sheet.md) — quick references.


## Key Takeaways
1. One 1 MB gradient chunk through a ring AllReduce looks identical at the application layer across
   all three fabrics (NCCL posts a send, the NIC DMAs the GPU, the peer DMA-writes into its GPU) —
   the wire differs sharply, so the journey is where you find each fabric's real cost.
2. InfiniBand is lossless-by-credits with 24 B headers (~245 packets @4096B): a congested egress
   advertises zero credit and backpressure stalls the sender; forwarding is by LID from the
   SM-programmed LFT, and the only reordering comes from optional adaptive routing.
3. RoCEv2 is lossless-by-PFC-policy with 58 B UDP/IP headers (~112 packets @8942B): ECN marks
   before the PFC XOFF backstop, the receiver returns a CNP on a separate DSCP 48, and the fixed
   dst port 4791 + few QPs create the ECMP entropy problem.
4. UET is lossy-by-design: an ephemeral PDC is set up 0-RTT, per-packet EV spraying fans one chunk
   across all equal-cost paths, RUD reassembles out-of-order with zero-copy and no reorder buffer,
   and NSCC reads ECN+RTT from the ACKs — so there is no separate CNP packet.
5. The comparison is quantified by header math [E] — IB 24 B/0.59%, RoCEv2 58 B/1.42%, UET 98 B/
   2.39% @4096B (126 B with TSS) — but loss model and CC feedback (credits vs ECN+CNP vs
   ACK-carried NSCC), not header bytes, are what actually differ.

## Related
- [IB packet format](./09-infiniband-packet-format.md) — the complete IB header/opcode map behind Journey 1.
- [RoCE fundamentals](./16-roce-fundamentals.md) — RoCEv2 packet layout behind Journey 2.
- [Lossless RoCE design](./23-roce-lossless-fabric-design.md) — the PFC/ECN lossless policy Journey 2 depends on.
- [UET deep dive](./31-uetch-deep-dive.md) — UET PDC/RUD/NSCC/LLR internals for Journey 3.
- [RoCE CC & load balancing](./22-roce-cc-and-load-balancing.md) — ECMP entropy and MRC for Journey 2's path choices.
- [Cheat sheet](./55-cheat-sheet.md) — quick reference across all three journeys.

## References
- IBTA / RDMA header-format documentation — LRH+BTH+ICRC 24 B IB sub-net header.
- IETF RoCEv2 Fast-CNP draft — 58 B RoCEv2 header, UDP 4791, CNP/ECN signaling.
- NCCL user-guide environment docs — NCCL ring, GPUDirect behavior.
- UEC 1.0 spec and author paper (arXiv:2508.08906) — UET PDS/SES/EV/PDC/RUD/NSCC/LLR/TSS.
- NVIDIA Spectrum-X and Meta RoCE references — closed-loop spray+TCC and no-DCQCN alternatives.
- [E] Constants used: IB hdr 24 B (0.59% @4096B, 0.27% @8942B); RoCEv2 hdr 58 B (1.42% @4096B,
  0.65% @8942B); UET hdr 98 B = Eth14+IPv4(20)+UDP8+PDS12+SES44 (2.39% @4096B, 1.10% @8942B), TSS +28 B →
  126 B; 1 MB → ~245 IB pkts / ~112 RoCEv2 & UET pkts; ~20 µs serialization @400G (NDR400) and
  ~10 µs @800G.
