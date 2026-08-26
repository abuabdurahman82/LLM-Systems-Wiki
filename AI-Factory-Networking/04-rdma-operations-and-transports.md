# RDMA Operations and Transports
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: IB Spec Vol 1 (via `packet.transport.ib` manpage), OpenFabrics verbs docs, NVIDIA/Mellanox ConnectX & InfiniBand docs; [E] figures from section constants bank (2026-08-25).

## 30-Second Explanation
RDMA is five verbs-level operation families plus five transports. The **operations**
are what an application can ask the NIC to do to a *remote* buffer: SEND/RECV, RDMA
WRITE, RDMA READ, WRITE-WITH-IMMEDIATE, and ATOMIC (fetch-add, compare-swap). They split
into **two-sided** (SEND/RECV — the remote CPU must post a matching RECV in advance, so
both sides participate) and **one-sided** (WRITE/READ/ATOMIC — the remote CPU does
nothing; the NIC addresses the remote memory directly with an R_key). The **transports**
are how those operations are made reliable and ordered on the wire: RC, UC, UD, DC
(InfiniBand), plus XRC (an RC variant with a shared receive queue). Page
[03-rdma-fundamentals.md](./03-rdma-fundamentals.md) is the object model (QP/MR/CQ/WQE); this page is the
op-by-op wire behavior and the transport comparison an engineer must pick from.

## What
Four operations families deliver remote-memory access; each has a distinct wire
signature (headers) and a distinct CPU-involvement profile [F: `packet.transport.ib`,
IB Spec Vol 1]:

| Operation | Direction | Remote RDMA headers | Remote CPU work | Receiver must pre-post? | One/two-sided |
|---|---|---|---|---|---|
| **SEND / RECV** | push data to remote | BTH (+ payload) | consumes a RECV WQE, posts completion | **yes** | two-sided |
| **RDMA WRITE** | push data to remote | RETH + BTH | none (just DMA + CQE) | no | one-sided |
| **RDMA WRITE with IMMEDIATE** | push data + 4 B control | RETH + BTH + IETH | sees 4 B immediate in CQE | yes (matches op only) | one-sided data, two-sided signal |
| **RDMA READ** | pull data from remote | RETH (request) then read-response to sender | none | no | one-sided |
| **ATOMIC** (fetch-add / compare-swap) | read-modify-write a remote word | AtomicETH; reply AtomicAckETH | none (NIC executes atomically) | no | one-sided |

Definitions [F: IB transport spec]:
- **SEND**: the remote side must have a **Receive WQE** posted on its RQ; the data lands
  in the buffer that RECV specified and consumes one RECV. Opcodes SEND_FIRST /
  MIDDLE / LAST / LAST_WITH_IMMEDIATE.
- **RDMA_WRITE**: carries **RETH** (remote virtual address + R_key + length); writes
  directly into the remote buffer **without** consuming a remote RECV. A plain WRITE
  generates **no completion on the remote side** — that is the one-sided property; only
  WRITE_WITH_IMMEDIATE produces a remote CQE (carrying the 4-B immediate).
- **RDMA_READ**: request (RETH) travels to the target; the target NIC reads its local
  memory and returns **read-response** packets to the requester. That is one request→response
  round trip (request to target, response back), so READ latency **>** WRITE latency
  (an extra full round trip); READ bandwidth is often lower at small sizes on some NICs.
- **WRITE WITH IMMEDIATE**: a WRITE plus a 4-B **Immediate Data** carried in the
  **IETH** (4 B); the 4 B are placed **into the remote CQE**, not into remote memory —
  a zero-cost "you may proceed" flag attached to a DMA.
- **ATOMIC**: FETCH_AND_ADD and COMPARE_AND_SWAP on a remote 8-B word; the NIC does the
  RMW in its memory-interface atomically. Request carries AtomicETH; the reply carries
  AtomicAckETH with the *original* value [F: `packet.transport.ib`]. (The note in
  research calls out that a pseudo-opcode "CND" is **not** standard — the congestion
  packet is **CNP**, covered in [10-infiniband-flow-control-and-qos.md](./10-infiniband-flow-control-and-qos.md).)

