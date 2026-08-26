# The Reference Lossless RoCEv2 Fabric Design
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: IETF Fast-CNP draft (RoCEv2), IEEE 802.1Qbb (PFC) / 802.1Qaz
(ETS), NVIDIA DCQCN/lossless config, Juniper DCQCN buffer-partition example, Meta
SIGCOMM'24 (no-DCQCN case); fetched 2026-08-25. This is a *reference design* —
wire/buffer/MTU arithmetic is [E] from the section constants bank; vendor defaults
are `[F: vendor spec]`.

## 30-Second Explanation
This page is the complete, end-to-end recipe for a **lossless RoCEv2 AI fabric**:
an L3 leaf-spine with BGP+ECMP, jumbo **9k MTU** to cut per-packet overhead, a
**two-traffic-class DSCP scheme** (one for RoCE data, one for CNP control), **PFC
on exactly one priority** (not eight — you want losslessness on the RoCE class and
nothing else), **ECN/WRED thresholds set *below* the PFC XOFF point** so the
NIC-based CC (DCQCN) slows senders end-to-end while PFC only ever backstops, and
buffer partitions whose **headroom is sized to absorb a measurable amount of
pause-latency** (e.g. ~50 KB per 400G port per 1 µs). Layered on that is link
design (400G/800G, DAC vs AOC by reach), rail-optimized rack mapping, a NIC
checklist, and a final design checklist table. **The one idea to take away:** the
whole system is a *threshold hierarchy* — ECN marks first, PFC pauses only as a
last resort, and the buffers in between are sized by arithmetic, not guesswork. See
[42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) for how many leaves/spines you need.

## The threshold hierarchy (read this first)
```text
   LOW buffer occupancy                     HIGH buffer occupancy
   |--- ECN K-min --------------- ECN K-max -------- PFC XOFF -------- XON ----|
   |<-- WRED marks CE (prob ramps) -->|<--pause frame fills headroom-->|
   |<------- the "spend life on DCQCN" zone -------->|<-- PFC backstop zone -->|
   ECN marks FIRST so the sender throttles end-to-end (slow, safe);
   PFC only fires when ECN hasn't caught up, and only on ONE priority.   [I]
```
The design goal: **you should see mostly ECN/CNP, rarely PFC XOFF.** If PFC is
constantly firing, the ECN and PFC thresholds are misaligned — the single most
common RoCEv2 misconfig and the root of pause storms. **[I/E:]** Verify by watching
`pfc_xoff_rx` vs the ECN counters — if XOFF dominates, re-tune §5 before touching
anything else.

## 1. Topology: L3 leaf-spine with BGP/ECMP
### What
A two-tier Clos: **leaf** (ToR) switches hold the hosts, **spines** interconnect
the leaves. Routing is **L3 (IP) + BGP**; flow distribution is **ECMP** over
equal-cost paths. This is exactly the design in [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md).
### Why
RoCEv2 rides inside UDP/IP, so it is **routable** — you get multipath (ECMP),
per-tenant isolation, and no L2 broadcast-domain growth. PFC still runs, but only
within the lossless traffic class per link. (If you only need one rack, an
L2/VLAN design works, but it does not scale and brings no ECMP — the AI case is
always multi-rack leaf-spine.)
### How
```text
  leaf uplinks -> 2+ spines (ECMP next-hops)
  each RoCEv2 flow hashed to ONE spine by ECMP   (entropy problem -> ./22-roce-cc-and-load-balancing.md)
  BGP carries the loopbacks/underlay; jumbo MTU on every RoCE port  [F/I]
```
**Failure modes:** ECMP polarization (page 22); BGP/MTU mismatch dropping jumbo
packets silently. Measure: per-uplink utilization — one spine saturated with others
idle = hashing problem, not capacity.

### When (is lossless even required?)
**Semantics caveat [I]:** if your workload tolerates drops (UET, or IRN-style
reordering NICs), a lossy fabric is cheaper to build. This page is the **lossless**
reference for stock RoCEv2 RC, which does *not* tolerate loss well (Go-Back-N).
Choose lossless if you run stock RoCE RC; consider lossy if you move to UET or
spraying-with-NIC-reorder endpoints. **[A]**

