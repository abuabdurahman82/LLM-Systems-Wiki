# Multi-Agent Systems
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
A multi-agent system (MAS) replaces one agent loop with several coordinated loops:
role-specialized agents, orchestrator/worker topologies, and debate/aggregation
schemes. MAS is a *context* and *capability* strategy — each agent gets a fresh,
narrow context — and a *coordination* cost center. The open 2026 question is when
the second agent's capability exceeds its communication + duplication cost [I].

## The topologies
```
single agent            orchestrator-worker         peer pipeline        debate
    [agent]          [orchestrator]→[worker]×N   [A]→[B]→[C]→[aggregator]  [A]↔[B] (N rounds)
                       (task split, results merged) (chained roles)       (argue, then aggregate)
```
1. **Orchestrator-worker** (the production default): a router/planner decomposes,
   workers execute subtasks in *fresh contexts*, the orchestrator integrates.
   This is how production coding agents parallelize (e.g., "explore this module"
   subagents) and how `../Agents/README.md` describes delegation.
2. **Chained roles** (MetaGPT, ChatDev): fixed pipeline of roles
   (PM → architect → engineer → reviewer), each role = a prompt + context
   contract. [F: arXiv:2308.00352, arXiv:2307.07924] The "SOP as prompts"
   pattern; the chain length is the context-isolation budget.
3. **Debate / multi-agent deliberation** (Du et al. arXiv:2305.14325 [F];
   Mixture-of-Agents arXiv:2406.04692 [F]): N agents produce, argue, aggregate.
   MoA's central empirical claim: layered aggregation of heterogeneous agents
   can beat the single best constituent agent on some reasoning tasks [F:
   abstract] — with the caveat that cost scales linearly with N and the gain
   is task-dependent [I].
4. **Graph-shaped workflows** (AFlow arXiv:2410.10762 [F], GPTSwarm
   arXiv:2402.16823 [F]): the topology itself is a data structure — nodes are
   agents/prompts/tools, edges are control flow; AFlow *learns* the graph via
   MCTS. See `../Graph-Engineering/Agent-Workflow-Graphs.md` — the MAS
   literature and the graph-engineering literature converge here.

## Frameworks (the 2024–2026 landscape)
| Framework | Org | Model | Notes |
|---|---|---|---|
| AutoGen | Microsoft (arXiv:2308.08155 [F]) | conversation of agents | composable, human-in-the-loop patterns |
| MetaGPT | (arXiv:2308.00352 [F]) | SOP pipeline | software-company roles |
| ChatDev | (arXiv:2307.07924 [F]) | chat-chain waterfall | dev-communication simulation |
| CrewAI | open | role+task crews | production-adjacent |
| LangGraph | LangChain | explicit state graph | the "MAS as graph" line (see Graph-Engineering) |
| OpenAI Agents SDK | OpenAI | handoffs + guardrails | successor to Swarm |
| OpenHands | (arXiv:2407.16741 [F]) | coding-agent platform | env + agent + runtime |

[F: repos/docs; capability claims are vendor-reported where noted.]

## Delegation economics (hand-computable)
When is a subagent worth it? The parent spends tokens on (a) writing the task spec
S, (b) reading the result digest R; the subagent spends its own tokens T_sub on a
*clean context*. Delegation wins iff the subagent's clean-context accuracy gain
g × value(task) exceeds (S + R + T_sub) × price + integration failure risk [I —
the framework; the inputs are measured per-task].
Concretely [E: arithmetic]: if the parent's context is 60k of 128k used and the
subtask needs 40k of exploration, running in-parent costs ~40k extra input tokens
(at $3/M ≈ $0.12) *plus* accuracy degradation from the polluted context
(`../Context-Engineering/Lost-in-the-Middle-and-Long-Context-Reality.md`); a
subagent costs spec+digest ~4k + its run ~40k (at $3/M in ≈ $0.12, similar $,
*plus* a cold start, *minus* the pollution). The decision is rarely about $ —
it's about **context isolation** [I: this is the dominant real-world reason].

## When multi-agent helps (evidence-based)
- **Parallelizable subtasks** — N independent explorations (repo search, data
  collection): near-linear speedup, no coordination tax. [I: engineering consensus]
- **Role specialization with distinct expertise** — e.g. security reviewer +
  correctness reviewer with different prompts/checkers; beats one generalist on
  audit-style tasks [I: consistent with agent-benchmark practice].
- **Debate on checkable problems** — MoA-style gains on math/reasoning
  [F: arXiv:2406.04692]; smaller or negative on open-ended generation [I].
- **Verification** — an *independent* verifier (different model/config) catches
  errors the actor's self-check misses; this is the evaluator pattern this very
  wiki uses (`../Evaluation/`).
- **When it hurts:** single-context tasks (the subtask needs the parent's state),
  chatty topologies (message traffic > work), and cost-sensitive latency-bound
  paths (each hop adds 4–20 s — see `Tool-Use.md` § latency).

## Failure modes specific to MAS
1. **Telephone-game drift** — each handoff loses context; the final agent works
   from a lossy spec. Mitigate: structured contracts, artifacts (files) over
   messages.
2. **Coordination overhead** — orchestrator token cost scales with N × message
   frequency; "chatty" MAS burns budget on talk. [I]
3. **Circular reasoning** — agents with the same model agree with each other;
   debate with identical models ≈ sampling the same errors N times. Use
   *different* models/configs for real debate [I].
4. **Credit-assignment blindness** — when the team fails, which agent was at
   fault? (Evaluation problem — `Agent-Evaluation.md` § trajectory scoring.)
5. **Compounding across boundaries** — an interface contract error propagates
   invisibly; the failure looks like "model quality" but is plumbing.

## Related
`Agent-Loops-and-Reasoning-Strategies.md` · `Agent-Evaluation.md` ·
`../Graph-Engineering/Agent-Workflow-Graphs.md` · `../Harness-Engineering/Model-vs-Harness.md`.

## Key Takeaways
Multi-agent = context isolation + specialization − coordination tax. Use it for
parallel work, role expertise, and independent verification; avoid it for
single-context, chatty, or cost-bound tasks. [I] The 2026 production default is
orchestrator-worker with file-based handoffs, not chatty peer networks.
