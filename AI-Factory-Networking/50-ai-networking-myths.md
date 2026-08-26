# Ten AI-Networking Myths, Debunked
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: IETF RoCEv2 draft, IBTA/NVIDIA IB docs, UEC 1.0 spec + author paper, Meta RoCE blog, IRN SIGCOMM'18; fetched 2026-08-25.

## 30-Second Explanation
AI networking has attracted a shelf of half-truths — "RoCE is just Ethernet", "more buffers is
better", "RDMA means the CPU never works", "zero drops = it's fast". Most of these feel true
because they name a real technology, but they miss the *engineering* that separates a working
fabric from one that looks fine on paper. This page debunks ten of them with the tag discipline
used across the section: `[F]` sourced fact, `[E]` arithmetic computed this session, `[I]`
inference. The through-line: **a fabric performs at the speed of its worst, most misunderstood
bottleneck — headroom, entropy, latency term, or tail — not its nominal port rate.**

## Myth 1 — "RoCE is just Ethernet"
> RoCE is just Ethernet with extra steps.

**Why it feels true:** it traverses Ethernet frames and standard switches look at it like UDP.
**Refutation [F]:** RoCEv2 is InfiniBand's *transport* (BTH, PSN, RC semantics) carried inside a
UDP/IP Ethernet frame (UDP 4791) [F: IETF Fast-CNP draft]. It is not the default behavior of
Ethernet at all: plain Ethernet is lossy and gives you no ordering, no RDMA, no reliable connection.
RoCE's losslessness *is engineered policy* — you add **PFC + ECN/DCQCN + QoS/DSCP** or RDMA
collapses under the very first drop (Go-Back-N retransmit) [I/F: IRN]. "Just Ethernet" is exactly
the configuration that breaks it.

## Myth 2 — "InfiniBand is simply faster Ethernet"
> InfiniBand is just Ethernet that goes faster.

**Why it feels true:** both carry packets between servers and both see "400/800 Gb/s".
**Refutation [F]:** they differ at the *link, control-plane, and addressing* layers:
- **Link layer:** IB uses **credit-based flow control** (a packet is sent only when the receiver
  has credit), making losslessness a *property of the hardware* [F: IB credit-loops doc]; Ethernet
  is lossy by default and needs PFC to fake it.
- **Control plane:** IB has a **Subnet Manager (SM)** that discovers the fabric and programs
  forwarding/LIDs/QoS; Ethernet has IP routing + distributed protocols [F: NVIDIA IB security doc].
- **Addressing:** IB uses **LID** (LRH, per-hop) + **GID** (GRH, inter-subnet); Ethernet uses
  **MAC/IP** [F: IB header doc].
Two different animals that happen to move bytes quickly.

## Myth 3 — "PFC alone makes Ethernet lossless"
> Turn on PFC and the network is lossless.

**Why it feels true:** PFC is the thing people call "lossless Ethernet", and the toggle exists.
**Refutation [F]:** PFC is a **reactive, per-priority pause** (IEEE 802.1Qbb) — when a buffer fills,
it sends an XOFF that pauses that priority class and back-pressures upstream [F: 802.1Qbb/Juniper].
It cannot *prevent* congestion; it can only spread it, and it is vulnerable to **head-of-line
blocking and pause storms / deadlocks** (a circular-pause state where nothing progresses) [F:
Cisco AI/networking whitepaper; IP Infusion]. Real "lossless" RoCE is a *system*: **ECN marks before
the queue hits the PFC threshold, DCQCN slows the sender, QoS/dedicated buffer headroom absorbs
the pause propagation delay** [F: IP Infusion DCQCN]. PFC is one backstop, not the whole answer.

## Myth 4 — "400G Ethernet always gives 400 Gb/s app throughput"
> A 400 Gb/s NIC moves 400 Gb/s of your data.

**Why it feels true:** that's the number on the box, and line rates are everywhere in marketing.
**Refutation [E]:** the RoCEv2 header is **58 B/packet** (Eth+IPv4+UDP+BTH+ICRC). As a fraction of
payload [E computed 2026-08-25]:
| Payload | header overhead | payload/(frame) |
|---|---|---|
| 256 B | 22.66% | 81.5% |
| 1500 B | 3.87% | 96.3% |
| 4096 B | 1.42% | 98.6% |
| 8942 B (jumbo) | 0.65% | 99.4% |
So header-only efficiency at jumbo is ~99% [E] — but realized *app throughput* lands closer to
**~90–95% of line at large messages** and **far less for small ones** [I], because of PPS ceilings
(a 400 GbE link tops out at **32.9 Mpps @ 1518 B** but only **5.5 Mpps @ 9018 B** [E]),
congestion-control backoff, and contention. At 256 B messages the per-packet overhead alone burns
~18.5% of the line. "400 Gb/s" is a *line* rate, never an app guarantee.

