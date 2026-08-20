# Reasoning Evaluation: verifying answers, not just scores
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
Reasoning evaluation faces a two-layer problem: (a) does the final answer equal
the ground truth, and (b) is the chain of thought that produced it actually
valid. Layer (a) is cheap to check and easy to game — memorized shortcuts,
format hacks, and retrieved solutions all pass without any reasoning. Layer
(b), process validity, is what capability claims actually rest on, but it is
much harder to verify automatically. Three scoring mechanisms cover most of
the space: exact match on normalized answers, unit-test/oracle execution for
math and code, and an LLM judge of the chain. GSM8K and MATH accuracy now
overstate reasoning because of saturation plus contamination, and
GSM-Symbolic shows models often solve the memorized original rather than a
one-variable-transformed problem. A "reasoning score" is only defined at a
fixed effort level or thinking budget, and honest capability reports should
print outcome and process scores side by side.

## The two-layer problem: answer vs process
Every reasoning benchmark quietly makes two distinct claims:

- **Outcome (layer a):** the final answer equals the ground truth.
- **Process (layer b):** the chain of thought is a valid derivation of the
  answer — each step follows, no arithmetic errors, no unjustified leaps.

Layer (a) is gameable by construction [I]: a model that pattern-matches the
*question* to a memorized *answer* (shortcut answer), one that exploits the
grader's normalization (format hack: emit the answer twice, in different
formats), or one that reproduces a training-set solution (see
`Benchmark-Contamination.md`) scores high on outcome with zero reasoning.
Process supervision — rewarding intermediate steps instead of the final
answer alone — is the counterweight, but it is hard: you need either a
step-level verifier or human step annotations, and a wrong step that cancels
with a later wrong step still yields the right answer (worked example
below). The method under test matters too: chain-of-thought prompting
(Wei et al., arXiv:2201.11903 [F]) and Tree of Thoughts (Yao et al.,
arXiv:2305.10601 [F]) are not just baselines — they are the mechanism whose
validity we are measuring. A model that imitates CoT-flavored prose without
performing the computation is a CoT-faithfulness failure; see
`../Reasoning/README.md` for the prompting and method side.

## Scoring mechanisms
| Mechanism | Unit verified | Cost | Failure mode |
|---|---|---|---|
| Exact match on normalized answer | final answer string | near-zero | format gaming, near-misses, zero process signal |
| Unit-test / oracle execution | answer checked by running tests or a grader | low, deterministic | tests weaker than the spec; only when answers are executable |
| LLM judge of the chain | step-level validity | high, stochastic | judge bias, position effects — see `LLM-as-a-Judge.md` |

- **Exact match on normalized answers** is the default for GSM8K/MATH-style
  sets: strip units, LaTeX, and whitespace, then compare strings. Robust for
  single-answer math, useless as a process signal [I].
- **Unit-test / oracle execution** is the gold scorer wherever the answer is
  executable (code generation, numeric math with a grader). Its limits: a
  test suite weaker than the problem definition passes bad solutions, and
  overfitted tests are a separate contamination channel [I].
- **LLM judge of the chain** is the only general process scorer. Cheap per
  call, but stochastic and biased; calibrate against a human step-audit on a
  sample before trusting it [I; see `LLM-as-a-Judge.md`].

## Why MATH/GSM8K accuracy overstates reasoning
GSM8K (Cobbe et al., arXiv:2110.14168 [F]) and MATH (Hendrycks et al.,
arXiv:2103.03874 [F]) defined the field, but two effects now bias their
numbers upward:

1. **Saturation.** Frontier models cluster at the top of GSM8K, so the
   benchmark cannot discriminate among strong models; differences live in the
   last few points, which sit inside the noise [I].
2. **Contamination.** Both sets are old enough and popular enough (small,
   textbook-style, public since 2021) to be plausibly inside training data,
   so "accuracy" measures retrieval as much as reasoning [I; see
   `Benchmark-Contamination.md`].

