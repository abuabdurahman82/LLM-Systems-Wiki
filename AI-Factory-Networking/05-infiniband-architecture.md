# InfiniBand Architecture
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: InfiniBand Trade Association (IBTA) Vol 1 (PHY→transport), NVIDIA/Mellanox InfiniBand docs, OFA/OpenSM docs; [E] figures from section constants bank (2026-08-25).

## 30-Second Explanation
InfiniBand (IB) is a **purpose-built switched fabric for RDMA**, not a "faster
Ethernet." It is engineered from the PHY up around three things Ethernet hand-waves:
**losslessness by credit flow control** (a sender only transmits what the receiver has
buffer credit for, so packets are never dropped by congestion), a **control plane — the
Subnet Manager (SM)** — that discovers the fabric, assigns 16-bit LIDs, and programs
switch forwarding (there is no BGP/ARP/IP by default), and **LID-based L2 forwarding**
with an optional GID/GRH network layer only for cross-subnet routing. The stack is a
clean layering: application → UCX/MPI/NCCL → verbs → HCA → transport → network → link →
PHY. Node types are HCAs (host endpoints), switches, routers, the SM, and the SA; a TCA
is the legacy storage/peripheral endpoint term. Every layer exists to make one-sided
RDMA operations (page [04-rdma-operations-and-transports.md](./04-rdma-operations-and-transports.md)) fast, ordered, and lossless.

## What
The IB stack (IBTA Vol 1) breaks cleanly into layers [F: IBTA spec]:

```text
┌────────────────────────────────────────────────────────────────────┐
│ Upper-Layer Protocols (ULPs)   IPoIB, SDP/RDS, SRP, iSER, NVMe-oF, │
│                                uCM, MAD (SMP/GMP), UD multicast    │
├────────────────────────────────────────────────────────────────────┤
│ VERBS  (ibv_* API)   ── the RDMA programming interface             │
├────────────────────────────────────────────────────────────────────┤
│ TRANSPORT  ── QP-based services RC · UC · UD · DC · XRC            │
│              + RDMA ops (SEND/WRITE/READ/ATOMIC), retransmit,      │
│              ordering, PSN, RNR (page ./04, ./08)                  │
├────────────────────────────────────────────────────────────────────┤
│ NETWORK  ── GRH + GID (128-bit), routing across subnets (routers)  │
│              LRH (LID) consumed/rewritten per hop                   │
├────────────────────────────────────────────────────────────────────┤
│ LINK  ── framing, LRH(8B), LID forwarding, per-VC credit flow       │
│          control (lossless), Virtual Lanes (VL0–15), SL2VL, VCRC   │
│          (page ./10, ./09)                                         │
├────────────────────────────────────────────────────────────────────┤
│ PHYSICAL  ── lane signaling per generation (8b/10b / 64b/66b /     │
│              PAM4), DAC/AOC/fiber, connectors (page ./06)          │
└────────────────────────────────────────────────────────────────────┘
```

The **key architectural claim**: unlike TCP/IP-over-Ethernet (where IP routing and
end-to-end loss recovery live in the endpoint OS), IB moves **flow control (credits),
forwarding (LID tables), reliability (RC retransmit), and congestion handling into the
fabric and the HCA silicon**. [F: IBTA model; [I] emphasis]

## Why
Why does a purpose-built fabric beat Ethernet for AI? Three structural reasons [I:
architectural analysis; F: credit-losslessness docs]:
1. **Losslessness by construction.** IB does not *react* to congestion with drops or
   pause frames the way Ethernet/PFC does; it *prevents* overflow with **per-link,
   per-VL credit flow control**. A congested egress simply stops advertising credit and
   backpressure propagates hop-by-hop to the source HCA. Packets are dropped only by an
   SM-configured Head-of-Queue (HOQ) timeout (a deadlock guard). [F: credit-loop docs]
2. **RDMA as the native service.** The verbs model and one-sided ops are in the spec, so
   NCCL/MPI/UCX can drive memory-to-memory transfers with kernel bypass and zero-copy
   (page [03-rdma-fundamentals.md](./03-rdma-fundamentals.md)).
