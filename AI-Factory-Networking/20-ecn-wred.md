# ECN and WRED Marking for RoCE
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: RFC 3168 (ECN), IP Infusion DCQCN explainer, Juniper DCQCN drop-profile config, RFC 6040 (ECN over tunnels); arithmetic from section constants bank (2026-08-25).

## 30-Second Explanation
**ECN (Explicit Congestion Notification)** is the "report congestion before it hurts"
mechanism that keeps PFC from having to pause ([19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md)). A switch
marks a packet's IP header **CE (Congestion Experienced)** instead of dropping it, once
that packet's egress queue crosses a threshold on a **WRED curve** — marking starts at
**K-min**, ramps probability linearly, reaches **P-max at K-max**. Only **ECN-capable**
traffic (the RoCE class, identified by DSCP) is marked; everything else is just dropped
normally. The receiver sees the CE mark and (via **DCQCN**, [21-dcqcn.md](./21-dcqcn.md)) tells the
sender to cut its rate *end-to-end*, so congestion feedback travels as a mark, not as a
signal of loss inflicted. Science is in the thresholds: **ECN must fire *before* the
PFC XOFF threshold** — that placement is the central tuning decision of the whole fabric,
because mark-too-late means pause storms, and mark-too-early means needless throttling.

## What — the three ECN states of an IP packet
ECN repurposes the two low bits of the IPv4 ToS byte / IPv6 Traffic Class (RFC 3168):

| ECN bits (ECT/CE) | Name | Meaning |
|---|---|---|
| `00` | Not-ECT | not ECN-capable; switch may drop, never marks |
| `01` / `10` | ECT(1) / ECT(0) | ECN-capable transport, no congestion yet |
| `11` | CE (Congestion Experienced) | switch has marked: you are congested |

```text
IP header ToS byte, bits 6-7:
 0   1   2   3   4   5   6   7
| DSCP (6 bits)         |ECN|      EC = ECT/CE
                        └┬┘       00 not-ECT, 01/10 ECT, 11 CE
```
When a packet arrives with ECT set and the queue is congested, the switch flips it to
**CE** and *forwards* it — no drop. The receiver's NIC converts CE into a CNP back to the
sender ([21-dcqcn.md](./21-dcqcn.md)).

## Why
ECN exists because **dropping as the *only* congestion signal is destructive for RoCE**:
a drop triggers Go-Back-N retransmission and throughput collapse ([17-why-roce-is-harder.md](./17-why-roce-is-harder.md)).
Marking instead lets the *sender slow down* while the packet still carries data — the
mark is information, the drop is damage. And ECN outruns PFC: it takes one RTT for the
mark→CNP→rate-cut loop to work, and it is **end-to-end**, whereas PFC is hop-by-hop and
only buys time locally. ECN's job is to *make PFC nearly unnecessary*. [I]

## How — WRED-based marking at the switch egress queue
Marking happens at the switch's **egress queue**, and it is **per-traffic-class** (per
TC/priority): each queue gets its own WRED curve. Occupancy-based:

```text
mark probability P
  1 ┤              ●
    │            ╱        = P-max at K-max
    │          ╱            (linear ramp from K-min)
 Pmax┤  ──●──╱
    │   ╱  K-min           below K-min: no marking
    │ ╱
  0 ┤●────────────────────►  queue depth
    K-min       K-max      (K-max < PFC XOFF threshold, below)
```
- **Below K-min**: no marking.
- **K-min → K-max**: mark with probability ramping 0 → **P-max** (a drop-profile, e.g.
  fill-level [55 90], probability [0 100] in Juniper terms [F: Juniper DCQCN config]).
- **Above K-max**: mark at P-max (all eligible packets), still *forwarding* them.
- The same curve, with a drop-action, is WRED's classic drop function; with a
  mark-action it is the ECN marker [I/A].

**Mark-vs-drop policy:** on the ECN-capable RoCE class, the switch *never drops* above
K-max — it marks at P-max and continues forwarding (the buffer is protected by PFC, so
the queue physically cannot overflow if headroom is sized right). On **not-ECT** classes,
the identical curve is a normal WRED *drop* profile. So "the WRED curve" does mark *or*
drop depending on whether the packet is ECN-capable [F: vendor behavior on RoCE fabrics].

**Per-queue independence**: each TC's queue has its own K-min/K-max/P-max, so the RoCE
queue's ECN thresholds are set independently of the lossy class's drop thresholds — you
often want the lossless class to mark early (protect PFC) while the lossy class just
drops [I].

