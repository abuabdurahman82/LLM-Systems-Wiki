# Context Management (the harness-side window policy)
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
`../Context-Engineering/Context-Budget.md` says what *fits*; this page says
*how the harness operates the window across a long run*: the canonical ordering,
the compaction trigger, the tool-output budget, the prefix-cache discipline, and
the failure modes (bloat, poisoning, goal drift). It is the *operational* twin of
the context-engineering theory.

## The canonical per-step window (production ordering)
```
[0] stable system prompt + agent role + safety rails     (cacheable; do NOT edit mid-run)
[1] tool schemas / capability contract                   (cacheable; toggle groups on demand)
[2] goal + hard constraints (NEVER compacted)            (re-anchored verbatim every step)
[3] task spec / current objective                        (from planner)
[4] retrieved context (files, docs) — compressed         (context-compressed; re-fetchable)
[5] memory retrievals (episodic + semantic)              (budget-limited; scored)
[6] trajectory summary (compacted history)               (the "so far" block)
[7] recent tool outputs (last k, size-capped)            (newer raw, older summarized)
[8] scratchpad / plan state                               (working set)
[9] the model's own last action + its observation        (recency-anchored)
[10] current instruction / what-to-do-next               (END: recency effect)
```
Two principles drive the ordering:
1. **Cacheable prefix first** (0–1): identical every step → the serving stack's
   prefix cache pays prefill once (`../KV-Cache/README.md`; `../Inference/`).
2. **Critical content at the ends** (2 at front, 9–10 at back): the U-shaped
   attention curve means the middle is where things go
   ("lost in the middle", arXiv:2307.03172 [F] —
   `../Context-Engineering/Lost-in-the-Middle-and-Long-Context-Reality.md`).
   The goal is deliberately at position 2 (primacy) *and* restated near the end
   (recency) — the "goal sandwich".

## The compaction trigger (operational spec)
```
on each step:
  if tokens(window) ≥ HIGH_WATERMARK (= 0.75 × N_budget):
      run compact():
        1. freeze [0]–[2]            (never compacted)
        2. summarize [4]–[8] oldest → [6] trajectory summary
           structured: [Goal][Done][Open][KeyFacts][Next]
        3. drop raw oldest tool outputs (keep ≤ k most recent raw)
        4. verify: restate goal+open items; diff load-bearing facts
  elif a single tool output > OUTPUT_CAP (= 5k tokens):
      summarize/extract that output now (event-based, don't wait for the wall)
```
- **High-water mark, not wall:** compact at 75% so the summary *fits* in the
  freed space; compacting at 99% is truncation wearing a summary's clothes [I].
- **Structured summary, not prose:** the `[Goal][Done][Open][KeyFacts][Next]`
  block is diff-able — you can *check* it kept the constraints (the #1 compaction
  bug is silently dropping one; `../Context-Engineering/Context-Compaction.md`
  § verification).
- **Dual trigger:** threshold-based *or* size-based; the size trigger catches a
  single 40k-token tool dump that a threshold would miss until the next step.

## Tool-output budgeting (the bloat source)
The #1 cause of agent context bloat is *unbudgeted tool outputs* [I: consistent
across production post-mortems]. Rules:
1. **Cap at the source** — the tool layer truncates/extracts before the result
   enters the window (`../Agents/Tool-Use.md` § Seam 4). A 1MB grep result
   becomes "500 matches, top 20 shown, full list at /tmp/grep.out" — the pointer
   is the context, not the payload.
2. **Summarize big structured data** — a 2k-row table → row count + schema +
   min/max/distinct + sample rows; the model re-queries if it needs specifics.
3. **Errors as summaries** — a 200-line stack trace → exception type + last 3
   frames + "full trace in log". The model learns to read the summary shape.
4. **Deduplicate** — repeated identical tool results (the same file read 3×)
   are the *same* context 3×; keep one, reference the others.

## Prefix-cache discipline (the money policy)
- **Never mutate [0]–[1] mid-run.** Editing the system prompt or reordering tools
  invalidates the cached prefix for *all subsequent steps* — a hidden 32k-token
  prefill tax on every remaining step [E: 31 remaining steps × 32k = ~1M wasted
  prefill tokens, cf. `../Context-Engineering/Context-Budget.md`].
- **Stable ordering of dynamic content:** retrieve the *same* files in the *same*
  order across a task family → the [4] region also caches. Agentic search that
  randomizes file order every run defeats the cache [I].
- **Serving-stack coupling:** vLLM prefix caching (the APC mechanism; the vLLM
  paper arXiv:2309.06180 [F] covers PagedAttention + continuous batching, the
  *foundation* on which the engine's prefix cache is built [I: the "APC" name is
  vLLM-engine terminology, not the paper's]) and SGLang
  RadixAttention (arXiv:2312.07104 [F]) both key on the *token* prefix; the
  harness's job is to make that prefix *stable and shared*.
- **Measure it:** TTFT step-over-step is the observable — a healthy agent run
  shows flat/low TTFT after step 1; rising TTFT means the cache is missing
  (ordering changed, or the engine evicted the prefix under load —
  `../KV-Cache/Eviction.md`).

## Failure modes & mitigations
| Failure | Symptom | Mitigation |
|---|---|---|
| **Bloat** | TTFT rising, compaction thrashing | tool-output caps at the source (§ tool-output budgeting) |
| **Goal drift** | agent re-litigates settled decisions | goal sandwich (front + end); goal outside compaction region |
| **Silent constraint loss** | "forgets" a requirement mid-task | structured summary + post-compaction restatement check |
| **Poisoning** | retrieved/stored bad content steers behavior | provenance tags; drop the *source*, never the goal; quarantine suspect memories (`../Context-Engineering/Agent-Memory.md`) |
| **Cache invalidation storm** | TTFT spikes every step | freeze [0]–[1]; stable dynamic ordering; monitor TTFT |
| **Recency overfit** | agent follows the newest tool result over the goal | goal restated at the *end*, after the tool outputs |

## Related
`../Context-Engineering/Context-Budget.md` · `../Context-Engineering/Context-Compaction.md` ·
`Control-Loops.md` (the loop that *uses* this window) · `../KV-Cache/README.md` ·
`../Agents/Tool-Use.md` § Seam 4.

## Key Takeaways
Operate the window with three rules: **cacheable prefix first, critical content
at the ends, cap outputs at the source.** Compaction is a *verify-after* operation,
never a silent one; the goal lives outside the compaction region; and the serving
cache makes *stability* a cost property, not just an accuracy one.
