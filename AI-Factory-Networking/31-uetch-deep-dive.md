# Ultra Ethernet Transport (UET) — Deep Dive
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: UEC spec 1.0 (Jun 11 2025; current 1.0.3, Jul 16 2026), author paper arXiv:2508.08906, UEC spec-update blog; fetched 2026-08-25.

## 30-Second Explanation
UET (Ultra Ethernet Transport) is the **clean-slate, connectionless transport** that the
Ultra Ethernet Consortium designed to replace RoCEv2's lossless, connection-based model.
Where RoCEv2 embeds InfiniBand's *connected queue-pair* transport and therefore demands
lossless, strictly-in-order delivery (PFC + DCQCN), UET throws that state away: it is
**connectionless** — there is no handshake, no per-peer queue pair, and the *first data
packet itself* carries all the state needed to create an ephemeral **Packet Delivery
Context (PDC)**. Delivery is **unordered** by default (RUD), each packet carries an
**Entropy Value (EV)** in the UDP source-port position for **per-packet spraying** across
every equal-cost path, and the receiver reassembles with a per-PDC **bitmap** using
Direct Data Placement — **no re-order buffer**. UET is **lossy-by-design**: it needs no
PFC, uses two traffic classes to avoid deadlock even on lossless fabrics, and covers
link errors with optional hop-by-hop **Link Level Retry (LLR)**. This page unpacks the
transport end to end; for the consortium, specs, and the "why not RoCEv2" motivation see
[./30-ultra-ethernet-consortium.md](./30-ultra-ethernet-consortium.md).

> **Production status guardrail.** Everything below is the UET **spec 1.0.3 (July 16,
> 2026)** plus early silicon — *not* a broadly-deployed fabric. Switches (Broadcom
> Tomahawk 6/Ultra) and one NIC (AMD Pensando Pollara 400) are shipping [I]; independent
> commentary expects broader production adoption through 2026–2027 [I]. Do not read this
> page as describing installed capacity.

## What
UET is the transport layer of the UEC stack. Per the spec's single 562-page document it
sits under the **Software** layer (libfabric mapping), above **Link** and **Physical**
layers, and bundles four sub-protocols [F: spec Contents; arXiv §1.1/§3]:

```text
   Software layer:  libfabric v2.0 (OFI) — the north-bound API; FEP addressed
                    by IP + JobID + PIDonFEP + Resource Index
        │
   UET transport ──────────────────────────────────────────────
   │  PDS  Packet Delivery Service   — per-packet delivery modes, header
   │  SES  Semantics                 — message semantics matching, message-id
   │  CMS  Congestion Management     — NSCC + RCCC (see ./32), load balancing
   │  TSS  Transport Security        — AES-GCM-256 AEAD, Secure Domains (see ./32)
   │──────────────────────────────────────────────────────────
   Link layer:  LLR (Link Level Retry) · optional CBFC (credit flow control)
   Physical:    100 Gb/s/lane baseline; 200 Gb/s/lane added in 1.0.3
   Wire:        Ethernet + optional UDP/IP (port 4793) or flat native-IP mode
```

The single most important sentence: UET **removes the queue-pair / connection state that
limits RoCE and InfiniBand scale**, replacing it with ephemeral PDCs created on demand.
[F: spec §3.2.3; spec-update blog]

## Why
The four reasons the consortium cites for a *new* transport rather than another RoCE
tweak [F: arXiv:2508.08906 §1]:
1. **RoCEv2 = IB transport on Ethernet, unchanged** → it inherits IB's requirement for
   lossless, strict in-order delivery, guaranteed by PFC, which brings head-of-line
   blocking and congestion spreading.
2. **In-order delivery pins a flow to one path** → ECMP flow-hash polarization, no useful
   multipathing; hash collisions can halve effective bandwidth.
3. **No fast end-to-end loss signal** → ECN-only, ingress-marked, slow; DCQCN cannot react
   inside sub-millisecond AI transfers.
4. **Connection state does not scale** → per-peer QP state is the binding constraint at
   millions of endpoints.

