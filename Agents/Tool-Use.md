# Tool Use (function calling → MCP)
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
Tool use is the *API surface* between a model and the world: structured emission of
a named action with typed arguments, execution outside the model, and ingestion of
the result back into the context. Every agent capability in
`Agentic-AI-Evolution.md` is built on this surface — and its failure modes
(wrong tool, wrong arguments, malformed output) are the single biggest source of
per-step error in production agents [I].

## The progression
1. **Retrieval-as-tool** (2020–2022): RAG (arXiv:2005.11401 [F]) — retrieval is
   "just a tool the pipeline calls". Pre-LLM tool use, no model-side decision.
2. **Learned tool use** (2023): Toolformer (arXiv:2302.04761 [F]) — model teaches
   itself *when/how* to call tools, self-supervised. Tool use becomes a *model
   capability*, not a pipeline step.
3. **API precision at scale** (2023): Gorilla (arXiv:2305.15334 [F]) — LLM connected
   to massive API libraries with retrieved docs; ToolLLM (arXiv:2307.16789 [F]) +
   ToolBench — 16,000+ real APIs, tool-call accuracy measured against
   ground-truth. API-Bank (arXiv:2304.08244 [F]) — earlier benchmark family.
   Key finding of this era: **argument errors** (right tool, wrong params) dominated
   errors, not tool-selection errors [I: consistent across ToolLLM/ToolBench
   results].
4. **Code as action space** (2024): CodeAct (arXiv:2402.01030 [F]) — execute Python
   instead of JSON tool-calls; fewer schema errors, richer composition (loops,
   conditionals in actions). SWE-agent (arXiv:2405.15793 [F]) — the agent-computer
   interface as first-class design object.
