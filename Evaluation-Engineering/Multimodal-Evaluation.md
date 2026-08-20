# Multimodal Evaluation: vision, OCR, grounding, and the modality gap

`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation

Multimodal evaluation adds four new failure axes that pure text eval cannot see: input
modality (image, audio, video in), output modality (text, bounding boxes, or actions
out), grounding (does the answer actually refer to the right region of the image), and
temporal reasoning (for video). The benchmark families that anchor this area are MMMU,
MMBench, and MathVista [F: arXiv:2311.16502; arXiv:2307.06281; arXiv:2310.02255]. But the
discipline is dominated by infrastructure problems, not model quality: LMMs-Eval is the
"reality check" showing that large multimodal model evaluations are frequently broken by
data leakage between splits and inconsistent preprocessing [F: arXiv:2407.12772]. Two
structural issues define the field: the **modality gap** — text benchmarks are saturating
while multimodal capability lags, so the interesting signal is in the multimodal delta
[I] — and **preprocessing sensitivity** — the same image at different resolutions or crop
scales produces different scores, so preprocessing must be pinned in the protocol [I].
Cost is real: a vision token costs money, and a full battery is thousands of dollars of
inference, not thousands of cents. [I]

## What multimodal eval adds over text eval

| New axis | Question it answers | Example failure it catches |
|---|---|---|
| Input modality | Can the model perceive the signal at all? | OCR garbling, audio transience, video keyframe misses |
| Output modality | Can it emit structured output (bbox, action)? | "The object is here" but no valid box |
| Grounding | Is the answer *about the right region*? | Right answer, wrong object in the image |
| Temporal reasoning | Does it track order/cause across frames? | Reverses before/after in a video clip |

Text eval measures language competence. These axes measure whether the perception stack —
preprocessing, tokenization of the image into the model's input space, and the model's
own spatial/temporal processing — is intact. A model can be a strong reasoner and a weak
perceiver; text-only evals are blind to that split. [I] See `../Multimodal/README.md` for
the architecture side (how images become tokens) and `../Glossary/README.md` for token
definitions.

## Benchmark families

**Understanding / reasoning (arXiv-verified)**:

- **MMMU** — massive multi-discipline multimodal understanding and reasoning: college
  level, multi-subject, multi-step [F: arXiv:2311.16502].
- **MMBench** — "is your multimodal model an all-around player?" a structured
  capability battery with circular evaluation to mitigate answer-position bias
  [F: arXiv:2307.06281].
- **MathVista** — mathematical reasoning in visual contexts: charts, geometry,
  function plots [F: arXiv:2310.02255].

**OCR/document, grounding/UI, and video suites** — these are referenced throughout the
2026 open-model leaderboards; per this wiki's citation discipline, they are treated as
vendor/HuggingFace artifacts, cited `[F: vendor/HF]` where used, and deliberately not
assigned arXiv IDs from this registry [F: vendor/HF, per `../Evaluation/README.md` and
`../Benchmarks/README.md`]. The practical consequence: for these suites the version
number and the item set matter more than the name — pin both in the protocol. [I]

**Evaluation infrastructure**:

- **LMMs-Eval** — the reality check: audits how large multimodal model evaluations are
  frequently broken by data leakage between splits and inconsistent preprocessing across
  harnesses; before trusting a multimodal number, check which harness ran it and whether
  its splits were clean [F: arXiv:2407.12772].

## The modality gap

Text benchmarks (MMLU and successors) are saturating; top models approach ceiling on
them. Multimodal benchmarks are not — the gap between what a frontier model scores on
text and on vision-grounded tasks is where the real capability signal lives. Two
consequences [I]:

1. **The delta is the metric.** Reporting "MMMU 71" in isolation is meaningless; the
   informative quantity is MMMU minus the equivalent text task, which isolates the
   perception cost.
2. **Contamination looks different.** A text benchmark leaks through memorization; a
   multimodal benchmark can leak through the *image itself* if it appeared in training
   data (stock-photo overlap, web-scrape duplication). LMMs-Eval's leakage findings are
   the canonical demonstration [F: arXiv:2407.12772]. See `Benchmark-Contamination.md`.

## Resolution sensitivity and preprocessing as protocol

The same image at different resolutions or aspect ratios produces different model outputs
and therefore different benchmark scores [I]. This is not noise; it is a measured degree
of freedom. Protocol requirements [I]:

- Pin **input resolution / max-pixel budget** in the harness, and report it next to the
  score — a score without its resolution is a rumor.
- Pin **crop/resize policy** for bounding-box items; a bbox scored against a resized
  reference with the wrong scale is a preprocessing bug, not a model result.
- Pin **image token count** (how many vision tokens the image costs) so results are
  comparable across models that patch images differently.
- For video: pin **clip length and fps sampling** — both are protocol parameters, and a
  video benchmark run at 2 fps measures a different task than one at 8 fps. [I]

## Annotation quality: coarse vs fine-grained

MCQ (coarse) and free-response/bbox (fine-grained) labels have different reliability
profiles [I]:

| Item type | Scored by | What it can miss |
|---|---|---|
| Multiple-choice | exact match on choice | guessing (25% base rate with 4 options), position bias |
| Free-form text | LLM judge or exact-after-normalization | judge bias (see `LLM-as-a-Judge.md`) |
| Bounding box / segmentation | IoU threshold | a 0.5 IoU threshold passes boxes that are clearly wrong |
| Temporal (video) | clip-level or frame-level label | frame-sampling artifacts (a "missing" event at low fps) |

The rule: the more fine-grained the label, the more the *scoring protocol* determines the
result. An IoU threshold choice is a hyperparameter of the benchmark, and it must be
reported. [I]

## The judge problem: image-grounded claims are harder to judge

An LLM judge evaluating an image-grounded claim is weaker than one evaluating pure text,
because the judge itself may hallucinate about the image [I]. Practical controls:

- The judge must receive **the image in context** — a text-only judge cannot verify
  "the red car is on the left."
- **Calibrate the judge against human labels** on a held-out image subset; if judge-human
  agreement on image items is materially below its text agreement, do not use it for the
  image items. Method in `LLM-as-a-Judge.md`; agreement measurement in
  `Statistical-Evaluation.md`. [I]
- Prefer **binary, checkable image claims** ("does a bounding box overlap the target
  region?") for the judge where possible, and reserve open-ended image critique for
  humans. [I]

## Cost: the hand example [E]

Multimodal evals are expensive because every image costs vision tokens. Worked example:

- A 1024×1024 image at typical patching costs roughly **1.3k vision tokens**
  [I: order-of-magnitude estimate for standard patch-size tokenizers].
- A battery of 1000 items, each with that image plus ~0.5k text tokens, run over
  **3 seeds** → 3000 completions × (1.3k + 0.5k) = 3000 × 1800 = **5.4M total tokens**.
- At a blended $1 per million tokens: 5.4 × $1 = **~$5.40** [E: 5.4M × $1/M].

That is the *inference* cost of one battery on one model — before harness development,
before a second model, before the judge pass on top (judges over image items are even
more expensive: the judge also pays the image tokens, doubling the vision cost for the
judged subset [I]). Video multiplies this further by the frame count at the pinned fps.
Budget for it: multimodal eval is a recurring line item, not a one-off. [I]

## Interlock

- `../Multimodal/README.md` — how images become model input (the architecture side of
  this page's protocol side).
- `Context-Long-Context-Evaluation.md` — long-context and multimodal interact: many
  images in one context is a long-context problem wearing a vision costume. [I]
- `LLM-as-a-Judge.md` — the judge problem above is this page's section, not a footnote.
- `../Evaluation/README.md` and `../Benchmarks/README.md` — where the vendor/HF suites
  are catalogued.

## Related

- `../Multimodal/README.md`
- `Context-Long-Context-Evaluation.md`
- `LLM-as-a-Judge.md`
- `Benchmark-Contamination.md`
- `../Evaluation/README.md`

## Key Takeaways

Multimodal eval adds four axes — input modality, output modality, grounding, and temporal
reasoning — that text eval cannot see, and the current frontier signal (the modality gap)
lives exactly there. The field's binding constraint is infrastructure, not models: split
leakage and unpinned preprocessing (LMMs-Eval's findings) can invalidate a benchmark more
than the model can [F: arXiv:2407.12772]. Pin resolution, crop policy, clip length, and fps
in the protocol — a multimodal score without its preprocessing parameters is not a number,
it is a rumor — and budget real dollars, because image tokens make every battery cost
orders of magnitude more than its text twin.
