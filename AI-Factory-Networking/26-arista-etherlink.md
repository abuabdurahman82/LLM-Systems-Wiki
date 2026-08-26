# Arista Etherlink & EOS AI
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: Arista AI-networking pages (2025), 7800R4 / 7060X6 datasheets, Arista PR 2025-03-12, Arista "Demystifying Ultra Ethernet" blog, NetworkWorld buyer's guide; fetched 2026-08-25.

## 30-Second Explanation
Arista's AI-fabric answer is **"open, standards-based Ethernet plus an AI feature kit on the
proven EOS operating system."** Arista makes no data-center switch ASIC of its own — it buys
merchant silicon (**Broadcom Tomahawk 5** for fixed leaves, **Jericho 3-AI** for the modular
spine) and differentiates in software: EOS, **CloudVision**, CV UNO telemetry, and a
**massive-radix two-tier** topology story. Etherlink is that collection of AI optimizations
(DLB, packet spraying, trimming, MRC, congestion signaling) built to be **forward-compatible
with Ultra Ethernet Consortium (UEC)** specs; Arista is a founding UEC member. The positioning
is deliberately the "open, no-vendor-lock-in" alternative to NVIDIA Spectrum-X: multi-vendor
NICs, huge single-switch radix, mature hyperscale ops, standards-path rather than proprietary
end-to-end protocol. [F: Arista + [I] synthesis]

## How Etherlink sits in the taxonomy
```text
                       Scale-out backend fabric (cross-rack, RDMA)
                                    │
      ┌─────────────────────────────┼─────────────────────────────┐
      │                             │                             │
 NVIDIA Spectrum-X        Arista Etherlink (EOS AI)         Plain RoCEv2
 (proprietary, SuperNIC)   (open, merchant silicon)         (merchant, no vendor kit)
```

## Architecture
A **two-tier (leaf–spine) Clos** is the headline pattern, but Arista's differentiator is
**radix**: enough ports on one logical spine switch to collapse what other vendors would run
as a 3-tier or multi-plane fabric. The Etherlink "kit" layers software features on EOS — no
change to the underlying Ethernet/IP forwarding model is required; every feature is additive
and UEC-aligned. EOS is a founding member of the UEC. [F: Arista]
- Data plane: standard Ethernet L2/L3, cut-through, PFC/ECN/ETS QoS where configured.
- Control plane: EOS (BGP EVPN, VRRP/MLAG on the front-end; the backend is typically a
  flattened L3 or EVPN leaf-spine).
- AI kit: DLB, PFC-aware DLB, ECN-aware scheduling, packet spraying, packet trimming, MRC,
  CSIG, telemetry. [F: Arista AI-networking page]

## Switch ASIC
**Merchant silicon — Arista does not design its own data-center switch ASIC.** [F]
| Model | Role | ASIC | Ports / capacity | Status |
|---|---|---|---|---|
| **7060X6** AI Leaf | fixed leaf | Broadcom **Tomahawk 5** | 64 × 800GbE (51.2 Tb/s) | shipping [F: Arista/NetworkWorld] |
| **7800R4** AI Spine | modular spine | dual **Jericho 3-AI** per linecard | 576 × 800GbE / 1152 × 400GbE; up to 460 Tb/s chassis | shipping [F: Arista datasheet] |
| 7800R3 / 7500R | earlier modular | Broadcom/Jericho prior gen | 400G-era | older [I] |

- **HyperPort**: on 7800R4, bonds four 800G ports into **3.2 Tb/s aggregate** logical links
  (vendor claim: 44% shorter JCT for AI flows). [F: Arista datasheet — vendor claim]
- 64 × 800GbE = 51.2 Tb/s → 800 Gb/s/port = 100 GB/s/port [E: constants bank].
- The "7500R7" label is **UNVERIFIED** — the flagship modern AI spine in the research notes is
  the 7800R4. [I]

## NIC / DPU / SuperNIC
**Arista ships no NIC/DPU/SuperNIC** — unlike NVIDIA (SuperNIC) or AMD (Pensando). [F/I] This
is a deliberate choice: Etherlink interoperates with **third-party NICs** (merchant RoCE NICs,
and UEC-ready NICs as they ship). The consequence is that the "smart endpoint" features that
Spectrum-X puts on the SuperNIC (receiver reordering, hardware CC) are, in the Arista story,
meant to be supplied by **UET NICs** (e.g. AMD Pensando Pollara, as they become available) —
or not at all until then. [I: inference from architecture]
- No vendor lock-in on the host adapter: standard RoCEv2 NICs work today.
- Full UEC/UET endpoint features depend on NIC hardware that is early-shipping as of
  2026-08 (see [30-ultra-ethernet-consortium.md](./30-ultra-ethernet-consortium.md)).

