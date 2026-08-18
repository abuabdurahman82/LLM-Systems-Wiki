# Inference Optimization: What to Apply FIRST
`Evidence-based deep dive` · 2026-08-17 · Two independent-evaluator passes (deepseek-v4-flash-0731 @ 10.1.1.51:8888; 8 flags adjudicated — see §8). Testbed B = local vLLM, DeepSeek-V4-Flash-0731, 2-node TP=2, NVFP4 KV, prefix cache + chunked prefill + DSpark spec decode all ON. Companion core page: `../Inference-Optimization.md`. Sister deep dive: `./pd-disaggregation-deep-dive-2026-08-17.md`.

**Evidence-based optimization ladder for LLM serving · 2026-08-17**

Method: Observe → hypothesize → measure → change one variable → benchmark → compare → accept/reject.
Every recommendation below is linked to a measured bottleneck or an explicit hypothesis test. Nothing is
recommended on "best practice" grounds alone.

**Claim tags:** [F] verified primary source · [A] assumption · [I] inference · [E] measured/verified this session.

---

## 1. Evidence base — what was actually measured this session

### 1.1 Testbeds
| | Testbed A (primary target workload) | Testbed B (measurement host) |
|---|---|---|
| Model | RadixArk/Qwen3.8-27B-NVFP4 | deepseek-ai/DeepSeek-V4-Flash-0731 |
| Engine | SGLang (v1 API) [F: /v1/models owned_by=sglang, 2026-08-15] | vLLM 0.25.2.dev0 [E: system_fingerprint] |
| Endpoint | 10.1.1.60:30000 | 127.0.0.1:8888 |
| GPU | UNVERIFIED (host was up on 2026-08-15; [A] RTX 5090 per user spec) | NVIDIA GB10, TP=2 over 2 nodes [E] |
| max_model_len | 100,000 [F: /v1/models 2026-08-15] | 1,048,576 [E] |
| Status 2026-08-17 | **DOWN** — TCP connect to 30000 (and 80/443/8000/8080) fails in <1 ms [E] | **UP**, serving |

**Consequence:** no new numbers could be pulled from the Qwen3.8 endpoint today. All [E] numbers below are
from Testbed B. Where the ladder's recommendations for the Qwen3.8 workload depend on Testbed-A evidence,
they are marked as experiments to run once the endpoint is back (§7).

### 1.2 Testbed B configuration (the live optimization state we measured against)
From the running vLLM process [E: `ps`]:
- `--kv-cache-dtype nvfp4_ds_mla` (NVFP4 KV cache, MLA-optimized layout)
- `--enable-prefix-caching --enable-chunked-prefill`
- `--max-num-seqs 6 --max-num-batched-tokens 8192` (chunked-prefill budget)
- `--speculative-config {"method":"dspark","num_speculative_tokens":5}` (vendor DSpark draft, 5 tokens/step)
- `--tensor-parallel-size 2 --nnodes 2`
- `--moe-backend flashinfer_b12x`, `--enable-flashinfer-autotune`
- block_size=256, gpu_memory_utilization=0.80

**This matters:** six of the seventeen techniques on the user's list are ALREADY deployed here.
The measured effects are therefore *deltas of a further optimization*, not of turning the first one on.
I report both readings.

### 1.3 Model facts (fetched live from HF, config.json 2026-08-17)
- 43 layers, hidden 4096, vocab 129,280, 256 routed experts + 1 shared, top-6, MoE FFN 2048 [F: config.json]
- Attention: 64 heads, head_dim 512, MLA with `num_key_value_heads=1`, shared KV latent 128 + 64 rope dims [F: config.json]
- Weights: FP8 attention/dense + NVFP4 experts (`expert_dtype: "fp4"`, block 128×128, ue8m0 scales) [F: config.json]
- Derived [E: Python-verified 2026-08-17]:
  - **Total params ≈ 283.3 B** (embeddings 1.1 B + attention 4.2 B + experts 278.1 B = 98% of params).
    [I] Attention figure assumes the DeepSeek LoRA-factorized Q/O layout implied by the config's
    `q_lora_rank=1024` / `o_lora_rank=1024` (a full-rank 64×512 Q/O would be ~11.5 B; the config's
    explicit low-rank fields are the basis for 4.2 B). HF safetensors reports 304.2 B *tensors* /
    166.9 GB file [F: HF API]; the 20.8 B gap vs 283.3 B is quant scales (ue8m0, F32), the
    indexer heads, the nextn/dspark layers — i.e. tensor count ≠ clean architectural param count.
  - **Active per decode step ≈ 12.8 B** (dense 5.2 B + 6 routed experts 6.5 B + 1 shared expert 1.1 B)
  - **Active bytes/step ≈ 9.5 GB** (experts @4.5 bit/param + dense @1 B/param)
  - **KV per token = 43 × (128+64) = 8,256 dims, shared across heads** (MLA) → 8.1 KB/token FP8;
    NVFP4 (4.5 bit/dim incl. block-scale overhead — the documented convention, not raw 4-bit) =
    4.54 KB/token (raw 4-bit would be 4.03 KB) → **0.152 GB per 32k-context sequence (NVFP4, 4.5-bit
    convention; 0.135 GB raw 4-bit)**, 0.609 GB per 128k sequence (0.541 GB raw 4-bit)
- HF safetensors metadata: 304.2 B tensors total, file size 166.9 GB [F: HF API]