UET's bet: make the transport **unordered + sprayable + lossy-tolerant** and the fabric,
collectives, and tail latency all improve at once. It is the transport bet, not just a
"RoCEv2 with more headroom" — see ## Comparison.

## How — the connectionless, 0-RTT PDC model
UET is **connectionless**. There is **no handshake** of any one-way/three-way kind: the
spec calls the establishment a "**dynamic connection protocol** … similar to 0-RTT" —
the **first data packet carries all state** needed to create the context, and
transmission proceeds at full rate during establishment [F: spec-update blog; spec text
~25609; arXiv §3.2.3]. This is a structural break from RoCE/IB, where a QP setup
handshake precedes any data.

```text
0-RTT PDC establishment (no handshake):
  Sender                                            Receiver
    │  PDC-not-established                         │
    │  data packet 1 ────────────────────────────► │  creates ephemeral PDC
    │  (carries PDC id + all state)                │  from the packet itself
    │  data packet 2 ────────────────────────────► │  installs receive state
    │  ... full rate already                      │
    │  ACK/CACK ────────────────────────────────  │  (reliability confirmed)
```

**Replay exposure.** Because establishment is 0-RTT and state is taken from the first
packet, UET is "**susceptible [to replay]** … when security is off" [F: spec-update blog].
With TSS enabled, PSN + per-epoch timestamp counters give replay protection (see
./32). Never run a UET fabric with security off across a trust boundary unless replay is
acceptable — this is a documented property, not a configuration warning [F].

The **PDC** is the ephemeral context that replaces a QP: it names the receiver reassembly
bitmap, the entropy/order state, and the congestion context it belongs to. PDCs are cheap
and created/destroyed on demand, which is what lets UET target **millions of endpoints**
without per-peer connection tables [F: arXiv §2, §3.2.3].

## Packet flow — delivery modes and the on-wire format
There are **four packet-transport (delivery) modes**, defined at the PDS layer [F: spec
§3.5; arXiv §3.2.1]:

| Mode | Name | Ordering | State | Used by |
|---|---|---|---|---|
| **RUD** | Reliable Unordered Delivery | message-level only | receiver PDC | default bulk; AI profiles |
| **ROD** | Reliable Ordered Delivery | strict packet in-order | per-path | wildcard matching / MPI / minimal endpoints |
| **RUDI** | Reliable Unordered for Idempotent Ops | message-level | **no receiver state** | HPC only; most scalable |
| **UUD** | Unreliable Unordered Delivery | none | none | software / sysadmin |

(There is no "Unreliable Ordered Delivery" — no use case [F].) **RUD** is the default and
what enables **packet spraying**: out-of-order arrival is normal, so the sender may put a
different EV on every packet. **ROD** gives RoCE-like strict order for MPI wildcard
matching at the cost of single-path flowlets. **RUDI** is the scaling king — idempotent
operations need no receiver tracking state — but is HPC-profile-territory [F].

**The wire format** (Ethernet 14B + FCS 4B; over UDP/IP or native IP) [F: arXiv §3.2.2;
spec §3.6; **[E]** bank row "UET PDS/SES hdrs"]):

```text
 over UDP (default):  14B Eth | 20B IPv4 | 8B UDP (src-port = EV) | PDS | SES | [TSS] | payload | [CRC] | 4B FCS
 over native IP:      14B Eth | 20B IPv4 | 4B entropy hdr (=EV)   | PDS | SES | [TSS] | payload | [CRC] | 4B FCS

 PDS header bytes:   RUD/ROD = 12B   (16B when RCCC credits in use)
                     RUDI     =  8B
                     UUD      =  4B
 optional:           4B end-to-end CRC
 SES header bytes:   44B standard · 32B matching (≤8 KiB msg) · 20B minimal non-matching
 optional TSS:       +12B header (16B with explicit source id) + 16B ICV
```

**Entropy Value (EV)** sits in the **UDP source-port position** (or the 4B entropy header
in native-IP mode) and drives per-packet path selection [F: arXiv §2.1]. The sender can
change EV per packet → **per-packet spraying**; keeping the same EV holds a flow on one
path in-order [F].

