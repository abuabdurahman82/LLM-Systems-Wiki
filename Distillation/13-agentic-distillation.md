# 13 — Agentic and Tool-Use Distillation
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
Agents fail differently than chat models: they must *decide* when to act, choose tools,
form valid arguments, and interpret results across many turns. Agentic distillation
transfers these behaviors by training a small student on a teacher agent's full
trajectories — plans, tool calls, observations, and reasoning between them. It is
response distillation (`06`) where the response is an *interactive behavior trace*, and
its natural evaluation is task success, not token likelihood.

## The trajectory being distilled

```
Task
 ↓
Teacher Agent
 ↓
Plan            ("I need current pricing → search")
 ↓
Tool Call       search(query="...")
 ↓
Observation     (raw results)
 ↓
Reason          ("the second result looks authoritative; extract")
 ↓
Tool Call       calculator(...) / read(url)
 ↓
Observation
 ↓
Reason + Answer
```

The student learns the *whole loop*, including the parts pure-text distillation
cannot show: when to call (trigger conditions), which tool (selection), with what
arguments (formatting), and what to do with the output (interpretation).

## Tool-use distillation

What the student must learn, per turn:

| Skill | Signal in the trace | Failure without it |
|---|---|---|
| When to call | decision points (call vs answer directly) | over-calling (slow, brittle) or under-calling (hallucinated facts) |
| Which tool | selection given the toolset | wrong-API errors |
| Arguments | schema-correct parameterization | format errors, silent failures |
| Interpretation | reasoning between observation and next action | ignoring/contradicting tool output |
| Recovery | handling errors, empty results, retries | cascading failures |

Training data = teacher trajectories formatted as the student's chat template
(function-calling format matters: train in the exact format you will serve —
OpenAI-style tool JSON, HF chat-template tool blocks, etc. [I: format-mismatch is a
top-3 failure cause in practice]).

### Where the trajectories come from
1. **Teacher agent run on task corpus** (the default): strong agent + real/executed
   environments; keep the full (observation, reaction) structure.
2. **Human-demonstration amplification:** few human demos → teacher re-demonstrates
   at scale with variations.
3. **Environment replay:** existing logs (SRE, ops, coding) become trajectories after
   PII scrubbing (→ `14`).
4. **On-policy agentic KD (2026):** student rolls out in the environment; teacher/verifier
   scores or rewrites its actions; student trains on its own states — the `10` recipe
   in tool space [Research Result: earliest deployments are RL-flavored (agent RLVR);
   teacher-scored student-rollout distillation is emerging].

### Evaluation
- **Task success rate** end-to-end (the metric that matters).
- **Step-level metrics:** tool-call validity (parse rate, schema pass), argument
  correctness, observation-use consistency, recovery rate after injected failures.
- **Efficiency:** steps per task, tokens per task, unnecessary-call rate.
- Generalization checks: held-out tools (does the student call an unseen-but-similar
  tool correctly?) and held-out environments (does it transfer across MCP servers /
  APIs?) [I: eval design consistent with `Evaluation-Engineering/Agent-Tool-Use-Evaluation.md`].

## Planning distillation
Decomposition quality is a trainable artifact: include the teacher's *plan text* (or
structured plan) as part of the target. Variants:
- **Plan-then-execute traces** (explicit plan block) — more stable for small students;
- **Implicit planning** (plan inside CoT) — matches modern reasoning-model behavior;
- **Search-strategy transfer:** trajectories that include backtracking ("that path
  failed, trying X") teach recovery, at the cost of longer traces (→ verbosity filters,
  `07`).

## Function-calling specifics
- Schema discipline: enforce the target format in data *and* at training (loss on
  argument tokens can be up-weighted [I]).
- Parallel calls, dependent calls, and cancellation are behaviors — synthesize traces
  that exercise them or the student won't have them.
- Keep the toolset *fixed within a training run*; teach tool discovery separately
  (retrieval over tool descriptions) if needed.

## Multi-agent and GUI distillation (2026 frontier)
- **Multi-agent trajectories:** teacher orchestrator + worker agents produce
  communication traces (delegation, result aggregation); distilling the *orchestrator*
  is the common ask — its value is exactly the decision-making [Research Result].
- **GUI/computer-use distillation:** trajectories of clicks/typing/screenshots from a
  strong vision-language teacher into a smaller VLM agent; pairs with
  `Multimodal/` and inherits all of this page's concerns plus grounding errors
  [Experimental: active 2025–26 research; evaluation standardization is lagging].

## Cross-links and non-duplication
- The agent runtime (how tools are wired, MCP/A2A, loops) is owned by `Agents/Tool-Use.md`
  and `Agents/Agent-Protocols.md` — this page owns *transferring the behavior into the
  weights*.
- Environment safety (executing teacher/student actions) → `Safety/README.md` sandboxing
  guidance; trajectory PII → `14` §cleaning.
- On-policy mechanics → `10`; data cleaning → `14`; eval method →
  `Evaluation-Engineering/Agent-Tool-Use-Evaluation.md`.

## Related
- `10-on-policy-distillation.md` — student-rollout training (the 2026 agentic default)
- `06-sequence-and-response-distillation.md` — the base recipe this extends
- `Agents/Tool-Use.md` — the runtime side of the behaviors being distilled
- `Agents/Multi-Agent-Systems.md` — orchestration topologies
- `Evaluation-Engineering/Agent-Tool-Use-Evaluation.md` — success-rate and step metrics

## Key Takeaways
- Agentic distillation transfers the *decision loop* — when/which/how-to-call and how to
  interpret — not just answers.
- Train in the exact serving format; schema discipline is a first-class failure mode.
- Evaluate at task level (success rate) with step-level diagnostics; hold out tools and
  environments for generalization checks.
- On-policy agentic distillation (student rolls in the environment, teacher scores) is
  the emerging 2026 pattern and inherits all of GKD/OPD's cost/infra trade-offs.
