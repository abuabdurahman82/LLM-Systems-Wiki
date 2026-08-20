# RAG Evaluation: retrieval, faithfulness, and the pipeline as system
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
RAG evaluation differs from model evaluation because the unit is the
*pipeline* — retriever + generator + prompts + chunking — not a single model.
The metric stack has three layers: retrieval quality (recall@k, MRR),
generation quality against ground truth (faithfulness/groundedness, answer
relevance, context relevance — RAGAS, arXiv:2309.15217 [F]), and end-task
success. Component metrics mislead in both directions: high retrieval recall
can still yield unfaithful answers, and low recall can still yield a right
answer from parametric memory. The SLO number is the end-task pass rate, not
retrieval recall. LLM-as-judge scoring is cheap and correlates with human
judgment but is biased; execution-based oracles are gold where they exist.
Evaluate under distribution shift with canary sets per corpus version, and
report cost per query.

## The unit is a pipeline, not a model
A RAG system is `corpus + chunker + retriever + (ranker) + generator +
prompt`. Any single component can change the answer while the others stay
fixed [I]. Consequences for evaluation [I]:
- A "RAG model score" is meaningless unless every pipeline component is
  pinned (chunk size, top-k, prompt, model checkpoint).
- Improvements can come from any component; attribution requires ablations
  (e.g., swap in a perfect retriever to isolate the generator).
- Two systems with the same generator can differ in accuracy by retrieval
  quality alone [I].

See `../RAG/README.md` for system design; this page is the measurement side.

## The metric stack
| Layer | Metric | Question it answers |
|---|---|---|
| Retrieval | recall@k, MRR [I: definitions] | did the relevant chunk reach the context window? |
| Generation vs ground truth | faithfulness/groundedness (answer supported by the retrieved context), answer relevance (answer addresses the question), context relevance (retrieved chunks are actually relevant) [F: arXiv:2309.15217] | is the answer honest and on topic? |
| End-task | task pass rate against gold answers | did the system solve the user's job? |

**Why component-level metrics mislead [I]:**
- High retrieval recall + low faithfulness: the right chunk was retrieved and
  the model hallucinated anyway (paraphrase drift, synthesis error).
- Low retrieval recall + right answer: the model answered from parametric
  memory — it "worked," but the RAG did nothing, and the answer will rot when
  the corpus changes.
- recall@k and pass rate can therefore move in opposite directions, and
  neither alone is the SLO number.

## Faithfulness: measurement and judging
Faithfulness (groundedness) = the answer's claims are *supported by* the
retrieved context. Standard operationalization: decompose the answer into
sentence-level claims, check each against the retrieved chunks (entailment),
faithfulness = fraction supported [I: the decomposition step; F:
arXiv:2309.15217 for the metric family].

- **LLM-as-a-judge** is the practical faithfulness scorer: cheap, scales to
  full eval sets, correlates with human judgment, but biased (verbosity,
  position, self-preference — see `LLM-as-a-Judge.md`; calibrate against
  human ratings per `Human-Evaluation.md`).
- **Synthetic eval sets** — Q&A pairs generated from the corpus itself — are
  contamination-free *for your corpus*, which is the only contamination you
  control; the questions inherit the generator's biases and need sampled
  human audit [I].
- **Gold-set construction** — human-annotated question -> answer -> source
  triples — is the 20% of the eval that matters: a few hundred gold items
  with known sources support both end-task scoring and attribution ("the
  retriever missed chunk X" vs "the generator garbled it") [I].
- **Survey taxonomy:** the RAG evaluation survey (arXiv:2405.07437 [F])
  organizes the field along retrieval, generation, and end-to-end evaluation
  — a useful map when choosing a metric stack.
- **Self-critique as a measurable signal:** Self-RAG (arXiv:2310.11511 [F])
  trains the model to emit reflection tokens (retrieve / relevant /
  supported / useful); reflection-token accuracy is itself an evaluable
  signal and a free faithfulness probe inside the model's own output [F].

## Distribution shift, cost, and oracle choice
- **Distribution shift:** new documents, new question types. Maintain
  **canary sets per corpus version** — a fixed gold set re-scored on every
  corpus or pipeline change; regression on the canary is the early warning
  [I].
- **Cost-aware eval:** retrieval is cheap, generation is not. Report
  tokens/query and $/query alongside quality — a 20% quality gain that costs
  3x is a different decision than the same quality at the same cost [I].
- **Oracles vs judges:** use execution-based / programmatic oracles
  wherever the answer is checkable (numeric answers, structured outputs,
  code); fall back to judge-based scoring only where no oracle exists, and
  calibrate the judge against the oracle on the overlapping subset [I].
- **Long-context interlock:** retrieval quality interacts with context
  placement — a retrieved chunk landing in the middle of a long prompt hits
  the lost-in-the-middle effect, so RAG eval must control or report chunk
  position within the context [I; see
  `Context-Long-Context-Evaluation.md`].

## Worked example: which number goes in the SLO [E]
A 200-query RAG eval on a fixed corpus version, gold answers known:
- Retrieval recall@5 = **0.90**
- Generation faithfulness (judge) = **0.78**
- End-task pass = **0.71**

Step 1 — which number is the SLO? The user's job is the end task, not the
retrieval. If recall@5 were 0.90 and pass were 0.50, the SLO breach lives in
generation; if recall were 0.50 and pass were 0.71, the breach lives in
retrieval. The SLO number is **0.71**; the component numbers exist to say
*where* to fix [I].

Step 2 — the independence ceiling. Assume end-task success needs *both*
retrieval and faithfulness, acting independently:
- Expected joint success = 0.90 x 0.78 = **0.702** [E: 0.9 x 0.78 = 0.702].
- Observed end-task pass = **0.71** ~ 0.702.

The system operates *at the independence ceiling*: no pass rate is available
unless one of the two components improves, and the binding constraint is the
lower one — faithfulness (0.78), not retrieval (0.90) [I: the independence
assumption is an [A] bound; the [E] arithmetic shows the ceiling]. Invest in
the generator / prompt / context placement, not in a better retriever [I].

## Related
- `../RAG/README.md`
- `Context-Long-Context-Evaluation.md`
- `LLM-as-a-Judge.md`
- `Human-Evaluation.md`
- `Evaluation-Fundamentals.md`

## Key Takeaways
Evaluate the pipeline, not the model: pin every component and use
component-level ablations for attribution. Retrieval recall and pass rate can
move in opposite directions, so the SLO is end-task pass rate, with
component metrics as the diagnostic layer. Use oracles where they exist,
judges where they do not (calibrated), canary sets per corpus version, and
$-per-query next to every quality number.
