# Cisco AI Ethernet (Nexus 9000 / Silicon One)
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: Cisco Silicon One G200/G202/G300 datasheets & investor PR (Feb 2026), Nexus 9000 AI specs (N93240E-SG2/N9364E-SG2), N9300 GX2 AFD/ETRAP datasheet, Cisco-NVIDIA newsroom (Feb 2025); fetched 2026-08-25.

## 30-Second Explanation
Cisco's AI-fabric story is **in-house ASICs (Silicon One) + the Nexus 9000 switch line + Nexus
Dashboard** running standard RoCEv2/PFC/ECN, with the AI differentiators (Approximate Fair
Drop, deep-buffer P200, path-based LB) living in the silicon. Unlike Arista (merchant chips)
and NVIDIA (proprietary end-to-end), Cisco is the "silicon-plus-full-stack" incumbent: it owns
the ASIC, the switch, and the management suite, and integrates at the platform level with
NVIDIA (the Cisco–NVIDIA partnership, announced Feb 2025) rather than competing head-on on a
proprietary transport. Its AI pitch is conservative and standards-based — RoCEv2 lossless
Ethernet, well-instrumented, enterprise-familiar — with a new 102.4T G300 (announced, not yet
shipping) aimed at "agentic-era" AI data centers.

## The Silicon One family (in-house ASIC)
**Silicon One is Cisco's own architecture spanning routing + switching** — one silicon platform
instead of separate router/switch ASICs. [F: Cisco]
| Part | Capacity | Role / notes | Status |
|---|---|---|---|
| **Silicon One G200** | 51.2 Tb/s, ~512 MACs, 10G–800G | standalone switching/AI spine | **shipping** [F: Cisco] |
| **Silicon One G202** | 25.6 Tb/s, ~256 MACs | ToR/leaf AI + front-end (half-G200) | **shipping** [F: Cisco] |
| **Silicon One G300** | **102.4 Tb/s** | "Intelligent Collective Networking" — fully-shared buffer, path-based LB, proactive telemetry | **announced Feb 2026, production UNVERIFIED** [A] |
| **Silicon One P200/P202** | 51.2 Tb/s (P200), deep-buffer | powers **Nexus 9364E-SG2/N9364E-SP2R-X** | shipping [F: Cisco] |

- **G300 claims** are vendor-simulated: +33% network utilization / −28% JCT vs a simulated
  non-optimized fabric — **not an independent measurement**. [A — vendor simulation]
- The Q-series (Q100/Q110/Q200/Q201…) are service-provider/edge members of the same Silicon
  One family; the specific "G2 Ultra" labels in circulation are **UNVERIFIED**; G200/G202
  confirmed. [I]

## Architecture
Unified **Silicon One + Nexus 9000 (N9000)** fixed/modular, with the **Cisco 8000** routers for
routing-converged front/back-end. AI scale-out is RoCEv2 lossless Ethernet: leaf-spine for
front-end + back-end, with deep-buffer parts (P200) for the incast-heavy spine role. [F]
```text
       ┌─────────────────────────────────────────────┐
       │  Silicon One G200 / P200 (back-end spine)   │ ← deep-buffer, AFD, WRED, ECN
       └───────────────┬─────────────────────────────┘
                       │ 400G/800G uplinks
       ┌───────────────┴─────────────────────────────┐
       │  Nexus 9364E-SG2 (leaf, 64×800G)  [F: Cisco]│
       └───────────────┬─────────────────────────────┘
                       │ 800G downlinks (RoCEv2, PFC, ECN, GPU host)
                    GPU / accelerator (Gaudi, others)
```
- **Roughly:** back-end scale-out (GPU↔GPU) = RoCEv2 lossless on Silicon One leaf-spine;
  front-end (K8s/storage) = standard Nexus switching; both managed by **Nexus Dashboard**. [F/I]

## Topology
**Leaf-spine** front-end + back-end scale-out; N9000 fixed/modular; the P200 deep-buffer spine
for large fabrics; **G300** (announced) targets very large "agentic-era" AI DCs. Rail-optimized,
**AI POD**-style architectures are a first-class Cisco pattern — a self-contained pod of
leaf/spines serving a GPU POD with lossless RoCE. [F/A: Cisco]
- AI POD = the unit of deployment: a manageable number of GPU racks + dedicated spine, with
  uplink capacity sized to the POD's training bisection ([42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md)). [I]

