# RAG Golden Datasets — The Evidence Set Everything Else Is Judged Against

`LAST_UPDATED: 2026-08-29` · Status: core page · Dataset facts [F] confirmed
this pass (HotpotQA, MuSiQue, 2WikiMultihopQA, MS MARCO, Natural Questions,
BEIR — see the benchmark section); construction practice [I].

## 30-Second Explanation
You cannot improve a RAG system you cannot measure, and you cannot measure it
without a **golden dataset**: a curated set of questions, each with the
*expected evidence* (which chunks/docs answer it), the *expected source*, and
the *expected answer*. The golden set is the substrate for every evaluation in
45, every ablation in 53, every deployment gate in 51 — and it is the one
artifact that separates "we tuned until it looked right" from "we measured".
This page is how to build one, including the slices that catch the failures
generic benchmarks miss.

## The record shape
Each golden record [I: the minimal complete shape — extend per domain]:
```
{
  "id": "g-0001",
  "question": "What was the Q3 revenue for the EU region?",
  "question_type": "single-hop | multi-hop | comparative | unanswerable | adversarial",
  "expected_evidence": ["doc:fin-q3-report:chunk:42", "doc:fin-q3-report:table:rev-by-region"],
  "expected_source": "fin-q3-report (v3, 2025-11)",     // which document(s), which version
  "expected_answer": "€142.3M (v3 report, p.14)",
  "answer_form": "exact | tolerant | graded(0-4)",
  "difficulty": 1-5,
  "requires": ["multi-hop", "table", "exact-number", "version-sensitivity"],
  "created": "2026-08-29", "reviewed_by": "human", "status": "active"
}
```
The fields that matter most: **expected_evidence** (what retrieval should
find — the retrieval-layer label), **expected_source + version** (what
*provenance* the answer should cite — the 12/45 citation check), and
**question_type** (which failure class the record exercises — the slices
below).

