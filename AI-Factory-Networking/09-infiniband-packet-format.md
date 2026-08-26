# InfiniBand Packet Format: Headers, Opcodes, and the Wire Layout
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: IBTA Vol 1 — `packet.transport.ib` manpage, IB QoS/DOCA docs, NVIDIA credit-loops & security docs; arithmetic from section constants bank (2026-08-25).

## 30-Second Explanation
An InfiniBand packet is a short, fixed-ish header stack in front of a payload, surrounded by two integrity checks. The **LRH (8 B)** is always first and is consumed/rewritten on every hop. An optional **GRH (40 B)** appears when the packet must cross a router (inter-subnet). Then the **BTH (12 B)** — the transport header every QP operation carries — names the opcode, the destination QP, and the packet sequence number (PSN). Each operation family bolts on its own extended transport header: **RETH (16 B)** for RDMA READ/WRITE, a **DETH (8 B)** for unreliable datagrams, an **AETH (4 B)** on acknowledgements (carrying the ACK/NAK syndrome), **AtomicETH (28 B)** for atomics, an **IETH (4 B)** for invalidation, and 4 B of **immediate data** where allowed. Finally **ICRC (4 B)** protects the packet end-to-end and **VCRC (2 B)** protects each link hop. An RDMA READ request is genuinely small (LRH+BTH+RETH = 36 B; 76 B with the 40-B GRH for
global routing); the full global+transport header stack tops out around 104 B before payload. The whole thing is why **IB's intra-subnet header is only 24 B** (LRH+BTH+ICRC) and why RoCEv2 pays 58 B for the privilege of living in Ethernet [E: constants bank].

