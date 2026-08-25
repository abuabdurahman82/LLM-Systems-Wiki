# Collective Communication Fundamentals
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
A *collective* is a group communication primitive: N participants each contribute a
buffer, and the operation defines what every participant ends up with. LLM
parallelism maps almost one-to-one onto these patterns — DDP does AllReduce,
tensor parallelism does AllReduce/AllGather, pipeline parallelism does Send/Recv,
expert parallelism does All-to-All. Learn the seven shapes and the
`T ≈ α + n·β` cost model and most "why is this slow" questions become arithmetic.

## 1. Point-to-point (the baseline)
```text
GPU 0 ─────────► GPU 1
```
Operations: **Send / Receive / Put / Get / Read / Write**. Two-sided (Send/Recv)
needs both ends active; one-sided (Put/Get, RDMA or NVSHMEM-style) needs only the
initiator [F: NVIDIA NVSHMEM docs — "one-sided communication from within CUDA
kernels"]. Use cases: pipeline parallelism activation handoff, KV-cache transfer,
prefill → decode transfer, model weight transfer, checkpoint movement. P2P is also
the *building block*: every library can implement any collective from Send/Recv, at
the cost of many more steps and messages.

## 2. The seven collectives (diagram, input, output, volume, LLM use)

### 2.1 Broadcast
```text
        GPU0
      /  |  \
     ▼   ▼   ▼
   GPU1 GPU2 GPU3
```
Input: one buffer on the root (N−1) ranks empty. Output: everyone has root's buffer.
Volume: O(n) point-to-point traffic from root, ≈ (N−1)×size total. LLM use:
config/weight distribution at startup, embedding-table fan-out, seed broadcast.

### 2.2 Reduce
```text
   GPU0 ─┐
   GPU1 ─┼─► GPU0   (sum/avg/max across all)
   GPU2 ─┤
   GPU3 ─┘
```
Input: one buffer per rank. Output: single reduced value on the root. Volume:
(N−1)×size moved to root. LLM use: rare in inference; gradient reduction when a
parameter server or a single rank aggregates.

### 2.3 AllReduce
```text
   GPU0 [a]  ┐
   GPU1 [b]  ├────► all GPUs end with [a+b+c+d]
   GPU2 [c]  │        (same buffer size as input)
   GPU3 [d]  ┘
```
Input: buffer on every rank. Output: the reduction on *every* rank — same size as
input. Ring implementation moves 2(N−1)/N × size through each link
[E: 2(N−1)/N → 1.0 at N=2, 1.75 at N=8, 1.969 at N=64, 1.998 at N=1024].
LLM use: **the workhorse** — gradient AllReduce (DDP/ZeRO-1), the two per-layer
AllReduces of tensor parallelism, loss synchronization.

### 2.4 AllGather
```text
   GPU0 [a] ──► everyone: [a b c d]
   GPU1 [b]        (each rank's slice concatenated, all ranks)
   GPU2 [c]
   GPU3 [d]
```
Input: 1/N of the final buffer per rank. Output: the full buffer on every rank;
each rank sends its slice, link traffic = (N−1)/N × size. LLM use: ZeRO-3/FSDP
parameter gather, context-parallel sequence assembly, TP AllGather variants.

### 2.5 ReduceScatter
```text
   all GPUs [a b c d] ──► GPU0 [a']  GPU1 [b']  GPU2 [c']  GPU3 [d']
                           (reduced slice per rank)
```
Input: full buffer on every rank. Output: the reduced result partitioned — rank i
keeps slice i. Link traffic (N−1)/N × size; AllReduce = ReduceScatter + AllGather
composed, which is why both appear together in ZeRO-1 (grads) and TP.

### 2.6 All-to-All
```text
   each rank i sends a slice to every rank j; everyone ends with
   the transpose: rank i's k-th output block = rank k's i-th input block
```
Input: N slices per rank. Output: the "transposed" buffer on every rank; every
rank talks to every other — N(N−1) flows, volume (N−1)/N × size per link but with
the worst interference pattern of any collective [I: flow-interference argument].
LLM use: **MoE expert dispatch and combine** — tokens routed to experts on other
GPUs; see [14 MoE Communication](14-moe-communication.md).

### 2.7 Gather / Scatter (asymmetric)
Gather: one rank receives all slices (reverse of scatter); Scatter: one rank sends
slices to all. Input/output on one rank differ in size. LLM use: checkpoint
aggregation on rank 0; data shuffling at dataset boundaries. Lower priority in
LLM serving than the six above.

## 3. Cost model: α + nβ
```text
Communication Time ≈ Latency Cost + Message Size / Effective Bandwidth
T ≈ α + nβ
```
- **α** — fixed latency: kernel launch, protocol handshake, NIC doorbell,
  synchronization round-trips. A few µs on NVLink, tens of µs across a RDMA hop
  [I: typical RDMA RTT 2–5 µs for small messages].
- **n·β** — per-byte transfer cost at the *effective* (not line) bandwidth.

Why it matters, with the canonical numbers from this section [E]:

| Message | On NVLink (~900 GB/s eff.) | On 100 GbE | Dominated by |
|---|---|---|---|
| 1 KiB | ~2 µs | ~10 µs | α (latency) |
| 1 MiB | ~1.2 µs | ~0.084 ms | α + β |
| 16 MiB | 18.6 µs | ~1.3 ms | β (bandwidth) |
| 4.0 GiB | 4.77 ms | 343.6 ms | β (bandwidth) |

- **Small tensors are latency-sensitive** → pick low-α protocols/paths (NVLink,
  LL/LL128, in-network reduction), overlap aggressively.
- **Large tensors are bandwidth-sensitive** → pick high-β paths (NVLink, GDR over
  IB), chunk and pipeline to keep every link busy.
- **The crossover is where algorithm/protocol choice bites** — NCCL's
  algorithm+protocol selection (ring vs tree, Simple vs LL128) exists to be on the
  right side of this crossover per message size; see
  [05 NCCL Algorithms & Transport](05-nccl-algorithms-transport.md).

Contributors beyond the two terms: serialization (packing into protocol frames),
protocol overhead (flags for LL, 128-byte alignment), PCIe traversal (if the path
bounces through the host), NIC latency (QP setup, doorbell), GPU synchronization
(stream/event waits), and network congestion (retransmits on lossy Ethernet).

## 4. Mapping collectives to LLM parallelism
| Parallelism | Dominant communication | Why it appears |
|---|---|---|
| Data Parallel | AllReduce / ReduceScatter | every replica computes its own gradient; parameters must re-synchronize |
| Tensor Parallel | AllReduce / AllGather | each layer's output is partial until split GEMMs combine (row/col splits) |
| Pipeline Parallel | Send / Receive | only the boundary between stages moves (activations backward-pass too) |
| Expert Parallel | All-to-All | tokens must physically land on the GPUs holding their routed experts |
| Sequence Parallel | AllGather / ReduceScatter | sequence shards reassemble for attention, gradients scatter back |
| Context Parallel | AllGather / P2P | ring attention passes KV blocks around the ring |
| FSDP / ZeRO | AllGather / ReduceScatter | sharded params gathered just-in-time, grads reduced-and-scattered |
| MoE | All-to-All | same as EP, plus load imbalance makes sizes non-uniform |
| Prefill/Decode Disaggregation | P2P KV transfer | not a collective at all — one producer, one consumer, bulk copy |

Two rows deserve a "why": **TP** splits GEMM row/column so each GPU holds 1/N of a
layer, but the output must be complete before the next op — that *is* an AllReduce
per row-parallel GEMM (two per transformer layer: attention output + MLP output)
[../GPU-Systems/Tensor-Parallelism.md]. **EP** differs from DP AllReduce because
the payload is *tokens*, not parameters, and the destination is decided per-token
at runtime — no fixed schedule, no symmetric volume; that's why EP gets its own
libraries (UCCL-EP, DeepEP) rather than "AllReduce with a twist".

## Key Takeaways
1. Seven shapes cover virtually all LLM communication; know input, output, and
   link volume for each.
2. AllReduce = ReduceScatter + AllGather; that identity is why ZeRO-1/TP talk in
   "both".
3. `T ≈ α + nβ`: small messages die on latency, big ones die on bandwidth — the
   whole algorithm/protocol debate is about the crossover.
4. All-to-All is structurally different from AllReduce: N(N−1) flows, runtime-sized
   messages — MoE's defining property.
5. P2P is both a workload class (KV transfer) and the substrate every library
   builds collectives from.

## Related
[01 Why Communication Matters](01-why-communication-matters.md) ·
[04 NCCL Deep Dive](04-nccl-deep-dive.md) ·
[14 MoE Communication](14-moe-communication.md) ·
[32 Small vs Large Messages → see 16](16-performance-benchmarking.md)

## References
- NCCL User Guide, API (collectives + P2P) — https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/api.html (fetched 2026-08-25) [F]
- NVSHMEM docs (one-sided model) — https://docs.nvidia.com/nvshmem/ (fetched 2026-08-25) [F]
- `../GPU-Systems/Tensor-Parallelism.md`, `../GPU-Systems/MoE-Expert-Parallelism.md` (internal)
