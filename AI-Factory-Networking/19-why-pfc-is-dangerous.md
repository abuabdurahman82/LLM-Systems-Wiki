# Why PFC Is Dangerous: Failure Modes of Priority Flow Control
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: IEEE 802.1Qbb, Cisco AI/ML whitepaper, IP Infusion DCQCN explainer, NVIDIA DCQCN params; arithmetic from section constants bank (2026-08-25).

## 30-Second Explanation
PFC (802.1Qbb) keeps a priority's queue from *overflowing* — but that is all it does,
and the price of no-drop is that **the network can stall**. PFC is *lossless at the
queue* by pushing the problem *upstream*: it pauses the sender, hop by hop. When many
hops pause each other in a cycle, **nothing moves at all** (deadlock); when one congested
queue pauses a sender that is itself paused, the effect **cascades** fabric-wide; and
because PFC is per-*priority*, a pause on the RoCE priority **head-of-line blocks** every
other flow unlucky enough to share that priority's buffer. The industry slogan is true:
**PFC alone is not lossless** — a mis-tuned PFC fabric simply *moves the loss* (and adds
pause storms, deadlocks, and unfairness) while still occasionally dropping. That is why
production AI fabric puts **ECN/DCQCN in front** (slow senders down *before* the buffer
fills) and keeps PFC strictly as a rare backstop, plus vendor **PFC watchdog** features
to break a stuck pause. This page is the dark side of [18-data-center-bridging.md](./18-data-center-bridging.md).

## What — the failure modes
PFC is not one failure; it is a family of them, all consequences of *pushing back-
pressure rather than absorbing or signaling congestion*:

| Symptom | Underlying cause | Where it bites |
|---|---|---|
| **Pause storm** | ECN/PFC thresholds misaligned → PFC fires constantly | continuous pause frames, fabric idles |
| **Pause propagation / cascade** | one congested queue pauses upstream, which pauses further upstream | congestion spreads outward, innocent traffic throttled |
| **Deadlock (circular pause)** | A pauses B while B pauses A (or a loop of queues) | zero progress; fabric hangs |
| **Head-of-line (HOL) blocking** | paused priority's buffer holds traffic behind it | same-priority flows and queues stall behind a pause |
| **Starvation / unfairness** | PFC's no-drop class hogs buffer+scheduler | other priorities/tenants starve |
| **Buffer exhaustion elsewhere** | headroom reserved on no-drop queue squeezes shared buffer | lossy/Best-effort class drops more |

Why any of this matters at all: RC retransmits with Go-Back-N, so a drop — or a pause
storm that idles the fabric — is doubly costly ([17-why-roce-is-harder.md](./17-why-roce-is-harder.md)).

## Why
PFC's design *assumes* it is a rare backstop. In practice it becomes the active control
loop whenever ECN is missing, mis-tuned, or fires too late; and PFC's feedback is
**link-local and binary** (pause/resume), with no notion of *how much* to slow down —
so it alternates between "too late" (overflow/drop) and "too much" (idle). The whole
DCQCN/ECN machinery exists precisely to replace PFC-as-controller with a *rate-based,
end-to-end* one, leaving PFC as an emergency brake. [I]

## How — deadlock and cascade mechanics
**Pause propagation.** Pause does not stop congestion; it *moves* the waiting traffic
back up the path. Switches have finite buffers at *every* stage; each paused upstream
queue eventually fills and pauses *its* upstream neighbor. A single hotspot becomes a
wall of paused hops.

**Circular pause / deadlock.** Because PFC is *per-priority*, a pause on priority 3 at
switch A toward switch B can coincide with a pause on priority 3 at B toward A (or a
multi-hop ring). Now A is waiting on B and B is waiting on A: **no queue drains, no
frames move — a livelocked hang** with zero DROP counters, which makes it notoriously
hard to detect (throughput collapses to ~0 but no packet loss is recorded).

