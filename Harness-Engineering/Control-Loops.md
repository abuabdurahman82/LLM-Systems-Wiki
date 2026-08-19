# Control Loops (retries, budgets, stopping, routing)
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
The control loop is where an agent *lives*: the plan→act→observe→revise cycle
(`../Agents/Agent-Loops-and-Reasoning-Strategies.md`) plus the **operating
system of the loop** — budgets, stopping conditions, no-progress detection,
retry semantics, and model routing. A strong model in a weak loop burns budget on
loops; a strong loop can rescue a mediocre model on bounded tasks. This page is
the "OS layer" of the loop.

## The five loop controls (the non-negotiables)
### 1. Budgets (spend control)
Four budgets, all enforced *before* the step, not discovered after:
- **Step budget** — max iterations (hard stop; the compounding-error ceiling,
  `../Agents/Agentic-AI-Evolution.md` § compounding-error math).
- **Token budget** — cumulative input+output cap (cost control; the window
  re-read is the dominant term, `../Agents/Tool-Use.md` § economics).
- **Wall-clock budget** — max elapsed time (the latency SLO).
- **$/task budget** — the business cap; converted to a token cap via pricing
  (worked example below).

> **Worked $-cap example [E: arithmetic]:** a $2.00/task budget. If the run is
> 80% input / 20% output tokens and in=$3/M, out=$15/M [A], let T = total tokens:
> cost = 0.8·T·3/1e6 + 0.2·T·15/1e6 = T·(2.4+3.0)/1e6 = T·5.4/1e6. Setting
> that = $2.00 → T = 2.00·1e6/5.4 ≈ **370k total tokens**. [E: 2,000,000/5.4
> = 370,370] So the $ budget translates to ~370k total tokens *before* the
> harness knows the step count — the budget is on the *aggregate*, not the
> per-step.

### 2. Stopping conditions (define "done" *before* the loop)
The loop stops on the first of:
- **Goal met** — the checker passes (test green, artifact valid, user confirmed).
- **No progress** — k consecutive steps with no state change (see § 3).
- **Budget exhausted** — any of the four budgets in § 1.
- **Irreversible gate hit** — the next action needs a human (write to prod,
  spend money, delete data) → stop + escalate (`Sandboxing.md` § gates).
- **Explicit abort** — the model emits a structured `ABORT(reason)` (give it the
  *ability* to stop; a loop that can't say "I can't do this" is a loop that
  will pretend it can).

A loop without a *pre-declared* done condition will run to the budget and call it
"done" — the single most common harness bug [I].

### 3. No-progress detection (loop-breaking)
The agent can *loop* — same tool, same args, same result, 10 times. Detection:
- **State-hash check** — hash (tool, args, normalized result); if the last k
  steps share ≥ m repeated hashes → no-progress.
- **On trigger:** force a *replan* (the model must try a *different* action), or
  compact (`Context-Management.md`), or stop+escalate.
- **Budget on replanning:** max k replans, then stop — otherwise you've just
  moved the loop to the planner [I].

### 4. Retry semantics (per-tool, not global)
- **Idempotent reads** (search, read) → retry on transient errors (timeout, 5xx)
  with backoff; safe to retry N times.
- **Writes / side-effecting tools** → **do NOT auto-retry** (a retried `deploy`
  deploys twice). Retry only after the harness *verifies the prior attempt didn't
  land* (a pre-check).