3. **Deterministic control plane.** The SM owns the fabric map (LIDs, forwarding, QoS,
   partitions); there is no IP auto-configuration or ARP to fail. This determinism is
   what makes µs-scale P2P latency and line-rate bandwidth achievable and predictable.

Ethernet is lossy by default and only becomes "lossless" for RoCE by adding PFC +
ECN/DCQCN — a patchwork IB gets natively. → [17-why-roce-is-harder.md](./17-why-roce-is-harder.md),
[16-roce-fundamentals.md](./16-roce-fundamentals.md).

### Why IB is not "faster Ethernet"
It is tempting to read the speed table (page [06-infiniband-speed-generations.md](./06-infiniband-speed-generations.md)) and
treat IB as Ethernet with bigger numbers. It is a **different architecture**; the four
structural differences an engineer must internalize [F: IBTA + NVIDIA docs; [I] framing]:
1. **Credit losslessness, not drop-and-retry.** Ethernet switches drop on buffer
   overflow and let TCP/RoCE recover. IB switches *stop sending* when the downstream
   buffer is full (per-VL credit flow control) and backpressure propagates to the
   source. There is no congestion drop in steady state — only the SM's HOQ-timeout
   deadlock guard ever drops a packet. [F: credit-loop docs]
2. **An SM control plane, not routing protocols.** There is no BGP/OSPF/ARP/DHCP on an
   IB data plane. The **Subnet Manager** centrally discovers the fabric and programs
   **LID-forwarding tables**. Control is centralized and deterministic rather than
   distributed and converged.
3. **LID addressing, no IP by default.** Data moves by 16-bit **LID**s (L2), not IP.
   IP appears only as **IPoIB** (a ULP, for management), and the network-layer **GRH/GID**
   exists only when a router joins subnets. An IB fabric is one flat L2 domain the SM
   owns; "routing" in the IP sense is a separate, optional layer. [F: `packet.transport.ib`]
4. **RDMA/verbs in the spec.** The HCA is a first-class RDMA engine by construction; the
   verbs model, one-sided ops, and reliable transport are part of the architecture, not
   an overlay bolted onto a lossy wire (contrast RoCE/UET on Ethernet).

These four — losslessness by construction, a central control plane, LID addressing, and
native RDMA — are why IB can hit µs-scale, line-rate, in-order GPU-to-GPU traffic that
Ethernet must engineer hard for. The cost is a purpose-built, single-ecosystem fabric at
higher per-port price. [I]

## How — the layers and node types in operation
### Layer responsibilities at a glance
| Layer | What it does | Key objects / fields | Handled by | Where it lives |
|---|---|---|---|---|
| Upper-layer (ULPs) | apps & protocols: IPoIB, SRP, iSER, NVMe-oF, MAD, UD multicast | IPoIB broadcast groups, SRP sessions | ULP software | above verbs |
| Verbs | RDMA programming interface | PD, MR, QP, CQ, WQE, CQE, rkey | libibverbs (user) | endpoint software |
| Transport | QP services, RDMA ops, reliability, ordering, RNR | RC/UC/UD/DC/XRC, PSN, AETH, RETH | HCA silicon | endpoint/offload |
| Network | inter-subnet routing | GID, GRH (40 B), routers | routers | optional L3 |
| Link | framing, LID forwarding, credit flow control, virtual lanes | LRH (8 B), LID, VL, SL2VL, credits | HCA + switches | L2 fabric |
| Physical | lane signaling, encoding, connectors, FEC | per-gen line code, 4x/8x lanes | HCA + transceivers | PHY |

### Nodes
Node types [F: NVIDIA security-in-IB / IBTA]:
- **HCA — Host Channel Adapter**: the endpoint NIC in a host, attached via PCIe. Each
  active port gets a 16-bit **LID** (SM-assigned) and a **GUID** (factory,
  64-bit). This is the device that executes verbs (posts WQEs, DMAs, drives transport).