## What
### The boxed byte-offset layout
Byte offsets measured from the first byte of the transport header as seen on the wire. LRH starts at byte 0; GRH is present only when the LRH Global bit is set (shown at offset 8); BTH follows at 8 (local) or 48 (global); per-op ext headers come next; then payload (≤ 4096 B), then ICRC and VCRC [F: https://manpages.ubuntu.com/manpages/noble/man3/packet.transport.ib.3.html; sizes part of the constants bank / research notes].

```text
 LOCAL (one subnet)                                    GLOBAL (across a router)
 byte  0       12          32        ...              byte  0       8             48
       | LRH 8 |  BTH 12   | (ext)   | payload | ICRC4|VCRC2
       0      8      20     32        ...              0      8       48           60     ...
                                                                                    | GRH 40 |
                                                                                8       48

       0            8     16      24      32      40      48      56      64
       |            |      |       |       |       |       |       |       |
  0─── | LRH (8B)  | BTH (12B)         | RETH (16B)               | payload ─...
  8─── ...(GRH here when Global)...
       ── Transport envelope that repeats shaping every packet:
       LRH  8  : DstLID, SrcLID, SL(4b), LNH/global bit, VL, packet length, opcode-ish routing
       BTH  12 : opcode, Solicited, MigReq, PadCount, TVer, P_Key(16b), DestQP(24b), AckReq, PSN(24b)
       ICRC 4  : invariant, computed over invariant fields, checked end-to-end (not per hop)
       VCRC 2  : variant, computed over variant fields, checked+stripped per link
```

Full header inventory and byte sizes [F: https://manpages.ubuntu.com/manpages/noble/man3/packet.transport.ib.3.html]:

| Header | Size (B) | Present for | Carries |
|---|---|---|---|
| LRH | 8 | **every** packet | DstLID, SrcLID, SL, VL, packet length, global/link-next-header bit, header/version |
| GRH | 40 | **only Global** (router-bound) | source + dest GID (128-bit each), next header, hop limit, traffic class — mirrors IPv6 |
| BTH | 12 | **every** packet | opcode, solicit, MigReq, PadCount, Transport Version, **P_Key**, **DestQP**, **AckReq**, **PSN** |
| RETH | 16 | RDMA READ/WRITE request | virtual address (64b) + **rkey** + DMA length (32b) |
| AETH | 4 | ACK/NAK, read-response | **syndrome** (ACK/NAK type) + MSN (message seq) |
| AtomicETH | 28 | ATOMIC request | remote operands (old/new for CAS, add for FA) |
| AtomicAckETH | 8 | ATOMIC ACK | original remote value |
| DETH | 8 | UD (datagram) | **Q_Key** + source QP number |
| IETH | 4 | SEND_WITH_INVALIDATE | remote key to invalidate |
| Immediate | 4 | *_WITH_IMMEDIATE | 32-bit application immediate token |
| ICRC | 4 | **every** packet | invariant CRC, end-to-end |
| VCRC | 2 | **every** packet | variant CRC, per link hop |
| Payload | ≤ 4096 | data ops | message bytes (MTU 256–4096) |

## Why
Three design goals explain the shape [I: architecture rationale]:
1. **Smallest fast header for the 99% case.** Nearly all AI traffic is intra-subnet, LID-routed, RC. That path needs only LRH + BTH + ICRC = **24 B** of overhead [E: constants bank]. The big GRH is add-on *only when needed*, so the common case stays lean.
2. **Separate integrity domains.** **ICRC is invariant** — computed over header fields that don't change hop-to-hop, verified end-to-end (catches any upstream tamper/corruption after transport). **VCRC is variant** — computed over the hop-local LRH, checked and regenerated at each link (catches serialization corruption per link). Splitting them means a router can legally rewrite the LRH/VCRC without invalidating the end-to-end ICRC [F: manpage].
3. **Transport state is carried in the header, not a connection table lookup.** The LRH's DLID routes each hop; the BTH's DestQP + PSN let the destination NIC demux to the right QP and ordering state — switches never read the BTH, which is what makes a switch a stateless forwarder and keeps QP state at the HCAs [I].

## How — which headers appear per operation
LRH (+ optional GRH) and BTH are always present; the table shows the extra extended-transport headers [F: names/sizes from manpage; the "which header per op" mapping is [F] opcode semantics / [I] where inferred]:

| Operation | Extra headers (beyond LRH+BTH) | Payload? | Response/ACK carries |
|---|---|---|---|
| SEND (FIRST/MIDDLE/LAST) | — | yes | (RC) AETH ACK |
| SEND_LAST_WITH_IMMEDIATE | Immediate (4) | yes + imm token | AETH ACK |
| SEND_LAST_WITH_INVALIDATE | IETH (4) | yes | AETH ACK |
| RDMA_WRITE (FIRST/MIDDLE/LAST) | RETH (16) | yes (data to remote addr) | (imm/ack per last) |
| RDMA_WRITE_LAST_WITH_IMMEDIATE | RETH (16) + Immediate (4) | yes | AETH ACK |
| RDMA_READ_REQUEST | RETH (16) | **no** (request only) | response carries payload |
| RDMA_READ_RESPONSE_* | — (payload on response) | yes (returned) | — (it *is* the response) |
| ATOMIC COMPARE_SWAP / FETCH_ADD | RETH (16) + AtomicETH (28) | no | AtomicAckETH (8, original val) + AETH |
| ACK / NAK (RC) | AETH (4) | no | — |
| UD SEND_ONLY | DETH (8) | yes | — (unreliable, no ack) |
| UD *_WITH_IMMEDIATE | DETH (8) + Immediate (4) | yes | — |
| UD *_WITH_INVALIDATE | DETH (8) + IETH (4) | yes | — |
| CNP / BECN | — | no | congestion notification |

Header-cost intuition: an **RDMA READ request** = LRH(8) + BTH(12) + RETH(16) = **36 B** local (40 B with GRH). A **UD datagram with immediate** = LRH(8) + BTH(12) + DETH(8) + Immediate(4) = 32 B (+40 B GRH if global). The **largest** transport stack (global atomic) approaches LRH(8)+GRH(40)+BTH(12)+RETH(16)+AtomicETH(28) = 104 B before ICRC/VCRC [E-derivable from the size table]. All of these are dwarfed by the ≤ 4096-B payload, which is why IB overhead at full MTU is under ~1.6% [E: constants bank; e.g. local READ-with-GRH = 76/4096 ≈ 1.86% worst case, typical WRITE ≈ 24/4096 ≈ 0.6%].

### BTH fields (the header every QP op shares)
From [F: https://manpages.ubuntu.com/manpages/noble/man3/packet.transport.ib.3.html]:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
| opcode(8) | TVer(4) | Pad(3) | R(1) | P_Key(16b)      | ... |
|          DestQP(24b)          |Ack|      PSN(24b)             |
+---------------------------------------------------------------+
```
- **opcode** — which operation this packet is (see list below).
- **Solicited Event (S)** — marks a solicit event (partner may arm a notification).
- **MigReq / padcount / Transport Version** — migration support, padding after 4-B boundary, header version.
- **P_Key** — 16-bit partition key; the receiver validates it (full vs limited member) at the QP and the switch can enforce it at the port [F: NVIDIA security docs].
- **DestQP** — destination QP number (used by RC/UC; in UD the DETH additionally carries Q_Key + source QPN).
- **Acknowledge Request (AckReq)** — asks the peer to return an ACK when the QP's allowed timer conditions are met (in-order pacing of ACKs).
- **PSN** — 24-bit Packet Sequence Number; RC uses it for ordering + retransmission; the ACK's AETH carries the MSN (message sequence number); the BTH PSN is the ACK's own PSN.

## Packet flow — an RDMA READ end to end
```text
Host A (issuer)                              Switch(es)               Host B (target)
post RDMA_READ{rkey,addr,len} ─ doorbell
 NIC: LRH+BTH{RdmaRRequest,PSN}+RETH
  ──────────────────►  LID-routed, LRH hops  ──►  [BTH+PSN matched to QP m]
                                                        NIC validates rkey/addr/range
                                                        DMAs data out of B's memory
  ◄────────────────── read-response FIRST/MIDDLE/LAST ──  LRH+BTH{Resp}+AETH+payload
  NIC reassembles by PSN, DMAs into A's buffer
  posts CQE (completion)                                    (ACK per pacing rule)
```
Step cost: 1 round trip of header overhead (1 request + 1 response; the request is tiny: 36 B), and the **payload travels only once** — READ is a pull, so it costs one request + one response, no receiver WQE [I]. Contrast SEND where the request *is* the data.

## GPU relationship
NCCL's cross-GPU traffic is dominated by RC **RDMA_WRITE** (gradient push, checkpoint writes, KV transfer) and some **RDMA_READ** (ZeRO pulls). These ride the headers above; the GPU memory is the SGE source/destination. The practical GPU-facing facts [I]:
- **Small-message overhead:** at 256-B payload, IB pays **9.38%** header overhead [E: constants bank]; at 4096 B **0.59%** [E]. So GPU collectives that decompose into many small WRs eat more header fraction than bulk data.
- **IMMEDIATE data** is the classic "ack now" nudge — many collectives use WRITE_WITH_IMMEDIATE so the target CPU/GPU gets woken without a separate message [see [03-rdma-fundamentals.md](./03-rdma-fundamentals.md)].
- **P_Key in BTH** is how a multi-tenant GPU cluster keeps job/tenant partitions from talking to each other even on shared switches [F: NVIDIA security docs; see [12-infiniband-routing-topology-partitions.md](./12-infiniband-routing-topology-partitions.md)].

## Design — the opcode list
BTH opcodes, standard names [F: https://manpages.ubuntu.com/manpages/noble/man3/packet.transport.ib.3.html]. The numeric encodings (hex) I could **not** verify from a fetched primary source this session — **the hex values below are UNVERIFIED**, names are [F]:

| Family | Opcodes |
|---|---|
| SEND | SEND_FIRST, SEND_MIDDLE, SEND_LAST, SEND_LAST_WITH_IMMEDIATE, SEND_LAST_WITH_INVALIDATE |
| RDMA_WRITE | RDMA_WRITE_FIRST, _MIDDLE, _LAST, _LAST_WITH_IMMEDIATE |
| RDMA_READ | RDMA_READ_REQUEST; RDMA_READ_RESPONSE_FIRST, _MIDDLE, _LAST, _LAST_ONLY |
| ATOMIC | COMPARE_SWAP, FETCH_ADD (request carries AtomicETH; ack carries AtomicAckETH) |
| Control/ACK | ACKNOWLEDGE (RC ACK/NAK, AETH), **CNP** (congestion-notification packet — see below) |
| UD | SEND_ONLY, SEND_ONLY_WITH_IMMEDIATE, SEND_ONLY_WITH_INVALIDATE (DETH present) |
| XRC | XRC_SEND_* variants (RDETH/XRCETH present) |

Note: "**CND**" is **not** a standard IB opcode — likely a garbled reference to **CNP** or to SHARP aggregation; treat as not-a-real-opcode [I; flagged UNVERIFIED in research notes].

## Tuning
- **MTU wins:** use the largest MTU the path allows (4096 B on modern IB; IPoIB often 2048/4096). At 4096 B you're at **0.59%** overhead [E: constants bank]; dropping to 256 B costs **9.38%** [E]. Set per-path-record MTU, not just port.
- **Read vs write choice:** for repeated access to remote memory, WRITE avoids the request/response round trip of READ when data is pushed; READ is right when you pull. On the wire READ has the small-request advantage but adds a response leg.
- **PSN/ACK pacing:** AckReq + the ACK-pacing budget let you trade ACK frequency against retransmit window; don't over-ACK tiny messages (extra AETH packets), don't under-ACK (long recovery on loss).
- **GRH avoidance:** keep AI traffic intra-subnet (no GRH) — 24 B vs 64 B header is real at small MTU [E]. Routing across a router for AI data is a design smell; see [07-infiniband-addressing.md](./07-infiniband-addressing.md).

## Troubleshooting
- **ICRC mismatch** — end-to-end corruption/tamper; counts jump only when data is actually bad on the wire (rare; usually a cable/optics issue). Counter: `ICRC` in `perfquery`.
- **VCRC errors per link** — local serialization/CRC errors on a specific link; a rising VCRC count points at that cable/port [F: perfquery counters].
- **PSN/retry errors** — sequence mismatch or retries on the RC QP usually mean a drop somewhere without proper recovery; combine `IB packet sequence errors` counters with `NCCL_IB_TIMEOUT` tuning [see [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md)].
- **P_Key drops** — BTH P_Key fails validation (membership/enforcement mismatch) → silent partition-level loss ("can reach SM, not each other") [F: NVIDIA security docs].
- **Congestion (CNP/BECN) triggers** — frequent CNPs indicate the congestion-control loop is active; investigate hot flows rather than treating them as errors [I].

## Comparison — IB headers vs RoCEv2
| | InfiniBand (local) | InfiniBand (global) | RoCEv2 (Ethernet) |
|---|---|---|---|
| Always-present base | LRH(8)+BTH(12)+ICRC(4)=**24 B** | +GRH(40)=**64 B** | Eth(14)+IPv4(20)+UDP(8)+BTH(12)+ICRC(4)=**58 B** [E: constants bank] |
| L2 framing | IB link | IB link | Ethernet MAC |
| Routable? | subnet (LID) | yes (GID/GRH) | yes (IP/UDP) |
| Overhead @ 256 B | 9.38% [E] | 25.0% [E: 64/256] | 22.66% [E] |
| Overhead @ 4096 B | 0.59% [E] | 1.56% [E: 64/4096] | 1.42% [E] |
| Flow control | native credits [F] | native credits | PFC pause (see [10-infiniband-flow-control-and-qos.md](./10-infiniband-flow-control-and-qos.md)) |

The headline: IB-local headers beat both the GRH case and RoCEv2's always-on IP/UDP shim at small messages — the reason IB sustains low overhead on fine-grained GPU traffic [E].

## Lab
On a Linux host, wade in live:
```text
$ rdma link show                      # ports, speeds, state
$ perfquery <lid> -c 0x13 <n>         # read error counters (ICRC, VCRC, drops)
$ ib_read_bw <server_lid> --report_gbits   # wire an RC READ between two HCAs
```
`perftest` (`ib_send_bw`, `ib_write_bw`, `ib_read_bw`) is the fastest way to see opcode-class behavior; `rdma resource show qp` shows live QPN/state/path per QP your app created [A]. For the wire, use NVIDIA/IB hardware counters rather than a generic tap — the ICRC/VCRC counters are the ground truth [F: perfquery].

## AETH — the acknowledge header and RC ACK/NAK
Every RC acknowledgement carries a 4-byte **AETH**; only the LAST RDMA_READ_RESPONSE carries AETH (FIRST/MIDDLE read-responses do not) [F: https://manpages.ubuntu.com/manpages/noble/man3/packet.transport.ib.3.html]. The syndrome tells the sender whether the packet was accepted and, if not, *why*, so it can retransmit correctly:

```text
 AETH (4 B)
 ┌──────────┬──────────────────────────┐
 │ syndrome │ MSN (24-bit)             │
 │  8 bits  │  (last msg seq accepted) │
 └──────────┴──────────────────────────┘
```

| Syndrome class | Meaning to the sender | Action |
|---|---|---|
| **ACK** | packet(s) up to MSN accepted in order | advance window, free retransmit buffer |
| **NAK – remote access** | rkey / address / length rejected by receiver | don't retry (protocol error) — QP error |
| **NAK – remote op error** | operation failed at receiver | don't retry — QP error |
| **NAK – remote invalid request** | bad opcode/attributes | don't retry — QP error |
| **NAK – invalid RD/IRd error** | RD-invalid | retry per rules |
| **NAK – sequence / retry exceeded** | out-of-window PSN or retry budget spent | QP error |
| **RNR-NAK** | receiver busy, no receive WQE waiting | **retry later** (this one IS retryable, backed off) |

The syndrome naming and ACK/NAK/RNR classes are [F: manpage]; the exact syndrome **bit encodings** I could not verify from a single fetched primary source this session — treat exact values as UNVERIFIED, classes as [F]. **RNR-NAK is the one "NAK" that is deliberately retryable** — it's the receiver saying "I'm busy right now, come back," not "your packet was wrong." That distinction is why RC survives momentary receive-buffer starvation without dropping the connection [I; see [08-infiniband-queue-pairs.md](./08-infiniband-queue-pairs.md) RNR].

## CNP / BECN — congestion notification
IB's link layer carries congestion feedback so senders can slow down before losslessness turns into stalled queues [F/I: the research notes list "ACKNOWLEDGE … and CNP/BECN congestion-notification packets"; exact bit layout is [I]]:
- **FECN / BECN** are the **forward / backward explicit congestion-notification** fields: a switch that detects congestion on an egress marks the congested packet (FECN, forward direction); the destination reflects this as **BECN** back to the *source*, which throttles the offending flow. This is IB's native **BCN (Backward Congestion Notification)** scheme — deterministic, no packet loss, cooperative source pacing [I].
- **CNP (Congestion Notification Packet)** is the small control datagram used by the **DCQCN-style** congestion scheme (the same one RoCE uses) to tell the source, out-of-band, that its flow is congesting a queue — distinct from in-packet FECN/BECN marking [I].

Practical reading for AI: a healthy fabric rarely fires these; **frequent CNP/BECN activity is a symptom**, not a cause — it says some flow (often a straggler in a collective tail, or an all-to-all hot spot) is hammering a shared egress and the congestion loop is actively throttling it [I]. Adaptive routing (`./13-...`) is the higher-level answer that reduces how often the fabric has to fall back to congestion *reaction* in the first place.

## Example — hand-calculable wire costs
Header arithmetic for the common AI ops, using sizes from the table and the [E] constants bank (intra-subnet, GRH absent):

| Op (local) | Headers (B) | At 4096-B payload | At 256-B payload |
|---|---|---|---|
| SEND (no imm) | 8(LRH)+12(BTH)+4(ICRC)=24 | 0.59% [E] | 9.38% [E] |
| RDMA_WRITE/READ | 8+12+16(RETH)+4=40 | 0.98% | 15.6% |
| UD SEND | 8+12+8(DETH)+4=32 | 0.78% | 12.5% |
| RDMA_READ request | 8+12+16=36 (no payload) | — | — |

Derivables (computed this page from [F] header sizes — flagged [E] for the parent to bank if reused): SEND-at-256-B reads 64/4088 vs 64/256; the **WRITE/READ** family pays an extra 16 B of RETH versus SEND — why tiny munition messages (control plane) usually ride UD/SEND rather than a full RDMA op [I]. The headline stands: **payload size dominates**; at 4096 B every IB op is under 1% header overhead [E: constants bank].

## Troubleshooting — quick counter map
| Counter / signal | What it means | First move |
|---|---|---|
| ICRC errors ↑ | end-to-end corruption/tamper | check cable/optics; rare |
| VCRC errors ↑ (single link) | per-link CRC failure | reseat / replace that link |
| `IB packet sequence errors`/retries | a drop happened somewhere despite losslessness | look for HOQ timeout, P_Key drop, congestion |
| NAK / RNR-NAK rates | receiver busy or bad request | RNR → tune receive posting; true NAK → protocol bug |
| CNP/BECN frequency | congestion loop active | find the hot flow; consider AR `./13-...` |
| P_Key drop | partition enforcement/membership mismatch | audit P_Key on port + HCA `./12-...` |

## Lab — observing the wire
On modern NVIDIA/Mellanox HCAs the ICRC/VCRC/retry counters are the ground truth; a packet capture of the RDMA headers usually requires the hardware counter view rather than a libpcap tap [I; perftest as the exercise]:
```text
$ perfquery <lid> -c 0x13 <start_port>     # error counters: ICRC, VCRC, drops
$ rdma resource show qp                     # live QPN/state/path per QP
$ ib_read_bw -a <lid> --report_gbits        # drive READ traffic, watch counters
$ ibstat / iblinkinfo                        # per-port link state + counters
```
To see opcode-level behavior (SEND vs WRITE vs READ), run `ib_send_bw` / `ib_write_bw` / `ib_read_bw` in turn while polling the error counters; each family produces a distinct packet mix on the wire [A].

## A complete RDMA_WRITE, byte by byte
Lay a single local (intra-subnet) RDMA_WRITE out on the wire to fix the offsets. Sizes are [F: manpage]; byte positions follow from the running sum [I] (RFC-2534-style byte-offset accounting):

```text
 byte offset   size   field
 0            8      LRH     {DstLID, SrcLID, SL=?, VL, packet length, Global=0, …}
 8           12      BTH     {opcode=RdmaWrLast, P_Key, DestQP, AckReq, PSN}
 20          16      RETH    {remote VA, rkey, DMA length}   ← where this write lands
 36           P      PAYLOAD (P ≤ 4096)
 36+P         4      ICRC    (invariant, end-to-end)
 40+P         2      VCRC    (variant, per link)
 ─────────────────────────────────────────────────────────────
 total on the link (before link/physical framing) = 40 + P + 2 = 42 + P bytes
```

Concrete numbers (hand calculation, arithmetic over [F] header sizes):
- P = 256 B → **42 + 256 = 298 B/packet**; header+CRC share = (8+12+16+4+2)/256 = 42/256 ≈ **16.4%** of payload — real. (The bank's 24/256 = 9.38% [E] is the *SEND* case without RETH; the RDMA family carries the extra 16-B RETH, hence higher.)
- P = 4096 B → 42 + 4096 = **4138 B/packet**; 42/4096 ≈ **1.03%**.
- A 4-MiB gradient at 4096-B MTU = 4×1024×1024/4096 = **1024 packets** [I: arithmetic]. A single
  bulk flow at 50 GB/s emits 50 GB/s ÷ 4138 B/pkt ≈ **12.1 Mpps** [E] — far within any modern
  NIC's PPS budget, but a useful sense of scale for PPS-bound small-message workloads [I].

This is "show me the money": for bulk GPU data you want the **biggest MTU** (fewest packets, least header fraction); for latency-sensitive control you accept the small-packet tax in exchange for no fragmentation [I].

## Design decisions that fall out of the packet format
- **MTU vs latency:** 4096-B MTU minimizes overhead (0.59% for SEND [E]) but serializes a full packet; smaller MTUs cut serialization latency for latency-bound control. AI bulk traffic picks 4096 and pays the small extra tail [I].
- **SEND vs WRITE vs READ framing:** SEND is the cheapest header (24 B [E]) but needs a receive WQE; WRITE adds RETH but is one-sided; READ is one-sided but costs a request+response leg. The packet format explains *why* NCCL prefers WRITE for pushing gradients and READ for pulling shards [I; see [08-infiniband-queue-pairs.md](./08-infiniband-queue-pairs.md)].
- **UD vs RC:** UD's DETH (unreliable) is how management/IPoIB stays lightweight; reliability is a per-transport choice, not a wire-layer given [I].

## Key Takeaways
1. **Every IB packet = LRH(8) + BTH(12) + [op-specific ext headers] + payload + ICRC(4) + VCRC(2)**; GRH(40) only when routed [F: manpage].
2. **Intra-subnet = 24 B** (SEND), **RoCEv2 = 58 B**, **global = 64 B** [E: constants bank]; at 256-B payload that's 9.38%, 22.66%, 25.0% respectively [E].
3. **BTH fields** (opcode, P_Key, DestQP, AckReq, PSN) carry the transport state in the header, keeping switches stateless [F].
4. **AETH syndrome + MSN** make RC's ACK/NAK self-describing; **RNR-NAK is the retryable one** [F/I].
5. **CNP/FECN/BECN** are the congestion loop's signals — frequent firings are a symptom, not the cause [I].
6. **ICRC (end-to-end, invariant)** and **VCRC (per-link, variant)** partition integrity checks so routers can rewrite hop-local fields without breaking end-to-end validation [F: manpage].

## References (supplement)
- IBTA — `packet.transport.ib` manpage (all header sizes, BTH fields, opcode names, AETH, LRH/GRH): https://manpages.ubuntu.com/manpages/noble/man3/packet.transport.ib.3.html
- NVIDIA IB security (P_Key / BTH): https://networking-docs.nvidia.com/nvidiainfinibandsecurityoverviewandguidelines/security-in-infiniband
- NVIDIA credit loops (CNP/losslessness): https://enterprise-support.nvidia.com/s/article/howto-prevent-infiniband-credit-loops
- IB QoS (SL2VL / arbitration): https://networking-docs.nvidia.com/doca/archive/3-4-0/infiniband-qos
- [E] figures from the section constants bank (computed 2026-08-25).

## Related
- [03-rdma-fundamentals.md](./03-rdma-fundamentals.md) — the verbs model these headers implement.
- [08-infiniband-queue-pairs.md](./08-infiniband-queue-pairs.md) — QP state machine, PSN, AckReq source.
- [07-infiniband-addressing.md](./07-infiniband-addressing.md) — LID (LRH) vs GID (GRH) addresses in these headers.
- [10-infiniband-flow-control-and-qos.md](./10-infiniband-flow-control-and-qos.md) — ICRC/VCRC's cousin, the credit flow-control layer.
- [12-infiniband-routing-topology-partitions.md](./12-infiniband-routing-topology-partitions.md) — P_Key in the BTH and partitions.
- [13-infiniband-congestion-adaptive-routing.md](./13-infiniband-congestion-adaptive-routing.md) — CNP/BECN and congestion control interplay.
- [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md) — counter-driven debugging.

## References
- IBTA — `packet.transport.ib` manpage: header sizes, BTH fields, opcode names, GRH/LRH: https://manpages.ubuntu.com/manpages/noble/man3/packet.transport.ib.3.html
- NVIDIA InfiniBand security / P_Key: https://networking-docs.nvidia.com/nvidiainfinibandsecurityoverviewandguidelines/security-in-infiniband
- NVIDIA credit loops / losslessness: https://enterprise-support.nvidia.com/s/article/howto-prevent-infiniband-credit-loops
- IB QoS / arbitration: https://networking-docs.nvidia.com/doca/archive/3-4-0/infiniband-qos
- [E] figures from the section constants bank (computed 2026-08-25).
