# Juniper AI Fabric (QFX / Junos / Apstra)
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: Juniper ai_fabric_ip_services docs, NetworkWorld 800G buyer's guide (QFX5240), Juniper/Mist/Apstra product pages; fetched 2026-08-25. Juniper = acquired by HPE (closing 2025).

## 30-Second Explanation
Juniper's AI-fabric answer is **Top-of-Rack 800G (QFX5240, Broadcom Tomahawk 5) + the Apstra
controller (intent-based fabric modeling and telemetry) + Mist AI assurance, all on Junos**.
Like Arista, Juniper makes **no merchant-switch ASIC of its own** — it buys Broadcom and
differentiates in **software and intent-based automation** (Apstra's "AaaS for AI") plus
validated RoCEv2/DLB reference fabrics. Its congestion story is the standard **RoCEv2 lossless
(PFC/ECN) + DCQCN** model, with **dynamic load balancing** and RDMA-aware LB on the switches,
and UET-readiness/packet-trimming flagged where the silicon supports it. Juniper's edge over
its merchant peer Arista is ops: Apstra turns fabric bring-up and change into a model-checked,
intent-based workflow rather than per-switch CLI. [F: Juniper; [I] synthesis]

## How Juniper's AI fabric is built
```text
   Apstra controller (intent-based fabric modeling, telemetry, day-0..2 automation)
        │  (models the fabric; validates changes against intent before deploy)
        ▼
   QFX5240 leaf ──── QFX5240 / spine-class (TH5, 800G)   ← Junos onboard
        ▲
        │  800G down / uplinks; RoCEv2 lossless (PFC/ECN), DLB
   GPU / accelerator (validated w/ AMD MI300-class & RoCE NICs)
```

## Architecture
**Junos** is the single NOS across QFX; **Apstra** provides intent-based AaaS ("Apstra AaaS
for AI") that models the fabric, automates leaf-spine bring-up, and validates every change
against the declared intent before it is applied; **Mist** adds AI-native wired/wireless
assurance and is being merged into HPE-Juniper AI networking. The reference design is a
validated RoCEv2 leaf-spine (often with AMD MI300 stacks). [F: Juniper]
- Data plane: merchant-silicon Ethernet, cut-through, PFC/ECN/ETS where configured.
- Control plane: **Junos** (BGP EVPN / IS-IS for the backend), driven by Apstra's modeled
  config rather than hoarded CLI snippets. [I]

## Switch ASIC
**Juniper does not make its own data-center switch ASIC** — merchant Broadcom. [F]
| Model | Role | ASIC | Ports | Status |
|---|---|---|---|---|
| **QFX5240** | high-density 800G ToR/AI | **Broadcom Tomahawk 5** | 64 × 800G in 2U (QSFP-DD/OSFP) | shipping [F: NetworkWorld buyer's guide] |
| QFX5220 | earlier 400G ToR | Tomahawk 2/3-era | 400G | older [F/I] |
| QFX5120/5260 | **UNVERIFIED** as distinct shipping AI models | — | — | not confirmed [I] |

- The modern 800G AI ToR is the **QFX5240**; "QFX5260" and a "7250"-style AI spine naming are
  **not confirmed** in the research notes. [I/UNVERIFIED]

## NIC / DPU / SuperNIC
Juniper is a **switch/controller vendor**, not a NIC/DPU maker; endpoints are third-party
RoCEv2 NICs (NVIDIA ConnectX, Pensando, AMD MI300's NICs, etc.) running DCQCN. This is the same
"no endpoint lock-in" stance as Arista. [F/I] · DPU taxonomy: [37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md).

## Topology
**Intent-modeled leaf-spine** (and multi-tier at scale) via Apstra; the AI fabric is a
**RoCEv2 lossless** reference design that Apstra stands up and validates. Multi-rack to
multi-thousand-accelerator fabrics are the target; **no crisp independent scale number was
found** and none is fabricated here. [F/I — scale **UNVERIFIED**] · Clos math:
[42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md).

## Load balancing
- **Dynamic Load Balancing (DLB)** on QFX — Broadcom-class flowlet/flow LB. [F]
- **Weighted packet-spraying / RDMA-aware LB** — references to RDMA-aware LB and
  congestion-aware routing appear in Juniper AI-fabric docs; **the exact "WDS" (weighted
  dynamic/static) as a distinct Juniper mechanism is UNVERIFIED**. [I]
- DLB is automated into the fabric by **Apstra** (DSCP/PCP automation for RDMA lossless). [F]

## Congestion control
**RoCEv2 + DCQCN at the NICs**, with ECN/PFC at the switches, per the Juniper reference
designs. No Juniper-proprietary end-to-end CC transport is published. [F: Juniper docs,
per research notes] · DCQCN: [21-dcqcn.md](./21-dcqcn.md).

## PFC strategy
Standard lossless RoCEv2 **PFC** with multiple configurable lossless priorities; Apstra
automates the threshold/policy. A **PFC watchdog** (per-priority timers; detect a stalled
lossless class) is part of safe-PFC operation. [F] · PFC watchdog/dangers:
[19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md).

## ECN strategy
**ECN marking + WRED** to drive DCQCN, standardized via the reference fabric; **congestion-aware
routing**/LB reacts to marked state where supported. [F/I] · ECN/WRED: [20-ecn-wred.md](./20-ecn-wred.md).

## Telemetry
**Mist AI** assurance + **Apstra analytics/telemetry streaming** (gRPC + Junos native streaming).
Apstra's value is *model-based* telemetry: it compares live fabric state to the modeled intent,
so deviations (a congested link, a dropped lossless priority) surface as intent violations
rather than raw counter floods. [F] → [40-network-telemetry.md](./40-network-telemetry.md).

## Automation
**Apstra** is the headline: intent-based AaaS, day-0 (fabric modeling/config), day-1 (deploy),
day-2 (change validation, ZTP), all model-checked. This is Juniper's clearest differentiator
vs Arista/Cisco on AI fabrics. [F]

## GPU integration
Validated reference AI fabrics typically **with AMD (MI300-class)** and standard RoCE NICs;
works with any RDMA accelerator. Juniper's integration depth is at the **fabric/automation**
layer, not a GPU/NCCL plugin. [F/I]

## NCCL / RCCL integration
Standard **NCCL-over-RoCEv2**; the Apstra validation of RoCEv2 priorities/DLB is what makes
NCCL traffic behave, not a Juniper NCCL shim. [F/I] · NCCL: [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md).

## Scale
Apstra-managed **multi-rack to multi-thousand-accelerator** fabrics are the claimed scope, but
**no crisp scale number was confirmed**; left UNVERIFIED rather than invented. [UNVERIFIED]

## Strengths
- **Exceptional intent-based ops**: Apstra fabric modeling/automation + Mist assurance is the
  class leader among these vendors. [F/I]
- **Strong 800G ToR** on TH5 (QFX5240), clean Junos. [F]
- **HPE tailwind**: joining HPE's AI stack (HPE Cray/Slingshot + HPE-AMD) broadens reach. [F/I]

## Limitations
- **Merchant-silicon parity**: no unique spray/CC protocol differentiator vs Arista — leans on
  Broadcom features + Apstra. [I]
- **HPE integration churn**: post-acquisition roadmap disruption/overlap with HPE switching. [I]
- **UET specifics unconfirmed**: trimming/UET NIC status not a crisp, shipped Juniper story. [I]

## Best-fit
Enterprises standardizing on **HPE/AMD (MI300)** stacks, and ops-focused shops that want
**Apstra/Mist automation** to run a multi-vendor RoCEv2 fabric with minimal per-box CLI toil.
[F/I]

## UET readiness (packet trimming)
- **Packet trimming** and UET-readiness are **supported where the merchant silicon supports
  them** (Broadcom TH5 class = trimming-capable); **specific Juniper UET/UEC silicon shipping
  status is UNVERIFIED** in the research notes. [I/UNVERIFIED]
- Juniper participated in a **VIAVI+Juniper UET interop test (Tokyo, 2025)** — an early public
  UET validation, not a shipping product. [I: per research-uec §7] · UEC/UET:
  [30-ultra-ethernet-consortium.md](./30-ultra-ethernet-consortium.md), [31-uetch-deep-dive.md](./31-uetch-deep-dive.md).

## Comparison: the three merchant/open vendors
| Dimension | Juniper | Arista | Cisco |
|---|---|---|---|
| Switch ASIC | merchant (TH5) | merchant (TH5/Jericho3-AI) | **in-house** Silicon One |
| Differentiator | **Apstra/Mist intent ops** | massive-radix + UEC-forward DLB/spray | deep-buffer P200 + AFD |
| AI ToR flagship | QFX5240 (64×800G) | 7060X6 (64×800G) | Nexus 9364E-SG2 (64×800G) |
| CC model | RoCEv2 + DCQCN (+DLB) | RoCEv2 + DCQCN; UEC later [A] | RoCEv2 + DCQCN (+AFD/WRED) |
| UEC | member; UET interop tested [I] | founding, UEC-forward | founding member |

## Apstra in practice (the ops differentiator)
The concrete value of Apstra over a CLI-driven fabric: [F: Apstra intent model]
- **Fabric as a model**, not a pile of switch configs: you declare leaves/spines/links/IP
  fabrics once; Apstra generates and applies per-box Junos.
- **Change validation**: every proposed change is dry-run against the model and rejected if it
  violates intent (e.g., a change that would leave a lossless priority un-ECN'd).
- **Telemetry-to-intent**: live state streaming compared to the model means a PFC storm or a
  bad DSCP mapping raises as an *intent violation* with the offending object, not a raw counter.
- For RoCEv2 AI specifically, Apstra automates **DSCP/PCP mapping, DLB, and lossless thresholds**
  so NCCL traffic lands on the right class by construction — the same job Cisco's CLI workflow
  above does by hand. [F/I]

### Example: sizing the intent model's lossless class
A hand-checkable design decision Apstra's model forces you to state explicitly — which
priorities are lossless and what PFC headroom they get: [I: derivation from constants bank]
```text
Given: 800G leaf downlink to a GPU, PFC threshold at 1 µs react time.
PFC headroom = 800 Gb/s × 1 µs = (800e9/8 B/s) × 1e-6 s = 100,000 B = 100 KB  [E]
So a 9K-frame lossless queue needs ~11 jumbo frames of headroom at 800G (round up for safety).
```
The point: Apstra (or any intent tool) should *derive* this from the topology, not have it
typed per-switch. `800 Gb/s = 100 GB/s` and `PFC thr (800G,1us)` follow the constants-bank
pattern (`verified-constants.md`). [E]

## Key Takeaways
1. Juniper = **QFX (TH5 800G) + Junos + Apstra + Mist**; no own ASIC, no own NIC.
2. Apstra intent-based automation is the **real differentiator** — fabric-as-model, not CLI.
3. Load balancing = **DLB / RDMA-aware LB / congestion-aware routing**, automated by Apstra;
   "WDS" is UNVERIFIED.
4. CC = standard **RoCEv2 + PFC + ECN + DCQCN** (+ PFC watchdog); no proprietary transport.
5. UET/trimming = **silicon-dependent, UNVERIFIED as a shipped Juniper story**; HPE acquisition
   is both tailwind and churn.

## Related
- [26-arista-etherlink.md](./26-arista-etherlink.md) — the closest merchant-software peer.
- [27-cisco-ai-ethernet.md](./27-cisco-ai-ethernet.md) — the in-house-ASIC peer.
- [24-vendor-landscape.md](./24-vendor-landscape.md) — full vendor/ASIC/NIC map.
- [30-ultra-ethernet-consortium.md](./30-ultra-ethernet-consortium.md) / [31-uetch-deep-dive.md](./31-uetch-deep-dive.md) — the UET path Juniper tests.
- [49-design-decision-tree.md](./49-design-decision-tree.md) — when intent-based vs silicon matters.

## References
- Juniper `ai_fabric_ip_services` reference-fabric docs [F: Juniper docs].
- QFX5240 via NetworkWorld 800G buyer's guide (2024/25) [F: NetworkWorld].
- Juniper/Mist/Apstra product pages [F]; HPE acquisition noted [F].
- [E] constants from the section bank (computed 2026-08-25).
