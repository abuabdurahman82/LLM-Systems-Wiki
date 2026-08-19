# Agent Evaluation (benchmarks, harness effects, agent-as-judge, cost)
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
Evaluating an agent is *not* the same as evaluating a model: the unit of
measurement is a **trajectory** (a sequence of thoughts, tool calls, and
observations over a horizon), not a single output. This changes everything — the
benchmark must be an *environment* with a verifiable final state, the scorer must
attribute credit across steps, and the number that matters is a **task success
rate** (often heavily horizon- and cost-controlled). `../Evaluation/README.md`
covers model benchmarks (MMLU, etc.); this page covers the agent-specific layer.

## Why agent evaluation is harder
1. **Horizon** — a task is 5–200+ steps; a model benchmark is 1 step.
2. **Statefulness** — the environment changes; you must reset between runs or
   results are order-dependent.
3. **Stochasticity** — same task, different run, different result; you need many
   seeds, and the *variance* is the story (see § reporting).
4. **Cost** — a single trajectory can be 100k+ tokens; benchmarks are expensive,
   so sample sizes are small → wide confidence intervals.
5. **Credit assignment** — when a task fails at step 80, *which* step caused it?

## The benchmark families
**Web / browsing:** WebArena (arXiv:2307.13854 [F], self-hosted websites),
Mind2Web (arXiv:2306.06070 [F], offline web actions), WebVoyager-class online
suites. Measure navigation + task completion.

**OS / computer use:** OSWorld (arXiv:2404.07972 [F], real-VM open-ended tasks);
the 2024-10 Anthropic computer-use public beta (arXiv: n/a — [F:
anthropic.com/news/3-5-models-and-computer-use]) is the de-facto production
reference [I: state-of-the-practice judgment].
These measure screenshot-in → action-out grounding.

**Tool + user interaction:** tau-bench (Sierra, 2024 [F: sierra.ai]) — a *user
is simulated* (by another LLM), and the agent must follow a domain *policy* while
the user pressures it; the headline metric is a **hallucination rate** (agent
invents API fields / violates policy under pressure). Distinct from other
benchmarks because the *adversary is conversational*, not environmental.

**General assistant:** GAIA (arXiv:2311.12983 [F]) — "simple" human tasks
(browse + reason + multi-step) with a single final answer; at publication,
humans 92% vs GPT-4+plugins 15% [F: abstract] — the gap between human and
agent on *simple* tasks is the sharpest picture of the agent capability
frontier (and the benchmark has stayed hard: frontier 2024–25 systems improved
but the human gap persisted [I]).

**Long-horizon / consequential:** TheAgentCompany (arXiv:2412.14161 [F]) —
multi-hour business/IT tasks (design + code + deploy) with real consequences;
Terminal-Bench (arXiv:2601.11868 [F]) — hard, realistic command-line tasks in
containers. These push horizon to 100+ steps.

**Coding:** SWE-bench / Verified / SWE-Gym / Commit0 / SWE-agent-ACI —
covered in `Coding-Agents.md` § benchmark lineage.

**Leaderboard infra:** HAL (arXiv:2510.11977 [F]) — a cross-task, cross-harness
leaderboard arguing the field lacks a stable comparison substrate.

## The harness-effect problem (a benchmark number is not a model number)
The *same model* run under two different harnesses (tools, prompts, memory,
retries) can differ by **10–30+ points** on agentic evals [I: consistent across
SWE-bench-class work; see `../Harness-Engineering/Model-vs-Harness.md` for the
dedicated treatment and a hand-computable example]. Consequences:
- **Always report the harness** — "model X scores Y on Z-benchmark" is
  meaningless without the scaffold spec (tools, ACI, prompt, retries, memory).
- **Head-to-head must hold the harness fixed** to isolate the model, or
  hold the model fixed to isolate the harness. Most public comparisons
  conflate the two [I].
- **A number can be "the model" or "the model+harness"** — say which.

