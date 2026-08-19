# Agentic AI Evolution (2022 → 2026)
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
Between 2022 and 2026, "the LLM" went from *a thing that answers in one forward
pass* to *a thing that runs a multi-hour task*. The arc had five distinct phases,
each driven by a different technical unlock, each creating new failure surfaces that
the next phase's research had to absorb.

## Phase 1 — In-context reasoning (2022)
- **Chain-of-Thought** (Wei et al. 2022, arXiv:2201.11903 [F]): asking the model to
  emit intermediate steps before the answer unlocked multi-step arithmetic/relational
  reasoning. Key finding: the trick only worked at a certain model scale — reasoning
  was a *scale-gated emergent capability*, not a prompting trick. [F]
- **Self-consistency** (Wang et al. 2022, arXiv:2203.11171 [F]; *different
  paper* from Wei et al. CoT): sample many CoTs, majority-vote the final answer
  — the first 'test-time compute' pattern.
- Why it mattered: reasoning became an *observable artifact in the prompt stream*,
  which made the next step possible — you could now interleave thought with action.

## Phase 2 — Reasoning + acting (2022–2023)
- **ReAct** (Yao et al. 2022, arXiv:2210.03629 [F]): alternate reasoning traces and
  actions (`Thought → Action → Observation → …`) in one loop over an environment
  (HotpotQA, ALFWorld, WebShop) — the template that essentially every subsequent
  agent loop is a variant of. [I: influence-level judgment, not a claim of the paper]
  - ALFWorld (arXiv:2010.03768 [F]) and WebShop (arXiv:2207.01206 [F]) were the
    original embodied/web environments these loops were tested in.
- **Toolformer** (Schick et al. 2023, arXiv:2302.04761 [F]): the model learns *when
  and how* to call its own calculator/lookup/API tools, self-supervised.
- **Gorilla** (patil et al. 2023, arXiv:2305.15334 [F]) and **ToolLLM** (Qin et al.
  2023, arXiv:2307.16789 [F]; ToolBench benchmark): API-call precision at scale —
  the right *API*, the right *arguments*. ToolLLM's ToolBench covered 16,000+ real
  APIs [F: abstract].
- **HuggingGPT** (Shen et al. 2023, arXiv:2303.17580 [F]): LLM as controller that
  routes tasks to specialist HuggingFace models — early "LLM as orchestrator".
- **Reflexion** (Shinn et al. 2023, arXiv:2303.11366 [F]) and **Self-Refine**
  (Madaan et al. 2023, arXiv:2303.17651 [F]): the model critiques and revises its own
  trajectory/output in verbal reinforcement — the first *self-improvement loop*
  without weights changing.
- **Tree of Thoughts** (Yao et al. 2023, arXiv:2305.10601 [F]): deliberate
  tree-search over reasoning steps — reasoning as search, not one-shot generation.
- **AgentBench** (Liu et al. 2023, arXiv:2308.03688 [F]): first multi-task agent
  benchmark suite; documented the large capability gaps of that era's models.

## Phase 3 — Memory, planning, multi-agent (late 2023)
- **MemGPT** (Packer et al. 2023, arXiv:2310.08560 [F]): OS-inspired context
  management — the LLM's context window as "main memory", external storage paged in
  and out by the model itself. Direct ancestor of today's agent memory layer
  (`../Context-Engineering/Agent-Memory.md`).
- **LLM+P** (Liu et al. 2023, arXiv:2304.11477 [F]): LLM proposes, classical planner
  (PDDL) verifies/executes — hybrid symbolism that kept plans *sound* even when the
  model hallucinated.
- **Generative Agents** (Park et al. 2023, arXiv:2304.03442 [F]): 25 simulated
  townspeople with memory/reflection/planning — the memory-stream architecture
  (retrieve-reflect-plan) that persists in modern agent memory designs.
- **Voyager** (Wang et al. 2023, arXiv:2305.16291 [F]): open-ended skill-learning
  agent (Minecraft) with an auto-curriculum and a persistent skill library —
  capability *compounds* when skills are stored as reusable code.