### 1.4 Measured performance (client-side, streaming, /v1/completions, temperature=0)

**A. Prefill sweep (B=1, out=32)** [E]
| prompt | TTFT | prefill rate |
|---|---|---|
| 447 tok | 0.41 s | — |
| 2,013 tok | 1.08 s | ~1,870 tok/s |
| 8,103 tok | 3.90 s | ~2,080 tok/s |
| 32,376 tok | 16.11 s | ~2,010 tok/s |
| 97,191 tok | 51.47 s | ~1,888 tok/s |

→ TTFT is **linear in prompt length** (97k/32k = 3.00× in tokens, 3.19× in time; ~6% rate deviation
across 32k→97k). No saturation at 100k context. [E]

**B. Decode latency** [E]
| context | B | mean ITL | per-req speed |
|---|---|---|---|
| small | 1 | 62–68 ms | ~15.4 tok/s |
| 32k | 1 | 66 ms (256-out decode) | ~15.2 tok/s |
| 98k | 1 | 68 ms | ~14.7 tok/s |

→ **ITL is flat across context length 0→98k** and essentially flat across short-prompt B=1.
At B=4 (1k prompts, 64 out): ITL 114–235 ms (~4–8.7 tok/s/req), wall 3.6 s.

**C. Prefix cache** [E]
| run | prompt | cached_tokens | TTFT |
|---|---|---|---|
| cold | 8,103 | 0 | 3.92 s |
| warm (identical prefix) | 8,103 | 7,936 | 0.45 s |

