# Troubleshooting RDMA & InfiniBand Fabrics
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: NVIDIA InfiniBand security/ops docs, MLNX_OFED/OpenSM manpages, ibdiagnet manual, DGX SuperPOD design guide; fetched 2026-08-25.

## 30-Second Explanation
An InfiniBand fabric is *lossless by construction* — credit-based flow control means a packet is
only sent when the receiver has buffer to accept it, so across the whole fabric there are
essentially no congestion drops and only one deliberate drop path (the Head-of-Queue timeout, an
SM-configured deadlock guard) [F: enterprise-support.nvidia.com credit-loops article]. That changes
how you troubleshoot: because the data plane almost never drops, most IB problems show up as
**link/PHY errors**, **SM (control-plane) problems**, or **QoS/P_Key misconfiguration** — not as
ordinary "congestion loss". The workflow is always: (1) is the link up and at the right speed?
(2) are the port counters clean? (3) is the control plane coherent (SM, partitions, routing)?
(4) only then congestion. This page gives that decision process, the counter family, the common
faults, and a command cheat sheet.

## The decision tree (vertical)
```text
SYMPTOM: collectives slow / retries / link flaps / "got completion with error"

 1. LINK UP? ................. ibstat / ibstatus / iblinkinfo
    ├─ Port state != Active, Phys state != LinkUp
    │     → link-down fault: cage, cable/DAC, or SM not managing  [see: link down]
    └─ Active/LinkUp → next

 2. RIGHT SPEED? ............. ibstat "Rate:" / ibstatus "Rate:"
    ├─ 4xNDR shows as 200 or 400? (HDR100 vs HDR vs NDR mixing)
    │     → wrong-speed fault: auto-negotiation limits, FEC mismatch [see: wrong speed]
    └─ Expected rate → next

 3. COUNTERS CLEAN? .......... ibqueryerrors / perfquery / ibdiagnet -r
    ├─ symbol_error, link_error_recovery, link_downed, rcv/xxmit errors ↑
    │     → degraded-link fault: BER / FEC / reseat  [see: degraded link]
    └─ clean → next

 4. GPUDIRECT / HOST PATH? ... nvidia-smi topo -m ; perftest vs nccl-tests
    ├─ ib_write_bw host >> GPU, "Peer to peer not allowed"
    │     → host-side fault: IOMMU/ACS, nvidia-peermem, NUMA  [cross-ref ./46]
    └─ OK → next

 5. PFC/ECN (RoCE only) ...... ethtool -S | pfc_xon/xoff, np_cnp_sent
    ├─ pause/CNP counters rising → lossless-rate problem  [cross-ref ./46]
    └─ n/a for native IB → next

 6. CONGESTION? .............. ibdiagnet ; UFM congestion report
    ├─ hot spots / queue depth at spines  → congestion fault [see: hot spots]
    └─ clean → next

 7. TOPOLOGY / ROUTING ....... ibnetdiscover ; opensm -e (routing engine)
    ├─ adaptive routing on the right SL? NCCL_IB_ADAPTIVE_ROUTING + NCCL_IB_SL
    ├─ fat-tree engine vs min-hop (credit loops at scale!)
    └─ VL stall / credit starvation → SM QoS misconfig  [see: VL stall]
```
[I] The order matters: an SM fault can *cause* a "link down" on some ports and a wrong-speed fault
on others, so a single SM outage masquerades as several distinct symptoms. Fix the control plane
first, re-check the ports, then the data plane. Re-run the tree *after* each remediation — the most
common mistake is treating the "link down" symptom instead of the SM root cause that produced it.

### Reading hardware state (worked example)
`ibstat mlx5_0` output snippet and what to learn from it [F: finestrat tooling, output fields [I]]:
```text
State: Active                                     ← LID path is up (forwarded by SM)
Physical state: LinkUp                            ← PHY trained (cable/optics OK)
Rate: 200                                          ← 4x HDR200 nominal (Gb/s)
Link layer: InfiniBand
```
If `State` is `Down`/`Initializing` while `Physical State` is `LinkUp`, the SM has not yet
assigned a LID/forwarded this port — a *control-plane* fault, not a cable. If `Physical State` is
`Polling`, the PHY is still training (check media). Match `Rate:` against the sibling ports to catch
a silent half-rate negotiation before it ever reaches a workload.