- **Multi-agent systems**: CAMEL (arXiv:2303.17760 [F]) role-playing two-agent
  society; **MetaGPT** (Hong et al. 2023, arXiv:2308.00352 [F]) — "one software
  company" of specialized agents (PM/architect/engineer) with SOPs; ChatDev
  (Qian et al. 2023, arXiv:2307.07924 [F]) — chat-chain waterfall for software dev;
  **AutoGen** (Wu et al. 2023, arXiv:2308.08155 [F]) — composable multi-agent
  conversation framework (Microsoft). (Phase boundaries are approximate: CAMEL
  is 2023-03, MoA-type work lands in Phase 4.)
- **GAIA** (Mialon et al. 2023, arXiv:2311.12983 [F]): benchmark for *general* AI
  assistants (web browsing + multi-step reasoning, human-designed, "simple" for
  humans yet hard) — humans 92% vs GPT-4+plugins 15% at publication [F: abstract].
- **SWE-bench** (Jimenez et al. 2023, arXiv:2310.06770 [F]): real GitHub issues,
  real repos; best models at publication resolved ~1.96% of issues [F: abstract]
  — the yardstick that defines the next two phases.
- Surveys fixing the vocabulary: Wang et al. 2023
  (arXiv:2308.11432 [F]); The Rise and Potential of LLM-based Agents
  (arXiv:2309.07864 [F]).

## Phase 4 — Frontier agent capability (2024–2025)
- **Aggregation multi-agent**: **Mixture-of-Agents** (Wang et al. 2024,
  arXiv:2406.04692 [F]) — layered aggregation of agent outputs beats any single
  agent on some reasoning tasks.
- **Coding agents matured**: SWE-agent (Yang et al. 2024, arXiv:2405.15793 [F])
  introduced the *agent-computer interface* (ACI) concept — the interface layer is
  as important as the model; OpenHands (Wang et al. 2024, arXiv:2407.16741 [F]) the
  open platform; **CodeAct** (Wang et al. 2024, arXiv:2402.01030 [F]) showed
  executable code actions beat JSON actions. SWE-bench Verified
  (OpenAI, 2024-08 [F: openai.com]) filtered the set to a clean ~500-issue subset,
  becoming the de-facto headline number for coding models (e.g., o1/GPT-5-class
  models reached 40–50%+ [I: check current vendor numbers; see `Latest-Research/`]).
- **Web/computer agents scaled up**: WebArena (arXiv:2307.13854 [F]), Mind2Web
  (arXiv:2306.06070 [F]), **OSWorld** (Xie et al. 2024, arXiv:2404.07972 [F]) —
  real-OS tasks; Anthropic's computer use entered public beta with the 2024-10
  Claude 3.5 Sonnet refresh [F: anthropic.com/news/3-5-models-and-computer-use].
- **Long-horizon tool use**: **tau-bench** (Sierra, 2024 [F: sierra.ai]) —
  tool-agent-user interaction with *user simulation*, where policy constraints
  create a measurable hallucination rate (agents violate policies under user
  pressure).
- **Agent Q** (Putta et al. 2024, arXiv:2408.07199 [F]; note: its benchmark
  domain is *web navigation*, not SWE) and **SWE-Gym**
  (arXiv:2412.21139 [F]) and **Commit0** (arXiv:2412.01769 [F]): training
  environments + RL pipelines that turn multi-step agent capability into a
  *trained* skill
  rather than a prompt trick. **AgentTuning** (Liu et al. 2023, arXiv:2310.12823
  [F]) had earlier established generalized agent abilities via SFT data.
- **Memory in production**: Mem0 (arXiv:2504.19413 [F]), Zep/Graphiti temporal
  knowledge graph (arXiv:2501.13956 [F]), A-MEM (arXiv:2502.12110 [F]) — the
  agent-memory layer became a real product category
  (`../Context-Engineering/Agent-Memory.md`).
- **Workflow learning**: Agent Workflow Memory (arXiv:2409.07429 [F]) — agents
  induce reusable workflows from their own past trajectories; **AFlow**
  (arXiv:2410.10762 [F]) — MCTS over workflow graphs, *learning* agentic
  workflows instead of hand-designing them. See
  `../Graph-Engineering/Agent-Workflow-Graphs.md`.
- **Evaluation infrastructure**: TheAgentCompany (arXiv:2412.14161 [F]) —
  consequential, long-horizon business tasks; Terminal-Bench
  (arXiv:2601.11868 [F]) — hard, realistic command-line tasks; HAL
  (arXiv:2510.11977 [F]) — cross-task agent leaderboard; Agent-as-a-Judge
  (arXiv:2410.10934 [F]) — LLM judges for agent trajectories.