→ **8.7× TTFT reduction; cached prefix processed at ~17,636 tok/s vs ~2,010 tok/s cold (8.8×)**.
vLLM counters: 411,102 prompt tokens total, 66,816 served from local cache (16.3% hit-rate of prompt volume,
but that includes my benchmark's own repeats; the controlled cold/warm pair is the clean signal).

**D. Speculative decoding (DSpark, k=5)** — cumulative counters from the serving session [E]
- 17,240 draft steps → 46,981 accepted tokens = **2.73 accepted/step** (incl. bonus token)
- Per-position acceptance: 84% / 67% / 52% / 40% / 30%
- Measured B=1 decode ≈ 15.4 tok/s **with** spec decoding enabled.
- [I] A bandwidth-bound decode reading 9.5 GB active bytes per step:
  - at a single GB10's ~273 GB/s [spec-sheet, not measured] → ≈29 fwd-steps/s × 2.73 ≈ **79 tok/s ceiling**;
  - at 2-node aggregate (TP=2 over 2 nodes, each node reads its own weight shard → 2×273 ≈ 546 GB/s) → ≈157 tok/s ceiling.
  - Measured 15.4 tok/s → **~5.1× below the conservative (single-node) ceiling, ~10.2× below the 2-node ceiling**,
    i.e. decode here is NOT purely bandwidth-bound — MoE dispatch / TP-over-2-nodes comm / kernel inefficiency
    (or all three) dominates. This is a testable inefficiency, not an explanation. E4 (below) settles which.

**E. Throughput & batching** [E]
- 12 concurrent requests (256 in / 32 out): wall 5.1 s, 384 out tok → **75.2 tok/s aggregate**.
  Per-request ITL 154–220 ms (12 reqs ≈ 2× the max-num-seqs=6 → 2 waves).
- 3 concurrent 16k prefills: TTFT 7.96 / 15.88 / 23.78 s — a **perfectly even staircase**, wall 24.3 s ≈
  the 3×16k single-stream time (48.6k tok / 24.3 s ≈ 2,000 tok/s aggregate). **Chunked prefill serializes
  prefill work at ~constant aggregate rate; it protects decoders but does NOT speed up prefill.** [E]

**F. What is already true by configuration:**
continuous batching, chunked prefill, prefix caching, NVFP4 weights, NVFP4/FP8 KV, MLA/GQA (h_kv=1),
FlashAttention-class kernels (flashinfer), DSpark spec decode, TP=2 — all ON on Testbed B.

---

## 2. Technique-by-technique effect table

Columns: effect on **TTFT / ITL / throughput / memory / quality / GPU-util / operational complexity**.
"Direction" is for a typical serving stack; magnitude cells are [E] where I measured them on Testbed B,
[I] where they are inferred from the measured numbers, [I-generic] where they follow from established
roofline logic (cited) without a local measurement. UNVERIFIED where I cannot back it.

| # | Technique | Bottleneck it addresses | TTFT | ITL | Throughput | Memory | Quality | GPU util | Op complexity |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Continuous batching** | static-batch idle slots; decode GEMV under-amortized | ~0 | ↓ per-req ITL ↑ with B (measured 62→114+ ms at B=4) [E] | ↑↑ (measured 75.2 tok/s agg vs ~15.4 B=1 = **4.9×** at B=12) [E] | ~0 | none | ↑↑ (fills SMs) | low (engine default) |
| 2 | **Chunked prefill** | long prefills monopolizing the schedule; decoder starvation behind a prefill | ↓ for *other* requests behind a big prefill; ↑ for the big one itself (adds scheduling chunks) | ↓ (decoders no longer stall behind a 50 s prefill) | ~0 (measured: aggregate prefill rate unchanged ≈2,000 tok/s) [E] | ~0 | none | ↑ (SMs busy during chunks) | low (one flag) |
| 3 | **Prefix caching** | redundant prefill of shared prefixes (system prompts, few-shot, RAG context) | **↓↓ cold 3.92 s → warm 0.45 s = 8.7×** [E]; scales with prefix-length share | 0 | ↑ effective (less prefill work) | ↑ (cache residency) | none | ↑ | low (one flag; needs stable prefixes) |
| 4 | **KV-cache optimization (layout/eviction/CP)** | KV memory cap → concurrency; long-context prefill | ↓ (larger context, fewer preemptions) | ↓ at long S (less KV read; MLA already cut it ~85× vs a same-head MHA, apples-to-apples [E math, row 14]) | ↑ (more concurrent seqs: 0.15 GB/32k-seq NVFP4 [E] means dozens fit) | ↓↓ (bytes/seq) | eviction heuristics: small risk at 50% budget, rising at 25% [I-generic] | ↑ | medium (layout) / low (eviction flag) |
| 5 | **KV-cache quantization** | KV bytes/seq → concurrency ceiling; KV read bandwidth | ↓ (more headroom before preemption) | ↓ (KV reads cheaper; measured regime is not KV-read-bound, so small here) [I] | ↑ | ↓ (NVFP4 vs FP8: 1.8× at 4.5-bit convention / 2.0× raw 4-bit; vs BF16: 3.6× / 4.0× [E math: 8,256 dims × {2, 1, 0.5625/0.5} B]) | UNVERIFIED locally; reported near-lossless at FP8, small drops at 4-bit [I-generic] | ~0 | low (one flag — already ON) |
| 6 | **Speculative decoding** | decode steps below bandwidth/compute ceiling; per-token launch+dispatch overhead | 0 (drafts only help after TTFT) | **↓ 2.73× in accept-count** [E]; realized ITL gain is the open question (§4 E2) because measured 15.4 tok/s is 5.1–10.2× under the bandwidth ceiling [E] | ~0 at high B (draft capacity dilutes) | ↑ (draft overhead small here: vendor DSpark, no separate draft model [F: config dspark_*]) | ~none (probabilistic sampling preserves distribution) [F: dspark config `draft_sample_method: probabilistic`] | ~0 | low (one flag — already ON) |
| 7 | **FP8 (weights)** | weight bytes → decode bandwidth; VRAM | ~0 (compute-bound prefill barely moves) | ↓ (up to ~2× vs BF16 when bandwidth-bound; small where dispatch-bound) [I] | ↑ | ↓ (~2× vs BF16) | ~lossless for LLMs [I-generic; consistent with vendor shipping FP8] | ↑ | low if checkpoint is FP8-native; high if you quantize |
| 8 | **INT8 (weights/act)** | same as FP8, older hardware | ~0 | ↓ similar | ↑ | ↓ ~2× | slightly more sensitive than FP8 [I-generic] | ↑ | medium (calibration) |
| 9 | **INT4 (weights)** | weight bytes → decode bandwidth + VRAM | ~0 | ↓ up to ~3–4× vs BF16 when bandwidth-bound [I] | ↑ | ↓ ~4× | small-to-moderate task-dependent drop [I-generic] | ↑ | medium (AWQ/GPTQ artifacts) |
| 10 | **AWQ** (INT4 activation-aware) | same, with less quality damage | — | as INT4 | as INT4 | as INT4 | better than naive INT4 [I-generic] | as INT4 | low if checkpoint exists |
| 11 | **GPTQ** | same, post-hoc GEMM-based quant | — | as INT4 | as INT4 | as INT4 | comparable/slightly worse on long-gen [I-generic] | as INT4 | low |
| 12 | **FlashAttention** | attention O(S²) memory traffic; non-fused attention kernels | ↓ at long S (faster prefill attention) | ~0 (decode attention is small share) | ~0 | ↓ (no S×S materialization) | none (bitwise-equivalent math) | ↑ | low (default in all modern engines) |
| 13 | **PagedAttention** | KV fragmentation → unusable memory; preemption cost | ~0 | ~0 | ↑ (higher effective KV utilization) | ↓ waste (block overhead ~1/block_size: block_size=256 here → ≤0.4% [E config]) | none | ~0 | low (engine default) |
| 14 | **GQA/MLA (architecture)** | KV bytes/seq (design-time, not deploy-time) | n/a (choose at model selection) | ↓ (less KV read) | ↑ (more concurrency) | **Apples-to-apples (precision-independent): MLA stores 43 × (128+64) = 8,256 KV dims/token vs a 64-head, d_h=128 MHA's 43 × 2 × 64 × 128 = 704,512 dims/token = 85× fewer** [E math]. Stacking KV quant adds a further ~2× (FP8) or ~3.6× (NVFP4 vs BF16) on top. | ~none (quality-neutral by construction at equal capacity) | ~0 | **not tunable post-hoc** — this is a workload-fit decision, not an optimization step |
| 15 | **Tensor parallelism** | single-GPU weight/KV capacity; weight-bandwidth split | ~0 (adds comm per step, small at B=1) | ↑ slightly (allreduce per step; measured 2-node TP adds latency [I]) | ~0 within a node; enables larger B | ↓ per-GPU weights (283B model can't fit one GB10: ~162 GB mixed-precision weights [I math: scales with the [I] attention caveat; HF file is 166.9 GB] > one node's usable memory) | none | ↑ | medium-high (NCCL topology sensitivity) |
| 16 | **Pipeline parallelism** | model doesn't fit a GPU row; >1 node | ↑ (bubble at low B) | ↑ | ~0 | ↓ per-GPU | none | ↓ at low B (bubbles) | medium-high |
| 17 | **Expert parallelism** | MoE expert memory + decode of many experts across GPUs | ~0 | ↓ for MoE at scale (experts spread, less per-node memory traffic) | ↑ at high B | ↓ per-GPU expert weights | none | ↑ | medium (router overhead; needs DP or huge B to stay busy) |
| 18 | **Prefill/decode disaggregation** | prefill and decode fighting over the same SMs/schedule; long-prefill P99 TTFT + decode P99 ITL both suffer under mixed load | ↓↓ for prefill-heavy mix (dedicated prefill fleet) | ↓↓ for decode-heavy mix (no prefill interruptions) | ↑ (both fleets sized to their regime) | ↑ total fleet (redundant weights) | none | ↑↑ (each fleet in its roofline regime) | **high** (KV transfer fabric, 2 fleets, autoscaling) |

**Key cross-check of the table against evidence:** the only technique whose effect I could directly
measure as a *causal delta* was prefix caching (§1.4C: 8.7×). Spec decode's *acceptance* is measured
(2.73×) but its *ITL contribution* is not isolated (no A/B without restart). Everything else is
config-on-both-arms or architecture-fixed; I say so in each cell rather than pretending.

---

## 3. Workload profiles and dominant bottlenecks

For each profile: likely dominant bottleneck, then the *first* optimization justified by that bottleneck.
"Iterations per task" and "prefix share" are [A] — the standard ranges I would expect; replace with your
telemetry before acting (that telemetry is step 0 of the ladder).

| Workload | Shape [A] | Dominant bottleneck (expected) | First optimization | Why, linked to evidence |
|---|---|---|---|---|
| **Interactive chatbot** | B moderate, S_in 1–4k, S_out 200–1k, prefix share high (system prompt) | **redundant prefill of shared system prompt**; then decode dispatch overhead | **Prefix caching** (then spec decode) | Measured 8.7× TTFT on identical-prefix [E]; ITL 62 ms [E] is the residual floor to attack next with spec-decode A/B |
| **RAG** | S_in = docs 4k–32k, S_out 0.5–2k, per-request docs usually unique but *templates+instructions* shared | **per-request prefill of retrieved docs** if no doc-level cache; **KV capacity** at 32k | **Prefix caching for the fixed head + larger KV budget (NVFP4 KV)** [I: doc bodies rarely repeat verbatim → lower hit-rate than chatbot; needs measurement] | Prefill at 2,010 tok/s [E] means a 16k doc costs 8 s cold; cache head, accept body; NVFP4 KV already ON |
| **Coding agent** | many calls, S_in 8k–64k (repo context), S_out 0.5–2k, **repeated conversation prefix grows** | **re-prefill of conversation history each tool-call round** | **Prefix caching (aggressive, whole-session)** [I: this is the highest-value prefix workload — every turn repeats all previous turns] | Measured 8.8× on 8k prefix [E]; an agent with 20 turns re-sends ~all prior context each call; expected TTFT cut compounds per turn |
| **Long-context research agent** | S_in 100k–1M, S_out 1–10k, low repetition | **prefill time itself** (linear, 97k = 51.5 s [E]); at 1M ≈ 9 min single-stream [I: linear extrapolation, UNVERIFIED above measured range] | **Chunked prefill + prefix cache of stable corpus head** (if corpus is re-used) else **faster prefill hardware/disaggregated prefill** | Prefill is the entire latency at this profile; decode (ITL 68 ms [E] at 98k) is secondary |
| **High-throughput API** | B high, mixed S, tail-latency SLA | **roofline knee: batch size vs per-req ITL**; prefill/decode interference under mixed load | **Right-size max-num-seqs / continuous batching** (measure knee) → **P/D disaggregation if tail SLAs collide** | Measured 75.2 tok/s at B=12 vs 15.4 at B=1 [E]; knee location UNVERIFIED (server capped at 6 seqs — that cap, not the roofline, was binding; must raise cap to find the true knee) |
| **Reasoning model** | S_out 2k–100k+ (thought tokens), long decodes | **decode time dominates end-to-end latency** (ITL × 10⁴–10⁵ tokens) | **Speculative decoding** (measured 2.73 accept/step [E]) + KV-headroom for long outputs | For a 30k-token answer at 15.4 tok/s [E], that's 32 min of decode; every ITL improvement multiplies over 30k tokens — spec decode's leverage is maximal when output length is maximal |
| **MoE model** | any of the above, with expert routing | **expert memory + dispatch overhead** (98% of params are experts [E math]); per-step active bytes ~9.5 GB [E] | **Expert parallelism / MoE kernel quality** (flashinfer backend here [E config]); quantization already done (NVFP4 experts) | Measured decode is 5.1–10.2× under the bandwidth ceiling [E+I] → the gap is dispatch/comm, the exact thing EP and kernel tuning target |

---

## 4. The optimization ladder — built, then challenged by the data

Baseline ladder proposed by the user:
`baseline → observability → batching → prefix cache → quantization → KV optimization → spec decode → parallelism → disaggregation`

**Challenges found in the evidence:**

1. **Observability must come before "batching", and it's not optional.** Every recommendation above is
   "enable X *if* the telemetry shows Y". Without TTFT/ITL decomposition, prefix hit-rate, KV utilization,
   acceptance rate, and preemption counters, you cannot know which rung to climb. On Testbed B the vLLM
   metrics endpoint gave us prefix hit-rate, spec acceptance, preemptions, KV usage in one scrape [E].
   **Verdict: ladder rung 0 confirmed, strengthened.**

2. **Batching and chunked prefill are already ON everywhere in 2026 engines** (both measured ON here
   [E]). The real question is *right-sizing* (`max-num-seqs`, chunk budget 8,192 here [E]), which is a
   tuning step, not an enable step. **Verdict: re-order — merge into observability/rung 0 as "tune the
   scheduler to your arrival distribution". The knee must be measured; on Testbed B the 6-seq cap meant
   the measured 75 tok/s throughput is scheduler-limited, not roofline-limited [I].**

3. **Prefix cache moves UP: for 3 of the 7 workload profiles it is the single highest-value first change**,
   with a measured 8.7× TTFT delta [E] and near-zero risk. The generic ladder buries it at rung 3.
   **Verdict: for chatbot/RAG/coding-agent, prefix cache is rung 1 — before quantization, before anything
   touching model bytes.** It's the only technique in the whole table whose causal effect I could measure
   without a server restart.

4. **Quantization is mostly a purchase decision, not a deploy decision, in 2026.** Both testbed models ship
   quantized (NVFP4 27B [F: model name], FP8+NVFP4 Flash [F: config]). If you chose BF16, the first real
   question is "can I switch the model to an FP8/NVFP4 checkpoint" — a model-change, not an optimization
   of a fixed stack. **Verdict: keep the rung, but re-label "model/precision selection" and run it BEFORE
   KV optimizations, because KV dtype choices interact with the weight precision already on the board.**

5. **Spec decode is a latency tool, not a throughput tool, and its value is workload-conditional.**
   Measured acceptance 2.73/step [E] is strong, but realized ITL gain requires the A/B (E2 in §5).
   The generic ladder places it at rung 6 — fine for high-throughput API (where B is high and drafts
   dilute) but **wrong for reasoning/agent workloads where it belongs at rung 2–3** [I: leverage
   proportional to output length]. **Verdict: make the rung position workload-conditional.**

6. **Parallelism and disaggregation are last and expensive, and only after the scheduler is tuned.**
   P/D disaggregation's benefit (both fleets in their roofline regime) is real but it multiplies fleet
   cost and adds a KV-transfer dependency; I have **no local measurement** supporting its net value on
   either testbed, so it is UNVERIFIED for these systems [I: direction only]. **Verdict: rung N, gated on
   tail-latency evidence that mixed scheduling cannot fix.**

**Revised, evidence-challenged ladder (for a fresh 2026 deployment):**
```
0. Observability (TTFT/ITL split, prefix hit-rate, KV util, spec acceptance, preemptions, prefill rate)
1. Scheduler right-sizing (continuous batching on; find the knee; chunked-prefill budget tuned to p95 prefill)
2. Prefix caching (stable heads; expected TTFT delta: measure, baseline 8.7× on identical 8k prefix [E])
3. Precision/quantization choice at model-selection time (FP8/NVFP4 checkpoint; KV dtype to match)
4. KV optimization (layout/eviction only if KV cap is the measured binding constraint)
5. Spec decode (workload-conditional: prioritize for long-output workloads; A/B its ITL delta)
6. Parallelism sizing (TP/EP to fit memory & split bandwidth — measured: weights 162 GB need ≥2 nodes [E math])
7. Disaggregation (only with measured prefill/decode tail-collision evidence)
```

---

## 5. Inference optimization scorecard

Effort: S = flag/config · M = model swap or data pipeline change · L = architecture change.
"Gain" is the expected delta on the *binding* metric, with the evidence state.

| Optimization | Problem it solves | Expected gain | Quality risk | Effort | Hardware dependency | Measurement required to accept |
|---|---|---|---|---|---|---|
| Observability/telemetry | Unknown bottleneck | 0 direct; enables everything else | none | S | none | — (it is the measurement) |
| Continuous batching right-sizing | Under-amortized decode GEMV | Throughput: 4.9× seen 15.4→75.2 tok/s at B=12 [E]; per-req ITL +80% [E] | none | S (limits) | GPU count | knee sweep: B ∈ {1,2,4,8,16,32}, report agg tok/s + P95 ITL |
| Chunked-prefill budget tuning | Prefill starvation of decoders | P95 ITL under mixed load (direction [I]); prefill rate unchanged ~2,000 tok/s [E] | none | S | none | mixed-load P95 ITL with budget ∈ {4k, 8k, 16k} |
| Prefix caching | Redundant prefill | TTFT 8.7× on 8k identical prefix [E]; scales with hit-rate × prefix-length | none | S | prefix stability in traffic | hit-rate from `cached_tokens`/`prompt_tokens`; TTFT cold vs warm per bucket |
| KV quantization | KV bytes/seq → concurrency | Concurrency ceiling 1.8× (NVFP4 vs FP8) / 3.6× (vs BF16) per token [E math: 8,256 dims] | UNVERIFIED locally; small [I] | S (flag) | engine support | KV utilization + max concurrent seqs before preemption |
| FP8/INT8/INT4 weights | Decode bandwidth + VRAM | Up to ~2× (FP8) / ~4× (INT4) when bandwidth-bound [I-generic]; **smaller when dispatch-bound — our testbed is 5.1–10.2× under the bandwidth ceiling, so expect less than textbook** [I] | FP8 ~none; INT4 small-moderate [I-generic] | M (checkpoint) | GPU tensor cores | A/B TTFT/ITL/throughput + fixed 50-sample quality set |
| Speculative decoding | Per-step overhead below ceiling | 2.73 accepted/step [E] → up to ~2.7× ITL if the step-overhead model holds [I]; UNVERIFIED end-to-end | ~none (probabilistic) [F: config] | S–M (draft choice) | none major | A/B with/without: ITL P50/P95, agg throughput, acceptance |
| FlashAttention-class kernels | Attention memory traffic | Embedded in engine; no separate delta expected at ≤100k [I] | none | S | engine default | prefill attention share via profiler at 32k/100k |
| PagedAttention | KV fragmentation | ~1/block_size overhead saved (≤0.4% at block=256 [E config]) | none | S | engine default | KV util before/after (already on — no delta measurable) |
| GQA/MLA | KV bytes/seq (architecture) | Already maximal at h_kv=1 [F: config] | ~none | — (model choice) | — | n/a — select model, don't optimize |
| Tensor parallelism | Single-node memory | Enables 283B-class models: 162 GB weights need 2 nodes [E math] | none | M | multi-node fabric | per-node weight bytes; ITL delta vs single-node (if it fit) |
| Pipeline parallelism | Multi-node memory | ~0 throughput; + bubble latency | none | L | multi-node | bubble % vs B |
| Expert parallelism | MoE expert memory + dispatch | Targets the 5.1–10.2×-under-ceiling gap [E+I]; UNVERIFIED magnitude | none | M | ≥2 nodes, good NIC | decode tok/s A/B; expert load balance |
| Prefill/decode disaggregation | Mixed-regime interference | Direction [I]: both fleets to their roofline; UNVERIFIED locally; +fleet cost | none | L | 2 fleets + KV transfer | tail TTFT + tail ITL under mixed load vs colocated |

---

## 6. TOP 5 experiments — highest information value

Each: hypothesis · independent variable · controlled variables · metrics · expected result · failure interpretation.

### E1. Where is the throughput knee? (answers "how big may I let the batch get?")
- **Hypothesis:** aggregate throughput rises with concurrent sequences until a knee where P95 ITL degrades
  >2× its B=1 value (124 ms); on this server the knee is *at or beyond* the current cap of 6.
- **Independent variable:** `max-num-seqs` ∈ {6, 12, 24, 48} (server restart, one value at a time).
- **Controlled:** model/quant, GPU topology, arrival pattern (closed-loop, 256-in/128-out uniform),
  temperature 0, chunked-prefill budget, warm-up ≥50 requests discarded.
- **Metrics:** aggregate tok/s, P50/P95 ITL, P95 TTFT, KV utilization, preemptions.
- **Expected:** tok/s still rising at 48 with P95 ITL < 250 ms → cap was the constraint; or knee at 12–24
  → right-size there and stop.
- **Failure interpretation:** if P95 ITL degrades *before* tok/s peaks, the scheduler (chunked-prefill
  interference) is the constraint, not the roofline → move to E3. If tok/s is flat from B=6, decode is
  dispatch-bound → E2/E4 explain it.

### E2. Does spec decoding actually buy the ITL its acceptance rate promises?
- **Hypothesis:** DSpark (k=5, 2.73 accept/step [E]) reduces B=1 mean ITL by ≥40% vs spec-off on the same
  workload, with no quality change.
- **Independent variable:** `speculative-config` ON (dspark k=5) vs OFF — one restart.
- **Controlled:** same model/quant/hardware; workload = 100 requests × (1k in / 256 out), temp 0; plus a
  fixed 50-prompt quality set (answer-set diff) with temp 0.7.
- **Metrics:** mean/P95 ITL, tok/s, acceptance (from counters), quality diff on the 50-prompt set.
- **Expected:** mean ITL 65 ms → ~35–48 ms (2.73 accept × 50–70% step-efficiency, assuming draft
  generation is cheap relative to a target step — DSpark is a fused vendor draft, not a separate
  model [F: config]).
- **Failure interpretation:** if ITL drops <20% (i.e. stays >52 ms), the 5.1–10.2×-under-ceiling gap [E] is draft-generation or
  comm cost eating the accept gain → switch draft (e.g., k=7 per vendor docs [F: README]) or conclude
  dispatch-bound (→ E4). If quality diff appears, sampling mismatch → fix `draft_sample_method`.

### E3. Chunked-prefill budget vs long-context TTFT/ITL interference
- **Hypothesis:** raising the chunk budget from 8,192 to 16,384 tokens cuts P95 TTFT for 16k+ prompts by
  ≥25% while keeping P95 ITL of co-scheduled decoders <150 ms.
- **Independent variable:** `max-num-batched-tokens` ∈ {4096, 8192, 16384}.
- **Controlled:** mixed load = 2 concurrent 16k-prefill + 4 concurrent 256-in/128-out decoders, repeated
  20×; same everything else.
- **Metrics:** P50/P95 TTFT (prefills), P50/P95 ITL (decoders), aggregate tok/s.
- **Expected:** TTFT P95 drops roughly ∝ budget; decoder ITL roughly flat (chunking already protects it).
- **Failure interpretation:** if decoder ITL jumps at 16k budget, chunking protection is weaker than
  believed → keep 8k, and start designing toward P/D separation (§rung 7) for long-context-heavy traffic.

### E4. Is decode dispatch-bound or bandwidth-bound? (the 5.1–10.2× gap [E] must be explained before any
parallelism spend)
- **Hypothesis:** the 15.4 tok/s B=1 decode (vs ~79–157 tok/s bandwidth ceiling, single-node vs 2-node
  aggregate [E+I]) is dominated by inter-node TP communication + MoE dispatch overhead, *not* HBM
  bandwidth.