```text
   Switch A ──pause prio3──►  Switch B
        ▲                        │
        └──pause prio3──────────┘   (A and B each waiting on the other)
            → circular pause → no progress, no drops counted
```
This full vertical flow is broken by a **PFC watchdog** (below), by disabling PFC on
that class, or by never letting topologies form pause cycles.

**Head-of-line blocking.** PFC pauses a *priority*, not a flow. The sender's NIC and the
switch put many QPs/flows on the same priority; when that priority is paused, *all* of
them stall in the queue — even flows going to uncongested destinations that had nothing
to do with the pause. Lossless-class tail latency becomes hostage to the worst hotspot
sharing its priority. [I]

## When — why PFC alone is dangerous but also necessary
PFC is dangerous *as the primary congestion mechanism*; it is correct as a **last-line
backstop**. Danger appears when any of these is true:
- ECN is disabled or its K-thresholds sit *above* the PFC XOFF threshold (ECN never
  marks before PFC pauses) [I].
- DCQCN/rate control is off or mis-configured, so PFC is the only brake.
- Headroom is too small, so PFC still loses the race and drops anyway.
- Topology/forwarding allows a pause cycle (usually impossible in a healthy
  tree/CLOS without mis-forwarding, but path changes can create it).

## Hardware impact
- **Buffers**: no-drop headroom is *reserved*, taking space from the shared/lossy pool
  [E: PFC thr per µs = 12.5 KB @100G, 50 KB @400G; headroom is multiple such rows].
- **ASIC**: per-priority pause state machines, headroom tracking, and now PFC-watchdog /
  pause-deadlock timers consume die area and complexity.
- **NICs**: must honor PFC at full line rate (pause quanta handling), and, on
  Spectrum-X-class hardware, detect/avoid relying on PFC by doing congestion control
  itself [F: vendor].

## Inference impact
For inference serving, PFC head-of-line blocking is the worst outcome: **one busy
decode request sharing the RoCE priority can pause and delay every other request in that
priority** — turning a per-request stall into a *serving-wide* tail-latency event. The
token-loop p95 can balloon while the fabric reports "zero drops." [I: inference
condition]

## Example — a pause storm budget (why thresholds matter)
Say the RoCE priority runs at 400 Gb/s (50 GB/s) [E] toward a hot receiver. The switch
reserves ~50 KB of headroom per µs of pause-reaction [E]. If ECN's K-min sits *above*
XOFF, ECN never marks before the queue fills, so DCQCN never cuts rate, so the queue fills
every cycle and PFC pauses constantly — a pause storm emitting a PAUSE every few microseconds,
with the link
idling in between. Moving ECN K-thresholds *below* XOFF lets marking happen first and
turns the storm into a few ECN marks per burst (see [20-ecn-wred.md](./20-ecn-wred.md)). The arithmetic
is the lesson: thresholds are bytes apart, and the whole difference between "stable" and
"storm" is where the mark/pause lines sit.

A deeper version of the same storm: apply it at incast. N GPUs converge on one hot
receiver; each of the N senders' queues individually stay under PFC's headroom, but
*collectively* they are funneling ~N × line-rate worth of return traffic into the
receiver's single egress buffer. The receiver's queue fills in microseconds and
immediately saturates at XOFF, so PFC pauses the *upstream switch ports*, which pause
their senders, which — because every sender is part of the same served batch of GPUs —
wait on the *same* receiver. The pause climbs the tree faster than any of the senders
drain. This is PFC *as a controller* failing structurally: a binary back-of-queue signal
applied across a many-to-one fan-in with no per-flow notion of "how much less". Only an
end-to-end rate signal (DCQCN, [21-dcqcn.md](./21-dcqcn.md)) can resolve it; a bigger XOFF only
postpones it. [I/E: incast reasoning on the [E] headroom rows]

## Failure modes → mitigations (symptom → cause → fix)

