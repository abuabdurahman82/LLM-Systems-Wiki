# 07 — Reasoning Distillation: Transferring the Thinking, Not Just the Answer
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
Reasoning distillation trains the student on the teacher's *chain of thought*, not just
its final answer. The trace is a denser, more checkable, more generalizable supervision
signal: intermediate steps expose *why* an answer is right, give gradable checkpoints,
and teach behaviors (decomposition, reflection, backtracking) that answer-only data
cannot show. But more tokens ≠ better data: quality, verification, diversity and length
control decide whether traces teach reasoning or teach the student to ramble.

## The basic transfer

```
Question
   ↓
Teacher Reasoning Model
   ↓
Reasoning trace  (Step 1 … Step k, self-checks, retries)
   ↓
Answer
                    ↓ student learns
Question
   ↓
Reasoning           ← student generates the process, not just the product
   ↓
Answer
```

This is response distillation (`06`) with the trace as the payload — but the payload
change is qualitative. A trace is *behavioral data*: it shows the student how to attack
a problem, not merely where to stop.

## Answer distillation vs reasoning distillation

```
Answer-only:      Question → 42
Reasoning:        Question → Step 1 → Step 2 → Step 3 → Step 4 → 42
```

| Dimension | Answer-only | Reasoning traces |
|---|---|---|
| Supervision density | 1 signal per problem | k intermediate checkpoints |
| What transfers | final mapping | process + strategy + answer |
| Checkability | answer only | per-step (tests, math checkers, step judges) |
| Error propagation | all-or-nothing | trace shows *where* reasoning fails |
| Verbosity risk | none | real — see below |
| Token cost of data | low | 10–1000× higher [I: typical trace lengths] |
| Best transfer mechanism | — | a model *demonstrating* learned reasoning outperforms answer-mimicry; the R1 paper reports distilled-trace students beating their instruction-tuned bases and, at 32B, an RL-only peer (→ `08`) |

## Why traces supervise better (the mechanism)

1. **Credit assignment:** with a wrong answer, a step-wise trace localizes the failure;
   the student's next dataset can target it (→ §error mining, `18`).
2. **Compositional behavior:** traces encode transferable moves (define variables, try a
   small case, check units, backtrack) that apply to new problems, not just the training
   distribution [I: the standard process-supervision argument, cf. Lightman et al.
   arXiv:2305.20050 for step-level value].
3. **Train-time compute is free:** the student's SFT loss gets k informative positions
   instead of one; more signal per example.