## Myth 5 — "More switch buffers always improve AI performance"
> Bigger buffers = more headroom = better.

**Why it feels true:** drops are bad, and buffers prevent drops.
**Refutation [I/F]:** buffers size the *reaction* of PFC and ECN. **Too much depth delays both** —
the queue builds for longer before the lossless pushback or ECN marking fires, so end-to-end
congestion control reacts late, exactly the "pause storms even with DCQCN configured" failure from
misaligned ECN/PFC thresholds [F: IP Infusion]. The hardware detail that wins is not raw depth but
**having the CC thresholds sit below the PFC headroom** — buffer budget must *match* the reaction
latencies of ECN and PFC, and deep buffers raise tail latency on the lossless queue [I]. More isn't
better; *tuned* is better. A useful tension to remember: the buffer that absorbs an incast burst is
the same buffer that delays the ECN mark that would have made the burst unnecessary [I].

## Myth 6 — "ECMP automatically balances GPU traffic"
> Hash-based multipath spreads my flows evenly.

**Why it feels true:** ECMP is the default, and routers don't complain.
**Refutation [F/I]:** RoCEv2's destination UDP port is fixed (**4791**), so the hash key collapses
to (src IP, dest IP, **UDP src port**) — and a training node runs only a *few tens of QPs*, so there
are few distinct 5-tuples to spread [F: Meta "RoCE networks for distributed AI training at scale";
[I]]. Result: unrelated elephant flows hash to the **same link**, and a single bad collision can
halve effective bandwidth. [F: Meta blog reports hash-collision losses; the classic case is two
flows on two uplinks both landing on one → the other sits idle → **~50% bandwidth loss**.] The real
answers are per-QP entropy in the UDP **source** port, and adaptive **flowlet / DLB / MRC spraying**
rather than static ECMP [F: Broadcom DLB; OpenAI MRC]. ECMP without entropy is hope.

## Myth 7 — "RDMA means the CPU is never involved"
> The whole point is that the CPU stays out of the data path.

**Why it feels true:** kernel-bypass zero-copy keeps bulk data off the CPU.
**Refutation [F/I]:** RDMA offloads the **data path**, not the whole job. **Registration**, **QP
setup**, **CQ polling**, and all **small-message** handling still touch the CPU; the control plane
(verbs, work requests) is software [I]. Only the wire-speed *payload* is DMA'd HCA↔GPU/memory
without host staging [F: RDMA verbs model]. GPUDirect removes the CPU from the *data* hop, but a CPU
is still scheduling the work. "RDMA = no CPU" overstates what's accelerated.

## Myth 8 — "NVLink replaces the backend network"
> Scale-up is so fast I don't need InfiniBand/RoCE anymore.

**Why it feels true:** NVL72's NVLink domain runs ~1.8 TB/s/GPU and ~130 TB/s aggregate, and the
GB200 NVL576 (8 racks, 576 GPUs) extends *one* NVLink domain to 576 GPUs [F: NVIDIA], dwarfing a
400–800 Gb/s NIC by orders of magnitude.
**Refutation [F/I]:** scale-up is **bounded** — even the NVL576's 576-GPU NVLink domain is a hard
edge: it is one (very large) domain, not a scaling fabric. A job that exceeds that domain (a
1,000- or 10,000-GPU training cluster) must cross into **scale-out** over the backend network
(IB/RoCE), over an order of magnitude slower per GPU than in-domain NVLink, and collectives that
cross that boundary pay the backend's cost [F/I: NVL72/NVL576 topology]. "NVLink replaces the
backend" is false because the NVLink domain is finite; the backend fabric is what makes *clusters*
of domains talk to each other. (NVLink5/6 keep growing the domain — NVL576 now, larger domains
announced on later platforms — but each generation still has an edge.)

## Myth 9 — "UET is simply RoCEv3"
> Ultra Ethernet is just the next RoCE.

**Why it feels true:** both are "RDMA over Ethernet", and "v3" sounds like a natural step.
**Refutation [F] (UEC 1.0):** UET changes the *transport model*, not just a version bump:
- **Connectionless**: ephemeral Packet Delivery Contexts with 0-RTT setup — no QP/connection
  handshake or per-peer connected state [F: UEC spec].
- **Per-packet spraying**: an Entropy Value in the UDP source-port position drives per-packet path
  selection across all equal-cost paths [F: UEC].
- **RUD (Reliable Unordered Delivery)**: the default is *unordered* with zero-copy placement — no
  reorder buffer required; RoCEv2/IB RC is strict in-order Go-Back-N [F: UEC].
- **NSCC** (sender, ECN+RTT+trimming) vs DCQCN/CNP; and UET is **lossy-capable** — designed for
  best-effort, with PFC kept only as an option [F: UEC].
