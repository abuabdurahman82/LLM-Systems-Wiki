# Self-RAG — Learning to Retrieve When Needed, and to Critique

`LAST_UPDATED: 2026-08-30` · Status: core page · [F: arXiv:2310.11511
"Self-RAG: Learning to Retrieve, Generate, and Critique through
Self-Reflection" — Asai, Wu, Wang, Sil, Hajishirzi, arXiv 2023-10-17 (title,
author list, date confirmed against the arXiv API record); ICLR 2024
acceptance confirmed 2026-08-30 via OpenReview forum hSyW5go0v8 (venue "ICLR
2024 oral", published 2024-02-01). NOT an outstanding-paper winner: the
official ICLR 2024 Outstanding Paper Awards list (blog.iclr.cc, 2024-05-06)
does not include it [F: award list fetched 2026-08-30]. Code:
github.com/AkariAsai/self-rag [F: repo confirmed via GitHub API,
2026-08-30].]

## 30-Second Explanation
Every RAG variant so far retrieves *always* (one-shot, 03) or *by rule*
(adaptive routing, 23). **Self-RAG** makes the retrieval decisions *learned
signals inside the model itself*: the LLM is trained to emit special
**reflection tokens** that answer four questions — *should I retrieve?*
(*Retrieve*), *is this retrieved passage relevant?* (*IsRel*), *is my
sentence supported by the passage?* (*IsSup*), and *does my answer improve on
the previous one?* (*IsUse*) — and generation is conditioned on emitting good
reflections. The model does not just retrieve; it *critiques its own
retrieval and generation*, and learns (via RL) to do that critique
calibratedly. [F: the four reflection token types, per the verified paper]

## The four reflection signals (precisely)
Self-RAG trains the model to interleave four special token types with normal
generation [F: per arXiv:2310.11511]:
| Token | Question it answers | Emitted when |
|---|---|---|
| **Retrieve** | "should I retrieve at all, and what should I retrieve?" | at the point in generation where more evidence would help (per-sentence decision) |
| **IsRel** | "is this retrieved passage relevant to my current context?" | after each retrieved passage is inserted |
| **IsSup** | "is my next sentence *supported by* the passage just cited?" | per generated sentence (the faithfulness signal, made self-checking) |
| **IsUse** | "is my whole answer *useful* (complete/helpful) for the question?" | at the end of the answer (the utility signal) |

The design consequence [I: the architectural point]: the four signals turn
the RAG pipeline into a *model-internal control loop* — the same loop
agentic RAG (24) runs with *external* tool calls, but here the loop's
decisions are the model's own emissions, trained end-to-end. No external
router, no reflection LLM pass: the critique is in the logits.

## How it is trained (the mechanism, not the folklore)
[F: per the verified paper]:
1. **Reflection-token supervision**: the model is fine-tuned (SFT + RL) with
   a reward that favors emission of *correct* reflection tokens — Retrieve
   when retrieval helps, IsRel=1 only when the passage is actually relevant,
   IsSup only for entailed sentences, IsUse for genuinely complete answers.
   The labels are produced by an auxiliary *critic model* (a second model
   trained on the same signal) — the "self" in Self-RAG is a trained critic,
   not the generator's untrained opinion.
2. **Inference with reflection weighting**: at generation time, the model
   *samples* continuations and *weights* them by their reflection-token
   likelihood — a continuation that emits IsSup=0 (unsupported sentence) is
   down-weighted even if it is fluently generated. The model effectively
   does a *search over its own outputs conditioned on its own critique*.
3. **No retrieval in the parametric case**: when Retrieve=0 (the question is
   answerable from parametric memory), the model answers without retrieval —
   the "when to retrieve" decision (23's routing problem) is learned, not
   thresholded.

## What this buys (and the honest limits)
Buys [F: the paper's reported direction — improvements over vanilla RAG on
open-domain QA benchmarks, largest when the question mix includes
"should-not-retrieve" cases; specific benchmark numbers live in the research
bank's final record]:
- **Adaptive retrieval without an external router**: the Retrieve decision is
  per-step and learned — the 54 "when NOT to retrieve" question, answered by
  the model itself.
- **Self-checking faithfulness**: IsSup is the 45 faithfulness measurement
  *inside* the generation loop — the model flags its own unsupported
  sentences (and inference weighting suppresses them).
- **Graceful non-retrieval**: on parametric-memory questions, the cost is the
  cheap path (no retrieval round-trip).
Limits [I: the honest read — do not generalize beyond the paper]:
- **The critique is only as calibrated as the training data**: on
  out-of-distribution domains, the IsSup/IsRel signals degrade; the paper's
  results are on its training distribution.
- **Reflection-weighted sampling costs inference**: the inference procedure
  (sample + weight by reflections) is more expensive than one forward pass —
  a latency/cost item 44 does not track in the vanilla case.
- **It is a model, not a system**: Self-RAG does not do multi-hop loops (27),
  source routing (36), or tool use (24) — it is the *single-retrieval-step*
  case, made adaptive. Compose it with the system patterns; it is not a
  replacement for them.

## Self-RAG vs the "learned retrieval control" family
| | Self-RAG (21) | CRAG (22) | Adaptive-RAG (23) | Agentic (24) |
|---|---|---|---|---|
| Where the decision lives | inside the model (reflection tokens) | a retrieval evaluator + external actions | a separate classifier/router model | an agent loop (external) |
| When-to-retrieve | learned per-step (Retrieve token) | always retrieve, then evaluate/correct | learned classifier (complexity routing) | per-step agent judgment |
| Evidence critique | learned (IsRel/IsSup tokens) | an LLM evaluator (retrieval quality) | — (the router is pre-retrieval) | reflection inside the loop |
| Training required | yes (SFT+RL on reflections) | no (an off-the-shelf evaluator) | yes (a classifier on complexity labels) | usually no (prompt + tools) |
| Cost profile | extra inference-time sampling | one evaluator pass | one classifier pass | k LLM loop passes |

The pattern across the four [I: the 45/54 design insight]: *every* learned or
rule-based retrieval-control system is trading a different slice of the same
cost/quality frontier — Self-RAG pays in *training + inference sampling*,
Adaptive-RAG in *a classifier call*, CRAG in *an evaluator call*, agentic in
*the whole loop*. The right one is a property of your query mix and SLOs
(54), not a universal ranking.

## Key Takeaways
1. Self-RAG emits four learned reflection tokens (Retrieve/IsRel/IsSup/IsUse)
   that make retrieval + critique model-internal [F: arXiv:2310.11511, ICLR
   2024].
2. Inference weights continuations by their reflection likelihood — the model
   suppresses its own unsupported sentences at generation time.
3. It answers "when to retrieve?" by learning, not by rule — the 23/54
   routing question, internalized.
4. Its cost is training + inference-time sampling; it is the
   single-retrieval-step case — compose, don't replace, the system patterns
   (24/27/36).
5. Calibrate expectations to the paper's distribution: out-of-domain critique
   quality degrades; the IsSup signal is a faithfulness *proxy*, not a
   guarantee (45).

## Related
[22 CRAG](22-corrective-rag.md) · [23 Adaptive-RAG](23-adaptive-rag.md) ·
[24 agentic](24-agentic-rag.md) · [45 evaluation (faithfulness)](45-rag-evaluation.md) ·
[54 decision tree](54-which-rag-should-i-use.md) · `../Post-Training/Alignment-RLHF.md`
(the RL side of the training)
