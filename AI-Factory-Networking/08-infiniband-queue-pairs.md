# InfiniBand Queue Pairs: QP Lifecycle, Work Queues, and Completion
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: IBTA `packet.transport.ib` manpage, OpenFabrics verbs/ibverbs, NVIDIA ConnectX (BlueFlame) documentation; arithmetic from section constants bank (2026-08-25).

## 30-Second Explanation
A **Queue Pair (QP)** is the *endpoint* of RDMA: one object on each NIC that holds a **Send Queue (SQ)**, a **Receive Queue (RQ)**, and gets completions written to a **Completion Queue (CQ)**. The application posts **Work Requests (WRs)** — which become **WQEs** in the SQ/RQ — and the NIC executes them and writes **CQEs** when done. To use a QP you must walk a **state machine**: `RESET → INIT → RTR → RTS`. Each transition unlocks exactly one capability: INIT lets you post work queues; RTR lets the NIC *receive* wire packets; RTS lets it *send* too. The whole model is a deferred-work pipeline: **posts are cheap (you ring a doorbell), completion is the only place you're told anything happened.** This page is the deep treatment of the object partly sketched in [03-rdma-fundamentals.md](./03-rdma-fundamentals.md).

## What
The QP model, concretely [F: OpenFabrics verbs / IBTA]:

```text
                    ┌────────────── QP (endpoint) ──────────────┐
                    │  Send Queue (SQ)   Receive Queue (RQ)     │
    App posts ───►  │  [WQE][WQE][WQE…]  [WQE][WQE][WQE…]       │
  work requests     │       │                │                  │
                    │       └──► NIC RDMA engine ◄──┘            │
                    └───────────────┼──────────────────────────┘
                                     │ writes
                                     ▼
                              ┌──────────────┐
                              │  CQ (Completion Queue)          │
                              │  [CQE][CQE][CQE…]               │
                              └──────────────┘
      doorbell = NIC MMIO reg write "SQ/RQ has new WQEs"
```

- **QP (Queue Pair)**: the transport endpoint, identified by a **QPN (Queue Pair Number)**, an integer the HCA assigns at creation and the peer must learn to talk to you.
- **WR (Work Request)** → **WQE (Work Queue Element)**: a posted operation. WQE fields: opcode (SEND, RDMA_WRITE, RDMA_READ, …), SGE list (scatter/gather), remote key/address, flags (signaled? inline? fence?).
- **SQ**: holds send-side WQEs. **RQ**: holds receive-side WQEs (only used by two-sided ops — SEND/RECV — and WRITE_WITH_IMMEDIATE).
- **CQE (Completion Queue Element)**: the NIC's report that a WQE finished (or errored); carries opcode, qp, byte count, and a status code. Only *signaled* WQEs generate a CQE (see Tuning).
- **CQ**: the queue that receives CQEs, can be driven by polling or by event.
- **Doorbell**: because WQEs live in host memory, the NIC needs a poke; the app writes to a **doorbell register** (MMIO) on the NIC, and the NIC then fetches the newly posted WQEs.

## Why
RDMA's entire bet is that the *data* never touches a kernel, so it constructs a **work-queue economy**: the host only does two cheap things — post work (a memory write + a doorbell) and consume result (poll/event a CQ) — and the NIC does the expensive transport off in silicon [I: architecture of the verbs model]. That splitting is why one host can drive tens of QPs at 50 GB/s without syscalls: the fast path is *never* in kernel code [F: OpenFabrics].

The state machine exists because a QP is a shared, two-ended resource: the NIC must not transmit before the *peer's* QP is ready to receive, and neither side can be allowed to send garbage before the necessary attributes (QPN, keys, path, starting PSN) are agreed. States gate capability so a half-configured QP cannot emit packets into a healthy fabric [I].

## How — the QP state machine
States in the RC/UC lifecycle (the four the task cares about, plus the error/extra states for completeness) [F: IBTA / verbs `ibv_modify_qp`]:

