# InfiniBand Flow Control and QoS: Credits, Virtual Lanes, SL2VL
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: NVIDIA credit-loop & losslessness doc, NVIDIA/DOCA InfiniBand QoS, IB security docs, vCluster/intelligentvisibility IB-vs-RoCE comparisons; no [E] numbers used beyond the constants bank.

## 30-Second Explanation
InfiniBand is **lossless by construction, not by reaction**. Every link implements **credit-based flow control**: the sender may put bytes on the wire only up to the **credits the receiver has advertised** for that **Virtual Lane (VL)**. When a receiver's VL buffer fills, it stops advertising credit; the sender (and then each upstream link through **backpressure**) stalls instead of dropping. There is **no implicit drop path** — the only deliberate packet loss is the SM-configured **HOQ (Head-of-Queue) timeout**, a deadlock guard that "gives up" on a stuck buffer. Around that engine rides the QoS machinery: up to **15 data VLs (VL0–14)** plus **VL15** reserved for subnet-management control, mapped from **16 Service Levels (SL0–15)** via each switch's **SL2VL table**, and serviced by a **weighted round-robin high/low-priority arbiter** per port. Contrast Ethernet: IB credits **prevent** overrun; RoCE's PFC **pauses after** the fact.

## What
### Credit-based flow control — the model
Per link, per direction, per VL, the receiver owns a buffer of fixed size (a credit ≈ a fixed byte/block count). It advertises how much buffer is free; the sender counts down as it transmits and stops when its advertised-credit runs to zero [F: https://enterprise-support.nvidia.com/s/article/howto-prevent-infiniband-credit-loops]. Credit granularity is a flow-control block (e.g. an HCA may track "2048 credits × 64 B"; exact values are vendor/mode-specific [A: https://ankushja.in/blog/2024/credits-flow-congestion/]).

```text
  SENDER port                          RECEIVER port
  ┌────────────────┐   credit: "room"  ┌────────────────┐
  │ advertised     │ ◄──────────────── │ VL buffer      │
  │ credit count   │                   │ free = credit  │
  │ (decrement on  │                   │ (increment when│
  │  each block tx)│   data blocks ──► │  DMA drains)   │
  └────────────────┘                   └────────────────┘
      transmit only while credit > 0; when the receiver runs out of
      VL buffer it advertises ZERO → sender stalls → upstream stalls
      (backpressure) → source HCA throttles → fabric stays LOSSLESS.
      Only escape hatch: SM-configured HOQ timeout deliberately drops.
```

### Virtual Lanes (VL) — 15 data + VL15
VLs partition each link into independent credit domains so one traffic class's backpressure cannot block another [F: https://enterprise-support.nvidia.com/s/article/howto-prevent-infiniband-credit-loops]. VL0–14 carry data; **VL15 is reserved for subnet-management / multicast control (SMP) traffic**, isolated by priority so the fabric can be managed even when data VLs are congested [F]/[I: https://networking-docs.nvidia.com/doca/archive/3-4-0/infiniband-qos].

```text
  link = 15 data VLs + VL15(SM)
  ┌─────┬─────┬─────┬──────────┬────┐
  │ VL0 │ VL1 │ VL2 │ …  VL14  │VL15│  ← each VL: its own credit pool,
  └─────┴─────┴─────┴──────────┴────┘     own buffer, own arbitration
     data traffic (NCCL maps to one of these via SL)
```

### Service Level (SL) → VL, and arbitration
- **SL** is a 4-bit field in the **LRH**, giving 16 service levels (0–15) at the ingress.
- Each switch maps SL → output VL through its **SL2VL table** (a per-port, per-priority mapping) [F: https://networking-docs.nvidia.com/doca/archive/3-4-0/infiniband-qos].
- **Arbitration** is weighted-round-robin with two priorities per VL: a **high-priority weighted round robin** and a **low-priority weighted round robin**. High-priority credits have a limit — once a VL has sent its high-priority quantum it must yield so low-priority traffic isn't starved [F: https://networking-docs.nvidia.com/doca/archive/3-4-0/infiniband-qos].

```text
  SL (in LRH)      SL2VL table        VL (out)
  SL = 3  ──►   SL0→VL0, SL3→VL2, ...  VL2 ──► high-priority credits
                (programmed by SM)          ──► low-priority credits
                                           weighted-round-robin arbiter grants
                                           each VL link time (high limited by
                                           credit cap so low is never starved)
```

### HOQ — the deliberate drop
The only way a packet leaves the fabric unintentionally-by-design is a **Head-of-Queue timeout**: a stuck (non-draining) VL buffer sitting past its configured timeout is declared dead and its packets are dropped as a deadlock guard — otherwise a credit cycle that never resolves would wedge the link forever [F: https://enterprise-support.nvidia.com/s/article/howto-prevent-infiniband-credit-loops]. So IB is "lossless under normal operation, with a time-bounded escape valve." RC recovers the dropped packet by retransmit; if the drop exceeds retry limits the QP fails.

## Why
RDMA's one-sided semantics (the receiver CPU never sees the data) remove the natural flow-control feedback that TCP's receive window provides. IB therefore puts pacing *at the link* instead: the receiver's buffer availability *is* the throttle, hop by hop [I]. VLs exist so a lossless scheme doesn't turn into a **head-of-line** free-for-all — a burst on one flow must not freeze unrelated traffic [F: credit-loops doc]. The predictable, in-order, no-drop behavior is precisely what GPU collectives (AllReduce, AllGather) need: they assume either delivery or an explicit timeout, not silent statistical loss [I].

## When
Always — credit flow control is intrinsic to IB, no enable switch. QoS knobs (SL2VL, arbitration weights, per-partition QoS via the SM) are **configured** by the Subnet Manager, not ad hoc: the SM's QoS policy files map SL→VL→weight [F: https://networking-docs.nvidia.com/doca/archive/3-4-0/infiniband-qos]. You don't "turn on" VLs; you choose which SL your traffic uses and let the SM's policy route it. In practice, NCCL lets you pick the SL (`NCCL_IB_SL`, default SL0) and the SM maps it to a VL; a tuned AI fabric gives NCCL its own SL/VL + timeout so the low-latency collective path isn't sharing arbitration priority with IPoIB/mgmt traffic [F: https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html].

## GPU relationship
Every NCCL ring/tree message crosses the credit/VL layer; the QPs and WQEs described in [08-infiniband-queue-pairs.md](./08-infiniband-queue-pairs.md) sit above it. Because the fabric is lossless, NCCL can run with a **bounded retry budget** (`NCCL_IB_TIMEOUT`) instead of layer-4 congestion response [F: NCCL env docs]. If SL/VL is misconfigured, NCCL traffic can share a VL with bulky IPoIB control traffic and suffer arbitration head-of-line delay — a classic "good port counters, slow collectives" symptom [I].

## Design
- **SL per traffic class:** allocate SLs by lifecycle (control/IPoIB on low priority, NCCL collectives on a dedicated high-priority SL/VL, storage/journals separate).
- **Weighted arbitration:** give the collective VL a generous high-priority credit quantum; cap the management VL so it can always make progress but never starve data.
- **No credit-loop traps:** allocate/rate VLs consistently across the fabric; a mis-sized VL buffer or arbitration misconfig can produce credit stalls that silently cap throughput [F: https://enterprise-support.nvidia.com/s/article/howto-prevent-infiniband-credit-loops].
- **HOQ timeout tuning:** too tight → spurious drops (RC retries, tail latency); too loose → deadlocks stall for too long. Set via SM policy [I].

## Tuning
- `NCCL_IB_SL` selects the SL; the matching SM QoS policy must assign that SL a high-priority VL or the tuning is inert [F: NCCL env docs].
- Raise `NCCL_IB_TIMEOUT` only enough to absorb legitimate credit/HOQ stalls; over-generous timeouts mask genuine fabric problems [I].
- Use `perfquery` / switch QoS counters to see VL utilization and whether high-priority credits are being exhausted (a proxy for arbitration under-provisioning) [I].
- Verify the SL2VL table matches the policy you think you configured (`ibqueryerrors` / switch CLI) [I].

## Troubleshooting
- **Credit stalls / throughput cap** — a VL reachable but starved: check arbitration weights + SL2VL mapping, look for a flow being pinned to a low-priority VL [F: credit-loops doc].
- **Mysterious drops at HOQ** — check the HOQ timeout value vs your latency/jitter; spurious HOQ drops read as RC retries + occasional QP `Timeout` [F: credit-loops doc].
- **Head-of-line on one VL blocking everything** — if all traffic shares one VL, a burst blocks it; spread SLs/VLs and verify arbitration [I].
- **VL15 surprise** — management traffic should ride VL15; if data ends up on VL15 (misconfig), it competes with SM control [I].

## Comparison — IB credits vs Ethernet PFC
| | InfiniBand (credits) | RoCEv2 (PFC) [F: vCluster/intelligentvisibility] |
|---|---|---|
| Mechanism | sender holds credits the receiver advertised | receiver sends **pause frames** on a priority class |
| Direction | per-link, per-VL, per-direction (always on) | per-priority **pause** — a reactive stop |
| Losslessness | **prevention** — sender can't overrun buffer | **reaction** — receiver must pause the sender in time |
| Buffer model | per-VL credit buffers | per-priority buffer thresholds (driver-quantized) |
| Congestion control | deterministic / BCN (native), no add-on needed | needs **ECN/DCQCN** on top or PFC storms |
| Failure mode | HOQ timeout drop (rare, deliberate) | PFC **storm / deadlock** if ring doesn't clear |
| GPU-collective fit | low-latency, no extra layer | works but needs DCQCN tuning for losslessness at scale |

The crisp way to state it: **IB credits prevent the problem (sender physically can't overrun); PFC reacts to it (receiver pauses the sender).** PFC's weakness is the pause-frame ring that can deadlock without careful buffer/resume thresholds; IB's credit model avoids the ring by construction, at the price of needing per-VL buffers and careful arbitration [F: https://www.vcluster.com/blog/gpu-cluster-networking-infiniband-roce].

## Lab
Two host `ib_read_bw`/`ib_write_bw` runs tell you the link is healthy, but the QoS view needs the fabric:
```text
$ ibstat / ibqueryerrors             # port counters, buffer overruns
$ ibv_devinfo                        # HCA SL/VL capability
$ (switch CLI) show qos sl2vl        # confirm SL→VL mapping
```
To *see* credit behavior, congest one flow with `iperf3`-like multicast or heavy `ib_write_bw` while watching the second flow's latency — with arbitration working, the second flow holds its latency; without, it degrades (head-of-line) [I].

## Credit-loop anatomy — a concrete walkthrough
Trace one congestion episode to make the mechanism concrete [I; mechanism [F: credit-loops doc]]:

```text
  T0 source HCA sends flow F to switch2's egress → receiver R.
  T1 R's buffer for VL-v fills: its NIC stops advertising VL-v credit.
  T2 switch2's VL-v credit for R → 0: switch2 cannot forward F, so its
     VL-v buffer upstream fills → it stops advertising credit upstream.
  T3 switch1's VL-v credit for switch2 → 0 → switch1 stalls → HCA stalls F.
  T4 Result: F is paced back to its source, hop by hop, WITHOUT a single
     drop — the fabric is lossless. Other flows on other VLs unaffected.
  T5 If the stall persists past the SM-configured HOQ timeout, switch2
     deliberately DISCARDS F's stuck HOQ packet as a deadlock guard —
     the one legitimate loss path in all of IB.
```

Key property *to design for*: because credit stalls propagate, a single oversubscribed shared egress can produce **head-of-line blocking** on its VL — which is precisely why you separate latency-sensitive collective traffic onto its own VL/SL and don't co-mingle bulky storage or IPoIB [I]. Credit-loop discipline (consistent VL allocation/rating across the fabric, no under-rated VLs) is what NVIDIA's guidance stresses to avoid a silent throughput cap [F: https://enterprise-support.nvidia.com/s/article/howto-prevent-infiniband-credit-loops].

## SL2VL example — programming a mapping
The SM's QoS policy defines, per switch port, which **SL → VL** and with what **weight**. A minimal AI fabric might program [A: policy example; SL2VL mechanism [F: DOCA QoS]]:

| SL | Traffic | VL | Priority/weight |
|---|---|---|---|
| 0 | default (NCCL default `NCCL_IB_SL=0`) | VL0 | high |
| 1 | IPoIB / control | VL1 | low |
| 3 | storage/journals | VL2 | low |
| 15 | reserved/management | VL15 (SM only) | — |
| others | unused → VL0 | | |

Two rules worth stating loudly [I]: (1) the **SL you pick on the HCA only means the LRH field**; the *actual* service class is whatever VL the SL2VL table assigns downstream — tuning `NCCL_IB_SL` is inert unless the SM maps that SL to the WL you want. (2) **VL15 is not a data VL** — it must carry SM/multicast control and is protected by priority isolation so management works even when all data VLs are jammed [F]/[I: DOCA QoS].

## Weighted arbitration — the high/low priority dance
The per-VL arbiter services two weighted round-robin lists [F: DOCA QoS]:
```text
  one link slot at a time:
  high-priority WRR (weight H) ──► VL grant (up to its high-priority credit cap)
        +  when high-priority credit cap reached
  low-priority WRR (weight L)  ──► VL grant (guaranteed at least L slots)
        ↺ repeat — high priority never starves; low priority never starves
```
The high-priority **credit cap** is the designed-in fairness valve: without it, an aggressive high-priority VL would monopolize the link and block its own low-priority traffic and other VLs. Weights and caps are SM-programmed [I]. For NCCL collectives you want the collective VL to win the high-priority WRR with a generous cap, and to keep its latency-critical messages off the low-priority list.

## Comparison — IB credits vs Ethernet PFC (threat model)
The losslessness difference is *where the intelligence sits* [F: vCluster / intelligentvisibility]:
| | IB credits | Ethernet PFC |
|---|---|---|
| Losslessness achieved by | sender respecting credit count | receiver transmitting **pause** frames |
| Unit of control | per-VL, per-direction counters | per-priority-class pause |
| Risk if misconfigured | credit stall / head-of-line (no drop) | **pause-frame storm / deadlock ring** |
| Congestion signal | native FECN/BECN (BCN) | benefits from ECN/DCQCN (else lossy) |
| Scale behavior | deterministic O(link) backpressure | can deadlock under ring without careful thresholds |
| Remedy for hot flows | adaptive routing / SL mapping | DCQCN + buffer sizing |

The one-sentence contrast the section keeps returning to: **IB credits prevent overrun at the source; PFC reacts by pausing after the fact** — which is why IB needs no pause protocol, and why RoCE must layer DCQCN/ECN on top of PFC to stay lossless at scale [F: https://www.vcluster.com/blog/gpu-cluster-networking-infiniband-roce].

## Key Takeaways
1. **IB is lossless by design**: the sender transmits only what the receiver's advertised **credits** allow, per link, per VL, per direction [F].
2. **Backpressure is the mechanism**: a full VL buffer stops advertising credit and the stall propagates hop-by-hop to the source — no drops.
3. **The only deliberate drop is the HOQ timeout** — an SM-configured deadlock guard, recovered by RC retransmit [F].
4. **QoS = 15 data VLs + VL15(SM)**, **16 SLs**, per-switch **SL2VL** tables, and **weighted round-robin high/low arbitration** — all SM-programmed [F].
5. **Choose your SL deliberately**: `NCCL_IB_SL` only sets the LRH field; the SL2VL mapping the SM programs decides the real service class [I].
6. **IB credits prevent (no pause protocol); Ethernet PFC reacts (pause frames)** — the structural reason RoCE bolsters PFC with ECN/DCQCN but native IB doesn't need to [F].

## Related
- [09-infiniband-packet-format.md](./09-infiniband-packet-format.md) — LRH carries the SL (4-bit) that feeds SL2VL.
- [08-infiniband-queue-pairs.md](./08-infiniband-queue-pairs.md) — the QP layer this link-layer pacing sits under.
- [05-infiniband-architecture.md](./05-infiniband-architecture.md) — where the link layer fits in the stack.
- [13-infiniband-congestion-adaptive-routing.md](./13-infiniband-congestion-adaptive-routing.md) — CNP/BECN congestion control above this.
- [17-why-roce-is-harder.md](./17-why-roce-is-harder.md) — the PFC side of the same losslessness problem.
- [README.md](../GPU-Communication/README.md) — what NCCL expects of a lossless fabric.

## References
- Credit loops & losslessness: https://enterprise-support.nvidia.com/s/article/howto-prevent-infiniband-credit-loops
- IB QoS / SL2VL / arbitration (DOCA): https://networking-docs.nvidia.com/doca/archive/3-4-0/infiniband-qos
- NCCL env (SL / timeout): https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html
- IB vs RoCE comparisons: https://www.vcluster.com/blog/gpu-cluster-networking-infiniband-roce · https://intelligentvisibility.com/ai-networking-solutions/ethernet-vs-infiniband
- IB security docs (node types / P_Key / SM): https://networking-docs.nvidia.com/nvidiainfinibandsecurityoverviewandguidelines/security-in-infiniband
