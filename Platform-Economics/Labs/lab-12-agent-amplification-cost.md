# Lab 12 — Agent Amplification Cost

`LAST_UPDATED: 2026-08-24` · Concept: agent economics · Builds on
[../35-agent-economics](../35-agent-economics.md).

## Goal
Compute the **Task Amplification Factor** and total agent-task cost vs a
one-shot chat answer, and show the budget needed to contain it.

## Approach (computation)
```python
calls = 27                       # planner + researchers + critic + revisions
per_call = (1500*2.00 + 500*8.00)/1e6   # GPT-4.1-class $/req -> $0.007
task_cost = calls * per_call
TAF = calls
print("per-call", per_call, "task", task_cost, "TAF", TAF)
# per-call ~0.007, task ~0.19, TAF 27
```

Then set a **run budget**: metadata says a task may send at most `step_cap`
calls; a runaway agent that exceeds it must be terminated by an admission guard.

## Expected result
TAF=27 turns a $0.007/call into a **~$0.19 task** — ~27×, and real agents also
send *longer* contexts, so effective amplification is often higher.

## Interpretation
Agent cost is dominated by **calls × output + context**, not the visible "one
question". Run-level **step/token/time/cost budgets** are the containment
mechanism ([35](../35-agent-economics.md),
[Production-Operations/34-agent-sre](../../Production-Operations/34-agent-sre.md));
meter at the run, not per call ([13](../13-tenant-metering.md)).

## Verify
Halve the calls to 14 → task cost halves. Show that a missing step cap lets cost
grow linearly with a runaway loop.
