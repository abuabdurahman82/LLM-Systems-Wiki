# RAG Evaluation — Measuring the Pipeline, Not the Model

`LAST_UPDATED: 2026-08-29` · Status: core page · Framework facts [F] confirmed
this pass against arXiv/GitHub (RAGAS arXiv:2309.15217; ARES arXiv:2311.09476,
NAACL 2024); metric definitions are standard IR (06).

## 30-Second Explanation
RAG evaluation fails when it treats the system as a model: "the answer scored
0.7" is not a diagnosis. The pipeline has **two independently failing layers**
— retrieval ("did the right evidence make the top-k?") and generation ("given
this evidence, is the answer faithful and complete?") — and a third,
end-to-end layer (task success, latency, cost). Each layer has its own
metrics, its own failure signature, and its own fix. Evaluate them
separately, gate on the end-task SLO, and treat the component metrics as
*diagnostics* — because high retrieval recall can still produce unfaithful
answers, and a retrieval miss can still produce the right answer from
parametric memory [I: the two-directional mislead; the core argument of this
page].

## Layer 1 — Retrieval quality (measurable without any LLM)
The golden set (46) provides, per question: the expected evidence (chunk/doc
ids) and, where useful, graded relevance. Standard IR metrics [F: standard
definitions — 06's foundation; 02's lineage for the ranking-metric tradition]:
| Metric | Definition | What it tells you |
|---|---|---|
| **Recall@K** | per query, \|expected evidence ∩ top-K\| / \|expected evidence\|, averaged over queries | "did we find *all* the expected evidence?" — the headline retrieval number; item-level, so a multi-evidence question that surfaces 1 of 2 chunks scores 0.5 |
| **Precision@K** | fraction of top-K items that are relevant | "is the net noisy?" — context-pollution signal (41) |
| **MRR** (mean reciprocal rank) | mean of 1/(rank of first relevant) | "how far down is the first hit?" — the reranker's job metric (14) |
| **NDCG@K** | discounted cumulative gain with graded relevance | "does the ordering respect the *degree* of relevance?" — the metric for graded golden sets |
| **Hit Rate@K** (success@K) | binary per query: was *any* expected evidence in top-K? | the coarsest, binary version of the above (1 of 2 chunks surfaced still counts as a "hit"); good for dashboards (50) |

Notes on usage [I: the discipline]:
- **K must be your operating K** (the k that gets packed, after rerank —
  typically 10, not the ANN's 100). Recall@100 measures the *retriever*;
  recall@10 measures the *system*.
- **Metric implementations are not equivalent**: "faithfulness" and
  "context precision" mean different things in different frameworks — e.g.
  RAGAS's *context precision* is reference-free and positions-aware, while
  other stacks' "context precision" (or "relevance") is a plain
  relevance-coverage score without position discounting [I: the difference is
  real and framework-specific; pin the exact definition you are using before
  comparing numbers across tools or across time].
- **Retrieval metrics are cheap and fast**: they run on the golden set with
  no LLM judge — which is why they belong in *every* index/model change's CI
  gate (51), not in a monthly report.

## Layer 2 — Generation quality (given the retrieved context)
Four properties, each a separate measurement [I: the decomposition is standard
across the frameworks below — definitions are not identical across them]:
| Property | Question | Typical measurement |
|---|---|---|
| **Faithfulness / groundedness** | Is every claim in the answer *supported by the provided context*? | claim decomposition → entailment check per claim against the context (LLM judge or model) |
| **Correctness** | Is the answer right *against the expected answer* (ground truth)? | exact/fuzzy match or LLM-judge similarity to the gold answer |
| **Completeness** | Does the answer cover *all* the required parts (multi-part questions)? | per-claim/per-part coverage check |
| **Relevance** | Does the answer address *the question asked* (not a neighboring one)? | LLM-judge or embedding-similarity to the question |

Faithfulness is the RAG-specific one: it is possible to be *faithful and wrong*
(context says X, the gold says Y, the model reports X faithfully) and to be
*right and unfaithful* (parametric memory supplied the correct fact the
retrieval missed). The two failures have different fixes (47: retrieval vs
generation layer) — which is exactly why they must be measured separately.

**LLM-as-judge caveats** (the standing discipline — `../Evaluation-Engineering/LLM-as-a-Judge.md`):
judge bias (position, verbosity, self-preference), judge/model divergence
(the judge's notion of "faithful" ≠ the task's), and the cost/latency of a
judge pass per answer. Use a *different, cheaper* model for the judge where
possible; calibrate the judge against a human-labeled subset before trusting
its scale [I: the standard practice; the wiki's eval section has the full
treatment].

## Layer 3 — End-to-end (the SLO layer)
The number the business actually sees [I: the SLO decomposition — 50's
observability feeds it]:
- **Task success / answer correctness** on the golden set (the end-task
  pass-rate — the SLO number, not a component metric).
- **Citation accuracy**: does the cited document actually support the cited
  claim? (the 48 citation-manipulation check, run continuously).
- **Latency**: TTFT + e2e, p50/p95/p99 (43's prefill-dominated shape).
- **Cost**: per request, per stage (44).
- **Goodput**: successful answers per unit cost/latency budget — the
  reliability-section's metric, applied here (`../Production-Operations/`).
- **Refusal calibration**: on the *unanswerable* slice of the set (46), does
  the system say "I don't know" instead of answering? Over-refusal and
  under-refusal are both failures.

## The frameworks (what exists, what they do)
| Framework | Origin (verified this pass) | Core idea |
|---|---|---|
| **RAGAS** | arXiv:2309.15217 "Ragas: Automated Evaluation of Retrieval Augmented Generation" (Es et al., 2023); repo `vibrantlabsai/ragas` (Apache-2.0) [F] | LLM-pipeline metric set: faithfulness, answer relevance, context relevance, context precision (all reference-free); context recall *and* correctness-style metrics *require* a ground-truth reference [F: metric semantics per the repo] — a common default stack in production, though "de-facto default" is a positioning claim, not a measured one [I] |
| **ARES** | arXiv:2311.09476 "ARES: An Automated Evaluation Framework for RAG Systems" (Saad-Falcon, Khattab, Potts, Zaharia; NAACL 2024) [F] | *prediction-powered inference*: cheap synthetic + few human labels → statistically grounded evaluation with confidence intervals; addresses the "LLM judges are noisy" problem head-on [F] |
| **DeepEval** | `confident-ai/deepeval` (repo confirmed this pass; details: pending final bank entry) [F: repo exists; specifics UNVERIFIED] | pytest-integrated eval framework; G-Eval (a judge-prompt framework for custom metrics) [UNVERIFIED this pass — the specific G-Eval framing is repo-level detail] |
| **TruLens** | `truera/trulens` (repo confirmed this pass; specifics: pending final bank entry) [F: repo exists; specifics UNVERIFIED] | "feedback functions" over (input, retrieval, output) triples; lineage: the OpenAI Evals experiment, spun out [UNVERIFIED this pass — the lineage claim is not established from the repo alone] |
| **LangSmith / LangSmith-class** | vendor platform [I: positioning] | tracing + eval on the pipeline (the 50 trace, instrumented) — evaluation-as-observability |

Do **not** assume these are equivalent: RAGAS gives you *metric definitions*;
ARES gives you *statistical methodology* (how many labels, what CI);
DeepEval gives you *test ergonomics*; TruLens gives you *feedback-function
composition*; LangSmith-class gives you *traces to evaluate*. A production
evaluation is usually: RAGAS-style metrics + ARES-style methodology +
framework ergonomics + the 50 trace as the data substrate [I: the composition
pattern].

## The evaluation workflow (what "evaluating RAG" means operationally)
1. **Build the golden set** (46): 100–500 questions with expected evidence +
   expected answer + the multi-hop/contradiction/unanswerable slices.
2. **Measure both layers** on every change (index version, embedder, chunker,
   prompt): retrieval metrics (no LLM — fast, CI-gate) + generation metrics
   (judge — slower, sample-based).
3. **Attribute failures** (47): retrieval-miss vs ranking-cut vs context-gap vs
   synthesis-error — the layer determines the fix.
4. **Gate deployments**: index/model changes ship when retrieval metrics do
   not regress AND end-task pass-rate holds (51's release discipline).
5. **Canary over time** (48): probe documents + probe queries with
   expected-answer monitors — the *continuous* version of the golden set
   (detects poisoning, staleness, drift).
6. **Calibrate the judge** against a human-labeled slice before trusting
   scale [I: the 45↔human-eval link, `../Evaluation-Engineering/Human-Evaluation.md`].

## Key Takeaways
1. Two independently failing layers + an end-to-end layer: retrieval
   (Recall@K/MRR/NDCG), generation (faithfulness/correctness/completeness/
   relevance), task success (SLO + citations + latency + cost + refusal).
2. Judge the retrieval layer *without* an LLM — it is fast enough for every
   change's CI gate.
3. LLM-judge metrics are not interchangeable across frameworks: pin
   definitions, calibrate against humans, use a cheaper judge model.
4. The frameworks compose: RAGAS-style metrics + ARES-style statistics +
   ergonomic runners + 50's trace as substrate.
5. Evaluation is a *workflow* (set → both layers → attribution → gate →
   canary → calibration), not a score.

## Related
[46 golden datasets](46-rag-golden-datasets.md) · [47 failure taxonomy](47-rag-failure-modes.md) ·
[50 observability](50-rag-observability.md) · [48 security (canaries)](48-rag-security.md) ·
[51 production (gates)](51-production-rag-reference-architecture.md) ·
`../Evaluation-Engineering/RAG-Evaluation.md` · `../Evaluation-Engineering/LLM-as-a-Judge.md`
