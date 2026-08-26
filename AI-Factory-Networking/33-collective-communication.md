# Collective Communication — Primitives & Fabric Impact
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: mlsysbook vol 2 (collective communication), nccl-tests PERFORMANCE.md, NVIDIA NCCL docs; arithmetic from section constants bank (2026-08-25).

## 30-Second Explanation
A collective is a **many-to-many data movement with a fixed pattern** that an AI job
repeats identically tens of thousands of times per training run. The seven primitives —
**Broadcast, Reduce, AllReduce, AllGather, ReduceScatter, AllToAll, Point-to-Point** —
are the vocabulary. For a fabric engineer the numbers that matter are the **wire-traffic
multipliers**: ring AllReduce moves **2(n-1)/n × M** bytes per rank (and holds near-full
bus bandwidth), AllGather/ReduceScatter move **(n-1)/n × M**, AllToAll moves **M** per
rank with *no reduction saving* — the collective that stresses the fabric hardest. The
same job's alternative parallelisms map onto different collectives: Data parallel =
AllReduce, Tensor parallel = many small AllReduces, Expert/Context parallel = AllToAll.
Because every rank runs the *same* collective at the *same* instant, these patterns are
**synchronized, elephant, and identical** — so a single slow path becomes a **tail** that
stalls the whole run (tail latency = JCT). This page teaches the primitives, the ring
mechanics, and the parallelism→traffic map. The UET angle: UET's unordered spraying and
in-network collectives (./32) exist precisely because these patterns wreck hashed,
lossless, single-path fabrics [I].

## The seven primitives
| # | Primitive | What it does | Direction of data | Reduction? |
|---|---|---|---|---|
| 1 | **Broadcast** | root sends one message to all ranks | root → all | no |
| 2 | **Reduce** | all ranks contribute, result lands on one root | all → root | yes (sum/max/…) |
| 3 | **AllReduce** | reduce, then result to **all** ranks | all → all | yes |
| 4 | **AllGather** | gather each rank's slice, result on **every** rank | all → all | no |
| 5 | **ReduceScatter** | reduce, then scatter slices across ranks | all → all (scattered) | yes |
| 6 | **AllToAll** | each rank sends a distinct slice to **each** other rank | all ↔ all | **no** |
| 7 | **Point-to-Point** | one sender → one receiver (send/recv) | pair-wise | no |

AllReduce = ReduceScatter + AllGather composed (conceptually and, in ring, literally
sequentially). AllToAll is the one *pure permutation* — every byte crosses the fabric once
as a distinct flow, so there is **no bandwidth saving**; its true cost is congestion, not
bytes [A/I: research-workloads §1].

## Wire-traffic formulas [E]
Notation: `n` = ranks, `M` = message size (bytes), `B` = link bandwidth (bytes/s),
`α` = per-step latency. These multipliers are the **constants bank** rows [F: nccl-tests
PERFORMANCE.md]:

| Primitive | Wire traffic per rank | Latency term | Notes |
|---|---|---|---|
| **Ring AllReduce** | `2(n-1)/n × M` | `2(n-1)·α` | **[E] 175 MB/rank for n=8, M=100 MB** |
| **AllGather / ReduceScatter** | `(n-1)/n × M` | `(n-1)·α` | **[E] 87.5 MB/rank for n=8, M=100 MB** |
| **AllToAll** | `M` (send) + `M` (recv) per rank | `α` per pair | no reduction; `M/(n-1)` per link |
| **Tree AllReduce (naive)** | `≈ M·log₂(n)` per rank | `2·log₂(n)·α` | time = `2·log₂(n)·M/B + 2·log₂(n)·α` (critical path moves M over log n hops each way); bandwidth-poor; see trees below |

**busbw relation (the number to remember) [E]:** `busbw(AllReduce) = algbw × 2(n-1)/n`.
For n=8 that is `×1.75`. The *algorithm bandwidth* (algbw) is what nccl-tests prints; the
*bus bandwidth* (busbw) is the corrected "how well did I use the fabric" figure — for a
healthy ring AllReduce it approaches the **link rate itself** (`2(n-1)/n × algbw → link` at
saturation; ≈0.95× link with overhead) [F: nccl-tests PERFORMANCE.md; E].

**Worked [E] (n=8, M=100 MB, 400 Gb/s = 50 GB/s, α=2 µs):**
```
Ring AllReduce:  traffic/rank = 2·(7/8)·100 MB = 175 MB
                 T = 175 MB / 50 GB/s + 14·2 µs = 3.500 ms + 0.028 ms = 3.528 ms
AllGather:       traffic/rank = (7/8)·100 MB = 87.5 MB
                 T = 87.5 MB / 50 GB/s + 7·2 µs = 1.75 ms + 0.014 ms = 1.764 ms
```
(The constants bank carries both: `ring AllReduce n=8 M=100MB 50GB/s | 175.0 MB/rank,
t=3.53 ms` and `AllGather n=8 M=100MB | 87.5 MB/rank, t=1.76 ms`.) At large n the ring
AllReduce bandwidth term is at the information-theoretic minimum — ring wins for big
messages; that is why it is the default for large-data-parallel AllReduce [F: mlsysbook].

