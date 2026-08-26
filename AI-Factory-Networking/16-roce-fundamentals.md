# RoCE Fundamentals
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: IETF draft-xiao-rtgwg-rocev2-fast-cnp-03, IBTA RoCE spec / BTH-iCRC via NVIDIA forum, Linux rdma-core man pages, NVIDIA WinOFDEV RoCE doc; overhead arithmetic from the section constants bank (2026-08-25).

## 30-Second Explanation
**RDMA over Converged Ethernet (RoCE)** runs the InfiniBand RDMA transport on top of
Ethernet instead of an IB link layer. There are two flavors. **RoCEv1** stuffs the IB headers
straight into an L2 Ethernet frame with **Ethertype 0x8915** — it is confined to one broadcast
domain and is **not routable**. **RoCEv2** encapsulates the same IB transport inside
**UDP/IP (well-known destination UDP port 4791)**, which makes it **routable** and gives
routers/switches something (src IP, dst IP, UDP port) to hash for ECMP [F: IETF draft +
Wikipedia/IBTA RoCE]. The packet is **Ethernet(14) | IPv4(20) | UDP(8) | BTH(12) | payload |
ICRC(4)** = **58 B/packet** of overhead [E: constants bank] — 22.66% of a 256 B payload,
1.42% at 4 KB [E]. Crucially, only the *encapsulation* changes: the IB transport (QP/PSN/
RC semantics, BTH) rides inside UDP essentially unchanged, which is why all the RDMA
knowledge from [03-rdma-fundamentals.md](./03-rdma-fundamentals.md) and [09-infiniband-packet-format.md](./09-infiniband-packet-format.md) carries
over. Because dst-port is fixed at 4791, **entropy for ECMP comes from the UDP source port,
set per-QP** (`mlx5dv_modify_qp_udp_sport`) — not a fixed "256" bank [F: man page; UNVERIFIED
for 256]. RoCE is the Ethernet AI-fabric workhorse ([17-why-roce-is-harder.md](./17-why-roce-is-harder.md), [21-dcqcn.md](./21-dcqcn.md)).

## What
RoCE is a **two-layer stack** — an IB transport riding an Ethernet/IP data plane.

| Flavor | Encapsulation | EtherType / dst port | Routable? | Typical use |
|---|---|---|---|---|
| **RoCEv1** | IB transport in Ethernet L2 frame | Ethertype **0x8915** | **No** (single L2 broadcast domain) | legacy / intra-DC, same-subnet |
| **RoCEv2** | IB transport in **UDP/IP** (IPv4 or IPv6) | **dst UDP 4791** (well-known) | **Yes** (L3, ECMP) | production AI fabrics |

RoCEv2's defining move is the UDP envelope: "RoCEv2 runs the InfiniBand transport layer over
UDP and IP protocols on an Ethernet network" [F: IETF draft-xiao-rtgwg-rocev2-fast-cnp-03].

## Why
1. **Routability.** RoCEv1 cannot cross a router (it has no IP/UDP layer), so multi-subnet or
   multi-rack routed fabrics need RoCEv2 [F: IETF draft].
2. **Stateless identification.** Port 4791 lets switches/platforms recognize RoCEv2
   without parsing IB headers (line-rate, no deep inspection) [F: IETF draft; [I]].
3. **ECMP / load-spreading.** RoCEv2 gives L3 the standard hash fields (5-tuple) that L2/L3
   forwarding uses — the source-port entropy (below) is what actually spreads flows [F: man page].
4. **Why RoCE exists at all.** It lets ordinary (carefully configured) Ethernet carry RDMA,
   versus building a separate IB fabric. The tradeoff: Ethernet is lossy by default, so RoCE
   needs PFC+ECN/DCQCN to approximate IB's native losslessness (`./17`, `./19`, `./21`). [I]
5. **Scale-out symmetry.** AI collectives are east-west and synchronized; every rank must be
   reachable at line rate. RoCEv1's single broadcast domain caps that; RoCEv2's routable
   UDP/IP envelope lets the fabric be a multi-rack/multi-pod Clos exactly like IB
   ([42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md)). [I]