## Topology
**Massive-radix two-tier.** The pitch: a single high-radix spine (or two tiers) carries tens
of thousands of end systems, because the radix is large enough that you do not need a third
tier. [F: Arista]
```text
       800G rail planes (example: 8 NICs/node, 8 planes)
   ┌──────────────┐
   │ 7800R4 spine │  ← 576×800G plane (massive radix ⇒ fewer/more capable tiers)
   └──────┬───────┘
          │ 800G uplinks (rail plane k)
   ┌──────┴──────┐
   │ 7060X6 leaf │ ×N leaves
   └──────┬──────┘
          │ 800G downlinks (one NIC/GPU, rail-optimized)
       GPU server
```
- Rail-optimized and multi-plane patterns are supported; the headline is *fewer tiers via
  more radix*. [F] · Clos math: [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md).
- Vendor scale claim: **100,000+ accelerators with Etherlink**; 7800R4 extends to **27,000+
  800G ports as one logical cluster**. [F: Arista — vendor claim]

## Load balancing
The Etherlink feature set (all UEC-aligned, all in EOS): [F: Arista AI-networking page, 2025]
- **Dynamic Load Balancing (DLB)** — flowlet/flow-based ECMP enhancement; shifts flows off
  congested members based on short idle gaps, without reordering a tight flowlet.
- **PFC-aware DLB & ECN-aware DLB** — load-balancing decisions that read the PFC/ECN state of
  the fabric rather than blind hashing.
- **Packet spraying** — distributing packets of a flow across equal-cost paths (the UEC
  direction); receiver reassembly required (on the NIC).
- **Packet trimming** — drop/cut packet payload on congestion and signal the sender (UEC
  fast-loss style), rather than dropping whole packets.
- **MRC + Congestion Signaling (CSIG)** — multipath reliable connection transport and explicit
  congestion signaling, both R&D toward UEC.

Arista's own framing: UET moves from **flow-based distribution to source-based per-packet
spraying**, and Arista is building for that. [F: Arista "Demystifying Ultra Ethernet" blog]

## Congestion control
- **Baseline today:** RoCEv2 lossless + PFC, with **DCQCN** tuning at the NICs and
  EOS-side QOS/PFC-priority configuration. This is the generic RoCE story (see
  [21-dcqcn.md](./21-dcqcn.md)). [F]
- **Forward-compatible:** UEC congestion control (NSCC sender-based; RCCC receiver-credit;
  LLR link retry; CBFC credit-based flow control) is **roadmap/announced**, not fully
  shipping in 2026. [A]
- **No proprietary end-to-end CC protocol** (unlike NVIDIA TCC): Arista leans on the standard
  RoCE stack now and UEC CC next. [I]

## PFC strategy
**Standard RoCEv2 lossless via PFC** on a dedicated lossless traffic class; PFC priorities
accounting for RDMA traffic; PFC headroom sized on the switch. The UEC path is to *reduce
reliance on PFC* via CC + optional CBFC, but that is forward-looking. PFC-aware DLB already
reads PFC state to route around congestion. [F/A] · PFC basics/dangers:
[18-data-center-bridging.md](./18-data-center-bridging.md), [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md).

## ECN strategy
ECN/WRED marking at the egress (switch) to drive DCQCN; the AI kit adds **ECN-aware DLB** so
marked flows are rebalanced. UEC's egress-marked ECN + RTT is the roadmap. [F/A] · ECN/WRED:
[20-ecn-wred.md](./20-ecn-wred.md).

## Telemetry
**CloudVision** is the management plane; **CV UNO** (Universal Network Observability) unifies
fabric telemetry; **NetDL Streamer** streams high-resolution counters; EOS AI Agent + **AVA
AI** add AI-centric troubleshooting (job-centric, not just per-flow). [F: Arista PR 2025-03-12]
- Ai-Job observability: correlate a training job's NICs/ports to fabric symptoms — the
  telemetry KPI for AI (tail latency). → [40-network-telemetry.md](./40-network-telemetry.md).

## Automation
EOS is highly programmable (eAPI, gRPC, ansible/terraform, CloudVision automation workflows
and **CloudVision as Code**). Config is intent-driven at the fabric level via CloudVision
rather than per-box CLI catch-up. [F: Arista]

## GPU integration
No first-party GPU; integrates with **third-party NICs** and merchant-RoCE endpoints. Works
with NVIDIA GPUs over standard RoCEv2 NICs, and is positioned for multi-vendor GPU clusters
(AMD, Intel, custom). Jumbo MTU + rail pattern standard. [F/I]

## NCCL / RCCL integration
NCCL/RCCL run over standard RoCEv2 transport; **no proprietary Arista-only NCCL feature** is
documented — tuning stays at the collective + PFC/ECN level (explicit NCCL/GDR tuning beyond
generic RoCE is **UNVERIFIED** in the research notes). [I/UNVERIFIED] · NCCL over RoCE:
[04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md).

