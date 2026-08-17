# Reasoning Models — Test-Time Compute
`LAST_UPDATED: 2026-08-16` · Status: core section

## 30-Second Explanation
The 2024–2026 shift: instead of spending compute at *training* time to get a better
single answer, spend compute at *inference* time — let the model "think" (long chain of
thought), verify, retry. The model is the engine; the reasoning process is the
drive-time. This is **test-time scaling**, and it's the third scaling axis after model
size and data.

## The research lineage (why each step mattered)
| Year | Work | Problem solved | Limitation that followed |
|---|---|---|---|
| 2022 | **Chain-of-Thought** (Wei et al., arXiv:2201.11903 [F]) | Few-shot prompting that elicits multi-step reasoning | needs CoT examples; unreliable |
| 2022 | **Self-Consistency** (Wang et al., arXiv:2203.11171 [F]) | Sample multiple CoTs, majority-vote | cost ×N; still prompt-level |
| 2023 | **Tree of Thoughts** (Yao et al., arXiv:2305.10306 [F]) | deliberate search over thought trees | expensive; needs value function |
| 2022 | **ReAct** (Yao et al., arXiv:2210.03629 [F]) | interleaved reasoning + *tool* action | agent scaffold, not model capability |
| 2023 | **Process supervision** (Lightman et al., arXiv:2305.16896 [F]) | reward the *steps*, not just the outcome | step-label data expensive |
| 2023 | **Outcome supervision** (standard RLVR) | reward only final answer | sparse credit assignment |
| 2024 | **OpenAI o1 / o3** (2024–2025) [F: OpenAI reports] | RL on long CoT with verifiable rewards → emergent search, backtracking | closed; cost; latency |
| 2024 | **DeepSeek-R1** (arXiv:2501.12948 [F]) | open reproduction: GRPO + rule-based rewards + distillation | open weights; reasoning on verifiable domains first |
| 2024–25 | **Qwen3, GPT-5.x, Claude 4.x/5, Gemini 3.x** reasoning tiers [F: vendor] | "thinking" as a product tier (effort levels) | — |
| 2025–26 | **Process RL, verifiers, search-based reasoning, self-reflection** [I: literature] | — | — |

## The three transitions (the big picture)
1. **Larger pretrained model** (2018–2023): more params → better single-shot.
2. **Post-trained reasoning model** (2024+): RL on CoT with verifiable rewards → the
   model *learns* to reason; test-time compute buys accuracy.
3. **Agentic reasoning system** (2025+): model + tools + memory + verification loops
   (`Agents/README.md`, `Harness-Engineering/README.md`) — reasoning spread across the
   system, not just the forward pass.

## Mechanisms (how modern reasoning models actually work)
- **Long CoT generation** (thousands–100k+ tokens of internal reasoning) — the "thinking
  budget" is now a product knob (effort levels in OpenAI/Anthropic/Gemini APIs [F:
  docs]).
- **Verification:** internal self-checks, external tools (code execution, search),
  process-reward models [I].
- **Search:** best-of-N, tree search, Monte-Carlo-style sampling over solutions
  [F: o1-era reports; Self-Consistency lineage].
- **RL algorithm:** PPO (OpenAI-era), **GRPO** (DeepSeek-R1; group-relative advantage,
  no value model [F: arXiv:2402.03300 "DeepSeekMath"]), RLOO/REINFORCE variants.
- **Distillation of reasoning:** teacher CoT → smaller student (R1-distill-Qwen/Llama
  [F]); "reasoning tokens" as a transferable artifact.

## Test-time compute — the economics
- Tokens-of-thought are *inference cost*: reasoning models spend 10–1000× more output
  tokens. The roofline implication: reasoning load is **decode-heavy** (long outputs),
  so bandwidth optimization + speculative decoding matter more for them. [I]
- **Reasoning ≠ always better:** easy tasks waste budget; "thinking budgets" should be
  adaptive. Open research [I].

## Failure modes
- **CoT unfaithfulness:** the stated reasoning may not match the actual computation
  (Turpin et al. 2023 arXiv:2305.04388 [F]); the model can "speak" reasoning without
  "doing" it.
- **Reward hacking on verifiers:** overfitting to the test distribution.
- **Latency/cost collapse:** 60s × $ answers for questions that needed 1s.

## Related
`Post-Training/README.md` · `Agents/README.md` · `Inference/Inference-Metrics.md` ·
`Harness-Engineering/README.md`.

## Key Takeaways
Reasoning = test-time scaling. The lineage: CoT prompting → RL on CoT (o1/R1) →
agentic systems. The open questions: faithfulness, adaptive budgets, and whether
test-time compute eventually substitutes for model scale.
