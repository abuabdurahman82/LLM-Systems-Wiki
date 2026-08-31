# 14 — Data Generation, Verification, Cleaning, and the Failure Modes
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
In response/reasoning distillation, the dataset *is* the method — so this page is the
production discipline behind it: the full generation pipeline, verification patterns,
cleaning (dedup, contamination, verbosity, language mixing), what degrades first in
students, hallucination/calibration/safety transfer, model lineage, and the complete
failure-mode catalog with mitigations. Terminology guard: **dataset distillation** is a
different field (compressing datasets, not models) — see the box at the end.

## The production pipeline

```
Seed dataset (prompts)
      ↓
Prompt generator (augmentation, difficulty ladder)
      ↓
Teacher LLM × N samples per prompt
      ↓
Filtering (format, length, language, dedup)
      ↓
Verification (tests / math / reference / judge / RM)
      ↓
Dedup (exact → semantic) + contamination check
      ↓
Difficulty scoring ─┬→ curriculum ordering
Quality scoring ────┘
      ↓
Student training
```

Every arrow is a quality multiplier or a quality leak; treat each as a pipeline stage
with owners, metrics, and thresholds [I: engineering posture].

## Synthetic-data cleaning checklist

| Stage | What to catch | Practical method |
|---|---|---|
| Exact dedup | identical samples | hash (normalized text) |
| Semantic dedup | paraphrase clusters | embedding sim + clustering threshold |
| Benchmark contamination | eval answers inside training data | → §contamination below |
| Prompt leakage | eval prompts rephrased as training prompts | semantic near-dup vs eval set |
| Answer leakage | answer/flag embedded in prompt or trace preamble | regex + reviewer spot checks |
| Malformed outputs | broken schema, truncation, tool-parse errors | schema validators |
| Reasoning loops | circular repetition, degeneration | repetition metrics (n-gram self-sim), length thresholds |
| Language mixing | mid-trace language switches | per-segment language ID |
| Excessive verbosity | trace length ≫ problem difficulty | learned difficulty-vs-length model; percentile cuts |

## Contamination (the integrity section)

Teacher-generated data can accidentally contain benchmark answers — the teacher may
have memorized eval sets, and its outputs smuggle them into your student's training set,
inflating results and lying about capability.

**Detection workflow (recommended order):**
1. **Source tracking:** record, for every training sample, its lineage (prompt source,
   generator, settings) — enables targeted quarantine (`19` §lineage).
2. **n-gram matching:** 8–13-gram overlap between training samples and eval sets
   (GPT-3-style 13-gram standard [F: arXiv:2005.14165 practice]); flag & drop.
3. **Semantic matching:** embedding near-dup to catch paraphrased contamination.
4. **Holdout canaries:** insert unique canary strings into evals; if a student "knows"
   them, the pipeline leaks.
5. **Order-of-magnitude sanity:** if student ≈ teacher on a benchmark but ≪ teacher on
   fresh/unreleased variants, suspect contamination
   [cross-link: `Evaluation-Engineering/Benchmark-Contamination.md` — the wiki's deep
   treatment; `Benchmarks/README.md` for benchmark saturation context].

## What degrades first (catastrophic-knowledge-loss catalog)

Empirical pattern across distillation projects [I: synthesis; per-project deltas vary
with data mix — measure yours]:

| Capability | Typical degradation | Why |
|---|---|---|
| Factual knowledge / long-tail | **first to go** | capacity-bound; traces rarely re-teach facts |
| Multilingual ability | early | unless traces are multilingual, English dominates |
| Calibration | early & silent | see §calibration |
| Rare-domain knowledge | early | long-tail again |
| Math/reasoning from traces | most durable | procedural, densely re-taught by traces |
| Coding | durable *if* traces include it | verifier-backed data is dense |
| Long-context behavior | silently degraded | most trace data is short (→ §long-context) |
| Tool use | preserved only if trained | behavior data must exist |
| Safety/refusal | **not inherited by default** | see §safety |

**Long-context capability:** a student distilled from short traces will lose effective
context discipline — positional robustness and long-range attention are trained
behaviors. Mitigations: include long-document QA/summarization traces; extend training
length progressively; verify with needle/haystack-style evals before shipping
[Research Result + I]. KV-cache implications of the smaller student →
`KV-Cache/README.md`.

## Distillation and hallucination

- **Can reduce it:** verified traces teach *grounded* reasoning; tool-use traces teach
  checking instead of guessing (→ `13`).
- **Can copy it:** unverified teacher errors become student training targets with
  teacher-grade confidence in the text — the student cannot tell (→ `07` §teacher
  hallucinations).
- **Amplification risk:** a small student with less factual knowledge may hallucinate
  *more* on facts its teacher knew — knowledge is capacity-bound, style is not
  [I: consistent with the capacity-gap literature]. Factuality filtering of data beats
  post-hoc fixes.

## Distillation and calibration

Does KD transfer or damage calibration? Both are observed; the honest summary:

- **Distribution-KD tends to preserve calibration better** — the student matches
  teacher uncertainty when trained on full distributions (temperature-soft targets)
  [Research Result: the original KD motivation includes soft-label information
  transfer, arXiv:1503.02531].
- **Response-KD tends to miscalibrate** — the student learns the teacher's *sampled*
  style but its own accuracy differs; confidence and accuracy decouple.
