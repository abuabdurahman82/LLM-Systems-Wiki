# InfiniBand Congestion Control & Adaptive Routing
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: NVIDIA InfiniBand Adaptive Routing whitepaper (vendor), NVIDIA credit-loop & OpenSM docs, NCCL environment-variable documentation, NVIDIA nccl issue #1687; fetched 2026-08-25.

## 30-Second Explanation
InfiniBand is **lossless by credit flow control** (sender only transmits what the receiver
has buffer credits for), which is great for reliability but turns congestion into
*backpressure* instead of *packets dropped* [F: NVIDIA credit-loop article]. A hot flow
fills a switch's egress buffer; the switch stops advertising credits; the *upstream* NIC
stalls — potentially all the way back to the source HCA. That is "credit starvation
propagation." The fabric protects itself with a **head-of-queue (HOQ) timeout** as the only
deliberate drop path [F]. You fight congestion two ways: **congestion signals** (BECN/ECN-class
notifications, vendor telemetry) that tell senders to slow down, and **adaptive routing (AR)**,
which avoids the hot link in the first place by spraying packets across multiple paths as the
switch sees congestion build. AR delivers packets **out of order**, so the NIC must reorder —
**ConnectX-5 and above include in-hardware out-of-order placement** and use the **DC transport**
[F: NVIDIA AR whitepaper]. This is why modern IB keeps fabric utilization high where
deterministic fat-tree routing would leave idle links. See [12-infiniband-routing-topology-partitions.md](./12-infiniband-routing-topology-partitions.md)
for the deterministic-vs-AR framing.

## Congestion in a credit fabric

### What
Because credits make loss costly-but-not-fatal, congestion shows up as **stalls and growing
queues**, not drops. Four canonical patterns:

1. **Hot spots** — many flows hash/route to one link (symmetric fat-tree polarization, or a
   popular destination); that egress port saturates while neighbors idle.
