# Inference Optimization — What to Apply FIRST
`LAST_UPDATED: 2026-08-17` · Status: core page · All [E] numbers from the 2026-08-17 measurement session
(Testbed B: local vLLM, DeepSeek-V4-Flash-0731, 2-node TP=2, NVFP4 KV, prefix cache + chunked prefill +
DSpark spec decode ON). Full evidence trail: `Deep-Dives/inference-optimization-ladder-2026-08-17.md`.

## 30-Second Explanation
Do not apply optimizations in a fixed order — apply them in **bottleneck order**. The ladder
`baseline → observability → batching → prefix cache → quantization → KV → spec decode → parallelism →
disaggregation` is a *starting hypothesis*, and 2026 engine defaults have already collapsed its first
rungs: continuous batching, chunked prefill, prefix caching, PagedAttention and FlashAttention-class
kernels are ON by default. The question is no longer "what do I enable" but "what is actually binding
here, and what is the measured delta of the one knob that moves it?"

**Method (non-negotiable):** Observe → form hypothesis → measure → change *one variable* → benchmark →
compare → accept/reject. No optimization is recommended without the bottleneck it addresses.

## Measured ground truth (Testbed B, 2026-08-17)
| Quantity | Value | Tag |
|---|---|---|
| Prefill rate | ~2,010 tok/s, linear to 97k ctx (~6% deviation), no saturation | [E] |
| Decode B=1 | 15.4 tok/s, ITL 62–68 ms **flat across 0→98k context** | [E] |
| Batch ceiling | 75.2 tok/s aggregate at B=12 (4.9× vs B=1) — but `max-num-seqs=6` cap binding | [E] |
| Prefix cache | **8.7× TTFT**: cold 3.92 s → warm 0.45 s on 8k identical prefix | [E] |
| Chunked prefill | 3×16k prefills → even TTFT staircase (7.96/15.88/23.78 s), aggregate rate unchanged ~2,000 tok/s | [E] |
| Spec decode (DSpark k=5) | 2.73 accepted tokens/step; per-position accept 84/67/52/40/30% | [E] |
| Bandwidth ceiling | 79 tok/s (single-node reading) / 157 tok/s (2-node aggregate); active bytes 9.5 GB/step | [I math, spec BW] |

**The key structural finding:** B=1 decode sits **5.1×–10.2× below the HBM bandwidth ceiling** →
decode on this stack is **dispatch/comm-bound, not bandwidth-bound**. This inverts the textbook "you're
bandwidth-bound so quantize next" reasoning: more quantization buys less than textbook while the
dispatch gap dominates. (Open question E4: profile to attribute the gap between MoE dispatch,
2-node TP allreduce, and kernel inefficiency.)

## The technique × effect table (summary)
Full 18-row table with TTFT/ITL/throughput/memory/quality/GPU-util/ops-complexity columns: see
§2 of `Deep-Dives/inference-optimization-ladder-2026-08-17.md`. Rows: continuous batching, chunked
prefill, prefix caching, KV-cache optimization, KV quantization, speculative decoding, FP8/INT8/INT4,
AWQ/GPTQ, FlashAttention, PagedAttention, GQA/MLA, TP, PP, EP, P/D disaggregation.

Headline cells:
- **Prefix caching** — the only technique with a *directly measured causal delta* (8.7× TTFT) and zero
  quality risk. Scales with hit-rate × prefix-length share.
- **MLA vs MHA (architecture)** — 85× fewer KV dims/token, precision-independent
  (8,256 vs 704,512 dims/token [E math]); KV quant stacks ~2× (FP8) / 3.6× (NVFP4 vs BF16, 4.5-bit
  convention; raw-4-bit 4.0×) on top. Not a deploy-time knob — a model-selection decision.
- **Speculative decoding** — 2.73× in *accept count*; realized ITL gain is workload-conditional and
  requires an A/B (E2). Leverage ∝ output length → high for reasoning/agent workloads, diluted at high B.

## Workload → first optimization
| Workload | Dominant bottleneck (expected) | First move |
|---|---|---|
| Interactive chatbot | redundant prefill of shared system prompt | **prefix caching**, then spec-decode A/B |
| RAG | per-request prefill of retrieved docs; KV capacity at 32k | prefix-cache the fixed head; NVFP4 KV budget |
| Coding agent | re-prefill of growing conversation each tool call | **aggressive whole-session prefix caching** |
| Long-context research agent | prefill time itself (97k = 51.5 s [E]; 1M ≈ 9 min [I]) | chunked prefill + stable-corpus-head cache, else faster prefill |
| High-throughput API | roofline knee: batch size vs P95 ITL; mixed-regime interference | right-size `max-num-seqs` (measure the knee); P/D disaggregation only if tail SLAs collide |
| Reasoning model | decode time dominates (ITL × 10⁴–10⁵ tokens) | **speculative decoding** + KV headroom |
| MoE model | expert memory + dispatch (98% of params; 9.5 GB/step active) | expert parallelism / MoE kernel quality; quantization already done |

