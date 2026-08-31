# Adaptive RAG — Route by Question Complexity

`LAST_UPDATED: 2026-08-29` · Status: core page · [F: arXiv:2403.14403
"Adaptive-RAG: Learning to Adapt Retrieval-Augmented Large Language Models
through Question Complexity" — Soyeong Jeong, Jinheon Baek, Sukmin Cho,
Sung Ju Hwang, Jong C. Park; NAACL 2024 (venue confirmed this pass via the
arXiv comment field).]

## 30-Second Explanation
Not every question needs the same retrieval machinery. "What year was the
Paris Peace Treaty?" needs one retrieval (or none); "Compare the failure
modes of X and Y across these three incidents" needs multi-hop,
iterative retrieval. **Adaptive RAG** learns a *router*: a small classifier
reads the question, assigns it a complexity class, and sends it to the
corresponding pipeline — no retrieval, single-step retrieval, or
iterative/reasoning retrieval. The bet: matching the pipeline to the question
beats a one-size-fits-all pipeline on *both* quality and cost [F: the
complexity-routing design, per the verified paper].

## The routing (the paper's design)
[F: per arXiv:2403.14403]:
```
question
  ↓ COMPLEXITY CLASSIFIER (a small LM / classifier, trained or prompted)
  ├── Level 1: simple factual → parametric answer OR single cheap retrieval
  ├── Level 2: moderate       → single-step RAG (retrieve → generate, 03)
  └── Level 3: complex         → iterative / reasoning retrieval
                                  (multi-step RAG — the 26/27 loop)
```
The classifier is the whole system: one cheap call whose decision selects the
*downstream compute budget*. The paper's reported direction [F: as verified
in the research bank]: accuracy gains over both no-retrieval and
always-retrieve baselines, concentrated in the question classes where the
wrong pipeline hurts — too much retrieval on simple questions (cost +
context pollution) and too little on complex ones (retrieval miss, 47).

The complexity labels come from *question-type analysis*: the paper defines
complexity by the structure of the question (single fact / single
document / multi-document multi-step) [F: the labeling scheme per the paper —
the exact label set is in the research bank record; the three-level
coarse-to-fine routing is the load-bearing design].