- **Independent variable:** none on the model — this is a profiling experiment: Nsight/NCCL counters on
  a 60 s B=1 decode capture; then a second arm with `nnodes=1` (TP=1, single node, if the model fits) vs
  the current TP=2-over-2-nodes.
- **Controlled:** same workload (256-in/512-out), temp 0, 20 iterations after warm-up.
- **Metrics:** SM active %, DRAM throughput per node vs ~273 GB/s spec (2-node aggregate 546 GB/s),
  NCCL bytes/s + latency per layer, time in MoE dispatch vs attention vs dense GEMM.
- **Expected:** DRAM throughput « spec ceiling while SM idle% high → dispatch/comm-bound confirmed.
- **Failure interpretation:** if DRAM is near ceiling, the 273 GB/s spec number is wrong (or NVFP4
  dequantization is the hidden cost) → re-derive the ceiling; either way the result re-prioritizes E1/E2
  (dispatch-bound: optimize kernels/EP; bandwidth-bound: quantize more aggressively / bigger batch).

### E5. Prefix-cache economics on a realistic agent trace (the 8.7× [E] was on an *identical* prefix;
real traffic repeats less)
- **Hypothesis:** on a replay of a real multi-turn agent trace (≥20 turns, 200-request replay), the
  cached-token share is ≥60% of prompt volume and warm TTFT P50 improves ≥3× vs cold.
