# Agent-Workflow Graphs (systems as graphs)
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
An agent loop is already a graph: nodes = (state, decision-point), edges =
(transition on an observation). Scale that up to *multiple* agents and you get
an **agent-workflow graph** — a graph whose nodes are agents/prompts/tools and
whose edges are control-flow (who calls whom, who verifies whom, who aggregates).
The 2024–26 research thread (AFlow, GPTSwarm, LangGraph, the MAS literature in
`../Agents/Multi-Agent-Systems.md`) is: **make that graph an explicit data
structure** — inspectable, optimizable, *learnable* — instead of an implicit
property of the prompt-and-code. This page covers the topology families, the
"hand-designed vs learned" question, and the observability problem that graph
systems create.

## Why make the workflow a graph (vs. an implicit loop)
An implicit loop (prompt + code) has the topology *hidden* in the code:
1. **You can't inspect it** — "who verifies whom?" is a code-reading exercise.
2. **You can't optimize it** — you can't run MCTS over a topology you can't
   represent.
3. **You can't route around failure** — if a node fails, the "next node" is a
   code branch, not a graph edge.
Making the workflow a *graph* (nodes + edges as data) buys: **inspectability**
(you can dump the topology), **optimizability** (AFlow's MCTS over graph
mutations), and **fault-tolerance** (route around a failed node via an alternate
edge). The cost: you now have *two* things to engineer — the nodes *and* the
edges [I: synthesis].

## The topology families (from `../Agents/Multi-Agent-Systems.md`, now as graphs)
| Topology | Graph shape | Where it's used | Failure mode |
|---|---|---|---|
| **Single loop** | 1-cycle (agent↔env) | ReAct-style | drift over long horizon |
| **Orchestrator-worker** | star (1 center, N leaves) | production coding agents (subagents) | center is a bottleneck + single point of context loss |
| **Pipeline / chain** | directed path A→B→C | MetaGPT/ChatDev SOP roles | telephone-game drift (each handoff loses context) |
| **Debate / aggregation** | N leaves → 1 aggregator | Mixture-of-Agents (arXiv:2406.04692 [F]) | N× cost; identical-model agreement (circular) |
| **Verifier graph** | actor → independent verifier | the evaluator pattern (this wiki) | verifier shares the actor's blind spot if same model |
| **Workflow DAG** | general DAG | AFlow, LangGraph | the *interesting* one — see below |

## The two research directions (hand-designed vs. learned)
### Hand-designed graphs (the 2024 default)
An engineer *writes* the workflow graph: the nodes (which agents/tools) and the
edges (control flow). LangGraph is the reference framework — the developer builds
a *state graph* (nodes = functions, edges = control-flow predicates, shared
state object) [F: LangChain/LangGraph docs]. GPTSwarm (arXiv:2402.16823 [F])
frames agents as *optimizable graphs* but still starts from a hand-designed
topology and does local edge-weight optimization.
**Strength:** explicit, reviewable, auditable. **Limit:** the topology is a
*guess*; you can't know the optimal graph for a new task without trying it.