```text
  RESET ──(modify: set QPN, P_Key, port, access_flags)──► INIT
   ▲                                                       │
   │                                                       │ (modify: path, RQ-depth,
 error / re-init                                            │  dest QPN, PSN start, ...
   │                                                       ▼
  SQE(ERROR)                                           RTR (Ready to Receive)
   ▲                                                       │   can now RECEIVE on wire
   │ (SQ error / fatal)                                    │ (modify: SQ enable)
   │                                                       ▼
  └───────────────────────────────────────────────   RTS (Ready to Send)
                                                       can SEND + RECEIVE on wire
```

| Transition | What it enables | What you must provide first |
|---|---|---|
| RESET → INIT | posting WRs to SQ/RQ (local), but **no wire traffic** | QPN, P_Key, port number, access flags |
| INIT → RTR | the NIC may **receive** packets belonging to this QP | remote QPN, path (msg? SL/MTU/rate), RQ depth, initial PSN |
| RTR → RTS | the NIC may also **send**; full duplex live | SQ enable, (opts: timeout/retry counters, SQD path, rnr) |
| RTS → SQD (Sq Drained) | draining in-flight sends before a modify | — |
| any → SQE / ERROR | stop; dead QP (or modified-in-error) | — |

**What each transition enables, precisely** [A: standard verbs semantics]:
- **RESET→INIT**: you may post to SQ *and* RQ. The link is still silent on the wire — this is the "load the gun" state. It also validates the QP's own attributes.
- **INIT→RTR**: the NIC is told "expect incoming packets for QPN X from peer Y with this starting PSN"; it now accepts and processes inbound RC packets and can DMA received data into posted receive buffers. No transmits yet.
- **RTR→RTS**: enable the SQ; the QP is fully live in both directions and will immediately start draining posted sends.

A common bug: posting SEND WQEs before RTS (they sit unsent), or *enabling* RQ before RTR is reached (packets dropped). The transition order forces you to bring the *receive* side ready before the *send* side, which is exactly what a reliable protocol needs [I].

### Packet flow — one full RC exchange
```text
Host A (QP n)                     wire                     Host B (QP m)
post SEND {data} ─ ring doorbell
  NIC builds LRH+BTH{SendLast,AckReq,PSN}+data
  ──────────────► [BTH SEND] ──────────────►  NIC: match QP m, consume RQ WQE,
                                                DMA data into B's buffer
  ◄────────────── [BTH Ack (AETH ACK)] ──────  NIC posts CQE to B's CQ
  NIC gets ACK ─ posts CQE (completion)          (app polls/event → done)
```
For one-sided RDMA_WRITE the receiving side posts *no* RQ WQE (no receive consume); the only CQE on B is a silent delivery unless IMMEDIATE data / signaled is used. See [03-rdma-fundamentals.md](./03-rdma-fundamentals.md) for the two-sided vs one-sided table.

## Hardware impact
Each live QP consumes HCA state: SQ/RQ ring buffers (in host memory), doorbell registers, and the NIC's per-QP transport context (PSN, retry timers, keys). At scale this is the **O(N²)** problem — an N-rank RC job needs ~N·(N−1) QPs (1024 ranks → ≈1 M QPs, many MB of NIC state), which is precisely why DC transport exists [F/I: see [03-rdma-fundamentals.md](./03-rdma-fundamentals.md) transport table]. The CQ needs headroom (measured in CQEs) or it overflows; the QP needs enough SQ/RQ depth for in-flight work.

## Inference impact
Serving and disaggregated-inference layers each reserve QPs and register buffers once. The steady-state cost is *latency from doorbell→CQE* per message; for KV-cache transfer (a bulk one-sided WRITE), QP setup cost is amortized and the gating factor is payload transfer time, not QP mechanics [I]. A badly sized CQ depth or a polling-vs-event mismatch directly shows up as tail latency in decode.