- **Independent variable:** replay prefix-cache ON vs OFF (one restart).
- **Controlled:** identical trace, order, temp 0; cold runs after a cache flush.
- **Metrics:** cached_tokens/prompt_tokens (global + per bucket), TTFT P50/P95, total prefill compute-
  seconds (from `prompt_tokens_by_source`), end-to-end task latency.
- **Expected:** hit-rate 50–80% (agent prefixes re-send conversation history [A]), TTFT P50 ↓ ≥3×,
  prefill compute-seconds ↓ proportionally.
- **Failure interpretation:** hit-rate <30% → traffic has unstable heads (timestamps/ids inside the
  prefix) → fix prefix hygiene first (stable system prompt, move volatiles to tail); the engine is fine.
  This experiment decides whether prefix caching is rung 1 for *your* traffic or a non-event.

---

## 7. Answer to "what do I apply FIRST"

For **the Qwen3.8-27B-NVFP4/SGLang workload** (the stated target): the endpoint was down during this
session, so the first *actionable* items are ordered by cost-of-wrong:

1. **Get observability on that endpoint** (SGLang metrics: TTFT/ITL split, `cached_tokens`, KV usage,
   batch stats). One hour of work; everything else is ranked by its output.
2. **Enable/verify prefix caching + chunked prefill** if not already (SGLang: `--enable-prefix-caching`,
   `--chunked-prefill-size`); expected delta from Testbed B evidence: up to 8.7× TTFT on stable prefixes.
