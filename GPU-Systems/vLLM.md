# vLLM Architecture — Paged KV, Scheduling, and the Life of a Request
`LAST_UPDATED: 2026-08-21 · Status: core page` · PART XV of the GPU-Systems handbook; the deep
dive that extends `./Inference-Engines.md` and pairs with `../Serving-Engines/vLLM.md` (engine fit).
Architecture claims [F] from vLLM docs/README (github.com/vllm-project/vllm, docs.vllm.ai) and
the SOSP'23 paper (arXiv:2309.06180). No version numbers asserted — check current vLLM docs.
Performance statements are hypotheses [I]; verify via `Labs/Lab-8`.

## 30-Second Explanation
vLLM's core bet: **manage the KV cache like virtual memory**. KV lives in a fixed pool of
uniform blocks (default 16 tokens/block [F: vLLM docs]); each request owns a *block table*
mapping logical positions to physical blocks, and the attention kernel indexes KV through that
table (PagedAttention, arXiv:2309.06180). This kills the two classic wastes of contiguous
per-request KV allocation — pre-allocation to `max_tokens` and fragmentation — so HBM runs at
~100% effective capacity. On top, a **Python scheduler does iteration-level continuous
batching**: each decode step refills finished slots, co-schedules prefill chunks with decodes,
reuses shared prefixes from a hash cache, and preempts when blocks run out. The rest is kernel
plumbing: pluggable attention backends, CUDA-Graph-captured decode, TP/PP/DP/EP, Prometheus.
Strength: breadth (models/quant/kernels) + day-0 support; whether the Python event loop holds
at very high batch is an open hypothesis, not a fact [I].

## Why vLLM Exists: The KV Memory Problem
Naive serving allocates, per request, a **contiguous** KV region sized to the *maximum possible*
sequence length (the sequence grows token by token; the kernel expects contiguous K/V). Two costs,
both [E] Python-verified below:

- **Wasted pre-allocation (internal waste).** A request whose actual output is 100 tokens still
  occupies its `max_tokens` region. 3 requests with actual lengths 100/200/300 against a 300
  cap reserve 900 slots, use 600 → **33.3% of the reserved KV is dead** [E].
- **Fragmentation (external waste).** As requests finish, free slots are scattered. A new
  500-token request can be stuck even though 500 free slots exist in total, because none are
  contiguous. Contiguous allocation turns KV into a classic free-list with external
  fragmentation — the same problem virtual memory solved 40 years ago [A: analogy].

PagedAttention is that solution ported to KV: uniform blocks, per-request block tables,
kernel-side indirection — any free block serves any request, so external fragmentation is zero by
construction and capacity math is trivial.

## PagedAttention
### What
KV is stored in **fixed-size blocks** (vLLM default 16 tokens [F: vLLM docs]). Each request keeps
a **block table**: logical block index → physical block ID. The attention kernel receives the
block table and gathers K/V block by block instead of assuming one contiguous tensor per request.
Full design: Kwon et al., "Efficient Memory Management for LLM Serving with PagedAttention",
SOSP'23, arXiv:2309.06180 [F]. Block layout / capacity equation: `../KV-Cache/README.md`;
the kernel-side view (paged layout changes attention IO): `../Attention/README.md`.

```
   GPU HBM: block pool (uniform, e.g. 16 tokens x h_kv x d_h x 2 x L)
   +----------------------------------------------------------+
   | [B0] [B1] [B2] [B3] [B4] [B5] [B6] [B7] [B8] ... [Bn]    |  <- physical blocks
   +----------------------------------------------------------+
   Request A (table):  0->B3, 1->B7, 2->B1        (47 tokens: B1 partial)
   Request B (table):  0->B3, 1->B5, 2->B2        (shares B3 with A: shared prefix)
   Request C (table):  0->B3                      (shares B3; refcount(B3)=3)

   attention kernel(Q, K, V, block_tables)  <- no contiguous K/V tensor exists
```
(Sketch: shared prefix blocks carry refcounts > 1; a block is reusable only at refcount 0.)