## Example — hand calculation
Inline threshold and doorbell batching change how many PCIe writes a 1000-message burst costs [E-derived; see Tuning]:
- **Inline off, 4-KB payload:** every message DMAs the payload after a doorbell → 1000 doorbells + 1000 DMA reads of 4 KB = ~4 MB pulled over PCIe.
- **Inline on (e.g. 128-B threshold), 64-B messages:** payload rides inside the WQE → one doorbell per message, no per-message DMA read of the payload. For 1000 × 64 B = 64 KB total, you save ~64 KB of DMA traffic plus the latency of each DMA fetch [A: threshold value; mechanism standard].
Rule: messages *under* your NIC's inline threshold are cheaper sent inline; larger ones should be batched (multiple WRs, one doorbell) to amortize the MMIO write. Batching 8 WRs per doorbell cuts doorbell PCIe traffic 8× [I].

## Failure modes
- **CQ overrun:** more signaled completions than CQ depth → CQ overflow, CQEs lost; data may already be delivered but the app never learns. Fix: size depth, poll faster, or mark fewer WRs signaled.
- **SQ/RQ under-posted:** a one-sided WRITE needs *no* RQ WQE, but a SEND does — forgetting the RECV strands the sender in `RTS` waiting forever (timeout/RNR) [I].
- **Wrong QPN / key:** packets to an uncreated QPN, or with a bad key, are dropped/NAK'd; symptoms are retries then `Timeout`/`Reset` errors.
- **QS in the wrong state:** SEND posted in `INIT` never goes out; receiving before `RTR` drops everything.
- **Error QP quarantine:** one error normally poisons just that QP (or, on some firmware, forces draining) — apps must re-create/re-init rather than reuse a QP in `SQE`.

## How to measure it
`rdma resource show qp` / `rdma qp` on Linux show every live QP, its state, port, and path [A]; `perftest` (`ib_write_bw`, `ib_send_lat`) isolates QP mechanics; `rdma resource show cq` shows CQ depth/use. Watch `nv_peer_mem`/`ib_read_bw --use_cuda` for GPU-memory-backed QP data. On the wire, `rdma debug` / hardware counters expose doorbell counts and CQ overruns [I].

## Design — doorbell posting, inline, SRQ, BlueFlame
**Doorbell posting.** WRs are written into host-memory SQ/RQ rings; the NIC learns via a doorbell MMIO write to its BAR. Naive per-WR doorbells serialize PCIe traffic, so real apps **batch** (write N WRs, ring once) — the NIC also supports **doorbell batching records** (a host-side batch buffer the NIC drains as one unit) [F: NVIDIA ConnectX doorbell batching]. 

**Inline data.** For small payloads (typ. ≤ 112–256 B depending on HCA, a vendor threshold), the application sets `IBV_SEND_INLINE` on the WR and the data bytes are copied **into the WQE itself** — they travel to the NIC in the same write-combined doorbell transaction, with no separate DMA read of the payload, removing both a DMA round-trip and a latency spike [A: vendor inline threshold].

**SRQ (Shared Receive Queue).** One RQ is shared by many QPs: a single pool of receive WQEs is *consumed by whichever QP needs a receive buffer next*. This lets a server pre-post a large buffer pool once and have any incoming SEND land in it. Benefit: you stop posting N receive WQEs per connection; SRQ amortizes memory and the receive-post cost across connections — the standard pattern for connection-per-rank fabrics [F: verbs `ibv_create_srq`].

**BlueFlame-style write-combined posting.** NVIDIA ConnectX's *BlueFlame* posts SEND WQEs and the doorbell as **write-combined (WC) MMIO writes**, so the doorbell "kick" rides in the very same PCIe transaction that carries the WQE — no extra round trip to nudge the NIC. Effectively the NIC discovers + executes a posted WQE with the minimum possible host-side transactions [F: vendor documentation / architecture]. The SRQ + BlueFlame + inline trio is why one host can sustain tens of millions of small ops/s with near-idle CPUs [I].

## Tuning
- **Complete fewer ops:** unset `signaled`/`IBV_SEND_SIGNALED` on the WRs you don't care about; post a *fence* or a tailing signaled WR so the CQ still tells you when the batch drained. Drives CQ pressure down in proportion.
- **CQ event vs poll:** busy **polling** `ibv_poll_cq` gives the lowest latency but burns a CPU; **event** completion (`ibv_req_notify_cq`) frees the CPU but adds notification latency. Industrial practice is a hybrid: sleep on the event, then burst-poll [I: standard].
- **Depth sizing:** SQ/RQ depth ≥ in-flight WRs (≈ BW × RTT / message size); CQ depth ≥ signaled WRs in flight. Under-size → stalls/overruns.
- **Inline threshold:** keep it just under the NIC cap; don't inline messages big enough that the copy into the WQE costs more than the DMA you saved [I].