3. **Run E1 (knee)** — 27B NVFP4 on a single RTX 5090 [A] is a different regime than Testbed B (no 2-node
   TP, 1.79 TB/s GDDR7 [F: spec]), so the knee and the 5.1–10.2×-gap question (E4) must be re-answered there.
4. **Then workload-dependent:** long-output agent/reasoning → E2 (spec decode A/B); mixed tail-latency
   → E3 (chunk budget) before considering disaggregation.

For **a fresh deployment generally**: follow the revised ladder in §4. The single most defensible first
optimization, given all evidence gathered today, is **prefix caching** — it is the only technique with a
directly measured 8.7× causal TTFT delta [E], zero quality risk, one-flag effort, and it addresses the
dominant bottleneck of 3 of the 7 workload profiles. Speculative decoding is second for long-output
workloads, pending the E2 A/B. Everything else is either already ON by default, a model-selection
decision, or gated on measurements not yet taken.

## 8. Independent-evaluator pass — findings and my adjudication

Evaluator: `deepseek-v4-flash-0731` via vLLM @ 10.1.1.51:8888 (the live evaluator endpoint; same model
family as Testbed B but a separate process). Pass 1 returned `finish_reason=length` with the full audit
in the reasoning field (known behavior for this reasoning model); findings below were extracted from the
complete 44.5k-char audit trail and **each re-verified independently by me before acceptance**.

