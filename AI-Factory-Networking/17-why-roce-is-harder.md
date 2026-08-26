# Why RDMA over Lossy Ethernet Hurts
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: IRN SIGCOMM'18 (DOI 10.1145/3230543.3230557), IBTA/IANA RoCEv2, vendor lossless configs; arithmetic from section constants bank (2026-08-25).

## 30-Second Explanation
RDMA (and specifically RoCEv2) was designed for a **lossless** fabric. Its Reliable
Connection (RC) transport retransmits with **Go-Back-N**: it has *no TCP-style
selective ACK*, so a single dropped packet forces the sender to retransmit from the
last *successfully delivered* PSN onward, resending perfectly good packets in a burst
[F: SIGCOMM'18 IRN, DOI 10.1145/3230543.3230557]. On an ordinary **lossy Ethernet**
network — where TCP's gentle selective recovery does fine — RDMA's retransmission is
both heavy and slow, so performance **collapses** as soon as any drop happens [E]. AI
collectives then make it worse: all-gather/all-reduce synchronize thousands of GPUs
that hit the same switch queue at once, creating **incast** into shallow switch buffers
and **microbursts**. The industry answer is not to make Ethernet drops harmless but to
make the network **lossless by policy** — Priority Flow Control (PFC) back-stops the
buffer, Early Congestion Notification (ECN) marks packets so senders slow down *before*
the buffer overflows. Net: on AI fabrics, Ethernet is engineered to *never drop the
RoCE class at all*; the loss is removed by policy, not tolerated by the transport.

### What
RDMA's Data-Centric transports were inherited wholesale from InfiniBand, which is
**credit flow-controlled and therefore lossless by design** (a receiver tells the
sender exactly how much on-wire data it can accept; no credit, no send). When that same
transport is carried over UDP/IP on Ethernet ([16-roce-fundamentals.md](./16-roce-fundamentals.md)), the credit
layer is gone — Ethernet has no per-flow credits — yet the RC transport still assumes
the network will not lose packets. The mismatch is the whole story of this page:
**the transport believes the fabric is lossless; Ethernet is not; therefore the fabric
must be made to behave losslessly or the transport stalls.**

### Why
Three compounding reasons make loss the enemy of RDMA on Ethernet:

1. **Go-Back-N retransmission** — RC tracks packet sequence numbers (PSN). On a drop,
   the *receiver* responds with a NAK (or silently times out), and the *sender*
   retransmits **everything from the last delivered PSN onward**, not just the one lost
   packet [F: SIGCOMM'18 IRN, DOI 10.1145/3230543.3230557; arXiv:1806.08159 UNVERIFIED —
   ID taken from ResearchGate DOI metadata]. Put one drop in the middle of a 1 MB
   message and you re-transmit half of it. TCP, by contrast, has selective ACK (SACK)
   and recovers just the gap.

```text
Go-Back-N (RDMA RC):  one drop ⇒ resend everything after it
sender PSN:  1  2  3  [4 *dropped at switch*]  5  6  7  8
receiver:    1  2  3  .            .  .  .  .   → NAK at 4
sender:      1  2  3  4  5  6  7  8  4  5  6  7  8   ← good pkts 5-8 resent!

TCP + SACK:   one gap ⇒ resend only the missing packet
sender:       1  2  3  [4 lost]  5  6  7  8   → SACK block says "only 4 missing"
sender:       4                                        ← 1 packet resent
```
2. **Throughput collapse, not graceful degradation** — RDMA reaches full line rate
   *only* when lossless; the moment retransmission begins, measured throughput drops
   sharply rather than sliding smoothly [E: widely reproduced field result — e.g.
   lossless-RDMA deployment guides]. The curve is cliff-like, not gradual.
3. **The loss is almost never "just one packet"** — AI collectives synchronize many
   senders onto one receiver's queue (incast) and synchronized iteration boundaries
   (microbursts); when one packet drops, hundreds nearby are in the same burst and drop
   too, so Go-Back-N resends a storm.

### When
Loss hurts most where the buffer the sender is hammering is small relative to the burst:
- **Incast at the receiver** — N GPUs all-gather to one GPU; the receiver's ingress
  queue overflows first [E: PFC thr (400G,1us) = 50 KB of buffer absorbs only ~1 µs of
  line rate — see [18-data-center-bridging.md](./18-data-center-bridging.md)].
- **Switch egress microbursts** — many flows hash to the same spine uplink for a few
  hundred nanoseconds and overflow the shallow shared buffer.
- **Synchronized collectives** — every GPU issues its AllGather at the same epoch, so
  the fabric sees periodic synchronized floods, not steady traffic.

```text
Incast / microburst into a shallow switch buffer:
 4 GPUs ──────────┐
 4 GPUs ──────────┼─►  [switch egress queue: 50 KB headroom]  ─► 1 GPU (receiver)
 4 GPUs ──────────┤      bursts arrive in the same µs window [E: 50 KB @400G·1µs]
 8 GPUs ──────────┘      queue overflows → drops → Go-Back-N → collapse
```

### Hardware impact
- The **NIC** must carry a reorder/retransmit engine sized for the lossless assumption;
  hardware Go-Back-N resend buffers and the retransmit path add silicon and, on loss,
  burn the host bus re-sending.
- The **switch** must provision buffer specifically so the *RoCE class never drops* —
  which is exactly what PFC headroom partitions buy (see [18-data-center-bridging.md](./18-data-center-bridging.md)).
  A lossy Ethernet switch (default shared buffer, drop-tail) is the worst possible
  substrate for stock RoCEv2 RC.
- **Packet-size asymmetry** amplifies the effect: RoCE commonly runs jumbo (MTU ~9000).
  A 58 B header on a 1500 B frame is 3.87 % overhead but on a 256 B packet is 22.66 %
  [E], so small-message collectives carry a far larger share of retransmission cost
  *and* more packets per byte, each of which is a candidate loss point
  [E: RoCEv2 overhead @1500B = 3.87 %; @256B = 22.66 %]. Jumbo cuts PPS demand too:
  a 100 Gb/s line carries only ~1.39 Mpps at 9018 B vs ~8.23 Mpps at 1518 B [E] — fewer
  packets, fewer things to lose, cheaper retransmit granularity.

The asymmetry cuts two ways. **Large packets** amortize the 58 B header ([E] above: 4096 B
payload → 1.42 % [E: RoCEv2 overhead @4096B = 1.42 %]) and reduce PPS, but a single lost
jumbo frame forces a Go-Back-N resend of a *large* amount of data. **Small packets**
(e.g. 256 B) waste 22.66 % of the wire on headers, double the PPS (more loss candidates,
more switch descriptor work), but each loss re-sends less raw payload. AI collectives mix
both: metadata/small control messages at tiny sizes, data tensors at jumbo. The net
operational rule: run jumbo on the RoCE class to cut PPS/overhead, and rely on PFC+ECN
([18-data-center-bridging.md](./18-data-center-bridging.md), [20-ecn-wred.md](./20-ecn-wred.md)) to make the *rare* jumbo loss never
occur — because when a 9 KB frame is lost mid-burst, Go-Back-N's amplification is at its
worst. [I]

### Inference impact
For **inference-serving** (prefill/decode with many small flows), the sharp edge of
loss shows up as **tail latency**: a single Go-Back-N resend turns a ~2–3 µs hop into
a tens-of-microseconds stall, and synchronized prompt-batching re-creates the incast
condition that triggers it. Microsecond jitter is exactly what an LLM token-loop
cannot absorb; decoding is latency-bound, so loss ≠ just bandwidth loss but *deadline*
misses. [I]

Concretely: if a batch of prompts faults at a shared switch uplink and drops one packet
into a mid-collective AllGather, entries in flight across the whole group are held up by
the Go-Back-N resend storm. A 100 MB collective resending half its volume at 50 GB/s
adds ~1 ms [E: ½ × ser(100MB @50 GB/s); ser = 100 MB / 50 GB/s = 2.0 ms → half the volume
= 50 MB → 1.0 ms] to what is normally sub-100 µs — that is
an order-of-magnitude tail event on a per-decode basis. Prefill is throughput-bound and
absorbs it as a hiccup; decode is latency-bound and the user sees a stall. [I]

### Example — why one drop dominates
Say a 100 MB message is in flight between two GPUs at 50 GB/s (a 400 Gb/s RoCE link)
[E: 400 Gb/s = 50 GB/s]. A single drop in the middle forces a Go-Back-N resend of the
*succeeding* half — ~50 MB re-transmitted. At 50 GB/s that alone costs 1.0 ms
[E: ser 100MB @50GB/s = 2.0 ms → half the volume ≈ 1.0 ms], on top of the added
round-trip and the reorder. A modern TCP with SACK would resend a handful of packets
and cost ~one RTT. That asymmetry — milliseconds vs one RTT — is why PFC+ECN exist:
the fabric spends its effort *preventing* the drop, not recovering from it.

### Failure modes
- **Drop → Go-Back-N storm**: one loss becomes a burst of resends, re-entering the same
  congested queue.
- **Retransmission amplification**: each lost packet inflates on-wire traffic,
  worsening the very congestion that caused the loss.
- **Throughput cliff**: the fabric never re-synchronizes cleanly, so utilization stays
  pegged at a fraction of line rate.
- **P99 spikes under incast**: burst arrival exceeds switch buffer, drops land in the
  middle of collectives, and iteration time (which AI sits through) balloons
  (walk the symptoms in [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md)).

### How to measure it
- `perftest` / `ib_write_bw` and `ib_read_bw` with `-d` on the RoCE device: drop-free
  full-rate is the baseline; any retransmit shows up as collapsed bandwidth.
- `ethtool -S <dev>` on ConnectX-class NICs: count `tx_retry_exeed`, `rx_*_err`,
  `ib*_retrans`, `out_of_buffer` — these rise exactly when the fabric is lossy.
- `rdma` tool and `rdma resource show` for QP state; NCCL error counters in
  `nccl-tests` (`allreduce_1node` vs multi-node) expose cross-node loss as slow
  multi-node runs versus clean loopback.
- Switch-side: `show queue` drop/PFC counters on the RoCE traffic class; **zero drops
  on the lossless class is the target** (see [23-roce-lossless-fabric-design.md](./23-roce-lossless-fabric-design.md)).

### How to make it not hurt (the "lossless by policy" idea)
The industry does **not** fix RDMA's poor loss tolerance; it deletes the loss. The
doctrine — "lossless by policy" — is: on the designated RoCE traffic class, the fabric
is configured so that **no packet is ever dropped by buffer overflow**. Two mechanisms
carry this ([F/A], detailed in the following pages):

| Mechanism | Layer | Role | Page |
|---|---|---|---|
| PFC (802.1Qbb) | link / buffer backstop | pauses a sender *before* its downstream queue overflows, hop-by-hop | [18-data-center-bridging.md](./18-data-center-bridging.md) |
| ECN/WRED (marking) | egress queue marking | marks congestion *before* PFC even fires, so senders slow end-to-end (DCQCN) | [20-ecn-wred.md](./20-ecn-wred.md), [21-dcqcn.md](./21-dcqcn.md) |
| DCQCN | endpoint control loop | receiver→CNP→sender rate cut | [21-dcqcn.md](./21-dcqcn.md) |

"Lossless" here is **a policy outcome, not an Ethernet property**: Ethernet itself
drops; the stack of PFC thresholds + ECN-knobs + buffer partitions is what makes the
RoCE class behave as if a port had InfiniBand's credits. That is both the enablement
and the fragility of RoCE — see [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md) for what happens when
the policy is mis-tuned.

### Comparison — RDMA over lossless vs lossy Ethernet

| Property | InfiniBand (credit FC) | RoCE over lossless Ethernet (PFC+ECN+DCQCN) | RoCE over plain lossy Ethernet |
|---|---|---|---|
| Link losslessness | by design (credits) | by policy (PFC/ECN) | none |
| RC retransmission tier | built-in, credit-driven | Go-Back-N, rarely exercised | Go-Back-N, constantly exercised |
| Drop tolerance | ~none needed | low (relies on PFC) | very poor |
| Typical throughput @0 loss | full rate | full rate | full rate |
| @1 drop | full rate (no drop possible) | small hit | **collapse** [E] |
| Ops burden | low | high (threshold tuning) | low, but useless for RC |
| What protects you | receiver credits | PFC backstop + ECN/DCQCN headroom | nothing |

Provenance note: the Go-Back-N / no-selective-retransmission claim is the core finding
of *Revisiting Network Support for RDMA* (IRN), Mittal et al., **ACM SIGCOMM 2018**,
DOI **10.1145/3230543.3230557** [F]. The arXiv id **1806.08159** appears in ResearchGate
metadata for this paper; it is **UNVERIFIED here** (flag via [16-roce-fundamentals.md](./16-roce-fundamentals.md)
parent re-verify list) — cite the DOI, not the arXiv id.

## Key Takeaways
1. RDMA RC retransmits with **Go-Back-N — no selective ACK**: one drop forces a resend from the last delivered PSN, re-sending perfectly good packets [F: SIGCOMM'18 IRN, DOI 10.1145/3230543.3230557].
2. On lossy Ethernet, throughput **collapses** (cliff, not graceful): a 100 MB flow at 50 GB/s losing one mid-message packet re-sends ~half its volume ≈ 1.0 ms [E].
3. Loss is almost never single-packet in AI: **incast** into shallow switch buffers + synchronized all-gather/all-reduce microbursts drop bursts in the same µs window (50 KB headroom @400G·1µs [E]).
4. The industry answer is not to make drops harmless but to make the RoCE class **lossless by policy** — PFC backstops the buffer, ECN/DCQCN slow senders first (see `./18`, `./20`, `./21`).
5. Jumbo cuts PPS (1.39 Mpps @9018B vs 8.23 Mpps @1518B [E]) and header overhead (58 B → 22.66% @256B, 1.42% @4096B [E]), but a lost jumbo frame is where Go-Back-N's amplification is worst.

## Related
- [16-roce-fundamentals.md](./16-roce-fundamentals.md) — the RoCEv2 encapsulation that inherits RC's Go-Back-N transport.
- [18-data-center-bridging.md](./18-data-center-bridging.md) — the PFC/ETS/DCBX machinery that makes a class lossless by policy.
- [20-ecn-wred.md](./20-ecn-wred.md) — ECN marking that signals congestion *before* the buffer overflows.
- [21-dcqcn.md](./21-dcqcn.md) — the CNP/rate-cut loop that turns ECN marks into sender throttling.
- [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md) — what happens when the lossless-by-policy stack is mis-tuned.
- [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md) — the collectives (all-gather/all-reduce) that create incast.

## References
- "Revisiting Network Support for RDMA" (IRN), Mittal et al., **ACM SIGCOMM 2018**, DOI 10.1145/3230543.3230557 (Go-Back-N / no-selective-retransmission, the core finding) [F].
- arXiv:1806.08159 (appears in ResearchGate metadata for IRN) — **UNVERIFIED**; cite the DOI, not this id.
- [E] throughput-collapse, PPS, header-overhead, PFC-headroom, and serialization figures from the section constants bank (computed 2026-08-25).
