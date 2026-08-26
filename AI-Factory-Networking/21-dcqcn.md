# DCQCN: The RoCEv2 Congestion Control Loop
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: Zhu et al., ACM SIGCOMM 2015 (DOI 10.1145/2785956.2787484), NVIDIA/Mellanox DCQCN params page, IP Infusion DCQCN explainer, Juniper DCQCN config; arithmetic from section constants bank (2026-08-25).

## 30-Second Explanation
**DCQCN** (Data Center Quantized Congestion Notification) is the de-facto congestion
control scheme for RoCEv2: it makes the *sender NIC* slow down based on *switch* queue
depth, so ECN does the throttling and PFC stays a rare backstop. The loop is simple to
state and subtle to tune. A switch that starts to congest marks incoming RoCE packets
**CE** ([20-ecn-wred.md](./20-ecn-wred.md)). The **receiver NIC** sees the CE mark and sends a single
**CNP (Congestion Notification Packet)** back to the sender. The **sender NIC** keeps an
estimate **α** of how congested the path is; on a CNP it cuts its rate by
**(1 − α/2)** — a multiplicative backoff — then recovers additively toward the line
rate. Three roles, one closed loop: **congestion point** (switch WRED marks), *notification
point* (receiver CNP), *reaction point* (sender α/rate). DCQCN is *not* a standard and
*not* an RFC: it is an **ACM SIGCOMM 2015 paper** by Zhu et al., implemented by
Mellanox/NVIDIA, Juniper, Cisco and others. Do not conflate it with **RFC 8257**, which
is **DCTCP** — a TCP scheme, unrelated. The whole game of production RoCE is *tuning
DCQCN's α-updates, gate timers, and CNP rate against the ECN/PFC thresholds*
([20-ecn-wred.md](./20-ecn-wred.md), [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md)).

## What
DCQCN is an **endpoint-driven, rate-based, quantized AIMD** congestion controller over
ECN-marked RoCEv2. Three cooperating roles:

| Role | Where | Function |
|---|---|---|
| **Congestion point** | switch egress queue (WRED/ECN) | marks ECT→CE as queue crosses K-min→K-max |
| **Notification point** | receiver NIC | converts CE into one CNP back to sender, rate-limited |
| **Reaction point** | sender NIC | maintains α; cuts rate on CNP; recovers additively |

It is *quantized* (QCN heritage: rate updates quantized like QCN's RQI/RI/RP bits, per
the DCQCN design), which is why it is named DC-**Q**-CN — the QCN lineage matters for
understanding the α math below [A/I: from the DCQCN paper/QCN terminology].

## Why
DCQCN exists to give ECN a *teeth* — an actual rate change at the sender — and to make
PFC unnecessary. Without it, ECN marks are just paint on packets; with PFC-only, the
fabric idle-thrashes ([19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md)). DCQCN's design goals, from the
2015 paper: (1) **fast reaction** to congestion (cut within ~1 RTT), (2) **no harm to
flow completion time (FCT)** for short flows, (3) **TCP-friendly-ness**, (4) robust to
how ECN is deployed on switches. Rate-based (not window-based) so it suits the NIC
hardware and the many-parallel-flows pattern of AI collectives. [A: paper abstract]

## How — the numbered control loop (vertical)
The full loop, step by step, as it appears on the wire:

```text
        SENDER NIC (reaction point)                    RECEIVER NIC          SWITCH (congestion pt)
        α, current rate R                                                    egress q, WRED curve
            │                                                                    │
            │① RoCE pkt (ECT), high rate                                        │
            │────────────────────────────────────────────────────────► queue grows
            │                                                                    │
            │                                                                    ▼ ② crosses K-min
            │                                                                    │ → mark ECT→CE ●
            │                                                                    ▼
            │                                  ③ CE packet forwarded (NOT dropped)
            │────────────────────────────────────────────────────────────────►
            │                                                                      (PFC XOFF sits
            │                                                                    │  above K-max;
            │                                                                    ▼  never reached)
            │                                   ④ receiver reads CE on RoCE class
            │                                   ⑤ receiver sends one CNP (DSCP 48)
            │◄───────────────────────────────── CNP (prio 6, strict-high) ─────
            │
            │⑥ on CNP: α update → rate ← rate × (1 − α/2)   [multiplicative cut]
            │   (rate-limited CNPs: min_time_between_cnps; gate/G-timer)
            │
            │⑦ no CNP for a full α-update interval → α decays (g step)
            │   → additive increase of rate (quantum per RTT); hyper-additive fast
            │     phase when α ≪ target
            │   → rate climbs back toward line rate until the next CNP
            ▼
       back to ① (recovery), PFC never fires if thresholds are sane
```

