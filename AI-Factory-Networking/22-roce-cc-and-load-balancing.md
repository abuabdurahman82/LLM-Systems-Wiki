# RoCEv2 Congestion Control & Load Balancing
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: DCQCN (Zhu et al., SIGCOMM'15), TIMELY (Mittal et al., SIGCOMM'15),
HPCC (Li et al., SIGCOMM'19), Swift (Kumar et al., SIGCOMM'20), Meta Engineering blog,
Broadcom Tomahawk-5 DLB, mlx5dv_modify_qp_udp_sport(3), OCP MRC 1.0 / OpenAI MRC;
fetched 2026-08-25.

## 30-Second Explanation
RoCEv2 has two separate problems to solve at once. **(a) Congestion control (CC):**
because stock RoCE Reliable Connection (RC) retransmits with Go-Back-N, a single
drop is expensive, so the fabric wants to slow senders *before* buffers overflow.
DCQCN is the de-facto production answer — switches mark ECN on the packet, the
receiver sends a CNP back, the sender cuts rate multiplicatively — but it is not
the only scheme (TIMELY, HPCC, Swift are real alternatives from the literature).
**(b) Load balancing:** ECMP hashes on the 5-tuple, but RoCEv2's UDP destination
port is fixed at 4791, so with few QPs per GPU there are few distinct 5-tuples and
traffic **polarizes** onto a few links. The countermeasures all add *path
diversity*: per-QP UDP source-port entropy, flowlets, Broadcom's Dynamic Load
Balancing, and endpoint-driven multipath (MRC). The root difficulty everywhere is
that stock RoCEv2 RC wants **in-order** delivery, and any scheme that sprays
across paths must first solve reordering.

## The CC landscape at a glance
```text
                 SWITCH marks?    FEEDBACK to sender        rate reaction              production status
DCQCN (SIGCOMM'15)  ECN-CE (WRED)   CNP packet(receiver->sender)  mult. cut (1-a/2),add.inc  de-facto RoCEv2 CC [F]
TIMELY (SIGCOMM'15) none            RTT measured at NIC           delay-gradient AIMD        research / niche  [I]
HPCC   (SIGCOMM'19) INT telemetry   exact link load via INT       rate=target/inflight       research / eval   [E]
Swift  (SIGCOMM'20) none            one-way delay(HW timestamps)  delay-AIMD, backoff 1 RTT  Google-style, niche[I]
```