| Symptom | Cause | Fix |
|---|---|---|
| Zero throughput, **zero drop counters** (CPU pegged, no errs) | circular pause / deadlock | PFC watchdog; break the pause cycle; verify no forwarding loop |
| Continuous PFC counters, low utilization | ECN not firing before PFC | move ECN K < PFC XOFF; enable DCQCN ([20-ecn-wred.md](./20-ecn-wred.md), [21-dcqcn.md](./21-dcqcn.md)) |
| Paused traffic's tail latency spikes while uncongested | head-of-line blocking on shared priority | isolate lossy class off the no-drop priority; reduce QPs/priority sharing |
| Lossy/best-effort class dropping | no-drop queue consuming shared buffer | reserve headroom correctly; cap lossless buffer share [E] |
| Drops *despite* PFC | headroom too small for pause-reaction | enlarge headroom ≥ reaction×line rate [E rows] |
| One hot flow pauses many others | per-priority granularity | more priorities or rate-based CC (DCQCN) instead of pause |

For the full counter-lookup decision tree, walk [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md).

## Tuning
- **ECN-threshold alignment (the single most important knob)**: ECN *must mark before*
  PFC pauses — i.e. K-min (marking start) < XOFF; setting K-max < XOFF as well guarantees
  *full* marking before the pause fires. If K-min ≥ XOFF, PFC carries the
  whole burden and storms happen [I], see [20-ecn-wred.md](./20-ecn-wred.md).
- **Isolate lossy traffic classes** onto a *non-PFC* priority so PFC can never pause
  them (and they can never be HOL-blocked by the lossless class).
- Size **headroom** generously (several [E] per-µs rows per lossless priority).
- **CNP/control on a strict-high priority** so feedback is never paused.
- **PFC watchdog policy**: enable it, but tune the timeout long enough that a *brief*
  stall from a real (recoverable) hotspot does not get force-dropped; a watchdog that
  trips too eagerly trades a pause for a drop — exactly what the lossless class was
  built to avoid [I, vendor-feature semantics]. The watchdog is a *safety net*, not a
  congestion mechanism; rely on ECN/DCQCN for the actual control ([21-dcqcn.md](./21-dcqcn.md)).
- **Verify hysteresis**: XON should sit below XOFF so the queue does not immediately
  re-pause on resume — a hysteresis gap prevents constant toggle [I]; fold this into
  headroom: XOFF + in-flight ≈ headroom ceiling.

## How to measure it
- Switch: `show pfc` / per-priority PFC TX/RX counters — *rate of change* of paused
  frames, not just "nonzero."
- NIC (Linux `ethtool -S`): `tx_pause`, `rx_pause`, `out_of_buffer`, `*_discard`.
- `perftest` under a controlled burst (`ib_write_bw -F`): watch for the pause-driven
  sawtooth in throughput.
- **The name of the game**: count *how often* PFC fires, not whether it works — the
  fabric is healthy when PFC is nearly silent and ECN/DCQCN is doing the throttling.
- Watchdog telemetry: **when** the watchdog last tripped and **which** queue — a
  recurring trip is a mis-tuned threshold (or a lost pause cycle), a one-time trip may
  be a genuine deadlock that the watchdog correctly broke [I].

## Comparison — PFC as backstop vs PFC as controller

| Role | What it does | Health signal | Page |
|---|---|---|---|
| PFC as **backstop (correct)** | rare pause only after ECN/DCQCN has throttled | PFC counters flat across a run | [18-data-center-bridging.md](./18-data-center-bridging.md) |
| PFC as **controller (wrong)** | constant pause = the only brake | PFC counters climbing, low util | [20-ecn-wred.md](./20-ecn-wred.md), [21-dcqcn.md](./21-dcqcn.md) |
| **watchdog** (vendor) | detects stuck pause, breaks it | fires rarely, only on failure | this page |

## Lab
- Linux switchdev PFC watchdog: enabled via `devlink` / `dcb` on supported NICs — see
  your vendor doc; it is a **vendor/switchdev feature, not an IEEE standard**
  (correction, `[A] correction` below).