For the **transports** that carry these ops — RC, UC, UD, DC, XRC — see the
**## Comparison** section below.

## Why
The whole point of distinguishing two-sided from one-sided is **who pays**. A
two-sided SEND requires the remote application to have *already* posted a RECV: the
receiver is a **peer** in the conversation and its CPU is on the hot path (it must run
to post the RECV, and it processes a completion when data arrives). A one-sided WRITE
or READ treats the remote machine as a **memory target**: the sender supplies the
address and the R_key, and the remote NIC DMAs the data with zero remote CPU work [I:
standard RDMA model]. Consequences:

- **One-sided ops are how GPUs exchange gradients.** NCCL's cross-node data path is
  RDMA WRITE (push) — the receiving GPU's CPU and HCA can receive at line rate because
  no receive-side protocol processing is required. [F: NCCL is RDMA-based]
- **SEND/RECV is how MPI point-to-point and control/signaling work**, where the
  receiver must know a message is coming and match it to a buffer.
- **WRITE-WITH-IMMEDIATE is the "write data silently, then poke" pattern** — SHMEM
  put-with-signal and many collective implementations use it to give a receiver a
  cheap lightweight wake-up without a full second message.
- **READ is how a node pulls work it doesn't own** — e.g. fetching a parameter/GEM shard
  from a peer (ZeRO-3 unshard path) rather than having the owner push it.

The transport choice then decides whether any of this is *reliable and in-order*. RC
retransmits and reorders; UC does not retransmit; UD is a fire-and-forget datagram;
DC is RC with O(N) connection state [I: standard]. That's a separate axis from the
operation type.

## How — the object-model to wire path
Every operation is built the same way at the verbs level [F: OpenFabrics verbs]:
1. The app registered a Memory Region (MR) on the *source* buffer (and the *target*
   down-machined its buffer and exported its `rkey` over a control channel out of band).
2. The app posts one **Work Request** (WR) on the Send Queue with an opcode, a
   scatter-gather list (SGE), and — for one-sided ops — the remote address + rkey.
3. The NIC consumes the WR, DMAs from the SGE, prepends headers, runs transport
   (credits, sequencing), and sends.
4. A **completion** (CQE) lands on the originating CQ; for SEND/RECV the receiver also
   gets a CQE; for one-sided ops the remote may get only a CQE (no data-path CPU).

```text
Application                     HCA fast path
   │ post WR (opcode, SGE, rkey)      │
   │ ring doorbell (MMIO)             │
   ▼                                  ▼
┌─────────────────┐   fetch WQE   ┌──────────────────┐
│ SQ / RQ / CQ    │ ─────────────▶│ Transport engine │
│ (WQEs, CQEs)    │               │ · DMA SGE        │
└─────────────────┘               │ · add headers    │
        ▲                         │ · sequence/credits│
        │ poll CQ (ibv_poll_cq)   └────────┬─────────┘
        │ CQE: consumed WR status          │ packets → port (LRH/BTH/RETH…)
```

### SEND/RECV in detail — two-sided pairing
```text
Sender:                                  Receiver:
post send WR {SGE}                       MUST already have posted recv WR {SGE}
   │                                           │
   ▼                                           │
[HCA DMA from local buf]                      │
   │ SEND (BTH+payload)                        │
   ├──────────────────────────────────────────▶│ [HCA validates P_Key, QP, PSN]
   │                                           │ DMA into the RECV-specified buffer
   │                                           │ CQE: {consumed 1 recv, remote addr}
CQE at sender: {op fully sent}                 │ (receiver CPU may be idle meanwhile)
```

### RDMA WRITE in detail — one-sided
```text
Sender:                                  Remote target (no RECV posted needed):
post write WR {local SGE, remote VA,
              remote rkey}
   │ RETH(VA,rkey,len) + payload          │ HCA checks rkey + VA range
   ├─────────────────────────────────────▶│ DMAs into remote buffer
   │                                      │ CQE (optional, notify-only)
CQE: op complete
```

