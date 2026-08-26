# InfiniBand Routing, Topology & Partitioning
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: OpenSM `current-routing.txt`, NVIDIA InfiniBand security / QoS docs, IBTA spec via NVIDIA forum; oversubscription arithmetic from the section constants bank (2026-08-25).

## 30-Second Explanation
Inside an InfiniBand **subnet**, every packet is forwarded by **LID** through switch
**forwarding tables (LFTs)** that the **Subnet Manager (SM)** computes — this page is about
*how* the SM decides those paths, *what shape* the fabric is, and *how* you isolate tenants
on top of it. The SM can compute routes a dozen ways: the default (**MinHop**), deadlock-free
orderings (**Up/Down**, **DOR**), and fat-tree-specialized engines (**credit-loop-free**) [F:
OpenSM routing engine list]. The fabric is then almost always one of a few canonical
shapes — **fat tree / Clos**, **Dragonfly/Dragonfly+**, or **rail / multi-plane** — whose
**oversubscription** (1:1, 2:1, 4:1) is a pure arithmetic choice [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md)
[E]. Isolation is handled by the **P_Key partition** carried in every packet's BTH, enforced
at switch ports [F: NVIDIA security doc]. Read [05-infiniband-architecture.md](./05-infiniband-architecture.md) first for
the layers; this page is the "control plane decides the path + fabric + tenants" story.

## Routing strategies

### What
The SM runs a **routing engine** that assigns each switch an LFT: for every destination LID,
which output port forwards it. OpenSM ships ten engines [F: OpenSM `current-routing.txt`]:

| Engine | Deadlock-avoid. | Notes |
|---|---|---|
| **MinHop** (default) | no (relies on credits) | plain shortest-path; the OpenSM default |
| **UPDN** (up*/down*) | yes (rank ordering) | acyclic by port-rank; from the up*/down* theory |
| **DNUP** | yes | Up/Down computed "down-first" (inverse of UPDN) |
| **Fat-tree** | credit-loop-free | for symmetric fat-trees; ideal for AI Clos |
| **LASH** | yes (SL-based) | shortest paths, deadlocks broken by **service level (SL)** reassignment |
| **DOR** (dimension-order routing) | yes | torus/Dragonfly: de-route one dimension at a time |
| **DFSSSP** | yes (single-source) | deadlock-free single-source shortest path |
| **Torus-2QoS / SSSP** | mixed | specialized / research engines |

### Why
MinHop gives the fewest hops but can place many long flows onto the same links (hot spots)
and, on a fat tree, can build clockwise/counter-clockwise loops that exhaust credit buffers
— the fabric is lossless, so a "credit loop" makes packets stall, not drop [F: credit-loop
article]. Deadlock-free engines trade hop optimality for the guarantee that the path graph
contains no cycle that could deadlock the credit mechanism. On the shapes AI fabrics
actually use, you rarely want MinHop: **fat-tree** on Clos, **DOR/UPDN** on Dragonfly [F:
OpenSM list].

### When to pick which
```text
Topology you built        Best routing engine (OpenSM)
────────────────────────────────────────────────────────
Symmetric fat-tree/Clos   fat-tree (credit-loop-free)   ← AI default
Irregular / floor-plan    MinHop or UPDN
Torus / Dragonfly         DOR (dimension-order)
Any + prune              DFSSSP / UPDN for deadlock-free
```
The practical rule for AI: if the fabric is a clean multi-leaf/spine fat tree, run the
**fat-tree** engine; anything else, prefer a deadlock-free engine over naive MinHop. [I:
standard OpenSM practice]

## Deterministic vs adaptive routing

### What
**Deterministic routing** (MinHop, fat-tree, DOR) pins a flow to one path for its lifetime:
the switches choose the same next hop for every packet of a flow. **Adaptive routing (AR)**
re-evaluates per packet (or per message) at each switch and can take a different next hop
based on live congestion, so two packets of the same flow may exit a switch on *different*
links and arrive **out of order**. [F: NVIDIA adaptive-routing whitepaper]

| Property | Deterministic | Adaptive (AR) |
|---|---|---|
| Path choice | fixed at route computation | per-packet/message at each switch |
| Symmetric hash hot spots | possible (polarization) | mitigated (sprays load) |
| Packet ordering | in-order by construction | out-of-order possible → HCA must reorder |
| NIC requirement | any | ConnectX-5+ in-HW OOO; DC transport [F: NVIDIA whitepaper] |
| Determinism / reproducibility | high | lower (path varies run-to-run) |
| Fabric utilization under skew | lower tails | higher (see ./13) |
| Where it lives | SM control plane | switches + NIC data plane |

The full congestion/AR story (signals, tradeoffs, NCCL toggles) is [13-infiniband-congestion-adaptive-routing.md](./13-infiniband-congestion-adaptive-routing.md).

## Topologies

