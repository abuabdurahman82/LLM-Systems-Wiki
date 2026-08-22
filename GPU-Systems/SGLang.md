# SGLang Architecture — Program-Aware, Zero-Overhead Runtime
`LAST_UPDATED: 2026-08-21 · Status: core page` · PART XVI of the GPU-systems handbook.
Primary source: SGLang/RadixAttention paper (arXiv:2312.07104) [F]; repo
github.com/sgl-project/sglang [F: SGLang docs]; FlashInfer (arXiv:2501.01005) [F].
Vendor claims are tagged and never presented as independent results.

## 30-Second Explanation
SGLang (LMSYS) bets that **the application's program structure is a first-class input to
the serving system**. Where vLLM sees *requests* (tokens in, tokens out), SGLang's
frontend DSL sees *programs*: multi-turn agent loops, shared system prompts, tool-call
DAGs, grammar-constrained outputs. That program awareness pays off in two structural
ways: (1) **RadixAttention** — a radix tree over token prefixes so any request sharing a
prefix automatically shares the same physical KV blocks, no hashing/discovery step;
(2) a CPU-side **batch scheduler designed with near-zero per-iteration overhead** (the
vendor's "zero-overhead" term [F: SGLang]), so the GPU step pipeline is not starved
waiting on host-side scheduling. Together these target exactly the workload class
dominant in 2025+: agentic, structured-output, high-concurrency, shared-prefix traffic.
This page is the GPU-systems view: what the runtime does to the scheduler, the KV cache,
the kernels (FlashInfer), and the multi-GPU/multi-node execution path. The engine-level
page is `../Serving-Engines/SGLang.md`; the fairness-framed comparison with vLLM is
`./Engine-Comparison.md`.

## Architecture at a glance
```
                ┌──────────────────────────────────────────────────────────┐
 HTTP/OpenAI    │  SGLang frontend (Python)                                │
 request ──────►│  DSL · program structuring · structured-output grammar   │
                │        │  (the program, not just tokens, is visible)     │
                │        ▼                                                │
                │  Batch scheduler ("zero-overhead" design goal)          │
                │   · continuous batching  · chunked prefill co-scheduled │
                │   · RadixAttention prefix-cache lookups                 │
                │        │                                               │
                │        ▼                                               │
                │  RadixAttention KV manager                             │
                │   radix tree: shared prefixes → shared paged blocks    │
                │   (64-token blocks default [F: docs])                  │
                │        │                                               │
                │        ▼                                               │
                │  Model runner: FlashInfer attention (paged KV,         │
                │  ragged batching) + CUTLASS/Triton GEMM · MoE · quant  │
                │        │                                               │
                │        ▼                                               │
                │  Sampling / compressed-FSM constrained decode → stream │
                └──────────────────────────────────────────────────────────┘
   Multi-GPU: TP intra-node (NVLink) · EP for MoE · multi-node via NCCL
```
The scheduler, the radix KV tree, and the model runner are **co-designed**: the tree
tells the scheduler what prefix work is free, and the scheduler keeps the GPU busy
while the tree grows. That coupling is the actual differentiator — no single kernel.

## The zero-overhead runtime
### What
The **zero-overhead batch scheduler** [F: SGLang] is the CPU-side runtime's core design
claim: per-iteration scheduling cost (admission, batch assembly, cache lookups, token
bookkeeping) is engineered to be small relative to one GPU model step, so decode is
never *launch-bound on the CPU* — the GPU keeps stepping while the host prepares the
next batch. Note the precise shape of the claim: it is a **vendor design goal**
[ F: SGLang ], not a language property and not a measured universal — the scheduler
is Python, and whether overhead stays negligible depends on batch size, concurrency,
and host CPU.

### Why
In decode, one step of a small model on strong hardware can complete in ~1–3 ms of
GPU time [A]. If the host scheduler needs 2 ms of CPU time between steps, the GPU sits
idle ~half the time and every token's inter-token latency (ITL) inflates by that idle
gap. At high concurrency the host work per step grows (more requests, more cache
lookups, more sampling/detokenization), so the CPU side is a *scaling* problem, not a
one-time constant. A runtime that treats host time as first-order keeps ITL flat as
concurrency rises — which is exactly where shared-prefix agentic traffic lives.

### How
Mechanisms the runtime uses to keep per-iteration host time low [F: SGLang; repo
docs for details] [A on exact implementation]:
- **Iteration-level, not request-level, scheduling**: one scheduling decision per
  model step; no per-token Python round-trips through the GIL.
- **Prefix lookups as tree operations**: the radix tree returns the matched-prefix
  length in O(tokens-in-prefix) pointer walks, not per-request hash/rehash.
- **CUDA Graphs for the decode path** where shapes are stable, removing kernel-launch
  overhead on the GPU side (`Kernel-Life.md`, `./Multi-GPU.md`).
- **Async tokenization/sampling off the critical path** [A] so host bookkeeping does
  not serialize the GPU step.

### When
Matters most at: high concurrency (many in-flight decodes), small/medium models on
fast GPUs (short GPU step → host time is a larger fraction), and long-running agent
sessions where per-token overhead compounds over hundreds of steps. Matters less at
B=1 on a slow model where the GPU step dwarfs any host cost.

### Hardware impact
None directly — this is a host-software property. Its value *to the GPU* is removing
idle gaps: a CPU-bound gap is the classic "GPU util oscillates, kernels are long
enough, but there are holes between them" profile (`Diagnostics.md`).

### Inference impact
- **ITL/TPOT**: directly protected from host-side stalls; flat ITL vs concurrency is
  the signature of a scheduler keeping up.
- **Throughput**: at high concurrency the difference between "scheduler keeps up" and
  "scheduler queues" shows up as total tok/s and P99.
- **TTFT**: indirectly — the same runtime also drives chunked-prefill pacing.

### Example [E]
Arithmetic (Python-verified): let T_gpu = 2 ms per decode step, T_sched = host time
per step. GPU idle fraction ≈ T_sched / (T_gpu + T_sched):
- T_sched = 0.2 ms → idle ≈ 0.2/2.2 = **9.1%** → ITL ≈ 2.2 ms
- T_sched = 2.0 ms → idle ≈ 2/4 = **50%** → ITL ≈ 4.0 ms (doubled!)
A scheduler that stays under ~0.3–0.5 ms/step at B=128 therefore holds ITL within
~15–25% of the pure-GPU step time. The *claim* is that SGLang's design keeps it there;
verify per-deployment (open question H4 in `../Serving-Engines/SGLang.md`).

### Failure modes
- **High-concurrency Python overhead**: thousands of in-flight requests, streaming
  detokenization, and cache-bookkeeping can push per-step host time up; "zero-overhead"
  becomes "small but not zero." Measure host time per iteration, don't assume.
- **CPU-limited host**: shared/vCPU-throttled hosts defeat any scheduler design.
- **Long-tail scheduling decisions** (cache-eviction storms, huge batch assembly) can
  create occasional multi-ms spikes even with a low *average* host time.

### How to measure it
- Per-iteration scheduler time (engine trace/logs) vs GPU step time; plot ITL vs
  concurrency and look for the elbow where ITL starts climbing.
- GPU timeline (Nsight Systems / DCGM): fraction of wall time with no kernel running.
- Compare against a baseline engine on the *same pinned config*
  (`Perf-Experiment-Template.md`, `./Engine-Comparison.md`).

## RadixAttention
### What
**RadixAttention** [F: arXiv:2312.07104] organizes the paged KV cache as a **radix
(tree) over token prefixes**: each node is a token string, and nodes that are literal
prefixes of one another share a single chain of physical KV blocks. Two requests with
the same 1536-token system prompt + agent history point at the *same 16×64-token
blocks* [E, below] — sharing is **defined structurally by the program** (the frontend
knows which requests share a prompt), not discovered by hashing token chunks.

### Why
The KV cache is the dominant HBM consumer at long context/high concurrency
(`../KV-Cache/README.md`, memory equation `2·L·B·h_kv·d_h·S·b`). In agentic workloads
the *system prompt and conversation history are the majority of every request's tokens*,
so re-prefilling or re-storing that prefix per request is pure waste: wasted prefill
FLOPs (TTFT) and wasted HBM (capacity). A data structure that makes shared prefixes
share *physically* — one allocation, N readers — is worth more at high concurrency than
most kernel-level tweaks.

### How
- Blocks are paged (default 64 tokens [F: SGLang docs]), allocated from a pool, exactly
  as in PagedAttention (`../Attention/README.md` for the paging lineage,
  arXiv:2309.06180).
- The radix tree indexes the pool: internal nodes hold token strings + block pointers;
  leaf nodes are per-request tails. Insert = walk/extend the chain; lookup = longest
  common prefix walk; eviction = LRU over tree structure (evict whole subtrees that
  are cold).
- Because the frontend (DSL) declares program structure, the engine knows in advance
  which requests share which prefixes — the tree is maintained *by construction*.
  **Contrast with vLLM's hash-based APC**: vLLM hashes prefix chunks to a block list
  and refcount-shares blocks that hash-collide on a prefix — sharing is *discovered*
  by the engine at cache time, no program knowledge required [F: vLLM docs,
  `./vLLM.md`]. Both end in shared paged blocks; they differ in *who decides sharing*
  (program-declared vs hash-matched) and in eviction structure (tree vs hash table).
- **Ragged batching** (attention over sequences of different lengths in one batch) is
  what makes this efficient on the kernel side — FlashInfer's core capability
  [F: arXiv:2501.01005].

### When
Every workload with repeated prefixes: shared system prompts, RAG with common
retrieval boilerplate, multi-turn agent sessions, batch jobs over one template.
Weakest when every request's prefix is unique (no sharing exists to exploit)
[I] — then the tree's overhead is paid for with nothing in return.

### Hardware impact
Sharing reduces **HBM capacity pressure** (one allocation instead of N) and **HBM
traffic** (the shared K/V rows are read once into cache and reused rather than
re-materialized per request). Attention itself is unchanged — the kernel reads the
same paged blocks via per-request block tables.

### Inference impact
- **TTFT**: a cache hit turns "prefill all S tokens" into "prefill only the Δ tokens"
  — prefill FLOPs drop proportionally to hit rate.
- **Capacity**: fewer KV bytes in flight → more concurrent sequences before eviction.
- **ITL**: little direct effect (decode reads the same blocks); benefit is indirect via
  reduced eviction churn.

### Example [E]
Python-verified numbers. Model: L=32 layers, h_kv=8, d_h=128, BF16 KV (b=2).
KV per token = 2·L·h_kv·d_h·b = 2·32·8·128·2 = **131,072 B = 128 KiB/token**
(same equation as `../KV-Cache/README.md`).
Workload: 1000 requests; each = 1024-token system prompt + 512 shared agent-history
turns + 128 unique tokens; SGLang default 64-token blocks [F: SGLang docs].
- Shared prefix = 1536 tokens → 1536·128 KiB = **192 MiB resident once**.
  1024-token system prompt = **16 blocks** of 64 tokens.
- Without sharing: 1000·(1664 tokens)·128 KiB = 215,040 MiB ≈ **203.125 GiB**.
- With sharing: 192 MiB + 1000·(128·128 KiB) = 192 MiB + 16,000 MiB ≈ **15.8125 GiB**.
- Ratio: 203.125 / 15.8125 = **12.8× less KV HBM**, and per-request prefill drops from
  1664 to 128 tokens = **13× less prefill compute** on a full hit.
These are the two levers — capacity and prefill work. The vendor-reported 5×-class
shared-prefix speedup (wall-clock, `../KV-Cache/README.md` cites the blog) is
[F: SGLang blog] — a **vendor claim**, and wall-clock gains depend on hit rate,
concurrency, and model; the 12.8×/13× above are the structural maximums *this
workload* offers, not a benchmark result.

### Failure modes
- **Cache thrash under low overlap**: eviction policy evicts subtrees that *were*
  shared but are now cold; hit rate collapses and you pay tree-maintenance overhead
  for no sharing.
- **One hot, many cold**: one huge shared prefix holds blocks that many requests
  actually don't use, evicting useful cold prefixes (admission policy problem).
- **Fragmented tree**: deep thin trees with many tiny nodes add per-node bookkeeping
  to the scheduler's per-iteration work — the zero-overhead claim depends on this
  staying cheap at scale.

### How to measure it
- `kv_cache_utilization` + **prefix-cache hit rate** (Prometheus) vs workload overlap
  fraction; hit rate should track overlap.
- TTFT distribution: compare P50 TTFT with the cache warm vs cold (`--ignore-each`-
  style cold start in your own harness).
- HBM accounting: measured KV pool occupancy vs the 12.8× theoretical share above.

## Scheduling: program-aware continuous batching
The scheduler runs **continuous batching** (iteration-level, per-token admission —
Orca-lineage [F: arXiv:2211.05102]) and **co-schedules prefill and decode** in the
same step: a batch may contain decode tokens *and* prefill chunks together
(chunked prefill [F: SGLang docs]), so a long prompt's prefill is chopped into chunks
that fit between decode steps instead of stalling everyone. The program-aware twist
[F: paper]: requests from the *same program* are known to the scheduler — siblings of
one agent session share prefixes in the tree, and scheduling decisions (admission
order, chunk budget) can account for that structure [I; the paper motivates it — exact
per-policy behavior is in the repo, check current docs].

## Structured generation
SGLang natively supports **grammar-constrained decoding**: regex, JSON schema, and
grammar/EBNF-style constraints, compiled to a compressed finite-state machine that
masks logits per step [F: SGLang docs/paper]. Two GPU-systems notes:
- The constraint is enforced *in the sampling step* — one extra CPU-side mask lookup
  per token; for agentic workloads this is cheap relative to the step, and it makes
  "parse → re-prompt → retry" loops unnecessary (fewer round-trips through the
  whole pipeline).
- Structured decoding **co-designs with speculative decoding**: the compressor-FSM
  approach lets a draft model propose tokens that are validated against the grammar,
  so constrained output does not forfeit spec-decode gains [F: SGLang blog].
This is a differentiator for tool-calling agents: every response is schema-valid by
construction, and the engine can see the *program* (tool DAG), not just the tokens.

## Speculative decoding
SGLang ships multiple spec-decode paths: **n-gram, EAGLE, STAGE, DFlash, Spec V2**
[F: SGLang docs]. Mechanism ref and the acceptance-rate arithmetic:
`../Speculative-Decoding/README.md` (EAGLE: arXiv:2401.15077). GPU-systems view:
spec decode trades draft FLOPs (compute roof, cheap at small K) for fewer verification
steps on the memory roof — best at **low-to-mid batch** where decode is bandwidth-bound
and the extra tokens-per-step are nearly free; gains shrink as batch grows toward B*
(`../Inference/Continuous-Batching.md`). EAGLE's draft head runs on the target model's
features, so it tracks model updates without retraining a separate draft [F: paper].
Compressed-FSM + spec decode: grammar-constrained generation and speculation compose
rather than compete [F: SGLang blog] — relevant to agentic loops that are *both*
constrained and latency-sensitive.

## Distributed serving: TP, EP, multi-node
- **TP (tensor parallelism):** intra-node, NVLink-class fabric required
  (`./Multi-GPU.md`, `Tensor-Parallelism.md`); 2 AllReduce/layer at small message
  size → fabric latency is the cost.
- **EP (expert parallelism) for MoE:** SGLang documents **large-scale EP demonstrated
  on a 96×H100 DeepSeek-class deployment [F: SGLang blog]** — 96 GPUs = **12 nodes of
  8×H100** [E: 96/8 = 12]. EP turns expert dispatch into an All-to-All over the node
  fabric (`MoE-Expert-Parallelism.md`); at this scale the serving story is as much a
  networking story as a GPU story.
- **Multi-node execution:** cross-node communication over NCCL/RDMA; prefill/decode
  disaggregation is supported, and the program-aware scheduler knows which requests
  belong to the same program, which matters when sibling requests' KV must move
  between P and D pools [I: batching sibling KV transfers is an inference from the
  design, not documented behavior — verify in current docs].
- **Quant coverage:** FP4 (NVFP4-class), FP8, INT4, AWQ, GPTQ [F: SGLang docs].
  Breadth trails vLLM's (GGUF and more quant schemes); for day-0 on a brand-new
  checkpoint, engine choice should track *who supports it first*, not performance
  (`./Engine-Comparison.md`).

## Cache-aware scheduling
The radix tree is not just a cache — it is **scheduling information**. At the
single-engine level the scheduler prefers admitting requests that hit the tree
(their prefill is nearly free). At the multi-replica level, **cache-aware routing**
should send a request to the replica whose prefix tree already holds its prefix,
accepting some load imbalance to buy prefill work away [A]. This is the serving
specialization of "balance remaining work, not requests" (`./Load-Balancing.md`):
routing on *prefix hit + queue depth + KV pressure* beats least-connections for
shared-prefix traffic. Cost: routing that is too sticky to hot caches overloads the
"lucky" replica; the right policy trades cache locality for load balance (the same
trade Mooncake-class systems make for disaggregated KV [F: arXiv:2407.00079]).

## Multi-node execution and the FlashInfer backend
SGLang's primary attention backend is **FlashInfer** [F: arXiv:2501.01005], a
JIT-compiled kernel library built around the two properties paged LLM serving needs:
- **Paged KV**: kernels consume per-request block tables (virtual→physical block
  mapping), so the KV cache can be a pool of fixed-size blocks with arbitrary
  per-request layout — the same paging vLLM's PagedAttention introduced
  [F: arXiv:2309.06180].
- **Ragged / variable-length batching**: one kernel launch handles a batch where each
  sequence has a different prompt length and different decode position — the
  prefill+decode co-batching above is only practical because the kernel accepts
  per-sequence offsets. FlashInfer JIT-compiles per (shape, arch) so the hot kernel
  matches the actual batch shape rather than a padded worst case [F: arXiv:2501.01005].
Multi-node: the same paged layout is what makes KV *transferable* — a block is a
self-contained chunk, so moving a prefix between nodes (P→D disaggregation,
hierarchical/offloaded KV) is a block-copy problem over NVLink/RDMA
(`../KV-Cache/README.md` distributed section, `Multi-Node.md`).

## SGLang vs vLLM — philosophy, not a performance verdict
| | **vLLM** | **SGLang** |
|---|---|---|
| **Architecture** | compatibility-first engine + **pluggable kernel ecosystem** (FA, FlashInfer, TRTLLM-GEN, FlashMLA, Triton backends) [F] | **program-aware runtime**: DSL frontend co-designed with scheduler + radix KV + FlashInfer [F] |
| **Prefix mechanism** | hash-based APC: hash chunks → block list, refcount sharing; sharing *discovered* by engine [F: vLLM docs] | RadixAttention: radix tree over prefixes; sharing *defined structurally by the program* [F: arXiv:2312.07104] |
| **Scheduling** | Python async, iteration-level continuous batching [F] | "Zero-overhead"-designed per-iteration scheduler (vendor term), program-aware, prefill/decode co-scheduled [F: SGLang] |
| **Structured output** | via guided-decoding integrations (xgrammar-class) [A: current docs] | **native**: regex/JSON/grammar + compressed-FSM co-designed with spec decode [F: SGLang docs] |
| **Spec decode** | n-gram / EAGLE / DFlash [F] | n-gram / EAGLE / STAGE / DFlash / Spec V2 [F: SGLang docs] |
| **Best-fit workload** | new-model day-0; widest quant coverage (GGUF, most schemes); general serving [F] | agentic / structured / high-concurrency / shared-prefix-heavy [F: SGLang] |

The deep dive on vLLM's side: `./vLLM.md`. The full matrix, fairness checklist, and
the hypothesis list (H1–H10) that these claims must be tested against:
`./Engine-Comparison.md`.

**Where each tends to excel (workload-fit, not "faster"):**
- **vLLM**: you adopt a model *today* and need it to work; you need the widest
  quantization coverage or a specific attention backend; your traffic is general
  serving with modest prefix overlap.
- **SGLang**: your traffic is agentic — long shared system prompts, multi-turn
  history, tool-call DAGs, grammar-constrained outputs, high concurrency. There,
  structural prefix sharing + program-aware scheduling attack the two dominant costs
  (prefill of shared prefixes, and per-token overhead at scale) directly.
- The principle (full statement in `./Engine-Comparison.md`): **the best engine
  depends on model, hardware, request pattern, context, concurrency, quant, and SLO.**
  Neither engine is universally faster; rankings are hypotheses pending a pinned,
  apples-to-apples benchmark on *your* workload.

## Key Takeaways
1. SGLang's bet is **program awareness**: the application structure (shared prefixes,
   tool DAGs, grammars) is a scheduling input, not just tokens-in/tokens-out.
