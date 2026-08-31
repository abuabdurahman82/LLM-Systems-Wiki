# Open Research Questions in RAG

`LAST_UPDATED: 2026-08-29` · Status: core page · Research-framing page: every question
below is framed by the authors [I]; claims that merely restate published results are
tagged [F] with the source. Where evidence was unavailable at authoring time, the
claim is marked UNVERIFIED — the section gets a correction pass against the
consolidated research bank.

## 30-Second Explanation
RAG engineering has solid defaults (57), but its research frontier is genuinely
open: nobody has settled how retrieval should be learned, when it should fire, how
it composes with long-context and reasoning models, or how it should express
uncertainty. This page frames thirteen open questions — what is known, what is not,
and why it matters — so that new experiments land on real gaps instead of
re-deriving folklore. Each question is written to be attackable with the section's
golden datasets (46) and the experiment matrix (53).

## How to read the thirteen

They cluster into four research programs, each with a different toolset [I]:

| Cluster | Questions | Primary testbed |
|---|---|---|
| **Decision policies** — when/where/whether to retrieve | Q2, Q3, Q8 | 24 + 53 matrix, cost-quality curves (44) |
| **Economics & caching** — pay-per-need retrieval | Q5, Q6, Q7 | 42, 43, 44 cost models |
| **Trust & provenance** — sources, conflicts, uncertainty | Q9, Q11, Q12 | 12, 34, 36, 48; adversarial golden sets (46) |
| **Learning & calibration** — learned retrieval, reasoning, refusal | Q1, Q4, Q10, Q13 | 21–23, 26, 28; 45 two-layer metrics |

## The thirteen questions

### 1. Can retrieval itself be learned end-to-end? [I]
Known: the field moved both ways — training retrievers jointly with the reader vs
freezing a general embedder and adapting only the reader. Open: whether joint
training beats frozen-plus-reranker on *your* corpus, and how it survives corpus
drift without retraining UNVERIFIED. Why it matters: every team faces the
frozen-vs-trained decision; the honest answer is a trade-off, not a consensus.

### 2. Should retrieval happen at every generation step? [I]
Known: fixed pipelines retrieve once; adaptive/agentic designs retrieve on demand
(23, 24); multi-hop tasks demonstrably need more than one shot (26). Open: a
general policy for retrieval frequency (per step? per plan?) and whether
always-retrieving wastes attention on already-answered parts [I]. Why it matters:
frequency is a direct dial on cost (44) and context pollution (41).

### 3. Can a model predict whether retrieval will help before searching? [I]
Known: some systems gate retrieval on query classification or self-assessed
uncertainty (23; 21); simple heuristics help. Open: a calibrated *pre-retrieval*
utility estimate — "my parametric answer is reliable, skip the search" — accurate
enough to automate UNVERIFIED. Why it matters: a good gate makes RAG pay-per-need
instead of pay-per-request (44).

### 4. How should retrieval interact with reasoning models (CoT/interleaving)? [I]
Known: interleaving retrieval with chains of thought helps multi-hop reasoning
(IRCoT-style lineage; Self-RAG-style reflection), and reasoning models that plan
first change *when* evidence is useful — UNVERIFIED for current reasoning-model
products. Open: whether long internal reasoning reduces or *increases* the need
for evidence, and whether evidence belongs inside the reasoning trace or before
it. Why it matters: it decides the shape of next-generation RAG pipelines (24).

### 5. When should RAG beat million-token context? [I]
Known: stuffing works only for bounded corpora; long-context utilization is
uneven (lost-in-the-middle; ../Context-Engineering/Lost-in-the-Middle-and-Long-Context-Reality.md),
and cost scales with length (01). At bank scale, 1M tokens ≈ 3.8 MiB of text ≈
750K words [E] — enterprise corpora are far larger. Open: principled per-task
crossover criteria — when full-context wins on *correctness*, not just price [I].
Why it matters: it decides whether you build an index or buy a bigger window (39; 44).

### 6. Can KV/prefix caching dramatically reduce RAG prefill cost? [I]
Known: retrieved-context prefill dominates per-request compute (43); KV and
prefix caching are the counterweight (../KV-Cache/Prompt-and-Prefix-Caching.md).
The obstacle is structural: the system prefix is constant, but the *retrieved*
block differs per query, so full-context reuse misses. Open: retrieval-aware
caching — packing so shared chunks share prefixes, or cache-friendly ordering —
at production hit rates UNVERIFIED. Why it matters: at bank cost, 50 chunks ≈
$0.084/request vs ≈ $0.023 for 10 [E]; a large fraction is cacheable prefill (44).

### 7. Can retrieval results be cached semantically without correctness loss? [I]
Known: exact-result caches (same query → same chunks) are safe and deployed (42);
shared caches are complicated by per-principal access (48). Open: semantic
caching — serving a *near-duplicate* query from cached retrieval — needs a
similarity threshold guaranteeing the cached evidence still contains the required
support UNVERIFIED. Why it matters: query distributions are heavy-tailed; a
correct semantic cache is the cheapest latency/cost win available (42).