- **Switch**: forwards between its ports **by LID**, using forwarding tables (LFT)
  programmed by the SM. Cut-through, low latency (~100 ns scale).
- **Router**: forwards **between subnets** by GID using the GRH; the only place IP-like
  network-layer routing appears (page [07-infiniband-addressing.md](./07-infiniband-addressing.md)).
- **Subnet Manager (SM)**: control-plane software (e.g. OpenSM, NVIDIA UFM) that
  *discovers* the fabric via SMAs in every HCA/switch, assigns LIDs, computes routes,
  programs LFTs, and configures partitions/QoS. **Without an SM the fabric does not come
  up.** Exactly one master SM per subnet; standbys monitor and take over. [F: OpenSM/UFM]
- **Subnet Administrator (SA)**: responds to path-record (PR) and other management
  queries — clients ask the SA for the best SL/MTU/rate/path rather than computing it
  themselves. [F: DOCA QoS docs]
- **TCA — Target Channel Adapter**: the legacy term for an endpoint on the *storage /
  peripheral* side (as opposed to a host). Rare in the GPU world today; HCAs dominate AI
  fabrics. [F: Wikipedia/IBTA]

### Node-type summary table
| Node | Role | Addressing | Control | GPU-world relevance |
|---|---|---|---|---|
| **HCA** | host endpoint (verbs executor) | LID + GUID (+GID) | SMA (managed by SM) | THE server NIC (ConnectX) |
| **TCA** | storage/peripheral endpoint | LID + GUID | SMA | legacy; not bought for GPUs |
| **Switch** | LID forwarding within subnet | LID-based LFT | SMA; gets LFT from SM | Quantum switches |
| **Router** | inter-subnet forwarding | GID/GRH | routed like L3 | only across subnets |
| **SM** | discovers + configures fabric | assigns all LIDs | master/standby election | OpenSM / UFM |
| **SA** | answers path-record queries | serves SL/MTU/rate | part of SM | used by apps/clients |

### Channel vs Host adapter
A **channel adapter** (generic IB term) is any end-node interface — the **HCA** is a
channel adapter on a *host* (CPU/GPU server), while the **TCA** is a channel adapter on
a *target* (storage/IO). Both present the same transport interface; the distinction is
what sits behind them. In AI practice you only buy HCAs (ConnectX) and the "TCA" concept
is historical. [F: Wikipedia InfiniBand; [I] for the AI-practice framing]

### How the Subnet Manager brings the fabric up
```text
1. SM (OpenSM/UFM) starts, scans its connected port
2. SM sends SMP (subnet management packets, VL15) to every node
3. Each HCA/switch responds via its SMA with its GUID, ports, capability
4. SM discovers the full topology (trees, loops), builds a fabric map
5. SM assigns each active port a 16-bit LID (single or multiple with LMC>0)
6. SM runs a routing engine (MinHop / Fat-tree / Up-Down / DFSSSP …) and
   programs each switch's LID forwarding table (LFT)
7. SM configures partitions (P_Key), QoS (SL2VL, MTU, rate), multicast
8. SM periodically sweeps (re-discovery, re-route on link/port change)
```
Every step partially orders the fabric: until the LFTs are programmed, no data packet
is forwarded — which is why "fabric won't come up" almost always means SM trouble
[I: synthesized from OpenSM/UFM flow; F: OpenSM manpage + NVIDIA SM docs].

### The verbs→HCA→fabric path (one RDMA WRITE, end to end)
```text
Application (e.g. NCCL ring step)
   │ ibv_post_send {WRITE, local SGE, remote VA, rkey}
   ▼
Verbs library (libibverbs) → user-space, kernel bypass
   │ ring doorbell (MMIO) → HCA
   ▼
HCA: fetch WQE, validate keys, DMA local mem, add headers,
     run transport (credits, PSN), drive link
   ▼
Fabric: LRH LID forwarding at each switch (credit flow, VL)
   ▼
Remote HCA: validate, DMA into remote HBM, generate CQE
   ▼
Remote app/NCCL sees completion (or the data just arrived)
```

