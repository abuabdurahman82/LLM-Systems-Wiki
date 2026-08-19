# Reasoning Graphs (reasoning as graph search)
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
A token sequence generates *one path* through a solution space; **reasoning as
graph search** explicitly builds the *space* — a graph whose nodes are partial
solutions (thoughts, states, hypotheses) and whose edges are transitions (extend,
revise, combine) — and then *searches* it: branch, evaluate, prune, backtrack.
This is the computation layer of graph engineering. The family: **Tree-of-Thoughts
(ToT)**, **Graph-of-Thoughts (GoT)**, and **Think-on-Graph** (reasoning *over* an
external knowledge graph), plus the 2024–26 shift of this pattern *inside* the
forward pass (test-time compute, RLVR-trained reasoning).

## Why graph search beats one-shot reasoning (the structural argument)
One-shot CoT (arXiv:2201.11903 [F]) commits to a path on the first draw; it
can't *see* an alternative it didn't generate, can't *evaluate* a partial
solution before committing, and can't *backtrack*. Graph search buys three
capabilities at the cost of extra model calls [I: synthesis]:
1. **Branching** — generate k candidate next-states instead of 1.
2. **Evaluation** — score each partial state (value function = another LLM call
   or a checker) *before* committing.
3. **Backtracking / recombination** — prune dead branches; combine sub-solutions
   from different branches (the "graph" in GoT, vs the "tree" in ToT).
**The cost** [E: arithmetic]: a search tree with branching factor b, depth d has
≈ (b^d − 1)/(b − 1) nodes (b=3, d=4 → 40 nodes [E: (81−1)/2 = 40]); each node
costs an *expansion* call and most cost a separate *evaluation* call, so a full
tree is ≈ 2× the node count ≈ **~80 LLM calls** [E: 40 expansions + 39–40
evaluations] — vs 1 call for one-shot. The entire design space
is *where to spend those calls* (the budget question,
`../Agents/Agent-Loops-and-Reasoning-Strategies.md` § strategy families).

## Tree-of-Thoughts (the canonical form)
ToT (Yao et al. 2023, arXiv:2305.10601 [F]):
```
Thought = a partial solution;  Tree = thoughts + parent links
Loop:  expand (b new thoughts from current frontier)
       → evaluate each (LLM value estimate + self-consistency)
       → select: best-first (UCB/BFS/DFS variants)
       → backtrack if all branches look dead
       → terminate on goal test
```
- **Where it wins [F: paper's reported tasks]:** Game of 24 (4% CoT → 74%
  ToT [F: abstract]), creative constrained writing, and mini crosswords —
  tasks with a *checkable intermediate state* and a *searchable* space.
- **Where it doesn't [I]:** tasks where the space is unbounded/ill-defined
  (open-ended QA) — the value function becomes garbage and the search is just
  expensive sampling. The 2024+ refinement [I]: ToT pays off where a *cheap
  oracle* exists for the intermediate states; without one, it tends to
  degenerate to self-consistency with extra steps.

## Graph-of-Thoughts (the generalization)
GoT (Besta et al. 2023, arXiv:2308.09687 [F]): a *general programming* framework
where thoughts form a **DAG/Graph** manipulated by a small set of operators —
**generate, branch, merge, aggregate, score, keep** [F: paper] — i.e. ToT plus:
- **Recombination** (merge two partial solutions from different branches),
- **Iteration** (cycle back to an earlier thought with new information),
- **Global aggregation** (a thought that sees the whole graph).
- **The claim [F: paper]:** graph-structured reasoning generalizes
  tree-structured reasoning (a tree is a special case of the graph), and on their
  benchmark tasks (sorting, single-source shortest path, graph problems) the
  graph operators give measurable gains over ToT-style trees.
- **The cost [I]:** the operators are *more model calls* (each op = 1+ LLM
  invocation), and the graph is built/adapted per task — so GoT is the "power
  user" mode: highest capability, highest cost. Production systems rarely run
  full GoT; they run *ToT-lite* (branch+evaluate+best-first) or move the search
  *inside* the model (below).