5. **Standardized interop** (2024–2026): MCP (Model Context Protocol, Anthropic
   2024-11 [F: github.com/modelcontextprotocol — open standard; spec schema
   versioned 2024-11-05 / 2025-03-26 / 2025-06-18 / 2025-11-25 — verified live 2026-08-19] and A2A (agent-to-agent, Google/IBM
   2025-04 [F: a2aprotocol.ai]) — see `Agent-Protocols.md`.

## Anatomy of a tool call (the exact contract)
A tool-call exchange has four failure-prone seams:

```
1. DISCOVERY   which tools exist? (schemas in context; or retrieved: Gorilla style)
2. SELECTION   which tool, when? (model decision — the "tool-choice" moment)
3. ARGUMENTS   typed, schema-valid params (the precision bottleneck)
4. INGESTION   result → context (truncation? formatting? error semantics?)
```

**Seam 1 — discovery.** Every tool in-context costs its schema tokens *on every
call* (see `../Context-Engineering/Context-Budget.md` for the budget math).
At N tools with ~200–500 tokens of schema each, 50 tools can consume 10–25k of a
context window before the user message arrives [E: arithmetic, typical schema
sizes]. Mitigations: static tool lists (small N), **retrieval-based tool selection**
(Gorilla: retrieve relevant API docs per query [F]), **dynamic tool loading** (MCP
servers that expose tools on demand), or **tool groups** the model toggles.

**Seam 2 — selection.** Model-side failure modes: hallucinated tool names, calling
when it shouldn't, "parallel tool calls" that are actually sequential. Modern
frontier models expose a tool_choice control (`auto` / `none` / `required` / named)
[F: OpenAI/Anthropic API docs] — the harness usually forces `required` when the task
is known to need a tool.

**Seam 3 — arguments.** Two sub-failures:
- *Schema violation* (missing field, wrong type) → provider rejects → one retry
  cycle, or the harness validates and bounces back the error text.
- *Semantically wrong* (valid JSON, wrong meaning: e.g. `limit=1000` when the user
  meant "a few"). This class is not catchable by schema validation — it needs
  domain checks or a second model pass [I].
Code actions (CodeAct) shrink both classes: the Python interpreter is a *much more
expressive and forgiving* argument space than a JSON schema [F: arXiv:2402.01030
claim].

**Seam 4 — ingestion.** Tool results must be *token-budgeted* (a 1MB tool output
cannot enter a 128k context verbatim) — truncation, summarization, or structured
extraction. Error results need a stable convention (nonzero exit + stderr vs JSON
`{"error": ...}`) so the model learns to retry or escalate. `../Harness-Engineering/
Context-Management.md` covers the mechanics.

## Schema design (where most tool bugs live)
Principles [I: engineering practice, consistent across MCP/Anthropic/OpenAI docs]:
1. **Few, orthogonal tools** — a 40-tool surface beats 4 overlapping tools × 10.
2. **Names as verbs** (`search_files`, not `files`); argument names as
   *self-documenting* (`start_line`, not `offset`).
3. **Required vs optional deliberately** — every optional argument is a new
   hallucination surface.
4. **Return structured data, not prose** — JSON/tables the model can parse
   reliably; long prose results → summarizer first.
5. **Errors as data** — `{ "error": "…", "hint": "…", "retry": true }` beats
   free-text failure; the hint field measurably reduces retry loops [I].
6. **Idempotence + safe defaults for destructive ops** — the harness adds
   confirmation gates for anything that writes (see `../Safety/`).

## Tool-call latency economics (hand-computable)
An agent step = 1 LLM call (prompt P + completion C) + 1 tool execution. With
typical 2026 numbers [A: stated assumptions, not measurements]:
- LLM call: P=8k in, C=400 out. At frontier speeds [A: 8k prefill ≈ 0.5–2 s;
  400 decode tokens at 30–100 tok/s ≈ 4–13 s] → ~4–15 s.
- Tool exec: 10 ms–5 s (search, HTTP, code exec).
- **Total step latency ≈ 4–20 s**, i.e. a 30-step task is 2–10 min minimum,
  *before* retries. [E: arithmetic]
- Token cost: 8k in × 30 steps + 400 out × 30 = 240k + 12k = **252k tokens** (in
  dominated by re-reading context every step) — the context re-reading is the
  dominant cost; this is why **prefix caching** matters for agents
  (`../Inference/Inference-Optimization.md`; `../KV-Cache/README.md`) and why
  context compaction (`../Context-Engineering/Context-Compaction.md`) is an
  *economic* tool, not just an accuracy one.

## Verification of tool use (why it's hard)
- **Ground-truth argument checking** is only possible when the task has a known
  API contract (ToolBench-style) [F].
- **Execution-based checking** (did the code run? did the test pass?) is the
  [I: dominant production pattern for coding agents] — the environment is the
  verifier.
- **LLM-judged tool traces**: Agent-as-a-Judge (arXiv:2410.10934 [F]) — an LLM
  scores the *trajectory*, not just the final answer; useful when execution
  feedback is sparse (browser, OS tasks).

## Failure taxonomy (observed, production-shaped)
1. **Wrong tool** — similar-name confusion; mitigated by orthogonal design.
2. **Wrong arguments** — the precision bottleneck; mitigated by schema strictness,
   code actions, examples.
3. **Result misread** — model mis-parses tool output (truncation, nested JSON);
   mitigated by structured returns + extraction.
4. **Looping** — same call repeated on unchanged state; mitigated by step budgets
   + loop detection in the harness (`../Harness-Engineering/Control-Loops.md`).
5. **Privilege abuse** — tool that can read can read *anything*; the sandbox and
   allow-list are the defense (`../Safety/`, `../Harness-Engineering/Sandboxing.md`).

## Related
`../Agents/Agent-Protocols.md` (MCP/A2A) · `../Context-Engineering/Context-Budget.md` ·
`../Harness-Engineering/Context-Management.md` · `../Safety/README.md`.

## Key Takeaways
Tool use is four seams (discovery/selection/arguments/ingestion) and a token
economy problem. The 2026 stack: code-or-MCP actions, retrieved or dynamic tool
discovery, execution-based verification, and prefix caching to keep the
multi-step token bill sane.
