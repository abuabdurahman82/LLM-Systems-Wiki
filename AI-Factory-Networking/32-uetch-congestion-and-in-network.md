# UET Congestion Control & In-Network Collectives
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: UEC spec 1.0.3, author paper arXiv:2508.08906, UEC spec-update blog, Broadcom Tomahawk Ultra release; fetched 2026-08-25.

## 30-Second Explanation
UET's **CMS (Congestion Management Subsystem)** = **Congestion Control** + **Load
Balancing**, running per **Congestion Control Context (CCC)** that serves one or more
PDCs. Crucially, CMS needs **only ECMP + egress ECN from switches** — no exotic switch
features — which is why UET promises to run on plain installed Ethernet [F: arXiv §3.3;
spec §3.6]. Congestion control comes in two algorithms: **NSCC** (Network Signal-based,
*sender-based, mandatory* on every UET NIC: a window driven by RTT multi-bit + ECN-CE
single-bit read from ordinary ACKs, with a 4-case decision) and **RCCC** (Receiver
Credit-based, *optional*, receiver grants per-source credits — excellent for incast;
optimistic credits start early). NSCC has **no CNP-style feedback packet** — congestion
signal rides inside normal ACKs and egress marking. On top of the transport, UEC defines
**INC (In-Network Collectives)**: the `fi_collective()` API offloads
AllReduce/Broadcast/AllGather into the switches (optional per profile; "first
standardized over Ethernet"), shipped today in-chip in the **Broadcom Tomahawk Ultra**.
This page covers CMS, NSCC vs DCQCN, telemetry, INC vs SHARP, and the **TSS** security
layer. Transport internals are in [./31-uetch-deep-dive.md](./31-uetch-deep-dive.md).

## CMS — what it manages, and what it needs
The **Congestion Management Subsystem** is the union of **Congestion Control** (bound the
bytes in flight) and **Load Balancing** (choose the path) [F: arXiv §3.3; spec §3.6].
- State lives per **Congestion Control Context (CCC); one CCC serves one or more PDCs**.
  This is the UET analogue of a congestion window owner: instead of a per-QP window
  (RoCE/DCQCN), a CCC bounds the shared transmit window for a set of delivery contexts.
- **Switch requirements are minimal: ECMP + egress ECN.** UET does not ask the switch for
  per-flow state, exotic schedulers, or CNP generation — only to spread flows (ECMP) and
  mark ECN at *egress* [F: arXiv §3.3; spec].

```text
  Sender NIC (per CCC)                         Switch                    Receiver NIC
  NSCC window ──► data packets ──────────────► egress-ECN marks ───────► reassemble
      │  adjust:(RTT multi-bit,               (ECN-CE bit set when        │
      │  ECN-CE single-bit)                   queue > threshold)         │
      │  ┌───────────  ACKs carry ECN/RTT signal (no CNP packet) ◄───── ACK/CACK
      └──┴── update window from the 4-case decision
```

**What is NOT in the spec.** The research memo is explicit: the names **"CCv1" / "CCv2" /
"TACC" (telemetry-assisted congestion control) do not exist in UET 1.x** — grep found no
CCv1/CCv2 and no TACC. (Web hits for "TACC" are the Texas Advanced Computing Center,
unrelated.) **Use the correct pair: NSCC + RCCC.** [F]

## NSCC — the mandatory, sender-based algorithm
**NSCC = Network Signal-based Congestion Control** [F: arXiv §3.3; spec §3.6]:
- **Sender-based and mandatory** on every UET NIC (it is the compliance floor).
- A per-CCC adaptive **window** built from a **blend of two signals read from ACKs**:
  **RTT (multi-bit signal)** + **ECN-CE marking (single-bit)**, decided with a **4-case
  table** (ECN set/clear × RTT high/low).
- **ECN is marked at egress** (as the packet departs the switch) — faster than RFC 3168
  *ingress* marking, shrinks feedback delay.
- **Quick Adapt (QA)** plus fast loss signals (**packet trimming**) estimate bottleneck
  bandwidth — this is how NSCC keeps up with **incast** in short, sub-millisecond AI
  bursts.
- **No CNP-style feedback packet.** Unlike DCQCN (which mints congestion-notification
  packets back to the sender), NSCC's congestion signal rides *inside normal ACKs* [F].

The four-case decision (RTT + ECN) [F: spec §3.6; A: tabular presentation of the
spec's NSCC cases]:

| Case | ECN-CE | RTT | NSCC window action |
|---|---|---|---|
| 1 | clear | low | increase (probing for bandwidth) |
| 2 | clear | high | mild increase / hold (delay-based signal) |
| 3 | set | low | decrease (ECN is ground truth, back off) |
| 4 | set | high | strong decrease (both signals agree: congested) |

## RCCC — the optional, receiver-credit algorithm
**RCCC = Receiver Credit-based Congestion Control** [F: arXiv §3.3; spec §3.6 (1.0.2
corrected its source algorithm)]:
- **Receiver-based and optional** to implement.
- The **receiver knows every incoming flow**, so it **grants per-source credits** before
  the sender transmits.
- **Excellent for incast** (the receiver arbitrates its own overload); **weaker for
  outcast/in-network congestion**, which is why the spec recommends running **NSCC
  alongside**.
- Supports **optimistic / pre-allocated credits** — start transmitting before permission,
  betting the credit arrives — cutting latency on short bursts.
- **Either / or / both can be enabled at runtime** (an "enabled/both" model, not a pick-one
  design) [F].

Big-picture: **NSCC = the always-on fabric/congestion controller; RCCC = the
receiver-centric incast optimizer; DFC** (Destination Flow Control, throttling a sender to
a slow consumer) **is the endpoint flow-control backstop** [F: spec §3.6].

## NSCC vs DCQCN — comparison table
RoCEv2's DCQCN (Zhu et al. 2015) is the incumbent UET NSCC must beat; the contrast is the
sharpest way to see the design bet (sources: arXiv §3.3 + DCQCN reference, Nokia blog)
[F/A]:

| Dimension | **UET NSCC** | **DCQCN (RoCEv2)** |
|---|---|---|
| Signalling basis | ECN + **RTT** + packet trimming, **egress-marked** | ECN (switch) + **CNP** packets + PFC |
| Feedback path | inside **normal ACKs** (no CNP) | dedicated CNP packet → sender |
| Fabric model | **lossy / best-effort** friendly | assumes **lossless (PFC)** |
| Connections | **connectionless** (CCC / PDC) | per-QP connected state |
| Incast handling | **Quick Adapt** + optional RCCC credits | ECN/CNP-based; slower on short AI xfers |
| Ramp | wire-rate start, rapid back-off | conservative DCTCP-style AIMD for RDMA |

The summary line: NSCC is built for **lossy, short-burst, connectionless** AI traffic;
DCQCN is tuned for **lossless, µs-RTT, connected** fabrics and cannot react inside a
sub-ms AI transfer [F: arXiv §1].

## Telemetry themes
UET leans on in-band telemetry fed back to the sender (PFC-free, rate-based) [F: spec;
I: architectural tie-in per research memo]. Three named themes:
- **Packet trimming** — on congestion a switch can truncate/cut a packet and signal the
  truncation back, so the sender knows both *that* and *where* congestion bit — a fast,
  lossy-fabric-native signal (used by NSCC's bottleneck estimate) [F: arXiv §3.3].
- **Out-of-order (OOO) counting** — counts reordered packets; a telemetry input to Load
  Balancing (how well per-packet spraying is working / whether a path is skewing).
- **Path probing** — adjectives load-balancing probes equal-cost paths to keep the spray
  fair.
(Beware the research memo's re-verify note: the *specific* mechanical details of UET
telemetry in-ACK signaling are [I] at spec level; INT vs gNMI vs UET distinctions from the
telemetry literature are separate — see ./44 for monitoring.) [I]

## In-Network Collectives (INC)
UEC's **INC** offloads **AllReduce, Broadcast, AllGather into the switches** via the
**libfabric `fi_collective()` API** — optional per profile, and per UEC **"the first time
such a technology is offered and standardized over Ethernet"** [F: spec §2.2.5.4.5,
profile tables; spec-update blog].

```text
Without INC (host/GPU does the reduce):          With INC (switch reduces):
  GPU → NIC → switch → NIC → GPU: reduce in GPU     GPU → NIC → switch: REDUCE in switch
  (data crosses fabric, turns around, comes back)    → multicast result back to all GPUs
  bytes on wire ≈ 2(n-1)/n × M (ring, see ./33)     fewer round trips; switch absorbs the fan-in
```

**INC vs NVIDIA SHARP** [F: research-uec note; A: synthesis]:

| Dimension | UEC INC | NVIDIA SHARP |
|---|---|---|
| Openness | open, multi-vendor, **Ethernet-standardized** | **proprietary (NVIDIA)** |
| Fabric | Ethernet (UEC); switch-embedded | InfiniBand; Spectrum-X Ethernet variant |
| Collectives | AllReduce/Broadcast/AllGather via `fi_collective()` | in-network reduction in Quantum/Spectrum switches |
| Standardized? | yes (UEC spec, optional) | vendor-defined |
| Status (2026) | **spec-defined + early shipping silicon** [I] | shipped/installed in NVIDIA ecosystems |

**Silicon status.** INC is **spec-defined and optional** — it is not required for
compliance [I]. Shipping proof: **Broadcom Tomahawk Ultra** (announced/shipping **July 15,
2025**) executes AllReduce/Broadcast/AllGather **in the switch chip** and is "compliant
with the UEC standard" [F: vendor claim; I: shipping]. So INC has real in-chip silicon but
**not yet a broad installed ecosystem** as of 2026 — production vs roadmap must be kept
distinct [I].

## TSS — transport security, in one paragraph
UET ships **TSS (Transport Security)** as a "first-class citizen," co-designed with the
transport, not bolted on [F: spec §3.4; arXiv §3.4]. It is **end-to-end Authenticated
Encryption (AEAD), default AES-GCM-256 with a 16B ICV**, authenticating the PDS+SES
headers, payload, and IP addresses (with optional enciphering). Keys live in **Secure
Domains (SD)** — groups of FEPs sharing a **Secure Domain Key (SDK)** distributed by an
SDME, with KDF-derived source keys and per-source keys for client-server, so key
management scales to massive deployments. **Replay protection** comes from **PSN + a
per-epoch Time-Stamp-Counter** (16-bit epoch + 48-bit counter), IV-mask randomization,
key/AN rotation, and PDCs that re-open every ~2³¹ packets to avoid PSN-wrap replay. It is
**not** MACsec/TLS/IPsec (though MACsec can still layer at L2); it's a purpose-built
transport cipher implemented at the **FEP (NIC)**, designed to pair with host-side
protections like PCIe **TDISP**. This is what closes the 0-RTT replay exposure noted in
[./31-uetch-deep-dive.md](./31-uetch-deep-dive.md): with TSS on, replay is prevented; with
security off, the "dynamic connection protocol" is replay-susceptible [F: spec].

## Lab — what to measure
1. **ECMP + egress ECN is the whole ask** — verify your switch fabrics expose egress ECN
   (most merchant 400/800G do); if they can mark at egress, UET NSCC has its signal. *Expect:*
   no CNP-like packets anywhere in the trace (grep the NIC counters for CNP = 0 is
   meaningful for NSCC vs DCQCN side-by-side) [A/I].
2. **NSCC vs DCQCN behavioural test** — run a bursty all-to-all (see ./34) under NSCC vs a
   DCQCN baseline; watch **incast recovery** (QA) and whether the lossy fabric stays at
   line rate. *Expect*: NSCC recovers incast in burst time; DCQCN needs lossless PFC to
   not collapse [I: hypothesis to test].
3. **INC on a Tomahawk Ultra** — there is no commodity pod to rent [I]; the lab step is
   conformance: run `fi_collective()` through the OFI provider and confirm the switch
   absorbs the reduce (fewer host round-trips). *Expect*: verify via the vendor's OFI
   provider + switch telemetry.
4. **Replay without TSS** — on a bench, flip TSS off and replay a captured 0-RTT PDC
   creation; *expect* duplication (the documented susceptiblity), then re-enable TSS and
   confirm replay is blocked by the PSN/epoch counter [F/A].

> **Where this fits.** Transport internals in [./31-uetch-deep-dive.md](./31-uetch-deep-dive.md);
> what all this traffic *is* — collectives — in [./33-collective-communication.md](./33-collective-communication.md)
> and [./34-moe-all-to-all.md](./34-moe-all-to-all.md); benchmarking in
> [./44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md);
> GPU-side software in [../GPU-Communication/README.md](../GPU-Communication/README.md).

## Key Takeaways
1. **CMS = Congestion Control + Load Balancing** per Congestion Control Context (CCC), needing **only ECMP + egress ECN** from switches — no exotic switching features — which is why UET promises to run on plain installed Ethernet. [F]
2. **NSCC** is the mandatory, sender-based controller: a per-CCC window from **RTT (multi-bit) + ECN-CE (single-bit)** decided by a 4-case table, with **no CNP packet** — the congestion signal rides inside normal ACKs; Quick Adapt + packet trimming keep up with sub-millisecond incast. [F]
3. **RCCC** is the optional receiver-credit algorithm: the receiver grants per-source credits (optimistic credits start early) — the **incast optimizer**, run alongside NSCC. [F]
4. **INC (In-Network Collectives)** offloads AllReduce/Broadcast/AllGather into switches via libfabric `fi_collective()` — "first standardized over Ethernet" — shipped in-chip in the **Broadcom Tomahawk Ultra** but spec-optional and early-ecosystem. [F/I]
5. The names **CCv1/CCv2/TACC do not exist in UET 1.x** — the correct pair is **NSCC + RCCC**; and **TSS** (AES-GCM-256, Secure Domains, PSN+epoch replay protection) closes the 0-RTT replay exposure of ./31. [F]

## Related
- [31-uetch-deep-dive.md](./31-uetch-deep-dive.md) — the transport (PDCs, RUD/ROD/RUDI, spraying, LLR) that CMS runs on.
- [33-collective-communication.md](./33-collective-communication.md) — the collectives that produce the incast NSCC/RCCC and INC handle.
- [34-moe-all-to-all.md](./34-moe-all-to-all.md) — the AllToAll/skew workload that stresses congestion control hardest.
- [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md) — how to measure CC, telemetry, and INC behavior.
- [README.md](../GPU-Communication/README.md) — the GPU-side software issuing this traffic.
- [55-cheat-sheet.md](./55-cheat-sheet.md) — quick reference across the section.

## References
- UEC Specification v1.0.3 — CMS/NSCC/RCCC (§3.6), INC (§2.2.5.4.5), TSS (§3.4) [F].
- "Ultra Ethernet's Design Principles and Architectural Innovations," arXiv:2508.08906 [F: author paper].
- UEC spec-update blog — 1.0.2 CC-algorithm corrections; INC billing [F].
- Broadcom Tomahawk Ultra release (Jul 15, 2025) — in-chip collectives, UEC-compliant [F vendor / I].
- Zhu et al. 2015, "Congestion Control for Large-Scale RDMA Deployments" (DCQCN) — the incumbent NSCC is contrasted against [F/A].
