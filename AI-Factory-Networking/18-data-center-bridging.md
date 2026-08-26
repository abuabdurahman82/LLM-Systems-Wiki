# Data Center Bridging (DCB): PFC, ETS, DCBX
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: IEEE 802.1Qbb/Qaz, Juniper DCB reference configs, NVIDIA/Mellanox lossless DSCP config; arithmetic from section constants bank (2026-08-25).

## 30-Second Explanation
**Data Center Bridging (DCB)** is the family of Ethernet extensions that turn a
best-effort, shared-buffer LAN into a fabric where one traffic class can be made
**lossless by policy**. Three IEEE pieces work together: **PFC (802.1Qbb)** pauses a
*single priority* class when its switch buffer fills (instead of pausing the whole
port), **ETS (802.1Qaz)** guarantees each priority group its bandwidth share, and
**DCBX (802.1Qaz's exchange protocol)** negotiates those parameters between the NIC and
the switch over LLDP so both ends agree. None of this is about *speed* — it is about
**buffer and bandwidth policy**: telling the network which packets may never drop (the
RoCE class, mapped via DSCP → priority) and which may. RoCEv2 itself does **not** require
DCB — with PFC off it is a *lossy* transport (usable, but slow under incast); the "lossless"
in "lossless RoCE" *is* the DCB configuration, and to get it you must set PFC/ETS/DCBX on every
hop. This page is the foundation for
[19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md) and [20-ecn-wred.md](./20-ecn-wred.md).

## What
DCB is three mechanisms, each a separate IEEE standard (and a fourth, ECN, that is not
technically in DCB but is co-configured with it):

| Standard | Full name | What it does | Layer |
|---|---|---|---|
| **802.1Qbb** | Priority-based Flow Control (PFC) | per-priority pause; 8 priorities | link, hop-by-hop |
| **802.1Qaz** | Enhanced Transmission Selection (ETS) | bandwidth guarantees between priority *groups* | scheduling |
| **802.1Qaz** | DCBX (Data Center Bridging eXchange) | LLDP-based auto-negotiation of PFC/ETS | control plane |
| (RFC 3168) | ECN (Explicit Congestion Notification) | mark, don't drop, under congestion | end-to-end marking ([20-ecn-wred.md](./20-ecn-wred.md)) |

## Why
RoCEv2 RC retransmits with Go-Back-N and cannot tolerate drops ([17-why-roce-is-harder.md](./17-why-roce-is-harder.md)).
The cheap fix is not to redesign the transport but to engineer the Ethernet so the
RoCE class never drops. PFC provides the *link-level* guarantee (a queue that never
overflows), ETS provides the *fairness* so the lossless class cannot starve everything
else, and DCBX provides the *agreement* so the host NIC and the switch enforce the same
policy. Without the family, "lossless" would be a one-sided, misconfigured fantasy.

## How — PFC (802.1Qbb) in detail
PFC operates on one of **8 priority classes** (the 802.1Q PCP / CoS value). When a
switch egress (or ingress) **queue for one priority** fills past its XOFF threshold, it
sends a **PFC PAUSE frame** to the *directly attached* upstream device saying "stop
sending priority N." When the queue drains below the XON threshold, it sends a resume.
This is *per-priority, hop-by-hop* back-pressure:

```text
              PFC PAUSE frame (only prio 3)
Sender NIC  ◄─────────────────────────────  Switch egress queue (prio 3) fills > XOFF
   │  (prio 3 traffic Paused)                   │
   │                                            │  queue drains < XON → PFC RESUME
   └── prio 3 data ───────────────►  prio 3 data delivered, then resumes
```
Vertical version of the same pause mechanism, step by step:

```text
 [1] Sender NIC drives prio-3 (RoCE) frames toward switch egress queue
           │
           ▼
 [2] Switch egress queue for prio 3 fills; occupancy passes XOFF threshold
           │
           ▼
 [3] Switch emits PFC PAUSE (prio 3) upstream to the sender's port
           │
           ▼
 [4] Sender's NIC stops TX of prio-3 frames; other priorities unaffected
           │
           ▼
 [5] Queue drains; occupancy drops below XON threshold
           │
           ▼
 [6] Switch emits PFC RESUME; sender's NIC resumes prio-3 TX
```
Full-page treatment of why this is dangerous under stress is in
[19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md). Here we focus on the mechanics.

**Headroom sizing.** The pause frame does not act instantly: the sender keeps the link
busy for the pause-propagation + reaction *round-trip* while the PFC frame travels, so
the downstream queue must have **headroom** reserved above XOFF big enough to hold
everything already in flight. That headroom is, in the simplest model, one line-rate
interval's worth of data:
- **100 Gb/s, 1 µs** → **12.5 KB** of headroom/absorption [E]
- **400 Gb/s, 1 µs** → **50 KB** of headroom/absorption [E]
- **800 Gb/s, 1 µs** → **100 KB** (scaled from the [E] rows, 100 Gb/s=12.5 GB/s ×8)
  [I: derived from the same per-µs row]

These are the **PFC threshold rows in the section constants bank**; real headroom adds
a stop-and-react multiplier (PAUSE-to-XON latency, deep ASIC pipeline), so switches
provision *several* such intervals per no-drop queue — see [23-roce-lossless-fabric-design.md](./23-roce-lossless-fabric-design.md)
for the full headroom budget. The takeaway: **headroom is measured in bytes reserved
per no-drop priority, and it scales linearly with line rate**.

**The PFC PAUSE frame** is not a normal data packet. It is a control frame carrying a
16-bit *pause quanta* (in units of 512 bit-times) for each of the 8 priorities in a
bitmask, so one frame can pause several priorities at once for the specified duration.
It is sent on the priority/class we are pausing or on a dedicated control channel —
exact framing is IEEE 802.3 Annex 31B (MAC Control PAUSE) extended per-priority by
802.1Qbb [F: IEEE 802.1].

## How — ETS (802.1Qaz) in detail
ETS lets you group the 8 priorities into **priority groups (PGs)** and assign each group
a **bandwidth share** (percentages summing to 100). The scheduler (a strict-priority +
weighted round-robin hybrid) guarantees each PG at least its share when the link is
fully loaded, and redistributes idle capacity. Typical AI fabric intent: give the
lossless RoCE priority its share, give CNP/control-priority a strict-high slot, and a
lossy best-effort class the remainder. ETS is what stops PFC's lossless class from
monopolizing the whole link — fairness, not just no-drop.

## How — DCBX (802.1Qaz) in detail
**DCBX** is the *negotiation* layer. It runs on **LLDP** (IEEE 802.1AB) and exchanges
PFC (which priorities are forced/pause-capable) and ETS (group bandwidth) TLVs between
the NIC and the directly attached switch. Purpose: both ends agree on the same policy *
before* lossless traffic meaningfully flows, and mismatches surface as errors rather
than silent drops. On Mellanox/NVIDIA hosts this is `mlnx_qos`/`dcb` tooling under the
hood; on Linux it's the `dcb` iproute2 subcommand. [F: vendor]

## DSCP → priority → queue mapping
Classification is the linchpin: a packet's **DSCP** (IP ToS field) decides its fate.
PFC pauses on the **802.1p priority** (the 3-bit PCP value, 0–7), so the whole design keys
off the DSCP→priority table. The chain is:

```text
 DSCP (IP) ──► 802.1p priority (0-7) ──► egress queue ──► ETS group (bandwidth share)
   26  ──────────► prio 3, PFC-enabled ─────────────► lossless priority group
   48  ──────────► prio 6, strict-high ─────────────► control priority group
```
("Traffic class" is the generic name for a DSCP/PCP-priority class on many switch families;
on Mellanox/NVIDIA the DSCP table maps DSCP → priority directly.)

Mellanox/NVIDIA defaults (DSCP-based QoS, widely reproduced):
- **RoCE data DSCP 26 (AF31) → priority 3**, PFC-enabled [F: vendor spec]
- **CNP DSCP 48 → priority 6** [F: vendor spec]

Because **ECN marking is per-queue/DSCP, PFC is per-priority, and CNP gets its own
DSCP**, the *entire* lossless+congestion design keys off this mapping. Host and switch
DSCP→TC tables must match exactly, or one end marks/pauses a different queue than the
other thinks — the root of many silent RoCE misconfigs (see [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md)).

## Packet flow (round trip, end to end)
```text
GPU-A app ─ post WR ─► NIC-A ─► DSCP 26 tagged ─► Leaf egress (prio 3, PFC on)
     │                                                        │
     │   switch queue fills  ─► ECN marks ●  ─► PFC backstop  │
     ▼                                                        ▼
GPU-B NIC ◄─ prio-3 flow + marked ● ─────────────────────◄  Leaf ingress (prio 3)
     │
     └─ on marked ●: NIC-B sends CNP (DSCP 48, prio 6) ──► back to NIC-A
                                                              │
                                              NIC-A cuts rate ─┘  (see 21-dcqcn)
```

## GPU relationship
The GPU never sees DCB directly — its NIC (ConnectX-class or equivalent) implements
PFC/ETS/DCBX and maps the GPU's RDMA traffic into the lossless priority. What the GPU
*does* feel is the result: on a correctly DCB'd fabric, collective time is flat and
drops are zero; on a mismatched fabric, NCCL hangs or iteration time explodes. From the
GPU's side, DCB is "an invisible contract the NIC keeps with the switch." [I]

## Design
- **One lossless priority for RoCE** in most AI fabrics (some use more for
  differentiated RDMA); **one strict-high priority for CNP/control** so congestion
  feedback is never itself paused.
- **Buffer partitioning example (reference config [F: Juniper DCQCN buffer model])**:

| Partition | Share | Holds |
|---|---|---|
| lossless | 80 % | the no-drop RoCE queue's working buffer (up to XOFF) |
| lossless-headroom | 10 % | absorption above XOFF while PFC takes effect |
| lossy | 10 % | best-effort / management, never paused |
- Headroom row scales with line rate [E: 12.5 KB @100G·1µs, 50 KB @400G·1µs].
- **Co-locate PFC thresholds and ECN marks deliberately**: ECN should fire *first*
  (lower threshold), PFC only as a backstop — the central tuning constraint (see
  [20-ecn-wred.md](./20-ecn-wred.md)).

## Tuning
- Set the **same DSCP→TC table on host and switch**; verify with `mlnx_qos` on
  Mellanox or `dcb app`/`tc` on Linux, and switch `show qos` equivalents.
- Size **headroom ≥ (reaction time × line rate)**: default to several [E] per-µs rows.
- Use **DCBX willing/desired** or explicit config but never let host and switch drift;
  treat a DCBX mismatch as a blocking error, not a warning.
- Keep **CNP on a strict-high, non-PFC (or highest-PFC) priority** so feedback is never
  paused behind the very traffic it is throttling.

## Troubleshooting
- **Symptom: RoCE drops on a "lossless" fabric** → check whether PFC is actually
  enabled on *both* ends of the link and whether DSCP→TC maps match (host vs switch).
- **Symptom: PFC counter rises continuously** → headroom too small or XOFF too low;
  ECN isn't firing before PFC ([20-ecn-wred.md](./20-ecn-wred.md), [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md)).
- **Symptom: CNP frames dropped/starved** → CNP on a paused priority; move to strict-high.
- **Symptom: best-effort starved** → ETS shares not set; lossless PG taking everything.
- Walk [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md) for the decision tree.

## Comparison

| Property | PFC (Qbb) | ETS (Qaz) | DCBX (Qaz) | ECN (RFC 3168) |
|---|---|---|---|---|
| Prevents drops | yes (backstop) | no | no | no (marks) |
| Guarantees bandwidth | no | yes | no | no |
| Negotiates policy | no | no | yes | no |
| Scope | per-priority, hop | per-group, link | NIC↔switch | end-to-end |
| Feedback to sender | pause (link-local) | n/a | n/a | CE mark → DCQCN |
| Page follow-up | [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md) | this page | this page | [20-ecn-wred.md](./20-ecn-wred.md) |

## Lab
- On a Mellanox/NVIDIA host: `mlnx_qos -i ethX` shows the current DSCP→priority map and
  PFC state; `mst` + `mlxreg`/`mlxstat` show buffer thresholds.
- Linux: `dcb pfc show dev ethX`, `dcb ets show dev ethX`, `dcb app show dev ethX`.
- Switch: `show pfc`, `show qos`, PFC frame counters on the lossless priority —
  **target: PFC fires rarely and ECN does the work** ([20-ecn-wred.md](./20-ecn-wred.md),
  [21-dcqcn.md](./21-dcqcn.md)).

## Key Takeaways
1. DCB = three IEEE pieces that turn best-effort Ethernet into a per-class lossless fabric: **PFC (802.1Qbb)** pauses one priority, **ETS (802.1Qaz)** guarantees each priority group its bandwidth share, **DCBX (802.1Qaz/LLDP)** negotiates both between NIC and switch.
2. PFC is per-priority, hop-by-hop back-pressure on one of **8 priorities**; because the pause isn't instant it needs **headroom** equal to one line-rate reaction interval — 12.5 KB @100G·1µs, 50 KB @400G·1µs [E] — and real fabrics reserve several such rows per no-drop queue.
3. Headroom is **reserved bytes per no-drop priority and scales linearly with line rate**; ETS keeps that lossless class from monopolizing the link, and CNP/control gets a strict-high slot.
4. DCBX never lets host and switch drift — a PFC/ETS mismatch surfaces as a blocking error, and host↔switch DSCP→TC tables must match exactly or lossless silently breaks.
5. Run RoCEv2 with PFC **on** and you are running the DCB machinery (PFC/ETS/DCBX); but RoCEv2 itself does **not** require DCB — with PFC off it is lossy (§30-seconds). The whole lossless design keys off **DSCP→priority** (PFC pauses on the 802.1p priority, not the DSCP directly).

## Related
- [17-why-roce-is-harder.md](./17-why-roce-is-harder.md) — why RoCE needs lossless-by-policy at all (Go-Back-N).
- [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md) — PFC's failure modes when it stops being a rare backstop.
- [20-ecn-wred.md](./20-ecn-wred.md) — the ECN marking that must fire *before* PFC pauses.
- [21-dcqcn.md](./21-dcqcn.md) — the ECN/CNP loop that reduces PFC to a last-line brake.
- [23-roce-lossless-fabric-design.md](./23-roce-lossless-fabric-design.md) — the full headroom/DCB budget for a no-drop fabric.
- [README.md](../Hardware/README.md) — the NIC/HCA silicon (ConnectX-class) that implements PFC/ETS/DCBX.

## References
- IEEE 802.1Qbb (PFC, per-priority pause) and IEEE 802.1Qaz (ETS + DCBX over LLDP) [F].
- RFC 3168 (ECN — co-configured with, though not formally in, DCB) [F].
- Juniper DCB/DCQCN reference configs (lossless DSCP→TC mapping) [F: vendor].
- NVIDIA/Mellanox lossless DCB config (RoCE DSCP 26→prio 3, CNP DSCP 48→prio 6) [F: vendor].
- [E] PFC headroom rows (12.5 KB @100G·1µs, 50 KB @400G·1µs) from the section constants bank (computed 2026-08-25).