### RDMA READ in detail — one-sided pull
```text
Sender:                                        Remote target:
post read WR {local SGE (landing),
              remote VA, remote rkey}
   │ RDMA_READ_REQUEST (RETH)                 │ HCA looks up rkey/VA
   ├─────────────────────────────────────────▶│ reads its local memory
   │                                          │ returns read-response data
   │ ◀────────── RDMA_READ_RESPONSE ──────────┤ (AETH + payload)
   │ DMA into sender's local SGE
CQE at sender.
```
Note the extra request→response round trip: the *sender's* latency includes the trip
out and back; the remote CPU never runs [I: wire behavior].

### ATOMIC in detail
```text
Sender:                                       Remote target:
post atomic WR {op=fetch_and_add,
                remote VA, rkey, addend}
   │ ATOMIC request (AtomicETH)               │ NIC RMWs the 8-B word atomically
   ├─────────────────────────────────────────▶│ returns AtomicAckETH {original value}
   │ ◀────────── ATOMIC response ──────────────┤
CQE contains the original remote value         │
```
Atomic ops are the basis of lock-free distributed data structures and MPI one-sided
accumulate/reduce-to-memory; they are rarely the byte-heavy path in LLM training (that
is WRITE/READ), but they are how per-rank flags and agreement counters are kept
consistent without messaging. [I: standard]

## When
- **SEND/RECV**: control messages, MPI point-to-point, and any case where the receiver
  must know *what* is arriving and match it to a logical buffer. Low-to-medium
  message-count, correctness-critical control paths.
- **RDMA WRITE**: bulk data you own and want to *push* — gradient exchange, checkpoint
  writes, KV-cache shipping in disaggregated inference. This is the **default AI
  collective op**.
- **RDMA WRITE + IMMEDIATE**: when a bulk write must also signal the peer (e.g. a
  chunk-complete flag, a "you may reduce now" nudge) without a separate control packet.
- **RDMA READ**: pull models (the owner does not know you want its data, or you want to
  fetch it on demand) — parameter/GEM shard fetch in ZeRO-3, out-of-core inference.
  READ also lets a target stay completely passive.
- **ATOMIC**: producers/consumers, distributed locks/counters, one-sided MPI accumulate.
- **Which transport**: RC for essentially all AI traffic (reliable + in-order);
  UD for multicast + SMP/MAD management; DC where RC's O(N²) state explodes at huge
  scale; UC almost never in AI (upper-layer retry). See **## Comparison**.

## Packet flow — headers by operation
Within a subnet the always-present headers are **LRH (8 B) + BTH (12 B) + ICRC (4 B)**;
one-sided ops add **RETH (16 B)** for WRITE/READ, or **AtomicETH (28 B)** for atomics.
Inter-subnet (router) adds **GRH (40 B)** before the BTH [F: `packet.transport.ib`].

```text
 0                    8       16       24       32        40        48
|---------------------|--------|--------|--------|---------|---------|
| LRH (8B)  [GRH if routed, +40B]      | BTH (12B)  | optional hdr | payload | ICRC(4) | VCRC(2)
                       opcode/P_Key/PSN    RETH(16)  ←WRITE/READ
                                           AtomicETH(28) ←ATOMIC
                                           IETH(4, carries 4B imm) ←WRITE_WITH_IMM
                                          DETH(8) ←UD only
```

Within-subnet header cost [E, constants bank]:
- **SEND** (LRH 8 + BTH 12 + ICRC 4) → **24 B/packet**; at a 256 B payload that is **24/256 = 9.38%** overhead [E: bank].
- **RDMA WRITE** adds RETH (16 B) → 40 B/packet (24 + 16); still under the RoCEv2 58 B because there is no Ethernet/UDP/IP envelope [E: bank w/ RETH from manpage].
- **ATOMIC** adds AtomicETH (28 B) → 52 B/packet (24 + 28).