## Switch ASIC (the four answer)
Cisco **does** make its own switch ASIC (Silicon One — see table above); it is **not**
NVIDIA-Spectrum-4-based. The "is the Cisco AI backend SN5600?" question is a firm **no at the
ASIC level** — the Cisco–NVIDIA relationship is a platform/partnership, not Cisco reselling
Spectrum-4. [F: Cisco + [I]]

## NIC / DPU / SuperNIC
Cisco is primarily a **switch/ASIC vendor** for this stack; the RoCEv2 NICs are third-party
(NVIDIA ConnectX, Pensando, etc.) or **AMD Pensando** DPUs in partner/Valor-style designs.
Cisco's own DPU story is lighter than NVIDIA's SuperNIC; the endpoints run standard DCQCN.
[F/I] · DPU taxonomy: [37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md).

## Load balancing
G200/G300 carry **advanced LB + fault detection** for AI JCTs; the G300 "path-based LB" is part
of Intelligent Collective Networking. At the **packet/flow level** it is Broadcom-class
flowlet/ECMP + the AFD elephant-mice distinction; there is **no proprietary end-to-end spray
protocol** like NVIDIA's TCC-to-SuperNIC loop. [F/A]

## Congestion control
**RoCEv2 + PFC lossless; DCQCN at the NICs.** No proprietary end-to-end CC protocol has been
published; the switch contributes ECN/WRED/AFD and lets the standard DCQCN control loop run at
the endpoints. G300's "path-based" features are ASIC-class assistance, not a new transport.
[F] · DCQCN: [21-dcqcn.md](./21-dcqcn.md).

## PFC strategy
Standard lossless RoCEv2 PFC on dedicated RDMA priorities; WRED + PFC coexistence is the
Cisco-supported arrangement. Deep-buffer (P200) helps absorb incast so PFC triggers less
often — the "buffer your way out of PFC storms" strategy (cf. Meta's deep-buffer CTSW, the
"no persistent PFC" datapoint in `research-vendors.md` §7). [F/I] · PFC dangers:
[19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md).

## ECN strategy
**ECN/WRED marking (egress)** to drive DCQCN at the NICs. Cisco adds **Approximate Fair Drop
(AFD)** with **ETRAP (Elephant Trap)** on the N9300 GX2 line — specifically aimed at RoCE
fabric fairness: distinguish elephant vs mice and drop/police proportionally so a few
elephants don't starve the many small flows, while *not* dropping the elephants that carry
training traffic. [F: Cisco N9300 GX2 datasheet]

## Telemetry
**Nexus Dashboard** (unified operations across N9000/Cisco 8000), model-driven telemetry,
and **Splunk** (Cisco-owned) for observability/retention. AI-oriented telemetry is
proactive/programmatic rather than an end-to-end protocol like CU-TCC. [F]

## Automation
Nexus Dashboard + **Full-Suite / NSO** programmability, ansible/YANG, intent-based lifecycle
management. Cisco's strength is a familiar, heavily-automated enterprise ops model. [F]

## Conceptual config workflow (RoCEv2 AI backend, in order)
A representative Cisco Nexus RoCE/DCB bring-up for an AI backend — the *concept*, not a
copy-paste CLI: [I: standard Nexus RoCE/DCB sequence, per Cisco DCB/RoCE feature guides]
```text
1. class-map / policy-map  define a "ROCE" class, set its QoS queue & DSCP/CoS.
2. priority-flow-control mode on   enable lossless on the ROCE class only
   (mtu 9216 on the fabric ports for jumbo 9K RDMA frames).
3. policy-map type queuing  set WRED + ECN thresholds on the ROCE queue
   (ecn, wred) — marking is the DCQCN signal source.
4. ETS   ensure the ROCE class gets its guaranteed share (bandwidth percent).
5. interface NVE / fabric   apply the policy; verify with
   show policy-map type queuing / show priority-flow-control counters.
6. Nexus Dashboard   import the fabric; monitor PFC/ECN drops and AFD counter state.
```
The two failure questions the workflow pre-empts: **PFC on the wrong (all) classes** and
**ECN marking not applied** — either silently ruins an AI job ([46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md)).

## GPU integration
Validated reference designs with **Intel Gaudi 3 + Nexus 9000**; RoCEv2/PFC for distributed
training; works with any RDMA-capable accelerator. Specific **NCCL/GDR tuning claims beyond
generic RoCE are modest/not deeply documented**. [F/I]

## NCCL / RCCL integration
Standard **NCCL-over-RoCEv2**; no Cisco-proprietary NCCL plugin published. Tuning is the
generic DCQCN/PFC/ECN work ([04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md)). [F/I]