### Why
Three capabilities fall out of one mechanism:
1. **Near-zero fragmentation** — uniform blocks mean every free block is a valid allocation.
2. **Shared prefixes** — two requests whose tokens 0–15 are identical can point at the *same*
   physical block; no copy.
3. **Cheap preemption** — dropping a request means dropping its block-table entries; the blocks
   return to the pool (or swap to CPU) without moving anything else.

### How
At startup vLLM measures free GPU memory after loading weights (capped by
`--gpu-memory-utilization`) and divides it into the block pool; the allocator keeps a free list
of block IDs. Each step: new K/V rows are written into the request's current block; on block
fill the table extends with a freshly allocated ID. The attention kernel (any paged-KV-capable
backend [F: vLLM docs]) gathers K/V via the table, so model code never sees a per-request K/V
tensor — only the table plus a per-block buffer.

### When
Always — paged KV is vLLM's default and its defining feature. Block size is a tunable knob
(default 16 [F: vLLM docs]): smaller blocks → finer prefix sharing, more table overhead;
larger → less overhead, more tail waste.

### Hardware impact
The kernel pays index work (per-block address computation, gather of non-contiguous K/V) —
the price of the win. The payoff is HBM-level: effective KV capacity approaches 100% of the
reserved pool, so the whole decode batch can live in HBM; and the uniform layout is what makes
CUDA-Graph capture and paged-kernel backends tractable [I].

### Inference impact
More sequences fit concurrently → the continuous batch runs at a bigger B → decode GEMMs stay
near the roofline knee (`../Inference/Continuous-Batching.md`, `../Inference/Roofline.md`).
Layout itself does not change ITL; it raises the **capacity ceiling** everything else runs under.

### Example [E]
L=32, h_kv=8, d_h=128, BF16 (b=2): KV per token = 2·32·8·128·2 = **131,072 B = 128 KiB**
(Python-verified). One 16-token block = 128 KiB × 16 = **2 MiB**. A 64 GiB KV pool holds
64·GiB ÷ 2 MiB = **32,768 blocks** = 524,288 token slots → ~524 tokens/sequence average for
1,000 concurrent sequences. This is the sizing arithmetic: pool size ÷ block bytes = capacity.

### Failure modes
- **Tail waste:** a sequence of 256 tokens on 16-token blocks can waste up to 15 tokens
  (15/256 ≈ **5.9%** [E] worst-case tail for that length); average is less.
- **Table-overhead at extreme context:** very long sequences need long tables; gather overhead
  grows [I].
- **Pool exhaustion:** blocks run out → preemption (below), which is where P99 is born.

### How to measure it
`gpu_cache_utilization` (fraction of blocks in use), block allocation/eviction counters,
preemption counts, and effective tokens/sequence at steady state (`## Observability`).

