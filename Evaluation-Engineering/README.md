# Evaluation-Engineering — LLM Evaluation Engineering
`LAST_UPDATED: 2026-08-19` · Status: core section

## 30-Second Explanation
Evaluation is the discipline of turning a model's behavior into a number you can
trust. Most of the engineering is in the *protocol*, not the model: pick the right
unit of measurement (output / trajectory / pipeline / system), pin the full
scoring stack, control contamination and saturation, report variance and cost,
and calibrate whatever scorer you use (exact match, execution, human, LLM judge)
against ground truth. A number without its protocol is a rumor.

## The domain map
| Page | Covers |
|---|---|
| `Evaluation-Fundamentals.md` | What eval measures; units; the eval stack; capability/reliability/cost; protocol spec |
| `Model-Evaluation.md` | Benchmark families for raw models; score hygiene; reading model cards |
| `Benchmark-Design.md` | Task→dataset→scorer design; construct validity; lifecycle; synthetic data |
| `Benchmark-Contamination.md` | Contamination & saturation: detection, mitigation, retirement |
| `Reasoning-Evaluation.md` | Answer vs process; CoT faithfulness; effort-level confounds |
| `Coding-Evaluation.md` | HumanEval → SWE-bench → Terminal-Bench; pass@k vs pass^k; execution oracles |
| `Agent-Tool-Use-Evaluation.md` | Trajectories, environments, harness effects, cost-per-success |
| `Context-Long-Context-Evaluation.md` | Usable vs advertised length; NIAH limits; RULER/LongBench; memory over turns |
| `RAG-Evaluation.md` | Pipeline-as-system; retrieval + faithfulness; RAGAS; SLO number choice |
| `Harness-Serving-Evaluation.md` | SLOs, goodput, model-under-load; accuracy at deployed precision |
| `Safety-Red-Teaming.md` | Refusal, jailbreaks, agentic harm; ASR/over-refusal; red-team methodology |
| `Multimodal-Evaluation.md` | Vision/OCR/grounding/video; eval-infrastructure failures; modality gap |
| `LLM-as-a-Judge.md` | Judge paradigms, bias taxonomy, calibration, when not to use judges |
| `Human-Evaluation.md` | Annotation design, rater reliability (kappa), hybrid pipelines, cost |
| `Statistical-Evaluation.md` | CIs, Wilson/McNemar/bootstrap, judge agreement, multiple comparisons |

## How this section relates to the rest of the wiki
- `../Evaluation/README.md` + `../Benchmarks/README.md` — the *benchmark reference*
  (what each benchmark tests / does not test). This section is the *engineering
  discipline* around benchmarks: how to design, run, score, and read them.
- `../Agents/Agent-Evaluation.md` — the agent-specific page; this section
  generalizes it and adds the statistical and scorer-calibration layers.
- `../Inference/Inference-Metrics.md` — serving metrics; `Harness-Serving-Evaluation.md`
  turns those metrics into SLO tests.
- `../Context-Engineering/`, `../RAG/`, `../Safety/` — the capability domains this
  section measures; the cross-links go both ways.

## The five rules (summary)
1. **Pin the protocol** — model+checkpoint+quant, sampler, context limit, effort
   level, retries, harness, environment version, scorer, aggregation. Anything
   unpinned is a hole.
2. **Match the unit to the question** — output (model), trajectory (agent),
   pipeline (RAG), system (serving). Different units are not comparable.
3. **Report variance and cost** — mean ± CI and $/success, not bare means.
4. **Check the scorer** — every scorer (judge, human, test oracle) is calibrated
   against ground truth; judge-human agreement and test-oracle failure modes
   are reported alongside the score.
5. **Watch the clock** — contamination and saturation move the meaning of the
   number; prefer live/holdout sets at the frontier and log the dataset version.

## Key Takeaways
Evaluation is a stack — task, dataset, scorer, aggregation, report — and each
layer can silently move the number. The discipline is pinning every layer,
reporting variance + cost, and calibrating the scorer. Benchmark *reference*
lives in `../Benchmarks/`; benchmark *engineering* lives here.
