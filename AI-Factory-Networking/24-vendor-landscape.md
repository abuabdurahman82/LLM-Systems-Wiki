# AI-Fabric Vendor Landscape: Who Makes What
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: Broadcom IR (Tomahawk 4/5/Ultra, Jericho, Thor), NVIDIA Spectrum-X
spec, Arista/Cisco/Juniper/HPE/AMD/Marvell/Huawei product pages, SONiC docs;
fetched 2026-08-25.

## 30-Second Explanation
AI fabric is not one product — it is five separable roles stacked on top of each
other: **switch vendor** (sells a switch system), **ASIC vendor** (sells the
switching chip inside it), **NIC vendor** (sells the endpoint card), **DPU
vendor** (sells a smart-NIC/DPU), and **complete-fabric provider** (sells the whole
stack including the NIC and the CC/spray protocol). The crucial fact of the market
is that **most switch vendors buy the ASIC from a merchant (usually Broadcom)** and
differentiate with software, radix-specific board layout, power, optics and
service — which is why HPE's and Dell's 800G switches often contain the *same*
Broadcom Tomahawk-5 silicon as each other. NVIDIA is the outlier that owns switch
ASIC, switch and NIC in one closed loop (Spectrum-X). Everything else is a matrix
of who buys whose chip. Production vs announced must stay distinct: **51.2T
merchant silicon (Broadcom Tomahawk-5 TH5, Marvell Teralynx-10 TL10) is the shipping
tier**; **102.4T (TH6 / Marvell G200) is announced/roadmap** (NVIDIA in-house
Spectrum ASICs are a separate, closed-loop track).

## The five roles (a 5-interpretation model)
```text
                  sells switch   sells chip   sells NIC   sells DPU   owns whole fabric
switch vendor       [yes]           no         (optional)   (optional)       no
ASIC vendor        (as ref)        [yes]      (sometimes)      no            no
NIC vendor            no            n/a        [yes]       (optional)        no
DPU vendor            no            n/a        [yes]        [yes]            no
fabric provider      [yes]*      [own ASIC]*   [yes]        [yes]            [yes]
* NVIDIA only (Spectrum-4 in-house + SuperNIC + full closed loop); Arista/EOS is
  fabric-class software, not a NIC.  [I]
```

### What / Why / How per role
- **Switch vendor:** assembles the ASIC + optics + NOS into a sellable box (HPE,
  Dell, Cisco, Juniper, Arista, Huawei). **Why:** most do not want to design their
  own chips. **How:** buy merchant silicon, write/curate the NOS.
- **ASIC vendor:** designs the switching silicon. **Broadcom** is the merchant
  default; **Marvell** (Teralynx) is the second merchant option; **NVIDIA/Cisco**
  are in-house-ASIC switch players. **[F]**
- **NIC vendor:** endpoint RDMA card (NVIDIA ConnectX/BlueField, AMD Pensando,
  Broadcom Thor NICs). **[F]**
- **DPU vendor:** programmable smart-NIC (NVIDIA BlueField, AMD Pensando, Intel
  IPU/E2000, Marvell OCTEON). **[F]**
- **Complete-fabric provider:** ties switch + NIC + protocol + management into one
  tuned system — only **NVIDIA Spectrum-X** does this end-to-end today [F: vendor].
  Arista approaches fabric-class software on merchant silicon but is not a NIC
  vendor [I].

### Converged vs discrete fabric (the buyer's fork) `[I]`
```text
CONVERGED (one vendor owns the whole loop):  NVIDIA Spectrum-X
   pro: tuned CC+spray+NIC, single throat to choke for support
   con: vendor lock-in; price; proprietary vs open UEC
DISCRETE (pick ASIC + switch + NIC + NOS separately): Broadcom/TH5 + Dell/HPE/Edgecore + any NIC
   pro: choice, open standards (OCP/UEC/SONiC), competitive price
   con: *you* integrate CC/spray/reorder consistency across vendors
```

