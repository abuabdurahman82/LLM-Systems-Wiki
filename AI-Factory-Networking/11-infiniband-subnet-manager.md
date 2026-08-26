# InfiniBand Subnet Manager: The Control Plane That Brings the Fabric Up
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: OpenSM manpage & routing doc, NVIDIA UFM/OpenSM/SM-HA docs, NVIDIA IB security & QoS docs, IBTA `packet.transport.ib` manpage; no [E] numbers used beyond the constants bank.

## 30-Second Explanation
InfiniBand has **no plug-and-play data plane** — nothing routes until a **Subnet Manager (SM)** says so. The SM is a control-plane process that **discovers** every HCA and switch, **assigns LIDs** to every active port, **computes routes** and **programs each switch's forwarding table (LFT)**, configures **QoS (SL2VL, arbitration)** and **partitions (P_Key)**, and keeps monitoring. It talks to the hardware through **management packets (MADs)** carried on the two well-known management QPs, **QP0 (subnet-management packets)** and **QP1 (general services / the Subnet Administrator)** [F: IBTA `packet.transport.ib`; SMA in every HCA/switch — NVIDIA security docs]. The canonical implementations are **OpenSM** (the reference, OpenFabrics, ships in MLNX_OFED/DOCA) and **NVIDIA UFM** (its enterprise platform). Only one SM is **master** per subnet; **standby SMs** take over on failure. **No SM → no fabric comes up at all**, because LIDs, LFTs, and partition/QoS state simply don't exist until one runs.