**Transport layer-4 encapsulation: UDP port 4793.** Per the author paper, UET runs over
UDP/IP with **port 4793 assigned by IANA**, with an optional **native IP mode** whose 4B
entropy header replaces the 8B UDP header [F: arXiv:2508.08906 §2.1]. (The research memo
that fed this page flagged that the 4793 number was surfaced in the author paper and
asked for a direct spec-1.0.3 grep to reconfirm — treat the IANA assignment as
[F: author paper], port number stable [I]). The EV lives in what *would* be the UDP
source port — the same trick RoCEv2 uses for per-QP entropy but with per-*packet*
granularity instead of per-flow.

**Receiver reassembly — no re-order buffer.** Because RUD/RUDI are unordered, the
receiver must reassemble. It does so per-PDC with a **receive bitmap**, cumulative **ACK
(CACK)** + a **64-bit SACK bitmap**, optional **ACK coalescing**, and an **MP_RANGE**
field that bounds the outstanding PSN window so the receiver need not over-provision
tracking state [F: arXiv §3.2.5; spec-update blog]. Crucially, reordered packets land
straight into the **application buffer via Direct Data Placement (zero-copy)** — there is
**no re-order buffer at all** [F]. That is the payoff of embracing unordered delivery:
the sender sprays freely, and the receiver's NIC DMAs each packet to its final offset.

```text
Receiver per-PDC state (not a re-order buffer):
  PDC { bitmap of received PSNs, window bound = MP_RANGE, session keys }
  packet arrives → check bitmap slot (out of window? drop/NACK) →
  Direct Data Placement: DMA payload straight to app-buffer offset → mark slot →
  coalesced CACK + 64-bit SACK when appropriate
```

