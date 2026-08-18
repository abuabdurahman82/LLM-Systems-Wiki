# Post-Training & Alignment — SFT → RLHF → DPO → RLVR
`LAST_UPDATED: 2026-08-18` · Status: core page · All citations [F]-verified against primary sources (arXiv, 2026-08-18); engineering claims labelled [I].

## 30-Second Explanation
A pretrained LLM is a *next-token engine*, not an assistant: it imitates web text, so it
hallucinates confidently, ignores instructions, and is unfiltered. **Post-training** turns it
into a usable system with three stages: (1) **SFT** — supervised fine-tuning on
instruction/response pairs; (2) **reward modeling** — learn a preference function from
human comparisons; (3) **RL** — optimize the policy against that reward. Since 2023 the field
has repeatedly re-derived stage 3 into cheaper forms (DPO) and replaced human preference with
verifiable rewards (RLVR), which is what powers 2024+ reasoning models.

## Why this exists (the problem it solves)
- Pretraining's objective (cross-entropy on web text) has **no notion of "helpful" or
  "safe"** — the web contains both, in equal measure, and both are fluent.
- Scale alone does not fix this: GPT-3-scale models are still chatty, sycophantic, and
  unsafe without alignment [F: InstructGPT, arXiv:2203.02155].
- The objective mismatch is *behavioral*: pretraining optimizes P(next token | web prior);
  we want P(best completion | instruction). Post-training is the bridge between those
  two distributions — and the part of the stack where "capability" and "usefulness"
  diverge.

## The lineage (what each step solved and what it left)
| Year | Work | Problem it solved | Limitation that followed |
|---|---|---|---|
| 2017–20 | **RL from human preferences** (Christiano et al., arXiv:1706.03741 [F]; Stiennon et al., arXiv:2009.01325 [F]) | the SFT→RM→PPO loop on RL/summarization tasks — *before* LLMs | small tasks; not at LLM scale |
| 2022 | **InstructGPT** (Ouyang et al., arXiv:2203.02155 [F]) | the SFT→RM→PPO-RLHF pipeline **at LLM scale**; smaller aligned GPT-3 preferred over *unaligned* larger GPT-3 | 3-model cost (policy + RM + ref); PPO instability; reward-hacking |
| 2022 | **Anthropic HH** (Bai et al., arXiv:2204.05862 [F]) | helpful/harmless RLHF on GPT-J/XL | same 3-model cost; single-preference-dimension RM |
| 2022 | **Constitutional AI** (Bai et al., arXiv:2212.08073 [F]) | AI-generated critique + revision reduces human label cost | critique quality bounds revision quality; self-correction limits |
| 2023 | **DPO** (Rafailov et al., arXiv:2305.18290 [F]) | eliminate the RM: closed-form optimum of KL-constrained preference objective is a *classifier* on pairs → direct policy update | off-policy; degrades if preferences drift; sensitivity to temperature β |
| 2024 | **OpenAI o1 / DeepSeek-R1** (o1 training per OpenAI reports [A: details not fully published]; R1 arXiv:2501.12948 [F]) | **RLVR**: reward = verifiable correctness (math/code/unit tests), no human preferences | only where answers are checkable; reward-hacking on verifiers; cost of thinking tokens |
| 2024–25 | **RLAIF / RLAIF-V** (arXiv:2405.17220 [F]) | AI feedback at scale approximates human preference | circularity: teacher's blind spots get amplified; needs strong teacher |
| 2024–25 | **Tulu 3** (arXiv:2411.15124 [F]) | open recipe: SFT + DPO + iterative DPO on open data | gap vs closed models persists but narrows |

## How it works — the math

### Stage 1: SFT (behavior cloning)
Minimize cross-entropy on (instruction, ideal response) pairs:
`L_SFT = -Σ log π_θ(r_t | r_<t, x)`. Cheap, stable, but it can only imitate *what humans
wrote* — the ceiling is the demonstration quality, and MLE fine-tuning tends toward
*averaged*, over-dispersed outputs (it fits the data distribution, not a single best
response [I]).