## How
The IB transport heads + semantics are reused; only the lower layers change:
```text
InfiniBand:  LRH(8) | [GRH] | BTH(12) | [ext] | payload | ICRC(4)    (native fabric)
RoCEv1:      Eth(14,0x8915) | BTH(12) | ... | payload | ICRC(4)      (L2 only)
RoCEv2:      Eth(14) | IPv4(20)/IPv6(40) | UDP(8, dst 4791) | BTH(12) | ... | ICRC(4)
```
The **IB Base Transport Header (BTH, 12 B)** carries opcode, P_Key, dest QP, PSN; the
**invariant CRC (ICRC, 4 B)** protects the invariant fields end-to-end [F: IBTA via NVIDIA
forum]. Those are identical on IB and RoCE — the UDP/IP/Ethernet layers are purely additive
carrier.

## Packet flow — complete RoCEv2 frame with byte offsets
```text
Byte offset  0               14              34            42             ...
             │ Ethernet      │ IPv4 (20B)   │ UDP (8B)     │ IB BTH (12B) │...
             │ 14B           │               │              │
             └───────────────┴───────────────┴──────────────┴──────────────
 EtherType=0x0800 (IPv4) / IP proto=17 (UDP) / UDP dst port=4791 (RoCEv2; RoCEv1 uses EtherType 0x8915, no IP/UDP)
  0      14      34      42      54            ...payload...        +4
  | Eth  |  IPv4 |  UDP  |  BTH  | ext hdrs |   payload             | ICRC |
  |  14  |  20   |   8   |  12   | (0..n)   |   ...                |  4   |

Overhead (IPv4 path, no ext hdrs) = 14+20+8+12+4 = 58 B/packet          [E: bank]
Overhead @ 256 B payload  = 58/256 = 22.66%                             [E: bank]
Overhead @ 4 KB payload   = 58/4096 = 1.42%                             [E: bank]
```
Byte layout corroborated by the IETF Fast-CNP figure (Ethernet / IP / UDP / IB Transport
Header / payload / iCRC) [F: IETF draft]. With IPv6, IPv4's 20 becomes 40 → 78 B/packet.

### How the receiver finds it
The NIC/switch classifies on EtherType→IP→UDP dst port 4791, then hands the rest to the RDMA
engine, which parses BTH (QP, PSN, opcode), checks the ICRC, and places data per the RDMA
operation. The UDP payload *is* the IB packet (BTH onward), unmodified.