- Critically, there is **no "v3" of the IB transport** — RoCEv2's semantics are what they are;
  "RoCEv3" is not an IBTA-defined term, and UET is a *different* transport, not a RoCE revision
  [F: UEC internal architecture; [I: "no RoCEv3" is not IBTA-defined]]. UET is not RoCEv3 — it is
  a clean-slate sibling.

## Myth 10 — "Zero drops means the network performs well"
> No dropped packets = healthy, fast network.

**Why it feels true:** drops are the obvious disaster, so their absence must be success.
**Refutation [I]:** zero *drops* hides a lot. An IB or PFC/RoCE fabric can run zero-drop while
suffering **PFC stalls** (a pause propagates and idles unrelated flows), **rising queue latency**
(on a lossless priority, packets wait in deep queues), and **polarization** (one spine hot, its
peers idle, flows reordered) — all invisible in a drop counter [I]. The number to chase is
**goodput and tail latency** on the actual workload (perftest/nccl-tests busbw, P99 collective
time), not the drop count. Zero drops is table-stakes; it says nothing about whether the fabric is
*fast* [I].

## The debunked list at a glance
| # | Myth | One-line truth |
|---|---|---|
| 1 | RoCE is just Ethernet | It's IB transport in UDP; losslessness is engineered policy |
| 2 | IB is faster Ethernet | Different link layer (credits), control plane (SM), addressing (LID/GID) |
| 3 | PFC alone = lossless | Reactive per-priority pause; needs ECN+QoS+headroom as a system |
| 4 | 400G = 400 Gb/s app | Header + PPS ceilings + CC; ~90–95% of line at large, far less small |
| 5 | More buffers better | Deep buffers delay PFC/ECN reaction; must match CC thresholds |
| 6 | ECMP balances GPU traffic | Low entropy (4791) → hash collisions → ~50% loss [F: Meta] |
| 7 | RDMA = no CPU | Data path offloaded; registration/QP/CQ/small msgs touch CPU |
| 8 | NVLink replaces backend | Scale-up is rack-local; 72-GPU domain ≠ cluster |
| 9 | UET is RoCEv3 | Connectionless, spray, RUD no-reorder, NSCC, lossy-capable — a sibling, not a v3 |
| 10 | Zero drops = good | PFC stalls/queue latency/polarization hide; measure goodput/tail |

## Related
- [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md) — where the "myth 10" hidden failures actually show up.
- [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md) — myth 3/5/6's failures in the symptom table.
- [49-design-decision-tree.md](./49-design-decision-tree.md) — myth 8/9's real design tradeoffs.
- [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md) — goodput/tail vs drop counters.
- [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md) — where the latency term multiplies (myth 8).


## Key Takeaways
1. Most AI-networking myths name a real technology but miss the engineering — RoCE's losslessness,
   IB's credit control plane, ECMP's entropy limits — and a fabric performs at the speed of its
   worst, most misunderstood bottleneck, not its nominal port rate.
2. "Lossless" is a system, not a toggle: PFC is a reactive per-priority pause that spreads
   congestion and can deadlock; real RoCE needs ECN to mark before the PFC threshold, DCQCN to slow
   the sender, and buffer headroom to absorb pause propagation.
3. "400 Gb/s" is a line rate, never an app guarantee: the 58 B RoCEv2 header plus PPS ceilings
   (32.9 Mpps @1518B, 5.5 Mpps @9018B) plus CC/contention land realized throughput near ~90–95% of
   line at large messages and far less for small ones.
4. More buffer is not better — deep buffers delay the PFC/ECN reaction, and the buffer that absorbs
   an incast burst is the same buffer that delays the ECN mark that would have made it unnecessary;
   *tuned* beats *big*.
5. Two "free" fixes hide real cost: ECMP without entropy is hope (fixed 4791 + few QPs → hash
   collisions → ~50% loss; fix with per-QP src-port entropy / DLB/MRC), and zero drops says nothing
   about speed — PFC stalls, queue latency, and polarization hide behind a clean drop counter, so
   measure goodput and tail latency.

## References
- IETF RoCEv2 Fast-CNP draft — 58 B header, UDP 4791, CNP/ECN signaling.
- IEEE 802.1Qbb — per-priority pause (myth 3).
- Cisco AI/networking whitepaper; IP Infusion DCQCN — pause storms/deadlocks (myths 3, 5).
- Meta "RoCE networks for distributed AI training at scale" — ECMP hash-collision loss (myth 6).
- NVIDIA NVL72/NVL576 vendor docs — domain-local scale-up bandwidth (myth 8).
- UEC 1.0 spec — connectionless PDCs, per-packet EV spray, RUD, NSCC (myth 9).
- [E] Constants: RoCEv2 header-overhead table (256B 22.66%, 1500B 3.87%, 4096B 1.42%, 8942B 0.65%);
  400GbE PPS 32.9 Mpps @1518B vs 5.5 Mpps @9018B.
