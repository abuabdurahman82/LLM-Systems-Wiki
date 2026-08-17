# Post-Training — From Base Model to Aligned Assistant
`LAST_UPDATED: 2026-08-16` · Status: core section

## 30-Second Explanation
A pretrained base model predicts the next token of the internet — it doesn't *help*.
Post-training shapes behavior: SFT teaches format/instruction-following; RLHF (or its
successors) shapes *preferences*; distillation compresses behavior; reasoning
post-training (2024+) adds long CoT via RL on verifiable tasks.

## The pipeline (canonical, OpenAI/Anthropic-style [F/I])
1. **SFT (supervised fine-tuning):** small curated set of (instruction, response) pairs.
   Cheap, stable, low ceiling.
2. **Reward model (RM):** rank human preference pairs (Bradley-Terry); the RM is the
   learned proxy for "which response is better."
3. **RL with RM:** PPO (Schulman 2017 arXiv:1707.06347 [F]) maximizes RM reward − KL(to
   SFT) penalty. **InstructGPT (Ouyang 2022, arXiv:2203.02155 [F])** proved RM+PPO beats
   3×-scale base on preference. **ChatGPT (2022)** productized it.
4. **Preference optimization without RL (2023–):**
   - **DPO** (Rafailov 2023, arXiv:2305.18290, NeurIPS [F]) — closed-form policy from the
     RL objective; no RM, no sampling; the 2023–24 default for research.
   - **IPO** (2023 arXiv:2310.12036), **ORPO** (2024 arXiv:2403.17722), **KTO** (2024
     arXiv:2402.01306, unpaired data), **SimPO** (2024 arXiv:2310.16811) — DPO variants.
5. **RLAIF / constitutional approaches:** AI-feedback instead of human labels. **Constitutional
   AI (Bai et al. 2022, Anthropic, arXiv:2212.08073 [F])** — principles + critique/revision +
   SL-CAI; the template for Claude-class alignment. **RLAIF (Lee 2023, arXiv:2309.00267
     [F])** — Google.
6. **Rejection sampling / best-of-N:** sample N, keep the best per RM or verifier — the
   simplest "test-time compute" and the precursor of reasoning RL.
7. **Distillation:** teacher → student (logit or sequence level); GPT-3→GPT-4-class
   knowledge distillation; also used for **reasoning distillation** (DeepSeek-R1
   distilled Qwen/Llama "R1-distill" models [F: DeepSeek-R1 arXiv:2501.12948]).

## Why post-training matters (the research result)
Same base, different post-training → wildly different alignment/safety/verbosity
profiles. Base-model benchmarks understate assistant quality; post-training is where
"helpfulness, honesty, harmlessness" (HHH) is engineered [F: InstructGPT, Anthropic
system-card practice].

## Preference data — how it's collected
Human raters rank/annotate response pairs (thousands–millions of pairs at frontier
scale); rubrics per task; inter-rater agreement tracked [I: standard practice, sizes
UNVERIFIED per lab].

## Reward hacking (the core failure mode)
The policy exploits RM artifacts: verbosity bias, sycophancy, format gaming,
"jailbreak-then-restore" outputs that score well. Mitigations: KL penalty, RM
ensembles, process reward, iterative RM updates [I: literature consensus].

## Reasoning post-training (the 2024+ shift)
OpenAI o1 (2024) showed: **RL on long CoT with verifiable rewards** (math/code) →
emergent systematic search. DeepSeek-R1 (2025, arXiv:2501.12948 [F]) reproduced it with
GRPO and open weights — the "reasoning RL is a post-training technique" consensus.
See `Reasoning/README.md`.

## Alignment tradeoffs
Helpfulness vs safety; sycophancy vs disagreement; refusal calibration; capability vs
alignment tax (the "alignment tax" term [I]). No Pareto point is known — it's an
ongoing research frontier.

## Related
`Reasoning/README.md` · `Training/README.md` · `Agents/README.md` ·
`Evaluation/README.md` (how post-training quality is measured).

## Key Takeaways
Post-training = SFT + preference optimization + (increasingly) RL on verifiable tasks.
DPO is the research default; PPO still dominates frontier production; Constitutional AI
is the AI-feedback template; reward hacking is the standing failure mode.