## The IB payload does not change — a BTH walkthrough
RoCEv2's genius is that the transport looks byte-for-byte like native IB's once you get past
UDP. The **BTH (12 B)** fields are the same ones [09-infiniband-packet-format.md](./09-infiniband-packet-format.md) describes
for IB [F: IBTA vol-1; NVIDIA forum]:
```text
BTH (12 B), re-used verbatim inside RoCEv2 UDP:
  bit 0..7      Opcode            (SEND/RDMA_WRITE/RDMA_READ/ATOMIC/ACK/CNP ...)
  bit 8         Solicited Event   (SE)
  bit 9         MigReq
  bit 10..11    PadCount          (pads payload to 4 B multiple)
  bit 12..15    Transport Version
  bit 16..31    P_Key             (partition key — same role as ./12)
  bit 32..55    Destination QP    (QP number at the receiver) [+ Dest QP == self]
  bit 56..63    Acknowledgment Request + reserved
  bit 64..95    PSN               (packet sequence number — the retransmit counter)
```
Why this matters ([I: derived]): because QP/PSN/P_Key/opcode semantics are preserved, the
entire RDMA stack — memory keys, one-sided WRITE/READ, RC ordering/retransmit, partition
checking — works over Ethernet exactly as over IB. The **only** differences introduced by RoCE
are (1) the lower-layer addresses (MAC/IP/UDP instead of LID) and (2) the losslessness mechanism
(Ethernet PFC + ECN/DCQCN policy versus IB's native credits — see `./17`, `./20`, `./21`). The
**ICRC (4 B)** is computed over the *invariant* fields, end-to-end, just like IB (VCRC is
per-link and does not apply because Ethernet has its own FCS/CRC). [F: IBTA via NVIDIA forum;
[I] analysis]

## Packet journey — one RDMA WRITE over RoCEv2, numbered
```text
 SENDER NIC/GPU                                            RECEIVER NIC/GPU
 (1) App posts RDMA WRITE WQE; NCCL/verbs registers GPU MR
 (2) NIC DMAs payload from GPU HBM (GPUDirect, ./15)
 (3) NIC builds headers: Eth | IPv4 | UDP(dst 4791, sport per-QP)
        + BTH{opcode, P_Key, DstQP, PSN} | RETH{addr,rkey,len} | payload
 (4) NIC computes ICRC over invariant fields; marks DSCP (26, RoCE prio)
 (5) Drives frame onto wire @ line rate
 (6) [Fabric] switches classify dst UDP 4791; hash 5-tuple (incl. sport) for ECMP;
         apply lossless/ECN marking per DSCP→TC queue (PFC/ECN), see ./20 ./21
 (7) RECEIVER NIC classifies 4791; strips Eth/IP/UDP
 (8) Validates BTH: DstQP, P_Key, PSN, opcode; checks ICRC
 (9) NIC DMAs payload into GPU HBM at RETH address (GPUDirect)
(10) Completes WQE → CQE; app polls completion  (./03)
```

### Overhead at a glance [E: constants bank]
The bank defines **overhead % = header bytes / payload bytes** (stating the denominator once).
On the IPv4 path the headers are 58 B/packet, so:
| Payload | Total frame | Overhead % | Note |
|---|---|---|---|
| 256 B   | 314 B   | **22.66%** | [E] bank — small-message handle is poor |
| 1500 B  | 1558 B  | **3.87%**  | [E] bank — no jumbo |
| 4096 B  | 4154 B  | **1.42%**  | [E] bank — typical IB-style MTU |
| 8942 B  | 9000 B  | **0.65%**  | [E] bank — jumbo frame |
The takeaway [I]: at AI's 256 B–4 KB message range you pay 22.7%→1.4%; batching to 4 KB (or
jumbo 9 KB) amortizes the encapsulation. Compare IB intra-subnet, 24 B/packet → 9.38% @256 B,
0.59% @4 KB [E: bank] — RoCE's extra ~34 B (Eth+IP+UDP vs LRH) is the routability cost.

## RoCEv1 in detail
RoCEv1 predates the routable design and is essentially IB-with-only-the-LRH-replaced. Instead
of the IB **LRH (8 B)**, the frame opens with an **Ethernet header carrying EtherType 0x8915**
(the IBA EtherType), then the **GRH (40 B, Global Route Header — required, even intra-subnet,**
because there is no LID layer to route on), the **BTH**, optional ext headers, payload, ICRC
[F: IBTA RoCE / [I] from header requirements]. Because there is no IP/UDP layer, **there is
nothing to route on across L3**: it stays inside one L2 broadcast domain.
```text
RoCEv1 frame:  Eth[14, 0x8915] | GRH[40] | BTH[12] | ...ext... | payload | ICRC[4]
RoCEv2 frame:  Eth[14, 0x0800] | IPv4[20] | UDP[8, 4791] | BTH[12] | ... | ICRC[4]
```
RoCEv2 replaced the mandatory 40 B GRH with a routable **IPv4/6 + UDP(8)** header — shorter in
the common IPv4 case (20+8=28 B vs 40 B GRH) and, decisively, *routable*. That is why production
AI fabrics are RoCEv2 [F: IETF draft; [I] comparison]. Practical note: a GID-index of 0 on a
Mellanox HCA selects the RoCEv1 (link-local/GRH) encoding, and index 3 typically selects the
RoCEv2 global GID — a classic v1/v2 mix-up fires when a routable fabric is expected but only the
L2 flavor is available ([F: NCCL GID doc; [I]] and `./45-/./46-` troubleshooting).