**Lossy-by-design & two traffic classes.** UET targets **best-effort (lossy)** fabrics
(drop, ECN, trimming) and also runs on lossless ones; to avoid request/response
**deadlock on lossless networks** it uses **two traffic classes** — a *data* TC and a
*control/ACK* TC [F: arXiv §1.2/§3.3/§3.5; spec-update blog]. On a lossy fabric a dropped
ACK is recovered by retransmission; on a lossless fabric, a deadlock cycle (every node
waiting for the other's buffer) is avoided by giving control its own queue.

## GPU relationship
UET is invisible to the GPU — *that is the point*. The GPU programs **NCCL/RCCL/MPI-adjacent
collective libraries**, which map onto **libfabric v2.0** (OFI); the libfabric **Fabric
Endpoint (FEP)** terminates the transport, roughly a NIC, addressed by
**IP + JobID + PIDonFEP + Resource Index** [F: spec-update blog; arXiv §1/§3.1]. So:
- Existing AI stacks (NCCL-like CCLs, MPI) migrate with **no code change** — the same
  API, a new provider underneath.
- The GPU's "connection state" is just the cheap PDC at the NIC, not a QP it must manage.
- **Inference impact:** connectionless + spraying directly attacks the **incast and tail
  latency** problems that dominate AI JCT (see ./33, ./35): a collective can fan its
  packets over every path instead of pinning to a hashed flow, and a short sub-RTT
  transfer needs no setup round-trips — good for small latency-bound AllReduce /
  prefill pipelining [I].

## Design — why the details are the design
Put the pieces together and the architecture is coherent:
1. **Connectionless PDC** removes the scale barrier and the setup handshake.
2. **Unordered RUD** lets the sender **spray** without caring about order → uses all
   equal-cost paths → kills ECMP polarization [F].
3. **Receiver-side bitmap reassembly + DDP, no reorder buffer** makes out-of-order
   *free* — the hardware price of spraying is paid once at the receiver NIC [F].
4. **Lossy tolerance + two TCs** removes the PFC head-room/head-of-line tax; corruption is
   handled by **LINK-level retry (LLR)**, *not* end-to-end go-back-N [F: arXiv §3.5.1].
5. **Congestion is a sender-side job** (NSCC, see ./32) using in-ACK telemetry rather
   than separate CNP-style packets [F: arXiv §3.3].

### Link-layer options: LLR and CBFC
Two **optional** link-layer tools replace or augment PFC [F: arXiv §3.5.1; spec §5.1]:
- **LLR (Link Level Retry)** — a **hop-by-hop, link-partner-to-link-partner**
  retransmission scheme, negotiated via **LLDP**. The transmitting link buffers
  LLR-eligible frames in a **replay buffer**, stamps a sequence number in the preamble,
  and the receiving link ACKs to free the buffer; recovery is **go-back-N + NACK** with a
  short retransmission timeout (**~1 µs** link RTT) for tail/NACK loss. Control (N)ACKs
  ride as 8B Control Ordered Sets in the PCS. Value: corruption (marginal links,
  intermittent components) is fixed at the link in **~1 µs** instead of an end-to-end
  RTT — protecting tail latency of a job where one bad link stalls the whole collective
  [F: spec-update blog; arXiv §3.5.1]. LLR is about *corruption recovery*, not flow
  control.
- **CBFC (Credit-Based Flow Control)** — the optional **flow control** analogue: per
  **virtual-channel** credit counters, "advantage over PFC": less buffer headroom and
  per-VC configurability [F: arXiv §1.2/§3.5]. CBFC is to PFC as IB's per-VL credits are
  to PFC — but in UET it is *optional*, because UET is fundamentally lossy-tolerant and
  does not need link-level losslessness for correctness [A: synthesized comparison].

Endpoint-level flow control is a separate stack: **RCCC receiver credits** (receiver
grants credits; optional, incast-optimal) and **Destination Flow Control (DFC)** — which
throttles a sender to keep up with a slow receiver/bus/memory (a penalty value for NSCC,
credit-rate cut for RCCC) [F: spec §3.6; spec text ~21497]. Note the research memo's
warning: **"EFC (end-to-end flow control)" is NOT a UET-1.0 term** — the actual
mechanisms are RCCC + DFC [F].

## Tuning
UET tuning is largely *congestion* tuning, covered in ./32 (NSCC/RCCC, DFC). Transport
level, the knobs that matter:
- **Delivery mode per workload**: RUD default; ROD only where strict packet order is
  required (MPI wildcard); RUDI where idempotence allows dropping receiver state (HPC).
  The mode is the biggest lever on both sprayability and receiver cost [F].
- **EV strategy**: per-packet EV for maximum spread; keep EV constant for in-order
  per-flowlet where a workload needs it. EV is the multipathing dial [F].
- **MP_RANGE / ACK coalescing**: bound the PSN window (receiver tracking cost) and batch
  ACKs to cut control traffic — relevant at high message rates [F].
- **Two TCs**: ensure data and control/ACK land on separate queues (matters on lossless
  fabrics) [F].
- **Security**: TSS is opt-in per Secure Domain; enabling it adds 12+16B per packet and
  replay protection — a deliberate security/latency trade [F: spec §3.4].

## Troubleshooting
- **Replay / duplicates visible** — a fabric running with **security off** can see replay
  of 0-RTT-established PDCs; enable TSS or bound the trust domain ([F: spec-update blog]).
- **Out-of-order but no loss** — *expected* under RUD; not an error. A rule of thumb
  [I]: reorder is healthy (spraying working); *retransmits* are the signal to chase.
- **Dropped ACKs on lossy fabric** — window stalls if CC mis-tunes; check NSCC state and
  the DFC/penalty path (consumer-side) [F: spec §3.6].
- **LLR retransmit storms** — replay-buffer thrash on a marginal link; LLR fixes the hop
  fast, but if retransmits persist it is telling you a physical/PHY problem (marginal
  optic/cable) sits under the transport [A].
- **"Is it RoCEv2"-style lossless tuning required?** — No: UET does **not** want PFC
  ingress-buffer headroom the way RoCE does; fighting latency by adding PFC is
  counterproductive [F: arXiv §1].

## Comparison — why UET is *not* "RoCEv3"
RoCEv3 is a seductive but wrong label. UET is not RoCE+1; it is a different design space
(spec table, open source for the architecture, arXiv §8) [F:A]:

| Dimension | UET (1.x) | RoCEv2 |
|---|---|---|
| Heritage | UEC clean-slate transport (2023–25) | IB transport over routable Ethernet (~2014) |
| Connection model | **Connectionless**, ephemeral PDC, 0-RTT, no handshake | Connected QPs (RC/UC/DC), setup handshake |
| Ordering | RUD/RUDI out-of-order + zero-copy; ROD optional | Strict in-order packet delivery |
| Multipath | **Per-packet spraying** (EV in UDP port) | ECMP flow hashing only (one path/flow) |
| Lossless required | **No** — lossy-tolerant; optional CBFC/PFC | **Yes** — PFC lossless (HOL blocking) |
| Congestion control | **NSCC** (sender, ECN+RTT) + optional **RCCC** | **DCQCN** (ECN + CNP + PFC) |
| Fast loss recovery | Packet **trimming** + SACK + EV detection | Go-Back-N over lossless fabric |
| Link error handling | **LLR** (link retransmit, ~1 µs) + CBFC | PFC lossless + FEC |
| In-network compute | **INC** (fi_collective) standardized/optional | none standardized |
| Security | **TSS**: AES-GCM-256, Secure Domains, replay | none native (L2 MACsec/other) |
| Scale target | millions of endpoints, connectionless | bounded by connection state |
| API | libfabric v2.0 (OFI) | Verbs / libfabric |

**The clean-slate claim.** Every row in that table is a *by-design* decision, not a
tweak: connectionless instead of QP, unordered instead of ordered, spraying-native
instead of hash-bound, lossy-capable instead of lossless-required. That is why calling it
"RoCEv3" understates the change [F: arXiv §1].

## Profiles — AI Base / AI Full / HPC
The spec defines **three profiles** — **AI Base, AI Full, HPC** [F: spec §1.1.2
Table 2-4; arXiv §2.2]. Endpoints advertise multiple profiles and **negotiate to the
greatest common feature set** [F]:

| Feature | AI Base | AI Full | HPC |
|---|---|---|---|
| Target traffic | CCL (NCCL-style) collectives | AI + storage (RMA read) | MPI / OpenSHMEM, latency short msgs |
| Delivery modes | RUD | RUD / RUDI + RCCC | ROD (packet order) + RUDI |
| Transport matching | none (done in libfabric/CCL) | exact (non-wildcard) tag | wildcard/in-order tag |
| Deferrable send | — | **yes** | **no** ⚠ |
| Atomic ops / rendezvous | minimal | atomics | full rendezvous, more atomics |
| RMA read | — | **mandatory** (storage) | full |
| Cost/complexity | lowest | mid | richest |

**Key nuance [F: spec ~5391; arXiv §2.2]: HPC is NOT a strict superset of AI Full.**
*Deferrable send is the one AI-Full capability HPC does not support* — HPC treats a
deferrable send as a normal send. AI Base is a proper subset of both AI Full and HPC.
Interop: peers negotiate to the *greatest common* feature set [F].

## Lab
A UET lab is early-gear [I] — there is no commodity "install UET" like OFED. What you
*could* validate today, and what it would verify:
1. **libfabric mapping (no hardware needed):** compile an app against **libfabric v2.0**
   and inspect which **provider** it selects; UEC ships reference code that runs over
   ordinary NICs to prove the transport/API mapping [F: spec-update blog]. *Expect:* the
   same MPI/NCCL app runs unchanged because UET speaks the OFI northbound API.
2. **Packet-spraying principle (on RoCE hardware, generalizable):** use ndctl/perf tools
   to vary the UDP source port per packet and watch paths spread — the EV mechanism is
   RoCEv2's per-QP entropy trick made per-packet [A]. See the RoCE entropy bank row.
3. **Header arithmetic [E]:** build the on-wire cost of a sprayed RUD message. Per
   payload packet, add 14B Eth + 20B IPv4 + 8B UDP + 12B PDS + SES (44B std / 32B match) =
   e.g. 98B with 20B-payload *control* frames … check against the [E] bank's PDS/SES
   header row (PDS 12B / 16B with RCCC; SES 44/32/20B; +4B e2e CRC; TSS +12B + 16B ICV).
   *Expect:* transport overhead comes almost entirely from SES/TSS, so the **bulk-payload
   sweet spot is where header cost is negligible** — matching the RoCE overhead math in
   the constants bank [E].
4. **LLR sanity:** because LLR is LLDP-negotiated and hop-by-hop, verify it is really a
   *link-partner* recovery, not end-to-end — inject corruption on a single link and
   confirm recovery happens in ~1 µs locally, not after a full round trip [A: engineering
   test].

> **Where this fits.** Next: the congestion side — **NSCC vs RCCC**, INC in-network
> collectives, and TSS security in [./32-uetch-congestion-and-in-network.md](./32-uetch-congestion-and-in-network.md).
> Workload consequences in [./33-collective-communication.md](./33-collective-communication.md)
> and [./34-moe-all-to-all.md](./34-moe-all-to-all.md); the full packet journey in
> [./51-complete-packet-journeys.md](./51-complete-packet-journeys.md); hardware/GPU side
> in [../GPU-Communication/README.md](../GPU-Communication/README.md).

## Key Takeaways
1. UET is **connectionless** — no handshake: the first data packet carries all state and creates an ephemeral **PDC** (0-RTT "dynamic connection protocol"), replacing the per-QP state that caps RoCE/IB scale at millions of endpoints. [F]
2. Four PDS delivery modes — **RUD** default (message-level ordering, enables spraying), **ROD** (strict packet order, MPI wildcard), **RUDI** (idempotent, no receiver state, HPC), **UUD** (unreliable) — reassemble per-PDC with a bitmap + Direct Data Placement, so there is **no re-order buffer**. [F]
3. **Per-packet spraying** via the Entropy Value (EV) in the UDP source-port slot (port 4793, IANA) spreads every packet across equal-cost paths, killing ECMP flow-hash polarization. [F]
4. **Lossy-by-design**: no PFC needed; two traffic classes (data vs control/ACK) prevent deadlock on lossless fabrics; link corruption is fixed hop-by-hop by **LLR** (~1 µs), not end-to-end Go-Back-N; optional **CBFC** replaces PFC. [F]
5. UET is a clean-slate design space, not "RoCEv3": connectionless vs connected, unordered vs ordered, spraying vs hash-bound, lossy-capable vs lossless-required — every table row a by-design choice. [F]

## Related
- [30-ultra-ethernet-consortium.md](./30-ultra-ethernet-consortium.md) — the why/what: the five RoCEv2 gaps, the 562-page spec, shipping status.
- [32-uetch-congestion-and-in-network.md](./32-uetch-congestion-and-in-network.md) — NSCC/RCCC congestion control, INC collectives, TSS security
- [33-collective-communication.md](./33-collective-communication.md) — the collectives this transport is built to carry.
- [51-complete-packet-journeys.md](./51-complete-packet-journeys.md) — end-to-end packet walks, including UET on the wire.
- [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md) — the GPU/CCL side that drives the transport.
- [55-cheat-sheet.md](./55-cheat-sheet.md) — quick reference across the section.

## References
- UEC Specification v1.0 (Jun 11 2025; current **1.0.3**, Jul 16 2026) — PDS/SES, LLR/CBFC, profiles [F].
- "Ultra Ethernet's Design Principles and Architectural Innovations," arXiv:2508.08906 (2025-08-12) [F: author paper — secondary where noted].
- UEC spec-update blog — 1.0.x changes; 0-RTT/replay; LLR; PDC model [F].
- [E] AFN constants bank — "UET PDS/SES hdrs" row (PDS 12/16B, SES 44/32/20B, e2e CRC +4B, TSS +12B +16B ICV) used in the header-arithmetic lab.
