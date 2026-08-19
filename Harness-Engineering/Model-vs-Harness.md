# Model vs Harness (how much is which?)
`LAST_UPDATED: 2026-08-19` · Status: core page · **the section's live research question**

## 30-Second Explanation
When an agent scores 40% on SWE-bench Verified, how much of that is *the model*
and how much is *the harness* (prompts, tools, memory, retries, verification)?
This question is the heart of harness engineering — it determines where to invest
(model upgrades vs scaffold work) and how to read *any* published benchmark number.
The honest 2026 answer: **both, multiplicatively, and the split is task- and
horizon-dependent** — with a hand-computable decomposition below that makes the
argument concrete.

## The decomposition (the model)
An agent task's success is *not* the sum of "model part + harness part"; it is a
**product of per-step gates**:
```
task_success = P(each step succeeds) over T steps
             = Πₜ P(step_t)
where P(step_t) = model_capability(step_t) × harness_reliability(step_t)
```
- `model_capability` = the model's probability of emitting a correct action *given
  a well-formed context* (its "raw" skill at step t).
- `harness_reliability` = the probability the harness *feeds it the right context,
  gives it the right tools, doesn't corrupt/truncate the observation, and recovers
  from its errors* (retries, replans, compaction that keeps the goal).
[E: the *ratios* are arithmetic; the *factor values* are empirical/modeling
choices, not derivable]

**Key structural point [I]:** the harness can at best *recover* what the model
fails (retry a bad step, re-fetch a truncated result), so `harness_reliability`
acts as a *recovery multiplier on the model's per-step p* — but it **cannot create
capability the model doesn't have**. A harness can't make a model that can't fix a
syntax error *fix a syntax error*; it can only give the model *more chances* and a
*cleaner board*. This asymmetry is why the split is horizon-dependent (below).

## The hand-computable worked example (the whole argument in one table)
Fixed task: T=20 steps. Model A p₀=0.95/step (weaker), Model B p₀=0.98/step
(stronger). Harnesses: H_naive (no retries, lossy observations) recovery
factor 0.90; H_good (retries + no-progress + clean context) recovery factor 0.99
[i.e. per-step effective p = p₀ × recovery, capped at 1]. [A: all p-values are
*modeling choices* for illustration — the point is the *structure*, and the
[E] arithmetic below]

| Config | per-step p (A) | 20-step (A) | per-step p (B) | 20-step (B) |
|---|---|---|---|---|
| A + naive | 0.95·0.90 = 0.855 | 0.855^20 = **0.0436** | — | — |
| A + good | 0.95·0.99 = 0.9405 | 0.9405^20 = **0.293** | — | — |
| B + naive | — | — | 0.98·0.90 = 0.882 | 0.882^20 = **0.0812** |
| B + good | — | — | 0.98·0.99 = 0.9702 | 0.9702^20 = **0.546** |

[E: 0.855^20=0.04358; 0.9405^20=0.29321; 0.882^20=0.08117; 0.9702^20=0.54604]

Read this table *carefully* — it is the whole section in four numbers:
1. **Same model, better harness:** A goes 0.0436 → 0.293 = **6.7×**. The harness is
   the single biggest lever on a fixed model. [E: 0.29321/0.04358 = 6.73]
2. **Same harness, better model:** naive goes 0.0436 → 0.0812 = **1.86×**; good
   goes 0.293 → 0.546 = **1.86×**. The model gap is *consistent* (×1.86) across
   harnesses — it doesn't disappear. [E: 0.08117/0.04358=1.862;
   0.54604/0.29321=1.862]
3. **The interaction:** B+good (0.546) is **12.5× better than A+naive
   (0.0436)** — but that's *both* changing [E: 0.54604/0.04358 = 12.53]. The clean
   single-factor ratios are the ×6.7 (harness) and ×1.86 (model) above. The
   *multiplicative* structure means **you cannot attribute a benchmark number to
   one factor without holding the other fixed.** (Note: the product form
   `Π P(step_t)` is a *clean-board approximation* — the retry loop in the
   the "good" column is modelled as a **per-step effective-p multiplier (p₀ ×
   recovery)**, not as a literal second attempt on the same step. The two are
   *close but not equal*: a literal one-retry with a full reset gives
   p = p₀ + (1−p₀)·p₀ = 0.9975 for p₀=0.95, vs the 0.9405 multiplier here — the
   multiplier deliberately *penalizes* the harness for the cost/risk of the retry
   loop (context churn, budget, re-planning), so it is the conservative estimate.
   Both are [A] modeling choices; the multiplier is what the table uses.
4. **Horizon amplification:** at T=5 the same factors give A+good 0.736 vs
   A+naive 0.457 (1.61×) — the harness's edge *shrinks* on short tasks [E:
   0.9405^5=0.73586; 0.855^5=0.45691; ratio 1.61] and *grows* as T grows
   (at T=50: 0.9405^50 = 0.0466 vs 0.855^50 = 3.97e-4, ratio **117×** [E:
   0.9405^50=0.04655, 0.855^50=0.000397, ratio 117.4]). **The harness matters
   more the longer the horizon.** [I: this is the structural reason long-horizon
   agent work is dominated by scaffold quality]