| # | Evaluator flag | My re-verification | Adjudication |
|---|---|---|---|
| 1 | "experts = 278.1 B is 43× too high; should be 6.5 B" | Evaluator computed 257 experts × 3 × 2048 × 4096 = 6.5 B **without multiplying by 43 layers**. Correct: 43 × 257 × 3 × 2048 × 4096 = 278.1 B. Cross-check: HF file size 166.9 GB ÷ ~4.36 bits/param ≈ 300 B-class model, consistent with 283 B + overhead. | **REFUTED** — evaluator dropped the layer factor |
| 2 | "attention should be 11.5 B, not 4.2 B" | Evaluator assumed full-rank Q/O (2 × 4096 × 64 × 512 per layer). The config explicitly carries `q_lora_rank=1024`, `o_lora_rank=1024`, `o_groups=8` — a factorized layout: Q d→1024→32768, O grouped 32768→1024→d. With factorization: 97 M/layer × 43 = 4.2 B. | **REFUTED as error, PARTIALLY ACCEPTED as caveat** — kept 4.2 B but added an explicit [I] note that full-rank would be 11.5 B and the low-rank reading is inferred from config fields |
| 3 | "KV vs BF16 = 8× is wrong" | 2 B (BF16) / 0.5625 B (NVFP4) = 3.56×. My "8×" had silently compared against FP32. | **ACCEPTED** — corrected to 3.6× everywhere (2 occurrences + scorecard) |
| 4 | "bandwidth ceiling wrong: 2-node TP=2 reads 2×273 GB/s aggregate" | Valid point: TP shards weights across both nodes, so per-step read is 4.75 GB from *each* node's HBM, in parallel. Ceiling ≈157 tok/s (2-node) vs 79 tok/s (single-node reading); gap vs measured 15.4 widens to ~10.2× (2-node) from ~5.1×. | **ACCEPTED** — now both readings are stated; the qualitative conclusion (not bandwidth-bound) is unchanged but stronger |
| 5 | "≤6% rate deviation is actually 6.1%" | \|2010−1888\|/2010 = 6.07%. | **ACCEPTED** — reworded to "~6%" |
| 6 | "shared expert omitted from active count" | Valid: shared expert is always active. 5.2 + 6.5 + 1.1 = 12.8 B; active bytes 9.5 GB (not 8.9). | **ACCEPTED** — active params/bytes updated; ceiling numbers re-derived on 9.5 GB |
| 7 | "283.3 B total vs HF 304.2 B tensors inconsistent" | 304.2 B *tensors* includes quant scales (ue8m0/F32, 37.7 M), indexer heads, nextn/dspark layers; 20.8 B gap. | **PARTIALLY ACCEPTED** — added one-line reconciliation; no figure changed |
| 8 | Spec-decode "incl. bonus token" confusion | 46,981/17,240 = 2.725; per-position sum 0.84+0.67+0.52+0.40+0.30 = 2.73 — consistent. | **REFUTED** — numbers were already consistent; phrasing kept |