## GPU relationship
RoCE is the RDMA carrier AI NICs (ConnectX-7/8, BlueField) use on Ethernet. GPU gradients
walk the same NCCL path as [15-gpudirect-rdma-nccl-infiniband.md](./15-gpudirect-rdma-nccl-infiniband.md) (PyTorch →
torch.distributed → NCCL → NET → verbs → ConnectX), except the wire is Ethernet+UDP instead of
IB LRH. GDR applies identically: the NIC DMAs GPU HBM over PCIe, and the en/decapsulation
(Eth/IP/UDP, BTH, ICRC) is handled in NIC silicon. The **GID index** NCCL uses
(`NCCL_IB_GID_INDEX`, often 3 for RoCEv2 global GID) selects which IPv6/global GID on the HCA
— a v1 vs v2 mismatch is a classic failure [F: NCCL docs; [I]]. RoCE inherits the IC **RC** selective-retransmission cost on loss (the sender retransmits
the missing message(s) on a timer; no bulk GBN flood) — which is why it wants lossless
Ethernet [F: IRN SIGCOMM'18; see [17-why-roce-is-harder.md](./17-why-roce-is-harder.md)].

## DSCP marking at the source — the classification chain
RoCE's lossless/congestion design keys entirely off how the source marks the packet and how
the switch maps that to a queue [F: NVIDIA Onyx/min.io lossless-DSCP guides]. The chain is:
```text
source NIC marks DSCP (e.g. 26, AF31, RoCE priority)   [F: vendor default]
    → switch "trust DSCP" maps DSCP→Traffic Class→priority queue
    → that priority queue is enabled for PFC (lossless) and ECN-marked
    → the SAME DSCP must match host↔switch, or nothing aligns (pause storms / no ECN)
CNP (congestion-notification packet) rides its own high priority: DSCP 48 / PCP 6 [F: vendor]
```
The three knobs must agree: **DSCP (host), TC (switch), priority/PFC class (switch)**. This is
the standard Mellanox mapping: **RoCE DSCP 26 → priority 3**, **CNP DSCP 48 → priority 6** [F:
vendor spec, widely reproduced]. Because ECN marking is per-queue/DSCP and PFC is per-priority,
a misalignment between K-max (ECN) and the PFC threshold is the single most common RoCEv2
misconfig (→ [20-ecn-wred.md](./20-ecn-wred.md), [21-dcqcn.md](./21-dcqcn.md)).

## Why UDP (and why the IB transport stays unchanged)
RoCEv2 deliberately uses **UDP, not TCP**. Reasons [I: standard analysis from RoCE design]:
1. **TCP's own reliability/ordering is redundant and harmful** — IB's RC transport already
   sequences (PSN) and retransmits; stacking TCP's window/congestion on top adds state and
   latency for nothing.
2. **UDP is the minimum routable envelope** — IP provides L3 reachability; UDP provides a
   stateless demultiplexing port + a hashable field for ECMP, with no transport baggage.
3. **Headers stay small** — UDP(8) costs 8 B versus TCP's 20 B+.
So the IB transport is "essentially unchanged inside UDP": the BTH/QP/PSN/RC semantics are
carried verbatim (the BTH walkthrough above), and the NIC's RDMA engine treats UDP/IP as the
lower-layer "carrier," exactly as it treats Ethernet's MAC header on RoCEv1. The only
transport-related additions are the port-4791 classification and the source-port entropy for
ECMP — both *forwarding* aids, not transport state. This is what the IETF draft means by "Runs
the InfiniBand transport layer over UDP and IP" [F: IETF draft; [I] analysis].

## Design — source-port entropy, ECMP, and DSCP

### UDP source-port entropy per QP (the ECMP key)
RoCEv2's **destination** port is fixed (4791), so the only *flow-varying* field a hashing
switch can spread on (besides IPs) is the **UDP source port**. Real drivers derive it from the
QP/LIDs: NVIDIA WinOFDEV documents **`UDP.SrcPort = (SrcPort XOR DstPort) OR 0xC000`** —
forcing the two high bits and producing a large, per-QP value space [F: vendor spec,
WinOFDEV]. The kernel/rdma-core programmatic knob is **`mlx5dv_modify_qp_udp_sport()`**: "The
UDP source port is used to create entropy for network routers (ECMP), load balancers and
802.3ad link aggregation switching that are not aware of RoCE IB headers." [F: man page
`mlx5dv_modify_qp_udp_sport(3)`]
```text
● Do NOT quote "256 UDP source ports" as the entropy set — UNVERIFIED (research notes could
  not confirm it from any primary source). The socket is 16-bit; drivers derive a per-QP
  value (e.g. the XOR|0xC000 form), so the candidate space is far larger than 256 [F: vendor
  spec; UNVERIFIED for "256"].
● Real constraint: a training job keeps few QPs, so it presents few distinct source ports —
  ECMP entropy is inherently low and hash collisions polarize flows [F: Meta Engineering
  "RoCE for distributed AI training"; [I]].
● Why polarization bites AI: ECMP hashes the 5-tuple, but RoCE's dst port is fixed (4791), so
  entropy collapses to (src IP, dst IP, src UDP port) — and a single rank has only its few QPs.
  Several elephant flows can hash to one uplink, saturating it while peers idle: busbw drops
  with no PFC storm, the classic "no loss yet slow" symptom [F: Meta; [I]]. Mitigations: more
  per-QP sport entropy, flowlet-based switching, or MRC-style endpoint multipathing
  (`./22-roce-cc-and-load-balancing.md`).
```
### DSCP marking at source
The source NIC marks each RoCE packet's DSCP/Traffic Class; the switch uses DSCP→TC→priority
to (a) assign it to the PFC-enabled (lossless) or lossy priority and (b) apply ECN marking
([20-ecn-wred.md](./20-ecn-wred.md)). Mellanox default: **RoCE DSCP 26 → priority 3**, **CNP DSCP 48 → priority
6** [F: vendor spec, widely reproduced]. Marking must be identical host↔switch or DCQCN+PFC
silently degrades [F; [E]-style operational truth]. NCCL sets the TC via `NCCL_IB_TC`.

