# 35 — Agentic AI Economics

`LAST_UPDATED: 2026-08-24` · Status: core page · Numbers from
[scripts/economic_foundation.py](scripts/economic_foundation.py).

## 30-Second Explanation

**Agent cost is not chatbot cost.** A chat is *one user request → one model
call*. An agent is *one user request → a planner, research agents, tools, a
critic, revisions, and a final answer* — typically **many model calls**. The
**Task Amplification Factor** is the number of model calls per user task, and it
multiplies cost. An agent task that makes 27 model calls costs ~**27×** a
one-shot answer. This is the single most important reason agents need their own
metering and budgets ([13-tenant-metering](13-tenant-metering.md),
[20-quota-engineering](20-quota-engineering.md)).

## Chat vs agent

```
CHAT:   1 user request ────────────────→ 1 model call ──→ answer

AGENT:  user task
          ↓
        planner          (LLM call 1)
          ↓
        research agents  (LLM calls 2..n)
          ↓
        tools            (tool calls, each may feed an LLM call)
          ↓
        critic           (LLM call — evaluation/revision)
          ↓
        revisions        (more LLM calls)
          ↓
        final answer
```

## Task Amplification Factor

$$\text{TAF} = \frac{\text{model calls per user task}}{\text{1 model call}}$$

**Worked example (computed):** one user request → **27 model calls** (planner +
several research agents + critic + multiple revisions). If each call costs the
equivalent of a one-shot gpt-4o-mini request (~$0.0005), the agent task is
27 × $0.0005 ≈ **$0.0142** — vs $0.0005 for a chat answer. TAF=27 ⇒ ~27× cost.

> Note: TAF is a *multiplier on calls*, but agent calls are often *longer* too
> (more context, tool payloads, reasoning tokens) — so real amplification is
> usually **> call-count × one-shot cost** ([07-prefill-decode-economics](07-prefill-decode-economics.md)).

## What multiplies agent cost

- **Recursive agents** — agents spawning agents.
- **Tool loops** — a tool call that triggers more LLM calls.
- **Delegation** — sub-agents each with their own budget of calls.
- **Parallel agents** — many at once (fan-out) — also a concurrency/noise risk ([19](19-noisy-neighbor.md)).
- **Evaluator models** — critics that are themselves LLM calls ([36-evaluator-economics](36-evaluator-economics.md)).

## Cost per Completed Agent Task

$$\text{Cost per Completed Task} = \sum_{\text{calls}} \text{cost}_{\text{call}} + \text{cost of retries/failures}$$

Budget-driven framing (from [22](22-budget-aware-routing.md)): an agent run
should carry a **run-level token/time/cost budget** and a **step cap**, or a
single runaway agent can burn a month of a tenant's quota in minutes — the
classic failure mode of [55-governance-antipatterns](55-governance-antipatterns.md)
("unbounded agents"). See [Production-Operations/34-agent-sre](../Production-Operations/34-agent-sre.md)
for the reliability side.

## Metering agents

Meter at the **run/task** level, not just per call: attribute all of an agent
task's calls to the originating user request, so the *task cost* — not the
visible one call — is what gets charged and governed
([13-tenant-metering](13-tenant-metering.md), [14-showback-chargeback](14-showback-chargeback.md)).

## Related

[36-evaluator-economics](36-evaluator-economics.md) ·
[34-ai-cost-waste](34-ai-cost-waste.md) ·
[Production-Operations/34-agent-sre](../Production-Operations/34-agent-sre.md) ·
[Agents/](../Agents/README.md) · [22-budget-aware-routing](22-budget-aware-routing.md)

## Key takeaways

1. Agents amplify cost: 1 task → many model calls (TAF).
2. Chat = 1 call; agent = planner + researchers + tools + critic + revisions.
3. Meter and budget at the agent-run level, with step/time/token/cost caps.
4. A runaway agent is a top waste/failure mode — contain it.
