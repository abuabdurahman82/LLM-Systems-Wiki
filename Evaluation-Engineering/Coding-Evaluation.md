# Coding Evaluation: from function completion to repo-scale agents
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
Coding evaluation is a ladder: single-function completion (HumanEval) to
contamination-controlled live sets (LiveCodeBench), diverse function-call
benchmarks (BigCodeBench), repo-scale issue resolution (SWE-bench, SWE-bench
Pro), and terminal-CLI agent tasks (Terminal-Bench). Each rung measures a
different capability and misses what the next rung tests. The sampling metric
matters as much as the benchmark: pass@k (at least one of k samples passes)
flatters a stochastic model, while pass^k (all k must pass) matches
production use where each issue is one shot. Unit-test execution is the gold
scorer, but tests are only as good as the test suite. Coding benchmarks now
face a memorization question — SWE-bench Verified may test memory rather than
ability for some models — and a vendor-number problem: leaderboards mix
harness, model, and retry policy into one number.

## The ladder of difficulty
| Benchmark | Unit of task | What it measures | What it misses |
|---|---|---|---|
| HumanEval (arXiv:2107.03374 [F]) | single function, hidden tests | basic function completion | saturated + contaminated [I]; no repo context |
| LiveCodeBench (arXiv:2403.07974 [F]) | continuously refreshed problems | ability free of training contamination | still function-level; refresh window matters |
| BigCodeBench (arXiv:2406.15877 [F]) | functions requiring diverse library calls | realistic API / function-call usage | single-file; no repo navigation |
| SWE-bench (arXiv:2310.06770 [F]) | real GitHub issues, multi-file patches | repo-scale understanding + editing | harness-sensitive; static, so contamination risk |
| SWE-bench Pro (arXiv:2509.16941 [F]) | long-horizon SE tasks in harder, production-grade repos [I] | long-horizon, production-realistic work | even more harness-dependent; costlier to run |
| Terminal-Bench (arXiv:2601.11868 [F]) | CLI / terminal tasks in containers | tool use + agentic execution, not just code | environment-locked; terminal-flavored |

Two cross-cutting findings:

- **HumanEval is no longer a capability signal** — it is function-level,
  saturated for frontier models, and long inside the contamination window
  [I]. It survives as a regression test, not a ranking.
- **SWE-bench is harness-sensitive by construction.** The same model with a
  different agent-computer interface (ACI) produces different scores:
  SWE-agent (Yang et al., arXiv:2405.15793 [F]) shows that interface design —
  file search, edit tools, observation formatting — is a first-order
  variable, not an implementation detail. A SWE-bench number is therefore a
  (model, harness, retry policy) tuple, not a model number [I; see
  `../Harness-Engineering/Model-vs-Harness.md`].

## pass@k vs pass^k: which number matches the job
- **pass@k** = probability that at least one of k samples passes. The
  standard unbiased estimator (Chen et al., HumanEval, arXiv:2107.03374 [F])
  from n samples of which N pass:
  `pass@k = 1 - C(n-k, N) / C(n, N)` [I: estimator convention; see
  `Statistical-Evaluation.md` for CI caveats].
- **pass^k** = probability that all k samples pass = p^k, where p is the
  single-sample pass rate [I].

Hand example [E]: n = 10 samples, k = 5, N = 2 passing.
- C(n-k, N) = C(5, 2) = 10; C(n, N) = C(10, 2) = 45.
- pass@5 = 1 - 10/45 = 1 - 0.2222 = **0.778**. [E: 35/45 = 0.7778]

Production use for SWE-style agents: each issue is one shot (or a fixed,
small retry budget), so the operational metric is pass^k with k = 1 — i.e.,
the single-shot p. The best-of-many flattery of pass@k misstates deployed
behavior. Illustration for a model with single-issue p = 0.5 [E]:
- pass@1 = 0.5
- pass@10 = 1 - 0.5^10 = 1 - 0.0009765625 = **0.999**
- pass^10 = 0.5^10 = 0.0009765625 = **0.001**

Same model, two "numbers" about 1000x apart [E: 0.999/0.001 = 999]. If your deployment samples k times and
accepts any pass, report pass@k; if each task is one shot, report p and treat
pass@k as the offline exploration ceiling [I]. **Cost implication:**
best-of-k sampling multiplies inference cost by roughly k (k generations plus
k scorings); a leaderboard pass@10 number implies ~10x the cost of the
pass@1 configuration [I; see `../Inference/Inference-Metrics.md`].

## Test execution as the gold scorer; the memorization question
Unit tests are the oracle: compile and run the generated code against hidden
tests. This is the strongest available coding scorer — deterministic, cheap,
no judge. Its limits: (1) tests weaker than the spec pass wrong solutions;
(2) a model that overfits the *visible* test behavior passes the suite while
being wrong on the spec; (3) in repo-scale benchmarks the pass-to-pass and
fail-to-pass tests define the "correct patch," so a harness that edits the
tests or the environment can game the oracle [I].

The deeper 2025-26 problem is **memorization**. For some models,
SWE-bench-Verified results test memory, not ability — the model has seen the
issue or the repository during training and reproduces patches rather than
solving [F: arXiv:2512.10218]. Mitigations mirror the reasoning side: fresh
issue releases, repo-variant transforms, and synthetic task scaling. The
synthetic side is now its own field: SWE-smith (arXiv:2504.21798 [F])
generates task variants at scale, SWE-Gym (arXiv:2412.21139 [F]) is a
training environment plus verifier pipeline, and Commit0 (arXiv:2412.01769
[F]) trains on library-generation tasks from scratch. Note the asymmetry:
synthetic *training* sets are useful; synthetic *evaluation* sets need human
audit or they inherit the generator's blind spots [I].

## The vendor-number problem
Public "coding agent" leaderboards mix harness + model + retry policy + test
subset into one number, and they are not comparable across rows unless all
four are pinned [I]. The same model with a different scaffold can move
materially on SWE-bench-style suites [I; see
`../Harness-Engineering/Model-vs-Harness.md` for the decomposition]. A
minimum honest spec (mirroring the agent side): model + checkpoint, harness
version, environment/test-set version, metric (pass@k vs pass^k, with k
stated), number of runs with CI, and cost per resolved issue [I]. See
`../Agents/Coding-Agents.md` for the agent side and
`../Agents/Agent-Evaluation.md` for the trajectory side.

## Pitfalls
- Quoting pass@k without k, n, N, and the sampling policy — an unusable
  number [I].
- Ranking models on a saturated function-level set after a capability jump
  — the ranking sits inside the noise; move up the ladder [I].
- Using best-of-k offline results to predict single-shot production
  quality — the two regimes differ by orders of magnitude (worked example
  above) [I].
- Treating a passing test suite as proof of correctness — the suite is a
  lower bound on the spec, not the spec [I].
- Reading a leaderboard row as a model number when it is a
  (model, harness, retry policy, test subset) tuple [I].

## Related
- `../Harness-Engineering/Model-vs-Harness.md`
- `../Agents/Coding-Agents.md`
- `../Agents/Agent-Evaluation.md`
- `Statistical-Evaluation.md`
- `Benchmark-Contamination.md`

## Key Takeaways
Coding evaluation is a ladder from function to repo to terminal, and each
rung isolates a different capability; HumanEval is saturated and contaminated,
SWE-bench is harness-sensitive. Match the sampling metric to the job:
pass@k for exploration, single-shot p / pass^k for production, and remember
best-of-k multiplies cost by k. Execution oracles are gold where they exist
but only as strong as the test suite, and the open 2026 question is whether a
given repo-scale score measures ability or memory.