## Why "always retrieve" and "never retrieve" both fail
The routing argument is a cost/quality frontier, not a folklore [I: the
framing; the paper's measurements support it]:
| Question class | Always-retrieve | Never-retrieve | Adaptive (right pipeline) |
|---|---|---|---|
| Simple, in-parametric-memory | pays retrieval latency+cost for zero gain; retrieved noise can *contaminate* the parametric answer | right | single cheap retrieval or none |
| Simple, in-corpus | works, over-served | fails (corpus knowledge) | single-step RAG |
| Complex multi-hop | *one* retrieval — structurally insufficient (26) | fails | iterative retrieval (the loop earns its cost) |
The asymmetry is the point [I]: over-retrieval costs money and can hurt
quality (the retrieved-but-irrelevant chunk, 41); under-retrieval costs the
*answer* (the unrecoverable miss, 47). A router is the only way to get the
right amount for each class in one system.

## The router problem (where adaptive RAG lives or dies)
The entire system is bounded by the classifier [I: the standing risk — the
same discipline as 22's evaluator]:
1. **Misdetection of complexity**: a question that *looks* simple but needs
   two hops (the "which company's founder…" trap, 26) routed to single-step
   → the confident-incomplete failure, now *attributable to the router* (a
   new failure layer in 47: routing failure — see 36's "right source not
   consulted" twin).
2. **Training-label leakage**: the complexity labels are human- or
   LLM-assigned on a dev set; a router that memorizes *phrasing correlates*
   ("why" vs "what") rather than true complexity misroutes on paraphrases.
   Mitigation: label by *evidence structure* (how many documents/hops the
   answer needs), not by surface form — and validate on held-out paraphrases
   (46's paraphrase slice).
3. **Distribution shift**: a router trained on one question mix degrades on
   another (a support-desk mix vs a research mix have different complexity
   bases). Re-tune per deployment; monitor the routing distribution over time
   (50: log the per-query class — it is the cheapest high-signal trace you
   have).
4. **The classifier is a model, with its own cost**: a small LLM router is
   still an LLM call per query (order of ms–tens of ms with a small model
   [I: the cost class that makes routing "cheap relative to the pipelines it
   selects" — verify against your router model's latency, 44).

## Where adaptive routing sits in the system (the 54 relationship)
The decision tree in 54 is a *design-time* version of adaptive routing:
"does this system's traffic contain multi-hop questions? → route that class
to the loop." Adaptive RAG makes the routing *per-query at runtime*. The
production shapes [I]:
- **Hybrid routing**: rules for the obvious classes (structured-data question
  → SQL, 30; obvious no-retrieval → parametric) + a learned classifier for
  the rest — the rules catch the cheap cases, the classifier handles the
  gray zone.
- **As one of several routers**: source routing (36: which *source*) and
  complexity routing (23: which *depth of retrieval*) are orthogonal
  decisions on the same query; a production router stack is
  (source, depth, cost-class) per query (51's router box is where they
  live).
- **The exit is a first-class route**: "no retrieval needed" is not a router
  failure — it is the cheapest, often-best answer for in-memory questions,
  and the system must be *allowed* to take it (54's "when NOT to use RAG",
  made per-query).

## Adaptive-RAG vs the learned-control family (extending 21/22)
| | Adaptive-RAG (23) | Self-RAG (21) | CRAG (22) |
|---|---|---|---|
| Decision point | *pre-retrieval* (which pipeline) | *during generation* (retrieve-or-not, per step) | *post-retrieval* (use-or-correct) |
| Signal | question complexity (a static property of the input) | reflection tokens (dynamic, per-step) | evidence quality (dynamic, per-query) |
| Model | a small classifier/LLM | the generator itself (trained) | an evaluator LLM |
| What it optimizes | compute allocation across classes | groundedness of each step | recovery from retrieval misses |
The composition [I: the design insight]: the three decisions are
*complementary* — a system can route by complexity (23), and *within* the
complex route, run a Self-RAG-style generator (21) whose post-retrieval
corrections are CRAG-style (22). Each layer earns its cost only if the
measured failure it fixes exists in your traffic (45/46 — the ablation
discipline applies to every control layer you add).

## Failure modes
1. **Routing failure (new layer in 47)**: the right pipeline exists but the
   router did not select it — invisible to per-pipeline metrics, visible only
   end-to-end (45's task-success slice, stratified by routed class).
2. **Complexity-label drift**: the label distribution on live traffic
   diverges from the training mix → the router's decision boundaries were
   never calibrated for the new mix (re-tune; 50's routing-distribution
   monitor).
3. **The cheap-class contamination**: simple questions routed to retrieval
   get retrieved *noise* that contaminates the parametric answer (the
   "retrieval made a good answer worse" case — measure it: parametric-only
   vs retrieved on the simple slice, 46).
4. **The complex-class floor**: no router fixes a single-hop ceiling — a
   complex question routed to single-step still fails (26's structural
   limit); the router's job is to *avoid* that floor, and its failure mode
   is reaching it anyway.
5. **Cost-class mismatch**: the routed pipeline's cost class exceeds the SLO
   (a Level-3 question at p99 latency) — the router must be cost-aware, not
   just quality-aware (44: route the *cost class*, not just the complexity).

## Key Takeaways
1. Adaptive RAG = a learned complexity router that selects the pipeline
   depth (none / single / iterative) per question [F: arXiv:2403.14403,
   NAACL 2024].
2. It optimizes the cost/quality frontier: over-retrieval costs money + can
   contaminate; under-retrieval costs the answer; the router gets the right
   amount per class.
3. The system is bounded by the classifier — evaluate it as a classifier on
   your set (45/46), label by *evidence structure* not surface form, and
   monitor the routing distribution (50).
4. It composes with source routing (36) and the learned-control family
   (21/22): complexity routing is one decision in a router stack.
5. "No retrieval" must be a first-class route — the cheapest answer is often
   the right one for in-memory questions (54).

## Related
[21 Self-RAG](21-self-rag.md) · [22 CRAG](22-corrective-rag.md) ·
[24 agentic](24-agentic-rag.md) · [36 federated (source routing)](36-federated-rag.md) ·
[54 decision tree](54-which-rag-should-i-use.md) · [44 economics](44-rag-economics.md) ·
[50 observability (routing traces)](50-rag-observability.md)
