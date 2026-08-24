# Continuous Batching (iteration-level scheduling)
`LAST_UPDATED: 2026-08-16` · Status: core page

## 30-Second Explanation
Instead of waiting for a whole batch of requests to finish before starting the next one
(static batching), the scheduler admits/evicts individual requests **every decode step**.
A finished token frees its slot; a waiting prompt joins mid-stream. This is why modern
serving GPUs stay busy.

## The progression
1. **Static batching** — fixed batch, all-or-nothing. A short request waits for the
   longest one → terrible tail latency, low utilization.
2. **Dynamic batching** — assemble a batch opportunistically, but still batch-level
   granularity.
3. **Continuous / in-flight batching** — *iteration-level*: reschedule every step.
   [F: Orca "Iteration-level Scheduling" (Yu et al. 2022, OSDI'22, arXiv:2211.06863);
   DeepSpeed-MInference "in-flight batching" (2024); vLLM/SGLang/TRT-LLM all implement
   it [F: engine docs]]

## Why it changes GPU utilization (first principles)
- Without it, the GPU is idle during the tail of every batch (the shortest request in the
  batch finished long ago; its slots are dead). Utilization ≈ 1/avg(output-length spread).
- With it, every slot that finishes is immediately refilled. The batch is always ~full of
  *live* decode work. Utilization approaches "fraction of steps with ≥1 running request"
  [I].
- It also turns decode GEMVs into **GEMMs**: the batch dimension B grows toward the
  roofline knee (`Inference/Roofline.md`), amortizing the weight stream.

## Mechanics
- **Admission:** waiting queue; a request enters when KV blocks are available
  (`KV-Cache/README.md` paged allocation).
- **Preemption:** under memory pressure, evict (recompute or swap to CPU) low-priority
  requests' KV. [F: vLLM scheduler]
- **Chunked prefill co-scheduling:** a long prompt is prefilled in chunks *between*
  decode steps so it doesn't stall the batch — the canonical "mixed" step.
  [F: SGLang chunked prefill; vLLM `--enable-chunked-prefill`]
- **Priority & fairness:** request priorities, max-sequence-length caps, fair sharing.

## Impact
- **Throughput:** large (often the single biggest serving win) [I: consistent across engines].
- **P95/P99 latency:** better than static; tail governed by preemption + KV contention.
- **TTFT:** a *new* knob — chunked prefill trades some TTFT for decode ITL stability.

## Limitations
- CPU scheduler overhead at very high B (the SGLang "zero-overhead" claim targets this;
  unverified in head-to-head tests — see `Serving-Engines/`).
- KV fragmentation/contention at high concurrency → preemption storms.
- Mixed prefill+decode steps have different optimal kernel choices.

## Related
`Inference/The-Life-of-a-Token.md` · `Inference/Roofline.md` · `Inference/Inference-Optimization.md` · `KV-Cache/README.md` ·
`Serving-Engines/` · `Labs/Lab-5` ·
`Inference/Production-Serving/07-scheduling-inside-the-engine.md` (what the router above the engine may assume about this scheduler).

## Key Takeaways
Continuous batching is *the* utilization unlock of modern serving; chunked prefill is the
mechanism that keeps long prompts from stalling it.