## Tuning
- **MTU**: RoCE commonly runs jumbo 9000/9216 on every RoCE-facing port [F: NVIDIA/min.io
  guide]. At MTU 9000 the ~8954 B payload yields overhead ≈0.6% [I: derived; research-roce §10].
- **Source-port entropy**: prefer per-QP sport derivation / enough QPs; re-seed hashing on
  storms. ECMP polarization → vary sport or add flowlets (see [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md)).
- **DSCP/TC alignment**: host DSCP must equal switch DSCP→priority mapping; CNP needs its own
  high-priority DSCP.
- **GID index** on the HCA for v2 global routing (`NCCL_IB_GID_INDEX`).
- Headers overhead tolerance: for small messages, 58 B/packet matters (22.66% @256 B [E]);
  for 4 KB+ payloads it's ~1.4% [E] — batch into 4 KB where possible.

## Troubleshooting
- **Cross-subnet hang** → GID index set to RoCEv1 (idx 0) instead of v2 global (idx 3): fix
  `NCCL_IB_GID_INDEX`/perftest `-x`.
- **Packets dropped under burst but "link up"** → PFC not on the RoCE priority, or DSCP→TC
  mismatch.
- **busbw collapses, no PFC storm** → ECMP polarization (hash collision): few distinct sport
  → re-hash / per-QP sport.
- **ICRC errors** (`rx_icrc_encapsulated`) → corruption on the wire, cable/PHY issue.
- Counters to watch: `np_cnp_sent`, `np_ecn_marked_roce_packets`, `rp_cnp_handled`/`ignored`
  (rising ignored = CC not configured), `pfc_xoff_rx` (→ [21-dcqcn.md](./21-dcqcn.md), `./45`/`./46`).

