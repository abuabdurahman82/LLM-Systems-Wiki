# 20 — Future Research, Glossary & References
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
Where LLM distillation is going through 2026 and beyond: on-policy loops, agent and
multi-agent transfer, verifier-guided and reward distillation, distillation scaling
laws, cross-tokenizer methods, and reasoning compression — sorted into **established**,
**active research**, and **speculative**. Plus the glossary and the primary-source
bibliography for the whole section.

## Research directions (labeled per the section's evidence scheme)

| Direction | Status | What's established | What's open |
|---|---|---|---|
| On-policy distillation | **Active → productionizing** | dense per-token reverse-KL on student rollouts works; 9–30× cheaper than RL for reasoning gains [F: arXiv:2306.13649; Thinking Machines 2025] | teacher-serving economics at scale; black-box OPD; stability theory [Open Question] |
| Agentic distillation | Active | trajectory SFT builds tool-use skills (`13`) | on-policy agent KD at scale; environment-design effects; GUI transfer [Experimental] |
| Multi-teacher OPD | Active | specialist teachers scoring student rollouts beats mixing data [Research Result: 2026 reports, single-source] | conflict resolution; router learning; generalist-synergy data [Open Question] |
| Verifier-guided distillation | Established pattern | verification > volume (`07`) | verifier quality ceiling; verifier-gaming dynamics |
| Reward-model distillation | Established pattern | cheap RMs change RL/BoN economics (`12`) | fidelity-vs-bias transfer; process-RM compression |
| Distillation scaling laws | **Established (2025)** | compute-optimal teacher/student allocation exists; distillation beats supervised pretraining up to a compute level that scales with student size [F: arXiv:2502.08606] | LLM-specific constant fitting; reasoning-trace token scaling [Open Question] |
| Self-play / self-improvement loops | Active | iterate generate→verify→train works (STaR lineage, R1-Zero) | separation from RL proper; collapse conditions |
| Multimodal distillation | Active | VLM teacher → VLM student for perception+reasoning | text-KD tricks don't all transfer [Experimental] |
| Inference-time / test-time distillation | Speculative | — | "distilling" test-time search into weights; boundary with RL unclear [Open Question] |
| Cross-tokenizer KD | Early | response-KD is the workaround (`05`) | true distribution-level alignment across tokenizers [Open Question] |
| Synthetic-data optimization | Active | dedup/difficulty/curriculum matter (`14`) | principled data-value estimation |
| Reasoning compression | Active | traces can be shortened with quality retention [Research Result] | length-quality frontier; student-specific budgets |

Reading discipline for 2025–26 claims: a paper's benchmark table is *its* setting —
teacher, harness, thinking budget, contamination state. Require: same-harness
replication or a fresh-variant benchmark before treating as production-proven
[→ `17` discipline].

## Glossary (section-wide)

| Term | Meaning |
|---|---|
| Teacher / student | the capable-but-expensive source model / the smaller model being trained |
| Dark knowledge | similarity structure in the teacher's probabilities over non-answers (`02`) |
| Temperature (T) | softmax sharpening knob; T² compensates KD-loss gradients (`02`) |
| Forward / reverse KL | mode-covering / mode-seeking divergences (`03`) |
| Exposure bias | train-serve state mismatch from static teacher data (`10`) |
| On-policy KD | teacher scores the student's own rollouts (`10`) |
| GKD | Generalized Knowledge Distillation — on-policy data + divergence choice (`11`) |
| Response/sequence KD | SFT on teacher-generated text (`06`) |
| Reasoning distillation | transfer via verified chains of thought (`07`) |
| Best-of-N | sample N, verify, keep the best (`07`) |
| Top-K logit KD | keep K largest teacher probabilities per position (`05`) |
| Feature/attention KD | match hidden states / attention maps (`05`) |
| Patient KD | multi-layer intermediate matching (`05`, `09`) |
| Self-distillation | teacher = earlier/same-family instance of the model (`09`) |
| Multi-teacher KD | several teachers (ensemble/domain/routing) (`09`) |
| Preference distillation | transfer pairwise preference behavior (`12`) |
| Reward-model distillation | compress the judge/RM (`12`) |
| Agentic distillation | transfer tool-use trajectories (`13`) |
| Capacity gap | student cannot represent all teacher behavior (`01`) |
| Retention ratio | student score ÷ teacher score (shorthand, `17`) |
| Compression ratio | teacher params ÷ student params (`17`) |
| Contamination | benchmark answers leaked into training data (`14`) |
| Dataset distillation | compressing *datasets* — a different field (`14`) |
| Lineage | the full provenance record of a distilled model (`19`) |
| Break-even (N*) | C_distill ÷ (C_teacher − C_student) per-token costs (`17`) |

## Primary-source references (all verified this session)