**The answer to "how much is model vs harness":** *both, multiplicatively.* On a
bounded task the model sets the per-step p; the harness multiplies how many of
those p's you actually get to use. **You cannot read a single benchmark number and
split it** — you need a *factorial design* (same model × 2 harnesses; same
harness × 2 models), which is exactly why
`../Agents/Agent-Evaluation.md` § harness-effect says "always report the harness."

## The three empirical effects (what the evidence says)
All three are [I] unless noted — this is an active, contested question, and the
wiki's policy is to *not declare a winner* without a pinned factorial benchmark.

1. **Scaffold effect (harness moves a lot, on a fixed model):** identical model,
   different harness → large swings on agentic evals. The SWE-agent paper's
   central empirical result is that the *agent-computer interface* (a harness
   variable) dramatically changes performance [F: arXiv:2405.15793]. Order of
   magnitude: 10–30+ points on SWE-bench-class work [I: consistent with the
   ablation literature]. **The worked table's ×6.7 harness ratio is the
   hand-computable version of this.**
2. **Ceiling effect (model sets the top, on a fixed good harness):** at a fixed
   *strong* harness, swapping models dominates the ranking — frontier-vs-frontier
   agent gaps track underlying model gaps [I: cross-vendor reading]. The worked
   table's consistent ×1.86 model ratio across harnesses is the hand-computable
   version: **the model gap is *stable*, the harness gap is *large***.
3. **Absorption effect (the split moves over time):** each model generation
   *absorbs* harness techniques — long-horizon reliability, tool discipline, and
   planning quality increasingly get *trained into* the model rather than
   scaffolded around it (`../Agents/Agentic-AI-Evolution.md` § Phase 5). Consequence
   [I]: the harness's *per-step recovery* value shrinks as models improve, but
   **never to zero** — cost control, observability, safety rails, and sandboxing
   are *structural* harness jobs the model will never absorb. So the harness
   *thins* (fewer recovery scaffolds) but does not *disappear*.

**Unverified hypotheses (do not treat as settled) [H1–H3]:**
- **H1:** "On 2026 frontier coding models, a top-3 harness beats a minimal
  harness by ≥2× on SWE-bench Verified." *Deciding experiment:* pinned factorial
  — 2 frontier models × {minimal, top-3} harnesses, ≥5 seeds each, report
  success ± CI + $/task. (The ×6.7 in the table suggests "yes", but the p-values
  are [A].)
- **H2:** "Harness gains shrink monotonically with model generation (absorption)."
  *Deciding experiment:* same harness, N model generations (2024→2026) on one
  task; plot the harness/model ratio per generation.
- **H3:** "Beyond ~50 steps, harness quality explains > model quality of the
  variance in task success." *Deciding experiment:* long-horizon task (T=100),
  factorial model×harness, run an ANOVA on success; compare main effects.
Each H is *paired with the experiment that would decide it* — the wiki's standard
(no winner declared without the pinned benchmark).

## How to read any published agent number (a decision rule)
Given "model M scores S on benchmark B with harness H":
1. **Is H pinned?** If not, the number is *model+harness* and non-comparable.
   Stop there.
2. **Is it the harness you care about?** Your harness ≠ the paper's harness; the
   transfer is unknown (re-measure on yours).
3. **What horizon?** Short-horizon numbers understate harness importance;
   long-horizon numbers overstate it (the ×1.6 at T=5 vs ×117 at T=50 above).
4. **What cost?** A +10-point harness that 5×'s cost may be *worse value*
   (`../Agents/Agent-Evaluation.md` § cost as a first-class axis).
5. **Variance?** One-run numbers hide the harness's *reliability* effect; the
   harness's real job is often *variance reduction*, not just mean lifting [I].
Only after all five is a number *yours to use*.

## Related
`Harness-Anatomy.md` (what the harness *is*) · `Control-Loops.md` (the recovery
machinery that *is* most of `harness_reliability`) · `../Agents/Agent-Evaluation.md`
§ harness-effect · `../Agents/Agentic-AI-Evolution.md` § Phase 5 (absorption).

## Key Takeaways
Success = model_capability × harness_reliability, *per step, compounded over the
horizon*. The model sets the per-step p; the harness decides how many of those p's
you get to use — so it's the biggest *single* lever on a fixed model (×6.7 in the
worked table), but it cannot create capability the model lacks (the model gap,
×1.86, stays). The split is horizon-dependent (harness matters more the longer the
task), and it *moves* as models absorb scaffolds. Read every agent number as
model×harness, never as "the model's score."