### Stage 2 (classic RLHF): reward model + PPO
1. **RM:** Bradley-Terry over preference pairs: `L_RM = -E[ log σ( r_θ(x, y_w) - r_θ(x, y_l) ) ]`.
2. **RL:** maximize `E[r_θ(x,y)] - β·KL(π_θ ‖ π_ref)` via PPO (Schulman et al., arXiv:1707.06347
   [F]; the InstructGPT run is the reference LLM-scale implementation [F: arXiv:2203.02155]).
   - `π_ref` = SFT policy (KL anchor that prevents reward hacking).
   - Three models live in memory at once: policy, reference, RM → ~3× SFT memory cost [I].
   - **Overoptimization:** reward is a proxy; KL-regularized optimal policy still
     *exploits* RM gaps. Gao et al. 2023 ("Scaling Laws for Reward Model
     Overoptimization", arXiv:2210.10760 [F]) show reward and *true* utility diverge as
     RL strength grows; the 2024 follow-up extends this to DPO-style direct
     alignment (arXiv:2406.02900 [F]: reward and true utility diverge as alignment
     strength grows, with a computable "overoptimization cliff").

### DPO: the closed-form shortcut
The KL-regularized RL objective has a known closed-form optimal policy:
`π*(y|x) = (1/Z)·π_ref(y|x)·exp(r_θ(x,y)/β)`. Substituting into Bradley-Terry gives a
loss on pairs *without any RM or RL loop*:
`L_DPO = -E[ log σ( β·( log π_θ(y_w)/π_ref(y_w) - log π_θ(y_l)/π_ref(y_l) ) ) ]`.
- **Wins:** one model in memory, stable SGD dynamics, competitive quality vs PPO-RLHF at
  scale [F: arXiv:2305.18290; Zephyr-7B arXiv:2310.16944 (DPO-distilled from Llama-2-Base)];
  (note: Llama-2-*Chat* itself used PPO-RLHF, not DPO [F: arXiv:2307.09288]).
- **Limits:** implicit RM is fixed at training time → can't iterate; off-policy data
  degrades it; β (reference-temperature) is the single most sensitive hyperparameter
  [I: consistent across Zephyr, Tulu 3, open Llama-2-DPO runs].

### RLVR (the 2024+ replacement for the preference loop)
Where a *verifier* exists (math: final answer match or step checkers; code: unit tests;
agentic: environment reward), drop human preferences entirely:
- **Outcome RL (GRPO):** sample G completions per prompt; advantage =
  (reward − group mean)/group std (normalized within the group); no value model.
  DeepSeekMath introduced GRPO (arXiv:2402.03300
  [F]); DeepSeek-R1 scaled it to ~14k-token CoT (arXiv:2501.12948 [F]).
- **Process RL (PRM):** reward per step (Lightman et al., "Let's Verify Step by Step",
  arXiv:2305.20050 [F]); needs step-level labels → expensive but better credit
  assignment.
- **Why it works where RLHF stalled:** reward is *objective* and *dense* (a test suite
  gives many independent pass/fail signals vs a human's single preference rating [I]),
  which narrows the proxy-to-true gap that drove overoptimization — but does NOT remove
  it: reward-hacking of the *verifier* (overfitting the test distribution, gaming the
  checker) is now the standing failure mode, so it only helps where verification is
  cheap *and* faithful.

## Limitations (what's still unresolved)
- **Reward hacking / Goodhart:** any proxy reward gets exploited; KL anchors only slow
  it, they don't stop it [F: Gao et al. 2022, arXiv:2210.10760; "Scaling Laws for Reward
  Model Overoptimization in Direct Alignment Algorithms" (2024), arXiv:2406.02900].
- **Alignment tax:** alignment can reduce capability on narrow tasks (InstructGPT
  reported this on coding) [F: arXiv:2203.02155 §5].
- **Distribution shift:** SFT→RM→RL each shift the data the next stage sees; DPO's
  implicit RM is the worst offender (no retraining loop) [I].
- **Sycophancy & preference instability:** human labels disagree (30–40% pair
  disagreement is normal [I: consistent across published annotation studies]); the RM
  learns the *average annotator*, not the *user*.
- **Verifier dependence (RLVR):** reward-hacking of the *verifier* is the new failure
  mode; test-distribution overfitting; unit tests don't capture spec conformance [I].
- **Cost:** a full RLHF pass historically cost 10–100× the SFT pass in GPU-hours [I:
  consistent across open run reports].

## What changed in modern LLMs (the 2024–2026 state)
- **Default pipeline (contested):** SFT → a preference stage (DPO / iterative DPO for
  research; PPO- or GRPO-style RLHF still common in production) → optional RLVR for the
  reasoning tier. Which of {PPO, DPO, GRPO} a given lab ships is not settled and shifts
  by cost/quality trade-off [I: consistent across open recipes and vendor notes].
- **Reasoning tiers** (o1/o3, R1, Qwen3-thinking, Gemini 3, Claude 4.5/5): RLVR-trained
  CoT policies with user-selectable "effort" — post-training became a *product surface*
  (`Reasoning/README.md`).
- **Open weights:** Tulu 3 + Zephyr + Llama-2-Chat + Qwen-Instruct show the open
  alignment gap is closing but not closed (closed models still win on hard preference
  data and scale of RLVR compute) [F: Tulu 3 report].
- **Safety:** Constitutional AI → RLAIF → "constitution + self-critique" loops are the
  dominant open-weight safety story [F: arXiv:2212.08073].

## Related
`README.md` (post-training index) · `Reasoning/README.md` (test-time scaling, RLVR
lineage) · `Post-Training/Distillation.md` (expand) · `Safety/README.md` ·
`Inference/Inference-Metrics.md` (cost of thinking tokens) · `Labs/Lab-9` (expand).

## Key Takeaways
1. Post-training is the *bridge* between "predicts the next web token" and "follows
   instructions" — it exists because pretraining's objective has no usefulness term.
2. Classic RLHF = SFT + RM + PPO (3 models; first at LLM scale in InstructGPT, though
   the loop predates it by Christiano 2017 / Stiennon 2020). DPO collapsed that to 1
   model; RLVR replaced *preferences* with *verifiers* where possible — narrowing, not
   eliminating, the proxy-to-true gap.
3. The open problem moved from "how do we align" to "how do we align *while scaling
   test-time compute* without Goodhart'ing the reward."

## References (verified 2026-08-18 via arXiv API)
- Christiano et al. 2017 — Deep RL from human preferences. arXiv:1706.03741 [F]
- Stiennon et al. 2020 — Learning to summarize from human feedback. arXiv:2009.01325 [F]
- Ouyang et al. 2022 — InstructGPT. arXiv:2203.02155 [F]
- Rafailov et al. 2023 — DPO. arXiv:2305.18290 [F]
- Bai et al. 2022 — HH-RLHF. arXiv:2204.05862 [F]
- Bai et al. 2022 — Constitutional AI. arXiv:2212.08073 [F]
- Schulman et al. 2017 — PPO. arXiv:1707.06347 [F]
- Gao et al. 2022 — Scaling Laws for RM Overoptimization. arXiv:2210.10760 [F]
- "Scaling Laws for Reward Model Overoptimization in Direct Alignment Algorithms" (2024). arXiv:2406.02900 [F]
- Touvron et al. 2023 — Llama 2 (PPO-RLHF chat models). arXiv:2307.09288 [F]
- Zephyr: Direct Distillation of LM Alignment (2023). arXiv:2310.16944 [F]
- Lightman et al. 2023 — Let's Verify Step by Step. arXiv:2305.20050 [F]
- Shao et al. 2024 — DeepSeekMath / GRPO. arXiv:2402.03300 [F]
- DeepSeek-AI 2025 — DeepSeek-R1. arXiv:2501.12948 [F]
- RLAIF-V (2024). arXiv:2405.17220 [F]
- Wang et al. 2024 — Tulu 3. arXiv:2411.15124 [F]
