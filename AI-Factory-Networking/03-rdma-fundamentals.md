# RDMA Fundamentals
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: OpenFabrics Alliance (verbs API), Linux kernel RDMA docs, Mellanox/NVIDIA ConnectX docs; arithmetic from section constants bank (2026-08-25).

## 30-Second Explanation
RDMA — Remote Direct Memory Access — is a **programming model plus a set of NIC hardware
capabilities** that let one machine read or write another machine's memory *without*
involving either machine's CPU, kernel, or TCP/IP stack. The application posts a
**work request** to a **queue pair** on the NIC; the NIC then DMAs the data out of the
local memory, drives it across the fabric, and the remote NIC DMAs it into the remote
application's memory — generating only one completion event at the end. The result:
kernel bypass, zero-copy, CPU bypass, and microsecond-scale latency that a socket-based
stack cannot reach. Every AI fabric transport in this section (InfiniBand, RoCEv2, UET)
is a *carrier* for this model: change the wire, keep the verbs.

## What
RDMA is not a protocol; it is a **memory-access semantic over a fabric**. Four properties
define it [F: OFA verbs definition]:
1. **Kernel bypass** — the fast path (post work, poll completion) never enters the kernel.
2. **Zero copy** — data moves application memory → NIC → wire → NIC → application memory,
   with no intermediate kernel buffers.
3. **CPU bypass** — neither the sending nor the receiving CPU touches the data in flight
   (for one-sided operations; see two-sided vs one-sided below).
4. **Transport offload** — retransmission, ordering, flow control, (optionally)
   segmentation happen in NIC silicon, not in OS code.

```text
Traditional socket path                    RDMA path
Application                                 Application Memory
    ↓                                            ↕
Socket API                        RDMA library / verbs
    ↓                                            ↕
Kernel TCP/IP stack               NIC / HCA (RDMA engine)
    ↓                                            ↕
NIC DMA (into kernel buf)         Network
    ↓                                            ↕
Copy to user (2nd DMA)            Remote NIC / HCA
    ↓                                            ↕
Application copy (3rd copy)       Remote Application Memory

copies: 2–4 per message, N kernel transitions    copies: 0, 0 CPU context switches
```

### Why
The socket path costs, per message: syscall entry/exit (kernel transition), TCP/IP
processing, 2–4 memory copies, and context switches when data is large. At 12.5 GB/s
(100 Gb/s), copying 1 MB four times takes the memory bus ~0.3 ms — pure overhead with
no progress [E: 4 × 1MB at ~30 GB/s effective DDR traffic ≈ 0.13 ms per copy-pair, order
of magnitude]. RDMA removes the copies and the kernel from the *data* path; the NIC's
RDMA engine does the transport. This matters when the message size is in the
100 KB–100 MB range and the operation happens every millisecond (collective
communication), not when the message is 1 KB and rare (web traffic). [I: standard]

### How — the object model
The verbs API (ibverbs) exposes a small object model. Every other concept in this section
is built from these:

```text
Device (HCA)
 └── Protection Domain (PD)         — security/namespace boundary; QPs and MRs must
                                      share a PD to interact
 ├── Memory Region (MR)             — registered (pinned) memory + rkey/lkey
 │    ├── lkey: used locally (e.g. local DMA source checks)
 │    └── rkey: exported; remote RDMA WRITE/READ must present the correct rkey
 └── Queue Pair (QP)                — a unidirectional-transport endpoint pair
      ├── Send Queue (SQ)           — application's posted sends
      │    └── Work Queue Elements (WQEs) — one per posted work request
      ├── Receive Queue (RQ)        — application's posted receives (two-sided ops)
      └── Completion Queue (CQ)     — receives CQEs (completion queue elements)
           └── doorbell             — MMIO register write that says "WQEs are posted"
```

**Memory registration** (`ibv_reg_mr`): the app pins a buffer (page-locks it so the DMA
engine can use a stable physical address), builds the NIC's DMA translation tables, and
gets back an MR with `lkey`/`rkey`. Registration is expensive (ms-scale for large
regions) — so real systems **register once, use many times** (NCCL registers its buffers
at initialization). [F: OFA/NVIDIA practice]