## Broadcom: the merchant-silicon backbone
### Silicon line-up `[F: vendor — Broadcom IR]`
```text
Tomahawk 4 (TH4)  25.6 Tbps, 400G-era   -> basis of much of Meta's 100k+ fabric   [F/E]
Tomahawk 5 (TH5)  51.2 Tbps, 512x100G SerDes -> 64x800G / 128x400G / 256x200G; shipping [F]
Tomahawk 6 (TH6)  102.4 Tbps, announced; Cognitive Routing 2.0; "world's first"    [A]
Tomahawk Ultra    UEC-compliant; runs AllReduce in the switch (in-network collectives) [F: vendor]
Jericho3/3-AI     deep-buffer 800G; powers Arista 7800R4 spine & hyperscale AI spines [F]
Thor              Broadcom's NIC line (Thor / Stingray are separate NIC vs DPU SKUs; ~400G-class) [F: vendor]
```
### Why so many OEMs ship "different" systems on common silicon `[I]`
The ASIC fixes the port-count/bandwidth envelope; the *product* is software
(NOS/QoS/telemetry), board layout, power/thermal, optics choice, and service. So
HPE, Dell, Juniper, Edgecore, H3C, Celestica, Lenovo, Supermicro all sell systems
around TH5 — Broadcom IR names H3C, Delta, Ruijie as TH5 adopters **[F: Broadcom
IR]**; **WiLCOM as an AI-flag TH5 builder is UNVERIFIED**. The differentiator
migrates up the stack: whoever writes the best RoCE/UEC feature set for that
silicon wins the sockets. **Buyer's rule [I]:** compare the *software + validated
reference design* on top of the silicon, not the silicon itself — the ASIC is
often identical.

## The vendor matrix
| Vendor | Switch system | Switch ASIC | NIC/DPU | Fabric software | Role(s) | Notes/status |
|---|---|---|---|---|---|---|
| NVIDIA | SN5600/SN5610 (800G) | **Spectrum-4** (in-house) | SuperNIC (BF-3, CX-7/8) | DOCA+NetQ, TCC, MRC | complete-fabric | closed loop; [25-nvidia-spectrum-x.md](./25-nvidia-spectrum-x.md) [F] |
| Broadcom | ref platforms | TH4/TH5/TH6, Ultra, Jericho | Thor NICs | (merchant) | ASIC + NIC vendor | silicon merchant default [F] |
| Arista | 7060X6, 7800R4 | merchant (TH5/Jericho3-AI) | — | EOS, CloudVision, DLB | switch vendor | UEC-aligned [F] |
| Cisco | Nexus 9000/8000 | **Silicon One G200/G202/G300** | — | Nexus Dashboard | switch+ASIC vendor | G300 102.4T announced [A] |
| Juniper | QFX5240 (800G) | merchant (TH5) | — | Junos, Apstra, Mist | switch vendor | HPE-owned; DLB on QFX [F] |
| HPE | Slingshot 400, Aruba TH5 | merchant | Slingshot NICs (LLR/UEC-facing) | Slingshot | switch+NIC (HPC) | X40000 naming UNVERIFIED [I] |
| Dell | 800G leaf/spine | merchant (TH5/TL10) | — | SONiC/OS10 | switch vendor | merchant-based [F] |
| AMD | (MI300 scale-out) | — | Pensando Salina/DPU, Pollara/Vulcano/NIC | Pensando SW | DPU/NIC vendor | UEC co-lead [F] |
| Intel | — | — | IPU E2000/E2100; Gaudi-3 200G on-chip | — | NIC/DPU vendor | UET NIC UNVERIFIED [I] |
| Marvell | (switch ref) | Teralynx 10 (51.2T) | OCTEON 10 DPU | — | ASIC + DPU vendor | 2nd merchant option [F] |
| Huawei | CloudEngine 16800 | in-house | (no public in-house NIC/DPU; iLossless/NPCC software) | iMaster NCE-AI | switch+ASIC vendor | iLossless/NPCC [F] |
| SONiC ecosystem | (multi-OEM on merchant) | merchant | — | **SONiC NOS** (open) | NOS layer | open-NOS base for AI [F] |

## Ecosystem notes (where [I] is the honest tag)
- **SONiC** is a **NOS, not a fabric vendor** [F] — it pairs with merchant ASICs
  (TH4/5, some NVIDIA Spectrum) and is the base hyperscalers extend for RoCE/UEC.
  Microsoft co-founded UEC and Azure uses Spectrum-X at Fairwater plus custom
  RoCE-like Ethernet; **Maia is Microsoft's AI accelerator, not an Ethernet
  protocol** — drop it from the fabric claim **[F]**; whether core Azure training
  backends are specifically "SONiC + Spectrum-4" is **UNVERIFIED** [I].
- **Meta's anomaly [E]:** production AI training **without transport CC (no
  DCQCN)** on commodity Ethernet, driven by collective co-tuning + PFC — the
  strongest argument that merchant RoCE + careful tuning works at 100k+ scale.
- **AMD Pensando** UEC-first NICs: Pollara 400 (sampled Q4'24, GA H1'25) **[F]**;
  **"Pollux" as a shipping name is UNVERIFIED** (shipping/announced = Salina DPU,
  Pollara NIC, Vulcano 800G). **[I/UNVERIFIED]**