## When
InfiniBand is the right choice when [I: design guidance; cross-ref [49-design-decision-tree.md](./49-design-decision-tree.md)]:
- **The workload is synchronous east-west collectives** (gradient sync, all-to-all) where
  losslessness and low tail latency dominate — the AI-train case.
- **Scale reaches hundreds to tens of thousands of GPUs/NICs** where a single subnet and
  SM-managed fabric is operationally tractable.
- **You want deterministic, SM-governed QoS** (SL→VL) rather than Ethernet's DCB/PFC.
- **You accept a single-vendor-ish, purpose-built fabric** and pay the higher per-port
  cost vs merchant-silicon Ethernet.
Choose RoCE/UET instead when you need commodity Ethernet economics, multi-vendor open
silicon, IP integration, or when lossless-isolation and SM complexity are liabilities.
IB is also the *reference* fabric the rest of this section teaches against
(page [05-infiniband-architecture.md](./05-infiniband-architecture.md) → all of Part B).

## Packet flow — what a packet looks like crossing the fabric
Within one subnet a packet is: **LRH (8 B) + [BTH (12 B) + operation headers] + payload
+ ICRC (4 B, invariant, end-to-end) + VCRC (2 B, variant, recomputed per link)**.
Inter-subnet (through a router) a **GRH (40 B)** is inserted between LRH and BTH
[F: `packet.transport.ib`]:
```text
 0            8            16         28           40         …        +2
|------------|------------|----------|------------|---------|-----|-----|
| LRH (8B)   | GRH (40B,  | BTH(12B) | op headers | payload |ICRC |VCRC |
| LID/SL/VL/ |  only when | opcode/  | RETH/DETH/ |         | (4B)|(2B) |
| length/op  |  routed)   | P_Key/PSN| AtomicEth  |         |     |     |
```
- **LRH** is rewritten at every hop (LID-based L2). **VCRC** changes per link.
- **ICRC** is computed once over invariant fields and verified end-to-end → corrupted
  packets are detected at the destination even if intermediate links are quiet.
- Header cost within subnet = **24 B/packet** (LRH 8 + BTH 12 + ICRC 4); at 256 B
  payload that's **9.38%** overhead, at 4096 B it's **0.59%** [E: constants bank].

## GPU relationship
For GPUs, the "host" behind the HCA is typically a server with 4–8 GPUs and 8× 400/800G
HCAs in a rail-optimized leaf (page [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md)). NCCL speaks
verbs over the HCAs; the **fabric topology is chosen so every rail has a dedicated
switch** so the HCA port isn't oversubscribed. The SM assigns each HCA port a LID; the
SM/SA policies set the **SL** NCCL uses (`NCCL_IB_SL`) and map it to a **VL** for QoS.
GPUDirect RDMA makes the HCA read/write GPU HBM directly ([15-gpudirect-rdma-nccl-infiniband.md](./15-gpudirect-rdma-nccl-infiniband.md)).
The fabric sees **HCA ports**, not GPUs — GPU count maps to HCA/NIC count
(`NCCL_IB_HCA` pins which HCAs NCCL uses). [F: NCCL env docs; [I] framing]