**The complete lifecycle of one RDMA operation** (e.g. RDMA WRITE):
```text
1. App registers buffer B (local MR, rkey exported to peer out-of-band)
2. App creates QP, exchanges QP numbers/keys via a control channel (sockets, IB Mads, ...)
3. App brings QP through states: RESET → INIT → RTR → RTS (see ./08-infiniband-queue-pairs.md)
4. App builds WQE: {opcode=RDMA_WRITE, remote addr, rkey, local SGE list, byte count}
5. App writes WQE to SQ memory, rings the doorbell (MMIO write to NIC BAR)
6. NIC fetches WQE, validates keys, DMAs data out of B (scatter/gather)
7. NIC packetizes, applies transport (headers, ICRC), drives onto fabric
8. [network: switches route/forward the packets; retransmission on loss is done by the sending NIC per transport rules (RC), not by switches]
9. Remote NIC verifies (rkey/addr/range), DMAs data into remote buffer
10. Plain WRITE: remote NIC generates **no** CQE — the remote side is never notified (that is the one-sided property); only WRITE-with-IMMEDIATE produces a remote CQE (the 32-bit immediate)
11. Sender NIC generates CQE in sender's CQ (ACK-based, after all data delivered)
12. App polls CQ (ibv_poll_cq) → sees CQE → reuses WQE slots; next operation
```
Note the asymmetry: step 12 happens on the **sender** only (a plain WRITE produces no remote CQE), and step 9's CPU involvement is
*zero* on the remote side — that is the "one-sided" property. [I: standard]

### When
Use RDMA when: (a) message sizes exceed ~64 KB (below that, kernel socket latency may
compete), (b) operations are frequent (µs–ms cadence), (c) the fabric is RDMA-capable
(IB or RoCEv2 or UET). Do **not** use RDMA for: sparse, small, latency-dominated web
traffic, or where the fabric cannot support it (plain Ethernet without RoCE: you get TCP).
The GPU world is the archetype: NCCL's cross-node path is 100% RDMA (or its EFA
equivalent — see [29-cloud-ai-fabrics.md](./29-cloud-ai-fabrics.md)). [I: standard]

### Hardware impact
The NIC must have: an RDMA engine (transport offload: segmentation, retransmission,
ordering, credits/CNP processing), DMA engines sized to sustain line rate (e.g. a 400G
NIC needs ≥50 GB/s DMA throughput, plus PCIe bandwidth ≥ that), registered-memory
translation (IOMMU/page tables), and — on modern SuperNICs — congestion-control hardware
and telemetry. PCIe is the second bottleneck after the wire: PCIe 5.0 x16 gives ~63 GB/s
[E: constants bank], so a 400G NIC (50 GB/s nominal) fits under one x16 gen5 lane group
with headroom; two 400G NICs in one host need gen5 x16 each (or a switch). [I: standard]

### Inference impact
RDMA underlies KV-cache transfer in disaggregated inference: the prefill node RDMA-WRITEs
the request's KV tensors to the decode node's HBM (via GPUDirect) — a bulk one-sided copy
that must finish before the decode step's time budget [F: practice in vLLM/llm-d; see
[35-training-vs-inference.md](./35-training-vs-inference.md) and [Prefill-Decode-Disaggregation.md](../Inference/Prefill-Decode-Disaggregation.md)].

### Example — hand calculation
An 8-rank ring AllReduce of 100 MB over NDR400 (50 GB/s per port) [E: constants bank]:
wire traffic per rank = 2·(7/8)·100 MB = **175 MB/rank**; transfer time ≈ 175 MB / 50 GB/s
= **3.5 ms** plus 14 latency terms (≈14 × 2 µs = 28 µs) → ≈ **3.53 ms**. The RDMA model
is what makes that 3.5 ms achievable: with the socket path, each of the 14 send phases
(7 reduce-scatter + 7 allgather, each moving a 12.5 MB chunk) would pay copy + syscall
costs, and the 14 sequential phases
would accumulate them — a plausible 2–5× slowdown. [E]

### Failure modes
- **Registration failure** — IOMMU disabled, address not pinnable, region larger than
  NIC limits: app can't create MRs; falls back to non-GPUDirect paths or fails init.
- **Wrong key/addr** — rkey mismatch or out-of-range remote address → NIC rejects the WQE
  (local error, CQE with error status, no packets sent).
- **CQ overrun** — app polls slower than completions arrive → CQ overflows, NIC may drop
  CQEs (data already delivered, but the app loses the notification).
- **Doorbell coalescing gone wrong** — posting one WQE at a time with immediate doorbell
  writes wastes PCIe; real apps batch (or the NIC coalesces) — but *over*-batching adds
  latency. [I: standard]
- **PCIe saturation** — DMA reads + wire writes share the PCIe link; a 400G NIC doing
  full send saturates the link and steals DMA bandwidth from the GPU. →
  [37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md).

### How to measure it
`ib_read_bw` / `ib_write_bw` / `ib_send_bw` (perftest) for raw throughput;
`ib_read_lat`/`ib_write_lat` for latency (the "point-to-point" numbers that feed the α
term in [33-collective-communication.md](./33-collective-communication.md)); `rdma resource` / `rdma link` on Linux for
live QP/MR/CQ state; `perfquery` counters for the link layer. → [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md).

## Two-sided vs one-sided — the operation families
| Operation | Sender CPU | Network | Receiver CPU | Receiver posts in advance? |
|---|---|---|---|---|
| **SEND / RECV** | yes (post send) | yes | **yes** (must have RECV posted) | yes |
| **RDMA WRITE** | yes (post) | yes | **no** | no |
| **RDMA WRITE with IMMEDIATE** | yes | yes | yes (only the 32-bit immediate, via a CQE) | yes |
| **RDMA READ** | yes | yes (read req + read resp) | **no** | no |
| **ATOMIC** (fetch-add / compare-swap) | yes | yes (atomic req+resp) | **no** | no |