## 2. Jumbo MTU: 9000 (and 9216/8942)
### What
Run **MTU 9000** on every RoCE-facing port; many vendor configs use **9216** (the
full 9kB-plus-overhead frame), giving ~**8942 B of payload** after the 58 B
RoCEv2/IPv4/UDP/BTH/ICRC headers. **[F: vendor refs — NVIDIA uses 9000, min.io 9216]**
### Why — the [E] math
| Payload | RoCEv2 overhead | Note |
|---|---|---|
| 256 B | **22.66 %** [E] | 58/256 — bad |
| 1500 B | 3.87 % [E] | 58/1500 — standard frame tax |
| 4096 B | 1.42 % [E] | 58/4096 |
| 8942 B | **0.65 %** [E] | 58/8942 — the jumbo win |
Jumbo cuts per-packet overhead **and** the PPS demand on switches/NICs (fewer
descriptors): at 400GbE, **5.54 Mpps @ 9018B frame vs 32.94 Mpps @ 1518B** [E:
constants bank]. Fewer, bigger packets = less per-packet work everywhere, fewer
interrupt/descriptor costs, and better CC granularity.
### How
Set `mtu 9000` (or 9216) consistently on **every** leaf/spine uplink and host NIC;
a single mismatch causes `Invalid MTU` QP failures / silent drops. **[I]**
### Failure modes
Mixed MTU across a path; jumbo on the NIC but not the switch (or vice-versa);
VXLAN/overlay carrying a 9000 payload needs +50 B of headroom (RFC-6040-style ECN
is preserved, but frame size is not — you need a 9050 MTU under overlay). **[I]**

