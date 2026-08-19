# Agent Loops & Reasoning Strategies
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
The *control loop* is the skeleton of every agent: how the model decides the next
thought, the next action, when to stop, and what to remember from each step.
Reasoning strategies (CoT, ReAct, Reflexion, ToT) are *fills* for that skeleton.
Getting the loop right matters as much as the model inside it — a bad loop wastes
capability; a good loop multiplies it [I].

## The canonical loop
```
            ┌──────────────────────────────────────────────┐
            │                                              │
   user goal┤   ┌────────┐    ┌────────┐    ┌────────┐     │
     ───────▶│   │ PLAN   │───▶│ ACT    │───▶│ OBSERVE│─────┤
            │   │(model) │    │(tool/  │    │(result,│     │
            │   └────────┘    │ code)  │    │ test,  │     │
            │                  └────────┘    │ stderr)│     │
            │                                └───┬────┘     │
            │      ┌─────────────┐               │          │
            │      │ REVISE/STOP │◀───────────────┘          │
            │      └─────────────┘  (done? error? new plan?) │
            └──────────────────────────────────────────────┘
```
Every "agent framework" (ReAct-style single loop, Plan-and-Execute, ReWOO,
Tree-of-Thought search, orchestrator-worker) is a variant of *where the model runs*
in this diagram and *what state is carried*.

## The strategy families
| Strategy | Paper | Loop shape | Cost | When it wins |
|---|---|---|---|---|
| **One-shot** | — | single forward pass | 1× | well-specified, knowledge-heavy |
| **CoT** | arXiv:2201.11903 [F] | think longer, no actions | 1–3× | multi-step reasoning, no tools |
| **ReAct** | arXiv:2210.03629 [F] | think→act interleaved, flat | N× | tool use w/ grounded feedback |
| **Reflexion** | arXiv:2303.11366 [F] | act → self-critique → retry, episodic memory | 3–10× | tasks where failure is cheap to detect |
| **Self-Refine** | arXiv:2303.17651 [F] | generate → critique → revise, same output | 3–5× | quality polish on artifacts |
| **Plan-and-Execute family** | LLM+P (Liu et al. 2023, arXiv:2304.11477 [F]) — the principled "plan → execute → replan" paper (LLM proposes, classical PDDL planner verifies/executes, LLM replans on failure) | plan once → execute steps → replan on failure | plan 1× + exec N× | long tasks w/ stable subgoals; planner-verifier hybrids. "Plan-and-Execute" as a name is mainly a community/LangChain pattern, not a single canonical arXiv paper. |
| **Tree-of-Thoughts** | arXiv:2305.10601 [F] | best-first search over partial solutions | 10–100× | search problems, puzzles, math w/ checkable states |
| **Multi-agent** | AutoGen arXiv:2308.08155 [F], MetaGPT arXiv:2308.00352 [F] | N loops, coordinated | N× | role specialization, debate, scale-out |

[E: cost column = relative token multiplier, stated as [I] ranges from observed
framework behavior — treat as planning estimates, not measurements.]

### ReAct (the workhorse)
```
Thought: I need to find the failing test.
Action:  run_tests(filter="auth")
Observation: 2 failed: test_login (AssertionError: ...), test_logout (...)
Thought: test_login fails on the redirect. Let me read the view.
Action:  read_file("views/auth.py", start=40)
Observation: def login(...): ...
```
Key properties [F: arXiv:2210.03629]:
- Observations *ground* the reasoning — the model stops inventing intermediate facts
  (vs pure CoT, which hallucinates them).
- The loop is flat: one trace, each step conditioned on all previous. Cheap to
  implement, cheap to debug.
- Failure mode: **drift** — after ~20–50 steps the model loses the thread of the
  original goal [I: observed across agent benchmarks; related to
  `../Context-Engineering/Lost-in-the-Middle-and-Long-Context-Reality.md`].

