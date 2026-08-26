# Ultra Ethernet Consortium: Why & What
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: UEC press releases (founding, 2023-07-19), UEC Specification v1.0 (562 pp; June 11 2025), UEC Specification-History page, UEC 1.0.2/1.0.3 release notes, arXiv:2508.08906 (author paper); fetched 2026-08-25.

## 30-Second Explanation
The **Ultra Ethernet Consortium (UEC)** exists because **RoCEv2 — RDMA carried in UDP/IP over
lossless Ethernet with PFC + DCQCN — does not scale well enough for massive AI fabrics.** RoCEv2
demands strict in-order, lossless delivery guaranteed by PFC; that means big buffer headroom,
head-of-line blocking, congestion spreading, and traffic locked to **one hash path** per flow
(no packet spraying), while **incast + Go-Back-N** waste bandwidth and **ECN is slow** to
propagate. UEC was announced **July 19, 2023** (a Linux Foundation Joint Development Foundation
project) by AMD, Arista, Broadcom, Cisco, Eviden/Atos, HPE, Intel, Meta, Microsoft, to build an
**open, clean-slate, RDMA-inspired transport over plain Ethernet** — **UET** — designed for
per-packet multipathing, lossy-or-lossless operation, fast loss recovery, and libfabric
compatibility. The result is a single **562-page spec**, first released **June 11, 2025 (1.0)**,
now at **1.0.3 (July 16, 2026, current)**. This page is the "why and what" overview; the
transport internals are in [31-uetch-deep-dive.md](./31-uetch-deep-dive.md).

## Why UEC exists: the concrete gaps in RoCEv2
The consortium's stated technical motivation — from the founding PR agenda, the UEC spec-papers,
and the author paper (arXiv:2508.08906) — names five concrete weaknesses in RoCEv2 for AI/HPC
at scale: [F: UEC materials + arXiv:2508.08906].
1. **PFC headroom & head-of-line blocking.** RoCEv2 embeds InfiniBand's transport, which
   requires **lossless, strict in-order** delivery guaranteed by **PFC**. PFC demands a separate
   traffic class with substantial **headroom buffer**, and causes **congestion spreading** and
   **head-of-line blocking** across the fabric. [F]
2. **In-order pins each flow to one hash path.** In-order delivery means flows use **ECMP flow
   hashing**, which **polarizes traffic** and limits path choice. [F]
3. **No packet spraying.** A single flow is pinned to one hash path; hash collisions can halve
   effective bandwidth — no per-packet multipathing. [F]
4. **Incast + Go-Back-N.** Crash-synchronized all-to-all / collective traffic overloads the last
   hop (incast); RoCE's **Go-Back-N** recovery retransmits long runs and wastes bandwidth, and
   **DCQCN relies on ECN + PFC** which cannot react fast in short, sub-millisecond AI
   transfers. [F]
5. **Slow ECN / limited telemetry.** No fast end-to-end loss signaling; ECN is marked only at
   ingress and propagates slowly. [F]

Nokia's UEC blog summary: RoCE "struggles in massive AI clusters … head-of-line blocking from
PFC and the lack of real-time congestion signaling." [F: ultraethernet.org, 2025-10-29]

## Why not just fix RoCEv2?
The UEC answer: the problems are **inherited from InfiniBand's transport** (connection/QP state,
so connection setup and per-peer state cap scale; strict in-order; Go-Back-N; PFC-dependent
losslessness). Patching RoCEv2 piecemeal leaves the architecture intact. UEC instead built a
**clean-slate transport on the existing Ethernet PHY/MAC**, keeping Ethernet's ecosystem while
replacing the transport and adding link/security layers. [F/I: author account]

## Consortium facts [F: UEC founding press release, 2023-07-19]
- **Announced July 19, 2023** (NOT January 2023 — that is when the pre-consortium group settled
  the architecture, not the public founding). [F]
- Governance: a **Linux Foundation Joint Development Foundation (JDF)** project. [F]
- **Founding members:** AMD, Arista, Broadcom, Cisco, Eviden (Atos), HPE, Intel, Meta,
  Microsoft. [F]
- New-member applications opened Q4 2023; membership grew to **100+ companies / 1,500+
  participants** by end-2024. [F: author account]
- Pre-history (author narrative, arXiv:2508.08906): a small AMD/Broadcom/HPE/Intel/Microsoft
  group formed Q1 2022 on a next-gen open Ethernet transport, codenamed **"HiPER"**, renamed
  **Ultra Ethernet (UE)**; consortium July 2022; combined HPC messaging + security + DC
  congestion management by **January 2023**. [F: author account — secondary]
- **NVIDIA**: joined **~August 2024** (quietly; logo on UEC homepage) but **continues to push
  InfiniBand (Quantum-X) and its own Spectrum-X Ethernet**, and has **not shipped UET silicon**
  — public stance: "we will support new standards that may emerge." So NVIDIA participates
  while competing with UEC via Spectrum-X. [I/F]