Net: **4 accepted (2 substantive: #3, #4/#6 which also shifted the E4 target), 2 refuted, 2 partially
accepted.** The refuted flags both share one root cause: the evaluator re-derived the param breakdown
from the head geometry and dropped the layer multiplier / low-rank factorization that the draft derived
from the config — consistent with the known pitfall of evaluators silently dropping a multiplier the
draft carries.

### Pass 2 (re-audit of §1–§7 after the pass-1 fixes; verdict returned in `content`, confidence 88%)
Re-verified each pass-2 flag independently before acting:
- **KV ratios "should be 2×/4×, not 1.8×/3.6×"** — *ACCEPTED as a convention clarification*: the 1.8×/3.6×
  figures use the documented 4.5-bit NVFP4 convention (4-bit value + block-scale overhead); raw 4-bit is
  2.0×/4.0×. Both now shown side-by-side so the convention is explicit (the known evaluator convention-drift
  pitfall — it assumed pure 4-bit).
- **"MLA ~170× vs MHA is apples-to-oranges (FP8-MLA vs BF16-MHA)"** — *ACCEPTED*: the clean
  precision-independent ratio is **85×** (704,512 MHA dims/token ÷ 8,256 MLA dims/token); KV quant adds a
  further ~2× (FP8) / ~3.6× (NVFP4 vs BF16) on top. The conflated 171× removed.
- **"162 GB weights is an assumption, not [E math]"** — *ACCEPTED*: re-tagged [I math] since it scales with
  the [I] attention-param caveat; the 166.9 GB HF file size cited as the anchor.
- **"§7 '5.4×-gap' typo"** — *ACCEPTED*: leftover from the pass-1 edit; fixed to 5.1×.
- **"total params 283.3 B should be 283.4 B"** — *REFUTED*: 1.059 + 4.171 + 278.108 = 283.34 B, which rounds
  to 283.3 B, not 283.4 B.
- All measured quantities (prefill rates, 8.7× prefix-cache, 2.73 spec-accept, 75.2 tok/s B=12, ITL
  62–68 ms, ceilings 79/157, 5.1×/10.2× gap) → **CORRECT** per the evaluator, no change.

**Two-pass net: 8 flags adjudicated — pass 1 (4 accepted / 2 refuted / 2 partial) + pass 2 (4 accepted as
clarification / 1 refuted / 0 net-error introduced).** No substantive performance conclusion changed in
pass 2; all pass-2 changes were convention-explicitness and tag hygiene. Residual known gaps: the 273 GB/s
GB10 bandwidth is a spec-sheet constant, not a measured roofline (E4 exists precisely to replace it with
measured DRAM throughput).

## Appendix — numbers that would invalidate the document
- If E1 shows no throughput gain from B=6→48 on Testbed B, the "right-size the scheduler" rung is dead
  and E4 owns the next decision.
- If E2 shows <20% ITL gain, remove spec decode from the reasoning-workload recommendation.
- If E4 shows DRAM near spec ceiling, recompute all bandwidth ceilings (the 273 GB/s spec value is
  unverified hardware constant).
- Any measurement on the Qwen3.8 endpoint once it is back supersedes Testbed B numbers for that host
  (different GPU, single node, different engine).
