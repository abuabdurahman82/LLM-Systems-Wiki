# Context & Long-Context Evaluation: usable length, not advertised length
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
The context window is the *maximum* length a model will accept; the *usable*
length is where performance actually holds, and the two differ. Performance
degrades in a U-shape with position in the context (lost in the middle,
arXiv:2307.03172 [F]), and retrieval-only tests like Needle-in-a-Haystack
measure the floor, not the ceiling. A full protocol measures accuracy at
multiple lengths, plots the curve, and defines usable length at an explicit
threshold (e.g., within 5 points of short-context performance). RULER and
LongBench v2 add multi-hop and aggregation tasks that NIAH cannot see.
Long-context eval is also expensive — prefill cost scales with context, so a
1M-token campaign is a budget decision. Report the length axis together with
the effort axis for reasoning models.

## Advertised vs usable length
- **Context window** — the maximum sequence length the model accepts
  (architecture limit or serving configuration).
- **Usable length** — the length at which task performance still holds.

The two are not the same: **lost in the middle** shows a U-shaped
degradation — performance for content near the beginning and end of the
context is good, for the middle much worse — across both in-context learning
and QA settings, and the effect persists as windows grow [F:
arXiv:2307.03172; see
`../Context-Engineering/Lost-in-the-Middle-and-Long-Context-Reality.md`].

Practical consequence [I]: "128K context" is not a capability claim, it is
an acceptance limit. Any system that places critical information in the
middle of a long context (a retrieved chunk, a user preference, a policy
note) should be measured, not assumed.

## Benchmark families
| Benchmark | What it tests | Limit |
|---|---|---|
| Needle-in-a-Haystack (NIAH) | single-needle retrieval at varying lengths and positions | retrieval only — necessary, not sufficient [I] |
| LongBench (arXiv:2308.14508 [F]) | bilingual, multi-task long-context understanding | static; partially saturated [I] |
| LongBench v2 (arXiv:2412.15204 [F]) | deeper understanding + reasoning on realistic long-context multi-tasks | harder; still static |
| RULER (arXiv:2404.06654 [F]) | synthetic multi-task: variable retrieval, multi-hop tracing, aggregation, QA at controlled lengths | synthetic; the task mix is a design choice [I] |

**Why NIAH is insufficient [I]:** it tests *retrieval without reasoning*. A
model that finds a planted sentence can still fail a task requiring three
facts joined that sit 80K tokens apart — passing NIAH at 128K while failing
multi-hop at 32K is a realistic profile. NIAH is the floor test (does the
context even get read?); RULER's multi-hop and aggregation tasks and
LongBench v2's realistic reasoning tasks are the ceiling tests [I].

## The effective-context-length protocol
Method [I: protocol; ingredients are the cited benchmarks]:
1. Pick a task with a well-defined answer (multi-hop QA is the default; it
   is one of RULER's task families [F: 2404.06654]).
2. Measure accuracy at a ladder of lengths — e.g., 4K, 16K, 32K, 64K, 128K,
   256K, plus the advertised maximum — with the answer position varied
   (beginning / middle / end) to expose the U-shape [F: 2307.03172].
3. Plot accuracy vs length; **define usable length as the longest length
   within a threshold of short-context performance** (e.g., within 5 points
   of the 4K score) [I: 5 points is a convention, not a law].
4. Repeat with >= 2 seeds; report the whole curve, not the top of it [I].

Report the *advertised vs usable* gap explicitly: a model with a 128K window
and 64K usable length is a different system from one with 128K usable, even
though both advertise the same window.

## Complementary signals
- **Instruction-following in context:** IFEval (arXiv:2311.07911 [F]) —
  verifiable constraints on the output. Useful as a "does the model still
  obey the instructions when the context is long?" signal, since constraint
  compliance degrades with length even when retrieval works [I].
- **Memory over turns:** LongMemEval (arXiv:2410.10813 [F]) — chat
  assistants answering questions about facts scattered across long
  multi-session histories; measures *temporal* memory, not single-context
  reading [F: 2410.10813].
- **Context-management systems themselves:** compaction, memory, and
  retrieval layers are also evaluable objects. Measure task success vs
  context budget (the protocol curve above, but with the manager in the
  loop) and compare against the no-manager baseline [I; see
  `../Context-Engineering/Context-Compaction.md` and
  `../Context-Engineering/Agent-Memory.md`].

## Prefill cost as an eval constraint
Long-context evals are expensive because prefill processes the entire context
on every item and every seed — see `../Inference/Inference-Metrics.md` for
why prefill dominates cost at long sequences. Hand example [E], at $0.30 per
million input tokens:
- 100 items x 100K tokens = 10,000,000 tokens = 10M tokens.
- 10M tokens x $0.30/M = **$3.00 per pass**.
- 5 seeds = 5 passes = **$15.00** [E: 5 x 3.00 = 15.00].
- A 1M-token variant: 100 items x 1,000,000 tokens = 100M tokens.
- 100M tokens x $0.30/M = **$30.00 per pass** [E: 100 x 0.30 = 30.00].

The full 1M-token, 5-seed campaign is therefore $150 — an order of magnitude
above the 100K campaign — before any output tokens [A: price is a
placeholder for illustration; the arithmetic is [E]]. Budget the eval
campaign like an inference workload before choosing the length ladder [I].

## Effort-level interaction
Long context and reasoning models interact: at high effort (large thinking
budget) a model may recover from middle-position degradation by
re-attending to the context, or it may burn budget on context it cannot use
[I]. Report both axes — length and effort — or the number is undefined [I;
see `Reasoning-Evaluation.md` for the effort confound].

## Pitfalls
- Reporting only the top of the accuracy-vs-length curve — the cliff, not
  the plateau, is the finding [I].
- NIAH-only validation of a "long-context model" — retrieval passing says
  nothing about multi-hop use of the context [I].
- Ignoring the U-shape: placing critical content mid-context and assuming
  the window is uniform [F: 2307.03172].
- Comparing two systems at one fixed length — the curves can cross, and
  the "better" model depends on where you deploy [I].
- Long-context + high-effort numbers reported without pinning effort — the
  two axes interact [I].

## Related
- `../Context-Engineering/Lost-in-the-Middle-and-Long-Context-Reality.md`
- `../Context-Engineering/Context-Compaction.md`
- `../Context-Engineering/Agent-Memory.md`
- `../Inference/Inference-Metrics.md`
- `Reasoning-Evaluation.md`

## Key Takeaways
Advertised context window and usable length are different numbers; the gap
is real (U-shaped lost-in-the-middle degradation) and must be measured, not
assumed. NIAH is a necessary-not-sufficient floor test; multi-hop and
aggregation tasks (RULER, LongBench v2) are the ceiling. Define usable length
at an explicit threshold on the accuracy-vs-length curve, count prefill cost
as part of the protocol, and pin effort level for reasoning models.