## What the one spec covers (a single 562-page document)
The spec is **one 562-page document** (not separate part-files) covering, per its Contents and
the author paper: [F: spec + arXiv §1.1/§3]
- **Software**: libfabric (OFI) API mapping — "based on libfabric v2.0 APIs, extended for
  UET," so NCCL-like CCLs and MPI migrate without code changes. [F]
- **Transport (UET)**: Semantics (SES), Packet Delivery (PDS), Congestion Management
  (CMS/CC), Transport Security (TSS). [F]
- **Link layer**: Link-Level Retry (LLR) + optional Credit-Based Flow Control (CBFC). [F]
- **Physical layer (PHY)**: 100 Gb/s per lane baseline; **200 Gb/s per lane added in 1.0.3**. [F]
- **Profiles**: AI Base / AI Full / HPC. [F]
- **In-network collectives (INCs)**: the libfabric `fi_collective()` API to offload collectives
  into switches (optional, per-profile) — billed by UEC as the first standardized Ethernet
  collective offload. [F]
- **Compliance checklists.** [F]

### The UEC stack (how the parts fit)
```text
   Frameworks / CCLs (NCCL-like, MPI, NVSHMEM)          ─ software, unchanged API
   libfabric (OFI) v2.0 ─ mapped to UET                  ─ spec: Software
   ─────────────────────────────────────────────────
   UET Transport:  SES (semantics) · PDS (delivery)      ─ spec: Transport
                   CMS (NSCC/RCCC CC + LB) · TSS (AES-GCM-256)
   ─────────────────────────────────────────────────
   Link layer:  LLR (link retry) · CBFC (credit FC, opt) ─ spec: Link
   ─────────────────────────────────────────────────
   Ethernet PHY/MAC: 100G/lane baseline; 200G/lane (1.0.3)
   Profiles AI-Base / AI-Full / HPC · INC collectives · compliance
```
The point of the single document: **one transport + one API + one PHY profile set**, so a
UET NIC, a UET switch, and a libfabric app can be validated against the *same* compliance text
— unlike the multi-part sprawl some protocol stacks ship. [F/I: framing]

## Specification timeline [F: UEC Specification-History page + release notes]
| Version | Release date | Key content |
|---|---|---|
| **1.0** | **Jun 11, 2025** | Initial public release (562 pp). |
| **1.0.1** | **Sep 5, 2025** | Editorial clarifications; **RCCC source algorithm correction**. |
| **1.0.2** | **Jan 2026** (RN: 01/28/26) | **CMS congestion-control algorithm corrections** (RCCC/credit handling) + editorial. |
| **1.0.3** | **Jul 16, 2026** (current) | Editorial clarifications; **adds 200 Gb/s-per-lane PHY**; LLR/CBFC race fixes; CC_Update LLR-eligible; MP_Range<128; PHY CtlOS protection. |

> **Correction worth flagging:** the common claim "UET spec published **Nov 2025**" is
> **wrong** — the only 2025 post-1.0 release is **1.0.1 (Sep 5, 2025)**; there is no November
> 2025 release in the primary record. [F]

### Four misconceptions to drop
1. **"UEC founded January 2023"** → announced **July 19, 2023**; Jan 2023 is when the proto-group
   settled the architecture, not the founding. [F]
2. **"UET spec released November 2025"** → **1.0 was June 11, 2025**; no Nov-2025 release. [F]
3. **"UEC congestion control is CCv1/CCv2/TACC"** → the spec terms are **NSCC + RCCC**; neither
   CCv1/v2 nor TACC appears in UET 1.x. [F]
4. **"NVIDIA is a UET silicon vendor"** → NVIDIA joined **~Aug 2024** but ships **no UET NIC**;
   it pushes Spectrum-X. [I/F]

## The ladder: Traditional Ethernet → RoCEv2 → enhanced AI Ethernet → UET
```text
 Traditional Ethernet          RoCEv2                    enhanced AI Ethernet          UET (Ultra Ethernet)
 ─────────────────          ──────────                ─────────────────────        ───────────────────
 lossy, TCP, ECMP           RDMA in UDP/IP            RoCEv2 + vendor spray/       clean-slate RDMA-
 async, north-south         PFC lossless + DCQCN      CC (Spectrum-X TCC,          inspired transport
                            in-order, 1 hash path     DLB/trim/MRC, etc.)          connectionless (PDC)
                                                                                    per-packet spraying
                                                                                    lossy-or-lossless
                                                                                    NSCC/RCCC + LLR + CBFC
 ────────────────────────────►────────────►───────────┴───────────────────►───────────────►
  2000s IC era            ~2014 (RFC-style)        2022–2025 (vendor kits)      spec 1.0 2025, silicon early
```
The ladder is *additive capability*, not a clean replacement ladder: enhanced AI Ethernet and
UET overlap, and vendors straddle them (e.g. Arista ships EOS RoCE + DLB today and builds for
UET; see [26-arista-etherlink.md](./26-arista-etherlink.md)). [I: framing]

## Where UEC fits in the fabric taxonomy
A distinguishing feature vs both RoCEv2 and InfiniBand: **no QP/connection setup handshake**
(UET uses ephemeral Packet Delivery Contexts, 0-RTT), and **no fundamental losslessness
requirement** (designed best-effort/lossy with optional CBFC; runs over lossless too). → detail
in [31-uetch-deep-dive.md](./31-uetch-deep-dive.md), CC in [32-uetch-congestion-and-in-network.md](./32-uetch-congestion-and-in-network.md). [F]

