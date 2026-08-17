# Agentic AI
`LAST_UPDATED: 2026-08-16` · Status: core section

## 30-Second Explanation
An agent = LLM + tools + memory + control loop (plan → act → observe → revise). The model
provides judgment; the harness (`Harness-Engineering/README.md`) provides the rails.
The 2024–2026 shift is from "LLM answers questions" to "LLM *does* tasks" — including
multi-hour autonomous coding, browsing, and tool use.

## The progression
```
LLM (2018–22)  →  LLM + tools (2023)  →  agent (2024)  →  multi-agent (2024–)  →  agentic workflow (2025–)
```
Each step adds a capability and a failure surface.

## Core components (the standard parts)
| Component | What it is | Research/systems |
|---|---|---|
| **Function calling / tool use** | structured tool-call emission + result ingestion | GPT-4 tools (2023), Claude tools, Qwen function-calling [F: docs]; **ToolBench** (arXiv:2302.04761) |
| **ReAct** (Yao 2022, arXiv:2210.03629 [F]) | reason + act interleaved; the template for most agent loops | — |
| **Planning** | decompose goal → subgoals; revise on failure | Plan-and-Execute; HuggingGPT (arXiv:2303.17580); LLM+P (arXiv:2304.11477) |
| **Reflection / self-critique** | generate → critique → revise | Reflexion (arXiv:2303.11366 [F]); self-refine (arXiv:2303.17651) |
| **Memory** | short-term (context) + long-term (vector/structured store) | MemGPT (arXiv:2310.08426 [F]); Letta; LangMem; agent-internal memory |
| **Delegation / subagents** | spawn specialized sub-agents for subtasks | Claude subagents; OpenAI multi-agent patterns; "orchestrator-worker" |
| **Verification / evaluators** | independent check of agent output | evaluator models (see your own pipeline: main model + independent evaluator); multi-agent debate (arXiv:2305.14325) |
| **Computer use** | operate OS/browser via screenshots + actions | Anthropic computer use (2024–2026 [F: docs]); OpenAI Operator; OpenInterpreter; OSWorld benchmark (arXiv:2404.07972 [F]) |
| **Browser agents** | navigate web for tasks | WebArena (arXiv:2307.13854 [F]); WebVoyager; Browser Use (open source) |
| **Coding agents** | sustained multi-file SWE work | SWE-agent (arXiv:2405.15793 [F]); Claude Code; Codex CLI; Devin; Terminal Bench (2025) |
| **Multi-agent debate** | N models argue; aggregate | Du et al. 2023 arXiv:2305.14325; ChatEval |

## The model-vs-harness question (the live research question)
How much of an agent's performance comes from the model vs the surrounding harness
(prompts, tools, memory, retries, verification)? Evidence:
- Harnesses can move benchmark scores by 10–30+ points on agentic evals [I: consistent
  across SWE-bench-class work — the "agent scaffold matters" literature].
- But capability ceilings track the model (Claude Code vs Codex vs Cursor gaps track
  model gaps) [I].
- The 2025–26 trend: model improvements *absorb* harness tricks (e.g., long-horizon
  reliability trained in, not scaffolded) — and harnesses get thinner. [I]
See `Harness-Engineering/README.md` for the dedicated treatment.

## Production agentic systems (2025–2026)
- **Coding:** Claude Code (Anthropic), Codex/OpenAI, Cursor, Aider, OpenCode — the
  dominant 2025–26 category [F: repos/docs].
- **Computer use:** Operator/Computer-Use (OpenAI/Anthropic), OpenInterpreter.
- **Enterprise agents:** ChatGPT Work, Claude for enterprise, Gemini agents — "from
  asking to doing" (OpenAI 2026-08 [F: RSS]).
- **Open frameworks:** LangGraph, CrewAI, OpenAI Agents SDK, Strands (HF 2026 [F]).

## Failure modes (the standing list)
1. Error compounding over long horizons (each step's error propagates).
2. Tool misuse / privilege escalation (`Safety/`).
3. Context bloat → lost-in-the-middle → degraded late-task performance
   (`Context-Engineering/`).
4. Verification blind spots (agent verifies itself with the same model).
5. Cost explosion (agent loops = many tokens; economics is the real constraint).

## Related
`Reasoning/README.md` · `Harness-Engineering/README.md` · `Context-Engineering/README.md` ·
`Safety/README.md` · `Evaluation/README.md` (agent benchmarks).

## Key Takeaways
Agent = model + harness + tools + loop. The model sets the ceiling; the harness sets how
much of it you reach. The live question is how much capability the 2026+ models absorb
into the forward pass vs leave to the scaffold.