2. **Incast into shallow credit buffers** — a collective (all-gather, reduce) fans many
   senders into one receiver's port; the receiver's per-VL buffer (and the link's capacity)
   is small relative to the burst, so credits clamp.
3. **Credit starvation propagation** — the congested egress stops releasing credits; the
   upstream port's buffer fills; it stops *its* upstream credits; the stall walks hop-by-hop
   back toward the source HCA. A single hot link can back up a whole branch of the fabric.
   [F: NVIDIA credit-loop article; mechanics of lossless backpressure]
4. **Head-of-queue (HOQ) timeout** — the SM-configured guard that *deliberately drops* a
   packet that has sat too long behind a blocked queue; the only intentional IB drop path,
   used to break deadlocks rather than to shed valid load [F: credit-loop article].

```text
source HCA ──► (stall) ◄──credit withheld── switch B buffer full
                                        ▲
                            credit withheld (backpressure walks upstream)
                                        ▲
              switch A buffer full ◄── traffic to hot port
                                        ▲
              many senders ─────────────┘ (incast → shallow per-VL buffer)
```

### Why it matters
Lossless fabrics trade drops for **latency spikes**: a backpressured ring step in NCCL delays
every GPU behind the straggler. Because AI collectives are synchronized, one hot link's stall
becomes the job's tail latency [I: standard systems argument, see ./01]. So IB needs
congestion *management* even though it never "loses" packets.

## Congestion signals: BECN / ECN-class and vendor telemetry

### What
IB provides an in-band congestion-notification path but it has never been universally
deployed; the practical signals are:
- **BECN / CNP-class** packets — an IB congestion-notification message (related to the CNP
  family in the IB spec; the research notes flag "CND" as a non-standard term — the real
  opcode is CNP/BECN [F: IB transport opcodes via man page]).
- **ECN-class marking** — on RoCE this is the DCQCN ECN/CNP loop; on native IB, per-VL
  queue-depth telemetry is the analog [I: comparison].
- **Vendor telemetry** — NVIDIA UFM/MLNX counters expose queue-depth, credit stalls, and
  port error counters (`ibqueryerrors`, `perfquery`, `ibdiagnet`) that surface congestion
  after the fact [F: NVIDIA counter docs].

The **switch-driven** congestion avoidance on modern Quantum switches works with **adaptive
routing**: the switch monitors its egress queues in real time and, on congestion, reroutes
incoming packets away from the hot output rather than relying on slow endpoint feedback [F:
NVIDIA AR whitepaper; Quantum-2 "advanced adaptive routing, congestion control"].

## Adaptive routing

### What
Adaptive routing moves the path decision from "computed once, fixed" to "re-evaluated by the
switch as traffic flows": the switch forwards each packet toward a next hop whose queue is
less congested. This is **per-packet spray** — different packets of the *same flow* can take
different links, so they can arrive **out of order** [F: NVIDIA AR whitepaper].

### How the out-of-order problem is solved
```text
Deterministic fabric:           Adaptive fabric:
  packet1 --S1--> --S2--> D        packet1 --S1--> --S2a-> D
  packet2 --S1--> --S2--> D        packet2 --S1--> --S2b-> D   (different path!
  in-order by construction         packet3 --S1--> --S2c-> D     OOO delivery)
                                                     ↓
                                     receiver HCA reorders in hardware
                                     (ConnectX-5+ in-HW OOO placement) [F]
```
Two requirements make this workable [F: NVIDIA AR whitepaper]:
1. **NIC hardware out-of-order placement** — ConnectX-5 and above can place OOO-received data
   into memory directly; without it the NIC (or transport) must buffer/reorder.
2. **DC (Dynamically Connected) transport** — NCCL's default on IB tolerates reordering;
   RC is usable only because the NIC's OOO engine covers it [F].

### NCCL integration
NCCL turns AR on by default on InfiniBand via **`NCCL_IB_ADAPTIVE_ROUTING=1`** (default on IB),
paired with an AR-enabled **`NCCL_IB_SL`** that the fabric admin has mapped to an AR-capable
service level [F: NVIDIA NCCL environment docs]. A **known limitation**: packets carrying
**immediate data are not AR-eligible** — the switches do not adaptively route them, and NCCL
accounts for this [F: NVIDIA/nccl issue #1687]. Concretely: AR helps bulk gradient/activation
traffic across the fat tree; it does not apply to the small immediate-data control packets.

### When to use it
Use AR when: the fabric is a fat tree with many equal paths (AR flourishes on symmetric
Clos), the workload has many concurrent flows (AllToAll, tree-reduce, MoE dispatch), and the
NICs are ConnectX-5+ (HW OOO). It is less critical on Dragonfly where DOR already spreads
load by dimension. [I: standard practice]

## Deterministic vs adaptive — the decision table
| Dimension | Deterministic (MinHop/fat-tree/DOR) | Adaptive (AR) |
|---|---|---|
| Path lifetime | fixed at SM route computation | re-chosen per packet at each switch |
| Ordering | in-order by construction | OOO possible → HW OOO + DC transport |
| Hot-spot response | none at data plane (switches don't react) | reroute away from congested egress |
| Fabric utilization under skew | lower (idle links + hot links) | higher (sprays into idle capacity) |
| NIC HW requirement | any | ConnectX-5+ OOO placement [F] |
| Transport compatibility | any (RC/UC/DC/UD) | DC (NCCL default), RC w/ NIC OOO [F] |
| Reproducibility / debuggability | high (deterministic path) | lower (path varies per packet) |
| NCCL switch | `NCCL_IB_ADAPTIVE_ROUTING=0` | `=1` (default on IB) [F: NCCL docs] |

## How modern IB keeps fabric utilization high
Putting it together: (a) pick a deadlock-free engine for the topology ([F] OpenSM fat-tree /
DOR), (b) let **adaptive routing** reroute around congestion in the data plane [F: NVIDIA AR
whitepaper], (c) solve the resulting reordering in **NIC hardware** so RC/DC semantics hold
[F], and (d) keep congestion *signals* (telemetry, CNP-class) as the feedback that tunes rates
and catches residual hotspots [I]. The result is a fabric that runs collectives near the
information-theoretic busbw limit even under skew — measured with nccl-tests
([44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md)).

## Failure modes
- **AR enabled with a NIC lacking HW OOO** → silent OOO data corruption/completion errors.
- **Immediate-data packets mis-handled** → NCCL tracks AR-ineligibility, but a manual
  override can route them onto a congested path.
- **HOQ timeout too low** → deliberate drops under legitimate bursts look like loss.
- **NCCL_IB_SL not AR-enabled in the SM** → AR flag set but the fabric doesn't adapt.

## How to measure it
`nccl-tests all_reduce_perf` busbw vs theoretical link rate (busbw = algbw·2(n−1)/n [E: bank])
tells you if the fabric is delivering; `NCCL_DEBUG=INFO`/`DEBUG_SUBSYS=NET` shows transport
and HCA selection; `ibqueryerrors`/`ibdiagnet` for credit-stall and port-error telemetry.
→ [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md) and [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md).

## Key Takeaways
1. Lossless IB turns congestion into **credit backpressure**, not drops; HOQ timeout is the
   only deliberate drop [F].
2. Modern IB reacts with **adaptive routing** — per-packet spray away from hot egress [F].
3. Spray ⇒ **out-of-order**; ConnectX-5+ HW OOO + DC transport make it correct [F].
4. NCCL enables AR by default on IB (`NCCL_IB_ADAPTIVE_ROUTING=1`); immediate-data packets
   aren't AR-eligible [F: NCCL docs + issue].
5. Deterministic = reproducible, hot-spot-prone; adaptive = higher utilization, needs HW OOO.

## Related
- [12-infiniband-routing-topology-partitions.md](./12-infiniband-routing-topology-partitions.md) — routing engines + topology context.
- [05-infiniband-architecture.md](./05-infiniband-architecture.md) — layers, VLs, credit flow control.
- [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md) — measuring busbw/utilization.
- [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md) — NCCL transports and topology discovery.
- [09-infiniband-packet-format.md](./09-infiniband-packet-format.md) — BTH opcodes incl. CNP/BECN.

## References
- NVIDIA *InfiniBand Adaptive Routing* whitepaper (vendor): resources.nvidia.com/en-us-accelerated-networking-resource-library/infiniband-white-paper-adaptive-routing [F].
- NVIDIA credit-loop / losslessness: enterprise-support.nvidia.com/s/article/howto-prevent-infiniband-credit-loops [F].
- NCCL env vars (ADAPTIVE_ROUTING, SL, GID): docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html [F: NCCL docs].
- NCCL immediate-data AR limitation: github.com/NVIDIA/nccl/issues/1687 [F: nccl issue].
- Quantum-2 "advanced adaptive routing, congestion control": nvidia.com/en-us/networking/quantum2 [F: vendor claim].
- [E] busbw relation from the section constants bank (computed 2026-08-25).