2. **RadixAttention makes prefix sharing structural** (radix tree, program-declared)
   vs vLLM's hash-discovered APC — both share paged blocks; they differ in who decides.
3. The **zero-overhead scheduler** is a vendor design goal [F: SGLang]: keep
   per-iteration host time ≪ GPU step time, or ITL grows with concurrency
   (0.2 ms vs 2.0 ms host time = 9% vs 50% GPU idle [E]).
4. The kernel layer is **FlashInfer-centric** [F: arXiv:2501.01005]: paged KV +
   ragged batching is what makes paged, co-scheduled prefill+decode practical.
5. **Choose by workload fit, then measure**: vLLM for day-0/quant-breadth, SGLang for
   agentic/structured/shared-prefix; verify with `Perf-Experiment-Template.md` and
   `./Engine-Comparison.md`, not by this page or by vendor blogs.

## Related
`./Inference-Engines.md` · `./vLLM.md` · `./TensorRT-LLM.md` · `./Engine-Comparison.md`
· `./Load-Balancing.md` · `./Multi-GPU.md` · `../Serving-Engines/SGLang.md` ·
`../Serving-Engines/README.md` · `../KV-Cache/README.md` · `../Attention/README.md` ·
`../Speculative-Decoding/README.md`

## References
- SGLang / RadixAttention — arXiv:2312.07104 [F]
- FlashInfer — arXiv:2501.01005 [F]
- PagedAttention / vLLM — arXiv:2309.06180 (SOSP'23) [F]
- Orca (iteration-level scheduling) — arXiv:2211.05102 [F]
- EAGLE — arXiv:2401.15077 [F]
- Mooncake (disaggregated KV) — arXiv:2407.00079 [F]
- SGLang repository/docs — github.com/sgl-project/sglang [F: SGLang docs]
- Vendor claims ("zero-overhead" term, 5×-class shared-prefix speedups, 96×H100
  deployment) — [F: SGLang], [F: SGLang blog]; vendor claims, not independent results.