## Reporting an agent result (the minimum honest spec)
To make an agent benchmark number reproducible and comparable, pin [I: checklist
derived from `../Inference` eval hygiene]:
1. **Model** + exact checkpoint/quant + sampling (temp, top-p, seed count).
2. **Harness** — tool set, ACI, system prompt, retry policy, step budget, memory.
3. **Environment** — version, seed/reset protocol, sandbox config.
4. **Metric** — task success (binary), partial credit?, cost-controlled?
5. **Statistical treatment** — #runs, mean ± CI (bootstrap), not just mean.
6. **Cost/latency** — total tokens, wall-clock, $/task.
Anything unpinned is a hole an independent evaluator will list
(`../Inference/Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md` § benchmark
fairness applies the same logic to serving evals).

## Agent-as-a-judge (scoring trajectories)
**Agent-as-a-Judge** (arXiv:2410.10934 [F]) — an LLM (itself often an agent)
scores another agent's *trajectory*, not just its final answer. Rationale:
- Many agent tasks have **no clean execution oracle** (open-ended research,
  browsing, design). The judge reads the trace and grades process + outcome.
- It can catch *process failures* (unnecessary loops, context bloat, privilege
  overreach) that a final-answer-only scorer misses.
**Caveats [I]:**
- A judge with the same model as the agent shares its blind spots — use a
  *different* model/config for independence (the evaluator pattern this wiki
  uses: main model + independent evaluator).
- Judge reliability is itself benchmarked (judge-consistency, agreement with
  human labels); treat agent-as-judge scores as *noisy proxies* until calibrated.

## The independent-verifier pattern (this wiki's own pipeline)
This encyclopedia applies the strongest version of agent evaluation to
*itself*: every major technical page is (1) drafted, (2) machine-verified for
arithmetic, (3) sent to an **independent evaluator** (a second LLM endpoint),
(4) the main author *re-verifies every evaluator flag before applying it*,
(5) revised, (6) delivered with the adjudication table visible. The principle
generalizes: **the single highest-value verification in an agent system is an
independent check by a different model/config**, because self-verification
shares the actor's errors. [I: this is the meta-lesson the whole wiki is built
on.]

## Cost as a first-class evaluation axis
An agent result without a cost/latency number is incomplete. Reporting
**success-per-dollar** (or success-at-latency-budget) is the correct
comparative axis, because a 90%-success agent at $10/task can be worse value
than an 85% agent at $1/task depending on task volume. Hand-computable
example: 1000 tasks/day, agent A = 80% @ $0.50/attempt vs agent B = 85% @
$2.00/attempt → A resolves 800 tasks for $500/day; B resolves 850 for
$2000/day. B delivers 50 more tasks *per day*, but A is **3.8× cheaper per
resolved task** ($0.63 vs $2.35) and delivers 3.8× more resolved tasks per
$1000 (1600 vs 425) [E: arithmetic].
[Economics: `Tool-Use.md` § latency economics; `Coding-Agents.md` § economics.]

## Failure modes in *evaluation itself*
1. **Benchmark contamination / memorization** — the model may have seen the
   test (SWE-bench Verified analysis, arXiv:2512.10218 [F]). Mitigate:
   held-out, recently-added tasks; canary strings.
2. **Order/seed dependence** — results vary with run order; report seed stats.
3. **Harness conflation** — the #1 silent error (above).
4. **Judge self-preference** — LLM judges favor their own model family's
   outputs; calibrate against human labels.
5. **Single-point estimates** — one run per task; the CI is ignored. Always
   report variance.

## Related
`Coding-Agents.md` · `Multi-Agent-Systems.md` · `../Evaluation/README.md` ·
`../Harness-Engineering/Model-vs-Harness.md` · `../Safety/README.md` (AgentHarm
arXiv:2410.09024 [F] for harmful-behavior measurement).

## Key Takeaways
The unit is the trajectory, not the token. Pin the harness or the number is
meaningless. Report variance + cost, not just mean success. And the strongest
verification is always *independent* — a different model, a different config,
never the actor grading itself.