## Design
InfiniBand fabric design decisions [I: engineering guidance; F: OpenSM/NVIDIA docs]:
1. **One subnet with one master SM** (OpenSM or UFM), plus redundant standby SMs, is the
   norm for AI clusters. Keep it a *single* subnet so LID forwarding suffices — you
   rarely need routers/GRH inside a building (cross-subnet routing is for scaling beyond
   an SM's domain or site-to-site).
2. **Route choice is set by the SM.** OpenSM offers ~10 routing engines (MinHop,
   Up-Down, **Fat-tree** (credit-loop-free, ideal for symmetric AI topologies), DFSSSP,
   LASH…). For AI fat-trees/rails the **Fat-tree** engine is the standard pick [F:
   OpenSM `current-routing.txt`]. → [12-infiniband-routing-topology-partitions.md](./12-infiniband-routing-topology-partitions.md).
3. **Partition (P_Key) isolation** is the tenancy/security mechanism: switch ports can
   enforce that only packets with an allowed P_Key are forwarded. The SM is a full
   member of the default partition (0x7FFF); other nodes are limited members [F:
   NVIDIA security-in-IB]. → [47-security-multitenancy.md](./47-security-multitenancy.md).
4. **QoS via SL→VL**: pick an SL for control (VL15 carries only SM control traffic) and
   map AI data traffic to a data VL with weighted arbitration. NCCL sets SL; the SM's
   SL2VL policy maps SL→VL [F: DOCA QoS].
5. **Scale the fabric with radix**, not subnets: switch radix × port-rate × tier count
   (fat-tree math in [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md)).

## Tuning
Operationally, the levers on an IB fabric [F: OpenSM/NVIDIA; [I] practice]:
- **SM routing engine** — Fat-tree for AI symmetric fabrics; MinHop for general HPC.
- **LID assignment stability** — OpenSM preserves existing LIDs unless
  `-r/--reassign_lids`; stable LIDs keep ranks' addresses stable across restarts. [F:
  OpenSM manpage]
- **SL/VL mapping** — give NCCL data its own SL/VL so it never contends with management
  (VL15) or storage; two-priority weighted-round-robin arbiter honors high-priority
  credits first. [F: DOCA QoS]
- **MTU 4096** to minimize header overhead [E: 0.59% vs 9.38% at 256 B].
- **P_Key consistency** — enforce partitions the same way on every switch port and HCA
  or traffic silently fails.
- **SM HA** — run primary + standby with synchronized state to avoid a fabric-down on
  SM failure (single-SM fabrics cannot initialize/reconfigure). [F: MLNX-OS/UFP docs]
- **Congestion/adaptive routing** are configured via the vendor (NVIDIA) tools and need
  matching HCA (ConnectX-5+ OOO) and switch (Quantum) capability. → [13-infiniband-congestion-adaptive-routing.md](./13-infiniband-congestion-adaptive-routing.md).

## Troubleshooting
- **"Fabric won't come up" / nodes can't see each other** → SM not running or
  misconfigured; no LIDs assigned. Check SM status first — everything depends on it.
  [F: credit-loop/security docs]
- **Nodes reach the SM but not peers** → P_Key mismatch / partition-enforcement
  inconsistency (a classic). Verify P_Key membership + enforcement matches HCA↔switch.
  [F: NVIDIA security-in-IB]
- **Duplicate GUIDs** → two ports sharing a GUID break discovery/routing; `ibdiagnet` /
  `ibswitches` flag them; reflash distinct GUIDs. [A: OFA behavior]
- **Rising BER / link flaps** → check `perfquery`/`ibqueryerrors` counters:
  `symbol_error`, `link_error_recovery`, `link_downed` — hints of bad cable/fiber; IB
  link target ≈ 1e-12 BER, NVIDIA-qualified cables 1e-15 [F: DGX SuperPOD widths-rates].
- **Mysterious drops/timeouts in an otherwise-lossless fabric** → HOQ timeout (the only
  deliberate IB drop path) mis-set; review per-VL buffer/credit config. [F: credit-loop
  docs]
- **SL/VL misrouting** → wrong SL2VL policy or an SL with no data VL yields dead
  traffic; trace with `iblinkinfo`/SM logs.

## Comparison — IB architecture vs Ethernet vs (RoCE)
| Axis | **InfiniBand** | Ethernet (plain) | RoCEv2 (Ethernet+RDMA) |
|---|---|---|---|
| Native RDMA | yes (verbs in spec) | no (TCP/UDP) | yes over UDP:4791 |
| Losslessness | credit flow control (native) | none (lossy) | PFC pause + ECN/DCQCN (add-on) |
| Control plane | SM (LIDs, LFT, QoS) | DHCP/BGP/ARP | IP + routing |
| Addressing | LID (L2) + GID/GRH (optional) | MAC + IP | MAC + IP + UDP |
| L3 routing by default | no (opt. GRH/router) | yes | yes |
| Per-port economics | high (purpose-built) | low (commodity) | low (commodity) |
| Determinism/tail latency | excellent (designed) | variable | good with engineering |

