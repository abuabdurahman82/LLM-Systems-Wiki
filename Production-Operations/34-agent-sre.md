# 34 — Agent SRE

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

Agents turn one request into **many model calls, tool calls, and possibly
sub-agents** — which multiplies the failure and cost surface. Agent reliability
is about **bounding** the agent so a runaway loop, an infinite retry, or a budget
blowup cannot damage users or the platform. The harness is the control point
(see `Harness-Engineering/`).

## Agent failure modes

| Mode | What it is |
|---|---|
| **Runaway loops** | agent never converges; repeats steps |
| **Infinite retries** | retries a failing tool/model forever |
| **Tool recursion** | a tool triggers another agent step repeatedly |
| **Context growth** | context/scratchpad grows unboundedly each step |
| **Delegation explosion** | spawning sub-agents exponentially |
| **Budget exhaustion** | token/time/cost exhausted mid-task |
| **Stuck tasks** | agent deadlocks / waits on nothing |
| **Incorrect tool action** | calls the wrong tool/args (harmful or wasteful) |

## The budgets — the reliability core

| Budget | Bounds | Why |
|---|---|---|
| **Step limit** | max agent iterations | stops runaway loops |
| **Token budget** | max total tokens (in+out) | stops context/token blowup |
| **Time budget** | max wall time per task | stops stuck tasks; pairs with timeouts ([14](14-retries-timeouts-circuit-breakers.md)) |
| **Cost budget** | max $ per task/session | stops economic damage ([33](33-cost-as-an-sre-signal.md)) |
| **Delegation limit** | max sub-agents / depth | stops delegation explosion |

When any budget trips: **terminate gracefully** (return best partial result +
status), don't silently loop.

## Operational practice (`[I]`)

1. **Enforce budgets in the harness** — the harness (not the model) owns
   step/token/time/cost/delegation limits `[Harness-Engineering/Control-Loops.md]`.
2. **Instrument every step** — per-step model/tool/sub-agent traces
   ([23](23-llm-tracing.md)) observable as agent SLIs ([21](21-production-dashboard.md)).
3. **Watch step/token/cost trends** — a rising steps-per-task or cost-per-task is a
   leading indicator of looping ([24](24-quality-observability.md)).
4. **Break the retry cycle** — bounded retries with backoff per tool call
   ([14](14-retries-timeouts-circuit-breakers.md)); circuit-break failing tools.
5. **Dry-run/verify tool actions** — sandbox and validate before side effects
   (`Harness-Engineering/Sandboxing.md`).
6. **Timebox realistically** — generous enough for hard tasks, strict enough to
   catch stuck tasks.

## Connect: Harness Engineering

The harness *is* the agent's operating environment — control loops, context
management, sandboxing. SRE obligations (budgets, tracing, termination,
observability) are implemented *there*. See `Harness-Engineering/Control-Loops.md`,
`Harness-Engineering/Context-Management.md`, `Harness-Engineering/Sandboxing.md`.

## Related

`13-overload-protection.md` · `14-retries-timeouts-circuit-breakers.md` ·
`23-llm-tracing.md` · `33-cost-as-an-sre-signal.md` ·
`Harness-Engineering/Control-Loops.md` · `Agents/Agent-Loops-and-Reasoning-Strategies.md`

## Key takeaways

1. Agents multiply model calls, tool calls, and cost — they need hard bounds.
2. Failures: runaway loops, infinite retries, tool recursion, context growth,
   delegation explosion, budget exhaustion, stuck tasks, wrong tool calls.
3. Enforce step/token/time/cost/delegation budgets in the harness.
4. Terminate gracefully on budget trip; instrument and watch per-step trends.