## 3. DSCP scheme: two traffic classes
### What
Classify RoCE by **DSCP** into two traffic classes: **TC for RoCE data** and **TC
for CNP control**. On Mellanox the default is **RoCE DSCP 26 (AF31) → switch
priority 3**; **CNP DSCP 48 → priority 6**. **[F: NVIDIA/mlnx_qos, widely
reproduced]**
### Why
ECN marking is per-queue/DSCP, PFC is per-priority, and CNPs get their own DSCP so
they never queue behind data. Aligning DSCP on host *and* switch is a
**prerequisite** for DCQCN+PFC to function at all. **[I]**
### How
```text
RoCE data: DSCP 26 -> priority 3 -> PFC-enabled lossless queue
CNP       : DSCP 48 -> priority 6 -> strict-high (never paused)
mgmt/other: lossy best-effort
tune with: mlnx_qos --dscp2prio set,26,3       [F: mlnx_qos]
```
### DCB / DCBX / ETS — the negotiation behind DSCP `[A]`
The RoCE QoS stack is DCB = **PFC (802.1Qbb)** + **ETS (802.1Qaz)** + **DCBX**
(802.1Qaz's exchange protocol) negotiating per-priority params between NIC and
switch. **Corrections worth knowing [A]:** ETS is **802.1Qaz** (some NIC spec
sheets wrongly list it under Qau); **802.1Qau is QCN**; PFC is 802.1Qbb. If the NIC
and switch do not agree on DSCP→PCP→priority via DCBX, the lossless mapping
silently diverges. **[I]**
### Failure modes
DSCP-on-host ≠ DSCP-on-switch → traffic silently classified lossy → drops under
incast; CNP sharing the data queue → feedback starvation. **[I]**

## 4. PFC on exactly one priority
### What
**PFC (IEEE 802.1Qbb)** is per-priority pause — an XOFF frame stops *one* of the 8
priorities on a link, not the whole link. **[A/F]** The design uses **PFC on exactly
one priority** — the RoCE data priority (3) — and leaves everything else lossy.
### Why
Scope PFC tightly: per-priority pause is what prevents **head-of-line (HOL)
blocking** of unrelated traffic, but **over-enabling** PFC (pausing many
priorities, or the control class) creates circular-pause **deadlocks** and
victimizes non-RoCE traffic. One PFC priority + one no-drop queue is the safe
default. **[A/F]**
### How / buffer sizing — [E]
The lossless queue needs a buffer partition sized to absorb the **pause
propagation latency** (the round-trip time for the XOFF to reach the sender and the
sender to stop). The constants: **PFC threshold ≈ (link rate in B/ns) × (1 µs)**:
**[E: constants bank]**
```text
 100 Gb/s (12.5 GB/s):  pause latency 1 us  -> headroom ~ 12.5 KB   [E]
 400 Gb/s (50  GB/s):  pause latency 1 us  -> headroom ~ 50  KB   [E]
 800 Gb/s (100 GB/s):  pause latency 1 us  -> headroom ~ 100 KB   [E: 800/8 = 100 GB/s]
```
XON should resume below XOFF (hysteresis) to avoid oscillation; XON == XOFF causes
flapping. **[F: vendor guidance]**
### Deadlock avoidance `[I]`
Credit/pause loops can deadlock a lossless fabric (a pause cycle where nobody
progresses). Mitigate with **PFC Watchdog** (detects a stuck no-drop queue and
drops/isolates the offender) and, on some vendors, careful per-priority pause
spread. **PFC Watchdog is a vendor/switchdev feature, NOT an IEEE standard** —
`pfc watchdog` in Linux switchdev, per-vendor on ASICs. **[A/F]**
### Failure modes
PFC on the wrong priority (lossless where you meant lossy, or RoCE mapped to a
non-PFC priority) → drops under burst; **pause storms** from ECN/PFC threshold
misalignment; single lost XOFF breaks losslessness transiently. **[I]**

## 5. ECN / WRED thresholds below PFC XOFF
### What
The switch marks **ECN-CE** on RoCE packets whose queue crosses **K-min**, ramping
marking probability linearly to **P-max at K-max** (a WRED curve), for the
ECN-capable DSCP class only. This is *separate from, and below*, the PFC XOFF
threshold. **[A/F]**
### Why
ECN must fire **before** the queue reaches PFC XOFF so DCQCN slows the sender
end-to-end and PFC stays a rare backstop. **If K-max ≥ PFC XOFF, ECN never fires
before pause → pause storms.** **[I/E:]** This ordering *is* the design.
### How — a concrete example (illustrative [I], not a verbatim command)
```text
per-lossless-queue WRED mark curve, e.g. [F: Juniper interpolate example, adapted]:
  K-min = 55% of queue, P-max at K-max = 90% of queue   (e.g. fill [55 90], drop-prob [0 100])
  PFC XOFF = ABOVE the 90% mark (headroom to absorb the pause itself)
  => ECN marks from 55%..90%; PFC only past ~90%.
Align ECN-safe queue depth << PFC XOFF; enable ECN on the scheduler/Tx queue.  [F/I]
```
### Failure modes
K-min too low → premature throttling (bandwidth left on the table); K-max ≥ XOFF →
ECN never beats PFC → constant pause; ECN not applied to the right DSCP → no
feedback at all; WRED drop-probability curve too steep → ECN marks nearly every
packet and collapses end-to-end rate ("DCQCN over-reacting"). **[I]**

## 6. Buffer partitioning
### What
Carve the switch buffering into named pools: **lossless (RoCE), lossless-headroom**
(for the pause absorption), and **lossy** (CNP/mgmt/best-effort). A representative
split: **lossless 80% / lossless-headroom 10% / lossy 10%** (ingress); egress
similar. **[F: Juniper 802.1Qbb/QoS reference config]**
### How — the [E] sizing recap and a worked example
The **lossless-headroom** pool is the one that must meet the PFC threshold
arithmetic from §4: it is the buffer that guarantees no-drop while a pause
propagates. At 400G, 1 µs of pause latency needs **~50 KB/port** just for headroom
**[E]**; scale by actual cable+Rx latency (more distance = more headroom). The
**lossless** pool is where normal queueing + ECN marking happens (**K-min ≤ K-max ≤
this pool's top**).
```text
WORKED EXAMPLE [E, arithmetic]: a 4096-GPU, 400G single-plane fabric (~64 leaves
x 64 hosts) [A: from ./42-clos-fat-tree-math.md math]. Per lossless leaf port:
  lossless pool      ~ 400 KB (normal queueing + ECN zone)
  lossless-headroom  ~  50 KB + margin ~10 KB  (covers ~1 us pause + margin)
  lossy (CNP/mgmt)   ~  50 KB
  (illustrative totals; actual split is vendor/switch dependent)   [I]
```
### Failure modes
Headroom too small → drops despite PFC; headroom too large → the lossless class
hoards memory and inflates PFC tail; not reserving headroom at all → the classic
*"PFC is on but we still drop"* surprise; CNP pool too small → feedback loss. **[I]**

## 7. Link / cable design (400G, 800G; DAC vs AOC)
### What
Fabric links are **400G (4×100G) or 800G (8×100G)**; the medium is **DAC**
(direct-attach copper) for short reach, **AOC** (active optical cable) for medium
reach, or **optical transceivers to a patch panel** for long reach. **[F]**
### Reach guidance (vendor-typical, treat as [F: vendor] — verify per cable)
```text
DAC (copper):    ~1–3 m   in-rack ToR-to-NIC         [F: vendor]
AOC (optical):   ~5–30 m  intra-row / short leaf-spine [F: vendor]
Optical/transceiver: >30 m to ~2 km  leaf<->spine/long haul  [F: vendor]
```
### Why
DAC is cheaper + lower power for in-rack; AOC/optical for inter-rack where copper
cannot do the reach. At 800G, PAM4 signaling margins tighten — a marginal link
leads to FEC-corrected errors that cost headroom and, worst case, PFC/drop
behavior. **Cable quality *is* a fabric feature.** **[I]**
### Failure modes
BER rising on a marginal link → retries/credit stalls/pause weirdness; DAC beyond
rated reach; mixed generations (400 vs 800G) needing explicit port config. Watch
`local_link_integrity_errors` / `symbol_error`. **[I]**

## 8. Rail-optimized mapping
### What
Wire each node's NICs so that "rail 0 of every node" shares one leaf (plane), "rail
1" the next, etc. The result is **N independent single-plane fabrics**, each a
complete Clos. **[F]** — math in [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) and
[38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md).
### Why / How
AllReduce sends rank i's traffic to ranks i±k; with rails, that traffic stays within
one plane and never crosses — eliminating cross-plane hops and keeping each
collective on its own bisection. NCCL: `NCCL_CROSS_NIC=0` keeps a ring on one rail
for rail fabrics. **[F: NCCL env]**
### Failure modes
Crossing rails (only 1 NIC connected on some node) → unpredictable topology; rail
imbalance (uneven NIC count) causes hot planes; a single NIC index sharing a leaf
as several rails → oversubscription. **[I]**

## 9. NIC configuration checklist (RoCEv2)
A working lossless RoCE NIC needs every line of the following aligned with the
switch:
```text
[ ] RoCEv2 enabled                 (GID from a routable IPv4/IPv6; GID idx for RoCEv2,
                                   NOT RoCEv1 idx 0)   [F/I]
[ ] DSCP 26 on RoCE data, DSCP 48  (align with switch DSCP->TC->priority)  [F: vendor]
[ ] PFC on the SAME single priority the NIC maps RoCE to  [F]
[ ] MTU 9000/9216                  (must equal switch MTU)  [F]
[ ] ECN capable                    (no-drop queue, ECN on)  [F]
[ ] per-QP UDP source-port entropy (NIC varies sport for ECMP)  [F: man page]
DCQCN params (see ./21-dcqcn.md for the full table):  [F: NVIDIA]
    initial_alpha ~1.0 ; alpha_min ; max/min rate ; quantum ; g step ;
    cnp_dscp=48 ; min_time_between_cnps (default ~4) ; clamp_target_rate
GDR: nvidia-peermem loaded; ACS disabled on the path (else peer-to-peer silently off)  [F]
```
**Verify:** `ibstat` (RoCE link, GID), `ethtool -S` (pfc_xoff_rx, np_cnp_sent,
rp_cnp_ignored), `nccl-tests all-reduce` busbw ≈ `0.95 × link` (busbw = algbw × 2(n-1)/n normalizes a saturated ring to link rate). **[F/I]**

## 10. End-to-end design checklist (table)
| Layer | Decision | Guide / anchor |
|---|---|---|
| Topology | L3 leaf-spine + BGP/ECMP | §1; switch counts -> [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) |
| MTU | jumbo 9000/9216 everywhere | §2; 0.65% overhead @8942B [E] |
| DSCP | RoCE data TC + CNP TC | §3; DSCP 26->prio 3, CNP 48->prio 6 [F] |
| PFC | on exactly one priority | §4; headroom ~50KB/400G/us [E] |
| ECN/WRED | K-min/K-max **below** PFC XOFF | §5; the core ordering rule |
| Buffers | lossless / headroom / lossy pools | §6; headroom from §4 [E] |
| Links | 400/800G, DAC in-rack, AOC/optical out | §7 |
| Rails | 1 plane per NIC index | §8; `NCCL_CROSS_NIC=0` [F] |
| NIC | full RoCEv2 checklist | §9 |
| Verify | ECN first, PFC rare; busbw ~99% of link | §9-10 |

## Troubleshooting: the lossless failure catalog
- **Pause storm** (`pfc_xoff_rx` spiking, all QoS tanks): ECN/PFC thresholds
  misaligned (§5) — first thing to recheck. **[I]**
- **Drops despite PFC:** headroom too small (§6) or PFC on the wrong priority (§4).
- **busbw collapse, no PFC storm:** ECMP polarization / entropy (§1; page 22), or
  GDR not engaged (ACS/IOMMU/`nvidia-peermem`, §9).
- **`rp_cnp_ignored` rising:** DCQCN not configured on the adapter (§9 — you think
  it is, it isn't).
- **`Invalid MTU` QP errors:** MTU mismatch on one hop (§2).
- **Cross-plane hot rail:** rail/plane imbalance (§8).
**[I]** — pairs with [17-troubleshooting.md](../GPU-Communication/17-troubleshooting.md).

## Cross-links
- [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) — switch counts (how many leaves/spines for your N).
- [21-dcqcn.md](./21-dcqcn.md) — the DCQCN parameters the NIC checklist points to.
- [20-ecn-wred.md](./20-ecn-wred.md) — ECN/WRED threshold geometry in depth.
- [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md) — ECMP entropy that makes §1's ECMP imperfect.
- [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md) — rail/multi-plane topology (§8).
- [09-infiniband-packet-format.md](./09-infiniband-packet-format.md) — the header math behind §2's overhead table.
- [16-roce-fundamentals.md](./16-roce-fundamentals.md) — RoCEv2 packet layout behind the whole design.
- [55-cheat-sheet.md](./55-cheat-sheet.md) — whole-section quick reference.
- [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md) — the NCCL vars referenced in §8-9.


## Key Takeaways
1. Lossless RoCEv2 is a **threshold hierarchy**: ECN/WRED marks below PFC XOFF so DCQCN
   throttles end-to-end, PFC only backstops on **one** priority; misalignment = pause storms. [I/E]
2. Jumbo **MTU 9000/9216** cuts RoCEv2 per-packet overhead to **0.65 % @ 8942 B** [E] and slices
   PPS demand; one mismatch hop causes silent drops. [F/I]
3. Two-class **DSCP** scheme: RoCE data DSCP 26 -> priority 3 (PFC), CNP DSCP 48 -> priority 6
   (strict, never paused); host and switch must agree or classification silently degrades. [F/I]
4. **Buffer headroom is arithmetic, not guesswork**: ~50 KB/400G and ~100 KB/800G per 1 us of
   pause latency in the lossless-headroom pool. [E: constants bank]
5. Verify by counter pairing -- ECN first, `pfc_xoff_rx` rare, `nccl-tests` busbw ~ 0.95 x
   link (busbw = algbw × 2(n-1)/n normalizes a saturated ring to link rate); if XOFF dominates,
   re-tune section 5 before anything else. [F/I]

## Related
- [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) -- the leaf/spine switch-count math section 1 anchors on.
- [20-ecn-wred.md](./20-ecn-wred.md) -- ECN/WRED threshold geometry behind section 5.
- [21-dcqcn.md](./21-dcqcn.md) -- the full DCQCN parameter table the NIC checklist points to.
- [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md) -- ECMP entropy that limits section 1's ECMP.
- [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md) -- the rail/multi-plane mapping in section 8.
- [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md) -- NCCL vars kept on-rail with `NCCL_CROSS_NIC=0`.

## References
- IEEE 802.1Qbb (PFC) / 802.1Qaz (ETS, DCBX) -- the per-priority pause and DCB negotiation
  standards behind sections 3-4. [F]
- IETF Fast-CNP draft -- the CNP/ECN feedback model the fabric assumes. [F]
- NVIDIA DCQCN / lossless RoCE configs (`mlnx_qos`) -- DSCP-to-priority mapping + DCQCN params. [F: NVIDIA]
- Juniper 802.1Qbb/QoS buffer-partition reference configs -- sections 4-6 sizing examples. [F: Juniper]
- Meta SIGCOMM'24 -- production AI over Ethernet **without** DCQCN (the no-DCQCN case). [F]
- [E] constants from the section bank (computed 2026-08-25). [E]