- **Intel Gaudi:** Ethernet for both scale-up and scale-out (Gaudi-3 24×200G
  RoCEv2 on-chip), 2-tier to 8,192 accelerators; **no distinct "IDI/PSI" fabric
  protocol confirmed — UNVERIFIED**. **[F/I]**
- **Huawei** (CloudEngine 16800, iLossless, NPCC proactive CC) is mostly of
  interest in APAC/Ascend contexts; export-control caution applies; independent
  verification is thinner than for Western vendors. **[F/I]**

## Vendor spotlights (one paragraph each)
- **HPE:** the HPC interconnect is **Slingshot** (originally Cray) — **Slingshot 400**
  switch family brings Optimized Ethernet + HPC formats, **LLR**, credit-based flow
  control on fabric links, and fine-grain FC / 802.1Qbb PFC at the edge, i.e. HPE
  ships a 400G-class AI Ethernet switch + NICs explicitly incorporating
  **Ultra-Ethernet-style** features [F: HPE Slingshot 400 QuickSpecs]. HPE also
  sells TH5-based Aruba switches, and the Juniper acquisition adds QFX5240 +
  Apstra + Mist. **The "HPE X40000 / AI40000 / 1.6T" tier is UNVERIFIED** —
  Slingshot 400 and TH5 switches are corroborated, but the next-gen 1.6T name/specs
  were not confirmed. **[I/UNVERIFIED]**
- **Dell:** a merchant-silicon switch vendor shipping TH5/TL10-family 800G leaf/spine
  (PowerSwitch) on SONiC/OS10; no in-house switch ASIC and no own NIC — a clean
  "assemble-on-Broadcom/Marvell" play **[F]**.
- **Arista:** standards-based EOS fabric, **merchant** silicon (7060X6 on TH5,
  7800R4 on dual Jericho3-AI), with an "AI feature kit" (DLB, PFC-aware DLB & ECN,
  packet spraying, packet trimming, MRC, CSIG) and forward-compatible UEC posture;
  a founding UEC member. Does **not** make its own NIC. **[F]**
- **Cisco:** in-house **Silicon One** G200 (51.2T, shipping), G202 (25.6T), and
  **G300 (102.4T, announced Feb 2026)** — the only other big switch vendor with its
  own 51.2T/roadmap-102.4T ASIC besides NVIDIA; Nexus 9000 family on Nexus
  Dashboard; AFD/ETRAP for elephant/mice fairness. Cisco-NVIDIA partnership is
  platform-level, not "SN5600-based" **[F/I]**. G300 production **UNVERIFIED** **[A]**.
- **AMD/Pensando:** the UEC-leading NIC/DPU vendor — Salina 400 DPU, Pollara 400
  UEC-compliant NIC (sampled Q4'24, GA H1'25), Vulcano 800 AI NIC **[F]**; a leading
  MRC co-developer with NVIDIA/Broadcom/Intel/Microsoft/OpenAI. No own switch ASIC.
- **Marvell:** the second merchant switch option — **Teralynx 10** (51.2T,
  programmable, in volume production for AI clouds) **[F: Marvell]** + **OCTEON 10**
  DPU. "Teralynx 8 1.6T" as a distinct new part **UNVERIFIED** (flagship is
  Teralynx 10). Celestica partners on Teralynx 10 **[F]**.

## Two philosophical camps
```text
Camp A: proprietary closed loop (NVIDIA)          Camp B: open / UEC-aligned merchants
switch ASIC + NIC + CC + spray + management          (Broadcom, Marvell, Jericho3-AI) +
owned by one vendor  [F: vendor]                     NIC-level UEC features, run by EOS/Junos/SONiC [F]
trade-off: integration & guaranteed tuning            trade-off: vendor choice, open standards, but
  vs vendor lock-in [I]                               CC/spray consistency is YOUR job [I]
```
**No universal winner:** the decision is a hypothesis — *"does my operator value
one-tuned-loop (NVIDIA) or open multi-vendor (UEC/merchant) more?"* The experiment
that would decide it is a head-to-head JCT/busbw measurement on the same-size
cluster; nobody has published a controlled one. **[I]**

## Failure modes / how to measure
- **Fabric-feature mismatch:** claiming a feature (DLB, ECN, base-range spray) that
  the *installed silicon* does not actually have → drops/underutilization; verify a
  capability against the ASIC datasheet and the NOS release, not against vendor
  marketing. **[I]**