- **Measure:** ECE (expected calibration error) / post-hoc temperature scaling on the
  student, per domain. Make it a release gate alongside accuracy
  [method → `Evaluation-Engineering/Statistical-Evaluation.md`].

## Distillation and safety

**Capability distillation ≠ alignment distillation.** Refusal behavior, safe-completion
policy, and jailbreak robustness do not transfer via capability data — they require
explicit alignment data and evaluation:

- Include safety-relevant traces (refusals, safe completions, policy boundaries) as a
  *deliberate* dataset component.
- A student distilled on open-web teacher outputs can be *less* safe than either
  teacher or base if safety data is absent [I: consistent with post-training
  literature; treat as strong prior].
- Evaluate adversarially (red-team suites) before release — safety is not an accuracy
  number [→ `Evaluation-Engineering/Safety-Red-Teaming.md`, `Safety/README.md`].

## Dataset distillation ≠ knowledge distillation (terminology box)

| | Knowledge distillation | Dataset distillation |
|---|---|---|
| Compresses | a model's capability | a dataset into a tiny synthetic one |
| Teacher model | central | not required (optimization-driven) |
| Output | a smaller model | a small synthetic dataset |
| Goal | cheap inference | cheap/faster training |
| This wiki | this whole section | one paragraph, on purpose |

Dataset distillation (Wang et al. lineage: image-set condensation via bi-level
optimization) trains *models on condensed data*; it is not a model-compression method
and does not appear elsewhere in this section [F: DC/DSA literature lineage].

## Model lineage (the template a distilled model must ship with)

```
Student base model:        <name, HF id, license>
Teacher model:             <name, version/hash, license, access mode>
Prompt dataset:            <source, size, license, contamination status>
Generation settings:       <temp, top_p, N samples, date range>
Filtering/verification:    <rules, pass rates, verifier versions>
Training code/config:      <repo, commit, framework, seeds, hardware>
Evaluation:                <benchmarks, harness, settings, results, date>
Known limitations:         <what degraded, what was tested>
Licenses/ToS:              <teacher-output-use permission, student license>
```
→ machine-readable template in `19-production-design.md` §lineage.

## Failure modes (the catalog)

| # | Failure mode | Symptom | Mitigation |
|---|---|---|---|
| 1 | Parroting teacher style | formatting quirks dominate content | style normalization; mixed-human data |
| 2 | Reasoning collapse | traces degenerate to templates | diversity requirements; length/loop filters |
| 3 | Overlong reasoning | cost blowup, latency | length-by-difficulty targets; concise-trace selection |
| 4 | Factual knowledge loss | QA/MMLU drops | mix in knowledge-dense data; knowledge-distillation stages |
| 5 | Exposure bias | strong on teacher data, drifts in production | on-policy phases (→`10`) |
| 6 | Teacher hallucination transfer | confident nonsense | independent verification (→`07`) |
| 7 | Mode collapse (multi-teacher) | one teacher's style wins | per-domain weighting; normalization |
| 8 | Catastrophic forgetting | base skills vanish after SFT | replay data; LR/epochs discipline; LoRA when apt |
| 9 | Vocabulary mismatch | KD losses never converge / NaNs | response-KD across families; tokenizer checks (→`05`) |
| 10 | Capacity mismatch | student can't fit teacher | intermediate teacher; revise student size (→`01`) |
| 11 | Synthetic contamination | inflated evals | §contamination workflow |
| 12 | Overfitting teacher quirks | benchmark-shaped behavior | fresh-prompt holdouts; independent harnesses |

## Myths vs reality

> **Myth:** "Distillation is the same as quantization."
> **Reality:** different axes — new smaller model vs reduced precision of the same one
> (→ `16`).

> **Myth:** "A 70B distilled into 7B is a 7B version of the same model."
> **Reality:** the student approximates *selected* capabilities within its capacity;
> long-tail knowledge and calibration typically don't make the jump.

> **Myth:** "More teacher data always makes a better student."
> **Reality:** quality, diversity, and verification dominate raw volume; duplicated
> low-grade traces teach templates (→ `07`).

> **Myth:** "Just save the teacher's chain of thought and train on it."
> **Reality:** unverified CoT = confident errors + style transfer; verify first.

> **Myth:** "Distillation preserves safety behavior."
> **Reality:** safety is a dataset and evaluation decision — never a side effect (§safety).

## Related
- `07-reasoning-distillation.md` — verification patterns (tests, checkers, judges)
- `10-on-policy-distillation.md` — the exposure-bias fix
- `Evaluation-Engineering/Benchmark-Contamination.md` — the wiki's contamination deep dive
- `Evaluation-Engineering/Safety-Red-Teaming.md` — adversarial safety evaluation
- `KV-Cache/README.md` — long-context serving implications
- `19-production-design.md` — lineage as a production artifact

## Key Takeaways
- The dataset is the method: pipeline stages (verify → dedup → decontaminate → balance)
  are where distillation quality is actually won.
- Factual knowledge, multilingual, calibration, and safety degrade *first and silently*;
  procedural skills from verified traces last.
- Long-context and tool-use behaviors must be re-taught explicitly — they are not
  free byproducts of short-trace distillation.
- Ship lineage with the model; it is the only way to reproduce, audit, and quarantine.