## The evidence-challenged ladder
```
0. Observability (TTFT/ITL split, prefix hit-rate, KV util, spec acceptance, preemptions, prefill rate)
1. Scheduler right-sizing (batching already ON; find the knee; chunked-prefill budget → p95 prefill)
2. Prefix caching (stable heads; measured baseline 8.7× on identical 8k prefix)
3. Precision/quantization choice at model-selection time (FP8/NVFP4 checkpoint; KV dtype to match)
4. KV optimization (layout/eviction only if the KV cap is the *measured* binding constraint)
5. Spec decode (workload-conditional; A/B its ITL delta — E2)
6. Parallelism sizing (TP/EP to fit memory & split bandwidth)
7. Disaggregation (only with measured prefill/decode tail-collision evidence)
```
Challenges to the naive order: observability is rung 0, not optional; batching/chunked-prefill are
enable-by-default in 2026 (the work is *right-sizing*, not enabling); prefix cache moves UP for
3 of 7 profiles; quantization is a purchase decision in 2026 (checkpoints ship quantized); spec decode
is workload-conditional; parallelism/disaggregation are last, expensive, and gated on tail evidence.

## Scorecard (effort: S = flag/config · M = model/pipeline change · L = architecture)
| Optimization | Problem solved | Expected gain | Quality risk | Effort | Hardware dep | Accept-measurement |
|---|---|---|---|---|---|---|
| Observability | unknown bottleneck | 0 direct; enables all | none | S | none | — |
| Batching right-sizing | under-amortized GEMV | 4.9× throughput seen at B=12 [E]; per-req ITL +80% | none | S | GPU count | knee sweep B∈{1..32}, P95 ITL |
| Chunked-prefill budget | prefill starvation | P95 ITL under mixed load [I]; rate flat ~2,000 tok/s [E] | none | S | none | mixed-load P95 ITL |
| Prefix caching | redundant prefill | 8.7× TTFT on identical 8k prefix [E] | none | S | prefix stability | hit-rate; cold vs warm TTFT |
| KV quantization | KV bytes/seq → concurrency | 1.8× vs FP8 / 3.6× vs BF16 per token [E math] | unverified locally | S | engine support | KV util; preemptions |
| FP8/INT4 weights | decode bandwidth + VRAM | up to 2×/4× **when bandwidth-bound — less here (dispatch-bound)** | FP8 ~none; INT4 small-moderate | M | tensor cores | A/B + 50-sample quality set |
| Spec decode | per-step overhead | 2.73 accept/step [E] → ≤2.7× ITL [I]; unverified end-to-end | ~none (probabilistic) | S–M | none major | A/B ITL P50/P95, throughput |
| FlashAttention/PagedAttention | attention memory / KV fragmentation | engine-embedded; ≤0.4% block overhead at 256 | none | S | default | none measurable (already ON) |
| GQA/MLA | KV bytes/seq (architecture) | 85× fewer KV dims vs MHA [E math] | ~none | — (model choice) | — | select model, don't optimize |
| Tensor parallelism | single-node memory | 162 GB weights need ≥2 nodes [I math] | none | M | multi-node fabric | per-node bytes; ITL delta |
| Expert parallelism | MoE expert memory + dispatch | targets the 5.1–10.2× under-ceiling gap [E+I]; magnitude unverified | none | M | ≥2 nodes, NIC | decode tok/s A/B; expert balance |
| P/D disaggregation | mixed-regime interference | direction [I]; unverified locally; +fleet cost | none | L | 2 fleets + KV transfer | tail TTFT+ITL vs colocated |

## TOP 5 experiments (highest information value)
Full specs (hypothesis / independent var / controls / metrics / expected / failure interpretation):
§6 of the deep dive.
1. **E1 — throughput knee:** sweep `max-num-seqs` above the 6 cap; find B where P95 ITL degrades.
2. **E2 — spec-decode A/B:** restart without DSpark; does 2.73 accept/step become real ITL?
3. **E3 — chunked-prefill budget vs long-context interference:** P95 ITL with 4k/8k/16k budgets under mixed load.
4. **E4 — dispatch-bound or bandwidth-bound?** profile the 5.1–10.2× gap (MoE dispatch vs 2-node
   allreduce vs kernels); measure real DRAM throughput to replace the 273 GB/s spec constant.
5. **E5 — prefix-cache economics on a realistic agent trace:** is warm-TTFT P50 ≥3× vs cold when
   prefixes are *similar but not identical*?

## Limitations
- Testbed B (283B MoE, 2-node GB10, vLLM) is a different regime from a single-GPU 27B-NVFP4/SGLang
  stack: bandwidth ceiling, knee location, and dispatch attribution must be re-measured there.
- E4 is unresolved: the dispatch-gap decomposition is pending a profiling run.
- KV-quantization quality impact: UNVERIFIED locally.
- The target Qwen3.8/SGLang endpoint was unreachable during the session; all [E] numbers are Testbed B.

## Cross-links
`Continuous-Batching.md` · `Roofline.md` · `Inference-Metrics.md` · `The-Life-of-a-Token.md` ·
`Prefill-Decode-Disaggregation.md` · `Deep-Dives/pd-disaggregation-deep-dive-2026-08-17.md` ·
`../KV-Cache/Eviction.md` · `../Speculative-Decoding/README.md` · `../Serving-Engines/vLLM.md` ·
`../Labs/README.md` (Lab 13: prefix-cache causal delta)