## UET vs RoCEv2 vs InfiniBand at a glance
| Dimension | UET (UE 1.x) | RoCEv2 | InfiniBand |
|---|---|---|---|
| Connection model | connectionless, ephemeral PDCs, 0-RTT | connected QPs, setup handshake | connected QPs, setup handshake |
| Ordering | RUD/RUDI out-of-order + zero-copy; ROD optional in-order | strict in-order | strict in-order |
| Multipath | **per-packet spraying** (EV in UDP port, IANA 4793) | ECMP flow hashing only | SL/adaptive routing |
| Lossless required | **no** (designed lossy; optional CBFC) | yes (PFC) | yes (credit FC) |
| Congestion control | **NSCC** (ECN+RTT) + optional **RCCC** | DCQCN (ECN+CNP+PFC) | IB CC (BECN), less common |
| In-network compute | **INC** (fi_collective), standardized | none | SHARP (NVIDIA, proprietary) |
| API | libfabric (OFI) | Verbs/libfabric | Verbs/OFI |
| Openness | open (JDF/Linux Foundation) | open spec | IBTA, NVIDIA-dominated |

([A/F — synthesized from spec + arXiv:2508.08906 + UEC blog]; full table:
[31-uetch-deep-dive.md](./31-uetch-deep-dive.md).)

## Shipping status as of 2026-08
- **Shipping / compliant:** Broadcom **Tomahawk 6** (Jun 3, 2025) and **Tomahawk Ultra**
  (Jul 15, 2025) are UEC-compliant switches, Tomahawk Ultra doing in-network collectives;
  **AMD Pensando Pollara 400** is billed the first UEC-compliant NIC (sampled Q4'24 / available
  H1'25). [F vendor / I shipping]
- **Validating:** switch vendors (VIAVI+Juniper Tokyo interop 2025; Nokia end-to-end UET test on
  7220/7250 IXR). [I]
- **Not shipped UET:** NVIDIA (no UET silicon; pushes Spectrum-X). Intel UET NIC status
  **UNVERIFIED**. Broad/independent commentary expects broader production adoption through
  2026–2027; UET NICs are early-deployment as of 2026. [I]
- General guidance: anything UET-flavored is **spec/early-silicon** unless a vendor page says
  otherwise. [F + [I]]

## Key Takeaways
1. UEC exists to fix five **concrete RoCEv2** gaps: PFC headroom/HOLB, one-hash-path pinning,
   no packet spraying, incast+Go-Back-N, slow ECN. [F]
2. Founded **July 19, 2023**, Linux Foundation JDF; original members AMD/Arista/Broadcom/Cisco/
   Eviden/HPE/Intel/Meta/Microsoft. [F]
3. One **562-page spec**: software (libfabric), UET, PHY (200G/lane in 1.0.3), LLR+CBFC,
   profiles, INCs, compliance. [F]
4. Timeline: **1.0 Jun 11 2025 → 1.0.1 Sep 5 2025 → 1.0.2 Jan 2026 → 1.0.3 Jul 16 2026
   (current)**. No "Nov 2025" release. [F]
5. **NVIDIA joined ~Aug 2024 but ships no UET silicon** — it competes via Spectrum-X. [I/F]
6. UET is **connectionless, lossy-first, spraying-native** — the opposite design center from
   RoCEv2's connected, lossless, single-path center. [F]

## Related
- [31-uetch-deep-dive.md](./31-uetch-deep-dive.md) — the transport (PDCs, RUD/ROD/RUDI, spraying, LLR).
- [32-uetch-congestion-and-in-network.md](./32-uetch-congestion-and-in-network.md) — NSCC/RCCC + INCs.
- `./30`'s ladder ties into [02-ai-networking-taxonomy.md](./02-ai-networking-taxonomy.md) (the five domains).
- [26-arista-etherlink.md](./26-arista-etherlink.md), [27-cisco-ai-ethernet.md](./27-cisco-ai-ethernet.md) — vendor UEC positioning.
- [49-design-decision-tree.md](./49-design-decision-tree.md) — when RoCEv2 vs UET vs IB.
- [README.md](../Networking/README.md) — the one-page primer.

## References
- UEC founding press release + JDF mirror (2023-07-19) [F: ultraethernet.org].
- UEC Specification v1.0 PDF (562 pp, 2025-06-11); 1.0.2/1.0.3 release notes [F].
- UEC Specification-History page (version/dates) [F].
- "Ultra Ethernet's Design Principles and Architectural Innovations," arXiv:2508.08906
  (2025-08-12) [F: author paper — treat author-account items as secondary].
- UEC "Why Ethernet Matters for AI Networking" blog (Nokia, 2025-10-29) [F].
- Vendor shipping: Broadcom IR (TH6, Tomahawk Ultra), AMD/NV tightness per NetworkWorld/Futuriom
  (NVIDIA joined ~Aug 2024) [F vendor / I].
