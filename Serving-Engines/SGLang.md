# SGLang (RadixAttention runtime)
`LAST_UPDATED: 2026-08-16` · Status: engine page (architecture facts [F] from SGLang
paper arXiv:2312.07104, README, release notes; performance claims [I] — verify via
`Labs/Lab-8`)

## 30-Second Explanation
LMSYS's engine built around **program awareness**: a frontend DSL that knows the
application's structure (multi-turn programs, tool-call DAGs, structured output) feeds a
scheduler and a **radix-tree prefix cache**. Its differentiator is the co-design of
frontend, scheduler, and KV — not any single kernel.

## Architecture
- **Frontend:** SGLang DSL / structured outputs; the program (not just tokens) is the
  scheduling unit [F: paper].
- **Scheduler:** Python, per-iteration CPU cost designed to be negligible vs GPU step
  time — vendor term **"zero-overhead"** (v0.4 release: "Zero-Overhead Batch
  Scheduler") [F: README/release notes]. *Note: it is a Python scheduler; "zero-overhead"
  is a design claim, not a language property.*
- **KV cache manager:** paged blocks (default 64 tokens) + **RadixAttention** — a radix
  tree mapping shared prefixes to physically shared paged blocks; tree-structured
  lookup/eviction [F: paper]. 5×-class speedups on shared-prefix workloads (vendor-
  reported [F: blog]).
- **Prefix caching:** structural by construction — the frontend tells the engine which
  prefixes are shared; no token-hash guessing [F].
- **Chunked prefill:** supported; claims low per-chunk overhead [F: docs].
- **Attention:** FlashInfer (primary), FlashAttention, Triton [F].
- **GEMM/MoE:** CUTLASS / Triton / FusedMoE [F].
- **Quantization:** FP4 (NVFP4-class), FP8, INT4, AWQ, GPTQ [F: docs].
- **Speculative decoding:** n-gram, EAGLE, STAGE, DFlash, Spec V2; compressed-FSM
  structured decoding co-designed with speculation [F: paper/blog].
- **Parallelism:** TP, PP, EP; large-scale EP demonstrated at 96×H100 (DeepSeek blog)
  [F]; multi-node via NCCL.
- **Disaggregation:** prefill/decode disaggregation; scheduler is program-aware
  (knows which requests belong to the same program) — batched KV transfer for siblings
  is an inference, not documented behavior [I]. DeepSeek 96×H100 production blog [F].
- **Observability:** Prometheus metrics (`kv_cache_utilization`, …) [F].

## Where it stands (fit, not performance verdict)
- Best fit: agentic / multi-turn / structured workloads at high concurrency; shared-
  prefix-heavy traffic.
- Open question: does the zero-overhead claim hold head-to-head vs vLLM at B≥128?
  Unverified — test it (H4).

## Mermaid
```
flowchart LR
  DSL[SGLang DSL / program] --> Sched[zero-overhead-claimed scheduler]
  DSL --> Radix[Radix tree prefix cache]
  Sched --> Radix
  Radix --> Alloc[paged blocks]
  Sched --> Batch[program-aware continuous batch]
  Batch --> Prefill[FlashInfer prefill]
  Prefill --> KV[(shared KV blocks)]
  KV <--> Decode[decode]
  Decode --> FSM[compressed-FSM structured decode] --> SSE
```

## Related
`Serving-Engines/vLLM.md` · `Serving-Engines/TensorRT-LLM.md` · `KV-Cache/README.md` ·
`Agents/README.md` (program-awareness ↔ agentic workloads).