So an NDR400 port (50 GB/s) carrying 256 B SENDs pays 9.38% of its wire budget to
headers; carrying 4096 B payloads pays **24/4096 = 0.59%** [E: bank]. **Use the largest
MTU (4096) for bulk collectives** — that is exactly why NCCL's Simple protocol packs
data into maximum-size packets. [I: standard]

## GPU relationship
GPUs do not speak verbs; the **HCA's RDMA engine** does, on behalf of a communication
library (NCCL/RCCL/MPI). The `rkey` is the remote GPU's **registered HBM buffer**
(pinned through GPUDirect, often via `nvidia-peermem`/BAR1 peer mapping). [F: GPUDirect
RDMA practice]
- **WRITE = the gradient path.** Each rank WRITEs its reduced gradient chunk into the
  next rank's HBM; the receiving GPU is busy computing while the HCA absorbs the write.
  This is why **one-sided WRITE is the performance backbone** of ring/ tree AllReduce.
- **WRITE_WITH_IMMEDIATE** appears in collective handshake phases to signal chunk
  receipt. [I]
- **READ = the shard-fetch path** (ZeRO-3/FSDP unshard): rank fetches a param shard
  from a peer's HBM by READ rather than having the owner push.
- **ATOMIC** is used sparsely in GPU collectives; NCCL generally prefers WRITE + a
  reduction in the destination, or SHARP in-network reduce (see
  [14-sharp-in-network-reduction.md](./14-sharp-in-network-reduction.md)).
- Crucially, **the CUDA-aware layer is what translates "GPU buffer" to an rkey**; if
  GPUDirect is broken (IOMMU on, ACS, bad `nvidia-smi topo`), NCCL falls back to a
  host-staged copy and one-sided bandwidth collapses. → [15-gpudirect-rdma-nccl-infiniband.md](./15-gpudirect-rdma-nccl-infiniband.md), [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md).

## Design
When designing an app/library around these ops [I: design guidance]:
1. **Prefer WRITE for push, READ only when you must pull.** WRITE has one wire trip for
   the data path (plus optional ACK); READ costs a request round trip, so at small
   sizes READ latency is roughly 2× WRITE's. [I]
2. **Register buffers once, reuse rkeys.** Memory registration is expensive (page-lock +
   NIC translation tables); NCCL registers its buffers at init and reuses them. [F: 03]
3. **Match transport to reliability need.** If you retransmit at the app layer anyway,
   UC/UD may suffice; if you need in-order delivery with no app bookkeeping, RC/DC.
4. **One-sided signature for receiver intrusion:** SEND/RECV is correct whenever the
   receiver *owns* the buffer layout; WRITE-with-rkey is correct when the sender owns
   the address and the receiver just provides a registered window.
5. **State budget:** RC = one QP (state) per connected pair; at N ranks that is ~N²
   QPs across the fabric. DC collapses this to O(N) via a shared target context.
   Design the *number of QPs* knowing the NIC's QP capacity (ConnectX-class NICs hold
   tens of thousands of QPs, but 1024 ranks × full-mesh still pressures memory). [I]

## Tuning
At the operation level the tunables that matter [F: NVIDIA/NCCL env + practice]:
- **Max MTU (4096)** on both ends for bulk WRITE/READ — halves header overhead vs 2048.
  [E: 9.38% at 256B vs 0.59% at 4096B]
- **`ibv_fork_init`** if the app forks after registering MRs (avoids CoW breaking DMA).
- **Completion batching / doorbell coalescing** — post many WRs then ring the doorbell
  once (or let the NIC coalesce) to cut PCIe MMIO traffic for small ops.
- **Larger WRs** amortize per-op completion overhead; NCCL uses multi-MB WRs in Simple
  protocol.
- For **READ-bound** paths, prefer enough in-flight READs to cover RTT (RDMA READ
  bandwidth = outstanding-reads × per-read size / RTT).
- **RC retry/ack tuning:** `ibv_modify_qp` retry counts (`retry_cnt`/`rnr_retry`) bound
  how long a QP retransmits before erroring — set generously for long-duration jobs.
