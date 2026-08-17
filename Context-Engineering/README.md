# Context Engineering
`LAST_UPDATED: 2026-08-16` · Status: core section

## 30-Second Explanation
**Prompt engineering** = crafting the instruction. **Context engineering** = deciding
*what information* fills the context window, *in what order, at what budget*, for each
step of a task — including conversation history, retrieval results, tool outputs,
summaries, and memory. **Harness engineering** = the whole system. Context engineering
is the heart of the harness: the window is the model's *entire world* at inference time.

## The three layers (don't conflate)
| Layer | Question | Example |
|---|---|---|
| Prompt engineering | how to ask | system prompt wording, few-shot examples |
| **Context engineering** | what to know now | which files, which history, which tool results fit in 128k |
| Harness engineering | how to operate | loops, tools, verification, subagents |

## The techniques
| Technique | What it does | Notes |
|---|---|---|
| **Context selection** | pick relevant chunks for the step | agentic search ("the model decides what to read") vs pre-selected |
| **Context compression** | summarize long content before injection | map-reduce; lossy — verify critical facts survive |
| **Conversation management** | sliding window vs summarization vs full-history | full-history dies on context limit; summaries drift |
| **Tool-result budgeting** | truncate/summarize big tool outputs | the #1 cause of agent context bloat [I] |
| **Long-term memory** | persistent store + retrieval | vector store, key-value, file-based (agent "notes") |
| **Working memory** | scratch space in-context | plan + current state |
| **Retrieval (RAG)** | external knowledge injection | `RAG/README.md` |
| **Prefix caching** | keep stable prefix KV-cached | system prompt + static docs first; TTFT economics (`KV-Cache/`) |
| **Semantic / prompt caching** | deduplicate repeated requests | provider-level; cost, not quality |
| **Context compaction** | mid-conversation summarization (e.g. Hermes compaction) | preserves goal + decisions, drops transcript |

## Why it matters (the failure it prevents)
**Lost-in-the-middle** (Liu et al. 2023, arXiv:2307.03172 [F]): attention to middle
content degrades as length grows. Context engineering places *critical* information at
the ends (recency + primacy) and keeps total length under the model's reliable range.
Note: "context length" ≠ "usable length" — the effective attention span is often far
below max [I: consistent across long-context evals].

## Production patterns (2025–26, [I])
- Agent harnesses: stable system prompt (cached) → task spec → retrieved files →
  tool outputs (truncated) → plan → history summary → current instruction.
- Compaction triggers: token-budget % (e.g. 70%) → summarize → continue.
- Memory: append-only log + periodic consolidation; retrieval by recency + relevance.

## Related
`Agents/README.md` · `Harness-Engineering/README.md` · `RAG/README.md` ·
`KV-Cache/README.md` (prefix caching economics).

## Key Takeaways
The window is the model's working memory. Context engineering = information triage under
a hard budget, done every step, for as long as the task lasts.