## Packet flow (marking round trip)
```text
Sender NIC ── RoCE pkt (DSCP 26, ECT) ──► Switch egress queue (prio 3)
                                              │  depth crosses K-min → P
                                              ▼
                           marked: ECT ∘ → CE ●, forwarded (NOT dropped)
                                              │
                                              ▼
Receiver NIC ◄──────────────────────────────── CE packet
      │
      ▼  CE detected on RoCE class
Receiver NIC ── CNP (DSCP 48, prio 6) ──► back to Sender NIC
      │
      ▼
Sender NIC cuts rate (DCQCN alpha/rate)  ── see 21-dcqcn
```
The **PFC XOFF threshold must sit *above* K-max** — reserving the ECN/K-max region and
then the headroom — so that by the time PFC would even consider pausing, senders have
*already* been told to slow (see [18-data-center-bridging.md](./18-data-center-bridging.md) for the headroom rows).

## GPU relationship
The GPU sees only the NIC beneath it. The NIC's DCQCN engine reads CE marks, computes
α, and throttles the interest rate of the GPU's traffic *without the GPU ever noticing
the congestion* (RDMA verbs carry no congestion signal to the app). The GPU's collective
time is flat when ECN fires correctly; when ECN is mis-thresholded it suffers the
pause-storm symptoms described in [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md) even though it "did
nothing wrong." [I]

## Design — the central tuning decision (± `[I]`)
The single most important knob in a RoCE fabric is **where K-max (full ECN mark) sits
relative to the PFC XOFF threshold**. Reason it out as a byte budget on the no-drop
priority:

```text
queue depth (bytes)
   ▲
   │  buffer ceiling (headroom filled)   ── PFC XOFF must catch everything here
   │  ├── headroom (reserved, ~N × line-rate·µs)          [E: 50 KB @400G·1µs]
   │  │    └── K-max (all packets marked → sender already cutting)
   │  │         └── K-min (start marking)
   ▼
```
- **K-min (and K-max) above XOFF** (or ECN disabled) → ECN never marks before the queue
  fills → **pause storms** [I/E]. (If only K-min is below XOFF, ECN fires — just not at full
  rate — so K-max < XOFF is the stronger "full-mark-before-pause" target.)
- **K-min too low** → premature marking → needless throttling, wasted bandwidth.
- Goal: ECN signals *well before* the queue would reach the PFC headroom; PFC stays a
  silent backstop [I].

**ECN across VXLAN (RFC 6040-style)** — ECN bits survive tunnel encapsulation: on
encap, the outer IP header's ECN field is derived from the *inner* packet's ECN value
(inner ECT → outer ECT; inner non-ECT → outer ECN-Disabled) so the underlay switch can
mark it, and on decap the inner ECN is set to **CE** if either the inner packet or the
tunnel (outer) was marked CE. This is why DCQCN/ECN keep working over EVPN-VXLAN
overlays — marking done
on the underlay is carried through to the RoCE endpoints [F: RFC 6040].

### Why threshold *placement*, not threshold *size*, is the decision
The bandwidth curves of ECN and PFC sit on the same buffer; the entire tuning story is
ordering them so the *cheapest* signal (a mark that costs ~nothing and lets the data
flow) always precedes the *most expensive* (a pause that idles the link and risks
cascade). ECN→mark→CNP→rate-cut is gentler and end-to-end; PFC is the last line. If you
widen *both* thresholds together you gain nothing — only their **relative offset**,
plus enough headroom above XOFF for PFC to absorb its reaction time, determines whether
the fabric idles-thrashes or runs flat. This is why the same K values are "correct" on
one fabric and catastrophic on another: the offset to PFC's XOFF differs. [I]

## Tuning
- Set **K-min / K-max / P-max** per lossless TC: e.g. fill-level interpolate [55 90],
  drop-probability [0→100] as the marker on the RoCE scheduler [F: Juniper DCQCN config].
- **Guarantee K-max < XOFF**; make headroom the difference between XOFF and the buffer
  ceiling [E] ([18-data-center-bridging.md](./18-data-center-bridging.md)).
- Enable ECN explicitly on the RoCE queue (a common miss: ECN compiled into the ASIC but
  never turned on for the lossless queue) [I].
- Align **host and switch** ECN/DSCP tables so the NIC knows the RoCE class is ECT.

