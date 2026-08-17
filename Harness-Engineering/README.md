# Harness Engineering
`LAST_UPDATED: 2026-08-16` · Status: core section

## 30-Second Explanation
The **harness** is everything around the model: system prompts, tools, memory, context
construction, retrieval, planning loops, verification, subagents, retries, sandboxing,
code execution, observability. Harness engineering is the discipline of designing that
scaffolding to maximize task performance *for a given model*.

## Why it exists
The model is a fixed function (at a given version); the task is open-ended. The gap is
closed by the harness. Two of the same model wrapped differently can differ by more than
two model generations on agentic evals [I: consistent with SWE-bench-class scaffold
experiments].

## The component inventory
| Component | Role | Design question |
|---|---|---|
| **System prompt** | role, constraints, style, tool contract | length vs specificity; stable vs dynamic parts (prefix-cacheable) |
| **Tools / function calling** | capabilities beyond text | schema design, error formats, tool granularity |
| **Context construction** | what goes in the window *now* | selection, ordering, budgeting (`Context-Engineering/`) |
| **Retrieval (RAG)** | ground external knowledge | chunking, reranking, freshness (`RAG/`) |
| **Memory** | cross-session state | write/read policies, compression |
| **Planning** | task decomposition | plan-ahead vs interleaved; replan triggers |
| **Verification** | check before acting/committing | static checks, test execution, independent evaluator |
| **Reflection / retries** | self-correction | budget; when to stop |
| **Subagents / delegation** | parallelize or specialize | fan-out criteria; result merging |
| **Evaluators (2nd model)** | independent critique | separate model to avoid self-confirmation (your own main+evaluator pipeline is the canonical pattern) |
| **Sandboxing / code execution** | safe effect-taking | isolation, resource caps, network policy |
| **Error recovery** | tool failures, API errors | retry semantics, fallbacks, state repair |
| **Observability** | trace everything | token budgets per step, cost attribution, replay |

## The central research question
**How much of an agent's performance comes from the model vs the harness?**
Evidence base (all [I] unless noted — this is an active, contested question):
1. Scaffold effect: identical model, different harness → 10–30 pt swings on SWE-bench
   Verified, Terminal Bench-class evals (SWE-agent paper ablations [F: arXiv:2405.15793]).
2. Ceiling effect: at fixed harness, model swaps dominate the ranking (Claude vs GPT vs
   DeepSeek gaps persist across harnesses) [I: cross-vendor benchmark reading].
3. Absorption effect: each model generation absorbs harness techniques (long-horizon
   reliability, tool discipline) — harness value shrinks as models improve, but never to
   zero (cost/observability/safety rails remain) [I: 2025–26 industry consensus].

## Benchmarks that measure harness effect
- SWE-bench / SWE-bench Verified (coding agents, scaffold-sensitive)
- Terminal-Bench (terminal agents, 2025 [F: terminal-bench repo])
- OSWorld / OSWorld-Verified (computer use, harness = action policy)
- GAIA / GAIA-2, τ³-bench (tool use)
- AgentBench, WebArena, BrowseComp (retrieval-heavy)
`Evaluation/README.md` + `Benchmarks/README.md`.

## Design principles (field wisdom, [I])
1. Prefix-cacheable stable system prompt; dynamic context after it.
2. Tools: few, precise, well-documented; error messages are *instructions to the model*.
3. Verification: always external to the acting model where safety matters.
4. Budget everything: tokens, wall-clock, retries — the agent must know its budget.
5. Observability: a trace you can replay is worth more than a leaderboard number.
6. Sandboxing: capability = risk; gate by effect, not by prompt.

## Related
`Agents/README.md` · `Context-Engineering/README.md` · `Safety/README.md` ·
`Labs/Lab-12` (two-model agent/evaluator experiment).

## Key Takeaways
Harness = the engineering around the model. The model sets the ceiling; the harness
determines how much of it the task sees — and the harness is where most production
reliability (and safety) lives.