## The slices (what the set must contain)
A set that is only "easy factual questions" validates nothing except the happy
path. The standing slices [I: the coverage checklist — sizes are
recommendations, not laws]:
| Slice | Share (typical) | What it catches |
|---|---|---|
| **Single-hop, well-phrased** | ~40% | the baseline; regression detection |
| **Paraphrased / colloquial** | ~15% | the query-doc phrasing gap (40/17's regime) |
| **Exact-token** (IDs, codes, citations) | ~10% | the lexical half of hybrid (13/37) |
| **Multi-hop** (bridge/comparison/aggregation) | ~15% | the 26 task class; one-shot RAG's structural failure |
| **Unanswerable** (not in corpus) | ~10% | refusal calibration — the system must *not* answer |
| **Adversarial / trap** | ~5% | near-miss distractors (same entity, wrong version/attribute); poisoned-doc detection hooks (48) |
| **Contradictory-corpus** | ~5% | two indexed docs disagree; the answer must surface the conflict (36) |
| **Stale-version** | ~5% | the expected answer is in v3, v2 says something else — version-sensitivity (12) |
| **Multi-modal** (figure/table-anchored) | ~10% of the rest | 31's failure class (answers in a figure or table, not prose) |
| **Cross-source** (federated) | ~10% | the 36 router's correctness — right source, right composition |

The unanswerable and adversarial slices are the ones generic benchmarks
*don't* give you: public sets (below) assume the answer exists in the corpus
and the corpus is clean. Your production failures (wrong version, poisoned
doc, "not in scope") live in the slices you build yourself.

## Hard negatives (the evaluation's sharpest instrument)
A **hard negative** is a chunk that is *plausibly relevant* but *wrong* —
same entity, different version; same metric, different region; the near-dup
that lost the tie. [I: the construction practice]:
- **Mine them from the system itself**: run the current retriever, take the
  top-50 for each golden question, and label which of the non-expected items
  are "plausible traps" (human 5-minute task per question).
- **Why they matter**: they are where rerankers (14) and thresholding (41)
  earn or lose their keep — a retrieval system that beats easy distractors
  but ships the hard negative looks "fine" on naive metrics and fails on the
  ones that hurt (the "confidently wrong" failure, 47).
- **Maintain them as their own set**: hard negatives for *retrieval* eval
  (should-not-be-top-k) are distinct from *generation* distractors
  (in-context but irrelevant — the 41 pollution case).

## Public benchmarks (the controls, not the answer)
[F: all confirmed this pass against arXiv]:
| Benchmark | arXiv | Venue | What it is |
|---|---|---|---|
| **HotpotQA** | 1809.09600 | EMNLP 2018 | 113K 2-hop questions over Wikipedia (bridge + comparison); the multi-hop reference [F: id/venue re-verified 2026-08-30 via arXiv API; CC BY-SA 4.0 per hotpotqa.github.io] |
| **MuSiQue** | 2108.00573 | TACL 2022 | 2–4-hop; the *no-brute-force* split (its key finding: systems that "read all Wikipedia" score well without retrieving hops) [F: id/venue re-verified via arXiv API comment "Accepted… TACL, 2022"] |
| **2WikiMultihopQA** | 2011.01060 | COLING 2020 | Wikipedia + Wikidata multi-hop, weakly supervised [F: venue = COLING 2020 per arXiv comment field] |
| **MS MARCO** | (Microsoft; passage ranking + QA) | — | the industrial-scale single-hop control (8.8M passages; ~900K queries in v2.1, of which 4,281 are the standard dev split; license: Microsoft terms, not CC — verify before reuse [F: license note; sizes per msmarco.org / ir-datasets]) |
| **Natural Questions** | (ACL Anthology Q19-1026; not on arXiv) | TACL 2019 | real web queries (307,373 train / 7,830 dev / 7,842 test) — the "actual user phrasing" control [F: anthology record, not arXiv] |
| **BEIR** | 2104.08663 | NeurIPS 2021 D&B | 18+ heterogeneous datasets for *zero-shot* retriever eval (no training on the target) |

Use them as **controls** [I: the discipline]: they tell you whether your
retriever is sane *in general*; your golden set tells you whether it is right
*for your corpus*. A system that scores well on BEIR and poorly on your set
has a domain-mismatch problem (07/37) — the two numbers together are the
diagnosis.

## Building the set: the workflow
1. **Seed from traffic** [I: the best source of realism]: take 200–500 real
   user queries (anonymized), cluster them, and pick representatives per
   cluster — your set covers your actual question distribution, not a
   benchmark's.
2. **Annotate evidence first, answers second**: a human (domain expert) marks
   *which chunks* answer each question (retrieval label); the expected answer
   is then written *from the marked evidence* (answer label). Reversing the
   order produces answers that "should" be in the corpus but whose evidence
   was never verified present — the classic annotation bug.
3. **Two-person rule for the hard slices**: multi-hop, unanswerable, and
   adversarial records get two annotators; disagreements are *kept* as
   "contested" records (the wiki's own `contested` discipline, applied to
   eval data) and resolved explicitly.
4. **Version the set** (like the index, 51): `golden-v7, 2026-08-29,
   corpus-snapshot S-881`. A golden set against a different corpus snapshot
   is not the same set — pin the corpus version per record.
5. **Refresh quarterly** (or on corpus restructure): 20–30% churn — new
   questions from traffic, retired questions whose documents changed, new
   hard negatives mined from the current system's mistakes.
6. **Keep it private** [I: the contamination discipline,
   `../Evaluation-Engineering/Benchmark-Contamination.md`]: the golden set is
   a trade secret of your product's quality; it is the one eval artifact you
   do not ship to a vendor.

## Failure modes of the dataset itself
1. **Answerable-everywhere assumption**: no unanswerable slice → the system
   learns to *always answer* and your eval cannot see the over-answer failure.
2. **Single-source answers only**: no cross-source records → the router (36)
   is never evaluated; federation ships untested.
3. **Version-blind**: records without `expected_source`/version → the
   stale-answer failure (47) is invisible by construction.
4. **Phrasing-homogeneous**: all questions in one register → the paraphrase
   gap (40/17) is never exercised.
5. **Retrieval-label drift**: evidence marked against chunk ids that a
   re-chunk (10) renumbers → the labels silently point at wrong chunks; the
   fix is to label by *stable content anchors* (doc + section + quote snippet)
   and resolve to chunk ids at eval time.
6. **Benchmark contamination**: using public sets that LLMs saw in training →
   parametric-memory answers pollute the retrieval measurement (the MuSiQue
   finding, generalized — [F: 2108.00573's brute-force result is the same
   failure family]).

## Key Takeaways
1. A golden record = question + expected evidence + expected source/version +
   expected answer + type/difficulty; the evidence label is the retrieval
   layer's ground truth.
2. Coverage is the product: single-hop, paraphrased, exact-token, multi-hop,
   unanswerable, adversarial, contradictory, stale-version, multi-modal,
   cross-source — missing a slice means blind to its failures.
3. Hard negatives, mined from your own system's near-misses, are the sharpest
   eval instrument for rerankers and thresholds.
4. Public benchmarks (HotpotQA/MuSiQue/2Wiki/MARCO/NQ/BEIR) are *controls*,
   not verdicts; your private, versioned set is the verdict.
5. Annotate evidence-first, two-person on hard slices, version the set against
   the corpus snapshot, refresh quarterly, keep it private.

## Related
[45 evaluation (the metrics)](45-rag-evaluation.md) · [47 failure taxonomy](47-rag-failure-modes.md) ·
[37 domain-specific](37-domain-specific-rag.md) · [51 production (gates)](51-production-rag-reference-architecture.md) ·
[53 labs (ablations run on the set)](53-rag-labs.md) ·
`../Evaluation-Engineering/Benchmark-Contamination.md`