### Fat tree / Clos
The canonical AI fabric: leaf switches hold the GPUs, spines interconnect leaves, uplinks
sized to 1:1. [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) carries the arithmetic; the picture:
```text
         spines  [ S1 ]----[ S2 ]----[ S3 ]----[ S4 ]      (spine layer, 1:1 → S = L)
                  │   │      │   │      │   │      │  │
        leaves   [L1][L2]  [L3][L4]  [L5][L6]  [L7][L8]    (leaf layer)
                   │  │      │  │      │  │      │  │
        hosts    g0 g1      g2 g3      g4 g5      g6 g7    (NICs/GPUs)
```
Every leaf reaches every other leaf through any spine — non-blocking when oversub = 1:1.

### Dragonfly & Dragonfly+
Instead of one fat Clos, **Dragonfly** groups switches into *groups*; within a group,
switches interconnect (all-to-all or a small Clos), and groups interconnect at a high radix.
A packet typically makes **3 hops**: source→group local, group→group, group→dest. This cuts
diameter (and switch count at scale) versus a giant Clos, at the cost of **group-to-group
uplinks being the scarce resource** (deliberately oversubscribed). **Dragonfly+** (per NVIDIA
"1x" variant) reshapes the group interconnect. NVIDIA claims Quantum-2 (NDR400) forwards
networks of ≥1e6 400G nodes in a 4-tier Dragonfly+ design [F: vendor spec — not independent].
```text
 Group G0            Group G1
 [S0a]──[S0b]        [S1a]──[S1b]       intra-group: switches mesh
   │  ╲     │          │  ╲     │
   │   ╲    │          │   ╲    │
   └────┬───┘          └────┬───┘
        └────────┬──────────┘        inter-group: high-radix uplinks (scarce)
                 │
        (3-hop path S0a → G0 local → G1 local → S1a)
```

### Rail-optimized, multi-rail, multi-plane, direct-connect
```text
Rail-optimized (dedicated leaf per NIC index):
   NIC#0 of every node  ──► Leaf_rail0      "rail 0"
   NIC#1 of every node  ──► Leaf_rail1      "rail 1"
   ...                                          (NCCL_CROSS_NIC=0 keeps a ring on one rail)

Multi-rail = each node has >1 NIC used in parallel.
Multi-plane = several independent rail-optimized fabrics (planes), one per NIC index,
              scaling linearly in plane count instead of one giant Clos.
Direct-connect = switches connect directly (torus/dragonfly edges), no spine layer.
```
Rail/multi-plane are detailed in [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md). The AI takeaway:
modern GPU pods (DGX + 8 NICs/node) build **rail-optimized multi-plane** fabrics so NCCL's
ring traffic on one rail never contends with another rail's — oversubscription is per-plane.

## Oversubscription 1:1 / 2:1 / 4:1

### What
Oversubscription = **inject bandwidth ÷ bisection bandwidth** [E: constants bank, Clos math].
- **1:1** — bisection = injection (every leaf can hammer the fabric at line rate). Needed
  for synchronized all-to-all collective stress. Cost: spines = leaves [E].
- **2:1** — bisection = half of injection; uplinks are the bottleneck under heavy east-west.
- **4:1** — quarter of injection; fine for some HPC/storage, wrong for AI collectives.

| Oversub | Meaning | bisection @1024×400G | When it's OK |
|---|---|---|---|
| 1:1 | non-blocking | 6.4 TB/s (32 L + 32 S) [E: bank] | AI training AllReduce/AllToAll |
| 2:1 | half capacity | 3.2 TB/s (16 spines) [E: bank row] | checkpoint, storage, some MoE |
| 4:1 | quarter capacity | ~1.6 TB/s (8 spines) [I: derived, half of the 2:1 bank row by construction] | HPC scatter/gather, management, DCI tails |

The full leaf/spine counts and the worked 32→32,768-GPU examples are
[42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) [E]. Rule of thumb [I]: **1:1 for scale-out GPU collectives;**
oversubscribe only fronts/management, never the gradient/activation plane.

## P_Key partitioning

### What
A **P_Key (partition key) = 16-bit** tag bound to each Queue Pair. Every packet carries its
QPs P_Key in the **BTH**; receivers filter on it. The **default partition (0x7FFF)** must
include every node; the **SM is a full member** of it and other nodes are **limited members**
[F: NVIDIA security doc]. Tenant isolation uses admin-defined P_Keys 0x0001–0x7FFE.

### Full vs limited membership
```text
Full member      — can both RECEIVE and SEND anywhere in the partition (a P_Key "owner").
Limited member   — can receive from, and send to, FULL members of its partition;
                    it cannot send to OTHER limited members (P_Key bit-15 restricts
                    limited→limited traffic).
```
In practice: the SM (and management/redfish paths) are full members of the default
partition; compute nodes are limited members of default + members of whatever tenant
partition(s) they belong to. [F: NVIDIA security doc]

### Enforcement at switch ports
The decisive mechanism is **partition enforcement on switch ports**: the SM programs each
switch port with which P_Keys may pass through it, and the switch drops anything else. This
is what actually isolates tenants on a shared fabric — it is per-**switch-port**, not just
a NIC-side claim. A mismatch (enforcement on the switch, inconsistent HCA memberships on the
neighbor) **silently blocks traffic**: "nodes see the SM but not each other" is the classic
symptom. [F: NVIDIA security doc; §12 of research notes]

