# InfiniBand Addressing: GUIDs, LIDs, and GIDs
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: IBTA — `packet.transport.ib` manpage, NVIDIA InfiniBand security/architecture docs, OpenSM manpage; arithmetic from section constants bank (2026-08-25).

## 30-Second Explanation
An InfiniBand fabric names every endpoint with **three identifiers at three scopes**[A: standard IBTA]:

- **GUID** — a 64-bit, factory-assigned, immutable identity burned into the hardware (per node, per port, per system image).
- **LID** — a 16-bit, **SM-assigned** number for each active port. It lives in the **LRH** and is the only address a **switch** needs to forward a packet inside the subnet.
- **GID** — a 128-bit address (`64-bit subnet prefix ‖ 64-bit port GUID`) used only when a packet must **cross a router into another subnet**, carried in an optional **GRH**.

The practical rule: **within a subnet, route by LID using the LRH alone; only when you leave the subnet do you add a GID and the 40-B GRH.** That is why an intra-subnet IB packet carries only a 24-B header, but an inter-subnet packet adds the GRH and carries 64 B [E] — the price of a globally-addressable, IPv6-shaped address space you almost never need inside an AI fabric, where nearly everything lives in one subnet.

## What
Three address objects, plus two route headers, make up IB addressing [F: https://manpages.ubuntu.com/manpages/noble/man3/packet.transport.ib.3.html]:

| Object | Size | Assigned by | Scope | Carried in | Used for |
|---|---|---|---|---|---|
| Node/Port/System-Image GUID | 64-bit | manufacturer | global, immutable | management/MAD | hardware identity, GID base |
| LID | 16-bit | SM | **one subnet only** | LRH | switch forwarding (LFT/FDB) |
| GID | 128-bit | prefix by SM + port GUID | global (across subnets) | GRH | router forwarding |
| LRH | 8 B | per-hop (rewritten) | local link | — | LID + SL + hop count |
| GRH | 40 B | at source | end-to-end | — | source/dest GID, mirrors IPv6 |

**GUIDs.** Every HCA exposes three distinct 64-bit GUIDs [A: IBTA / `ibv_devinfo`]: the **Node GUID** (identifies the HCA/device), the **Port GUID** (identifies each physical port), and the **System Image GUID** (ties all ports under one OS image together, used for failover/path-selection grouping). The Port GUID is the base leg of the Port GID. They are read by `ibv_devinfo` and recorded by `ibdiagnet` during fabric scans [F: standard OpenFabrics tooling].

**LID.** A 16-bit Local ID is assigned by the SM to every port the SM discovers and decides is *active*. Switches forward on the value in the LRH against their **LFT / forwarding database**, and every hop **consumes and rewrites** the LRH — the LID is a per-link, not end-to-end, value. Because it is 16 bits, the address space is small (65,535), which is *fine*: a LID only has to be unique within one subnet, and a router translates to a fresh LID for the next subnet. **LMC** (LID Mask Count) extends this: an LMC > 0 makes the SM assign a contiguous *block* of 2^LMC LIDs per port. NVidia/IB uses this to give multi-pathing software several addresses per port, e.g. LMC=3 → 8 LIDs [F: https://manpages.ubuntu.com/manpages/focal/man8/opensm.8.html]. Most AI fabrics run LMC=0 [I].

**GID.** The 128-bit GID = `64-bit subnet prefix ‖ 64-bit port GUID` [F: https://manpages.ubuntu.com/manpages/noble/man3/packet.transport.ib.3.html]. The subnet prefix is chosen by the SM (commonly the IPv6-style `fe80:...` link-local or an admin-assigned prefix); the low 64 bits come from the port GUID. The GRH layout *mirrors* IPv6 (RFC 2460) — but there is **no defined GID↔IPv6 mapping** in IB [F: https://manpages.ubuntu.com/manpages/noble/man3/packet.transport.ib.3.html]. GID index 0 on an HCA is usually the link-local (`fe80::/`) GID; additional indices carry admin-assigned global prefixes. The GID that NCCL actually uses on a port is selected via `NCCL_IB_GID_INDEX` (user-chosen index into the port's GID table; it is **not** auto-negotiated) [F: https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html].

## Why
Two independent problems drove this split [I: architecture rationale]:

1. **Small, fast lookups where it matters.** A switch at 50 GB/s per port only has a link-tick or two to look up the next hop. A 16-bit LID indexed directly into a forwarding table is a single lookup that fits in SRAM. A 128-bit GID hashed on every hop would add latency and cost for a capability (global routing) the vast majority of packets never need.
2. **Immutable identity that survives reboots and re-cabling.** GUIDs are burned in, so the fabric can *discover* and *name* hardware before any SM runs; LIDs are assigned dynamically and can be reshuffled by the SM. Identity (GUID) and location (LID) are deliberately decoupled, exactly like MAC (identity-ish) vs IP (location) in Ethernet — except IB keeps both in a single layer.

## How
**Local (intra-subnet) routing — LRH only:** the source HCA stamps an LRH with the dest LID; every switch looks up that LID, picks an output port, rewrites its LRH, and forwards; the fabric never consults a GID.

```text
  Local routing (one subnet) — LID-based, LRH only
  ┌─────────┐   LRH{DstLID}   ┌─────────┐   LRH{DstLID}   ┌─────────┐
  │ HCA A   │ ────────────► │ Switch 1│ ────────────► │ Switch 2│
  │ LID=1   │                │  LFT    │                │  LFT    │
  └─────────┘                │ LID→port│                │ LID→port│──► LID=n
                             └─────────┘                └─────────┘
  Headers used: LRH(8B) + BTH(12B) + … + ICRC(4B)   = 24 B [E: constants bank]
  Address consulted: LID only.  GRH absent (Global bit in LRH = 0).
```

**Global (inter-subnet) routing — GRH + GID:** when the source subnet prefix differs from the destination's, the HCA sets the LRH **Global bit** and adds a **GRH** carrying source and destination **GIDs**. IB *routers* (not switches) read the GRH, decrement the hop limit, and forward the packet into the next subnet, where a *new* LRH is stamped for the next leg [F: https://manpages.ubuntu.com/manpages/noble/man3/packet.transport.ib.3.html].

```text
  Global routing (across subnets) — GID-based, GRH + LRH
  subnet 10.0.0/16        IB Router        subnet 20.0.0/16
  ┌─────────┐ GRH{S=10GID,D=20GID}+LRH  ┌─────────┐  GRH{S,G}+{new LRH}  ┌─────────┐
  │ HCA A   │ ───────────────────────► │ Router  │ ─────────────────► │ HCA B   │
  └─────────┘   (within sub: LID fwd)   └─────────┘   (re-routing by GID)  └─────────┘
  Headers used: LRH(8B) + GRH(40B) + BTH(12B) + … + ICRC(4B) = 64 B [E: 8+40+12+4]
  Address consulted: GID (in GRH) at the router; LID still rewritten hop-by-hop.
```

### When
Use **LID/LRH** for everything inside one subnet — which in an AI fabric is essentially *all* RDMA traffic between GPUs in a cluster (NCCL communicates LID-to-LID on RC/DC QPs, never GID-to-GID) [I: standard]. Use **GID/GRH** only when you actually route across an IB **router** — e.g. two datacenter pods joined by a router, or management/IPoIB that spans subnets. If you never have a router, you can safely ignore GRH.

### Hardware impact
The HCA must hold, per active port, the SM-assigned LID(s) (and LMC block), the GUIDs, and the 16-bit GID index table [A]. Switches pay for nothing larger than a 16-bit LID keyed forwarding table; the moment a fabric enables Global routing, every switch that is a *router* also needs GRH lookup hardware and hop-count decrement [I]. In practice this almost never appears on AI leaf/spine (all-IB, one subnet), so the silicon cost of GRH sits mostly idle.

### Inference impact
Indirect but load-bearing: disaggregated inference and KV-cache transfer rely on the same RC QPs and the same LID-based fast path described in [03-rdma-fundamentals.md](./03-rdma-fundamentals.md) and [08-infiniband-queue-pairs.md](./08-infiniband-queue-pairs.md). Address resolution is a one-time cost at QP setup (the peer's LID/GID is exchanged out-of-band or via the SA path record), not something paid per byte — so addressing overhead is invisible to steady-state inference throughput [I].

### Example — hand calculation
An NDR400 port carries **50 GB/s** of payload [E: constants bank]. Wrap that back into addressing:
- Intra-subnet overhead at a 4096-B payload: 24/4096 = **0.59%** [E: constants bank]; at a 256-B payload: 24/256 = **9.38%** [E: constants bank]. So small messages pay disproportionately for the always-present LRH+BTH+ICRC.
- Inter-subnet (add the 40-B GRH): 64/4096 = **1.56%**; at 256 B: 64/256 = **25.0%** [E: 64 = 8(LRH)+40(GRH)+12(BTH)+4(ICRC); /256].

At 256-B payloads the global header eats a quarter of the wire — one concrete reason AI fabrics stay single-subnet and never quantize down to tiny messages on a routed path [I].

### Failure modes
- **Duplicate GUIDs** — two ports sharing a GUID break SM discovery/routing; OpenSM/`ibdiagnet` flag duplicates; fix by flashing distinct GUIDs [A: standard OFA behavior; see [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md)].
- **LID reassignment surprise** — re-running OpenSM (or a failover) with different assignment rules can reshuffle LIDs and strand connections; OpenSM preserves existing LIDs unless `-r/--reassign_lids` [F: OpenSM manpage].
- **Wrong subnet prefix / GID index** — a mismatched GID index in RoCE, or a wrong prefix, silently fails to reach the peer [F: NCCL docs].
- **Router misconfig / no route** — Global routing with a destination GID that has no path → packets dropped at the router; symptoms look like "can talk within pod, not across" [I].

### How to measure it
`ibv_devinfo` shows ports, GUIDs, and LIDs; `ibaddr` resolves and prints GID/LID for a port; `ibdiagnet` scans the whole fabric and reports LID/GUID tables and duplicate GUIDs [F: standard OFA]. `ibroute` walks the LFT. On the live QP, `rdma resource show qp` prints the local and remote QPN pair (`lqpn`/`rqpn`) your connection is actually using [A].

## Where the numbers come from — a worked address resolution
Walking a real connection from wire-up to live QP ties all four objects together [I: standard bring-up]:

```text
  1. Power on: HCA has GUIDs (node/port/system-image) burned in, NO LID yet.
  2. SM discovers via SMP/QP0: asks SMA on the HCA for its GUIDs.
  3. SM assigns LID (and 2^LMC of them if LMC>0) to the active port.
  4. SM builds the subnet prefix; combines it with the port GUID to form GIDs.
  5. NCCL/app calls SA (QP1) for a path record: "dest <GUID/LID> → SL/MTU/rate".
  6. App creates QP, gets peer LID/GID/QPN, walks QP to RTR→RTS (see ./08...).
  7. Every packet now carries {LRH:DstLID} intra-subnet (or {GRH:DestGID} + LRH across).
```

The identities a single port ends up with on a typical HCA [A: standard HCA]:

| Object | Example value | Who picks it | Stable across reboot? |
|---|---|---|---|
| Node GUID | `0x248a070300abcdef` | factory | yes |
| Port GUID | `0x248a070300abcdef01` | factory | yes |
| System Image GUID | `0x248a070300abcdef02` | factory/OS | yes |
| LID | `0x0021` (=33) | SM | no — re-assigned on rediscovery |
| Subnet prefix | `fe80:0000:...` (link-local) or admin prefix | SM/admin | usually |
| Port GID | `fe80::248a:07ff:fe00:...` (prefix‖portGUID) | SM+factory | derived |

### How the LID space and LMC work in practice
With LMC=0 a port has exactly one LID. With LMC=k it owns a block of 2^k LIDs — 8 with LMC=3 — and the SA/switch can use the block for explicit multipathing (different flows pin to different LIDs of the same port) [F: https://manpages.ubuntu.com/manpages/focal/man8/opensm.8.html]. Two caveats [I]: an LMC>0 grows each LFT row per LID in the block (LFT size grows), and IB runs out of LID space faster — everything must fit in 16 bits. AI fabrics overwhelmingly use LMC=0.

### GID indexes and the link-local vs global GID
Each port carries a **table of GIDs** (the "GID index" the verbs `ibv_query_gid` reads). Index 0 is almost always the **link-local** GID (`fe80::` prefix). Higher indices carry admin-assigned global prefixes and are what a routed/RoCE deployment selects [I]. On native single-subnet IB, NCCL's `NCCL_IB_GID_INDEX` either stays default or is set to 0/1 and auto-negotiated, because the GID is only meaningful if a router will actually use it; on RoCE it must point at the correct IPv6/global GID or the peer is unreachable [F: https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html].

## Example — hand calculation (concrete)
Say an HCA reports Port GUID `0x248a0703A001B2C3` and the SM sets an IPv6-style subnet prefix `fe80::` (so the first 64 bits are `fe80:0000:0000:0000`). The **Port GID** = `fe80::<low 64 bits of port GUID>` = `fe80:0000:0000:0000:248a:0703:a001:b2c3`. This is the 128-bit value that rides in the GRH only when a router is involved. Meanwhile the same port's **LID** might be `0x0015` (21) — and that single 16-bit number is all a switch's LFT cares about for intra-subnet forwarding. Net: the switch does a 16-bit lookup; the router would do a 128-bit GID lookup; both read correctly off the same fabric because the identity and the location are stored separately [I].

Overhead recap, with [E] from the bank — for a 4096-B message: intra-subnet 24/4096 = **0.59%**, inter-subnet 64/4096 = **1.56%**; for a 256-B message intra-subnet 24/256 = **9.38%**, inter-subnet 64/256 = **25.0%** [E: constants bank deltas: 24 = 8(LRH)+12(BTH)+4(ICRC); 64 = 8+40+12+4]. The jump at small messages is why routed/global headers are avoided for fine-grained GPU traffic.

## Addressing model summary table
| | GUID | LID | GID | LRH | GRH |
|---|---|---|---|---|---|
| Bits | 64 | 16 | 128 | — | — |
| Scope | global/immutable | one subnet | global | per-link | end-to-end |
| Assigned by | factory | SM | prefix by SM | rewritten per hop | at source |
| Routing use | identity only | switch forwarding | router forwarding | carries LID+SL | carries GIDs |
| In AI fabric? | yes (identity) | yes (every pkt) | rarely | always | only if routed |

## Multicast and IPoIB — where GIDs/link-local addressing actually show up
Multicast groups are addressed by a **MCG (multicast group)** GID, and IPoIB (IP-over-IB) lives on the management-like **IPOIB broadcast/multicast group**, one per partition [I; standard]: traffic to `255.255.255.255` or a subnet broadcast resolves to the partition's multicast GID. This is the one place GIDs are genuinely used even in single-subnet AI fabrics — the IPoIB control plane and any IP multicast. For GPU RDMA (NCCL, etc.), the data path is unicast LID/LRH, but the *setup* often touches IPoIB GIDs once at startup [I]. It also means every partition needs a working multicast group, or IPoIB neighbors vanish — a common "everything unicast is fine, control plane can't reach" failure [see [11-infiniband-subnet-manager.md](./11-infiniband-subnet-manager.md)].

## Key Takeaways
1. **GUID = identity (immutable, 64-bit); LID = location (SM-assigned, 16-bit, per subnet), GID = global address (128-bit, prefix ‖ port-GUID).**
2. Within a subnet, switches forward on **LID via the LRH only**; the 40-B **GRH** appears **only** when a router must carry the packet across subnets by **GID**.
3. That split is why intra-subnet headers are **24 B** but global headers are **64 B** [E]; at small messages (256 B) global overhead hits **25%** [E].
4. **LMC>0** gives a port a block of 2^LMC LIDs for multipathing; AI fabrics overwhelmingly use LMC=0.
5. NCCL's `NCCL_IB_GID_INDEX` matters mainly for **RoCE** (which IPv6/global GID); on native IB it's link-local index 0/1 and auto-negotiated [F].
6. The same HCA can be reached by LID (switch) or GUID/GID (router) — identity and location are stored separately, which is what makes re-wiring and re-LIDing survivable [I].

## References
- IBTA — `packet.transport.ib` (LRH/GRH, GID, BTH): https://manpages.ubuntu.com/manpages/noble/man3/packet.transport.ib.3.html
- NVIDIA InfiniBand security / node types / SM: https://networking-docs.nvidia.com/nvidiainfinibandsecurityoverviewandguidelines/security-in-infiniband
- OpenSM manpage (LID assignment, LMC, `-r`): https://manpages.ubuntu.com/manpages/focal/man8/opensm.8.html
- NCCL env (GID index, SL): https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html
- [E] figures from the section constants bank (computed 2026-08-25).

## A note on scope and adjacent pages
Addressing is often where new readers conflate IB with TCP/IP; the most useful one-liner is that **IB separates identity (GUID), location (LID), and global reachability (GID), and keeps them in different headers so each hop can re-stamp exactly the fields it must touch** [I]. The layer below (link/physical) is in [41-physical-layer.md](./41-physical-layer.md); the subnets/routing/topology view that consumes LIDs and GIDs is [12-infiniband-routing-topology-partitions.md](./12-infiniband-routing-topology-partitions.md); the way those become live connections is [08-infiniband-queue-pairs.md](./08-infiniband-queue-pairs.md). When something "connects in one subnet but not two," walk the address model before touching QPs: is it a LID problem here, or a GID/GRH problem at the boundary? [I]

## Related
- [05-infiniband-architecture](./05-infiniband-architecture.md) — the layer stack these headers sit in.
- [08-infiniband-queue-pairs](./08-infiniband-queue-pairs.md) — how a QP is brought up over a resolved LID/GID pair.
- [12-infiniband-routing-topology-partitions](./12-infiniband-routing-topology-partitions.md) — routing engines and how LIDs feed LFTs.
- [45-troubleshooting-rdma-infiniband](./45-troubleshooting-rdma-infiniband.md) — duplicate GUID / LID / P_Key failure hunting.
- [55-cheat-sheet](./55-cheat-sheet.md) — quick LID/GID/GUID reference.
- [GPU-Communication/README](../GPU-Communication/README.md) — the GPU-communication layer that runs over this fabric.