The one **number to internalize**: on a CNP the sender cuts
**rate ← rate × (1 − α/2)**. With initial α ≈ 1.0 that is a ~50% cut on the first
CNP [F: NVIDIA initial α ≈ 0.999; math [E]-derived below]. That is aggressive —
deliberately, so the first CNP clears the congestion fast — and recovery is then
additive so we regain bandwidth without re-triggering.

## Packet flow — CNP (notification point) detail
**CNP format**: a RoCEv2 packet whose BTH **OpCode is CNP**, sent to the *source* QPN of
the marked flow (the receiver constructs it; it needs no data payload of consequence and
does not carry RDMA data). It is typically assigned its own high DSCP so it is never
paused with the data class:
- **CNP DSCP 48 → priority 6** on Mellanox/NVIDIA default [F: vendor]
- Carried in the UDP/RoCEv2 encapsulation like any RoCE packet [A: IETF Fast-CNP draft
  on the CNP concept; NVIDIA DCQCN params]

**Rate limiting / suppression** — the *receiver must not* send one CNP per marked
packet, or CNPs would themselves flood the fabric. Constraints:
- **min_time_between_cnps** — minimum gap between CNPs from a receiver to a source
  (`DcQcnMinTimeBetweenCnps`, default ~4 µs at NVIDIA [F: vendor]). A commonly cited
  operational figure is ~1 CNP per ~50 µs [F: IP Infusion explainer].
- **cnp_dscp** and **cnp_802p_prio** set the CNP's DSCP/priority (48 / 6) [F: vendor].
- CNPs are sent on a **strict-high control priority** so they are not paused behind the
  very congestion they report ([18-data-center-bridging.md](./18-data-center-bridging.md)).

## Design — the three update laws (reaction point)
Every quantity below is from the NVIDIA/Mellanox DCQCN params page unless tagged [I].

**1. α estimation.** The sender keeps **α** = the fraction of its packets marked this
window (an ECN-estimator):
- **Initialize** α ≈ 1.0 — Mellanox `initial_alpha_value = 1023` in Q10 fixed point =
  1023/1024 ≈ **0.999** [F: vendor]. Starting near 1.0 means the *first* CNP causes a near-halving, which is what you want when you are already congesting.
- **α-update step `g`** — `dce_tcp_g` default 1019 (Q10) ≈ 0.995. On each α-update
  interval: if CNPs seen, α rises toward 1; if clean, α decays by g. [F: vendor]

**2. Multiplicative cut on CNP.** On a CNP (subject to the gate timer):
```
R ← R × (1 − α/2)
```
With α = 1.0 → R ← R × 0.5 (halve). With α = 0.8 → R ← R × 0.6. This is "rpg_gd"
mapping α to a rate-reduction factor [F: vendor]. The cut is what actually clears the
congestion point.

**3. Additive / hyper-additive recovery.** When no CNP arrives for the increase-timer:
- **Additive increase (AI)**: R += **quantum** per update period (QCN-style random/
  quantized increase; bytes-per-RTT). 
- **Hyper-additive fast phase**: when α stays well below its target (path clearly
  uncongested), DCQCN recovers faster than pure additive — the "hyper-additive"
  increase that lets a flow reclaim bandwidth quickly after a burst. [I: from the
  QCN/DCQCN design semantics; exact fast-phase constants are vendor-internal]

**Gate timers.** The sender does **not** act on every CNP — that would over-react to a
burst of marks from one event. DCQCN/QCN terminology: the sender waits **≥ one gate time
(G, roughly an RTT)** before applying a rate cut to a *further* CNP, and only *increases*
after the increase-timer expires with no new CNP. This prevents a single congested RTT
from cascading into a multiplicative wipeout. (Exact default ms gate values: **UNVERIFIED**
— see the re-verify list in `research-roce.md` §5/Claims 9.)

