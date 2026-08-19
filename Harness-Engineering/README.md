# Harness Engineering
`LAST_UPDATED: 2026-08-19` · Status: first-class section (extended 2026-08-19)

## 30-Second Explanation
The **harness** is everything around the model: system prompts, tools, memory,
context construction, retrieval, planning loops, verification, subagents, retries,
sandboxing, code execution, observability. Harness engineering is the discipline of
designing that scaffolding to maximize task performance *for a given model*.
The model is a fixed function (at a given version); the task is open-ended. The gap
is closed by the harness.

This section makes that discipline concrete: the *anatomy* of a harness
(`Harness-Anatomy.md`), the two hardest subsystems — context management
(`Context-Management.md`) and the control loop (`Control-Loops.md`) — safety
isolation (`Sandboxing.md`), and the live research question of how much of agent
performance is model vs harness (`Model-vs-Harness.md`), plus the 2025–26 state of
open harnesses (`Open-Harnesses.md`).

## Why it exists
Two of the same model wrapped differently can differ by more than two model
generations on agentic evals [I: consistent with SWE-bench-class scaffold
experiments; SWE-agent's ACI ablations, arXiv:2405.15793 [F]]. The harness is where
*reliability* (and *safety*) is engineered — the model gives capability, the
harness gives control.

## The pages in this section
| Page | The question it answers |
|---|---|
| `Harness-Anatomy.md` | What are the parts — full component inventory + design contracts |
| `Context-Management.md` | How is the window managed across a long run — the harness-side context policy |
| `Control-Loops.md` | How does the loop run — retries, budgets, stopping, no-progress detection, routing |
| `Sandboxing.md` | How are effects contained — isolation, resource caps, network, destructive-op gates |
| `Model-vs-Harness.md` | How much is model vs harness — the evidence + a hand-computable decomposition |
| `Open-Harnesses.md` | What's open and how it's built — Claude Code, Codex CLI, Aider, OpenCode, OpenHands… |

## The component inventory (index; detail in `Harness-Anatomy.md`)
System prompt · tools · context construction · retrieval · memory · planning ·
verification · reflection/retries · subagents · independent evaluators ·
sandboxing · error recovery · observability.

## Design principles (field wisdom, [I])
1. Prefix-cacheable stable system prompt; dynamic context after it
   (`../Context-Engineering/Context-Budget.md`).
2. Tools: few, precise, well-documented; error messages are *instructions to the
   model* (`../Agents/Tool-Use.md`).
3. Verification: always external to the acting model where safety matters
   (independent evaluator — the pattern this wiki itself uses).
4. Budget everything: tokens, wall-clock, retries — the agent must know its budget
   (`Control-Loops.md`).
5. Observability: a trace you can replay is worth more than a leaderboard number.
6. Sandboxing: capability = risk; gate by effect, not by prompt (`Sandboxing.md`).

## Related
`../Agents/` · `../Context-Engineering/` · `../Safety/README.md` ·
`../Inference/Inference-Optimization.md` (the serving side of harness economics).

## Key Takeaways
Harness = the engineering around the model. The model sets the ceiling; the harness
determines how much of it the task sees — and the harness is where most production
reliability (and safety) lives.
