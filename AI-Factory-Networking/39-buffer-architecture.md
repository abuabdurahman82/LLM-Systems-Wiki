# Switch Buffer Architecture: Shallow vs Deep, VOQ, and the ECN/PFC Ladder
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: Meta SIGCOMM'24 RoCE paper (deep-buffer CTRW/CTSW), IP Infusion / Juniper / Cisco RoCE-CC buffer guidance, section constants bank; fetched 2026-08-25.

## 30-Second Explanation
A switch buffer is the reservoir between a port that wants to send and a port that can't
absorb yet. AI collectives are **synchronized incast** — hundreds of GPUs fire at a
handful of ports in the same instant — and the buffer is what swallows that burst before
queues overflow. Two design philosophies exist: **shallow-buffer** (cut-through, a few
*tens of microseconds* of link) tuned for low constant latency, and **deep-buffer**
(hundreds of microseconds to milliseconds) tuned to absorb incast without dropping.
The buffer is *also* what sets the two signal thresholds that hold a lossless fabric
together — **ECN marking (Kmin/Kmax)** fires first as the queue fills, and **PFC XOFF**
only pauses when the buffer is nearly gone. Getting buffer size wrong in either
direction produces the classic AI-network disease: PFC storms and tail-latency spikes.
This page explains the buffer, the thresholds, and the failure modes.

## What — where the buffer lives and how it's allocated
```text
                          switch silicon
   ingress                │                    egress
   ┌───────────┐          │          ┌──────────────────┐
   │ ingress   │          │          │  egress queues    │  output port N
   │ (minimal) │  shared  │          │  [TC0][TC1]...[TC7]│
   └───────────┘ dynamic  │          └──────────────────┘
                 buffer   │         per-queue thresholds:
                (pool,    │         Kmin → start ECN mark
                 SRAM)    │         Kmax → max ECN prob (Pmax)
                          │         XOFF  → send PFC pause
```
- **Ingress buffering** holds a packet just long enough to look up the FIB and pick a
  port; modern switches are mostly **flat/shared** here. [F: standard]
- **Egress buffering** is where queueing happens: each output port runs per-traffic-class
  queues, and the silicon shares one **SRAM pool** across all of them with dynamic
  thresholds (a busy queue can borrow until a ceiling kicks it out). [F: standard]
- **VOQ (Virtual Output Queueing):** the *architectural* fix for head-of-line blocking.
  Instead of one FIFO per output (where a slow queue for port A stalls packets for port B),
  a VOQ switch keeps a **separate queue per (input, output) pair**, so traffic destined
  for an idle port never queues behind traffic for a congested one. [F: standard]

## Why — microbursts from incast are the real enemy
An AllGather steps like this: every leaf simultaneously pushes to the same aggregate
point. All-to-one **incast** produces a **microburst** far exceeding the average bit rate:
```text
 16 leaves × 50 GB/s each ─┐
                           ├─► spine downlink (50 GB/s)  ← receives ~800 GB/s of
 all fire at one output────┘     instant demand into one queue
```
The average demand on that port is modest, but the *instantaneous* arrival at step start
is many× the port rate. A shallow buffer overflows in the microburst → **PFC pause** (on
lossless) or **drop + Go-Back-N retransmit** (on lossy) — and tail latency blows up on
the strangled flow. [I: incast/collective standard] Buffer policy exists almost entirely
to ride out these microbursts without disturbing the data.

## When — shallow-buffer vs deep-buffer design choice
| | Shallow-buffer (cut-through) | Deep-buffer |
|---|---|---|
| Buffering | ~10–50 µs of link [E, see below] | hundreds of µs – ms |
| Forwarding | cut-through (start egress before full frame) | store-and-forward for large |
| Latency | lowest constant latency | higher mean, absorbs bursts |
| Incast handling | triggers ECN/PFC earlier | absorbs the microburst in-silicon |
| Typical role | leaf/ToR (fast, cheap) | **spine/CLOS agg**, storage, deep-buffer pool |
| Cost | cheap, small SRAM | expensive, large packet memory |

**"10–50 µs of link" is a bytes figure [E]:** from the PFC-threshold rows —
`PFC thr (400G, 1 µs) = 50 KB` and `PFC thr (100G, 1 µs) = 12.5 KB`. So 10 µs at 400G ≈
`10 × 50 KB = 500 KB`, 50 µs ≈ 2.5 MB; at 100G, 10–50 µs ≈ 125 KB–625 KB. A "shallow"
leaf built on a few MB of pool per port is on the order of tens of µs of link — enough to
cover the pause-propagation + a small microburst, not a big one. [E: derived from bank]