- **Error-class routing:** `transient` → retry; `validation` → feed the error
  back to the model to fix its args (one self-correction cycle); `auth/permission`
  → stop (the model can't fix a 403 by retrying); `logic` → treat as an
  observation, not an error to retry.
- **A retry is a step** — it counts against the step/token budget [I].

### 5. Model routing (cheap vs frontier per step)
Not every step needs the frontier model. Route by *step type*
(`../Inference/Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md` applies the
same signal logic at the serving layer):
- **Search / summarize / extract** → cheap, fast model (high volume, low stakes).
- **Plan / decide / edit critical code** → frontier model (low volume, high stakes).
- **Verify / critique** → a *different* model than the actor (independence;
  `../Agents/Agent-Evaluation.md` § independent verifier).
Routing is an *economic* and a *capability* decision: it cuts cost 3–10× [I:
order-of-magnitude, depends on step-mix] and can *improve* quality by matching
model strength to step difficulty. The router must know its per-step budget
(`../Inference/Inference-Optimization.md`).

## The state machine (reference implementation)
```
                    ┌────────────┐
        ───────────▶│  PLAN      │──(plan emitted, goal set)──┐
                    └────────────┘                             ▼
              ┌──────────────────────────────────────────┌────────────┐
              │  BUDGETS OK?  NO-PROGRESS?  GOAL MET?     │   ACT      │
              │  no / no / no ──────────────────────────▶ │ (tool call)│
              └──────────────────────────────────────────└──────┬─────┘
                                                                 ▼
              ┌──────────────────────────────────────────┌────────────┐
              │  retry / stop / verify                   │  OBSERVE   │
              │  (error-class, state-hash, checker)      │ (result)    │
              └──────────────────────────────────────────└──────┬─────┘
                                                                 │
                              ┌──────────────────────────────────┘
                              ▼
                    ┌───────────────────┐   goal-met / budget / no-progress
                    │   REVISE / STOP   │──▶ (record; escalate or terminate)
                    └───────────────────┘
```
Every edge is *deterministic and logged*. The model decides *what* to do inside
ACT/REVISE; the harness decides *whether the loop continues*. That split is the
whole discipline. [I]

## The human-in-the-loop gates (where the loop yields)
Insert *pre-committed* gates at irreversible steps (`Sandboxing.md`):
- **Confirm-before-write** (prod, money, delete, publish) → the loop pauses,
  presents the diff/action, waits for approval.
- **Escalate-on-uncertainty** — the model signals low confidence (or the verifier
  disagrees) → hand to a human with the trace.
- **Budget-approaching alert** — at 80% of the $/step budget, warn; the human
  can extend or cut the task.
The gate is a *state in the loop*, not a modal popup — it must be replayable and
logged like any other step [I].

## Why the loop matters more than the model (on bounded tasks)
A hand-computable illustration of *loop quality* dominating *model quality* on a
bounded task [I: illustrative, the exact numbers are a modeling choice]:
- Task needs 20 correct steps; model A (weak) p=0.95/step; model B (strong)
  p=0.98/step.
- Naive loop (no retries, no no-progress detection): A = 0.95^20 = 0.358;
  B = 0.98^20 = 0.667. B wins by 1.9×. [E: 0.95^20=0.3585, 0.98^20=0.6676]
- Now add a *retry-on-error* loop that gives each step 2 attempts (a failed step
  is re-tried once; effective step success = 1−(1−p)²): A_eff = 1−0.05² = 0.9975
  → 0.9975^20 = **0.951**; B_eff = 1−0.02² = 0.9996 → 0.9996^20 = **0.992**.
  [E: 0.9975^20 = 0.9512; 0.9996^20 = 0.9920]
  Now **A with a good loop (0.951) beats B with a naive loop (0.667)** by 1.42×,
  and even B-with-a-good-loop only edges A-with-a-good-loop (0.992 vs 0.951) —
  the loop quality compressed the model gap from 1.86× to 1.04×. [E:
  0.6676/0.3585 = 1.86×; 0.9920/0.9512 = 1.04×]
- The lesson: *a retry + no-progress loop recovers a large fraction of the
  model gap* on bounded, checkable tasks. The model sets the per-step p; the loop
  decides how that p compounds. [E: arithmetic; the model-agnostic part is the
  compounding, the p-values are [A] modeling choices]

(This is why `../Agents/Agent-Evaluation.md` insists on reporting the harness
alongside the model — the number is model *×* loop.)

## Related
`../Agents/Agent-Loops-and-Reasoning-Strategies.md` · `Context-Management.md` ·
`Sandboxing.md` · `Model-vs-Harness.md` · `../Inference/Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md`.

## Key Takeaways
The loop is an OS: **budgets** (4 kinds, enforced up front), **pre-declared
stopping**, **no-progress detection**, **error-class-aware retries** (never
auto-retry writes), and **per-step model routing**. The model chooses *what*;
the loop decides *whether to continue* — and that split is where reliability and
cost are actually won.