- **Roadmap-as-production:** never buy on the 102.4T/TH6/G300 roadmap for a system
  you need today; the 51.2T merchant tier (Broadcom TH5, Marvell TL10) is what ships. **[F]**
- **Silicon-parity trap:** two vendors on the same ASIC are *not* interchangeable —
  one may ship ECN/DLB tuned, the other not. Test with a RoCE traffic pattern, not
  a ping. **[I]**
- **Measure:** run `nccl-tests all-reduce` busbw and compare to
  `0.95 × link` (the ring-busbw saturation); if far below, suspect entropy/hashing (see
  [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md)) rather than the ASIC. **[E: constants bank —
  AllReduce busbw = algbw·2(n-1)/n]**

## Comparison table (roles × who matters)
| Need | Buy from | Examples | Watch out for |
|---|---|---|---|
| Cheapest open fabric | merchant ASIC + ODM + SONiC | H3C/Edgecore/Dell on TH5 + SONiC [F] | you own CC/integration [I] |
| Enterprise support/tooling | full switch vendor | Cisco Nexus, Arista EOS, Juniper Apstra [F] | extra NOS features you must tune [I] |
| Best latency/cut-through | in-house-ASIC switch | NVIDIA Spectrum-4, Cisco Silicon One [F] | ASIC roadmap vs shipping [A] |
| Host RDMA offload | NIC vendor | NVIDIA ConnectX, AMD Pensando [F] | pick the NIC your NOS pairs with [I] |
| Closed tuned loop | complete-fabric provider | NVIDIA Spectrum-X [F] | vendor lock-in [I] |

## Cross-links
- [25-nvidia-spectrum-x.md](./25-nvidia-spectrum-x.md) — the closed-loop fabric provider in depth.
- [23-roce-lossless-fabric-design.md](./23-roce-lossless-fabric-design.md) — the reference lossless architecture on merchant silicon.
- [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md) — CC & load-balancing landscape the vendors implement.
- [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) — switch-count/math that drives which radix you need.
- [55-cheat-sheet.md](./55-cheat-sheet.md) — quick lookup of the whole section.
- [README.md](../Networking/README.md) — Ethernet fabric fundamentals (root-relative).


## Key Takeaways
1. AI fabric = **five separable roles** -- switch / ASIC / NIC / DPU / complete-fabric; most
   switch vendors buy the ASIC (usually Broadcom) and differentiate in software. [I]
2. **Broadcom is the merchant default** (TH4/TH5 shipping; Jericho, Ultra, Thor); the shipping
   tier is **51.2T** (TH5/TL10/P200/Spectrum-4/G200), while **102.4T** (TH6/G300) is roadmap. [F]
3. **Only NVIDIA owns the closed loop** -- Spectrum-4 ASIC + SuperNICs + TCC -- the sole
   complete-fabric provider; everything else is a matrix of who buys whose chip. [F]
4. The buyer's fork is **converged (NVIDIA)** vs **discrete (Broadcom + Dell/HPE/Edgecore +
   SONiC + any NIC)**: tuned single-vendor loop vs open multi-vendor choice. [I]
5. Buy shipping silicon, not roadmap; and since two vendors often share an ASIC, **compare the
   NOS/CC software + validated reference design on top**, not the silicon. [I]

## Related
- [25-nvidia-spectrum-x.md](./25-nvidia-spectrum-x.md) -- the closed-loop fabric provider, in depth.
- [23-roce-lossless-fabric-design.md](./23-roce-lossless-fabric-design.md) -- the reference lossless design on merchant silicon.
- [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md) -- the CC/load-balancing landscape vendors implement.
- [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) -- switch-count math behind which radix you need.
- [README.md](../Networking/README.md) -- Ethernet fabric fundamentals (root-relative).
- [55-cheat-sheet.md](./55-cheat-sheet.md) -- quick lookup of the whole section.

## References
- Broadcom IR -- Tomahawk 4/5/6, Ultra, Jericho, Thor line-up and TH5 adopters. [F: Broadcom IR]
- NVIDIA Spectrum-X spec -- the closed-loop/complete-fabric case. [F: NVIDIA]
- Arista / Cisco / Juniper / HPE / AMD / Marvell / Huawei product pages and datasheets. [F]
- SONiC docs -- the open NOS base hyperscalers extend for RoCE/UEC. [F]
- Meta SIGCOMM'24 -- the no-DCQCN merchant-RoCE counterexample (the [E] anomaly). [F/E]
- [E] constants from the section bank (e.g. AllReduce busbw = algbw . 2(n-1)/n). [E]