## Continuous Batching
### What
**Iteration-level scheduling** [F: Orca, OSDI'22, arXiv:2211.05102]: the batch is not
a fixed set of requests — it is rebuilt *every decode step*. A request that hit EOS frees its
slot; a waiting prompt is admitted in the same step. Deep treatment:
`../Inference/Continuous-Batching.md`.

### Why
Static batching leaves slots dead while the shortest request in the batch waits for the longest.
With iteration-level scheduling every slot is refilled the moment it frees, and decode GEMVs
accumulate into GEMMs at batch B, amortizing the per-step weight stream.

### How
Each iteration the Python scheduler (async event loop [F]) does: (1) complete requests that hit
EOS/`max_tokens` and return their blocks; (2) admit waiting requests while blocks and the
`max-num-seqs` cap allow; (3) schedule this step's prefill (whole or chunk) + all running
decodes; (4) emit batch metadata — token IDs, positions, block-table slices — to the model
runner. No request moves inside a step; everything that changes happens *between* steps.

### When
Default mode. The scheduler is CPU-side Python; at very high B the host loop can become the
bottleneck before the GPU — the open H4 hypothesis in `../Serving-Engines/README.md`
(Python event loop at B≥128? unverified; test it) [I].

### Hardware impact
A batch that is (nearly) always full of live decode work is what keeps decode GEMMs at
M = B ≈ B* (the roofline knee). When the batch is mixed — prefill chunk + decodes — the step has
two different GEMM shapes, and kernel choice (one kernel for the mixed step vs split) matters [I].

### Example [E]
Static batch of 4 requests with outputs of 1/10/20/30 tokens: total slot-steps = 4 × 30 = 120;
busy slot-steps = 1+10+20+30 = 61 → **50.8% slot utilization** [E]. With continuous batching and
a non-empty waiting queue, freed slots are refilled next step → utilization approaches 100%
of live steps [I: idealized, queue-never-empty].

### Inference impact
The single biggest serving win for throughput [I: consistent across engines]. Tail latency is
then governed by preemption and KV contention, not batch structure.

### Failure modes
- CPU scheduler overhead at extreme B (see `When`).
- **Preemption storms:** sustained pool exhaustion → repeated evict/recompute cycles → P99 spikes.
- KV contention: one huge prefill starves decodes unless chunked (below).

### How to measure it
`num_requests_running` vs `num_requests_waiting`, batch-size distribution, ITL/TPOT percentiles,
and GPU idle gaps between kernel launches (Nsight Systems — `Profiling.md`).

## Scheduling Details
The per-step decision the scheduler makes for every request: **admit? batch? chunk? prefix hit?**

- **Admission:** a waiting request is admitted when (a) its non-shared prefix fits in free blocks
  and (b) `num running < max-num-seqs`. `--max-num-seqs` caps concurrent sequences — the direct
  knob on batch size and on per-request CPU metadata work [F: vLLM docs].
- **Token cap:** `--max-num-batched-tokens` caps the total tokens scheduled in one step
  (prefill tokens + decode tokens). This is the chunked-prefill chunk-size controller and the
  throttle that keeps a long prefill from monopolizing a step [F: vLLM docs].
- **Prefill placement:** a request's prompt runs first (or in chunks), writing K/V into its
  freshly allocated (or prefix-shared) blocks; only then does its decode stream start.
- **Preemption:** when the pool cannot serve the next step, running requests are preempted.
  Two flavors [F: vLLM docs]:
  - **Recompute:** drop the preempted request's blocks entirely; it re-prefills on resumption.
    Cost = wasted prefill FLOPs; no memory traffic.
  - **Swap:** copy the request's K/V to CPU host memory, free the blocks, reload later.
    Cost = PCIe round-trip. [E] 1,024-token prefix = 128 MiB KV; at PCIe 5.0 x16 ≈ 64 GB/s that
    is 134 MB / 64 GB/s ≈ **2.1 ms each way** (Python-verified) — small for a 1k-token request,
    larger for 32k.
  vLLM prefers recompute for short, cheap-to-recompute state and swap when recompute would be
  expensive [F: vLLM docs]. The waiting queue is priority-ordered; priorities affect
  preemption order — a low-priority victim is preempted first [F: vLLM docs].

## Prefix Caching (APC)
### What
Hash-based **automatic prefix caching**: each physical block is keyed by a hash of its tokens
plus the hash of the preceding block (a hash chain). New requests walk the chain looking up the
longest prefix whose blocks are still in the pool; those blocks are **shared via refcounts**, not
copied, and the request's prefill starts after the matched prefix [F: SOSP'23, arXiv:2309.06180;
vLLM docs]. Enable with `--enable-prefix-caching` [F: vLLM docs]. Contrast with SGLang's
structural RadixAttention: `./SGLang.md`.

### Why
Repeated system prompts, few-shot examples, and agent histories are the dominant real-world
prompt shape. Re-prefilling them per request wastes the most expensive compute in the system
(prefill is the compute-roof region) and inflates TTFT.

### How
During prefill, every completed block is inserted into the hash table (block hash → physical
blocks). On eviction (refcount 0, LRU order [F: vLLM docs]) the entry is dropped. A **warm**
prefix = matched blocks resident in the GPU pool; **cold** = evicted or never cached → full
re-prefill. Requests that share a warm prefix allocate *zero* blocks for the shared part.

### When
Any workload with repeated prefixes — chat systems with fixed system prompts, agentic loops,
RAG templates. The hit rate is workload-dependent; measure it, don't assume it [I].