The takeaway: IB moves losslessness + forwarding + QoS into the fabric/control plane;
Ethernet leaves loss to endpoints and adds RDMA/losslessness as layers on top. That is
the entire "why not just make Ethernet faster" argument. → [16-roce-fundamentals.md](./16-roce-fundamentals.md),
[23-roce-lossless-fabric-design.md](./23-roce-lossless-fabric-design.md).

## Lab
1. **Layer inventory.** On a host with OFED: `ibstat` / `ibv_devinfo` show the HCA,
   its ports, LIDs, and state ("LinkUp", 400 Gb/s). `ibstatus` = quick health. Observe
   that each port has a **LID** (SM-assigned) and **GUID** (factory). [I: tool behavior]
2. **See the SM at work.** Run `opensm -g --console_script` style SM (or use UFM), then
   `ibroute` / `ibswitches` / `ibnetdiscover` to see the discovered topology and the
   LID-forwarding tables the SM programmed. [I: OpenSM tooling]
3. **LID/sl change effect.** Modify `NCCL_IB_SL` (or `sl` in perftest) and observe QoS /
   path-record (SA) behavior change via the SL2VL mapping. [I]
4. **Fault the SM.** Stop the master SM alone: the fabric freezes (no new connections,
   no reconfig); restart or failover to standby restores it. Demonstrates single-point
   dependence → why HA matters. [I]
5. **Min-hop vs fat-tree route.** Re-run the SM with `-R ftree` vs `-R minhop` and diff
   `ibroute` output on a fat-tree; see the deadlock-free, credit-loop-safe path set. [F:
   OpenSM routing docs]

## Key Takeaways
1. InfiniBand is a **purpose-built switched fabric for RDMA**, not "faster Ethernet": losslessness comes from **per-link, per-VL credit flow control** (the fabric stops sending before buffers overflow — no congestion drops), not drop-and-retry.
2. A central **Subnet Manager (SM)** discovers the fabric, assigns 16-bit LIDs, and programs switch LFTs — there is no BGP/ARP by default, and **without an SM the fabric does not come up**.
3. **LID-based L2 forwarding** carries intra-subnet traffic (LRH, 24 B header); 128-bit **GID/GRH** (40 B) appears only when a **router** crosses subnets — typically unnecessary in a single-subnet AI fabric.
4. Node types are the **HCA** (host endpoint/verbs executor), switch, router, SM, and SA; TCA is the legacy storage/peripheral endpoint.
5. Four structural differences vs Ethernet — native credit losslessness, SM control plane, LID addressing, and verbs/RDMA in the spec — are why IB delivers µs-scale, in-order, line-rate GPU traffic.

## Related
- [04-rdma-operations-and-transports](./04-rdma-operations-and-transports.md) — the verbs model the layers carry.
- [07-infiniband-addressing](./07-infiniband-addressing.md) — LID/GID/GRH in depth.
- [09-infiniband-packet-format](./09-infiniband-packet-format.md) — headers/opcodes byte-for-byte.
- [10-infiniband-flow-control-and-qos](./10-infiniband-flow-control-and-qos.md) — the credit/VL machinery that makes IB lossless.
- [11-infiniband-subnet-manager](./11-infiniband-subnet-manager.md) — SM/OpenSM/UFM deep dive.
- [17-why-roce-is-harder](./17-why-roce-is-harder.md) — contrast with lossless-Ethernet complexity.
- [GPU-Communication/README](../GPU-Communication/README.md) — the software stack that drives these layers.

## References
- IBTA, InfiniBand Architecture Specification Vol 1 (PHY→transport) [F].
- NVIDIA: "Security in InfiniBand" networking docs; DOCA IB QoS; OpenSM docs.
- Wikipedia "InfiniBand" (OSI-style layer table, node types) [F].
- OpenSM routing guide (`current-routing.txt`) [F].
- [E] header-overhead figures from the section constants bank (computed 2026-08-25).
