# Corrective RAG (CRAG) — Evaluate the Retrieval, Then Act on It

`LAST_UPDATED: 2026-08-29` · Status: core page · [F: arXiv:2401.15884
"Corrective Retrieval Augmented Generation" — Shi-Qi Yan, Jia-Chen Gu, Yun
Zhu, Zhen-Hua Ling (author list verified this pass against the arXiv API
record); publication venue: UNVERIFIED this pass (no comment field).]

## 30-Second Explanation
One-shot RAG (03) trusts the retrieval: whatever the top-k is, it gets
generated over. **Corrective RAG (CRAG)** inserts an *evaluation step between
retrieval and generation*: a lightweight retrieval evaluator scores the
retrieved evidence (correct / incorrect / ambiguous), and the system takes a
*corrective action* based on the verdict — use it, refine it, or **go fetch
better evidence from an alternate source** (in the original system, web
search). The core idea: retrieval quality is a *measurable, per-query* signal,
and the system should act on that signal instead of passing raw top-k to the
generator [F: the retrieve→evaluate→correct loop, per the verified paper].

## The loop (precisely)
```
query
  ↓ retrieve (the standard first stage — vector/hybrid, 03/13)
  ↓ RETRIEVAL EVALUATOR (a small LLM scores the evidence:
  │     CORRECT  — the evidence answers the question
  │     INCORRECT— the evidence is off-topic / wrong
  │     AMBIGUOUS— the evidence may or may not answer it)
  ↓ corrective action (per verdict):
  ├── CORRECT   → filter the evidence (drop the weak passages), generate
  ├── AMBIGUOUS → keep + supplement: run the fallback search (web) and merge
  └── INCORRECT → discard the top-k; run the fallback search (web);
                  if the fallback is also weak → generate with a
                  "no reliable evidence" stance
  ↓ generate (with provenance labels: which evidence came from the index,
  │            which from the web, which was dropped)
```

Two design choices make it *corrective* rather than just "evaluated" [F: per
the verified paper's mechanism]:
1. **The evaluator is cheap and separable** — a small LM (not the generator)
   scores (question, evidence) — the evaluation is a first-class pipeline
   stage with its own latency/cost budget, not a prompt instruction to the
   generator.
2. **The actions are structural** — the verdict changes *what evidence the
   generator sees* (filter / supplement / replace), not just how it is told to
   behave. The "discard + web-search" path is the load-bearing one: it means
   the system *leaves its own corpus* when the corpus fails.

## Why the three-way verdict (not just good/bad)
The **ambiguous** middle class is the design's point [I: the reading of the
three-class design]: many retrievals are "topically near, answer unclear" —
the evidence mentions the entity but does not settle the question. A
binary good/bad verdict forces either over-correction (web-searching when
the corpus was good enough) or under-correction (generating over uncertain
evidence). The three-way split lets the system spend the expensive fallback
action *only* on the verdicts that need it [I: the cost argument — the
fallback (web search + extraction) is the most expensive corrective action;
gating it on a three-way signal is the 44 economics of corrective behavior].

## The evaluator problem (where CRAG lives or dies)
The whole system is bounded by the evaluator's calibration [I: the standing
risk — see also 45's judge-discipline]:
- **Evaluator false-positive** ("correct" when it is not): the system
  generates over bad evidence *with the confidence that evaluation was
  performed* — a worse failure than no evaluation, because the audit trail
  says "checked". Detection: measure the evaluator against a golden set (46)
  as a *classifier* (precision/recall of the verdicts), not just end-task.
- **Evaluator false-negative** ("incorrect" when the evidence was fine):
  every query pays the fallback (latency + cost + the web's own failure
  modes, 34) for no gain. The cost shows up directly in 44.
- **Evaluator drift over corpus change**: a small evaluator tuned on one
  corpus distribution degrades on another — re-calibrate per corpus
  (the 46 versioning discipline, applied to the evaluator).
- **The web fallback is its own RAG system**: fetch + extract + dedup +
  trust-tier (34) — CRAG's "corrective" path is a nested retrieval system
  with its own failure modes (injection, staleness, SEO).

## CRAG vs the learned-control family (the 21 comparison, extended)
| | CRAG (22) | Self-RAG (21) | Adaptive-RAG (23) | Agentic (24) |
|---|---|---|---|---|
| Evaluation point | post-retrieval, pre-generation (explicit stage) | inside generation (reflection tokens) | pre-retrieval (complexity routing) | per-step, in the loop |
| Corrective action | filter / supplement / **replace with web** | sample-weighting (suppress bad continuations) | choose the retriever depth | re-formulate + re-retrieve (any source) |
| Training | none (off-the-shelf evaluator LLM) | yes (SFT+RL on reflections) | yes (classifier) | usually none |
| Escapes the corpus? | **yes** (the web fallback) | no | no | yes (if web is a tool) |
| Cost per query | evaluator pass + (sometimes) web round-trip | inference sampling | classifier pass | k loop passes |

The distinguishing property [I: the design insight]: CRAG is the only one of
the four that *structurally leaves its own corpus on a bad retrieval* — which
is both its strongest property (the corpus-miss failure, 47, gets a recovery
path) and its biggest operational one (you are now depending on an external,
untrusted source, 34/48).

## Failure modes (named, per 47's layers)
1. **Evaluator layer**: miscalibrated verdicts (above) — the failure *is*
   the new layer CRAG adds; the 47 taxonomy gains a "correction failure"
   row.
2. **Fallback layer**: the web search retrieves *different* garbage — the
   correction makes the evidence worse, and the provenance labels make that
   *visible* (a good property: the answer shows which source it came from).
3. **Latency layer**: the evaluator + possible web round-trip add 10s of
   seconds to the tail (34's fetch/extract latency) — the p99 of a CRAG
   system is the web's p99, not the vector DB's.
4. **Trust layer**: web evidence enters the context with the corpus's trust
   — unless the provenance labels + trust tiers (36/48) are enforced, the
   generator (and the user) cannot tell which half of the context is
   vetted.
5. **Over-correction**: for corpora that are *usually* good (high retrieval
   recall), the evaluator's false-negatives dominate and the system pays the
   fallback on most queries for little gain — measure the verdict
   distribution before adopting (45/46).

## Key Takeaways
1. CRAG = retrieve → evaluate (correct/incorrect/ambiguous) → act (use /
   supplement / replace-with-web) — retrieval quality becomes a per-query,
   actionable signal [F: arXiv:2401.15884].
2. The three-way verdict exists to gate the expensive fallback on the
   verdicts that need it (44 economics of correction).
3. The system is bounded by the evaluator's calibration — evaluate the
   evaluator as a classifier on your golden set (45/46).
4. The web fallback makes CRAG the only learned-control pattern that leaves
   its own corpus — with the web's trust/latency/staleness problems nested
   inside (34/48).
5. It adds a failure layer (correction failure) to 47's taxonomy; the
   provenance labels are what keep that layer auditable.

## Related
[21 Self-RAG](21-self-rag.md) · [23 Adaptive-RAG](23-adaptive-rag.md) ·
[24 agentic](24-agentic-rag.md) · [34 web RAG (the fallback)](34-web-rag.md) ·
[45 evaluation](45-rag-evaluation.md) · [47 failure taxonomy](47-rag-failure-modes.md) ·
[48 security (the untrusted fallback)](48-rag-security.md)