## Scale
- **100,000+ accelerators** with Etherlink (fixed + modular + distributed spines). [F: Arista
  vendor claim]
- 7800R4: **27,000+ 800G ports** as one logical cluster; 576×800G per chassis plane. [F: Arista
  vendor claim]
- These are vendor design-scope claims, not an independent measurement. [I]

## Strengths
- **Open / UEC-aligned**: standards path, no NIC-vendor lock-in, founding UEC member. [F]
- **Massive single-switch radix**: fewer tiers, fewer failure domains in the spine. [F/I]
- **Mature ops**: EOS + CloudVision + CV UNO are hyperscale-proven. [F]
- **Multi-vendor tolerant**: works with merchant RoCE NICs and (soon) UET NICs. [F/I]

## Limitations
- **Merchant-silicon parity**: no in-house ASIC and no differentiated proprietary
  end-to-end CC/spray beyond what Broadcom silicon + EOS deliver. [I]
- **UEC features are forward-compatible, not all shipping**: DLB/spray/trimming exist, but
  full UEC CC/LLR/CBFC depend on the ecosystem. [I/A]
- **Endpoint intelligence is external**: Arista relies on third-party NICs for receiver
  reassembly and hardware CC, unlike NVIDIA's SuperNIC. [I]

## Best-fit
Multi-vendor GPU AI factories and Ethernet-specialized operators that want open Ethernet,
mature ops, and **no NVIDIA networking lock-in**; hyperscalers/ODMs standardizing on
merchant silicon with UEC trajectory. [F/I]

## UEC positioning
Arista is a **steering/founding UEC member** and its roadmap (per-packet spraying, NSCC/RCCC,
trimming, INCs) tracks the UET transport. The honest statement: Etherlink is a **bridge
today** (RoCEv2 + PFC + DLB) with **UEC plumbing being added**. Vs Spectrum-X, it trades
today's proprietary hardware CC for open multi-vendor ubiquity — a bets-on-open bet. [F/I] ·
UEC deep-dive: [30-ultra-ethernet-consortium.md](./30-ultra-ethernet-consortium.md), [31-uetch-deep-dive.md](./31-uetch-deep-dive.md).

## Comparison: Etherlink vs the field
| Dimension | Arista Etherlink | NVIDIA Spectrum-X | Vendor-neutral RoCEv2 |
|---|---|---|---|
| Switch ASIC | merchant (TH5 / Jericho 3-AI) | in-house Spectrum-4 | merchant (TH4/TH5) |
| Endpoint | 3rd-party NIC (none of its own) | BlueField/ConnectX SuperNIC | any RoCE NIC |
| CC | RoCE DCQCN now; UEC NSCC/RCCC later [A] | closed-loop TCC (SuperNIC) | DCQCN |
| Multipath | DLB, spraying, MRC/CSIG (EOS) | per-packet spraying + TCC | ECMP (+option) |
| UEC standing | **founding member** | member ~2024, pushes Spectrum-X | n/a |
| Best-fit | open multi-vendor AI fabrics | NVIDIA-GPU AI factories | commodity Ethernet |

## Key Takeaways
1. Arista = **merchant silicon + EOS software kit**; no own ASIC, no own NIC.
2. Differentiator is **massive-radix two-tier** and **mature CloudVision/CV UNO ops**.
3. DLB / PFC-aware / ECN-aware / spraying / trimming / MRC / CSIG are the Etherlink features,
   all UEC-aligned.
4. It is the **open, no-lock-in** answer to Spectrum-X; full UEC CC is roadmap, not shipping.
5. Today it runs RoCEv2 + PFC + DCQCN; tomorrow it inherits UET from the merchant ecosystem.

## Related
- [25-nvidia-spectrum-x.md](./25-nvidia-spectrum-x.md) — the proprietary-comparable it's positioned against.
- [24-vendor-landscape.md](./24-vendor-landscape.md) — where Arista sits vs other vendors.
- [30-ultra-ethernet-consortium.md](./30-ultra-ethernet-consortium.md) — the standards body Arista co-founded.
- [49-design-decision-tree.md](./49-design-decision-tree.md) — open vs proprietary fabric decision.
- [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) — the two-tier radix math behind massive-radix.

## References
- Arista AI-networking solution page + "Demystifying Ultra Ethernet" blog [F: Arista, 2025].
- Arista 7800R4 Series + 7060X6 datasheets [F: Arista datasheet — vendor claims as tagged].
- Arista PR "Intelligent Innovations for AI Networking," 2025-03-12 [F].
- [E] constants from the section bank (computed 2026-08-25).