## Packet flow — CNP frame layout (byte view)
The CNP is just another RoCEv2 frame: Ethernet | IPv4/IPv6 | UDP (dst 4791) | BTH | then
an opcode that says "CNP." The bits that matter to the switch are the **DSCP**/priority,
not the payload [F: vendor; A: IETF Fast-CNP draft on the CNP concept]:

```text
 0                   8                   16                  24
|---|------------------|------------------|------------------|
| Eth Dst(6) | Eth Src(6) | EtherType 0x0800 (IPv4)         |
|---|------------------|------------------|------------------|
| ToS: DSCP 48 (CNP) | ... | Protocol UDP | dst-port 4791  |
|---|------------------|------------------|------------------|
| BTH: opcode = CNP (0x81) | dest QPN = source QPN of flow  |
|-----------------------------------------------------------|
```
Because the DSCP is 48, the switch puts the CNP on priority 6 (strict-high) [F: vendor]:
it is *forwarded ahead of* the data class and, critically, **not paused by the PFC that
is throttling the data** — a paused CNP would be the worst deadlock ([19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md)).

## Worked example — one congestion episode (hand-calculable)
Setup: a 400 Gb/s RoCE flow (50 GB/s) [E] into a congested to a receiver; switch ECN
thresholds sane (mark before PFC, [20-ecn-wred.md](./20-ecn-wred.md)); α starts ≈ 1.0 [F].
Time step = one α-update period (~RTT, call it T):

| Step | Event | α (approx) | Rate R (as fraction of line) | Arithmetic |
|---|---|---|---|---|
| t₀ | full-rate, no marks | 0.999 | 1.00 | init α [F] |
| t₁ | burst → switch marks >K-min | — | — | CE set on packets |
| t₂ | receiver sends CNP #1 | 0.999 | **0.50** | R←R×(1−α/2)=1×(1−0.499) |
| t₃ | (gate G) CNP #2 still arriving | 0.999 | **0.25** | 0.5×(1−0.499) |
| t₄ | CNP #3 | 0.999 | 0.125 | 0.25×(1−0.499) |
| t₅ | marks stop (queue drained) | decay via g | 0.125 | α drifts down |
| t₆… | additive increase, no CNP | ↓ | 0.125→rising | R += quantum / T |
| t₇ | back near line if path is clean | low | ~1.00 | hyper-additive if α≪target |

The takeaway: **two half-cut CNPs take a flow to 25% of line** — that is the intended
"clear the buffer fast" behavior; the additive tail climbs back so the average stays
high. A real NIC quantizes and gates these to avoid the mathematically ideal but
operationally violent full sequence [I: from QCN/DCQCN design]. With PFC mis-tuned so
ECN *doesn't* fire first, step t₂ never happens and the switch pauses instead
([19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md)).

## DCQCN in the fabric — placement and preconditions
DCQCN is **per-NIC** and needs nothing special on the switch beyond ECN marking — which
is why it ships on every RoCE-capable switch (Mellanox/NVIDIA, Juniper, Cisco, Arista,
Broadcom silicon) [F: vendor]. For it to function, in dependency order:
1. **ECN enabled** on the RoCE queue, with K-min/K-max *below* the PFC XOFF threshold
   ([20-ecn-wred.md](./20-ecn-wred.md)).
2. **DSCP→TC→priority mapping identical on host and switch**, and the RoCE class marked
   ECT by the sender NIC ([18-data-center-bridging.md](./18-data-center-bridging.md)).
3. **CNP path clean**: CNP DSCP 48 / prio 6 strict-high, never paused [F].
4. **CNP rate/window sane** (`DcQcnMinTimeBetweenCnps`) so feedback is sparse but present.
Only then do the α/quantum/gate knobs have anything to act on.

## Why it works / why the tuning is everything
The reason DCQCN "just works" when tuned and "does nothing" when not is **threshold
ordering**: ECN K-thresholds (switch) must mark *before* PFC XOFF so that the
mark→CNP→rate-cut loop outruns PFC ([20-ecn-wred.md](./20-ecn-wred.md)). DCQCN's α/rate math is robust
within a wide range, but it is *blind* if the switch never marks. Production failures
are almost always ECN/PFC misplacement ([19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md)) or CNPs being
starved/paused — not the α math itself. [I]

