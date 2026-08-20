# Evaluation & Benchmarks
`LAST_UPDATED: 2026-08-19` · Status: core section

## 30-Second Explanation
A benchmark measures *one slice* of capability under *one protocol*. The discipline
is knowing what each benchmark tests, what it does NOT test, and how scores can
mislead (contamination, saturation, harness effects). A number without its
protocol is a rumor. **The engineering of that discipline — design, scoring,
statistics, judge calibration, SLOs — is now a first-class section:
`../Evaluation-Engineering/README.md`.** This page is the benchmark *reference*.

## The two failure modes of evaluation
1. **Contamination** — the test set leaks into training data → inflated scores that
   don't transfer. (Especially acute for static benchmarks; MMLU/GPQA are
   contaminated-era.) Deep treatment:
   `../Evaluation-Engineering/Benchmark-Contamination.md`.
2. **Saturation** — the benchmark's ceiling is reached; it no longer discriminates
   between strong models (MMLU is effectively saturated for frontier models).

## Benchmark families (`Benchmarks/README.md` has the per-benchmark detail)
| Family | Examples | Tests | Does NOT test |
|---|---|---|---|
| Knowledge/multi-task | MMLU, MMLU-Pro, GPQA | breadth, STEM reasoning | agentic, long-horizon, tool use |
| Math/reasoning | GSM8K, MATH, AIME | step reasoning, test-time compute | faithfulness of CoT |
| Code | HumanEval, MBPP | single-file coding | repo-scale SWE |
| SWE / agentic coding | SWE-bench, SWE-bench Verified, SWE-bench Pro, Terminal Bench | multi-file, real repos, terminal | non-coding tasks |
| Long context | LongBench, RULER, NIAH, Beam | retrieval within long input | *usable* length (lost-in-middle) |
| Agents / tools | GAIA, AgentBench, WebArena, tau-bench, BrowseComp, OSWorld | tool use, multi-step, web/computer | cost, safety |
| Multimodal | MMMU, MMBench, MathVista, ScreenSpot Pro, OmniDocBench | vision+text grounding | video temporal |
| Safety | AgentDojo, HarmBench, jailbreak suites | injection/refusal/robustness | capability |
| Open-ended | Chatbot Arena / LMArena, WildBench | human preference | reproducibility, cost |
| Live | LiveBench, HLE (Humanity's Last Exam) | resist contamination | — |

## 2026 evaluation shifts (observed in live sources, [F: vendor/HF])
- **Effort-level / thinking-budget** evaluation is now standard: the same model
  scores differently at different "effort" settings. A number without its effort
  level is incomplete. (`../Evaluation-Engineering/Reasoning-Evaluation.md`)
- **Agentic benchmarks dominate** the frontier narrative. They are
  harness-sensitive — a number is a model+harness+environment triple.
  (`../Evaluation-Engineering/Agent-Tool-Use-Evaluation.md`)
- **Vendor-reported numbers are the norm** and are *not independently
  reproduced*; treat as claims. (This wiki tags them [F: vendor].)
- **Reproducibility crisis**: the research output now outpaces verification;
  versioned, self-describing eval protocols are the mitigation.
  (`../Evaluation-Engineering/Evaluation-Fundamentals.md`)

## Good evaluation practice (methodology)
1. Report the **protocol**: model version, quant, context limit, sampling,
   effort level, harness, concurrency, retries.
2. Report **percentiles** (P50/95/99) and **CIs**, not just means.
3. Separate **capability** (can it) from **reliability** (does it every time)
   from **cost** (tokens/$).
4. Distinguish **capability benchmark** vs **SLO** (goodput at latency budget).
5. Watch for **contamination/saturation**; prefer live/holdout sets at the
   frontier.

The full method — statistical tests, judge calibration, SLO test design,
red-team protocol — is in `../Evaluation-Engineering/` (start with
`../Evaluation-Engineering/Evaluation-Fundamentals.md`).

## Related
`Benchmarks/README.md` · `Frontier-Models/README.md` ·
`Open-Source-Models/README.md` · `../Evaluation-Engineering/README.md`.

## Key Takeaways
Benchmarks are protocols, not numbers. Know what each tests and what it
misses; report the full protocol; and treat vendor frontier numbers as claims
until independently reproduced. For the engineering of evaluation itself,
go to `../Evaluation-Engineering/`.