**Classical & Transformer-era KD**
1. Buciluǎ, Caruana, Niculescu-Mizil — *Model Compression* (KDD 2006). [F]
2. Hinton, Vinyals, Dean — *Distilling the Knowledge in a Neural Network*. arXiv:1503.02531 (2015). [F]
3. Kim & Rush — *Sequence-Level Knowledge Distillation*. arXiv:1606.07947 (EMNLP 2016). [F]
4. Sanh et al. — *DistilBERT*. arXiv:1910.01108 (2019). [F]
5. Jiao et al. — *TinyBERT*. arXiv:1909.10351 (2019). [F]
6. Wang et al. — *MiniLM*. arXiv:2002.10957 (2020). [F]
7. Sun et al. — *MobileBERT*. arXiv:2004.02984 (2020). [F]
8. Menon et al. — *A Statistical Perspective on Distillation* (GC) / Furlanello et al. — *Born-Again Neural Networks*. arXiv:1805.04770 (2018). [F]
9. Pan et al. — *Patient Knowledge Distillation for BERT*. arXiv:1908.09355 (2019). [F]
10. Stanton et al. — *Does Knowledge Distillation Really Work?* arXiv:2106.05945 (2021). [F]
11. Beyer et al. — *Knowledge Distillation: A Good Teacher is Patient and Consistent*. arXiv:2106.05237 (2021). [F]

**LLM-era KD**
12. Gu et al. — *MiniLLM: Knowledge Distillation of Large Language Models*. arXiv:2306.08543 (ICLR 2024). [F]
13. Agarwal et al. — *On-Policy Distillation of Language Models (GKD)*. arXiv:2306.13649 (2023). [F]
14. Ko et al. — *DistiLLM*. arXiv:2402.03898 (2024); *DistiLLM-2*. arXiv:2503.07067 (2025). [F]
15. Xu et al. — *A Survey on Knowledge Distillation of Large Language Models*. arXiv:2402.13116 (2024). [F]
16. Shridhar et al. — *Distilling Step-by-Step* (2023) [reasoning-distillation antecedent]. [F]

**Reasoning & the flagship case**
17. DeepSeek-AI — *DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via RL*. arXiv:2501.12948 (2025) — pipeline, 800K dataset, six students, distill-vs-RL (Table 16), training costs (Table 7). [F]
18. Qwen Team — *Qwen3 Technical Report*. arXiv:2505.09388 (2025) — strong-model logit distillation for small models. [F]
19. Lu, K. et al. (Thinking Machines Lab) — *On-Policy Distillation*. thinkingmachines.ai/blog/on-policy-distillation (Oct 2025). [F]
20. Xie et al. — *Distillation Scaling Laws*. arXiv:2502.08606 (2025). [F]

**Alignment-transfer & agents (adjacent)**
21. Tunstall et al. — *Zephyr: Direct Distillation of LM Alignment*. arXiv:2310.16944 (2023). [F]
22. Zelikman et al. — *STaR: Self-Taught Reasoner*. arXiv:2203.14465 (2022). [F]
23. Ouyang et al. — *Training language models to follow instructions (RLHF pipeline context)*. arXiv:2203.02155. [F]

**Wiki-internal anchors (cross-sections)**
- `Post-Training/Alignment-RLHF.md` — SFT/RLHF/DPO/GRPO lineage [F]
- `Reasoning/README.md` — test-time compute, RLVR [F]
- `KV-Cache/README.md` — KV constants (128 KiB/token 8B-class) [E]
- `GPU-Systems/NCCL.md` — NVLink transfer references [E]
- `Evaluation-Engineering/Benchmark-Contamination.md` — contamination methods [F/E]
- `Speculative-Decoding/README.md` — draft/verify mechanics [F]

## Section 80/20 (the one-paragraph summary)
Distillation transfers capability, not weights: classical soft targets generalize to
LLMs as logits, features, and — dominating practice — verified responses and reasoning
traces. The recipe that broke the field open in 2025 (teacher traces + verification +
SFT → R1-Distill) and the recipe leading 2026 (teacher scores the student's own
rollouts — on-policy KD) are both data-and-signal engineering around the same KL core.
Measure everything per-harness, judge by capability-per-dollar, and remember the two
misconception guards: distillation ≠ quantization, and capability transfer ≠ alignment
transfer.

## Related
- `README.md` (this section) — the reading path and mental model
- `Post-Training/README.md` · `Reasoning/README.md` · `Quantization/README.md` ·
  `Speculative-Decoding/README.md` — the four neighbor pillars this section sits between
- `Learning-Path/Zero-to-Hero.md` — where to go next in the wiki
- `Latest-Research/README.md` — the rolling research radar (distillation watchlist)

## Key Takeaways
- The field's center of gravity has moved from "compress a model" to "transfer
  behavior" — traces, preferences, rewards, and now rollouts.
- Distillation scaling laws give the field its first predictive budgeting tool [F:
  arXiv:2502.08606]; everything 2026 beyond that is active research — label accordingly.
- The open questions that matter most in practice: black-box on-policy KD economics,
  agent-trajectory transfer at scale, and contamination-resistant evaluation.