## Think-on-Graph (reasoning *over* an external KG)
Think-on-Graph (ToG) is a different "graph": the graph is a **knowledge graph
that exists independently**, and the LLM *navigates* it.
- **ToG 2.0** (arXiv:2407.10805 [F]): the LLM agent issues *graph queries*
  (retrieving subgraphs around its current reasoning state), reasons over the
  returned subgraphs in context, and continues — a *deep & faithful* pattern:
  the reasoning is *grounded in the KG's structure*, reducing hallucination of
  the multi-hop connections.
- **ToG 3.0** (arXiv:2509.21710 [F]): *efficient & adaptive* — wider/deeper
  navigation with early-stopping; the agent decides *how much* of the graph to
  pull per step (a context-budget decision — `../Context-Engineering/
  Context-Budget.md`).
- **The principle [I]:** the KG is the *world model* and the LLM is the *agent*;
  each step is "query the world → reason → act". This is *exactly* the ReAct
  loop (`../Agents/Agent-Loops-and-Reasoning-Strategies.md`) with the "world"
  being a graph and the "action" being a subgraph query. The graph gives the
  reasoning *faithfulness* (the edges are extracted, not imagined) and the LLM
  gives it *flexibility* (the search policy is learned, not hand-coded).

## The 2024–26 shift: the search moves *inside* the forward pass
The external search pattern is being *absorbed*:
1. **Test-time compute scaling** — reasoning models (o1/R1-class, RLVR-trained,
   `../Post-Training/Alignment-RLHF.md`) reportedly do something ToT-*like*
   internally: hundreds-to-thousands of reasoning tokens that branch/prune
   *within one generation* [I: the internal-search analogy; exact mechanism not
   published]. The model *is*
   the search; you pay in tokens, not in separate API calls.
2. **RLVR as the selector** — training with a *verifiable reward* (a checker on
   the final answer) selects for trajectories that effectively *search well*;
   the search policy is learned, not prompted.
3. **What remains external [I]:** the search stays *outside* the model when
   (a) the state space is *external* (a KG, a code repo, a physical env — you
   can't put it all in the forward pass), or (b) the evaluation requires a
   *tool* (a compiler, a simulator, a database) — ToG/agent-loop patterns.
**The 2026 division of labor [I]:** *intrinsic* reasoning search → inside the
model (test-time compute); *extrinsic* search (over external structure/tools) →
graph/agent harness. This is the same absorption pattern as
`../Harness-Engineering/Model-vs-Harness.md` § absorption effect, applied to
reasoning.

## The evaluation question (how do you know the search helped?)
- **The oracle problem:** ToT/GoT need a *value function*; its quality caps the
  search's quality. A bad value function makes the search *worse* than one-shot
  (it prunes the good branch). The 2026 practice: use a *different, stronger*
  model as the value function, or a *checker* (code execution, a theorem prover,
  a unit test) when one exists [I: consistent with the independent-evaluator
  pattern this wiki uses].
- **The cost-normalized comparison [I]:** "search beats one-shot" is only true
  *at equal cost* or *equal accuracy* — a ToT that needs 40 calls to match a
  single strong call is a loss in production. Report *accuracy-per-token*
  (`../Agents/Agent-Evaluation.md` § cost axis).
- **The benchmark pin:** ToT/GoT papers report on *puzzle-class* tasks
  (checkable states). Transfer to open-ended tasks is not established — the
  wiki's standing rule: no declared winner without a task-pinned benchmark.

## Related
`Knowledge-Graphs-and-GraphRAG.md` (the KGs ToG navigates) ·
`GNN-Basics.md` (the model layer; the WL limit that motivated LLM hybrids) ·
`../Agents/Agent-Loops-and-Reasoning-Strategies.md` (ToT in the loop taxonomy) ·
`../Reasoning/README.md` (CoT/CoT-variants; test-time compute) ·
`../Post-Training/Alignment-RLHF.md` (RLVR — the learned search).

## Key Takeaways
Reasoning-as-graph-search buys **branching, evaluation, backtracking** at the
cost of **many model calls**. ToT = tree; GoT = graph (merge/recombine/iterate);
Think-on-Graph = navigating an *external* KG. The 2026 state: *intrinsic* search
is absorbed into the forward pass (test-time compute + RLVR); *extrinsic* search
over external structure/tools remains the domain of the graph/agent harness.
Judge any search method by **accuracy-per-token with a pinned task** — not by
capability alone.