## The counter family (what each one means)
IB port counters are exposed by `perfquery` / `ibqueryerrors` / `ibdiagnet -r`. The ones that
matter, and what each rising value tells you [F: NVIDIA mlx5 counters article / research-notes
counter set; behavior [I]]:

| Counter | Meaning | Rising = |
|---|---|---|
| `symbol_error` | physical-layer lane errors (bad signal) | bad cable / fiber / connector |
| `link_error_recovery` | port-training recovery events | marginal/unstable link |
| `link_downed` | port actually trained down | hard link failure or flap |
| `local_link_integrity_errors` | bad signal on the local receive side | bent fiber / dirty optic |
| `remote_physical_errors` | bad signal the far end saw from you | your TX side / cable |
| `rcv_errors` / `xxmit_errors` | receive/transmit framing errors | degraded link at speed |
| `vl15_dropped` | VL15 (SM/management) frames dropped | SM congestion / loop, control-plane problem |
| HOQ / credit timeout drops | Head-of-Queue timeouts (the one deliberate IB drop) | deadlock guard fired, credit starvation |
| `packet_seq_err` (NIC) | out-of-order / retransmit at the transport | adaptive-routing reorder or real loss |

[I] Rule of thumb: a single `symbol_error` is noise; rising, sticky error counters on one link are
the signal. `vl15_dropped` is special — VL15 carries only subnet-management traffic, so a rising
VL15 drop counter points at the **control plane**, not the data plane. `link_downed` plus an SM that
does not come back cleanly usually means the SM, not the cable.

Also worth knowing which counters are **not** authoritative: transport retransmit/out-of-sequence
counters (`packet_seq_err`, "Got completion with error") live on the *NIC*, not the switch, and are
the ones you see in a job log; switch-side physical counters are what you must query with
`ibqueryerrors`/`ibdiagnet`. Read both layers, because each answers a different question.

## Specific faults
### Link down (cage / DAC / SM)
**What:** port stuck in `Down`/`Polling`, or cycling `LinkDownedCounter` up.
**Why:** (a) dead optical/DAC, (b) seated in the wrong/loose cage, (c) port not enabled by the SM
(partition/enforcement), (d) SM itself down so nothing brings the fabric up.
**How to validate:** `ibstatus` (port state), `ibnetdiscover` (does the SM even see the HCA?),
reseat confirmed by a clean counters reset after reseat [I].
**Fix:** reseat/replace media; confirm in a valid cage; verify SM discovers and enables the port
[F: MLNX_OFED OpenSM]. Remember: **without an SM the fabric will not come up** [F: NVIDIA IB
security doc] — if many unrelated ports are Down simultaneously, interrogate the SM/HA first.

### Wrong speed (auto-negotiation / FEC mismatch)
**What:** HDR100 shows 100 while siblings show 200; NDR appears at half rate.
**Why:** IB auto-negotiation across generations is limited (HDR100 vs HDR200 vs NDR must be
explicitly cabled/configured) [F: NVIDIA DGX SuperPOD widths-rates]; FEC mode mismatch at one end
of a transceiver link downgrades or destabilizes the lane.
**Fix:** set lanes/width and FEC explicitly on both ends; confirm `ibstat Rate:` shows the expected
4xNDR/4xHDR value; match cable reach to the FEC mode (e.g. long-reach PAM4 needs RS-FEC) [A]. A
half-rate link that "looks up" is the most common silent throughput drain — always compare `Rate:`
across the rail before blaming the workload.