## Troubleshooting
- **Symptom: pause storms despite DCQCN** → ECN marking not enabled, or K-max ≥ XOFF;
  ECN never told senders to slow [I/E] ([19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md)).
- **Symptom: throughput below expectation, no drops, no pauses** → K-min too low;
  senders throttled when buffers were nowhere near overflow.
- **Symptom: CNP not arriving** → CNP priority paused or mismatched DSCP (CNP DSCP 48
  on Mellanox [F: vendor]).
- **Symptom: drops on lossless class** → PFC/headroom not sized `≥` reaction, or ECN
  region too small; buffer genuinely overflowed ([17-why-roce-is-harder.md](./17-why-roce-is-harder.md)).
- See [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md).

## Comparison

| Decision | Mark (ECN) | Drop (WRED) | Pause (PFC) |
|---|---|---|---|
| Feedback quality | rate signal to sender | loss (Go-Back-N) | hop-by-hop stop |
| End-to-end? | yes (via CNP) | yes (implicit) | no |
| Invoked when | queue ≥ K-min | not-ECT / no headroom | queue ≥ XOFF |
| Cost to fabric | ~0 (packet delivered) | retransmit + collapse [E] | cascade/deadlock risk |
| When to use | RoCE/ECN-capable class | lossy/best-effort | last-line backstop |
| Page | [20-ecn-wred.md](./20-ecn-wred.md), [21-dcqcn.md](./21-dcqcn.md) | [17-why-roce-is-harder.md](./17-why-roce-is-harder.md) | `./18-…`, `./19-…` |

## Lab
- On a switch with ECN on the RoCE queue: `show queue` ECN-mark counters vs PFC counters
  — healthy fabric shows **marks >> pauses**.
- Sweep K-min and K-max while running an incast (`nccl-tests` `allreduce`),
  record (drops, pause-count, completion time). The K placement that minimizes
  completion *and* keeps pause-count near zero is the dail tuning point [I/E].
- Verify CE propagation over an EVPN-VXLAN path if your fabric uses an overlay
  (RFC 6040 semantics) [F].

## Key Takeaways
1. ECN repurposes the two low IP ToS/TC bits (RFC 3168): **Not-ECT (00)** is never marked, **ECT (01/10)** is markable, **CE (11)** means "congested" — the switch marks and *forwards*, it does not drop.
2. Marking rides a **WRED curve** at the egress queue, per traffic class: no mark below K-min, linear ramp to **P-max at K-max**, then mark at P-max while still forwarding — occupancy-based, not per-flow.
3. Mark-vs-drop depends on ECN capability: the ECN-capable RoCE class is marked (never dropped; PFC protects the buffer), while the identical curve on a not-ECT class is a normal WRED *drop* [F: vendor behavior].
4. The central tuning decision is **where K-max sits relative to the PFC XOFF threshold** — mark-too-late ⇒ pause storms, mark-too-early ⇒ needless throttling; only the *offset* to XOFF (plus headroom above it) matters, not the absolute K values [I/E].
5. ECN bits survive tunnel encapsulation (RFC 6040), so DCQCN/ECN keep working over EVPN-VXLAN overlays.

## Related
- [21-dcqcn.md](./21-dcqcn.md) — the CNP loop that turns a CE mark into a sender rate cut.
- [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md) — the pause storms ECN prevents when it fires first.
- [18-data-center-bridging.md](./18-data-center-bridging.md) — the PFC XOFF / headroom rows ECN thresholds must sit below.
- [17-why-roce-is-harder.md](./17-why-roce-is-harder.md) — why drop-based signaling (vs marking) destroys RDMA.
- [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md) — diagnosing pause-storm vs overly-throttled symptoms.
- [README.md](../Networking/README.md) — QoS/marking behavior across the wider network.

## References
- RFC 3168, "The Addition of Explicit Congestion Notification (ECN) to IP" [F].
- RFC 6040, "Tunnelling of Explicit Congestion Notification" (VXLAN/overlay CE propagation) [F].
- IP Infusion DCQCN explainer (ECN/CNP/VXLAN-DCQCN stance) [F].
- Juniper DCQCN drop-profile config (fill-level [55 90], probability [0 100] marker) [F: vendor].
- NVIDIA/Mellanox DSCP/ECN defaults (ECN on RoCE class; CNP DSCP 48) [F: vendor].
- [E] mark-threshold/headroom reasoning (50 KB @400G·1µs) from the section constants bank (computed 2026-08-25).