- Reproduce a pause storm: set ECN K-thresholds *above* XOFF, run an incast target, and
  watch PFC counters skyrocket while throughput sags; then lower K below XOFF and watch
  ECN/DCQCN take over.
- Reproduce deadlock (harder): force a forwarding loop or a momentary mis-forward so two
  lossless queues pause each other; confirm **zero drop counters** while throughput is
  ~0, then confirm the PFC watchdog clears it. This is the classic "it's not reducing
  throughput because of loss" false-reading — which is why the symptom→cause table above
  lists "deadlock" as the zero-drop hang. [I]

> **Correction (`[A] correction`):** the common claim that "PFC watchdog is IEEE
> **802.1Qau**" is wrong. **802.1Qau is QCN** (QoS/802.1 Congestion Notification) — a
> different, standards congestion-notification mechanism, not a PFC-watchdog standard.
> Within the 802.1 family: **PFC = 802.1Qbb**, **ETS = 802.1Qaz**, **QCN = 802.1Qau**.
> **PFC watchdog has no IEEE designation**; it is a switch-vendor feature (Cisco,
> NVIDIA/Mellanox, Arista, Juniper all ship variants) and a Linux switchdev/devlink
> "pfc watchdog" for NICs. Treat any spec sheet claiming "802.1Qau PFC watchdog" as
> unreliable. [A: correction over common misconception]

## Key Takeaways
1. PFC guarantees **no-drop at the queue by moving the problem upstream** — it pauses the sender hop by hop; it's lossless *by policy*, not by property, so "PFC alone is not lossless" [F: IEEE 802.1Qbb; industry].
2. The failure modes are a family: **pause storm**, **pause propagation/cascade**, **circular-pause deadlock**, **HOL blocking**, **starvation**, and buffer exhaustion that re-drops the lossy class.
3. **Deadlock is the sneakiest**: circular pause yields zero DROP counters while throughput → ~0 — a livelocked hang that looks like "no loss," found via PFC counters/watchdog, not loss counters.
4. PFC is a **rare backstop, not the controller**: ECN/DCQCN must throttle first (ECN K-max < PFC XOFF), PFC only catches the residual overflow — malplaced thresholds are the difference between stable and a pause storm.
5. **PFC watchdog is a vendor/switchdev feature with no IEEE designation** — 802.1Qau is QCN, not a PFC-watchdog standard (PFC=802.1Qbb, ETS=802.1Qaz).

## Related
- [18-data-center-bridging.md](./18-data-center-bridging.md) — the DCB mechanics (PFC/ETS/DCBX) this page's dark side covers.
- [20-ecn-wred.md](./20-ecn-wred.md) — ECN marking that keeps PFC silent when thresholds are aligned.
- [21-dcqcn.md](./21-dcqcn.md) — the rate-based CC that replaces PFC-as-controller.
- [17-why-roce-is-harder.md](./17-why-roce-is-harder.md) — why a drop or pause storm is doubly costly (Go-Back-N).
- [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md) — decision tree for the zero-drop hang / pause storms.
- [README.md](../Networking/README.md) — fabric-wide QoS/pause behavior in the wider networking context.

## References
- IEEE 802.1Qbb (PFC), 802.1Qaz (ETS/DCBX), 802.1Qau (QCN — the correction over the "watchdog=Qau" myth) [F].
- Cisco AI/ML Fabric architecture whitepaper (PFC failure modes / no-drop design) [F: vendor].
- IP Infusion DCQCN explainer (PFC vs ECN/DCQCN control interplay) [F].
- NVIDIA/Mellanox DCQCN params (PFC-threshold/XOFF and watchdog semantics) [F: vendor].
- [E] PFC headroom rows (12.5 KB @100G, 50 KB @400G per-µs) from the section constants bank (computed 2026-08-25).
