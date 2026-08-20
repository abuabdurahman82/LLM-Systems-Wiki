# Agent and Tool-Use Evaluation: trajectories, environments, cost
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
The unit of measurement for an agent is the *trajectory* — a sequence of
thoughts, tool calls, and observations over a horizon — not a single output,
and the scorer must be either an environment probe or another agent
(Agent-as-a-Judge, arXiv:2410.10934 [F]). A benchmark must be a stateful,
resettable environment with a verifiable final state; the best-practices work
(arXiv:2507.02825 [F]) makes this explicit. Benchmark families span web,
computer use, tool-plus-simulated-user interaction, general assistants, and
long-horizon consequential tasks. The same model on a different scaffold can
move 10-30+ points on agentic sets, so the harness is a first-order variable.
Honest reporting requires a 6-item spec (model+checkpoint, harness,
environment version, metric, #runs+CI, cost), and cost is a first-class axis:
report success-per-dollar, not just success rate.

## Unit of measurement: the trajectory
An agent evaluation measures a **trajectory**: a sequence of
thought / tool-call / observation steps over a task horizon, ending in a
final state [F: arXiv:2410.10934]. This changes every part of the eval stack
relative to single-shot model evals [I]:

- **Scorer** — the final state may not be a text answer; it can be a VM, a
  database, a filesystem. Scoring requires a programmatic probe of the final
  state or an **agent-as-a-judge** that inspects the trajectory (trajectory
  scoring, not just final-answer matching) [F: 2410.10934].
- **Credit assignment** — a task that fails at step 80 of 100 did not fail
  "at step 80"; some earlier step committed the failure. Attributing which
  step caused the failure is open, and it is the only way to turn a failure
  log into training signal [I].
- **Judge independence** — an agent-as-a-judge shares the failure modes of
  the agents it judges (same family, same blind spots). Use a judge from a
  different family or a different paradigm where possible, and validate the
  judge against a human-audited trajectory sample [I; F: 2410.10934].

## The environment requirement
A serious agentic benchmark must be an **environment**, not a dataset:
stateful (actions change the world), resettable (each run starts from the
same initial state, or results are order-dependent), and verifiable (the
final state can be checked programmatically or by judge) [F:
arXiv:2507.02825]. Benchmarks that skip resettable state silently measure
*order effects* as much as capability [I]. Environment versioning is part of
the result: a website redesign or a package update between runs changes the
task under everyone's feet.

## Benchmark families
| Family | Benchmarks | Distinct signal |
|---|---|---|
| Web / browsing | WebArena (arXiv:2307.13854 [F]), Mind2Web (arXiv:2306.06070 [F]), BrowseComp (arXiv:2504.12516 [F]), BEARCUBS (arXiv:2503.07919 [F]) | navigation + multi-step web reasoning; BrowseComp adds long research-style queries [I] |
| Computer use | OSWorld (arXiv:2404.07972 [F]) | open-ended tasks in a real VM; screenshot-in to action-out grounding |
| Tool + user | tau-bench (arXiv:2406.12045 [F]) | simulated user plus domain policy; headline metric is **hallucination rate** (invented API fields, policy violations under conversational pressure) [I: metric interpretation] |
| General assistant | GAIA (arXiv:2311.12983 [F]) | multi-step "simple" tasks with a single final answer; breadth of real-assistant skills |
| Long-horizon consequential | TheAgentCompany (arXiv:2412.14161 [F]), Terminal-Bench (arXiv:2601.11868 [F]) | sustained execution with real consequences; 100+ step horizons [I] |

tau-bench is the odd one out: the adversary is a *simulated user* (another
LLM) that pressures the agent while a domain policy constrains it; the signal
is hallucination rate rather than task success [I]. BrowseComp targets long,
research-style browsing where the answer requires synthesis across many
pages [I].

## The harness effect and leaderboard infrastructure
**Harness effect.** Same model, different scaffold (prompts, tool schemas,
observation formatting, retry logic): 10-30+ point deltas on agentic sets
[I]. The (model, harness) pair is the unit of comparison;
`../Harness-Engineering/Model-vs-Harness.md` carries the decomposition and
`../Agents/Agent-Evaluation.md` the benchmark side.

**Leaderboard infrastructure.** HAL (arXiv:2510.11977 [F]) argues the field
lacks the shared evaluation infrastructure that model evals got —
reproducible runs, pinned environments, comparable numbers across labs [I:
reading of the paper's contribution].

**How many tasks are enough?** A replay analysis of public LLM agent
benchmarks (arXiv:2607.12338 [F]) shows the public task suites are small
enough that a handful of tasks dominate model rankings — on small n,
re-running the same tasks moves the leaderboard. Treat single-digit task
suites as directional, and demand #runs plus CI [I].

## Minimum honest reporting spec
Six items, mirroring the section-wide protocol (`Evaluation-Fundamentals.md`):

| # | Item | Why it matters |
|---|---|---|
| 1 | Model + checkpoint (date/revision) | capability moves fast; "frontier-class" is not a model |
| 2 | Harness version (scaffold, prompts, tools) | the harness is a first-order variable [I] |
| 3 | Environment version | stateful worlds change under you [I] |
| 4 | Metric + horizon (success rate at what step budget) | horizon changes the number [I] |
| 5 | Number of runs + CI | small-n suites have wide confidence intervals [I] |
| 6 | Cost per task (tokens, $, wall-clock) | cost is a first-class axis (below) |

A number missing any of these is a rumor, not a result [I].

## Cost as a first-class axis
Success rate without cost is misleading: the "better" agent may be several
times more expensive per resolved task. The operational metric is **cost per
resolved task** = (cost per attempt) / (success rate) [I].

Hand example [E]: agent A succeeds 80% at $0.50/attempt; agent B succeeds
85% at $2.00/attempt.
- A: $0.50 / 0.80 = **$0.625 per resolved task**.
- B: $2.00 / 0.85 = **$2.3529 per resolved task** [E: 2.00/0.85 = 2.35294...]
- Ratio: 2.3529 / 0.625 = **3.76x** [E: 2.3529/0.625 = 3.7647]

B is 5 points more accurate but 3.76x more expensive per success; whether
that is a good trade depends on the cost of a failure, and a capability
report should show both numbers side by side [I].

## Failure modes of agent evals
- **Contamination** — tasks leaking into training data; for SWE-style
  suites, some models test memory rather than ability [F: 2512.10218; see
  `Benchmark-Contamination.md`].
- **Order / seed dependence** — without resettable state or enough seeds,
  the number measures the random draw, not the model [I].
- **Harness conflation** — attributing a scaffold improvement to the model,
  or vice versa [I].
- **Single-point estimates** — one run per task, no CI; on small-n suites
  the point estimate is inside the noise [I; F: 2607.12338].
- **Judge dependence** — agent-as-a-judge results are only as good as the
  judge; re-run with an independent judge before trusting a delta [I].

## Related
- `../Agents/Agent-Evaluation.md`
- `../Agents/Coding-Agents.md`
- `../Agents/Tool-Use.md`
- `../Harness-Engineering/Model-vs-Harness.md`
- `LLM-as-a-Judge.md`

## Key Takeaways
The unit of agent evaluation is the trajectory, which forces environment-
based, stateful, resettable, verifiable benchmarks and agent-or-probe
scorers. The harness is a first-order variable (10-30+ points), so report the
full 6-item spec, never a bare success rate. Cost per resolved task is a
first-class axis alongside accuracy, and small public task suites mean
single-point estimates are often noise.
