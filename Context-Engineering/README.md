# Context Engineering
`LAST_UPDATED: 2026-08-19` · Status: first-class section (extended 2026-08-19)

## 30-Second Explanation
**Prompt engineering** = crafting the instruction. **Context engineering** = deciding
*what information* fills the context window, *in what order, at what budget*, for each
step of a task — including conversation history, retrieval results, tool outputs,
summaries, and memory. **Harness engineering** = the whole system
(`../Harness-Engineering/`). Context engineering is the heart of the harness:
the window is the model's *entire world* at inference time.

This section makes the discipline *quantitative*: the window is a hard budget
(`Context-Budget.md`), the model's usable span is *shorter* than its nominal one
(`Lost-in-the-Middle-and-Long-Context-Reality.md`), and every production system
needs a policy for what to compress, keep, or evict
(`Context-Compaction.md`, `Agent-Memory.md`).

## The three layers (don't conflate)
| Layer | Question | Example |
|---|---|---|
| Prompt engineering | how to ask | system prompt wording, few-shot examples |
| **Context engineering** | what to know now | which files, which history, which tool results fit in 128k |
| Harness engineering | how to operate | loops, tools, verification, subagents |

## The pages in this section
| Page | The question it answers |
|---|---|
| `Context-Budget.md` | What *fits* in the window — token + KV-memory arithmetic, prefix-cache economics |
| `Lost-in-the-Middle-and-Long-Context-Reality.md` | What actually *works* — effective context vs nominal, position effects, extension methods |
| `Context-Compaction.md` | What to *drop, shrink, or summarize* — prompt compression, agentic compaction, tree-indexed memory |
| `Agent-Memory.md` | What to *persist* — short/long-term memory architectures (MemGPT → Mem0/Zep/A-MEM) |

## Why it matters (the failure it prevents)
**Lost-in-the-middle** (Liu et al. 2023, arXiv:2307.03172 [F]): *task performance*
degrades when relevant information sits in the *middle* of a long context
(U-shaped performance vs position). Context engineering places *critical* information at
the ends (recency + primacy) and keeps total length under the model's reliable range.
Note: "context length" ≠ "usable length" — the effective attention span is often far
below the nominal max [I: consistent across long-context evals;
`Lost-in-the-Middle-and-Long-Context-Reality.md`].

## Production patterns (2025–26, [I])
- Agent harnesses: stable system prompt (cached) → task spec → retrieved files →
  tool outputs (truncated) → plan → history summary → current instruction.
- Compaction triggers: token-budget % (e.g. 70%) → summarize → continue
  (`Context-Compaction.md` § trigger design).
- Memory: append-only log + periodic consolidation; retrieval by recency + relevance
  (`Agent-Memory.md`).

## Related
`../Agents/` · `../Harness-Engineering/` · `../RAG/README.md` ·
`../KV-Cache/README.md` (prefix-caching economics + the memory equation) ·
`../Graph-Engineering/Knowledge-Graphs-and-GraphRAG.md` (graph-structured context).

## Key Takeaways
The window is the model's working memory. Context engineering = information triage
under a *hard, hand-computable* budget, done every step, for as long as the task
lasts — with the sharp 2026 realization that the *effective* window is far smaller
than the advertised one.
