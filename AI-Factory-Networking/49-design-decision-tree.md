# The Fabric Design Decision Tree
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: UEC 1.0 spec + author paper (arXiv:2508.08906), IBTA/NVIDIA IB docs, RoCEv2 IETF draft; fetched 2026-08-25. As-of date for market maturity claims: **2026-08-25**.

## 30-Second Explanation
There is no "best" AI fabric — only a fabric matched to your constraints: *performance ceiling*,
*ops model you already run*, *scale*, and *how soon you must ship*. The three real answers are
**InfiniBand** (max mature HPC performance, NVIDIA ecosystem, lossless by construction),
**RoCEv2 / AI Ethernet** (Ethernet ops model, most flexible, losslessness as engineered policy),
and **Ultra Ethernet Transport (UET)** (open next-gen transport, built for lossy fabrics and
packet spraying, but early silicon as of mid-2026). This page walks a decision tree, then gives the
full comparison table. **As-of date: 2026-08-25** — treat "shipping/announced/early silicon"
claims against that.

## The decision tree (vertical)
```text
START: "I need to move GPU-to-GPU traffic at scale."
│
├─ Need max MATURE HPC/AI perf, single-vendor is fine
│     → InfiniBand (NDR400/XDR800, SHARP, adaptive routing)   [F: NVIDIA Quantum line]
│
├─ Need the Ethernet ops model (familiar switches, multi-vendor, reuse of DC tooling)
│     → RoCEv2 / AI Ethernet (Spectrum-X-style; PFC+ECN+QoS as engineered policy)   [F]
│
├─ Open to a next-gen transport and this is a NEW design
│     → evaluate UET ecosystem maturity                           [I]
│       (as of 2026-08-25: spec 1.0.3 exists; switches + AMD Pollara NIC early silicon;
│        broader production adoption expected through 2026–2027)  [F: UEC history / [I]]
│
│  ── then size the design ──
├─ Small cluster (tens of GPUs)   → simple Clos / direct connect   [A]
├─ Hundreds of GPUs                → rail-optimized leaf-spine      [A]
├─ 10k+ GPUs                       → multi-plane / rail-per-plane   [A]
├─ Storage-heavy (checkpoints/datasets)
│     → ADD a separate storage fabric (isolate from compute)       [F: separation of fabrics]
├─ Multi-tenant public/private cloud
│     → RoCE + VXLAN overlays, OR UET TSS for stronger tenant security  [A] / [F: UET TSS]
└─ Inference / disaggregated (P/D split, KV shipping)
      → RoCE + a KV tier (latency/footprint), often over its own fabric  [I]
```

### Reading each branch
- **Max mature HPC perf → IB.** IB is purpose-built, single-vendor-optimized, and its SHARP
  in-network reduction lowers collective cost; as of 2026-08 it is the *proven* answer at the top
  of the performance curve (NDR400/XDR800 shipping) [F]. The cost is vendor lock-in and an HPC
  control plane (Subnet Manager) most DC teams don't already run.
- **Ethernet ops model → RoCEv2/AI Ethernet.** If your staff, tooling, and multi-vendor comfort are
  Ethernet, RoCEv2 is the fastest path — but you take on PFC/ECN/QoS tuning as a first-class
  operational burden, and Spectrum-X-style adaptive routing to fix entropy [F/I].
- **Open next-gen transport → evaluate UET.** If it is a *new* design with time, UET is the option
  to watch: connectionless PDCs, per-packet spray, lossy-capable, and TSS security in-spec [F] —
  but as of 2026-08-25 the silicon is early (AMD Pollara NIC; Broadcom switches; broad ramp expected
  through 2026–27 [I]). Only take it if an explicit maturity gate passes.
- **Scale tiers.** Tens of GPUs → simple Clos or even direct connect; hundreds → a rail-optimized
  leaf-spine so each GPU's NIC rail has a dedicated leaf plane; 10k+ → multi-plane (scale by planes,
  not one monster fabric) [A, per Clos/rail math in `./42`/`./38`].
- **Storage-heavy.** Checkpoint/dataset bursts are an incast problem; isolating them on a **separate
  storage fabric** prevents them perturbing collectives [F: separation-of-fabrics practice].
- **Multi-tenant cloud.** RoCE + VXLAN gives overlay segmentation; UET's TSS gives in-fabric
  encryption/security if you need tenant *confidentiality*, not just isolation [A / F: UET TSS].