- **Adaptive routing caveat:** packets carrying **immediate data cannot be
  adaptively-routed** by Quantum switches; NCCL tracks this, so WRITE_WITH_IMMEDIATE
  traffic takes the non-AR path [F: NCCL issue #1687]. If you need both AR and
  signaling, separate the data (AR-eligible WRITE) from the immediate (control). [I]

## Troubleshooting
Symptom → likely cause (operation/transport axis) [I: practices + research notes]:
- **"Got completion with error" / timeout on one-sided op** → rkey/VA mismatch or
  remote buffer not registered (the target never posted a window). Check `rdma resource
  show qp`, perftest `-x`, CQE error status "invalid rkey / remote access error".
- **SEND stalls but WRITE works** → remote RQ exhausted (no RECV posted): classic
  "receiver not posting RECVs" — grow the RQ depth or switch to WRITE.
- **RDMA READ latency high** → it *is* an extra request→response round trip vs WRITE;
  if you expected WRITE-like
  latency, switch to WRITE (or check for many small READs underutilizing in-flight).
- **ATOMIC hangs / wrong value** → the 8-B word is not 8-B aligned or the remote buffer
  wasn't pinned; atomics need registered, aligned memory.
- **Throughput is fine for WRITE but poor for READ** → not enough outstanding READs;
  raise `max_inline`/inflight, or the target's read bandwidth is NIC-limited.
- **pkey/QP mismatch** → packets silently dropped (P_Key is validated in BTH); symptoms
  are "nodes see fabric but not each other" [F: NVIDIA security-in-IB]. → [07-infiniband-addressing.md](./07-infiniband-addressing.md).
- **CRC/ICRC errors** → physical-layer/BER, not a programming error; see `ibqueryerrors`
  counters (`symbol_error`, `link_error_recovery`). [F: mlx5 counters]

## Comparison — the five transports
The operation you choose is carried by one of these. The four canonical IB transports
plus XRC [F: NVIDIA/OpenSM + InfiniBand docs]; DC is the Mellanox/NVIDIA dynamic-
connected extension used by NCCL [F: NVIDIA InfiniBand docs]:

| Transport | Reliability | Ordering | Connection state | Scalability (state) | Connection setup | Suitable workloads |
|---|---|---|---|---|---|---|
| **RC** (Reliable Connected) | ACK + retransmit, RNR | in-order per QP | 1 QP per connected pair | **O(N²)** QPs cluster-wide | RC CM (out-of-band) | **AI collectives, NCCL default** — most data traffic |
| **UC** (Unreliable Connected) | no retransmit | in-order | 1 QP per pair | O(N²) | RC CM | rare; upper-layer-retry, low-loss fabrics |
| **UD** (Unreliable Datagram) | none (best effort) | none (can reorder) | **1 QP reaches all** (DETH Q_Key) | **O(N)** — stateless | minimal (no CM) | multicast, SMP/MAD mgmt, IPoIB, small control msgs |
| **DC** (Dynamically Connected) | reliable + retransmit | in-order per target | shared target context, **O(N)** | the fix for O(N²) | dynamic per-message connect | very large HPC/AI where RC state explodes |
| **XRC** (eXtended RC) | reliable, as RC | in-order per QP | shared RQ across processes | reduces per-process RQ state | RC CM | multi-process apps sharing a receive queue |

Why RC dominates AI: AllReduce/collectives need **reliable, in-order** delivery and the
NCCL protocol assumes it. Its cost is O(N²) QP state — at 1,024 ranks that is ~1 M QPs.
DC and (in the Ethernet world) UET's connection model attack exactly that pressure.
[I: standard analysis] → [31-uetch-deep-dive.md](./31-uetch-deep-dive.md), [03-rdma-fundamentals.md](./03-rdma-fundamentals.md).

Summary decision:
- Need **multicast / management / many small peers on one QP** → **UD**.
- Need **reliable + in-order + modest node count** → **RC**.
- Need **reliable + in-order at huge scale (state-bound)** → **DC**.
- Need **reliable for a multi-threaded/multi-process consumer** → **XRC**.
- **UC** only where you accept loss+retry above the fabric (rare in AI).

## Lab
1. **Per-op wire signature (two-sided vs one-sided).** Two hosts with ibverbs +
   perftest: run `ib_send_bw` (SEND), `ib_write_bw` (WRITE), `ib_read_bw` (READ),
   `ib_atomic_bw` (ATOMIC) at the same size and record the bandwidth/latency. Expected:
   WRITE ≥ SEND > READ (READ pays the request round trip), atomic is lowest
   throughput. [I: expected behavior] → [16-performance-benchmarking.md](../GPU-Communication/16-performance-benchmarking.md).
2. **Confirm one-sided receiver is idle.** Run `ib_write_bw` server-side while watching
   `top` for the receiver process: the receiver CPU should stay near 0% (only the HCA
   ISR), versus `ib_send_bw` where the receiver end must post RECVs and polls. [I]
3. **Receiver-without-RECV failure.** Post WRITEs to a target that registered an MR but
   never posted a RECV: WRITE succeeds (no RECV needed), SEND fails with RNR/late-wqe.
   This is the cleanest demonstration of the two-sided rule. [I]
4. **Header-overhead check.** Run WRITE at 256 B and at 4096 B payload; the 4 KB run
   should show higher effective throughput because overhead drops from 9.38% to 0.59%
   [E: bank]. Verify against perftest's reported `avg` bandwidth.
5. **Transport behavior.** With a fault-injection cap or a lossy bridge in the path:
   RC retransmits (job survives small loss, packet_seq_err increments); UC/UD drop
   (app must retry above). Observe through `ibqueryerrors` / perftest error counters.
   [I]

## Key Takeaways
1. Five op families (SEND/RECV, WRITE, WRITE-WITH-IMMEDIATE, READ, ATOMIC) split **two-sided** (receiver must post a RECV; its CPU is on the path) vs **one-sided** (remote is a memory target addressed by R_key; its CPU does nothing).
2. **RDMA WRITE is the AI gradient-exchange backbone** (NCCL pushes gradients into the next rank's HBM); READ costs a request→response round trip (≈2× WRITE latency at small sizes) — push, don't pull.
3. Transports add reliability+ordering: **RC (reliable, in-order) is the AI default**, but its O(N²) QP state is the scale pressure that DC and UET's connection model attack.
4. UD (one QP reaches everyone via DETH Q_Key) is the management/multicast/control-plane workhorse; UC is rare in AI (upper-layer retry).
5. Header cost is 24 B/packet (LRH+BTH+ICRC); one-sided ops add RETH (16 B) or AtomicETH (28 B); at 256 B payload that's **9.38%** overhead vs **0.59%** at 4096 B — run **max MTU 4096** for bulk collectives.

## Related
- [03-rdma-fundamentals](./03-rdma-fundamentals.md) — the verbs object model these ops run on.
- [08-infiniband-queue-pairs](./08-infiniband-queue-pairs.md) — QP states and SQ/RQ/CQ mechanics.
- [09-infiniband-packet-format](./09-infiniband-packet-format.md) — all headers/opcodes in byte detail.
- [10-infiniband-flow-control-and-qos](./10-infiniband-flow-control-and-qos.md) — credits that make RC's retransmit meaningful.
- [07-infiniband-addressing](./07-infiniband-addressing.md) — rkey vs LID/GID (what "addressing" really targets).
- [04-nccl-deep-dive](../GPU-Communication/04-nccl-deep-dive.md) — which ops NCCL actually posts.
- [55-cheat-sheet](./55-cheat-sheet.md) — which op/transport to pick, in one table.

## References
- IB Spec Vol 1, transport layer — opcodes, RETH/AETH/AtomicETH, RC/UC/UD semantics
  [F: via `packet.transport.ib` manpage].
- NVIDIA: "RDMA Aware Networks" user guide; ConnectX datasheets [F: vendor docs].
- OpenFabrics / linux-rdma perftest & verbs documentation.
- [E] figures from the section constants bank (computed 2026-08-25).