## Comparison
| Mechanic | Purpose | Host cost | When it wins |
|---|---|---|---|
| Doorbell batching | amortize NIC notice | one MMIO per batch | many small WRs |
| Inline data | skip payload DMA-read | copy into WQE | payload < threshold |
| SRQ | share receive buffers across QPs | one post, many consumers | per-rank connections |
| BlueFlame / WC posting | co-locate WQE + doorbell | single WC transaction | low-latency sends |
| Poll vs event CQ | completion discovery | CPU vs latency | latency-sens. vs scale |

## Memory keys in use during QP operation
Two key families are in play the moment a QP runs [I; MR keys are [F: OFA verbs]]:

1. **Memory-region keys (lkey / rkey).** `ibv_reg_mr` returns an MR with a local **lkey** (used by the *local* NIC when it DMAs out of the buffer) and a remote **rkey** (exported to the peer so its NIC can RDMA into your buffer). These are literally carried in the **RETH** of RDMA ops ([09-infiniband-packet-format.md](./09-infiniband-packet-format.md)). The QP's SQ/RQ WQEs reference SGEs by lkey; one-sided ops present the peer's rkey to prove access.
2. **Transport/fabric keys (Q_Key, P_Key).** A **Q_Key** gates UD datagram access (a value both sides must share, carried in the DETH). The **P_Key** is the partition key in every **BTH** — the QP is bound to a P_Key at `INIT`, and the switch can enforce the partition at the port (`./12-...`). A QP whose P_Key doesn't match the partition is effectively invisible.

```text
  keys a live RC QP touches:
  ┌─────────────────┬────────────────────────┬───────────────────────┐
  │ lkey  (local)   │ rkey (remote)          │ P_Key / Q_Key         │
  │ SQ WQE SGEs     │ RDMA_WRITE/READ target │ BTH(P_Key)/DETH(Q_Key)│
  │ validated locally│ validated by peer NIC  │ validated per packet  │
  └─────────────────┴────────────────────────┴───────────────────────┘
```

### Error handling: RNR, retries, and the error state
Reliable transports add a few behaviors that shape the lifecycle [I; standard RC semantics]:
- **RNR (Receiver-Not-Ready):** a SEND arrives and the RQ has **no receive WQE posted** (or SRQ is empty). RC returns an **RNR-NAK** and the sender backs off (with a configured `rnr_timer`) and retries — rather than dropping.
- **Retry counters:** RC tracks `retry_count` (max re-sends) and `rnr_count` (max RNR re-attempts); exceeding them puts the QP into error and a CQE with failure status.
- **SQD (Sq Drained):** a transient state to drain in-flight sends before a QP attribute change; a real failure instead sends the QP to **SQE (SQ Error)** — from which the only reasonable move is destroy and re-create.

These interact with `NCCL_IB_TIMEOUT`, which sets how long RC waits before declaring a neighbor unreachable — too short on a lossless fabric spooks healthy rounds, too long hides real faults [F: NCCL env docs; see [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md)].

## Example — hand calculation (memory + doorbells)
Take a single HCA with a QP sustaining 50 GB/s [E: constants bank] and 4-KB messages → **12.5 M msg/s**. If every message drains one CQ depth slot and is signaled, the **CQ needs ≈ in-flight messages headroom**. At a generous 10 µs round trip that's ~125 in-flight; a CQ depth of 256 is comfortable. Now give each message a **separate doorbell** (a PCIe MMIO write): that's 12.5 M pcie-writes/s into the same BAR region — enough to become a real host-bus bottleneck. **Batching at 8 WR/doorbell** cuts it to ~1.6 M doorbells/s; **inline** the 64-B control messages so they skip the DMA read entirely. The arithmetic is why production NCCL posts long, batched, mostly-unsignaled WQEs and reserves huge SRQs instead of one-RWQ/one-CQ at a time [I; mechanics standard].