- **Inference / disaggregated.** P/D split ships KV between prefill and decode; a RoCE net plus a
  dedicated KV tier (or its own QoS) keeps decode latency within budget [I].

## The full comparison: InfiniBand vs RoCEv2 vs UET
As-of date: **2026-08-25**. `[F]` = sourced fact; `[I]` = inference/analysis; `[E]` = computed
(values from the constants bank).

| Dimension | InfiniBand (NDR/XDR) | RoCEv2 | UET (UEC 1.x) |
|---|---|---|---|
| **Base network** | IBTA switched fabric, credit flow control | Ethernet + IB transport in UDP/IP (UDP 4791) | Ethernet + UDP/IP (UDP 4793) optional native IP [F: UEC author paper] |
| **RDMA** | Native, verbs | Native (IB transport over UDP) | Native via libfabric v2.0 (OFI) [F: UEC] |
| **Routing** | LID (LRH) + SM; optional GRH/GID inter-subnet; adaptive routing | IP routing + ECMP hash (5-tuple) | Per-packet spraying (EV in UDP port), no reorder buffer [F: UEC] |
| **Lossless requirement** | Lossless by construction (credits) [F] | Yes — PFC lossless, or lossy workaround | No — designed lossy/best-effort [F: UEC] |
| **PFC dependency** | None (credit-based) | High — PFC is core to losslessness [F: IETF/IBTA] | Optional (PFC kept as option; CBFC alternative) [F: UEC] |
| **Congestion control** | IB CC/BECN; less central | DCQCN (ECN + CNP + PFC) [F: SIGCOMM'15] | NSCC (sender, ECN+RTT+trimming) + optional RCCC [F: UEC] |
| **Multipathing** | SL + adaptive routing | ECMP flow hashing; DLB/MRC for spray [F] | Per-packet spraying across all equal-cost paths [F: UEC] |
| **Ordering** | In-order (RC)/DC OOO w/ HW reorder | Strict in-order (RC), Go-Back-N | RUD/RUDI out-of-order + zero-copy; ROD optional [F: UEC] |
| **Connection model** | Connected QPs (RC/DC), setup handshake | Connected QPs, setup handshake | Connectionless, ephemeral PDCs, 0-RTT [F: UEC] |
| **Header overhead** | **24 B** sub-net (LRH+BTH+ICRC), 0.59% @4096B [E] | **58 B** (Eth+IPv4+UDP+BTH+ICRC), 1.42% @4096B, 0.65% @8942B [E] | PDS 12B(16B RCCC) + SES 44/32/20B; can exceed IB/RoCE at small msgs [E/F] |
| **Ecosystem** | NVIDIA-dominated, HPC-proven, SHARP [F] | Broad Ethernet vendor base, flexible [F] | Open, multi-vendor; early silicon (2026) [I] |
| **Management** | Subnet Manager (OpenSM/UFM), single control plane [F] | Standard NMS/DC tooling | New UEC stack; libfabric [I] |
| **Vendor flexibility** | Low (single-vendor dominant) [I] | High (many vendors) [F] | Highest (multi-vendor by design) [F] |
| **Ops familiarity** | HPC-specific (SM, LIDs) | Deep (Ethernet ops + QoS config) [I] | Newest — least operational track record (2026) [I] |
| **Maturity (2026-08-25)** | Production at scale (NDR/XDR shipping) [F] | Production at scale (Meta/cloud) [F] | Spec 1.0.3; switches+AMD NIC early silicon; production ramp 2026–27 [I] |
| **In-network compute** | SHARP (NVIDIA, proprietary) [F] | none standardized | INC (`fi_collective`) standardized/optional [F: UEC] |
| **Security** | P_Key/M_Key/Q_Key; no in-fabric auth [F: NVIDIA] | Relies on L2 (MACsec/ACL) | TSS: AES-GCM-256, secure domains, replay protection [F: UEC] |

### Reading the table honestly
- **Performance ceiling** favors IB today [I] — it is purpose-built, single-vendor-optimized, and
  SHARP lowers collective cost; but "mature max perf" is a snapshot, and UET's lossy-capable
  transport + per-packet spray targets the same ceiling from the open-Ethernet side [F: UEC].
- **RoCEv2's 58 B overhead** is real but small at jumbo sizes (0.65% @ 8942B payload [E]); the pain
  point is not header bytes but the PFC/ECN/QoS alignment that losslessness requires [I].
- **UET maturity** is the honest caveat: as of 2026-08-25 the standards are written, switches and
  at least one NIC (AMD Pollara) are shipping, but broad production clusters are still ramping
  [F: UEC history / [I]]. Do not present UET as drop-in production — it is a design-time option
  with an explicit maturity gate (see tree).
- **Header overhead math** — at 4096 B payload the IB 24 B sub-net frames cost 0.59%; RoCEv2's 58 B
  costs 1.42%; both are dominated by the far larger transport/SES headers in UET at small message
  sizes [E]. Pick the number that matches your dominant message size, not the minimum. At 8942 B
  jumbo payload RoCEv2 drops to 0.65% [E] — the case that shows header size rarely decides the
  choice; losslessness, entropy, and ecosystem do.

### The hypothesis framing (no universal winner)
These rankings are **hypotheses with a deciding experiment**, not verdicts [per section rules]:
- "IB > RoCE for this workload" is decided by running the same nccl-tests sweep on both physics-
  identical fabrics and comparing busbw + P99 at your message sizes [I].
- "UET can replace RoCE at scale" is decided by a production UET fabric beating a tuned RoCE/DCQCN
  fabric on *your* collective mix once the silicon matures — not by the spec alone [F/I].
Frame any procurement around those experiments, not a feature bullet.

## Related
- [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) — sizing the fabric the tree picks (leaf/spine/rail math).
- [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md) — rail-optimized and multi-plane designs for 100s–10k+ GPUs.
- [31-uetch-deep-dive.md](./31-uetch-deep-dive.md) — the UET column in depth (transport, NSCC/RCCC, TSS, profiles).
- [21-dcqcn.md](./21-dcqcn.md) — the RoCEv2 column's CC mechanism.
- [03-rdma-fundamentals.md](./03-rdma-fundamentals.md) — the verbs/dataplane layer all three share.
- [52-reference-architectures.md](./52-reference-architectures.md) — worked end-to-end designs per decision.


## Key Takeaways
1. There is no best fabric — only a match to constraints (performance ceiling, existing ops model,
   scale, time-to-ship); the three real answers are InfiniBand, RoCEv2/AI Ethernet, and UET, and
   every maturity claim is measured against the 2026-08-25 as-of date.
2. InfiniBand wins "max mature HPC perf" (purpose-built, NVIDIA-optimized, SHARP in-network
   reduction, lossless by credits) at the cost of vendor lock-in and an HPC Subnet-Manager control
   plane few DC teams already run.
3. RoCEv2/AI Ethernet wins "Ethernet ops model" — familiar switches and multi-vendor tooling — but
   takes on PFC/ECN/QoS tuning as a first-class burden, and **low hash entropy** as its main
   scaling problem: with a fixed dst port (4791) and few distinct QP/src-port pairs, ECMP's
   5-tuple hash maps many flows onto the same path (the NIC's source-port XOR is the usual fix).
4. UET is the design-time option for *new* builds: connectionless PDCs, per-packet spray,
   lossy-capable, TSS security in-spec — but silicon is early (AMD Pollara NIC, Broadcom switches)
   as of mid-2026, so take it only past an explicit maturity gate.
5. Size after the pick: tens of GPUs → simple Clos; hundreds → rail-optimized leaf-spine; 10k+ →
   multi-plane; add a separate storage fabric for checkpoint/dataset incast; and frame rankings as
   hypotheses with a deciding experiment (same nccl-tests sweep on both fabrics), not verdicts.

## References
- UEC 1.0 spec and author paper (arXiv:2508.08906) — transport, NSCC/RCCC, TSS, connectionless PDCs.
- IBTA / NVIDIA InfiniBand documentation — SHARP, adaptive routing, Subnet-Manager model.
- IETF RoCEv2 fast-CNP draft — PFC/ECN/DCQCN mechanisms, UDP 4791.
- Meta "RoCE networks for distributed AI training at scale" — production RoCE at scale.
- [E] Header-overhead constants: IB 24 B sub-net (0.59% @4096B); RoCEv2 58 B (1.42% @4096B,
  0.65% @8942B); UET PDS 12B + SES 44/32/20B (can exceed IB/RoCE at small messages).