## Tuning — parameter table (Mellanox/NVIDIA-style; `[F: vendor]` unless noted)
| Parameter | Role | Typical default [F: NVIDIA] | Notes / consequence of misconfig |
|---|---|---|---|
| `initial_alpha_value` | starting α | 1023 (Q10 ≈ 0.999) | too low ⇒ weak first cut |
| `alpha_min` | α floor for recovery | ~low (0) | floor too high ⇒ never recover |
| `dce_tcp_g` | α decay step (Q10) | 1019 (≈0.995) | g too high ⇒ α sticks high |
| `quantum` | AI bytes per RTT | vendor-set | too small ⇒ slow recovery |
| `min_rate` / `max_rate` | rate floor / cap | 1 Gb/s…line rate | min_rate = bandwidth floor under congestion |
| `rpg_gd`/`rreduce` | α→rate-cut mapping | (1 − α/2) | — |
| `DcQcnMinTimeBetweenCnps` | CNP gap (µs) | ~4 µs default | too small ⇒ CNP flood; too large ⇒ slow reaction |
| `cnp_dscp` / `cnp_802p_prio` | CNP QoS | 48 / 6 | wrong ⇒ CNPs starved/paused |
| gate / G-timer, increase-timer | reaction pacing | ~RTT (ms) [I] | exact ms **UNVERIFIED** |

Intel 800-series exposes analogues (`dcqcn_min_rate`, `dcqcn_min_dec_factor`,
`dcqcn_rai/hai_factor`, `dcqcn_rreduce_mperiod`) [F: vendor], confirming DCQCN is the
per-NIC selectable RoCE CC baseline across vendors.

### Common misconfigurations
1. **ECN not enabled / K-max ≥ PFC XOFF** — DCQCN never fires; PFC storms (fix in
   [20-ecn-wred.md](./20-ecn-wred.md)).
2. **CNP priority paused or DSCP mismatched** — feedback starved; sender never slows.
3. **min_time_between_cnps too small** — CNP floods the control priority, or CNPs
   self-pause.
4. **initial α too low** — first-congestion cut too weak, buffer overflows before
   recovery.
5. **quantum/AI too aggressive** — rate oscillates; sawtooth throughput.
6. **Host/switch α-parameter drift** — asymmetric behavior per port.
7. **Meta case study** — Meta ran production **without DCQCN** at 400G (firmware/CNP
   bugs), relying on **collective-library-co-tuning + PFC** on merchant Ethernet [E:
   paper datapoint]. This is the important reality check: DCQCN is *typical*, not
   mandatory, and a mis-tuned DCQCN can be *worse* than none [I: It's not always better
   to be on].

## GPU relationship
DCQCN runs entirely in the **NIC**; the GPU issues RDMA verbs and never sees congestion
signals. The GPU (and NCCL) *does* see the consequence: correct DCQCN keeps collectives
flat under incast; a congested fabric without working DCQCN produces idle GPUs
(PCIe/NIC backpressure or NCCL timeouts), i.e. **network congestion surfaces as GPU
compute starvation** — the opposite of what DCQCN should prevent. Because DCQCN is
per-NIC, one mis-tuned NIC drags that *GPU's* collective time even if the rest of the
fabric is fine. [I]

NCCL relevance: NCCL overlaps communication and compute, so a slow RoCE flow does *not*
automatically stall the kernel — the GPU hides some latency up to the point where the
bottleneck becomes the collective itself. The practical symptom is **scale-dependent
slowdown** (multi-node far below loopback busbw) that only appears under incast, which
is precisely where DCQCN tunes. Walk [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md) and
[16-performance-benchmarking.md](../GPU-Communication/16-performance-benchmarking.md) for the measurement side.

## Deployment checklist (production RoCE + DCQCN)
- [ ] ECN **enabled** on the RoCE egress queue (common silent miss) [F: vendor]
- [ ] ECN K-min/K-max **below** PFC XOFF; headroom sized ≥ reaction [E]
  ([18-data-center-bridging.md](./18-data-center-bridging.md), [20-ecn-wred.md](./20-ecn-wred.md))