**Where deep-buffering earns its keep [F: Meta SIGCOMM'24]:** Meta's production RoCE AI
fabric pairs shallow ToRs with **deep-buffer cluster spines (CTSW)** and reports that
with PFC trusting those deep buffers, the lossless queue **did not persistently trip in
four years** — the deep spine buffer *absorbs* the incast that would otherwise become a
pause wave. That is the empirical argument for deep spines on lossless Ethernet.

## VOQ and head-of-line blocking — why it matters to PFC
Head-of-line (HoL) blocking is the failure PFC makes *worse*. Without VOQ, a single
output port with a full queue blocks every packet behind it in the FIFO, even ones bound
for idle ports. A VOQ switch eliminates that for normal forwarding. The subtle case is
**PFC-induced HoL**: PFC is priority-based and hop-by-hop, so a pause on priority *p*
back-pressures *all* traffic in that priority on the link, not just the congested flow.
A slow receiver's XOFF can therefore stall otherwise-healthy QPs sharing the same
lossless priority — the classic "one bad flow pauses the whole class" failure. Real
fabrics isolate flows with multiple lossless priorities/VLs and keep PFC from running
except as a late backstop. [F: Cisco AI/ML whitepaper (pause spreads upstream); [I]]

## How — buffer size sets the ECN and PFC thresholds
The queue has a ladder. As depth grows, signals fire in order; the *spacing* between
them is set by how much buffer you have:

```text
 buffer depth ─────────────────────────────────────────────►
  0         Kmin        Kmax        XOFF(headroom cap)     100%
  │          │           │           │                      │
  │  absorb  │  ECN:     │  ECN prob  │  PFC: send XOFF      │  drop / watchdog
  │  idler   │  start    │  =Pmax     │  (pause producer)    │  (should never reach)
  │          │  CE-mark  │            │                      │
  └──────────┴───────────┴────────────┴──────────────────────┴───  (deep-buffer pools
                                                                   push XOFF far right)
```
- **ECN (Kmin→Kmax):** once queue depth crosses **Kmin**, the switch writes CE on
  ECN-capable RoCE packets, ramping marking probability linearly to **Pmax at Kmax**
  (WRED-style). The receiver turns CE into a **CNP** back to the sender, which slows its
  rate (DCQCN). ECN is the *early*, end-to-end signal. [F: IP Infusion / Juniper DCQCN]
- **PFC XOFF:** when the queue + headroom cap is reached (XOFF), the port sends a **PFC
  pause frame** to its upstream neighbor to stop feeding it. PFC is the *late*, hop-by-hop
  backstop. [F: 802.1Qbb]
- **The design rule:** ECN must mark *before* PFC pauses, so the fabric spends its time on
  end-to-end CC and keeps PFC in reserve. Buffer sizing is what separates Kmax from XOFF:
  too little room and PFC fires before ECN ever gets to act. [I: standard RoCE-CC guidance]
- **Headroom:** PFC needs a dedicated headroom accounting for pause-propagation delay
  (the bytes already in flight while a pause travels); a typical lossless budget is
  `~80% lossless / ~10% headroom / ~10% lossy` on the pools. [F: vendor ref config]

## How — one queue's evolution over a microburst (the vertical view)
Watch a single egress queue ride an incast burst, top to bottom:
```text
  depth
    ^
  XOFF─────────────────────────────┐  step 5: PFC XOFF pauses the upstream producer
    │                              ▼          (only if the burst outlasted the buffer)
  Kmax───────┐
    │        │  step 4: queue keeps growing toward the cap
  Kmin──┐    ▼
    │   │ step 3: ≥Pmax — sender (via CNP) cuts its rate; ripple starts to drain
    │   ▼
  EC N ┘ step 2: depth>Kmin → switch writes CE; receiver queues a CNP, sender slows
    │
    ▼
  idle     step 1: microburst from incast arrives; buffer absorbs the first bytes
  time ──────────────────────────────────────────────────────────────►
```
- **step 1 idle → fill:** the burst is absorbed; no signal yet.
- **step 2 ECN mark:** depth ≥ Kmin → CE-mark the RoCE packets → CNP to sender.
- **step 3 backoff:** sender's DCQCN drops rate; the queue stops climbing.
- **step 4 fill:** if the burst outpaces the backoff, depth nears the headroom cap.
- **step 5 PFC pause:** XOFF stops the immediate upstream; the queue now drains while the
  elastic demand backs off.
- **drain:** producers recover, queue returns to idle. If the whole ladder is mis-spaced
  (XOFF too close to Kmax), the fabric jumps straight from mark to pause and the *tail*
  pays.

## How to measure it
- Switch `show buffer pools`, `queue-depth` / `occupancy` per-port counters; INT per-hop
  occupancy where available ([40-network-telemetry.md](./40-network-telemetry.md)).
- CNP/ECN counters (`np_cnp_sent`, `np_ecn_marked_roce_packets`) and PFC counters
  (`pfc_xon/xoff`) — a rising XOFF with ECN never firing is the "thresholds mis-spaced"
  signature. [F: mlx5 counters]
- Microburst visibility: per-µs queue-occupancy histograms (gNMI/INT) or `ethtool -S`
  burst counters; average utilization hides the burst that matters.

## Failure modes — the tail-latency consequences of mis-sized buffers
- **Too shallow:** incast overflows before ECN/CNP round-trip → PFC pause fires eagerly →
  head-of-line blocking spreads to unrelated QPs on the same priority → **P99/P99.9
  jitter spikes**, and in the worst case a **pause storm** (E CN/PFC threshold
  misalignment: ECN never marks before pause). [F: IP Infusion "pause storms even with
  DCQCN configured"; [I]]
- **ECN too eager (Kmin too low):** marking starts while the queue is trivially busy →
  DCQCN over-reacts → sender collapses its rate → **bandwidth "sawtooth"** and a huge gap
  between single-QP and multi-QP throughput. [I: DCQCN tuning]
- **PFC headroom under-sized:** a pause frame's in-flight bytes overflow the headroom →
  drop + Go-Back-N even on a "lossless" fabric → the exact retransmit cost PFC was meant
  to avoid. [I]
- **Deep-buffer everywhere:** you pay latency/power for sinks you rarely touch; deep
  buffers belong at congestion points (spines, storage), not in every leaf. [I]

## Example — sizing the pause headroom by the numbers
A 400G spine downlink that must absorb a pause's propagation (say 2 µs of fabric round
trip): the headroom must hold `2 µs × 50 KB/µs = 100 KB` of in-flight data
(`[E] PFC thr (400G,1us) = 50 KB`, so 2 µs = 100 KB) **plus** a microburst margin above
the XOFF pointer. If an operator sets XOFF at 8 MB on a 16 MB pool, that leaves ~8 MB to
cover both headroom and burst — a typical deep-buffer config; a naive 2 MB pool with
XOFF at 1 MB has only ~1 MB left, which a 16-leaf incast (16 × 50 GB/s = 800 GB/s aggregate)
can exhaust in ~1.3 µs [E: 1 MB ÷ 800 GB/s = 1.25 µs] — i.e. **before** the 2 µs
pause-propagation headroom can help. The *spacing* between ECN-Kmax and PFC-XOFF is the whole game; the numbers
above make the arithmetic concrete. [E: PFC-threshold rows + [I] sizing logic]

## Key Takeaways
1. The buffer is the reservoir that absorbs synchronized incast microbursts — the enemy is *instantaneous* all-to-one demand (many leaves firing at one spine downlink), not average load ([./40-network-telemetry.md](./40-network-telemetry.md)).
2. Shallow buffers (tens of µs of link) suit leaves; deep buffers (hundreds of µs–ms) belong where incast lands (spines, storage) — Meta's deep-buffer spine reports PFC never persistently tripping in four years, not as a substitute for correct thresholds ([./23-roce-lossless-fabric-design.md](./23-roce-lossless-fabric-design.md)).
3. Buffer depth sets the signal ladder: ECN marks (Kmin→Kmax) must fire before PFC XOFF pauses; if XOFF sits too close to Kmax the fabric jumps straight from mark to pause and tail latency pays ([./22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md), [./40-network-telemetry.md](./40-network-telemetry.md)).
4. Size PFC headroom for pause-propagation bytes plus a microburst margin — 2 µs at 400G needs ~100 KB of in-flight above the XOFF pointer; too little headroom means drops even on a "lossless" fabric.
5. Mis-sized buffers surface as P99/P99.9 jitter and pause storms that back-pressurize unrelated QPs on the same lossless priority — the fix is re-spacing thresholds, not more raw capacity everywhere ([./38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md), [./45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md)).

## Related
- [40-network-telemetry.md](./40-network-telemetry.md) — the counters that reveal queue/threshold health.
- [./21-dcqcn.md](./21-dcqcn.md) / [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md) — DCQCN PFC/ECN loop.
- [./18-data-center-bridging.md](./18-data-center-bridging.md) — PFC mechanics in depth.
- [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md) — where buffers sit (leaf vs spine).
- [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md) / [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md) — buffer
  failure symptomatic trees.
- [17-troubleshooting.md](../GPU-Communication/17-troubleshooting.md) — cross-section queue/incast view.

## References
- [F] Meta, "RDMA over Ethernet for Distributed AI Training at Meta Scale," SIGCOMM 2024 —
  deep-buffer spine + PFC-never-tripped datapoint.
- [F] IP Infusion DCQCN explainer; Juniper DCQCN buffer/headroom config; Cisco AI/ML
  whitepaper (pause spreading, PFC watchdog).
- [E] PFC-threshold rows (100G 1µs = 12.5 KB; 400G 1µs = 50 KB) and serialization row
  (100 MB @ 50 GB/s = 2.0 ms) from the section constants bank, computed 2026-08-25.