## Phase 5 — Absorption & protocolization (2025–2026)
- **Capability absorption**: long-horizon reliability, tool-precision, and
  planning quality are increasingly *trained into* frontier models rather than
  scaffolded around them; production harnesses correspondingly get thinner
  (fewer scaffolds, more railings). [I — direction of travel well-supported by
  vendor releases; quantification pending]
- **Interoperability standards**: **MCP** (Anthropic, 2024-11 [F:
  github.com/modelcontextprotocol — open standard, spec schema versioned
  2024-11-05 / 2025-03-26 / 2025-06-18 / 2025-11-25, verified live 2026-08-19])
  standardized tool/context wiring; **A2A** (Google/IBM, 2025-04 [F: a2aprotocol.ai])
  standardized agent-to-agent messaging. `Agent-Protocols.md`.
- **Safety at scale**: AgentHarm (arXiv:2410.09024 [F]) benchmarked harmful
  agent behaviors — safety now spans the whole loop, not just the prompt.
- **Open question**: is multi-agent *additive* or a tax? Evidence is mixed —
  MoA-type aggregation helps on reasoning tasks [F: arXiv:2406.04692], but
  multi-agent coding systems show coordination overhead that single-agent +
  strong model often beats on fixed budgets [I: consistent with community
  reports; no settled head-to-head — see `Multi-Agent-Systems.md` § when-it-helps].

## Why it happened: the three unlocks
1. **Scale-gated reasoning** (CoT) — the model could plan.
2. **Structured actions** (tool-calling APIs, then code actions, then MCP) —
   the model could act *precisely* on the world.
3. **Cheap, checkable feedback** (tests, linters, shell exit codes, human review) —
   loops could converge. SWE-bench-class work works because *every step is
   checkable*; open-ended creative tasks remain far harder because feedback is
   sparse. [I]

## The compounding-error math (why horizons are hard)
If each step of a trajectory has success probability p, a T-step task succeeds with
probability p^T (independent-step approximation):

| per-step p | 5 steps | 20 steps | 50 steps |
|---|---|---|---|
| 0.99 | 0.951 | 0.818 | 0.605 |
| 0.95 | 0.774 | 0.358 | 0.077 |
| 0.90 | 0.590 | 0.122 | 0.005 |

[E: p^T; the table values are exact powers.] Reading: at p=0.95, going from 5 to 20
steps costs 2.16× in success probability (0.774 → 0.358); at p=0.90, going from 5 to
20 costs 4.8× (0.590 → 0.122), and from 5 to 50 you lose ~99% (0.590 → 0.005). [E:
0.95^5/0.95^20 = 1/0.95^15 = 2.158; 0.9^5/0.9^20 = 1/0.9^15 = 4.857;
0.9^5/0.9^50 = 1/0.9^45 = 114.6] Two
implications: (a) *step-level* reliability engineering (good tools, checks,
retries) beats *trajectory-level* hope; (b) the model improvement that matters
most for agents is **per-step success probability p** — and note the subtle point:
"making the model smarter" *is* one way to raise p (the two are not opposites);
what the p^T math says is that whatever *mechanism* raises p (a smarter model,
better tools, checks, retries), it is amplified exponentially in horizon:

> Hand-computable version: 0.95^50 = 0.0769; 0.96^50 = 0.1299; relative gain =
> 0.1299/0.0769 = **1.69×**. A 1-point per-step gain compounds to +69% at T=50,
> and at T=200: 0.95^200 ≈ 3.51e-5 vs 0.96^200 ≈ 2.85e-4 → **8.1×**. [E: p^T,
> exact powers] So the compounding effect is real and *exponential-in-horizon* —
> short tasks don't care much; very long tasks care enormously. This is why
> long-horizon reliability training is worth so much.

## Related
`Tool-Use.md` · `Agent-Loops-and-Reasoning-Strategies.md` · `Multi-Agent-Systems.md` ·
`Coding-Agents.md` · `Agent-Evaluation.md` · `../Graph-Engineering/Agent-Workflow-Graphs.md`.

## Key Takeaways
Five phases, three unlocks, one standing constraint: multiplicative per-step
reliability. [I: the pattern generalization] Most production agent systems in
2026 are instances of "make each
step checkable, make failures recoverable, make the horizon as short as possible".