### P_Key table programming
The SM/SA maintains each HCA's **P_Key table** (index → P_Key value + full/limited flag) and
the switch ports' membership. `ibswitches` / `ibdiagnet` / UFM expose it; tools like
`ib-kubernetes` (in NVIDIA Network Operator) program P_Keys for pods [F: Network Operator
docs]. Each partition also carries QoS (SL/MTU/rate) via its IPoIB broadcast group [F:
NVIDIA QoS doc].

### Comparison vs Ethernet VLAN / VRF
| Property | IB P_Key | Ethernet VLAN / VRF |
|---|---|---|
| Tag location | BTH of every packet | 802.1Q header / L3 VRF table |
| Enforcement point | switch port (SM-programmed) | switch + NIC (802.1Q); VRF at L3 router |
| Granularity | per-QP P_Key; full/limited roles | per-port/untagged; per-VRF |
| Membership model | full/limited distinct semantics | broadcast domain (VLAN) / routing table (VRF) |
| Looping/isolation | by port enforcement | by VLAN isolation / VRF separation |
| QoS binding | per-partition SL/MTU/rate | per 802.1p/DSCP |

Both isolate; IB's P_Key couples the isolation with the **transport** (QP bound to P_Key,
packet carries it), while Ethernet VLANs/VRFs are framing/routing-layer fabrics [F: NVIDIA
security doc; [I] comparison].

### GPU-as-a-Service implications
A GPU-as-a-Service (cloud/MaaS) fabric must give each tenant an isolated, predictable slice
of the shared IB network. That is exactly what P_Key partitioning provides: a tenant's QPs
carry a tenant P_Key, switch-port enforcement stops cross-tenant traffic, and per-partition
QoS delivers isolation of bandwidth/latency. The catch [I]: P_Key isolation is an
**L2/LID-subnet** boundary — if tenants must also be protected from layer-management and
LID-reachability abuse, combine P_Key with per-tenant subnets/routers and SM policy
([47-security-multitenancy.md](./47-security-multitenancy.md)). The cost of getting it wrong (one node in two partitions
leaking, or enforcement mismatch killing a whole tenant) is why production cloud fabrics
pair P_Key with careful SM/UFM policy and extensive `ibdiagnet` validation.

## Failure modes
- **Routing-engine mismatch** — running MinHop on a fat tree → credit loops / hot spots;
  re-run the fat-tree engine.
- **P_Key enforcement mismatch** — switch port blocks a neighbor whose membership isn't set
  identically → silent no-communication.
- **Duplicate LIDs/GUIDs** — SM discovery breaks; fix one GUID stray.
- **Oversubscribed a collective plane** — 2:1/4:1 on the gradient plane → busbw collapses
  (see ./44).

## How to measure it
`ibdiagnet` (fabric scan + route dump `-r`), `ibswitches`, `ibqueryerrors` for port state;
`nvidia-smi topo -m` for host↔NIC locality; nccl-tests `busbw` tells you whether the
computed topology actually delivers line rate (→ [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md)).

## Key Takeaways
1. The SM's routing engine decides paths; use **fat-tree** on Clos, **DOR/UPDN** on Dragonfly.
2. Deterministic = in-order, hot-spot-prone; adaptive = sprayed, needs NIC OOO (→ ./13).
3. AI fabrics are 1:1 rail/multi-plane Clos or 3-hop Dragonfly; oversub is arithmetic [E].
4. **P_Key** partitions isolate tenants; enforcement lives at switch ports [F].
5. GPU-as-a-Service rides on P_Key + SM policy for tenant isolation.

## Related
- [05-infiniband-architecture.md](./05-infiniband-architecture.md) — layers, node types, SM role.
- [13-infiniband-congestion-adaptive-routing.md](./13-infiniband-congestion-adaptive-routing.md) — congestion + adaptive routing.
- [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) — oversubscription arithmetic [E].
- [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md) — rail/multi-plane deep dive.
- [47-security-multitenancy.md](./47-security-multitenancy.md) — P_Key, VLAN/VRF, SR-IOV (planned).

## References
- OpenSM routing engines: github.com/linux-rdma/opensm/blob/master/doc/current-routing.txt [F].
- NVIDIA InfiniBand security & P_Key: networking-docs.nvidia.com/nvidiainfinibandsecurityoverviewandguidelines/security-in-infiniband [F].
- NVIDIA QoS / P_Key QoS policy: networking-docs.nvidia.com/doca/archive/3-4-0/infiniband-qos [F].
- NVIDIA credit-loop / fat-tree engine: enterprise-support.nvidia.com/s/article/howto-prevent-infiniband-credit-loops [F].
- OpenSM manpage: manpages.ubuntu.com/manpages/focal/man8/opensm.8.html [F].
- [E] oversubscription rows from the section constants bank (computed 2026-08-25).