## Ring AllReduce, step by step (n=4)
Ring AllReduce is two phases: **ReduceScatter** then **AllGather**. With `n=4` ranks and a
total message `M = 40 KiB` (10 KiB per rank's local block), each rank ends with the full
40 KiB reduced result and has moved `2(3/4)·40 = 60 KiB` on the wire — `1.5 × M` [E].

```text
  Phase 1 — REDUCE-SCATTER (n-1 = 3 steps)         Phase 2 — ALL-GATHER (3 steps)
  Ranks r0→r1→r2→r3 form a ring.                   Reduced blocks travel back around.
  Each step, each rank passes its (i+1)-to-a       Each step propagates the fully-reduced
  neighbor the chunk destined for that rank,        chunk toward everyone, so each rank
  adding (reducing) as blocks arrive.               ends holding ALL n chunks.

  Start (each rank holds 10 KiB):                   After RS, r_i holds reduced chunk #i.
   r0: A0 B0 C0 D0     r1: A1 B1 C1 D1             r0:C ✓  r1:D ✓  r2:A ✓  r3:B ✓
   r2: A2 B2 C2 D2     r3: A3 B3 C3 D3
                                                    4 AG steps spread the chunks:
  Step RS1: r0→r1, r1→r2, r2→r3   (10 KiB each)     AG1: r3→r2, r2→r1, r1→r0
  Step RS2: r0→r1, r1→r2, r2→r3   (10 KiB each)     AG2: r3→r2, r2→r1, r1→r0
  Step RS3: r0→r1, r1→r2, r2→r3   (10 KiB each)     AG3: r3→r2, r2→r1, r1→r0
  ── each rank sent 3×10 = 30 KiB             ── each rank sent 30 KiB
  Bytes moved per rank = 30 + 30 = 60 KiB = 1.5 × M ✓    (bank row × 2(3)/4 = 1.5)
```

The three links of the ring are busy simultaneously at every step, which is why ring
AllReduce reaches near-full **bus** bandwidth — every rank's NIC is used in parallel, a
property AllToAll does not share [I].

## Tree implementations
A **reduce + broadcast tree** pairs logarithmic latency with poor bandwidth: naive trees
move a full message at every level — `T_tree ≈ 2·log₂(n)·α + 2·log₂(n)·M/B` — fine for
small messages, terrible for large data-parallel AllReduce [F: mlsysbook]. The fix is the
**double binary tree**: NCCL's algorithm gives **O(log n) latency *and* full (ring-like)
bandwidth** — the reason there is no single hardcoded ring-or-tree rule. NCCL models
`{Ring, Tree, NVLS, CollNet} × {protocols}` per message size and picks the cheapest;
observed behavior is ring for large messages (bandwidth-optimal), tree for small messages
/ large node counts (latency) [F: NCCL modeling; I: NCCL analysis arXiv:2507.04786]. The
old `NCCL_TREE_THRESHOLD` env var was removed in NCCL 2.5 [F: NCCL docs].

```text
  n=8 naive tree AllReduce [E]: latency 2·3·2 = 12 µs (fine)
       per-level full-message cost ≈ 2·3·100MB/50GB/s = 12 ms (terrible for big AllReduce)
  ⇒ ring wins the large-message case; double-tree wins latency without the BW penalty.
```

For near-node local reduce, **NVLS** offloads AllReduce reduction into the **NVSwitch**
(Hopper+, NCCL 2.18+, `NCCL_NVLS_ENABLE`) — qualitatively ~two NVSwitch passes
(a reduce pass + a broadcast pass) instead of `2(n-1)` ring steps [F: NCCL issue #807;
I: exact "2-step" closed form UNVERIFIED]. See [../GPU-Communication/04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md).

## Parallelism → traffic pattern
Each parallelism strategy is a different collective signature over the same physical
fabric [F: mlsysbook; Megatron-FSDP guide; I: standard distributed-training analysis]:

| Parallelism | Main collective pattern | Message size / frequency | Network sensitivity |
|---|---|---|---|
| **Data (DP/DDP)** | 1 AllReduce over grads/step | large (`2G`), once/step | **bandwidth-bound** |
| **ZeRO-3 / FSDP** | AllGather params (2×P) + ReduceScatter grads (2×G) | large, 2–4×/step | **bandwidth-bound**; `2P+2G` = 2× DDP's `2G` |
| **Tensor (TP)** | ~2 AllReduces per transformer layer | **small, very frequent** | **latency-bound** (low α, low jitter) |
| **Pipeline (PP)** | point-to-point send/recv of activations | low volume | latency-sensitive; often overlapped |
| **Expert (EP)** | **AllToAll** dispatch + combine | token-level, no reduction | **incast + skew** (see ./34) |
| **Sequence / Context** | AllToAll K/V rotate, or ring-attention P2P | token/KV-level | fabric-stressing like EP; P2P-heavy |
| **Context (MLA/CP)** | AllToAll K/V | KV-cache sized | bandwidth + incast |

Key implication: **TP and small messages stress *latency*; DP/ZeRO stress *bandwidth*; EP
and context stress the *fabric* (AllToAll / incast).** A single fabric must be good at all
three — which is exactly the tension UET's unordered-spraying CMS (./32) and rail
topologies are engineered for [I].

## Why the fabric engineer must know this
1. **Synchronization ⇒ the slowest rank gates every step.** All ranks block on the same
   collective; one path's microburst delays *everyone*. This is why **tail latency, not
   mean, decides JCT** [I: standard systems argument].
2. **Elephant flows with identical, repeated shapes.** The *same* AllReduce/all-to-all
   fires tens of thousands of times; the fabric sees a repeating, correlated load, so
   hash polarization and routing imbalance compound rather than average out [I].
3. **Incident pattern = wait, not compute.** When a job "hangs" or steps slow, it is
   almost always a collective waiting on the fabric — the all-to-all incast (./34),
   a TP AllReduce gone cross-rack, or a checkpoint burst (see ./51). Knowing which
   primitive is in flight tells you which fabric lever to pull [I].
4. **The numbers give you the diagnosis.** Measure with nccl-tests: if AllReduce busbw is
   far below `0.95 × link`, the topology/NIC has a problem; if AllToAll throughput
   collapses under concurrency, it is incast/congestion control. (See
   [./44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md).)

## Lab — hand-calculable check
```
# From the bank [E]: confirm the multipliers yourself
n=8; M=100e6
print(2*(n-1)/n*M)   # ring AllReduce traffic/rank -> 175.0e6 B
print((n-1)/n*M)     # AllGather traffic/rank      -> 87.5e6 B
print(2*(n-1)/n)     # busbw multiplication factor -> 1.75
```
Then run `nccl-tests all_reduce_perf -b 100M -e 100M -g 8 -N 1` on a rail; *expect* algbw
≈ 28 GB/s and **busbw ≈ 49–50 GB/s** near the bank's `busbw = algbw×1.75` line at healthy
topology [A/E].

> **Where this fits.** The AllToAll-heavy forms (MoE, context) get their own page:
> [./34-moe-all-to-all.md](./34-moe-all-to-all.md). How these patterns play out in training
> vs inference: [./35-training-vs-inference.md](./35-training-vs-inference.md). Software
> that executes them: [../GPU-Communication/04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md)
> and [./36-communication-libraries.md](./36-communication-libraries.md).

## Key Takeaways
1. Seven primitives — Broadcast, Reduce, AllReduce, AllGather, ReduceScatter, AllToAll, Point-to-Point; AllReduce = ReduceScatter + AllGather composed; **AllToAll is the one pure permutation with no reduction saving**. [E]
2. Wire-traffic multipliers [E]: ring AllReduce `2(n-1)/n × M`, AllGather/ReduceScatter `(n-1)/n × M`, AllToAll `M`/rank; **busbw = algbw × 2(n-1)/n** (×1.75 at n=8). [F]
3. Ring AllReduce = ReduceScatter + AllGather phases keeping every ring link busy → near-full bus bandwidth, at the information-theoretic minimum for large messages; NCCL's double binary tree adds O(log n) latency without the bandwidth penalty. [F]
4. Parallelism→collective map: DP = AllReduce (bandwidth-bound), TP = small frequent AllReduces (latency-bound), EP/context = AllToAll (fabric/incast) — one fabric must serve all three. [F/I]
5. Collectives are **synchronized, elephant, and identical**: the slowest rank gates every step, so **tail latency, not mean, decides JCT**; diagnose with nccl-tests busbw vs `0.95 × link`. [I]

## Related
- [34-moe-all-to-all.md](./34-moe-all-to-all.md) — the AllToAll-heavy form that stresses the fabric hardest.
- [35-training-vs-inference.md](./35-training-vs-inference.md) — how these patterns differ across training vs serving regimes.
- [36-communication-libraries.md](./36-communication-libraries.md) — the software (NCCL/MPI/UCC) that executes these primitives.
- [32-uetch-congestion-and-in-network.md](./32-uetch-congestion-and-in-network.md) — UET's CC and INC built for these synchronized patterns.
- [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md) — NCCL internals behind ring/tree/NVLS.
- [55-cheat-sheet.md](./55-cheat-sheet.md) — quick reference across the section.

## References
- mlsysbook vol 2 — collective primitives, ring and tree analysis [F].
- nccl-tests PERFORMANCE.md — busbw/algbw definitions and the wire-traffic multipliers [F].
- NVIDIA NCCL docs — algorithm modeling (ring/tree/NVLS), NCCL_TREE_THRESHOLD removal in 2.5 [F].
- NCCL issue #807 — NVLS offload of reduction into the NVSwitch [F].
- arXiv:2507.04786 — NCCL algorithm analysis [I].
- [E] AFN constants bank — ring AllReduce/AllGather multipliers and worked n=8 examples.