### Degraded link (BER / FEC / reseat)
**What:** occasional retries, rising `symbol_error`, throughput below the perftest single-QP ceiling.
**Why:** rising bit-error ratio. IB link target ≈ **1 error per 1e12 bits**; NVIDIA-qualified
components are factory-tested to **1e-15** [F: NVIDIA DGX SuperPOD widths-rates]. Even a "lossless"
fabric leaks throughput to retransmission when BER climbs.
**Fix:** reseat (dirty/oxidized contact), re-terminate the fiber, swap media; confirm with a clean
`ibdiagnet` BER test reporting high-BER links [F: ibdiagnet manual]. Trend the counter over an hour,
not a minute — marginal links degrade intermittently.

### VL stall / credit starvation (SM QoS misconfig)
**What:** a workload stalls or crawls on one traffic class while counts stay clean.
**Why:** `SL→VL` mapping or VL arbitration is wrong, so a congested egress withholds credits and
backpressure propagates hop-by-hop to the source HCA — the credit loop the SM exists to avoid
[F: credit-loops article]. Too few VLs allocated, or NCCL's SL mapped to a starved VL [I].
**Fix:** use the SM's **fat-tree routing engine** (credit-loop-free for symmetric fat-trees, ideal
for AI) and verify SL/VL policy maps NCCL traffic to a provisioned VL [F: OpenSM routing doc].
[E] Note: the fat-tree engine is only correct on a symmetric fat-tree; on an asymmetric mesh it is
the wrong engine. Check `NCCL_IB_SL` matches the SL the fabric designated for AR/QoS traffic.

### SM failure (fabric down; standby takeover)
**What:** the whole fabric freezes — ports never come `Active`, or previously-usable endpoints stop
talking.
**Why:** one **master** SM per subnet [F: MLNX-OS SM HA]; if it dies and no standby has clean,
synchronized state, LIDs/paths go stale and traffic misdelivers or stops.
**Fix:** run primary + standby SM/UFM with HA; keep state synchronized; test takeover in a
maintenance window [F: UFM SM tab]. Validate `vl15_dropped` is not climbing after a takeover. If
UFM/OpenSM is running but a classifier port won't activate, check partition-enforcement consistency
(see P_Key below) — a control-plane fault often hides behind an apparent SM outage.

### Duplicate GUID (port flap / LID confusion)
**What:** two HCAs share a GUID → SM discovery/routing flips between them; port flaps; unrelated
endpoints lose each other.
**Why:** factory GUIDs get flashed/distributed carelessly (cloned disk images) [I].
**Fix:** flash distinct per-port GUIDs; `ibdiagnet` flags duplicate GUIDs [F: Oracle fabric-diag
doc]. Check after any reimage that GUIDs are unique.

### P_Key failures (partition membership)
**What:** "nodes reach the SM but not each other"; IPoIB broadcast group per partition missing.
**Why:** P_Key is in every BTH; receivers filter on P_Key validity (full vs limited) + index;
**switch-partition enforcement** drops anything whose P_Key the port's member partition does not
allow [F: NVIDIA IB security doc]. A mismatch at enforcement vs HCA membership silently drops
traffic — the fabric "works" (SM reachable) but peers can't talk.
**Fix:** make HCA membership and switch-port enforcement consistent; default partition 0x7FFF must
include all nodes (SM is its full member) [F: NVIDIA IB security doc]. Move tenants to admin
partitions (0x0001–0x7FFE).