### 8. Can agents learn optimal retrieval policies? [I]
Known: agentic RAG shows that choosing queries, sources, and stopping points beats
fixed pipelines on some tasks (24); today's policies are prompted, not learned.
Open: *learning* the policy — when, where, how many times, when to stop — against
joint cost+quality objectives, without over-retrieval UNVERIFIED. Why it matters:
retrieval policy is where agentic RAG most often wastes money (44; 24).

### 9. How should RAG work across private and public knowledge simultaneously? [I]
Known: enterprise systems blend a private index with web search as a corrective
or fallback source (34; 36); source routing is standard in federated designs.
Open: principled *precedence and trust* rules — when public sources may contradict
or outrank the private corpus, and how mixed provenance is displayed UNVERIFIED.
Why it matters: correctness and compliance, not just plumbing (48; Q11 below).

### 10. Can GraphRAG outperform vector retrieval consistently outside graph-heavy tasks? [I]
Known: graphs win when relationships are the question (28; 29;
../Graph-Engineering/Knowledge-Graphs-and-GraphRAG.md); on general QA the gains
are task- and extraction-dependent [I]. Open: is graph retrieval a consistent
*general* improvement or a specialized tool for relational query classes, given
extraction and maintenance cost UNVERIFIED. Why it matters: it decides whether
graphs belong in the default stack or only in relation-heavy domains (54).

### 11. How should contradictory sources be resolved? [I]
Known: corpora contain superseded versions and stale documents; mitigations are
metadata (freshness, version, authority) and in-context arbitration by the model
(12; 41). Open: a systematic conflict policy — provenance-weighted arbitration,
contradiction detection before packing, user-facing "sources disagree" output —
measured on adversarial corpora UNVERIFIED. Why it matters: unflagged
contradictions produce confident wrong answers, the costliest failure class [I] (47).

### 12. How should retrieval uncertainty propagate into model confidence? [I]
Known: rerankers and relevance scores estimate evidence quality (14), and
self-reflective designs critique their own evidence (21), but scores are rarely
calibrated probabilities. Open: propagating retrieval uncertainty end-to-end —
from hitless/sparse signals through packing into calibrated answer confidence
UNVERIFIED. Why it matters: consumers (agents, humans, gates) need to know *how
sure* the evidence basis is, not just the answer (50).

### 13. Can RAG systems know when the evidence is insufficient (calibrated refusal)? [I]
Known: abstention is recognized behavior, and self/corrective designs route weak
evidence away from generation (21; 22); most systems still generate something.
Open: a calibrated refuse-vs-hedge-vs-answer policy — tied to retrieval scores
and sub-claim coverage — with acceptable false-refusal rates UNVERIFIED. Why it
matters: "I don't know, and here is what I searched" is the correct output for
most failed retrievals, and the hardest to tune [I] (47; 45).

## Status snapshot [I]
Two of the thirteen feel *closest* to resolution: Q10 (graphs), where the field is
converging on "specialized tool, not default stack," and Q2 (retrieval frequency),
where adaptive designs already ship — both need only rigorous measurement to close.
Two feel *furthest*: Q11 (contradiction resolution) and Q12 (uncertainty
propagation), which lack even agreed evaluation protocols. The rest sit in
productive middle ground: mechanisms exist, production-grade calibration does not.
This snapshot is itself [I] and will date — treat it as a reading of the field in
August 2026.

## How to contribute
The testbed is here: build your hypothesis into 53-rag-labs.md's experiment
matrix, run it against 46-rag-golden-datasets.md (real questions, known evidence
chunks, per-layer labels), and evaluate retrieval and generation layers separately
(45). Report negative results with the same rigor — every "X did not help on our
corpus" entry saves the next team an architecture. Questions 3, 6, 7 are the
highest-leverage cost-side entries; 10, 11, 13 the quality-side ones (44; 57).

## Key Takeaways
1. The frontier is decision-making, not components: when to retrieve, what to trust, when to stop, when to refuse (Q2, Q3, Q8, Q13).
2. Economics questions (Q5, Q6, Q7) are research questions too — caching and retrieval-aware context packing are open, high-leverage problems (44).
3. Trust questions (Q9, Q11, Q12) block enterprise deployment more than accuracy does (48).
4. Every question is attackable with 46 (golden sets) + 53 (experiment matrix) + 45 (two-layer evaluation).
5. Treat all framings here as [I] starting points; the consolidated research bank and a correction pass may upgrade or revise them.

## Related
- The engineering baseline these questions extend: 57-rag-80-20.md · 03-basic-rag-pipeline.md
- Closest built systems: 21-self-rag.md · 22-corrective-rag.md · 23-adaptive-rag.md · 24-agentic-rag.md · 26-multi-hop-rag.md
- Testbed: 46-rag-golden-datasets.md · 53-rag-labs.md · ../Evaluation-Engineering/RAG-Evaluation.md
- Adjacent sections: ../Context-Engineering/Lost-in-the-Middle-and-Long-Context-Reality.md · ../Graph-Engineering/Knowledge-Graphs-and-GraphRAG.md · ../KV-Cache/Prompt-and-Prefix-Caching.md
- Where the answers will land: 61-rag-big-picture.md · 59 (this page's sibling updates)