### Reflexion (self-improvement without weight updates)
Loop: attempt → (fail) → verbal self-feedback ("what went wrong, what to try
next") → store in episodic memory → retry. [F: arXiv:2303.11366]
- Works best when **failure is signal-rich** (a test tells you exactly what broke).
- The "reinforcement" is *verbal* — no gradient, no reward model; the critic and
  the actor are the same model [I — a known blind spot, see
  `Agent-Evaluation.md` § verification].

### Tree-of-Thoughts (deliberate search)
Branch on partial solutions, evaluate each node, prune. [F: arXiv:2305.10601]
- Gains are large *where states are checkable* (math, planning, puzzle domains);
  expensive everywhere else (each node = 1+ LLM call).
- The 2024+ production analogue: "test-time compute scaling" — o1/R1-class models
  reportedly do something ToT-*like* inside the forward pass over hundreds of
  reasoning tokens [I: the internal-search analogy; the exact internal
  mechanism is not published]
  (`../Reasoning/README.md`). The external search loop is now mostly for
  *verifiable* problems with a cheap checker (see RLVR in
  `../Post-Training/Alignment-RLHF.md`).

## Planning: the three designs
1. **Implicit planning** — no explicit plan artifact; ReAct-style. Cheapest;
   plans die when context fills up.
2. **Explicit one-shot plan** — generate a numbered plan, execute steps.
   (Plan-and-Execute, ReWOO.) Better goal coherence over long horizons [I];
   brittle to environment surprises (no replan).
3. **Iterative replanning** — plan → execute k steps → observe → replan.
   LLM+P (arXiv:2304.11477 [F]) is the principled version: the LLM proposes,
   a *classical planner* (PDDL) checks feasibility, execution errors trigger
   replanning. Hybrid symbolism = soundness where the model is weak [F].
   Production coding agents in 2026 mostly run design 3 with *git diff + test
   results* as the observation channel [I].

## Stopping conditions (the underrated design decision)
An agent loop must have explicit stops, or it runs until budget exhaustion:
- **Goal predicate** — task checker passes (test green, file exists, user confirms).
- **No-progress detector** — last k steps produced no state change → force replan or
  abort (loop detection; `../Harness-Engineering/Control-Loops.md`).
- **Step/token budget** — hard cap (cost control); the *right* cap is the
  operating question — hand-computable: at 252k tokens/30 steps (240k in + 12k
  out [E: 30×8k + 30×0.4k]) and $3/M in + $15/M out [A: illustrative 2026
  pricing], 30 steps = (240k in × $3/M) + (12k out × $15/M) = 0.240×3 + 0.012×15 =
  **$0.72 + $0.18 = $0.90** (a 50-step cap ≈ $1.50 = 50/30 × $0.90). [E: arithmetic;
  prices [A]]
- **User escalation** — ask the human at decision points (confirm-before-write).

## Context carried between steps (what a good loop preserves)
1. **Goal** — restated verbatim (or re-anchored) at each step; drift is the #1
   long-horizon failure [I].
2. **State diff** — what changed since the last observation (file diffs, test
   results) rather than re-dumping the world.
3. **Scratchpad / working memory** — facts discovered, decisions made, open
   questions. In the context window for short tasks; externalized
   (`../Context-Engineering/Agent-Memory.md`) for long ones.
4. **Failure log** — what was tried and failed (prevents re-trying; enables
   Reflexion-style critique).

## Multi-step vs multi-agent: when to spawn
Spawning a subagent = a *fresh context* running the loop on a subgoal.
Use it when: (a) the subtask's working set exceeds the parent's remaining budget;
(b) the subtask is *parallelizable*; (c) isolation is needed (noisy exploration
shouldn't pollute the parent's context).
Don't use it when: the subtask needs the parent's full context, or the
communication cost (task spec + result digest) exceeds the work saved.
[E: rule-of-thumb; quantified per-task in `Multi-Agent-Systems.md` § delegation
economics.]

## Related
`Tool-Use.md` · `Multi-Agent-Systems.md` · `../Reasoning/README.md` ·
`../Context-Engineering/Context-Compaction.md` · `../Harness-Engineering/Control-Loops.md`.

## Key Takeaways
The loop is the skeleton; the strategy is the fill. ReAct + execution-based
verification is the 2026 workhorse; search-based strategies (ToT) are reserved
for checkable problems; explicit replanning is what makes 100-step tasks
possible; and every loop needs explicit stops or it becomes a cost incident.