### Congestion hot spots (ibdiagnet + UFM)
**What:** perftest/nccl-tests good but collectives collapse; some spine ports saturated.
**Why:** hash/routing hot spot, or an incast (collective) burst hitting one egress — IB's backpressure
then stalls other flows on that VL.
**Fix:** let UFM/ibdiagnet show per-port utilization and hot links; enable **adaptive routing** on the
AR-enabled SL (Quantum HDR/NDR/XDR fabric + HCA support) and route NCCL traffic there via
`NCCL_IB_ADAPTIVE_ROUTING` + `NCCL_IB_SL` [F: NCCL env doc; adaptive-routing whitepaper].
Immediate-data packets cannot be adaptively routed — NCCL tracks this [F: NVIDIA/nccl#1687].

## Command cheat sheet
| Tool | What it does | When to run |
|---|---|---|
| `ibstat` | per-HCA port state, **Rate**, link layer, phys state | always first — link up + speed + BER hint |
| `ibstatus` | condensed HCA health summary | quick triage |
| `iblinkinfo` | table of all port states across the fabric | who is Down / who flapped |
| `ibnetdiscover` | fabric topology + LID/GUID map | does the SM see everything; is topology as wired |
| `perfquery` | per-port performance/error counters, one host | drill a specific port's counters |
| `ibqueryerrors` | error counters across all ports | find the dirty link cluster-wide |
| `ibdiagnet -r` | full-fabric lint: route dump + BER test + cable checks | final pass; congestion/BER report |
| `opensm`/UFM logs | SM events, LID/P_Key/QoS decisions | control-plane faults: SM failover, partitions |

### Reads a typical session runs
```text
iblinkinfo | grep -i down                # every non-active port in one line
ibqueryerrors | grep -v '0 errors'       # only the dirty counters
ibdiagnet -r > /tmp/ibdiagnet.txt        # full lint + route table for the record
ibnetdiscover | head -50                 # is the topology what you wired?
tail -50 /var/log/opensm.log             # SM decisions on the failing object
```

## Related
- [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md) — the Ethernet/RoCE symptom→cause table and NCCL env vars.
- [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) — why the fat-tree routing engine matters at scale.
- [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md) — rail fabrics and AR/SL placement.
- [47-security-multitenancy.md](./47-security-multitenancy.md) — P_Key partitioning, M_Key, Q_Key isolation.
- [17-troubleshooting.md](../GPU-Communication/17-troubleshooting.md) — GPU-side (NCCL/perftest/nvidia-smi topo) triage.


## Key Takeaways
1. IB is lossless by construction — credit-based flow control means a packet is only sent into
   available buffer, so the data plane almost never drops; the single deliberate drop is the
   SM-configured Head-of-Queue timeout, making congestion-loss the *last* suspect, not the first.
2. Work the decision tree in order (link up → right speed → counters clean → host/GPUDirect →
   PFC/ECN → congestion → routing): an SM fault can present as link-down *and* wrong-speed at
   once, so fix the control plane first and re-run the tree after each fix.
3. Read counters by layer: `symbol_error`/`rcv_errors`/link-integrity = degraded link (BER target
   ~1e-12, NVIDIA-qualified ~1e-15); rising `vl15_dropped` flags the control plane, not data;
   retransmit/"completion with error" counters live on the NIC while physical counters live on
   the switch.
4. Route NCCL via the SM's fat-tree routing engine (credit-loop-free on symmetric fat-trees, wrong
   on asymmetric meshes) and adaptive routing on the AR-enabled SL; an SL→VL/VL-arbitration
   misconfig causes credit starvation and VL stalls that masquerade as congestion.
5. Two silent killers after bring-up/reimage: a half-rate link that still shows Active (match
   `ibstat Rate:` across the rail) and P_Key/GUID problems — duplicate GUIDs or
   enforcement-vs-HCA membership mismatch make the fabric "work" (SM reachable) while peers can't
   talk.

## References
- NVIDIA InfiniBand security/operations documentation — partition enforcement, "no SM, no fabric."
- MLNX_OFED / OpenSM manpages and routing docs — fat-tree routing engine, SL/VL policy.
- `ibdiagnet` manual and Oracle fabric-diagnostics doc — BER test, duplicate-GUID detection.
- NVIDIA DGX SuperPOD widths-rates doc — lane/FEC configuration, BER 1e-12 vs 1e-15 targets.
- NVIDIA credit-loops article (enterprise-support.nvidia.com) — the Head-of-Queue deliberate-drop path.
- NCCL environment-variables doc; NVIDIA/nccl#1687 — adaptive routing + immediate-data caveat.
