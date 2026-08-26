# NVIDIA Spectrum-X Ethernet AI Fabric
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: NVIDIA Spectrum-X spec (nvidia.com/en-us/networking/spectrumx),
"Sets the Standard for Gigascale AI, Now With MRC" blog (2025), OCP MRC 1.0, OpenAI
MRC paper; fetched 2026-08-25. Vendor numbers = `[F: vendor spec]`; production vs
announced distinguished throughout; anything unconfirmed is UNVERIFIED.

## 30-Second Explanation
**Spectrum-X** is NVIDIA's Ethernet AI fabric — the only *complete-fabric* offering
in the market, binding its own **Spectrum-4 switch ASIC** with **ConnectX/BlueField
SuperNICs** plus management into one closed loop (see [24-vendor-landscape.md](./24-vendor-landscape.md) for
why that is distinctive). The idea: take RoCEv2 and add AI-native extensions —
**rail-optimized multi-plane topology**, **per-packet adaptive routing
(spraying)** with the **NIC reordering** the spray requires, and **hardware
congestion control (TCC)** — so an 800G Ethernet fabric behaves like InfiniBand
without IB lock-in. It targets the scale tier of **multi-plane topologies to
100k+ GPUs** (OpenAI runs it; Microsoft's Fairwater uses it). **Reading rule for
this page:** vendor numbers are *claims* — every `[F: vendor spec]` is what NVIDIA
publishes, NOT independent fact; "production vs announced" is called out in each
field, and the exact PFC policy ("PFC disabled?") is UNVERIFIED.

## The 16-field vendor template

### 1. Architecture
Purpose-built, end-to-end Ethernet platform for AI scale-out; pairs **Spectrum-4**
switch ASIC with ConnectX/BlueField **SuperNIC** endpoints, jointly implementing
AI-tuned RoCEv2 extensions. **[F: NVIDIA spec]** Not used for in-node scale-up —
that is NVLink (see [README.md](../Hardware/README.md)). The platform is why NVIDIA can
guarantee the *whole loop* behaves — a closed integration no merchant-RoCE vendor
offers. **[I]**

### 2. Switch ASIC
**Spectrum-4: 51.2 Tb/s aggregate, ~600 ns cut-through hop. [F: NVIDIA spec]**
```text
   Spectrum-4 (51.2 Tb/s)  ->  SN5600 / SN5610 (64 x 800GbE OSFP)
                             or 128 x 400GbE split; 2U     [F: NVIDIA spec]
```
In-house ASIC — NVIDIA is both switch vendor and NIC vendor; **not** a UEC
*steering* member; often framed as a proprietary alternative to UEC Ethernet. **[I]**

### 3. Switch models
**SN5600** (flagship 800G leaf/spine): 2U, **64 × 800GbE OSFP** (or 128 ×
400GbE), 51.2 Tb/s. **SN5610**: compact 2U, **64 × 800GbE OSFP**, 51.2 Tb/s. Both
**[F: NVIDIA spec]**; the 800G port-count is corroborated by independent buyer's-
guide sources **[F]**. Lower 400G members (SN5000/SN5200) exist. Production
(shipping) vs announced: SN5600/SN5610 are **shipping** [F: vendor].

### 4. SuperNICs
- **BlueField-3 SuperNIC** (Arm 16-core A78 + ConnectX-7 inline): dual 400GbE or
  1×800GbE; **reorders sprayed packets, runs AI congestion control in hardware,
  emits per-flow telemetry**. **[F: NVIDIA spec]**
- **ConnectX-8 SuperNIC**: 800 Gb/s, PCIe Gen6 x16. **[F: NVIDIA spec]**
- **ConnectX-7 endpoints** get RoCEv2 + adaptive routing but **not** the full
  Spectrum-X CC loop — **BlueField-3 is required for the closed loop**. **[F:
  NVIDIA spec]** ConnectX-8 is in the same boat unless deployed as a SuperNIC
  pairing. **[I]**

### 5. Topology: rail-optimized + multi-plane
Rail-optimized leaf-spine by default; **multi-plane** is a first-class feature —
"Spectrum-X Multiplane" gives hardware-accelerated load balancing *across planes*
(explicitly used with OpenAI + MRC). **[A/F mixed — NVIDIA blog, 2025]**. See
[38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md) for the topology math (plane count = NIC index
count; each plane a full Clos).

### 6. Load balancing: per-packet adaptive routing + NIC reordering
Spectrum-4 **sprays RoCEv2 elephant flows** (AllReduce/AllToAll) per-packet across
all equal-cost paths; the **receiver SuperNIC re-orders** before delivering to the
RDMA engine. Mice/control flows (via BTH deep-packet-inspection) keep static ECMP.
**[F: NVIDIA spec]** — this is NVIDIA's answer to the ECMP entropy/polarization
problem in [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md), and it depends entirely on
endpoint reordering (the "packet reordering is the root difficulty" theme). 
**Trade-off [I]:** per-packet spray needs the SuperNIC's reorder buffer and adds
end-to-end latency; the deterministic lossless positioning reduces PFC reliance.

### 7. Congestion control: TCC
**Targeted Congestion Control (TCC)** — hardware CC on the SuperNIC over
AI-optimized RoCEv2 extensions; **not** DCQCN (DCQCN is the generic RoCE baseline).
**[F: NVIDIA spec]** PFC policy: Spectrum-X uses lossless RoCE (PFC) but aims to
minimize reliance via TCC — the **exact PFC priority policy and the claim that
"PFC is disabled" are UNVERIFIED** (research found mixed evidence; NVIDIA's
deterministic-lossless positioning implies reduced reliance, not a blanket
disable). **[UNVERIFIED — see research-roce §6]**

### 8. MRC (Multipath Reliable Connection)
An RDMA transport carrying **one connection across multiple paths** for throughput,
load-balancing and resilience. **[F]** Co-developed with **NVIDIA, AMD, Broadcom, Intel,
Microsoft, OpenAI** (OCP MRC 1.0); proven in production (NVIDIA, Microsoft, OpenAI — OpenAI
published *"Resilient AI Supercomputer Networking using MRC and SRv6"*); **released
as OCP open spec (OCP MRC 1.0)**. **[F]** MRC enables massively-scaled two-tier
Ethernet — OpenAI architecture claims **>100,000 accelerators in a two-tier
fabric** (**[A]** — OpenAI paper claim, third-party-scale). MRC is distinct from
TCC (TCC = rate/congestion; MRC = multipath reliability transport).

### 9. Telemetry / management
NVIDIA **DOCA** + Cumulus **NetQ** / NVIDIA "AI Enterprise Networking" fabric
tooling; NVIDIA Base Command/DGX integration. **[F: NVIDIA]** The specific always-
on fabric-controller name is **UNVERIFIED** (older "Cumulus NetQ"; newer platform-
level integration). Per-flow telemetry from the SuperNIC feeds the management plane
— a differentiator of the closed loop. **[I]**

### 10. GPU integration (NCCL)
NCCL tuned; SuperNIC Direct Data Placement; GDR over RDMA. NVIDIA claims ~**1.6–1.9×
gen-AI performance vs standard Ethernet** — **[F: vendor claim / marketing]**, not
independent. Feeds GB200/GB300 NVL72 scale-out ([README.md](../Hardware/README.md)).

### 11. Scale claims
Multi-plane to **100,000+ GPUs** — xAI Colossus ~100k Hopper on Spectrum-X
(secondary source, **UNVERIFIED, treat as [A]**); MRC two-tier to >100k (OpenAI
paper) **[A]**. Production datacenters with NVIDIA: **Microsoft Fairwater**
(hundreds of thousands of Blackwell GPUs) and **OpenAI** — **[F/A]**, per NVIDIA and
third-party reporting. **These are [A]/[E] third-party-scale claims, not measured
NVIDIA facts.**

### 12. Production vs announced (the honest column)
```text
SHIPPING/production [F/vendor]:   Spectrum-4 ASIC, SN5600/SN5610, ConnectX-7,
                                 BlueField-3 SuperNIC, TCC, per-packet spray + reorder
ANNOUNCED/roadmap or [A]:         OpenAI 100k+ two-tier MRC scale claim; ConnectX-8
                                 full closed-loop detail; xAI Colossus exact scale
UNVERIFIED:                       exact PFC priority policy; "PFC disabled"; fabric
                                 controller name; 95%-throughput claim primary source
```

### 13. Strengths
Tight NV-NIC integration, per-packet spraying + hardware CC, deep telemetry, proven
at hyperscale (Microsoft Fairwater, production with OpenAI). **[F]**

### 14. Limitations
**Vendor-locked** — NVIDIA switch + SuperNIC required for the full feature set;
proprietary vs UEC standards; PFC/CC tuning depth is still operationally real;
vendor performance figures need independent confirmation; not UEC-UET silicon
(participates in UEC ~Aug 2024 but ships no UET NIC). **[I / F on the UEC join]**

### 15. Best-fit
NVIDIA-GPU AI factories and hyperscale training whose operator already
standardizes on NVIDIA networking; teams that want one tuned loop over open
multi-vendor choice (the trade-off framed in [24-vendor-landscape.md](./24-vendor-landscape.md)).

### 16. Positioning
Spectrum-X sits between InfiniBand (open IBTA standard, NVIDIA-dominated) and UEC merchant
Ethernet (fully open). NVIDIA joined the UEC (~Aug 2024) but **has not shipped UET
silicon** — it competes with UEC Ethernet via Spectrum-X. **[F on the join; I on
the "no UET silicon" inference]** — cross-ref [31-uetch-deep-dive.md](./31-uetch-deep-dive.md).

## The loop, at a glance
```text
GPU -> SuperNIC -> Spectrum-4 switch (sprays per-packet) -> ... -> receiver SuperNIC
        ^   CC in HW (TCC)                                    (reorders, DDP)      |
        +------- RoCEv2+ extensions feedback loop ---------------------------------+
NIC = BlueField-3 REQUIRED for closed loop [F]; ConnectX-7 has spray/RoCE but not full TCC [F]
```

## Comparison to the open/UEC alternative
| | Spectrum-X | UEC-merchant (TH5/Jericho3/TL10) |
|---|---|---|
| Owner of loop | NVIDIA (ASIC+NIC+CC+mgmt) [F] | you / multi-vendor [F] |
| Spray+reorder | per-packet, NIC reorders [F] | DLB (Broadcom) / UET RUD [F/A] |
| CC | TCC (proprietary) [F] | DCQCN now; NSCC/RCCC (UEC) later [F] |
| Openness | proprietary platform [I] | open standards (OCP/UEC/SONiC) [F] |
| Scale evidence | Fairwater/OpenAI [A] | Meta 100k+ (no-DCQCN) [E] |

## Wire-model sanity check [I]
Per-planward: an 800G SuperNIC = 100 GB/s. A 1 MB ring-chunk serializes in ~10 µs
on an 800G plane (1 MB ÷ 100 GB/s) [A: 800 Gb/s = 100 GB/s, E: bank]. Whether
per-packet spray beats static ECMP is a JCT measurement on *your* topology — the
vendor cites utilization gains, but the claim rests on the closed loop being active
(BF-3 + Spectrum-4). **[I]**

## Independent verification status (do not skip)
This entire page is NVIDIA vendor claims unless independently corroborated. The
corroborated items and the still-open ones:
| Claim | Status | Basis |
|---|---|---|
| Spectrum-4 51.2T, SN5600/SN5610 64×800G | [F: vendor spec], port count corroborated | NVIDIA spec + buyer's-guide [F] |
| BF-3 SuperNIC reorders + runs CC | [F: vendor spec] | NVIDIA |
| MRC open spec, co-developed, deployed at OpenAI | [F]/[A] | OCP MRC 1.0, OpenAI paper |
| Fairwater (Microsoft) hundreds-k Blackwell on Spectrum-X | [A/F] | NVIDIA + third-party |
| 1.6–1.9× gen-AI perf | [F: vendor claim], **marketing** | NVIDIA |
| 95% throughput; xAI ~100k exact | **UNVERIFIED** | secondary only |
| "PFC disabled" / exact PFC priority policy | **UNVERIFIED** | mixed evidence |
**Rule [I]:** quote vendor numbers as claims; treat scale/throughput as
announced/`[A]` until an independent measurement or primary datacenter post
confirms them.

## Cross-links
- [24-vendor-landscape.md](./24-vendor-landscape.md) — where Spectrum-X sits in the vendor matrix.
- [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md) — TCC's role vs the DCQCN/TIMELY/HPCC/Swift landscape.
- [23-roce-lossless-fabric-design.md](./23-roce-lossless-fabric-design.md) — the lossless design Spectrum-X pushes PFC away from.
- [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md) — the topology Spectrum-X assumes.
- [31-uetch-deep-dive.md](./31-uetch-deep-dive.md) — the open alternative Spectrum-X competes with.
- [55-cheat-sheet.md](./55-cheat-sheet.md) — quick references.


## Key Takeaways
1. Spectrum-X is the **only complete (closed-loop) Ethernet fabric**: Spectrum-4 switch ASIC +
   BlueField/ConnectX SuperNICs + management, all NVIDIA -- the differentiator vs merchant RoCE. [F]
2. Its load-balancing answer is **per-packet adaptive routing (spraying) + receiver-NIC
   reordering**; the closed loop requires a **BlueField-3 SuperNIC** (ConnectX-7 has RoCE + spray
   but not full TCC CC). [F]
3. **TCC** (hardware CC on the SuperNIC) is the CC, distinct from DCQCN; the exact PFC policy and
   the "PFC disabled" claim are **UNVERIFIED**. [F / UNVERIFIED]
4. **MRC** (multipath reliable connection; OCP MRC 1.0, co-developed with AMD/Broadcom/Intel/MS/
   OpenAI) backs the >100k two-tier scale claims -- those are [A]/third-party, not measured facts.
5. Read every number as a **claim**: 1.6-1.9x gen-AI perf is vendor marketing; Fairwater / OpenAI /
   xAI Colossus scale need independent confirmation. [F: vendor claim]

## Related
- [24-vendor-landscape.md](./24-vendor-landscape.md) -- where Spectrum-X sits in the vendor matrix.
- [23-roce-lossless-fabric-design.md](./23-roce-lossless-fabric-design.md) -- the lossless design Spectrum-X pushes PFC away from.
- [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md) -- TCC vs the DCQCN/TIMELY/HPCC/Swift landscape.
- [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md) -- the rail/multi-plane topology Spectrum-X assumes.
- [31-uetch-deep-dive.md](./31-uetch-deep-dive.md) -- the open (UEC) alternative Spectrum-X competes with.
- [README.md](../Hardware/README.md) -- the NVLink/NVSwitch scale-up side (not Ethernet).

## References
- NVIDIA Spectrum-X platform spec (nvidia.com/en-us/networking/spectrumx). [F: NVIDIA]
- "Sets the Standard for Gigascale AI, Now With MRC" (NVIDIA blog, 2025). [F: NVIDIA]
- OCP MRC 1.0 open specification -- the released MRC standard. [F]
- OpenAI, "Resilient AI Supercomputer Networking using MRC and SRv6" -- the >100k two-tier claim. [F/A]
- [E] constants from the section bank (computed 2026-08-25; e.g. 800G = 100 GB/s). [E]
