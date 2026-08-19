# Harness Anatomy (component inventory & design contracts)
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
A harness = a model endpoint + the *system* that feeds it, acts on its outputs,
and checks the results. This page inventories the parts and — more importantly —
the **design contract** each part must satisfy, so two engineers can build
compatible harnesses and you can read any other agent system as a set of
configurable knobs. The mental model: **each component has an input contract, an
output contract, and a failure contract.** Design the contracts first; the
implementation is secondary.

## The stack (bottom-up)
```
┌────────────────────────────────────────────────────────────┐
│  OBSERVABILITY      trace, replay, cost attribution        │
├────────────────────────────────────────────────────────────┤
│  CONTROL LOOP       plan→act→observe→revise; budgets/stops
│  (Control-Loops.md)
├────────────────────────────────────────────────────────────┤
│  SUBSYSTEMS                                               │
│   Context Manager    window policy (Context-Management.md) │
│   Tool Layer         schemas, dispatch (../Agents/Tool-Use)│
│   Memory Layer       short/long-term (../Context-Engineering/Agent-Memory)│
│   Verification       checks + independent evaluator       │
│   Delegation         subagents (../Agents/Multi-Agent-Systems)│
├────────────────────────────────────────────────────────────┤
│  EFFECT LAYER       sandbox, execution (Sandboxing.md)     │
├────────────────────────────────────────────────────────────┤
│  MODEL ENDPOINT     vLLM/SGLang/hosted API                │
└────────────────────────────────────────────────────────────┘
```
Each boundary is a *seam*: you can swap any layer without touching the others.
A harness that hard-couples layers (e.g. a system prompt that assumes a specific
serving engine's tokenization) is fragile by construction [I].

## Component contracts
### 1. System prompt (the static prefix)
- **Input contract:** role, task framing, tool contract, safety rails, output
  format.
- **Output contract:** stable across steps (so prefix caching hits —
  `../Context-Engineering/Context-Budget.md`); *dynamic* parts (task spec,
  retrieved context) must come *after* it.
- **Failure contract:** a prompt regression changes *all* behavior; prompts are
  versioned like code and A/B-tested against the same task set [I].
- **Design rule:** keep it < ~5–10k tokens; every token is paid on *every* step
  without caching and taxes attention with it even with caching [I].

### 2. Tool layer
- **Input contract:** tool schema (name, args, required/optional).
- **Output contract:** structured result; errors as data with a `hint`
  (`../Agents/Tool-Use.md` § schema design).
- **Failure contract:** malformed args → bounce back the *exact* schema error
  (the model can self-recover); tool timeout → return a structured timeout, not a
  hang. Idempotent reads can be retried; writes must not be.
- **Design rule:** few, orthogonal, verb-named tools; each tool's docs are *part
  of the prompt budget* (50 tools × 300 tokens = 15k of the window before the
  user speaks [E: arithmetic]).

### 3. Context manager
- **Input contract:** per-step token budget, cacheable-prefix boundary.
- **Output contract:** an *ordered* window matching the canonical slot order in
  `Context-Management.md` — stable prefix → goal/task → retrieved context →
  memory → trajectory summary → recent tool outputs → plan/scratchpad →
  last action+observation → current instruction [F: `Context-Management.md`
  § canonical window; the summary here is a compression of that slot list].
- **Failure contract:** on overflow, *compact before truncating*; on poisoning
  suspicion, drop the suspect source, not the goal.
- **Design rule:** the goal + hard constraints live *outside* the compaction
  region (`../Context-Engineering/Context-Compaction.md`).

### 4. Memory layer
- **Input contract:** what is high-signal (write policy); provenance tagging.
- **Output contract:** retrieval scored by recency × importance × relevance,
  budget-limited.
- **Failure contract:** poisoned or stale memory is quarantined, not silently
  trusted (`../Context-Engineering/Agent-Memory.md` § poisoning).
- **Design rule:** store distilled facts + evidence, not raw transcripts.

### 5. Planning
- **Input contract:** goal + current state + available tools.
- **Output contract:** a numbered plan (explicit) or interleaved thoughts
  (implicit); a *replan trigger* (observation invalidated a plan step).
- **Failure contract:** a plan that can't progress → replan at most k times, then
  escalate (budget on *replanning*, not just on steps —
  `../Agents/Agent-Loops-and-Reasoning-Strategies.md` § planning).
- **Design rule:** explicit plans pay off above ~20 steps; below that,
  implicit ReAct-style is cheaper [I].

### 6. Verification
- **Input contract:** the artifact (code diff, answer, state change) + the check
  oracle (tests, linter, schema, independent model).
- **Output contract:** pass/fail + *where* it failed (a 5-line summary, not the
  full traceback — context hygiene).
- **Failure contract:** a failed check is *data* for the revision step, not an
  abort; but N consecutive fails on the same check → stop + escalate.
- **Design rule:** for anything safety-relevant, the verifier is a *different*
  model/config than the actor (independent-evaluator pattern; this wiki's own
  pipeline is the canonical instance).

### 7. Delegation / subagents
- **Input contract:** a self-contained task spec (the subagent has *no* parent
  context — say so explicitly, as in `../Agents/Multi-Agent-Systems.md`
  § delegation economics).
- **Output contract:** a *digest* (result + evidence + open items), not the raw
  transcript.
- **Failure contract:** a subagent failure returns a failure report the parent
  can route around; the parent's context is not polluted by the subagent's dead
  ends.
- **Design rule:** delegate for *context isolation*, parallelism, or role
  expertise — not because "more agents = better" [I].

### 8. Control loop (the skeleton)
See `Control-Loops.md` for the full treatment. Contract summary: every loop has
(a) a step budget, (b) a token budget, (c) a no-progress detector, (d) an
escalation path, and (e) a *deterministic* stop condition — "done" is defined
*before* the loop starts, not discovered inside it.

### 9. Effect layer / sandbox
See `Sandboxing.md`. Contract: the model's *intent* (a tool call) is mediated by
a *capability system* — the harness decides what the call *can* do, not what the
model *says* it does.

### 10. Observability
- **Contract:** every step logged with (input tokens, output tokens, tool calls,
  latency, cost, result) → replayable trace.
- **Failure contract:** a run you cannot replay is a run you cannot debug;
  logging is not optional infrastructure, it is part of the control loop
  (you need the trace to detect loops, measure no-progress, attribute cost).
- **Design rule:** cost attribution per *step* and per *tool*, not just
  per-run — the budget controls in `Control-Loops.md` need this granularity.

## The seams (where swaps happen)
| Seam | Swappable sides | Why it matters |
|---|---|---|
| model ⇄ harness | any OpenAI-compatible endpoint | test harnesses on weak models; route cheap steps to cheap models |
| tool schema ⇄ implementation | MCP servers, native tools | same contract, N backends |
| memory store ⇄ retrieval | vector / KG / files | the write/read policy stays, the substrate changes |
| verifier ⇄ oracle | tests, linters, 2nd model | the "check before commit" contract is model-agnostic |
| serving ⇄ harness | vLLM / SGLang / hosted | prefix-caching economics differ; the context *policy* shouldn't |

A well-factored harness is defined by these seams: any side can change without
touching the other. [I: this is the same modularity principle that makes serving
engines swappable — `../Inference/`]

## Reading any agent system (a checklist)
Given any production agent, you can now read it as answers to:
1. What's the static prefix, and how big is it? (cache economics)
2. How many tools, what's the schema style? (tool precision)
3. What's the context policy (ordering, compaction trigger)?
4. Where's the goal anchored, and is it compaction-safe?
5. What's the verification oracle, and is it independent?
6. What are the budgets (steps, tokens, $, wall-clock)?
7. What's in the sandbox, and what are the write gates?
8. Can I replay a run?
Answering all eight *is* understanding a harness. [I]

## Related
`Context-Management.md` · `Control-Loops.md` · `Sandboxing.md` · `Model-vs-Harness.md` ·
`Open-Harnesses.md` · `../Agents/Tool-Use.md` · `../Context-Engineering/Context-Budget.md`.

## Key Takeaways
A harness is a stack of layers with **input/output/failure contracts** at each
seam. Design the contracts; version the prompts; budget everything; keep the
goal outside the compaction region; verify with an independent oracle; and make
every run replayable. That checklist is both the design guide and the code-review
checklist for any agent system.
