# Agentic AI Engineering
`LAST_UPDATED: 2026-08-19` · Status: first-class section (extended 2026-08-19)

## 30-Second Explanation
An agent = LLM + tools + memory + control loop (plan → act → observe → revise).
The model provides judgment; the **harness** (`Harness-Engineering/`) provides the
rails. The 2024–2026 shift is from "LLM answers questions" to "LLM *does* tasks" —
including multi-hour autonomous coding, browsing, and tool use. This section is the
engineering discipline of making that reliable: how loops are structured, how tool use
is made precise, how multi-agent systems coordinate, how coding agents are built, and
how all of it is *measured*.

## The evolution this section explains
```
Foundation Model (2018–2023)          LLM: in-context knowledge + generation
   ↓
Tool-augmented LLM (2023)             "LLM + 1 tool call" (Toolformer/ToolLLM era)
   ↓
Agent (2023–2024)                     loop: plan → act → observe → revise (ReAct et al.)
   ↓
Multi-agent system (2024–)            roles, delegation, orchestrators (MetaGPT/AutoGen)
   ↓
Agentic workflow (2025–)              graph-shaped pipelines + learned workflows (AFlow)
   ↓
Frontier coding agents (2025–2026)    sustained multi-file SWE work, hours-long horizons
```
Each step adds a capability **and a failure surface** — the discipline is managing
both simultaneously. See `Agentic-AI-Evolution.md` for the full history with sources.

## The standard parts (component map)
| Component | What it is | Where in this wiki |
|---|---|---|
| **Function calling / tool use** | structured tool-call emission + result ingestion; API precision | `Tool-Use.md` |
| **Reasoning strategy** | CoT/ReAct/Reflexion/ToT — how the model thinks between acts | `Agent-Loops-and-Reasoning-Strategies.md` |
| **Planning** | decompose goal → subgoals; revise on failure | `Agent-Loops-and-Reasoning-Strategies.md` |
| **Memory** | short-term (context) + long-term (external store) | `../Context-Engineering/Agent-Memory.md` |
| **Delegation / subagents** | spawn specialized sub-agents; orchestrator-worker | `Multi-Agent-Systems.md` |
| **Verification / evaluators** | independent check of agent output (incl. agent-as-judge) | `Agent-Evaluation.md` |
| **Computer/browser use** | operate OS/browser via screenshots + actions | `Coding-Agents.md`, `Agent-Evaluation.md` |
| **Coordination protocols** | MCP (tool wiring), A2A (agent-to-agent) | `Agent-Protocols.md` |
| **Benchmarks** | SWE-bench, tau-bench, WebArena, OSWorld, GAIA, Terminal-Bench… | `Agent-Evaluation.md` |

## The model-vs-harness question (the live research question)
How much of an agent's performance comes from the model vs the surrounding harness
(prompts, tools, memory, retries, verification)? Evidence:
- Harnesses can move benchmark scores by 10–30+ points on agentic evals [I: consistent
  across SWE-bench-class work — see `Harness-Engineering/Model-vs-Harness.md`].
- Capability ceilings track the model: frontier-vs-frontier agent gaps track
  underlying model gaps [I].
- 2025–26 trend: model improvements *absorb* harness tricks (long-horizon reliability
  trained in rather than scaffolded) — and production harnesses get thinner [I].

## Production agentic systems (2025–2026)
- **Coding:** Claude Code, Codex/OpenAI, Cursor, Aider, OpenCode — the dominant
  2025–26 category [F: repos/docs; see `Coding-Agents.md`].
- **Computer use:** Anthropic computer use (public beta, 2024-10 [F:
  anthropic.com/news/3-5-models-and-computer-use]); OpenAI operator-style products.
- **Enterprise agents:** "from asking to doing" — task-completion products
  (OpenAI 2026 [F: vendor announcements; labelled vendor claim]).
- **Open frameworks / SDKs:** LangGraph, CrewAI, OpenAI Agents SDK,
  OpenHands (arXiv:2407.16741), Strands (HF) [F: repos].
- **Open interop:** MCP (tools), A2A (agent coordination) — `Agent-Protocols.md`.

## Failure modes (the standing list)
1. **Error compounding** over long horizons — each step's error propagates
   (multiplicative, not additive: `Agentic-AI-Evolution.md` has the math).
2. **Tool misuse / privilege escalation** — see `Safety/`.
3. **Context bloat** → lost-in-the-middle → degraded late-task performance
   (`../Context-Engineering/`).
4. **Verification blind spots** — the agent verifies itself with the same model
   (`Agent-Evaluation.md`).
5. **Cost explosion** — agent loops = many tokens; per-task economics is the real
   constraint (hand-computed example in `Agent-Evaluation.md`).

## Reading order
1. `Agentic-AI-Evolution.md` — the full story 2022 → 2026 with sources
2. `Tool-Use.md` — the API surface agents are built on
3. `Agent-Loops-and-Reasoning-Strategies.md` — the control loop + reasoning families
4. `Multi-Agent-Systems.md` — coordination, delegation, when multi-agent helps
5. `Coding-Agents.md` — the flagship application (SWE) in depth
6. `Agent-Evaluation.md` — benchmarks, harness effects, agent-as-judge, cost
7. `Agent-Protocols.md` — MCP/A2A interop layer

## Related
`../Harness-Engineering/` · `../Context-Engineering/` · `../Reasoning/README.md` ·
`../Graph-Engineering/Agent-Workflow-Graphs.md` · `../Safety/README.md` · `../Evaluation/README.md`.

## Key Takeaways
Agent = model + harness + tools + loop. The model sets the ceiling; the harness sets
how much of it you reach, and the evaluator (benchmarks + independent verifiers)
measures the gap. The live 2026 question: how much capability do frontier models
absorb into the forward pass vs leave to the scaffold.
