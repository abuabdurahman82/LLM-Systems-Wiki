# Safety Evaluation & Red-Teaming: refusal, jailbreaks, and agent harm

`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation

Safety evaluation is not one number; it is a three-layer construct. Layer 1 is
**refusal behavior**: does the model decline harmful requests, robustly, as measured by
HarmBench [F: arXiv:2402.04249]. Layer 2 is **jailbreak robustness**: how many crafted
attacks actually get past the refusal — the Jailbroken paper showed a large fraction of
jailbreaks succeed against safety-trained models [F: arXiv:2307.02483], and WildGuard
provides an open moderation classifier for the same failure modes [F: arXiv:2406.18495].
Layer 3 is **agentic harm**: an agent that *completes* a harmful task rather than merely
discussing it — AgentHarm measures this directly [F: arXiv:2410.09024], and AgentDojo
covers prompt-injection attacks on tool-using agents [F: arXiv:2406.13352]. Safety eval is
harder than capability eval because the construct is open-ended (there is no finite attack
space to enumerate) and the interesting population is the tail [I]. Headline metrics: ASR
(attack success rate), robust refusal rate, over-refusal rate — always reported per attack
family, never as a single blended number. [I]

## The three-layer construct

| Layer | Object | Failure looks like | Representative benchmark |
|---|---|---|---|
| 1. Refusal | chat model, no tools | "refused a benign request" or "failed to refuse a harmful one" | HarmBench [F: arXiv:2402.04249] |
| 2. Jailbreaks | chat model under crafted attacks | ASR under attack sets | Jailbroken [F: arXiv:2307.02483]; WildGuard [F: arXiv:2406.18495] |
| 3. Agentic harm | model + tools + environment | harmful task actually *executed* | AgentHarm [F: arXiv:2410.09024]; AgentDojo [F: arXiv:2406.13352] |

Layer 1 is the cheapest and the most misleading on its own: a model that refuses everything
scores perfectly on refusal and has a 100% over-refusal problem. HarmBench's contribution is
the **two-way framing** — robust refusal requires *high refusal on harmful prompts AND low
over-refusal on benign ones*, and its standardized attack sets let the two numbers be
compared across models [F: arXiv:2402.04249]. Layer 2 is where the arms race lives:
Jailbroken demonstrated that many jailbreak techniques succeed against safety-trained
models and that safety training does not close the gap [F: arXiv:2307.02483]. WildGuard is
useful on the infrastructure side as a moderation classifier you can run over model
outputs to label risk categories automatically [F: arXiv:2406.18495].

Layer 3 changes the risk class. An agent with a shell is not the same risk as a chat model:
the harm surface expands with every tool, and "refusal" stops being a complete control —
the agent must decline, and the environment must not let a completed task cause damage.
AgentHarm measures whether agents actually carry out harmful tasks, not whether they talk
about them [F: abstract, arXiv:2410.09024]; AgentDojo evaluates both prompt-injection
attacks and defenses in a realistic tool-using agent environment [F: arXiv:2406.13352].
See `../Safety/README.md` for the broader safety construct and `../Agents/Agent-Evaluation.md`
for how agent capability eval interacts with agent safety eval.

## Why safety eval is harder than capability eval

- **Open-ended construct.** Capability benchmarks have a finite, closed item set. The
  attack space does not close: every published defense generates new attacks. There is no
  "done." [I]
- **The population is the tail.** A 95% refusal rate hides the 5% that matters. Capability
  eval is dominated by the mean; safety eval is dominated by the worst cases, and
  reporting a mean without the tail distribution is a category error. [I]
- **Arms race / co-evolution.** Attack and defense co-evolve; a benchmark built from
  attacks N months old systematically overestimates current robustness because the stale
  attacks are the ones the model has seen in its training or fine-tuning data. [I]
- **Validity question.** Does "refusal" measure safety, or just a behavior pattern?
  Stylistic jailbreaks (change the surface form, keep the semantics) test one thing;
  semantic attacks (genuinely reframe the request) test another. A benchmark that only
  covers stylistic variants measures the former and reports it as the latter. [I]

## Red-teaming methodology

Pipeline [I]:

1. **Threat model** — who is the adversary, what can they do (black-box? white-box? can
   they inject content the agent retrieves?), what harm is in scope.
2. **Attack surface** — enumerate entry points: direct user prompt, multi-turn context,
   indirect injection via retrieved or tool-returned content, system-prompt edits.
3. **Attack families** — group techniques so results can be reported per family:
   - direct single-prompt attacks,
   - multi-turn escalation (gradual, role-play priming),
   - indirect / prompt injection via retrieved content (the AgentDojo class
     [F: arXiv:2406.13352]),
   - encoding / obfuscation (base64, token-smashing, foreign-language framing),
   - persona / roleplay framing. [I]
4. **Metrics per family** — report ASR and robust refusal *per family*, not one blended
   number. A model strong on direct prompts and weak on injection is a specific,
   actionable profile; blended, it is invisible. [I]

**Metric definitions** [I]:

- **ASR (attack success rate)** = successful jailbreaks / attack attempts.
- **Robust refusal rate** = harmful prompts correctly refused / all harmful prompts.
- **Over-refusal rate** = benign prompts refused / all benign prompts.

## Hand example [E]

A safety eval set contains 500 prompts: 50 harmful, 450 benign. The model refuses 45 of 50
harmful and 448 of 450 benign.

- ASR = 5/50 = **0.10 → 10%** (the 5 harmful prompts it did not refuse).
- Robust refusal = 45/50 = **0.90 → 90%**.
- Over-refusal = 2/450 = **0.00444 → 0.44%**.

Read jointly: a 90% refusal number *looks* fine; the 10% ASR is the release-blocking fact,
and the 0.44% over-refusal says the model is not over-refusing. Reporting only "90%
refusal rate" or only "10% ASR" each hides half the profile. [E]

## Trustworthiness as a multi-dimension construct

Safety is one facet of trustworthiness. TrustLLM frames trustworthiness as **six
dimensions including truthfulness, fairness, and robustness**, with benchmarks per
dimension [F: arXiv:2401.05561]. The practical consequence: "is the model safe?" is
unanswerable; "is the model robust under attack, truthful on its claims, and fair across
demographic slices?" is a real, decomposable evaluation. [I]

## LLM-as-a-judge for safety labeling, and its limits

At scale, human labeling of every model output is unaffordable; LLM judges do the cheap
triage — flagging candidate jailbreaks, categorizing refusals — with a human audit pass
over a sample (see `LLM-as-a-Judge.md` and `Human-Evaluation.md` for the hybrid pipeline).
The Constitutional AI line of work shows AI feedback used at scale in alignment itself
[F: arXiv:2212.08073], and `../Post-Training/README.md` covers the training side. The
limit: judge-based safety labeling inherits the judge's blind spots, and for the safety
*tail* — the rare, high-stakes failures — a judge's error rate is too high to trust
without human verification. [I]

## Canary tokens and private held-out attack sets

Published attacks leak: once an attack family is public, it enters training corpora and
fine-tuning sets, and public benchmarks stop measuring unknown robustness. The standard
controls [I]:

- **Private held-out attack sets** — a rotating library of unpublished attacks; the
  benchmark's power is the part nobody has seen.
- **Canary tokens** — embedded markers in test items that let you detect when test
  material has leaked into a model's training data (contamination detection is treated in
  `Benchmark-Contamination.md`).
- **Rotation schedule** — retire attack families from public reports before the next
  model generation is trained; keep the eval set ahead of the training set. [I]

## Related

- `../Safety/README.md` — the broader safety construct
- `../Agents/Agent-Evaluation.md` — agent capability vs agent safety, same environment
- `LLM-as-a-Judge.md` — the labeling workhorse and its calibration requirements
- `Human-Evaluation.md` — human audit of judge-flagged safety tail
- `Benchmark-Contamination.md` — why stale attack sets measure nothing new

## Key Takeaways

Safety is three layers — refusal, jailbreak robustness, agentic harm — and each layer has
its own failure mode and benchmark. Report ASR, robust refusal, and over-refusal **per
attack family**, because the construct is open-ended and the interesting population is the
tail. Guard the eval itself: attacks leak into training data, so canary and rotate private
held-out sets; and remember the validity question — a benchmark only measures safety to
the extent its attack families match the real threat model.