- [ ] DSCP→TC map **identical** host↔switch; RoCE = DSCP 26 / prio 3 [F]
- [ ] CNP = DSCP 48 / prio 6, **strict-high, unpaused** [F]
- [ ] `DcQcnMinTimeBetweenCnps` set (not left to a value that floods CNPs) [F]
- [ ] initial α ≈ 1.0; α_min; quantum sane [F]
- [ ] Verify with counters: **marks ≫ PFC pauses**, drops ≈ 0 on the lossless class
- [ ] Repeat on every NIC and every leaf — a single drifted port breaks the assumption
- [ ] Document which vendor's defaults you changed and why (tuning is fabric-specific)

## Troubleshooting
- **Symptom: high CNP rate** → congestion genuinely happening; check ECN thresholds and
  headroom, not CNP rate first.
- **Symptom: zero CNPs but PFC storms** → ECN not marking (K-max ≥ XOFF or ECN off) —
  the switch never told anyone [I/E].
- **Symptom: zero CNPs and dropped packets** → receiver not generating CNP (DSCP/prio),
  or CNPs being silently dropped.
- **Symptom: throughput oscillates** → AI/quantum too aggressive or gate timer too short.
- Counter-lookup: the symptom→cause table in [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md) plus
  [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md).

## Comparison
| Schemes | Base of control | Signals on | Type | Standard? |
|---|---|---|---|---|
| **DCQCN** | sender rate (α) | CNP (from CE) | quantized AIMD | paper (SIGCOMM'15) |
| **DCTCP (RFC 8257)** | TCP window | ACK CE ratio | TCP window | RFC |
| **TIMELY** | sender rate (RTT) | RTT gradient | delay-based | SIGCOMM'15 paper |
| **HPCC** | sender rate | INT in-band telemetry | precise rate | SIGCOMM'19 paper |
| **UEC (UET) CC** | sender rate | NSCC messages / CBFC | advanced (RFUN) | UEC spec 1.0 |
| PFC (no CC) | none (pause) | link PAUSE | hop-by-hop | IEEE 802.1Qbb |

Key contrast: **PFC reacts locally and slows everyone; DCQCN reacts per-flow at the
sender and only the congested flows** [I]. Versus DCTCP: DCQCN is for the RDMA/NIC
setting with ECN-CNP feedback and per-packet-irrelevant window mechanics; DCTCP is a
TCP sender-side refinement (do *not* blend them — RFC 8257 ≠ DCQCN) [A: correction].

## Limitations & when DCQCN is not the answer
- **It is feedback-agnostic to the *degree* of congestion after the first cut** — it
  relies on fine ECN/WRED placement; HPCC-style in-band telemetry gives the sender the
  actual queue depth, which DCQCN approximates with α [I].
- **It needs ECN and a wired CNP path** — any fabric or NIC that can't mark/emit CNPs
  correctly silently disables DCQCN, leaving only PFC ([19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md)).
- **Per-queue/per-flow fairness** is emergent, not guaranteed; with many equal flows the
  α-estimate can oscillate unless quantum/g are balanced [I].
- **The market already moving past it where cost matters**: Spectrum-X *doesn't* use
  DCQCN as the headline mechanism (it uses its own congestion control + MRC at the
  endpoint) [F: vendor]; UEC defines a richer transport CC (`../UET` page); but DCQCN
  remains the **operational baseline** every generic-RoCE fabric is tuned against — and
  the SIGCOMM'15 paper itself targeted *large-scale RDMA deployments*, exactly the AI
  cluster case [A].
- **Meta's counter-example**: production AI training at 400G **without DCQCN** — PFC +
  collective-user co-tuning instead — shows that a *mis-tuned or buggy* DCQCN can be
  worse than none [E: paper datapoint; I: inference].

## Lab
- `perftest` (`ib_write_bw -F`) under a background cross-traffic burst: observe DCQCN
  cut/recover as a sawtooth; with ECN off, see it stay flat then pause-storm
  ([19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md)).
- `rdma tool` / NIC counters (`eth0` `tx_retries`, CNP counter if exposed) correlated
  with `nccl-tests` `allreduce` completion under synthetic incast.
- Sweep `min_time_between_cnps` and record completion time + pause count: find the
  knee where CNPs neither flood nor starve [I/E].
- Checklist gate: before touching α/quantum, confirm ECN < PFC placement; the math does
  nothing if the switch never marks ([20-ecn-wred.md](./20-ecn-wred.md)).

> **Provenance (`[A] correction`):** DCQCN = *Congestion Control for Large-Scale RDMA
> Deployments*, Y. Zhu, H. Eran, D. Firestone, C. Guo, et al., **ACM SIGCOMM 2015**,
> pp. 523–536, DOI **10.1145/2785956.2787484** — a research paper, **not an RFC** (and
> not "Hasson et al.", not on a confirmed arXiv id). **Do NOT cite RFC 8257 for DCQCN:
> RFC 8257 is DCTCP**, a TCP congestion-control standard, unrelated to DCQCN. The IANA/
> IETF Fast-CNP draft describes the *CNP* concept used by RoCEv2 DCQCN, but DCQCN
> itself lives in the SIGCOMM'15 paper + vendor implementations (Mellanox/NVIDIA,
> Juniper, Cisco, Intel). [A: correction over the RFC-8257 conflation]