## Scale
G200 (51.2T) and P200 deep-buffer spine scale to large multi-POD fabrics; G300 (102.4T,
announced) targets 1M-scale ambitions. **No independent or vendor crisp "N accelerators"
number is asserted here** — Cisco's scale pitch is via the AI POD Architecture rather than a
single headline count. [I — not fabricated]

## Strengths
- **In-house 51.2T/102.4T silicon** — no merchant-ASIC dependency for G200/G300. [F]
- **Deep-buffer P200** for incast-heavy AI spine roles. [F]
- **Full stack**: Silicon One + Nexus + Nexus Dashboard (+Splunk) + enterprise familiarity. [F]
- **Conservative, interoperable**: standard RoCEv2 means it slots into existing Ethernet ops
  and multi-vendor NIC pools. [F/I]

## Limitations
- **Historically weaker top-tier AI differentiation** vs NVIDIA (SuperNIC/TCC) and Arista
  (UEC-forward DLB/spray) at the 800G tier. [I]
- **AI CC/spray features are ASIC-class**, not an end-to-end protocol — depends on third-party
  NICs for DCQCN. [I]
- **G300 is announced, not shipping** (Feb 2026 investor event); its JCT/utilization claims are
  simulated. [A]

## Best-fit
Enterprise AI + **front-end/back-end convergence**, Cisco-shop data centers, **Intel Gaudi /
third-party accelerator clusters**, and operators who want a full-stack vendor without adopting
the NVIDIA or Arista bets. [F/I]

## UEC / open positioning
Cisco is a **founding UEC member** and runs standards RoCEv2; its roadmap is UEC-compatible in
principle, though the research notes find **no proprietary Cisco end-to-end UEC play** — Arista
is the more UEC-forward merchant vendor. Cisco's differentiator is deep-buffer + in-house ASIC,
not transport innovation. [F/I]

## Comparison: Cisco vs the field
| Dimension | Cisco (Nexus/Silicon One) | Arista Etherlink | NVIDIA Spectrum-X |
|---|---|---|---|
| Switch ASIC | **in-house** (G200/G202/G300/P200) | merchant (TH5/Jericho3-AI) | in-house Spectrum-4 |
| Endpoint CC | DCQCN at 3rd-party NICs | DCQCN now; UEC NSCC/RCCC later | proprietary TCC (SuperNIC) |
| AI special | AFD/ETRAP, deep-buffer P200 | DLB/spray/trim/MRC (EOS) | per-packet spray + hw CC |
| Top 800G tier | G200 51.2T; **G300 102.4T [A]** | 7060X6 51.2T / 7800R4 | SN5600 51.2T |
| UEC | founding member | founding member | member ~2024 (pushes Spectrum-X) |

## Key Takeaways
1. Cisco's AI Ethernet = **Silicon One (in-house) + Nexus 9000 + Nexus Dashboard**, running
   standard RoCEv2/PFC/ECN/DCQCN.
2. AI differentiation is in the silicon: **AFD/ETRAP fairness** + **deep-buffer P200** (not a
   new transport).
3. **Ship state matters**: G200/G202/P200 shipping; **G300 102.4T announced** (Feb 2026),
   production UNVERIFIED.
4. Cisco does **not** use NVIDIA Spectrum-4; its NVIDIA link is a platform partnership
   (Feb 2025).
5. Best-fit is the enterprise full-stack / Gaudi / converged front-back-end niche, not the
   frontier-proprietary-spray niche.

## Related
- [26-arista-etherlink.md](./26-arista-etherlink.md) — the open-merchant comparable.
- [25-nvidia-spectrum-x.md](./25-nvidia-spectrum-x.md) — the proprietary end-to-end comparable.
- [24-vendor-landscape.md](./24-vendor-landscape.md) — where Cisco sits.
- [49-design-decision-tree.md](./49-design-decision-tree.md) — full-stack vs open vs proprietary decision.
- [21-dcqcn.md](./21-dcqcn.md) — the CC model Cisco assumes at the NIC.

## References
- Silicon One G200/G202 datasheets; G300 announced (Cisco investor event, Feb 2026) [F: Cisco].
- Nexus 9364E-SG2/N9364E-SP2R-X, N9300 GX2 AFD/ETRAP datasheets [F: Cisco datasheet].
- Cisco–NVIDIA expanded partnership newsroom (Feb 2025) [A: Cisco newsroom].
- [E] constants from the section bank (computed 2026-08-25).