```text
Two-sided SEND:                        One-sided RDMA WRITE:
  Sender posts SEND                        Sender posts WRITE
       ↓                                       ↓
  Network                                  Network
       ↓                                       ↓
  Receiver (RECV must be posted)             Remote memory (directed)
  receiver CPU: post + signal                remote CPU: does nothing
```
**When each is used.** SEND/RECV: when the receiver is *part of the conversation* (MPI
point-to-point, control messages, SHMEM put with signaling). RDMA WRITE: when the receiver
is a *target* — gradient exchange in NCCL, checkpoint writes, KV transfer. RDMA READ:
pulling a parameter shard (ZeRO-3), reading a peer's HBM. WRITE-IMMEDIATE: WRITE plus a
"you may now be woken" nudge — the pattern SHMEM and many collective implementations use
(write the data silently, then poke). [I: standard]

## Transports: RC, UC, UD, DC
| Transport | Reliability | Ordering | Connections | Scalability | Typical use |
|---|---|---|---|---|---|
| **RC** (Reliable Connected) | retransmits, ACKs | in-order, per-QP | 1 state per pair (QP) | O(N²) state — the limiter | AI workloads (NCCL default) |
| **UC** (Unreliable Connected) | no retransmit | in-order | 1 state per pair | O(N²) state | rare in AI; lossy fabrics + upper-layer retry |
| **UD** (Unreliable Datagram) | no | no guarantee | stateless | O(N) — one QP reaches everyone | management (MAD/SMP), small control msgs |
| **DC** (Dynamic Connected, IB ext.) | reliable, retransmits | in-order per target | **O(N)** — shared target context | the fix for O(N²) | large HPC where RC state explodes |

RC is what NCCL and virtually all AI traffic use. Its weakness: an N-rank job needs N·(N−1)
QP states across the cluster (1024 ranks → ~1 M QPs, tens of thousands of MBytes of NIC
state) — a real memory/scaling cost that DC transport and UET's connection model attack.
→ [31-uetch-deep-dive.md](./31-uetch-deep-dive.md). [I: standard analysis]

## RDMA networks that carry it
```text
RDMA (the model)
├── InfiniBand      — native fabric: IB link layer, credits, LID/GID addressing
├── RoCE            — carried in Ethernet: v1 (L2, un-routable), v2 (UDP/IP, routable)
├── iWARP           — carried in TCP (IETF standard, RFC 5040; rare in AI)
├── UET (Ultra Ethernet Transport) — clean-slate RDMA-inspired transport, UEC 1.0
└── Cloud-optimized fabrics (AWS EFA/SRD — RDMA-like, not IB/RoCE)
```
Detailed comparisons: [04-rdma-operations-and-transports.md](./04-rdma-operations-and-transports.md) (operations on each),
[49-design-decision-tree.md](./49-design-decision-tree.md) (fabric choice), [51-complete-packet-journeys.md](./51-complete-packet-journeys.md)
(the same 175 MB chunk, three ways).

## Key Takeaways
1. RDMA = verbs object model (PD/MR/QP/CQ) + NIC hardware that DMAs and offloads transport.
2. Registration is once-and-reuse; doorbells are how the app wakes the NIC; CQEs are how
   the NIC reports back.
3. One-sided ops (WRITE/READ) are the GPU-world workhorses: receiver CPU does nothing.
4. RC is the AI default; its O(N²) state is the scaling pressure that DC and UET address.
5. Measure with perftest (bandwidth/latency pairs) before touching anything fancier.

## Related
- [04-rdma-operations-and-transports](./04-rdma-operations-and-transports.md) — op-by-op wire formats and RC/UC/UD/DC.
- [05-infiniband-architecture](./05-infiniband-architecture.md) — the reference fabric that carries RDMA.
- [15-gpudirect-rdma-nccl-infiniband](./15-gpudirect-rdma-nccl-infiniband.md) — RDMA with the GPU as memory endpoint.
- [06-nccl-rdma-sharp](../GPU-Communication/06-nccl-rdma-sharp.md) — NCCL's RDMA transport in practice.
- [16-performance-benchmarking](../GPU-Communication/16-performance-benchmarking.md) — perftest/nccl-tests how-to.
- [55-cheat-sheet](./55-cheat-sheet.md) — perftest and rdma-tool command groups.

## References
- OpenFabrics Alliance, verbs API & InfiniBand architecture overview (ofa.org).
- Linux kernel RDMA documentation (kernel.org: Documentation/infiniband/).
- Mellanox/NVIDIA: "RDMA Aware Networks" user manual; ConnectX Datasheet.
- [E] figures from the section constants bank (computed 2026-08-25).