### Hardware impact
Shared blocks remove prefill GEMM work for the shared span (compute saved, not just memory) and
cut HBM traffic. The bookkeeping (hashing, refcounts) is CPU-side per-block work — negligible
for typical block counts, worth knowing at very high QPS [A].

### Inference impact
TTFT drops proportionally to the hit rate. [E] Worked case: 50 requests sharing a 1,024-token
prefix (L=32, h_kv=8, d_h=128, BF16): prefill work falls from 50×1,024 = **51,200 tokens to
1,024 (50×)** [E], and the shared footprint is 64 blocks × 2 MiB = **128 MiB** instead of
50 × 128 MiB = **6.25 GiB** [E] (Python-verified).

### Failure modes
- **Low hit rate:** highly diverse prompts → hashing overhead with no savings; disable it.
- **Eviction churn:** pool pressure evicts hot prefixes just before the next request needs them;
  watch the hit-rate curve over time, not a snapshot [I].
- **Routing miss (multi-replica):** the prefix lives on replica A but the request lands on B →
  cold start. Fix = KV-aware routing (`./Load-Balancing.md`).

### How to measure it
Prefix-cache query/hit counters → hit rate; split TTFT by warm/cold; evictions per minute.

## Chunked Prefill
A long prompt scheduled as one step stalls every decode in the batch for that one big kernel
(prefill is compute-bound, decode is latency-sensitive). Chunked prefill splits the prompt into
chunks of ≤ `max-num-batched-tokens` and **co-schedules each chunk with the running decodes**
[F: vLLM docs, `--enable-chunked-prefill`]:

```
step t:   [decode A] [decode B] [decode C] [prefill-chunk-1 (256 toks)]
step t+1: [decode A] [decode B] [decode C] [decode D (new)] [prefill-chunk-2]
...
```
Each decode step stays small (steady ITL); the long prompt pays its prefill in slices, amortizing
TTFT. Cost: mixed steps carry two GEMM shapes in one kernel call, so kernels must be
shape-flexible — one reason backends are pluggable [I]. Sarathi-style motivation: arXiv:2308.16369,
arXiv:2403.02310 [F].

## Speculative Decoding
vLLM ships draft-then-verify with pluggable drafters [F: vLLM docs]: **n-gram** (draft from the
request's own context — free), **suffix** (cache-based draft), **EAGLE** (feature-level draft
head on top of the target model, arXiv:2401.15077 [F]), and **DFlash** (draft-flash variants,
check current docs). The target model verifies the whole draft in one forward pass; accepted
tokens advance, the first rejection resamples. Mechanism and acceptance-rate analysis:
`../Speculative-Decoding/README.md`. ITL improvement is acceptance-rate dependent [I] — at low
acceptance the extra draft FLOPs can net to zero; at B=1 with good acceptance it is a real ITL
lever. Observability: draft/accepted-token counters (`## Observability`).

## Distributed Inference
Parallelism dimensions and where they pay [F: vLLM docs; deep dives `./Multi-GPU.md`,
`./Tensor-Parallelism.md`, `./Pipeline-Parallelism.md`, `./MoE-Expert-Parallelism.md`]:

| Dim | What moves | Fabric | Cost per step | Typical use |
|---|---|---|---|---|
| **TP** | split each layer's GEMMs across GPUs; 2× AllReduce/layer [I] | NVLink (intra-node) | 2 AllReduce/layer | model > 1 GPU, low ITL |
| **PP** | split layers into stages | RDMA (cross-node OK) | stage P2P; bubbles at low B | very large models, high B |
| **DP** | whole-model replicas + router | any | router overhead | throughput, load spread |
| **EP** | MoE experts sharded; AllToAll dispatch/combine | fast RDMA / NVL72 | AllToAll per expert layer | MoE models only |

DP + prefix awareness is where **KV-aware routing** enters: a router that steers a request to
the replica whose APC already holds the request's prefix turns a cold start into a warm one —
"balance remaining work, not requests" (`./Load-Balancing.md`).