## How DCQCN's closed loop actually works (an ASCII tour)
```text
  SENDER (reaction point)                  SWITCH (congestion point)      RECEIVER (notification point)
  NIC, DCQCN in hardware                   WRED ECN marker per queue
       | 1. sends RoCE data (ECN capable) ----------------------------->|
       |                                                               | 2. queue crosses K-min
       |                                                               |    -> mark ECN-CE (prob ramps
       |                                                               |       to P-max at K-max)
       |                                                               |    [marks BEFORE PFC XOFF]
       |                                            3. marked pkt ------->|
       |                                                                  | 4. NIC sees ECN-CE
       |                                   5. CNP back (DSCP 48) <---------|
       | 6. on CNP: rate <- rate * (1-alpha/2);  then additive-increase |
       |    on a no-CNP interval (gate ~1 RTT so it does not over-react)|
       v                                                                  v
```
**Role names** (DCQCN's three parts): the **congestion point** is the switch, the
**notification point** is the receiver NIC that emits **CNP** packets, the
**reaction point** is the sender NIC that cuts its rate. **[A/F]**

### What / Why / How — DCQCN
- **What:** end-to-end closed-loop CC for RDMA over Ethernet. **Why:** RC's
  Go-Back-N makes loss catastrophic, so slow the sender end-to-end while PFC acts
  as a backstop. **How (the three roles above):** switch marks **ECN-CE** past a
  WRED threshold (K-min → K-max, probability to P-max); receiver sends a **CNP**
  (OpCode = CNP, dest QPN = the marked flow's source QPN, DSCP 48 default); sender
  keeps an ECN-estimate **α** (start ≈ 1.0), on CNP cuts to `rate × (1 − α/2)`,
  recovers with additive increase. **[F/I]** — Zhu et al., SIGCOMM'15
  (DOI 10.1145/2785956.2787484).
- **CNP cadence:** the receiver rate-limits CNPs (NVIDIA `DcQcnMinTimeBetweenCnps`
  ~4 µs); the sender also gates actions (waits ≥ one RTT before acting on further
  CNPs) so it does not over-panick on a burst. **[F: NVIDIA DCQCN params]**
- **Production status [F]:** DCQCN is the de-facto production RoCEv2 CC — Intel
  ships DCQCN/TIMELY/DCTCP *selectable* per NIC, NVIDIA defaults to it. **The
  important exception [E]:** Meta disabled DCQCN at 400G in production
  (poor DCQCN performance for training collectives + problems with correct CNP counting),
  relying on collective co-tuning + PFC instead —
  a non-vendor datapoint that *"end-to-end CC is not mandatory."* See
  [24-vendor-landscape.md](./24-vendor-landscape.md).

### What / Why / How — TIMELY
- **What/Why:** RTT-based CC with **no switch feedback** — the NIC measures RTT to
  the receiver and adapts rate to keep delay in a target window. Useful where you
  cannot trust/obtain switch ECN (off-path, virtualized NICs).
- **How:** delay-gradient AIMD — if the RTT trend (gradient) is rising, cut; if
  falling, increase, within a target delay band.
- **When/status:** originated at Google (SIGCOMM'15, Mittal et al.); **not** the
  default on RoCE NICs. **[I]** production niche.

### What / Why / How — HPCC
- **What/Why:** use **INT (in-band network telemetry)** so the sender learns
  *exact* ingress/egress queue occupancy at every hop and sets a precise window:
  `rate = target / max(in-flight estimate)`.
- **Claim:** up to **95% FCT reduction vs DCQCN/TIMELY** in the paper's
  simulations. **[E]** — Li et al., SIGCOMM'19 (DOI 10.1145/3341302.3342085).
- **Status:** research/eval — needs **INT-capable switches on every hop**, which
  most AI fabrics do not have. **[E]**

### What / Why / How — Swift
- **What/Why:** delay-based AIMD using **NIC hardware timestamps** of one-way
  delay; a distinctive deliberate **one-RTT backoff on loss** (it gives up the
  rate for a round-trip rather than trust stale estimates).
- **When/status:** used at Google; good on uniform, low-jitter fabrics; **not** the
  default RoCE scheme. **[I]** — Kumar et al., SIGCOMM'20
  (DOI 10.1145/3387514.3406591).

## How to measure CC (before you trust any scheme)
Watch the NIC's **congestion counters** [F: NVIDIA mlx5]:
```text
np_cnp_sent                  = CNP sent by THIS NIC = it saw ECN = congestion it experienced
np_ecn_marked_roce_packets   = ECN-marked ingress it received
rp_cnp_handled / rp_cnp_ignored  = CNP received; IGNORED rising = CC not configured
                                   on this adapter (you think it is, it isn't)
```
**Interpretation:** if `rp_cnp_ignored` climbs, your NIC has DCQCN disabled — you
are running *without* transport CC (sometimes exactly Meta's choice, but usually a
misconfig). **[I]**

## ECMP entropy: the RoCEv2 polarization problem
### What
ECMP hashes a flow on its **5-tuple** (src IP, dst IP, protocol, src port, dst
port) to pick one equal-cost path and pins the whole flow there. **RoCEv2 fixes
UDP dst port = 4791** (the IANA RoCEv2 port), so the tuple collapses to
`(src IP, dst IP, UDP src port)`.

### Why it breaks
AI training keeps **few QPs per GPU** (tens of parallel flows, not thousands). A
handful of 5-tuples over a hash → many elephant flows land on the **same uplink**
while others idle: **polarization**. **This is the [F] Meta engineering finding**:
ECMP hashes on the five-tuple including UDP ports, and RoCEv2's single dst-port +
few QPs yields poor spread; Meta banked on deep-buffer spines + collective tuning
to ride it out.

### Example: why the tuple is near-empty
```text
2 GPUs, 2 QPs each, both talking to one dst IP on dst port 4791:
distinct 5-tuples = 4 (only the src UDP port varies)
over, say, 8 uplinks -> at most ~4 paths even under an ideal hash,
realistically 1-3; one elephant AllToAll saturates a single uplink -> ~50% BW.  [A, illustrative]
see ./16-roce-fundamentals.md for ECMP hash entropy math.
```
**Failure mode:** one uplink saturates, others idle; **nccl busbw collapses but
there is no PFC storm** — this is a hashing problem, not a buffer problem. **[I]**

## Countermeasures (all = add path diversity; the hard part is reordering)
```text
                 WHERE acts   granularity        path count              reorder fix needed?
per-QP UDP sport [F: man page]  NIC              1 path/flow (more spread)      no
flowlets         [F: DLB/HW]    switch           1 path/flowlet                 no (flowlets stay in-order)
Broadcom DLB     [F: vendor]    switch           per-packet OR flowlet          YES (per-pkt spray -> OOO)
MRC              [A]            endpoint NIC     per-packet, 100s of paths      YES -> NIC reorders
```
### 1. Per-QP UDP source port `[F: man page]`
Vary the **UDP source port** per QP so switches (which cannot see IB headers) gain
entropy. `mlx5dv_modify_qp_udp_sport(3)`: *"The UDP source port is used to create
entropy for network routers (ECMP), load balancers and 802.3ad link aggregation
switching that are not aware of RoCE IB headers."* NVIDIA's WinOFDEV derives it as
`UDP.SrcPort = (SrcPort XOR DstPort) OR 0xC000` (16-bit space, two high bits
forced) [F: NVIDIA WinOFDEV]. The often-quoted **"256 source ports" is
UNVERIFIED** — the field is 16-bit and the mechanism is per-QP derived, not a fixed
256-set. **[UNVERIFIED]** This is the *cheapest* fix and the first thing to enable.

### 2. Flowlet switching `[F/I]`
The switch breaks a long flow into **flowlets** separated by inter-packet gaps and
hashes each flowlet separately → a flow migrates paths between bursts without
per-packet reordering. Good middle ground: no reorder requirement, better spread.
WWT: flowlet switching mitigates *"low uplink entropy caused by RoCEv2's use of a
single UDP port."* **Requires** a gap long enough to be worth re-hashing (a
flowlet timeout) — round-robin/back-to-back AI traffic may leave no gap, so it
degrades to ECMP.

### 3. Broadcom Dynamic Load Balancing (DLB) `[F: vendor]`
On **Tomahawk and Trident (incl. Tomahawk 4/5)**, DLB supports **per-packet spray
and flowlet** modes, falls back to hash ECMP for ineligible (non-sprayable) flows,
and is **shipped/deployed** — Broadcom: *"DLB is successfully deployed in multiple
networks today"*; claims fabric utilization ~55% → 90%+ on TH4/TH5 **[F: vendor
claim]**. Per-packet spray ⇒ out-of-order ⇒ needs a reorder story at the receiver
(either the NIC reorders, or only flowlet-mode is used).

### 4. MRC — Multi-Path Reliable Connection
**Endpoint-driven multipath**, not a switch feature: a NIC-resident transport that
extends RoCE RC with **per-connection, per-packet spraying across hundreds of
paths**, **bounded reordering** (Max PSN Range), and SACK/NACK/trimmed-packet
recovery. **Open spec: OCP MRC 1.0**; co-developed by **AMD, Broadcom, Intel,
Microsoft, NVIDIA**; **deployed at OpenAI** (OpenAI *"Resilient AI Supercomputer
Networking using MRC and SRv6"*; MRC arXiv paper). **[F/A]** — see
[25-nvidia-spectrum-x.md](./25-nvidia-spectrum-x.md). Production: **deployed at OpenAI + NVIDIA/Microsoft
hyperscale [A]**, open-spec — not yet universal merchant-RoCE. Wake-up point:
because MRC owns reordering in the NIC, **it is the endpoint-side answer to the
entropy problem** — it stops depending on switch hash quality entirely.

## Packet reordering: the root difficulty
### What
Stock RoCEv2 RC is **in-order, lossless**: out-of-sequence arrival triggers
reorder-buffer build-up and, in lossy schemes, Go-Back-N retransmission. Every
spraying scheme must therefore place **receiver-side reorder/reassembly in the
NIC** — MRC's Max-PSN-Range + receiver reorder; IRN's reorder tolerance +
selective/negative ACKs. **[F/I]** — MRC arXiv; IRN SIGCOMM'18
(DOI 10.1145/3230543.3230557).
### Hardware impact
Reorder logic lives in NIC silicon and costs buffer + latency. Switches only spray
and mark; they never reassemble. Endpoint (NIC) reassembly scales with endpoint
count, which is exactly why MRC and UET put reassembly in the endpoint.

## NIC-based multipathing: the union of the above
The endgame is a NIC that *sprays and reorders itself*: AWS **SRD** (fully custom
reliable datagram, out-of-order, built-in CC — not RoCE) **[F: AWS]**; **MRC** on
NVIDIA/AMD NICs; UET's **RUD** (reliable unordered delivery + per-packet EV spray,
receiver zero-copy, no reorder buffer) — see [31-uetch-deep-dive.md](./31-uetch-deep-dive.md). The
spectrum:
```text
static ECMP   ->  flowlets     ->  per-packet switch spray (DLB)   ->  endpoint multipath (MRC/UET)
in-order, no      some spread      needs reorder at NIC               NIC owns spray + reassembly
  reorder         no reorder       [F: Broadcom DLB]                  [F/A: MRC, UET RUD]
```
**When to choose [I]:** static ECMP + per-QP port entropy for small/cheap fabrics;
DLB where only switches change; MRC/UET where the endpoint must own reliability and
path choice at 100k+ scale.

## Which to deploy — a hypothesis, not a winner
| | DCQCN | TIMELY | HPCC | Swift |
|---|---|---|---|---|
| Feedback signal | ECN-CE (switch) + CNP (receiver) [F] | RTT at NIC [A] | INT link load [E] | one-way delay, HW ts [I] |
| Switch requirement | ECN marking (WRED) [F] | none [A] | INT-capable switches [E] | none [I] |
| Rate rule | mult. cut `(1-a/2)`, add. inc [F/I] | delay-gradient AIMD [A] | `rate=target/inflight` [E] | delay-AIMD, backoff 1 RTT [I] |
| Loss handling | lossless (PFC backstop) [F] | reacts to loss too [A] | assumes INT, lossy-ish [E] | explicit backoff on loss [I] |
| Production (RoCE) | de-facto [F] | niche [I] | research/eval [E] | niche/Google [I] |
| Best for | today's lossless RoCE [F] | no-trust-ECN fabrics [I] | future INT fabrics [E] | stable low-jitter DCs [I] |
**Bottom line [I]:** deploy DCQCN now (it is what ships and what NICs default to);
treat HPCC as the INT future, Swift/TIMELY as niche. The experiment that would
decide a "winner" is a controlled FCT/JCT sweep of each on the same cluster —
nobody has published one for AI collectives.

## Cross-links
- [21-dcqcn.md](./21-dcqcn.md) — full DCQCN mechanics & parameter table.
- [20-ecn-wred.md](./20-ecn-wred.md) — ECN/WRED threshold design (K-min/K-max/P-max).
- [16-roce-fundamentals.md](./16-roce-fundamentals.md) — RoCEv2 packet layout & entropy basics.
- [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md) — topologies that load-balancing assumes.
- [31-uetch-deep-dive.md](./31-uetch-deep-dive.md) — UET RUD spraying & reassembly (the endpoint-multipath future).
- [23-roce-lossless-fabric-design.md](./23-roce-lossless-fabric-design.md) — where ECMP/CC sit in the full lossless design.
- [README.md](../Networking/README.md) — fabric-wide routing/ECMP reference.

## Key Takeaways
1. RoCEv2 has **two separate problems**: congestion control (slow senders *before* buffers overflow) and load balancing (spread flows across paths) — and the shared root difficulty is that stock RC wants **in-order** delivery, so any sprayer must first solve reordering.
2. **DCQCN is the de-facto production CC** (switch marks ECN-CE → receiver CNP → sender `rate × (1 − α/2)`); TIMELY, HPCC, and Swift are real literature alternatives with different sensor requirements (RTT, INT telemetry, HW timestamps).
3. **ECMP polarization**: RoCEv2 fixes UDP dst port 4791 and a GPU keeps few QPs, so few distinct 5-tuples hash onto one uplink while others idle — the classic "no PFC storm, but busbw collapses" symptom [F: Meta].
4. Countermeasures all **add path diversity**: per-QP UDP source-port entropy (cheapest, `mlx5dv_modify_qp_udp_sport`), flowlet switching, Broadcom DLB per-packet spray, and endpoint **MRC** (sprays across 100s of paths and reorders in the NIC) [F/A].
5. Where each fits [I]: static ECMP + per-QP port entropy for small/cheap fabrics, DLB where only switches change, **MRC/UET endpoint multipath** where the endpoint must own reliability and path choice at 100k+ scale.

## Related
- [21-dcqcn.md](./21-dcqcn.md) — full DCQCN mechanics and parameter table (the de-facto CC).
- [20-ecn-wred.md](./20-ecn-wred.md) — the ECN/WRED threshold design that the CC schemes feed on.
- [16-roce-fundamentals.md](./16-roce-fundamentals.md) — RoCEv2 packet layout and per-QP UDP source-port entropy.
- [31-uetch-deep-dive.md](./31-uetch-deep-dive.md) — UET RUD spraying and reassembly, the endpoint-multipath future.
- [23-roce-lossless-fabric-design.md](./23-roce-lossless-fabric-design.md) — where ECMP/CC sit inside the full lossless design.
- [README.md](../Networking/README.md) — fabric-wide ECMP/routing as the substrate these schemes assume.

## References
- DCQCN — Zhu et al., **ACM SIGCOMM 2015**, DOI 10.1145/2785956.2787484 [F].
- TIMELY — Mittal et al., **SIGCOMM 2015** (RTT-based, no switch feedback) [F].
- HPCC — Li et al., **SIGCOMM 2019**, DOI 10.1145/3341302.3342085 (INT-based; 95% FCT-reduction claim is the paper's simulated [E]) [F].
- Swift — Kumar et al., **SIGCOMM 2020**, DOI 10.1145/3387514.3406591 (delay-based, one-RTT backoff on loss) [F].
- IRN — Mittal et al., **SIGCOMM 2018**, DOI 10.1145/3230543.3230557 (reorder tolerance / selective+negative ACK basis) [F].
- Meta Engineering, "RoCE networks for distributed AI training at scale" (ECMP polarization, no-DCQCN datapoint) [F].
- Broadcom Tomahawk-5 Dynamic Load Balancing (vendor claim: ~55% → 90%+ utilization on TH4/TH5) [F: vendor].
- `mlx5dv_modify_qp_udp_sport(3)` man page; NVIDIA WinOFDEV UDP.SrcPort formula (`(SrcPort XOR DstPort) OR 0xC000`) [F: vendor].
- OCP MRC 1.0 spec; OpenAI "Resilient AI Supercomputer Networking using MRC and SRv6" / MRC arXiv paper [F/A].
- [E] CC/load-balancing figures from the section constants bank (computed 2026-08-25).