## What
Two management entities, five jobs [F: https://networking-docs.nvidia.com/nvidiainfinibandsecurityoverviewandguidelines/security-in-infiniband, https://manpages.ubuntu.com/manpages/focal/man8/opensm.8.html]:

| Entity | Role |
|---|---|
| **SM (Subnet Manager)** | discovers, assigns LIDs, computes + programs routes (LFTs), configures QoS & partitions, monitors, owns master/standby election |
| **SA (Subnet Administrator)** | responds to **path-record / path queries** from clients (OpenSM hosts the SA; UFM exposes it); returns the best SL/MTU/rate/lifetime for a requested path |
| **SMA (Subnet Manager Agent)** | a small agent **in every HCA and switch** that answers the SM's discovery MADs/management queries |
| **MAD (Management Datagram)** | the management message (SMP = subnet-management packets on QP0; GMP/general services on QP1) |
| **QP0 / QP1** | the two well-known management QPs every IB node must support: QP0 for SMPs, QP1 for GSI/general management (SA path records, etc.) [F: IBTA] |

### OpenSM vs NVIDIA UFM
| | OpenSM | NVIDIA UFM (Unified Fabric Manager) |
|---|---|---|
| Lineage | **OpenFabrics** OFED reference, open source; NVIDIA ships it in MLNX_OFED/DOCA [F: OpenSM manpage / NVIDIA OpenSM doc] | NVIDIA enterprise plugin-on-SM platform + telemetry/monitoring/automation [F: UFM docs] |
| Core SM | full subnet management, LID assignment, routing, partition, QoS | embeds an enterprise SM with the same duties, plus GUI/REST, monitoring, health, per-device licensing |
| Routing | 10 routing engines (MinHop default …) [F: opensm routing doc] | similar/core SM capabilities, service now common |
| Maturity | reference, scriptable (`opensm -c`, config files), the baseline AI/HPC choice | much richer day-2 ops (telemetry, dashboards, anomaly) |

For AI fabrics both get used: OpenSM is the default/self-managed path; UFM is where you need visibility + automation at scale [I].

## Why
A switch is a **stateless LID forwarder** — it has no idea how the fabric is wired until told. Someone must (a) learn the topology, (b) pick globally-unique LIDs, (c) inject the LFT so every LID maps to the right egress port, and (d) sync QoS/partition policy everywhere. Do that in one authoritative process and you get a *consistent* forwarding/QoS/P_Key view; do it in leaves independently and you get conflicts (duplicate LIDs, loops, P_Key mismatches). The SM is that single point of truth [I]. "No SM = no fabric" follows: before an SM runs, ports have **no LID**, switches have **no LFT**, and packets have **nowhere to route** — a freshly cabled cluster will not pass data until `opensm`/UFM brings it up [F: NVIDIA security docs].

## How — discovery via MAD over SMP
The SM walks the fabric using **Subnet Management Packets (SMPs) over QP0**. It sends a management MAD to the SMAs in each device: first to the known root switch, which answers with its port map and its neighbors; then to each neighbor to fan out. Each device also reports its GUIDs, LID, port state, and capabilities. This produces the topology graph the SM turns into LIDs and routes [F: IBTA / NVIDIA security docs].

```text
  Fabric initialization (vertical)
  ┌──────────────────────────────────────────────────────────────┐
  │ 1 DISCOVER   SM ──SMP/QP0──► switch1 ──► … ──► every HCA/SW │
  │              every SMA answers: GUID, port map, neighbors    │
  │ 2 LIDS       SM assigns 16-bit LID to each active port       │
  │              (LMC>0 → block of 2^LMC LIDs for multipathing)   │
  │ 3 ROUTES     SM runs a routing engine → per-port LIDs/path    │
  │ 4 LFT        SM programs each switch's Forwarding Table       │
  │ 5 QOS        SM programs SL2VL, arbitration, MTU/rate/lifetime│
  │ 6 P_KEY      SM enforces partitions on switch ports           │
  │ 7 ACTIVE     ports → ACTIVE; clients query SA path records    │
  └──────────────────────────────────────────────────────────────┘
        (One master SM owns this; standbys shadow and take over.)
```

### LID assignment
Every active port gets a 16-bit LID; OpenSM **preserves existing LIDs** across restarts unless told otherwise (`-r/--reassign_lids`) [F: OpenSM manpage]. With **LMC > 0**, a port gets a contiguous block of 2^LMC LIDs (multi-pathing). Details in [07-infiniband-addressing.md](./07-infiniband-addressing.md).

### Forwarding-table programming
The SM computes, per switch, an **LFT** mapping (dest LID → egress port/route), and pushes it into each switch [F: OpenSM manpage]. Choice of **routing engine** decides those routes — critical for AI because a bad route choice can create credit-deadlock loops or unbalanced fat-tree utilization [I]. OpenSM offers 10 engines [F: https://github.com/linux-rdma/opensm/blob/master/doc/current-routing.txt]:

| Engine | Behavior | Fit |
|---|---|---|
| **MinHop** (default) | fewest hops, ignores credit deadlock | general networks |
| **UPDN** | up*/down* ranking, deadlock-avoidance | generic safe default |
| **DNUP** | down-up variant | generic |
| **Fat-tree** | credit-loop-free for symmetric fat-trees; ideal for AI | AI fat-tree fabrics |
| **LASH** | SL-based shortest, deadlock-free | torus/modular |
| **DOR**, **Torus-2QoS** | dimension-order / torus w/ QoS | torus topologies |
| **DFSSSP** | deadlock-free single-source shortest path | general |
| **SSSP** | single-source shortest path | general |

For a symmetric AI fat-tree, **Fat-tree** routing (or a rail-optimized variant) is the one to pick; MinHop can underbalance the spines [I].

### QoS & P_Key programming, and the SA
The SM also pushes the **SL2VL** tables and **arbitration weights** onto every switch ([10-infiniband-flow-control-and-qos.md](./10-infiniband-flow-control-and-qos.md)), and enforces **P_Key partitions** at switch ports — only packets whose P_Key the port's member partitions allow are forwarded [F: NVIDIA security docs]. Clients then ask the **SA** (QP1) for a **path record** — "give me SL/MTU/rate for dest LID L" — and use that to configure their QPs. Inconsistency between partition membership and switch enforcement is the classic "can reach SM, not each other" failure [F].

### Primary/standby SM + failover
Only **one master SM** runs per subnet. Other SM instances are **standbys**: they monitor the master (Master-Slave election), keep state, and **take over** on failure. OpenSM and UFM both support primary/standby; MLNX-OS exposes native SM HA [F: https://docs.nvidia.com/networking/display/MLNXOSv3111014/Subnet+Manager+High+Availability]. On takeover the fabric must be re-`DISCOVER`ed/reprogrammed; a stale standby that kept different LIDs can momentarily misdeliver — keep standbys' view synchronized [I].

## When
You need the SM **every time** the fabric starts or its topology changes: power-on, cable moves, switch/HCA replacement, partition or QoS changes, failover. You do *not* need it in the steady-state data path — once LIDs/LFTs/QoS are programmed, packets flow without the SM being consulted (the SM is control plane, not in the data path) [I]. Practically: run `opensm` (or UFM) as a service, plus ≥1 standby, and restart it via the choreographer on any physical change.

## GPU relationship
NCCL does **not** route; it asks the **SA** for a path record between GPU host LIDs and then builds QPs on whatever SL/MTU/rate the SA returns [F: NCCL interacts with verbs/SM-provided SA]. So the SM's routing-engine and QoS decisions *are* the collective's tail latency: a wrongly-routed or under-arbitrated SL shows up as AllReduce hot spots rather than a "link down" [I]. Partition/P_Key membership controls which GPUs can even see each other — a security/isolation feature an AI cluster relies on for tenant separation ([12-infiniband-routing-topology-partitions.md](./12-infiniband-routing-topology-partitions.md)).

## Tuning
- **Routing engine:** pick Fat-tree for symmetric AI fat-trees; don't leave MinHop default on a rail-optimized fabric if you want balanced spines [I].
- **SM redundancy:** run primary + synchronised standby; verify the standby's LID map matches so takeover doesn't strand connections [F: MLNX-OS SM HA].
- **LMC only if you need multi-path LIDs;** otherwise keep 0 to avoid complicating the LFT [I].
- **Partition policy first:** define admin partitions before enabling switch enforcement to avoid a silent-isolation outage [F: NVIDIA security docs].
- **`-r` discipline:** OpenSM's `-r/--reassign_lids` advertises LID churn; avoid during production, it re-issues everything [F: OpenSM manpage].

## Troubleshooting
- **No SM, fabric down** — ports stuck in `INIT` (no LID, never ACTIVE); start/verify the SM [F: NVIDIA security docs].
- **Duplicate GUIDs** — SM discovery/routing breaks; fix by flashing distinct GUIDs; `ibdiagnet` flags them [A].
- **P_Key mismatch** — endpoints can reach SM but not each other; check membership & switch enforcement consistency [F: NVIDIA security docs].
- **Master/standby split-brain or stale takeover** — two SMAs fighting or stale LID map → misdelivery; keep standbys synchronised and one authoritative master [I].
- **Bad route / credit loop** — wrong engine on a fat-tree → unbalanced spines or (worst case) credit-deadlock stalls; re-run with Fat-tree/UPDN [I].
- **SA path record wrong** — client picks bad SL/MTU/rate; confirm returned path with the QoS policy [F: DOCA QoS].

## Comparison — control plane: IB SM vs Ethernet
| | IB Subnet Manager | Ethernet (no SM) |
|---|---|---|
| Who learns topology | SM (SMA agents, SMP/QP0) | switch-to-switch LLDP + STP/IS-IS; in AI fabrics a controller (e.g. a PFC/ECN policy manager) overlays the data plane |
| Addressing | SM-assigned LIDs | auto-negotiated MAC/IP (DHCP/LLDP) |
| Forwarding tables | SM programs LFTs centrally | distributed routing protocols |
| QoS | SM pushes SL2VL/arbitration | PFC/DCB/ETS, ECN config |
| Isolation | P_Key partitions, SM-enforced | VLANs/ACLs |
| Failure of control | **fabric never comes up** | data path mostly survives control loss |
| Reference impl | OpenSM / UFM | kernel / vendor NOS |

The IB design trades autonomous self-configuration for **strong central consistency**: one authority guarantees no duplicate LIDs, no loops, consistent partitions — at the cost of being a single point of bring-up [I].

## Lab
Spin up a reference SM and watch it work:
```text
$ opensm -c /tmp/osm.conf && opensm -F /tmp/osm.conf   # generate config, run
$ ibnetdiscover        # dump the topology the SM discovered
$ ibswitches / ibhosts # list discovered switches/hosts w/ LID+GUID
$ ibdiagnet -l /tmp    # full fabric audit: LIDs, LFT, partitions, BER test
$ opensm --engines ... # choose a routing engine (Fat-tree etc.)
```
`ibnetdiscover` + `ibdiagnet` are the fastest ground-truth for "did the SM bring it up and route it sensibly" [F: standard OpenFabrics tools].

## Partition (P_Key) enforcement — the SM's isolation lever
Beyond routing, the SM is what makes an InfiniBand fabric *isolatable*. Every port belongs to a partition (member of one or more P_Keys); the **default partition 0x7FFF** must contain every node, with the **SM a full member** and clients generally **limited members** (on the default
partition they can receive from full members; limited→limited sends are restricted) [F: IBTA;
NVIDIA security docs]. Admin tenants use P_Keys 0x0001–0x7FFE. Enforcement happens in two places the SM programs [F]:
1. **At the QP/HCA:** every packet's BTH carries a P_Key; the receiver validates full-vs-limited membership + index.
2. **At the switch port:** the SM can enforce that only packets whose P_Key the port's member partitions allow are **forwarded** — the primary mechanism for keeping two AI tenants on one physical fabric from talking [F: NVIDIA security docs].
Failure mode baked in: if switch enforcement is enabled but the neighbor HCA's partition attributes disagree, traffic **silently fails** — nodes see the fabric (SM up) but not each other. This is the #1 "SM says up, apps can't connect" root cause, detailed in [12-infiniband-routing-topology-partitions.md](./12-infiniband-routing-topology-partitions.md) and [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md).

## Choosing a routing engine — a decision walkthrough
OpenSM's engine choice *is* a load-balancing + deadlock-avoidance decision [F: https://github.com/linux-rdma/opensm/blob/master/doc/current-routing.txt]:
```text
  Is the fabric a symmetric fat-tree (the AI case)?
    yes ──► Fat-tree routing (credit-loop-free, balanced spines)
    no  ──► Is it a torus? ──► DOR / Torus-2QoS
          └─► generic mesh: UPDN (deadlock-safe) or MinHop (default) /
              DFSSSP / LASH
```
Rule of thumb [I]: on the canonical AI fat-tree (see [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md)) pick **Fat-tree** and check spine utilization after wiring; MinHop-underbalance on a rail-optimized design is a common silent-capacity mistake. Changing the engine on a live fabric forces a re-route — re-run discovery/LFT programming and expect churn; OpenSM's `-r` reassigns LIDs too [F: OpenSM manpage].

## Failover walkthrough — primary → standby
The SM does not need to be a special box; it runs as software on any host/switch, reached over the management path/in-band [I]. HA model [F: MLNX-OS SM HA; OpenSM primary/secondary with election]:
```text
  healthy:  master SM programs LFT/QoS/P_Key; standby(s) idle & synced
  master dies ──► standby detects via timeout/heartbeat ──► election
  new master takes over ──► re-DISCOVER ──► re-issue LIDs (preserve if possible)
       ──► re-compute routes ──► re-program switch LFTs/QoS ──► ACTIVE again
  Risk: a stale standby with a different LID map misdelivers during takeover;
  keep standbys' state synchronized (UFM/MLNX features) and ONE master authoritative.
  [I / F: SM HA]
```
Operational takeaway: single-SM clusters cannot re-initialize/reconfigure when it dies — the fabric doesn't *drop* mid-flight traffic immediately, but any new QP, cable move, or failover-dependent route requires the SM, and stale state can misdeliver [I; SM pain points `./45-...`]. For AI, run primary + ≥1 synchronized standby as a service the orchestrator restarts.

## Why "no SM = no fabric" — the honest statement
The strongest version is also the simplest to test: bootfully-cabled cluster with **no SM running** leaves every port in `INIT`/`DOWN` — no LID, no LFT, no route, no partition — so not a single data packet crosses it [F: NVIDIA security docs]. This is intentional. The IB design trades Ethernet's autonomous auto-config for **a single authoritative control process** that guarantees no duplicate LIDs, no forwarding loops, and consistent partitioning — at the cost of making that process load-bearing. It is the one component in an AI fabric you cannot "run without."

## Lab — bring-up and audit commands
```text
$ opensm -c /tmp/osm.conf && opensm -F /tmp/osm.conf &   # run a reference SM
$ ibnetdiscover     # topology the SM discovered (GUIDs, ports, LIDs)
$ ibswitches        # switches: SM port, LID, GUID
$ ibhosts           # hosts: LID, GUID, part
$ ibdiagnet -l /tmp # audit: routes, partitions, BER test, QoS
$ ibstat            # local HCA state — see ports go DOWN→INIT→ACTIVE as SM runs
```
The ritual that proves "SM did its job": watch `ibstat` on a host flip from `INIT` to `ACTIVE` the moment `opensm` starts, then `ibdiagnet` shows sane LFT/partition state [F: standard OpenFabrics tooling].

## Key Takeaways
1. **The SM is a single authoritative control plane**: it discovers every HCA/switch (SMPs over QP0), assigns LIDs, computes routes, and programs each switch's forwarding table (LFT), plus QoS (SL2VL/arbitration) and P_Key partitions [F].
2. **"No SM = no fabric"**: before an SM runs, ports have no LID and sit in `INIT`, switches have no LFT, so a freshly cabled cluster passes zero data until OpenSM/UFM brings it up [F].
3. **Discovery rides MADs on two management QPs**: QP0 carries subnet-management packets (SMP) to the SMA agent in every device; clients ask the **SA on QP1** for path records (SL/MTU/rate) to configure their QPs [F: IBTA].
4. **Choose the routing engine deliberately**: on a symmetric AI fat-tree use **Fat-tree** routing (credit-loop-free, balanced spines); leaving **MinHop** (the default) on a rail-optimized fabric underbalances spines and silently caps capacity [I].
5. **Primary/standby failover**: only one master SM runs per subnet; synchronized standbys take over on failure by re-discovering and re-programming LFTs/QoS/P_Keys — keep their LID maps in sync or takeover misdelivers [F: SM HA].

## Related
- [07-infiniband-addressing.md](./07-infiniband-addressing.md) — the LID/GUID/GID the SM assigns and programs.
- [09-infiniband-packet-format.md](./09-infiniband-packet-format.md) — P_Key in the BTH the SM enforces.
- [10-infiniband-flow-control-and-qos.md](./10-infiniband-flow-control-and-qos.md) — the SL2VL/arbitration QoS the SM programs.
- [12-infiniband-routing-topology-partitions.md](./12-infiniband-routing-topology-partitions.md) — routing engines and partition enforcement.
- [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md) — duplicate GUID, P_Key, SM-failover debugging.
- [55-cheat-sheet.md](./55-cheat-sheet.md) — `opensm`/`ibdiagnet` quick reference.
- [README.md](../GPU-Communication/README.md) — what NCCL consumes from the SA path record.

## References
- OpenSM manpage: https://manpages.ubuntu.com/manpages/focal/man8/opensm.8.html · MLNX_OFED OpenSM: https://docs.nvidia.com/networking/display/mlnxofedv585112lts/OpenSM
- OpenSM routing engines: https://github.com/linux-rdma/opensm/blob/master/doc/current-routing.txt
- NVIDIA UFM SM tab / defaults: https://networking-docs.nvidia.com/ufmenterprisearum/61915/subnet-manager-tab · https://docs.nvidia.com/networking/display/ufmenterpriseumv6180/Appendix+%E2%80%93+UFM+Subnet+Manager+Default+Properties
- SM HA (MLNX-OS): https://docs.nvidia.com/networking/display/MLNXOSv3111014/Subnet+Manager+High+Availability
- IB security / SM / P_Key / node types: https://networking-docs.nvidia.com/nvidiainfinibandsecurityoverviewandguidelines/security-in-infiniband
- IB QoS / SA path records (DOCA): https://networking-docs.nvidia.com/doca/archive/3-4-0/infiniband-qos
- IBTA manpage (QP0/QP1, MAD): https://manpages.ubuntu.com/manpages/noble/man3/packet.transport.ib.3.html