### Learned graphs (the 2024–26 frontier)
**AFlow** (arXiv:2410.10762 [F]) — *Automating Agentic Workflow Generation*:
the workflow graph (nodes = LLM calls / tools, edges = control flow) is a
*search space*, and AFlow runs **MCTS** over graph *mutations* (add/remove/reorder
nodes/edges) scored by a task reward, *learning* a workflow that outperforms
hand-designed baselines on its benchmark tasks. The headline claim [F: abstract]:
*automatically discovered* workflows can beat *human-designed* ones on certain
reasoning tasks.
**The open questions [I: the research agenda, not settled]:**
- **Generalization:** does a learned graph for task A transfer to task B?
  (AFlow's graphs are *per-task-family*; cross-task transfer is unproven.)
- **Stability:** MCTS over graphs is expensive (each mutation = run the whole
  workflow = N LLM calls); the search cost can exceed the task cost [I].
- **Interpretability:** a learned graph is a *black box* — you can execute it,
  but "why this edge?" is hard to audit (the safety/observability problem below).
- **The ceiling:** learned graphs optimize *the topology*; they don't fix the
  *node quality* (a bad agent-node in a great graph is still bad). The model
  `../Harness-Engineering/Model-vs-Harness.md` factorizes: topology is one
  factor, node capability another.

## The shared state question (the graph's hidden hard part)
A workflow graph is not just nodes+edges — it's a **state machine over a shared
context**. Two agents in the graph must agree on *what the current state is*:
- **Explicit state object** (LangGraph's shared state) — the state is a
  first-class data structure passed along edges; each node reads/writes it.
  The *contract* (what fields exist, who may write what) is the edge's
  *payload contract* (`../Harness-Engineering/Harness-Anatomy.md` § delegation).
- **Context isolation** — the reason to *use* a graph (vs one big agent) is that
  each node gets a *narrow* view of the state (its own subtask), which is the
  context-isolation benefit from
  `../Agents/Multi-Agent-Systems.md` § delegation economics.
- **The join problem** — when two branches recombine (GoT-style, or
  orchestrator merging subagent results), the *merge* is where contradictions
  surface (two subagents concluded different things). The graph needs a
  *reconciliation node*, not just an edge (`../Agents/Coding-Agents.md`
  § merge-conflict pattern).

## Observability: the graph makes tracing *essential* (not optional)
A single agent's trace is a line; a workflow graph's execution is a *tree/DAG of
traces*. The observability requirements scale up:
1. **Per-node accounting** — tokens, latency, cost *per node*, not just per-run
   (`../Harness-Engineering/Harness-Anatomy.md` § observability contract).
2. **Edge-level logging** — *what* passed across each edge (the state payload,
   not just "edge fired"). A debug question is usually "what did node B receive
   from node A?" — the edge payload is the answer.
3. **Replay** — the whole DAG execution must be replayable (deterministic given
   the same seed/state), or you can't A/B a topology change.
4. **The "which node failed" problem** — when the final answer is wrong, *credit
   assignment* across the graph is hard (the `../Agents/Agent-Evaluation.md`
   § trajectory-scoring problem, now with a graph structure). An
   *agent-as-judge* (arXiv:2410.10934 [F]) scores the trajectory; over a graph,
   it scores *per node* and the *edge handoffs*.
**The design rule [I]:** a workflow graph without per-node + per-edge observability
is a black box you can't debug, can't cost-attribute, and can't audit for safety.
Observability is a *first-class node property*, not an afterthought.

## MCP/A2A and the graph (the interop layer as edges)
The interop protocols (`../Agents/Agent-Protocols.md`) are the *edge* layer of
the graph:
- **MCP edges** — agent-node → tool-node (intra-organization; the tool is a
  server).
- **A2A edges** — agent-node → agent-node (inter-agent, cross-organization; the
  "other node" hides its internals behind an Agent Card).
So a production agent system's *full* graph = its internal workflow graph
(AFlow/LangGraph-style) **plus** its MCP edges (tools) **plus** its A2A edges
(peer agents). The topology question generalizes: *what is the right shape for
the internal graph, given the external tool/peer edges you already have?* [I]

## When a workflow graph pays off (the decision, [I] — evidence-informed)
- **Pays:** multi-stage tasks with *distinct* subtasks (each stage is a node),
  long horizons (context isolation matters), tasks where a *specific stage* is
  expensive (route that node to the frontier model, the rest to cheap —
  `../Harness-Engineering/Control-Loops.md` § routing), and *verification-heavy*
  flows (actor → verifier edges).
- **Doesn't pay:** single-context tasks (one agent is cheaper and has the full
  state), chatty topologies (edge traffic > work), or latency-bound paths (each
  edge adds 4–20 s — `../Agents/Tool-Use.md` § latency).
- **The learned-vs-hand question** [I]: hand-design when you *understand* the
  task's structure (a known pipeline); *learn* (AFlow-style) when the task is
  new, the structure is unknown, and you can afford the search cost. Default to
  hand-designed + observability; reach for learned graphs when the hand-designed
  one's failure mode is *clearly* a topology problem (not a node-quality problem).

## Related
`../Agents/Multi-Agent-Systems.md` (the MAS topologies as the graph's shapes) ·
`../Agents/Agent-Protocols.md` (MCP/A2A as the edge layer) ·
`../Agents/Agent-Loops-and-Reasoning-Strategies.md` (the single-node loop) ·
`../Agents/Agent-Evaluation.md` (trajectory scoring over graph executions) ·
`../Harness-Engineering/Harness-Anatomy.md` § observability.

## Key Takeaways
An agent system *is* a graph: nodes = agents/tools, edges = control flow +
state handoffs. Making it an *explicit* graph buys inspectability,
optimizability (AFlow's MCTS over topologies), and fault-tolerance — at the cost
of engineering the edges, not just the nodes. The 2026 split: **hand-design when
you understand the structure; learn when you don't and can afford the search.**
And because a graph execution is a DAG of traces, **observability (per-node +
per-edge accounting + replay) is mandatory**, not optional.