**Disaggregated P/D.** vLLM supports "disaggregated prefill, decode, and encode" serving:
prefill GPUs run prompts, decode GPUs run the stream, and finished KV is transferred between
them over shared memory, NIXL, or RDMA [F: vLLM docs; `../Serving-Engines/vLLM.md`]. This
isolates the two bottleneck regimes (compute-roof vs memory-roof) and removes prefill
interference from decode ITL at the cost of KV transfer. [E] 1,024-token prompt = 128 MiB KV
(Python-verified above): at IB NDR ≈ 50 GB/s that is 128 MB / 50 GB/s ≈ **2.7 ms** transfer
alone — cheap vs the prefill it protects; at 32k context the KV is ~4 GiB → ≈ **86 ms** at the
same link, and the transfer starts to matter. Architecture and failure modes:
`./Prefill-Decode-Disaggregation.md`, `../Inference/Prefill-Decode-Disaggregation.md`.

## CUDA Graphs and the Kernel Ecosystem
Decode at small-to-mid B is launch-bound: hundreds of small kernels per step, each a CPU→GPU
launch (`Kernel-Life.md`). vLLM **captures the decode step as a CUDA Graph** and replays the
whole launch sequence in one call, killing the per-kernel launch overhead [I: mechanism;
V1 does piecewise graph capture, and graph-hit fraction varies at odd batch sizes — always
annotate graph-hit fraction when benchmarking, per `../Serving-Engines/vLLM.md`].

The attention/GEMM layer is a **pluggable kernel ecosystem**, runtime-selected per model and
hardware [F: vLLM docs]:
- **Attention backends:** FlashAttention, **FlashInfer** (arXiv:2501.01005 [F]),
  TRTLLM-GEN, FlashMLA, Triton — all paged-KV-capable. This is why PagedAttention is a
  *layout contract*, not a kernel: any kernel that honors the block table works.
- **GEMM/MoE:** CUTLASS, TRTLLM-GEN, CuTeDSL, FusedMoE kernels [F: vLLM docs].
- **Quant:** FP8, NVFP4/MXFP4, INT8/INT4, GPTQ, AWQ, GGUF, compressed-tensors, ModelOpt
  [F: vLLM docs] — the widest quant coverage of the big three
  (`../Serving-Engines/README.md`).

Practical rule: pin the backend in any benchmark (a kernel-swap is as big a variable as a
model-swap); re-check backend selection after upgrades — defaults move [A].

## Trace: One Request Through vLLM
```
HTTP POST /v1/chat/completions
  |
  v
(1) API server        : tokenize prompt -> token IDs (CPU); build request state
  v
(2) Scheduler/step    : admit? blocks free? prefix hit? chunk size?
  |    APC lookup: hash the 16-token prefix blocks, walk the hash chain
  |    -> warm: N blocks shared (refcount up), prefill starts after token 16N
  |    -> cold: allocate fresh blocks from the free list
  v
(3) Batch builder     : assemble this step: token IDs + positions + block-table slices
  |                      (metadata on CPU; small — this is the per-request CPU cost)
  v
(4) Model runner      : L layers, each: RMSNorm -> QKV GEMM -> RoPE ->
  |                      attention (FlashInfer/FA, paged KV via block table) ->
  |                      O GEMM -> RMSNorm -> MLP GEMM (SwiGLU) -> residual
  |    prefill step: GEMMs at M=chunk_len, FA over the chunk (+ shared prefix)
  |    decode step:  GEMVs at M=B (CUDA-Graph replay)
  v
(5) KV update         : new K/V rows appended in-place into the request's current block
  |                      (no tensor reallocation; on block fill -> allocate next, extend table)
  v
(6) Logits + sample   : final LM-head GEMM -> top-p/top-k sampling -> 1 new token
  v
(7) Detokenize/stream : token -> text chunk -> SSE to client
  v
(8) Next step         : repeat (3)-(7) for the next decode step ...
                        until EOS / max_tokens; then free blocks (refcount--); request leaves
```
Data movement, step by step: the prompt crosses the wire once (step 1); each step the GPU streams
**weights** (decode: the whole model, memory-bound) + **KV** (paged gather, O(S) reads) + a few
activation tensors. The only steady-state host↔device traffic is batch metadata (step 3) and the
sampled token (step 7) — everything else stays in HBM. Swap-preemption is the exception: KV moves
across PCIe (`## Scheduling Details`).

