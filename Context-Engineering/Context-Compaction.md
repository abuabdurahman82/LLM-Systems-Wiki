# Context Compaction & Prompt Compression
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
Compaction is the policy for **what to drop, shrink, or summarize** when the
context budget (`Context-Budget.md`) is filling. Two distinct sub-fields:
1. **Prompt compression** — reduce *static* content (prompts, retrieved docs,
   tool schemas) with lossy-but-faithful compression, *before* it enters the
   window. [F: the "LLMLingua / RECOMP / 500xCompressor" line]
2. **Agentic compaction** — manage the *growing trajectory* of a long task by
   summarizing/evicting history on a schedule, preserving goal + decisions while
   dropping the raw transcript. [F: MemGPT-line; the "summarize-continue" pattern]
Both are *lossy* — the engineering question is always **what is safe to lose**
and **how to verify the load-bearing facts survived**.

## Sub-field 1 — prompt compression (static content)
The task: shrink a long prompt/doc so the model still performs, *before*
injection. The key tension: compression ratio vs faithfulness.

| Method | Paper | Ratio / mechanism | Notes |
|---|---|---|---|
| **LLMLingua** | Jiang et al. 2023, arXiv:2310.05736 [F] | coarse-to-fine, task-aware, per-token perplexity + a "question" signal; up to ~20× with little loss [F: abstract] | the reference line; prompt-agnostic |
| **LongLLMLingua** | (Jiang et al. 2024) [I] | reorders + de-duplicates for *long* multi-doc | targets the lost-in-the-middle reordering |
| **LLMLingua-2** | Pan et al. 2024, arXiv:2403.12968 [F] | *task-agnostic*, distilled small LM for token-level keep/drop; faster, ~4–5× | drops the per-task prompt; cheaper to run |
| **ReCOMP** | (2023) arXiv:2310.04408 [F] | a *selective* compressor that keeps *retrieved* passages relevant to the query | RAG-oriented (selective augmentation) |
| **500xCompressor** | (2024) arXiv:2408.03094 [F] | claims very high ratio with a compact tokenizer-style model | ratio vs quality tradeoff at the extreme end [I] |
| **In-context autoencoder (ICAE)** | Ge et al. 2023 [F: arXiv id UNVERIFIED 2026-08-19] | *learned* compression of in-context examples into short "tokens" | the research frontier: compression as a *model* capability |

**The faithfulness principle [I]:** compression is only as good as your check
that the load-bearing facts survived. The production pattern is:
1. Compress the *retrieval/scratch* content aggressively (it's replaceable —
   re-fetch if wrong).
2. Compress the *instructions* gently (an instruction that gets paraphrased away
   is a silent bug).
3. **Verify**: re-inject a compressed doc's key entities into a cheap
   "did you keep X?" probe, or diff against a canonical list.

**When NOT to compress:** short prompts, safety-critical instructions,
anything the user can see (compressed user-visible text is a bug, not a feature).

## Sub-field 2 — agentic compaction (the growing trajectory)
This is the 2025–26 production core. The trajectory (history + tool outputs)
grows unboundedly; you must compact *before the wall* on a schedule.

**The canonical pattern (MemGPT-line, arXiv:2310.08560 [F] → 2026 harnesses):**
- Treat the context window as *main memory*; keep a **fixed-size working set**
  (system + goal + recent k steps + scratchpad) and **page** older content into
  an external store.
- On a **trigger** (token-budget % threshold, e.g. ~70–80%, or a step count), run
  a **summarize-continue**: summarize the oldest slice into a compact
  "so far" block (goal, decisions made, open questions, key facts), drop the raw
  transcript, continue with `system + summary + recent_k + new work`.
- The summary is *structured*, not free prose: `[Goal][Done][Open][KeyFacts][Next]`
  so the next step re-anchors cheaply.

**Trigger design [I]:**
- **Threshold-based** (e.g. compact at 75% of budget) — smooth, but can lag a
  sudden big tool output.
- **Event-based** (compact after each tool result that exceeds a size cap) —
  catches the bloat source at the source (`../Agents/Tool-Use.md` § Seam 4).
- **Hybrid** (threshold OR size-cap) — the production default.

**What a good summary preserves [I — the "load-bearing" set]:**
1. The **goal** verbatim (re-anchor every compaction).
2. **Decisions** made and *why* (prevents re-litigating).
3. **Open questions / unresolved** (prevents dropping the thread).
4. **Key facts / identifiers** (file paths, IDs, numbers — the concrete anchors).
5. **Next step** (so the loop doesn't restart from scratch).
**What it drops:** the raw tool-output bodies, exploratory dead-ends, duplicate
state.

**The verification problem:** a summary can *silently drop* a load-bearing fact
(the classic compaction bug — the agent "forgets" a constraint). Mitigations:
- **Keep a durable goal + constraint block** that is *never* summarized
  (it lives outside the compaction region).
- **Structured extraction, not free summary** — pull named entities/constraints
  explicitly so they can be diff-checked.
- **Spot-check** — after compaction, the model re-states the goal + open items;
  a divergence is a signal the summary lost something.

## The two sub-fields combined (a full context manager)
```
        ┌──────────────┐
 input → │ 1. retrieve │  (RAG/agentic search → candidate content)
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │ 2. compress  │  (prompt-compress retrieved/scratch content; keep instructions)
        └──────┬───────┘
               ▼
        ┌──────────────┐   on trigger (threshold/size)
        │ 3. place     │  system + goal + summary(recent) + tool_outputs + instruction
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │ 4. verify    │  (did the goal + load-bearing facts survive? re-anchor)
        └──────────────┘
```
Steps 2–3 are the *per-step* cost; step 4 is the *quality* gate. A context
manager that does 2–3 without 4 is just a fancy truncator.

## Related
`Context-Budget.md` · `Agent-Memory.md` · `../RAG/README.md` ·
`../KV-Cache/Eviction.md` (the serving-side analogue) · `../Agents/Tool-Use.md` § Seam 4.

## Key Takeaways
Compression (static) and compaction (trajectory) are both *lossy by design*; the
discipline is **verify the load-bearing facts survive** and **keep the goal outside
the compaction region**. Compress scratch aggressively, instructions gently, and
never let a summary silently drop a constraint.