The clean counterexample is **GSM-Symbolic** (Mirzadeh et al.,
arXiv:2410.05229 [F]): take GSM8K problems, change *one variable* (a name, a
number, a direction), and re-test. The paper finds models often solve the
original problem with the original numbers rather than the transformed one —
they have memorized the problem, not learned the procedure [F]. The design
lesson: any static math set measures `min(ability, contamination)`, and only
variable-transformed or freshly generated sets isolate the procedure [I].

**Depth benchmarks** target the unsaturated end: GPQA (arXiv:2311.12022
[F], graduate-level "Google-proof" QA), ARC-AGI-1 (arXiv:1911.01547 [F],
novel abstract puzzles built around a generalization gap), ARC-AGI-2
(arXiv:2505.11831 [F], higher per-task cost, lower human ceiling), and
Humanity's Last Exam (arXiv:2501.14249 [F], frontier-expert-authored). None
are saturated yet, and all inherit the same process-vs-outcome ambiguity —
which is why they should be paired with chain judging, not reported as bare
accuracy [I].

## Effort levels, RL reward signals, and CoT faithfulness
- **Effort-level confound.** A reasoning score is only defined at a fixed
  test-time budget: same model, different thinking-token cap or "effort"
  level, different number. Vendor models expose discrete effort levels
  [F: vendor], so any cross-model or cross-version comparison must pin
  effort or report the full score-vs-effort curve [I].
- **Process vs outcome rewards for RL.** RLVR pipelines train on *outcome*
  verifiers (answer correct/incorrect) because they are cheap and scalable;
  *process* supervision (step-level reward) is more data-hungry — it needs
  step annotations or a learned step verifier — but gives a denser, less
  gameable signal [I; see `../Post-Training/README.md`]. The eval side
  mirrors the training side: outcome-only evaluation cannot detect a model
  that learned reward-hacking chains.
- **CoT faithfulness.** When the written chain does not match the
  computation that actually produced the answer, outcome scoring silently
  measures something else. Faithfulness failures come in two directions: the
  chain is decorative (the answer came from parametric memory) or the chain
  contains errors that cancel [I]. Only process scoring — human or judge —
  detects either [I].

## Worked example: outcome 100% does not imply process 100% [E]
A 5-question mini-MATH set. Two models, same effort level, same grader:

- **Model A:** 5/5 correct; every chain is a valid derivation.
- **Model B:** 5/5 correct; the chains on Q2 and Q3 contain arithmetic
  errors that happen to cancel (a wrong intermediate followed by a wrong
  compensating intermediate, right final answer).

|  | Process valid | Process invalid |
|---|---|---|
| **Outcome correct** | Model A (5/5 clean) | Model B (3/5 clean chains) |
| **Outcome wrong** | — | (error did not cancel) |

- Outcome score: A = 100%, B = 100% — a tie on the only number most reports
  print. [E: 5/5 = 1.0 for both]
- Process score: A = 100%, B = 3/5 = 60%. [E: 3/5 = 0.6]
- The 2x2 makes the point: the top-right cell (outcome right, process
  wrong) is exactly where outcome-only evaluation is blind, and it is
  nonempty in practice [I].

Why print both: a capability report that shows only 100% for B certifies a
model whose chains cannot be trusted on harder, longer problems where errors
will not cancel. Treat the process score as the confidence interval on the
outcome score [I].

## Related
- `../Reasoning/README.md` — CoT/ToT methods under test
- `../Post-Training/README.md` — RLVR, process vs outcome rewards
- `LLM-as-a-Judge.md` — chain judging, bias, calibration
- `Benchmark-Contamination.md` — why old sets measure memory
- `Statistical-Evaluation.md` — CIs on small reasoning sets

## Key Takeaways
Reasoning evaluation must separate outcome (did the answer match?) from
process (was the chain valid?); outcome-only scoring is gameable by
memorization and by cancelling errors, so capability reports should print
both. GSM8K/MATH accuracy overstates reasoning today through saturation and
contamination; GSM-Symbolic's one-variable transform is the minimal probe
that exposes memorization. Every reasoning number is meaningful only at a
pinned effort level, and process supervision remains the harder,
more data-hungry half of the problem.