## Observability
Prometheus (V1 metric set [F: vLLM docs; exact names — check current docs]):

| Metric | What it tells you |
|---|---|
| `gpu_cache_utilization` | fraction of KV blocks in use. Approaching 1.0 → capacity wall: expect queueing/preemptions next; add HBM, KV-quant, or shrink context |
| `num_requests_waiting` | admission-queue depth. Sustained > 0 → throughput ceiling reached; scale out (DP) or raise KV capacity |
| `num_requests_running` | live sequences. Compare against `max-num-seqs`: much lower → KV-limited, not config-limited |
| TTFT histogram (time-to-first-token) | queueing + prefill cost. Spikes on long prompts, cold prefixes, or preemption of in-prefill requests |
| ITL / TPOT histogram (time-per-output-token) | decode-step latency. Spikes → chunked-prefill co-scheduling, preemption, CPU scheduler overhead, or CUDA-Graph miss |
| prefix-cache query/hit counters | APC hit rate. High queries + low hits → shared-prefix workload missing its cache (wrong replica, eviction churn) |
| spec-decode draft/accepted tokens | acceptance rate. Low → drafter mismatch; disable or switch drafter |
| preemption / eviction counters (recompute vs swap split) | KV pressure signature. Recompute-dominant → short lifetimes, cheap; swap-dominant → long KV, PCIe-bound rescues |

Read together: high `gpu_cache_utilization` + growing `num_requests_waiting` + rising TTFT =
KV-limited cluster; low utilization + high waiting = scheduler/admission problem, not memory
(`Diagnostics.md`).

## Key Takeaways
1. PagedAttention = virtual memory for KV: uniform blocks + per-request block tables +
   kernel-side indirection → ~zero external fragmentation and trivial capacity math
   (pool bytes ÷ block bytes = token slots).
2. Continuous batching is iteration-level: the batch is rebuilt every step; admission,
   prefill chunking, and preemption are scheduler decisions made per step.
3. Prefix caching makes shared prefixes *physically shared* (refcounted blocks, not copies) —
   it saves prefill FLOPs and HBM at once; its value is hit-rate dependent.
4. The engine is a layout contract (paged KV) + a pluggable kernel ecosystem
   (FlashInfer/FA/Triton) + CUDA-Graph replay; pin all three when benchmarking.
5. No universal fastest engine: vLLM's edge is breadth and day-0 support; whether the Python
   event loop holds at B≥128 and whether its P/D transfer cost wins at long context are
   hypotheses to test on your hardware (`./Engine-Comparison.md`, `Labs/Lab-8`) [I].

## Related
`../Serving-Engines/vLLM.md` (engine fit) · `./Inference-Engines.md` (why engines exist) ·
`../KV-Cache/README.md` (KV budget equation) · `../Inference/Continuous-Batching.md` ·
`../Attention/README.md` (paged layout) · `./SGLang.md` (RadixAttention contrast) ·
`./Engine-Comparison.md` · `../Speculative-Decoding/README.md` · `./Multi-GPU.md` ·
`./Load-Balancing.md` (KV-aware routing) · `./Prefill-Decode-Disaggregation.md` ·
`./Kernel-Life.md` (CUDA Graphs) · `Diagnostics.md`.

## References
- Kwon et al., "Efficient Memory Management for Large Language Model Serving with PagedAttention", SOSP'23, arXiv:2309.06180 [F].
- Orca, "Efficiently Scaling Transformer Inference" (iteration-level scheduling), OSDI'22,
  arXiv:2211.05102 [F].
- vLLM project docs & README: github.com/vllm-project/vllm, docs.vllm.ai [F] (scheduler knobs,
  APC, chunked prefill, backends, Prometheus V1, disaggregated P/D — check current docs for
  availability of individual features). EAGLE arXiv:2401.15077 [F]; FlashInfer arXiv:2501.01005
  [F]; Sarathi arXiv:2308.16369, Sarathi-Serve arXiv:2403.02310 [F].