4. **Format bootstrapping:** even when the student can't yet *do* the reasoning,
   traces teach the output format that downstream verification and RL can improve
   (the R1 cold-start argument [F: arXiv:2501.12948 §2.3 — human CoT templates
   "often omit critical reasoning components such as explicit reflection and
   verification steps"]).

## The dark side: more tokens ≠ better data

| Pathology | What it looks like | Why it hurts | Mitigation |
|---|---|---|---|
| **Unfaithful reasoning** | trace is post-hoc rationalization; answer ≠ derivation | student learns plausible-sounding text, not derivation | verification against answers/tests; consistency checks (same answer, varied trace) |
| **Overlong reasoning** | 10K tokens for grade-school math | teaches waste; inference cost explodes in the student too; length is *imitated* | length filters/curricula; concise-trace selection; "budget forcing" at eval |
| **Repetitive patterns** | same template every problem | student memorizes template, fails off-pattern | diversity in prompts and teachers; dedup (→`14`) |
| **Style bias** | teacher idiosyncrasies ("wait—", headers, meta-talk) | student parrots style, not substance | normalization/rewriting passes |
| **Language mixing** | trace switches languages mid-stream | unusable in production | language-consistency filters — R1 used an LC reward for exactly this [F: arXiv:2501.12948 B.6] |
| **Reward hacking in generators** | teacher trained to please a judge produces performative reasoning | garbage in, confident garbage out | independent verifiers, not judge-style filters |
| **Teacher hallucinations** | confident false steps | student inherits confident falsehoods | answer/test verification; drop unverifiable domains (→`14`) |

## Teacher quality matters: not all teacher outputs are equal

Same prompt set, different teachers → different students, and stronger teachers do not
monotonically produce better students. The factors with 2025–26 evidence behind them:

- **Teacher strength:** stronger reasoning teachers produce traces that verify at higher
  rates and cover harder problems (the R1 distillation used R1 itself, at the time the
  strongest open reasoning model [F: arXiv:2501.12948]).
- **Verification pass rate is the effective quality knob:** a "weaker" teacher whose
  outputs verify 90% of the time can beat a "stronger" one at 60% once filtering is
  applied — you pay for only the verified fraction [I: economic framing; consistent with
  the best-of-N analysis in `27`-style pipelines and §verification below].
- **Diversity and difficulty distribution:** traces concentrated on easy problems teach
  little; difficulty scoring and stratified sampling beat raw volume (→ §active and
  §curriculum below, and `14`).
- **Calibration:** an overconfident teacher's *errors* look identical to its successes
  in the text; verifiers must be independent of the teacher [I].

[Research Result status: teacher-comparison studies through 2026 are consistent on
"verification + diversity beat raw teacher strength," but effect sizes are
benchmark-specific — treat rankings as per-benchmark, not universal.]

## Verified reasoning distillation (the production pattern)

```
Prompts
   ↓
Teacher generates N candidates per prompt
   ↓
Verifier  ─┬─ unit tests (code)
           ├─ math checker (symnumeric / answer match)
           ├─ reference answer
           ├─ judge model (open-ended)
           └─ reward model (preference-consistency)
   ↓
Accepted reasoning traces (correct AND legible)
   ↓
Student training
```

**Why verification beats volume:** unverified synthetic data both (a) injects confident
errors and (b) wastes student capacity on them; verification costs a bounded, parallel,
often-cheap compute and raises the *effective* quality of every downstream token.
DeepSeek-R1's dataset construction did exactly this shape: sample multiple responses
per prompt, retain only correct ones, filter mixed-language/paragraph/code-block CoT,
≈600K reasoning samples + 200K non-reasoning = 800K SFT samples
[F: arXiv:2501.12948 §4 + B.3.3].

## Best-of-N distillation

```
Prompt → Teacher × N generations → Verifier/Judge → Best response → Student
```

- **N and quality:** accuracy of the accepted set rises with N + a good selector; the
  *selector* (verifier vs judge vs RM) is usually the bottleneck, not N [Research
  Result: consistent with self-consistency and verifier literature, arXiv:2203.11171
  lineage].
- **Cost:** N× teacher generation spend; best spent on hard prompts (→ §active below).
- **Diversity:** keep near-miss correct-but-verbose / correct-but-different-style traces
  for curriculum stages instead of discarding [I].
- **A subtlety:** training on *best* traces only can make the student brittle on its own
  (slightly-off) distribution — the classic case for later on-policy phases (→`10`).

## Active distillation (spend teacher compute where it's needed)

```
Easy prompt   → student already handles it        (no teacher call)
Hard prompt   → uncertainty/entropy high          → query teacher
```

Signals for routing: student self-consistency disagreement, token-level entropy,
verifier failure on student attempts, or a learned difficulty model. This is active
learning in distillation clothing; the payoff is a large reduction in teacher spend for
the same student quality [I: framework is standard active learning; the cost model is
worked in `17` §break-even].

## Curriculum distillation

Order training data easy → medium → hard → very hard (by verifier-measured difficulty,
not teacher self-report). Evidence for reasoning students is mixed-but-leaning-positive:
it helps stability and reduces early-training collapse on hard data; it is not a
substitute for data quality [Research Result; the effect is dataset- and
scale-dependent — measure, don't assume].

## The 80/20 of reasoning distillation
1. Trace + verified answer > answer-only, at every student size tested publicly so far
   [F: arXiv:2501.12948].
2. Verification is the single highest-leverage component; budget it before volume.
3. Filter length, language consistency, and style — the student imitates *all* of it.
4. Best-of-N with an independent verifier is the cheapest quality multiplier.
5. Save the student's own failures — they are the targeting system for the next round
   (→ `18` §error mining).

## Related
- `08-deepseek-r1-distillation.md` — the canonical case study of this page's pipeline
- `14-data-generation-and-verification.md` — cleaning, contamination, safety/quality filters
- `10-on-policy-distillation.md` — what happens when the student's own traces enter training
- `Reasoning/README.md` — test-time compute & RLVR on the teacher side
- `Evaluation-Engineering/Reasoning-Evaluation.md` — how to measure the result
- `12-distillation-and-rl.md` — traces as reward signals (RLVR connection)

## Key Takeaways
- Reasoning distillation transfers *process*; its advantage is supervision density and
  behavioral transfer, not token count.
- Verification is the pipeline's load-bearing wall: unit tests, math checkers, judges —
  independent of the teacher.
- Trace pathologies (verbosity, unfaithfulness, language mixing, style parroting) are
  data problems with filter solutions.
- Best-of-N + active selection turns teacher spend into quality efficiently; curriculum
  ordering is a second-order refinement.
- The student inherits the teacher's reasoning *and* its pathologies — curation decides
  which dominates.