## Comparison — RoCEv1 vs v2 vs native IB
| Property | RoCEv1 | RoCEv2 | Native IB |
|---|---|---|---|
| Carrier | Ethernet L2 | UDP/IP | IB link (LRH/credits) |
| Routable | no | yes | within subnet (LID); GRH between |
| ID for forwarding | EtherType 0x8915 | dst UDP 4791 | LID (LRH) |
| ECMP entropy | via L2 hashing (poor) | UDP **source port** | LMC/multi-LID, SL, AR |
| Per-packet overhead | (Eth+IB) | 58 B/IPv4 [E] | 24 B intra-subnet [E] |
| Losslessness | needs PFC | needs PFC + ECN/DCQCN | native credits |
| Typical AI use | legacy | production Ethernet AI fabric | reference AI fabric |

## Lab
1. **Detect GID/flavor** — `show_gids` on the mlx5 device; run `ib_write_bw -x <gid_idx>` and
   observe success only on the v2 index for cross-subnet.
2. **Show the 58 B** — `tcpdump -i <if> udp port 4791 -XX` and count the bytes up to the IB
   BTH; compare overhead at 256 B vs 4 KB payloads.
3. **Entropy knob** — `man mlx5dv_modify_qp_udp_sport`, then vary the QP's source port and watch
   switch ECMP hashing spread flows.
4. **Overhead math** — compute 58/256=22.66% vs 58/4096=1.42% [E] and reason when jumbo
   (≈0.6% @ 9 KB) is worth it.
(More labs: [53-learning-labs.md](./53-learning-labs.md).)

## Key Takeaways
1. RoCEv1 = IB over L2 (EtherType 0x8915), **not routable**; RoCEv2 = IB over **UDP/IP, dst
   port 4791**, routable [F: IETF/IBTA].
2. The packet is Eth14|IPv4 20|UDP 8|BTH 12|payload|ICRC 4 = **58 B** overhead [E].
3. **Only the carrier changes** — the IB transport (BTH/QP/PSN/RC) rides inside UDP unchanged.
4. ECMP entropy = **UDP source port per QP** (`mlx5dv_modify_qp_udp_sport`); "256 ports" is
   UNVERIFIED [F: man page; vendor XOR|0xC000 form].
5. Overhead: 22.66% @256 B ⇒ 1.42% @4 KB [E] — batch to amortize.
6. DSCP-from-source drives lossless + ECN; align host↔switch (RoCE 26/prio3, CNP 48/prio6) [F].

## Related
- [17-why-roce-is-harder.md](./17-why-roce-is-harder.md) — retransmit cost, incast, pause storms.
- [21-dcqcn.md](./21-dcqcn.md) — the ECN/CNP congestion-control loop.
- [20-ecn-wred.md](./20-ecn-wred.md) — ECN marking; [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md) — PFC risks.
- [09-infiniband-packet-format.md](./09-infiniband-packet-format.md) — BTH/ICRC the UDP payload carries.
- [03-rdma-fundamentals.md](./03-rdma-fundamentals.md) — the verbs model both ride on.
- [51-complete-packet-journeys.md](./51-complete-packet-journeys.md) — the same gradient chunk on IB vs RoCEv2 vs UET.

## References
- IETF draft-xiao-rtgwg-rocev2-fast-cnp-03 (RoCEv2-over-UDP + UDP 4791 + packet figure):
  datatracker.ietf.org/doc/html/draft-xiao-rtgwg-rocev2-fast-cnp-03 [F].
- IBTA RoCE spec (v1 EtherType/BTH-iCRC): infinibandta.org; BTH 12B / iCRC 4B via
  forums.developer.nvidia.com/t/rocev2-specification/357391 [F].
- Kernel/rdma-core: man7.org/linux/man-pages/man3/mlx5dv_modify_qp_udp_sport.3.html [F: man page].
- NVIDIA WinOFDEV RoCEv2 (UDP.SrcPort formula): networking-docs.nvidia.com/winofdocumentation/55054000/rocev2 [F: vendor spec].
- Meta Engineering, "RoCE networks for distributed AI training at scale":
  engineering.fb.com/2024/08/05/data-center-engineering/roce-network-distributed-ai-training-at-scale [F].
- [E] overhead rows and RoCEv2 hdr bytes from the section constants bank (computed 2026-08-25).