## Key Takeaways
1. DCQCN = three roles in one closed loop: the **switch** marks CE as the queue crosses K-min→K-max (congestion point), the **receiver NIC** sends one CNP back (notification point), the **sender NIC** cuts its rate (reaction point) — ECN does the throttling and PFC stays a rare backstop.
2. The one number: on a CNP the sender cuts **rate ← rate × (1 − α/2)**; α starts ≈ 1.0 (Mellanox `initial_alpha_value` 1023, Q10 ≈ 0.999 [F]), so the *first* CNP ≈ halves the rate, then recovery is additive.
3. Recovery: no CNP across the increase-timer → **additive increase (quantum/RTT)** plus a hyper-additive fast phase when α ≪ target; a **gate timer (~1 RTT)** stops a marked burst from cascading into a multiplicative wipeout.
4. DCQCN is a **SIGCOMM'15 research paper** (Zhu et al., DOI 10.1145/2785956.2787484), not a standard or RFC; **RFC 8257 is DCTCP** — do not cite it for DCQCN.
5. Tuning bottoms out at threshold placement: ECN **K-max < PFC XOFF** and a clean, unpaused CNP path (DSCP 48 / prio 6 strict-high) — get those wrong and the α math is blind; a mis-tuned DCQCN can be worse than none (Meta ran 400G without it) [E/I].

## Related
- [20-ecn-wred.md](./20-ecn-wred.md) — the ECN/WRED marking (K-min/K-max/P-max) that feeds the loop.
- [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md) — the PFC failure modes working DCQCN is meant to prevent.
- [18-data-center-bridging.md](./18-data-center-bridging.md) — the DCB/DSCP preconditions for a clean, unpaused CNP path.
- [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md) — diagnosing CC/PFC symptoms in NCCL collectives.
- [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md) — the collectives DCQCN keeps flat under incast.
- [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md) — DCQCN against the wider CC/load-balancing landscape.

## References
- "Congestion Control for Large-Scale RDMA Deployments" (DCQCN), Zhu et al., **ACM SIGCOMM 2015**, pp. 523–536, DOI 10.1145/2785956.2787484 [F].
- RFC 8257 (DCTCP) — the TCP scheme DCQCN is *not*; cited to kill the conflation [F/A].
- NVIDIA/Mellanox DCQCN parameters page (α, `dce_tcp_g`, quantum, CNP DSCP/prio, `DcQcnMinTimeBetweenCnps`) [F: vendor].
- IP Infusion DCQCN explainer (CNP cadence/rate) [F].
- Juniper DCQCN configuration (ECN drop-profile, DSCP mapping) [F: vendor].
- IETF Fast-CNP draft (the CNP concept used by RoCEv2 DCQCN) [F/A].
- [E] worked-example arithmetic (α ≈ 0.999, two half-cut CNPs → 25% of line) from the section constants bank (computed 2026-08-25).
