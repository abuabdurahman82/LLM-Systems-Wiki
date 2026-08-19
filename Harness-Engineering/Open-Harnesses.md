# Open Harnesses (the 2025–2026 landscape)
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
A **harness** (README) can be *open* — the scaffolding is public code, so you can
read exactly what it does to the model, swap the model, and audit the safety rails.
The 2024–2026 shift: harnesses went from private vendor glue to a *category of
open-source systems* (coding agents, general agents, frameworks), and from
"prompt + tools" to full **runtimes** (sandbox, memory, orchestration,
observability). This page maps the landscape by *shape* (not by vendor marketing),
and gives the reading checklist from `Harness-Anatomy.md` applied to each.

## The three shapes of an open harness
1. **Coding-agent CLI** — a single-purpose harness for sustained SWE work:
   editor-loop + shell + git + tests in a sandbox. (The dominant 2025–26 shape.)
2. **General-agent runtime** — a model-agnostic runtime that adds memory,
   orchestration, MCP/A2A, and tool wiring to *any* task.
3. **Orchestration framework** — a library/SDK you build your agent *with*
   (graph/state machinery, roles, handoffs); the least "opinionated", the most
   composable.

## The landscape (2025–26)
| Harness | Shape | Org / source | What's notable |
|---|---|---|---|
| **Claude Code** | coding-CLI | Anthropic [F: anthropic.com/docs] | the reference agentic-coding CLI; subagents, hooks, MCP; the "thin-harness, strong-model" pole |
| **Codex CLI / OpenAI agents** | coding-CLI + SDK | OpenAI [F: openai.com] | the OpenAI counterpart; Agents SDK (handoffs + guardrails) |
| **Cursor / Aider / OpenCode** | coding-CLI | mixed [F: repos] | **Aider** (open, repo-map + editor loop) and **OpenCode** (open, terminal-native) are open; **Cursor** is *proprietary/closed* — so only the last two of this cluster are open |
| **OpenHands** | general-runtime | arXiv:2407.16741 [F] | the open *platform*: agent + runtime + sandbox + UI; the most complete open general harness |
| **CrewAI** | orchestration | open [F: repo] | role+task "crews"; low-friction MAS |
| **LangGraph / LangChain** | orchestration | LangChain [F: repo] | the "agent-as-state-graph" line; deterministic control over the loop |
| **AutoGen / AG2** | orchestration | Microsoft, arXiv:2308.08155 [F] | composable multi-agent conversation; human-in-the-loop |
| **Semantic Kernel** | orchestration | Microsoft [F: repo] | the enterprise/typed-language side |
| **OpenAI Agents SDK** | orchestration | OpenAI [F: docs] | successor to Swarm: handoffs, guardrails, sessions |
| **Strands** | orchestration | Amazon/HF [F: HF] | the 2026 open agent framework |
| **Letta (ex-MemGPT)** | runtime+memory | arXiv:2310.08560 [F] | the *memory-first* runtime — a harness built around persistent memory |

[F: repos/docs; the "notable" column is a capability summary, not a benchmark
ranking — see the anti-pattern below.]

## How to read any of them (the `Harness-Anatomy.md` checklist, applied)
For each harness, ask the 8 questions:
1. **Static prefix** — what's in the system prompt, and is it versioned/diffable?
2. **Tool surface** — native tools vs MCP vs retrieved? How many, how big?
3. **Context policy** — ordering, compaction trigger, goal anchoring?
4. **Memory** — does it persist? vector / KG / files? write/read policy?
5. **Verification** — execution-based (tests)? independent evaluator? self-check?
6. **Budgets** — steps, tokens, $, wall-clock? no-progress detection?
7. **Sandbox** — container? network default-deny? destructive-op gates?
8. **Replay** — can you get the trace of a run?
A harness that answers all 8 *transparently* is readable; one that hides them
(vendor-closed) you can only evaluate by its *outputs* — which is why the
open harnesses matter for research (you can read the scaffold, not just the
score). [I]

## The two poles (and why the split is the live question)
- **Thin harness + strong model** (Claude-Code-pole): bet that the model absorbs
  the scaffolding; keep the harness to rails (sandbox, budgets, MCP) + a good
  ACI. Relies on `Model-vs-Harness.md`'s *absorption effect* — the harness value
  shrinks as the model improves.
- **Thick harness + any model** (OpenHands / orchestration-pole): bet that the
  *scaffold* (memory, orchestration, verification, multi-agent) carries the
  capability, so you can run a *cheaper* model and still reach the task. Relies
  on the *scaffold effect* — the harness multiplies a weak model.
The 2026 working answer [I]: **thin for the frontier model on bounded tasks,
thick for the long-horizon / multi-model / cost-sensitive case.** The
`Model-vs-Harness.md` worked table is the quantitative seed of exactly this:
the harness's ×6.7 multiplier is what lets a *weaker* model's thick harness beat
a *stronger* model's thin one.

## Anti-patterns (what a harness should NOT do)
1. **Declare a winner from marketing.** "Fastest / most capable harness" with no
   pinned benchmark is a vendor claim, not a result (the wiki's standing rule:
   no declared winners without a pinned factorial benchmark —
   `Model-vs-Harness.md` § H1). The table above is a *capability map*, not a
   leaderboard. [I]
2. **Conflate the harness with the model.** Publishing "our agent scores X"
   without the harness spec makes the number non-reproducible
   (`../Agents/Agent-Evaluation.md` § reporting).
3. **Hard-couple layers.** A harness that assumes one serving engine's
   tokenization, or one model's tool dialect, breaks when you swap either side
   (`Harness-Anatomy.md` § seams).
4. **No replay.** If you can't get the trace, you can't debug a loop, attribute
   cost, or audit a safety failure (`../Safety/`).
5. **Prompt as the only control.** Relying on "the prompt says be safe" instead
   of a sandbox is a policy, not a control (`Sandboxing.md`).

## Where the open harnesses are heading (2026, [I])
1. **MCP/A2A as the default seams** — interop is no longer optional
   (`../Agents/Agent-Protocols.md`).
2. **Memory as a first-class layer** — the vector+KG+files hybrid
   (`../Context-Engineering/Agent-Memory.md`) is converging across runtimes.
3. **Execution-based verification everywhere** — tests/linters as the default
   oracle; independent evaluators for the open-ended rest.
4. **Model routing inside the harness** — cheap model for search/summarize,
   frontier for plan/edit (`Control-Loops.md` § routing).
5. **The harness gets thinner on the frontier, thicker at the edge** —
   frontier coding CLIs shed scaffolds; multi-agent / enterprise runtimes add
   them.

## Related
`Harness-Anatomy.md` (the parts) · `Model-vs-Harness.md` (the split) ·
`Control-Loops.md` · `Sandboxing.md` · `../Agents/Agent-Protocols.md` (MCP/A2A) ·
`../Agents/Coding-Agents.md` (the flagship shape).

## Key Takeaways
Open harnesses are now a *category*, not a curiosity: coding-CLIs, general
runtimes, and orchestration frameworks — each readable against the 8-question
checklist. The live design split is **thin+strong-model vs thick+any-model**, and
the `Model-vs-Harness.md` multiplier is the quantitative seed. The anti-patterns
are the same as the wiki's standing rules: no declared winners without pinned
benchmarks, always report the harness, and never treat the prompt as a control.