## Comparison — poll vs event, and when
| | Busy-poll CQ | Event (interrupt)-driven CQ | Hybrid |
|---|---|---|---|
| Latency per completion | lowest (µs) | higher (µs–tens-µs) | low in burst |
| CPU cost | burns a core per poller | near-zero idle | event to wake, poll in burst |
| Scale | 1 host, few QPs | many QPs, many hosts | the usual production choice |
| Risk | CPU spins, ASIC-friendly | interrupt storm at high rates | must tune coalescing |

## QP numbers — from well-known management QPs to app QPs
The QPN space is shared: a few are **well-known**, the rest are allocated by the HCA [F: IBTA / manpage]:
```text
  QP0  — SMP (subnet-management)   → the SM uses this to probe/manage the fabric
  QP1  — GSI / general services (SA path records, etc.)
  QPs 2+ — application QPs; the HCA hands out numbers at ibv_create_qp
```
The management QPs are why the SM (`./11-...`) and the fabric's own control traffic exist regardless of the app's QPs. When you run `rdma resource show qp` you'll see both the well-known ones and the per-connection app QPs your collective created — a handy sanity check that a QP reached `RTS` and has a path [I].

## Key Takeaways
1. A QP = (SQ + RQ) + a CQ to land completions; **WQEs** are posted ops, **CQEs** are results.
2. You must walk **RESET→INIT→RTR→RTS**; each transition unlocks one capability (post → receive → send) and can't be skipped.
3. **Doorbell = "WQEs are posted."** Batching WRs per doorbell, **inline** small payloads, and **SRQ** for per-rank connections are the three levers that keep the host fast path cheap.
4. **BlueFlame / write-combined posting** co-locates the WQE and the doorbell in one PCIe transaction — the mechanism that makes millions of small ops/s practical [F: vendor].
5. **Poll vs event CQ** is a CPU-vs-latency trade; production uses a hybrid (event to wake, burst-poll).
6. **Keys in play:** memory-region `lkey`/`rkey` for RDMA access, and transport `P_Key`/`Q_Key` for partition/datagram gating [I].

## References
- OpenFabrics / verbs API (`ibv_post_send`, `ibv_create_qp`, `ibv_create_srq`): ofa.org (RDMAn stack docs).
- IBTA — `packet.transport.ib` (QP0/QP1, BTH): https://manpages.ubuntu.com/manpages/noble/man3/packet.transport.ib.3.html
- NVIDIA ConnectX doorbell batching / BlueFlame: NVIDIA ConnectX-6/7 programming & architecture docs `[F: vendor]`.
- Linux `rdma` tooling (`rdma resource show qp/cq`): kernel.org RDMA docs.
- NCCL env (`NCCL_IB_TIMEOUT`, `NCCL_IB_SL`): https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html
- [E] section constants bank (verified-constants.md, computed 2026-08-25) — arithmetic for inline/doorbell batching and message-rate math (50 GB/s → 12.5 M msg/s at 4 KB; ≈125 in-flight at 10 µs RTT; CQ-depth/8×-batching figures).

## Related
- [03-rdma-fundamentals](./03-rdma-fundamentals.md) — the object model and the two-sided/one-sided families this page deep-dives.
- [07-infiniband-addressing](./07-infiniband-addressing.md) — how the LID/GID you need to configure a QP path is resolved.
- [09-infiniband-packet-format](./09-infiniband-packet-format.md) — the BTH that carries QPN, PSN, AckReq on the wire.
- [12-infiniband-routing-topology-partitions](./12-infiniband-routing-topology-partitions.md) — P_Key/partition binding each QP must honor.
- [45-troubleshooting-rdma-infiniband](./45-troubleshooting-rdma-infiniband.md) — QP-state and retry-counter debugging.
- [GPU-Communication/README](../GPU-Communication/README.md) — how NCCL instantiates these QPs per GPU pair.
- [55-cheat-sheet](./55-cheat-sheet.md) — rdma resource / perftest command reference for QP mechanics.
