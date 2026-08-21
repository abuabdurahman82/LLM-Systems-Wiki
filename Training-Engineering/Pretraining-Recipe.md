# The Pretraining Recipe — from corpus to converged model

`LAST_UPDATED: 2026-08-20` · Status: core page · Part of `Training-Engineering/`

> This is the *operational* recipe: given a compute budget, what data, what
> model, what optimizer, what schedule, in what order. The math of scaling
> lives in `Scaling-Laws.md`; the multi-GPU mechanics in `Parallelism.md`.

## 30-second explanation

Pretraining = next-token cross-entropy over a curated multi-trillion-token
corpus, run to compute-optimal (or deliberately over-trained) point, with the
whole pipeline engineered so the *effective* FLOPs spent are close to the
*nominal* FLOPs budget. The recipe has five stages, each with its own
failure mode: data (poisoning/duplicates), schedule (loss spikes),
precision (overflow), parallelism (comm bubbles), stability (NaN).

## Stage 1 — Data

### 1.1 Sources & scale
Frontier corpora are 10–16T tokens: DeepSeek-V3 14.8T [F: 2412.19437],
Kimi K2 15.5T [F: 2507.20534], Llama-3 15T [F: 2407.21783], Qwen3
~36T [I: Qwen3 report 2505.09388 — re-verify against the paper when
fetching full text]. Mix: web (60–80%), code (5–15%), books/academic
(5–15%), synthetic (growing share 2025–26) [I: standard mix across
open reports; exact ratios vary by lab and are usually undisclosed].

Open reference corpora:
- The Pile — Gao et al. 2020, 825GB curated mix. arXiv id UNVERIFIED
  this session (candidate `2101.00037` resolved to an *unrelated HEP
  paper* — do not cite until re-verified).
- RedPajama — `2411.12372` [F] — open reproduction of LLaMA's
  training mix (V1 ≈ 1T tokens) plus a much larger web-only V2; the
  combined datasets span >100T tokens (open crawl + dedup + quality
  signals).
- The Stack v2 (BigCode) — the standard open code corpus; arXiv id
  UNVERIFIED this session (candidate `2312.08568` resolved to an
  unrelated image-synthesis paper).
- FineWeb — `2406.17557` [F] — HuggingFace's 15T-token web corpus, the
  default open pretraining web set in 2024–26.
- DataComp-LM — `2406.11794` [F] — LM analogue of DataComp: curated
  dataset + leaderboard, the "ImageNet for LLMs" framework.
- DoReMi — `2305.10429` [F] — learns domain *mixing weights* by
  proxy-model proxy-loss; the canonical "mixture is a research
  problem" paper.

### 1.2 Cleaning (the part that shows up in quality)
1. **URL / document dedup** — exact URL, exact text, near-dup (MinHash /
   SimHash) [F: Lee et al. 2021, "Deduplicating Training Data Makes
   Language Models Better" `2107.06499`]. Duplicates → memorization
   artifacts + inflated data count.
2. **PII redaction** — regex + NER; compliance-driven. [I: standard]
3. **Language ID** — fasttext / lid; keep target-language fraction.
4. **Quality filtering** — C4-style heuristics (line-length, stopword
   ratio, "words per second" of text) [I: GPT-3 recipe]. Modern:
   classifier-based (FineWeb-Edu), perplexity-based.
5. **Decontamination** — holdout eval sets (MMLU, GSM8K, HumanEval…)
   scrubbed from train by exact + n-gram overlap. [I: mandatory in 2024+;
   see `Evaluation/Benchmark-Contamination`.]

### 1.3 Mixture & curriculum
- **Static mixture**: fixed domain ratios through training. [I: most runs]
- **DoReMi-style learned mixture** [F: 2305.10429]: train a small proxy,
  optimize domain weights to equalize relative loss, transfer to the big
  model.
- **Curriculum / staged**: base corpus → (code/math-heavy mid-train) →
  long-context extension (Llama-4 "mid-training") [F: 2601.11659] → SFT.
  [I: the "mid-training" long-context stage is now standard for
  32k→128k+ context.]

## Stage 2 — Model (see `Model-Anatomy.md`)

Pick (N, L, d, h, d_ff, MoE?) per the scaling-law point for the chosen
compute budget (next section). 2025–26 defaults [I: consistent across
open reports]:
- Pre-norm RMSNorm, RoPE, GQA (4–8 KV groups), SwiGLU, tied embeddings
  below 70B, no biases, MTP head optional (DeepSeek-V3-class).
- Context length: 8k → 32k base, 128k–1M with mid-training extension
  [I: Llama-4 Scout 10M context, DeepSeek 128k standard].

## Stage 3 — Optimization

### 3.1 Optimizer
- **AdamW** (Adam + decoupled weight decay) [F: Kingma 1412.6980;
  Loshchilov 1711.05101] — the default for everything ≤ Llama-3/Qwen3.
- **Muon** (2024–25, New-Isaac / Kaggle era; popularized by
  PyTorch `torch.optim.muon` [I: repo reference, UNVERIFIED arXiv id
  this session]) — Newton-Schulz orthogonalization of momentum for
  2-D matrices, elementwise Adam for embeddings; ~1.2–1.5× token
  efficiency claimed by Kimi K2's MuonClip variant [F: 2507.20534].
  MuonClip adds QK-clip for stability and was used on all 15.5T K2
  tokens with **zero loss spikes** [F: 2507.20534].
  [I] Muon is the 2025–26 "new optimizer to watch"; not yet the default.

### 3.2 LR schedule
Warmup (linear, ~1000–2000 steps [I]) → **cosine decay to ~10% of peak**
[F: standard across LLaMA/Llama-2/Qwen reports]. Peak LR: 3e-4 for 7B,
1.5e-4 for 70B, 1.0e-4 for 1T-MoE [I: roughly scales as N^-0.4].
Weight decay 0.1 (params) / 0 (biases, norms, embeddings) [I].

### 3.3 Precision
- **BF16** compute (forward + backward) + **FP32 master weights +
  FP32 Adam state** [F: mixed-precision recipe, Gupta et al.
  `1712.01192`].
- **FP8** (Hopper+) forward/backward with FP32 master — DeepSeek-V3
  trained on H800s with FP8 [F: 2412.19437, "H800" in report]; 2×
  compute/byte vs BF16 with careful scaling [I].
- **Optimizer state in FP32** is not optional: BF16 Adam state →
  divergence at ~1e5 steps [I: consistent failure mode].

### 3.4 Gradient handling
- Norm clipping at 1.0 [I: universal].
- **Loss-spike policy**: on spike, roll back to last clean checkpoint,
  optionally lower LR / skip the data shard. DeepSeek-V3: 0
  irrecoverable spikes over 14.8T tokens [F: 2412.19437]; Kimi K2: 0
  spikes over 15.5T [F: 2507.20534]; Llama-3: the report documents a
  loss-spike rollback procedure and multiple handled spikes (exact
  count in the full text, not the abstract) [F: 2407.21783].

## Stage 4 — Schedule (how the tokens get spent)

**Total tokens D = C / (6·N)** at 100% MFU [E: algebra, see
Scaling-Laws]. The practical schedule is:

```
step 0:    warmup LR, B = min(B_max, steps-to-convergence)
steady:    constant batch B for ~90% of D
cooldown:  optional batch ramp ×4–8 (more tokens/step, less steps)
```

**Batch-size logic [I: Megatron-3-era practice; 3D-parallelism paper id UNVERIFIED
this session]:**
- Start with a batch large enough that loss is stable (no gradient
  noise floor visible).
- Keep it constant until LR cooldown; optionally ramp batch in the last
  10–20% (each step sees more tokens → "free" extra data at the same
  compute cost, up to the point where gradient averaging across the
  batch stops helping).
- Global batch for 2024–26 frontier: ~10^7–10^8 tokens/step
  [I: e.g. DeepSeek-V3 §4.1 (verified 2026-08-20, full text): batch
  size in *sequences* ramps 3072 → 15360 over the first 469B tokens,
  then held at 15360; at S ≈ 8–16K that's ≈10^7–2.5×10^8
  tokens/step, and 14.8T tokens ÷ ~1.5×10^7 ≈ ~1.48M steps.
  Llama-3 405B used ~4M tokens/step [I].]

## Stage 5 — Infrastructure (what actually makes it run)

| Concern | Standard answer | Page |
|---|---|---|
| Model fits? | ZeRO-3 / FSDP + activation checkpointing | `Parallelism.md` |
| Fast enough? | DP×TP×PP×EP(+SP) decomposition | `Parallelism.md` |
| Network? | NVLink intra-node TP; IB/RoCE inter-node DP/EP | `Networking/` |
| Stable? | Sync checkpoints + fast restart + spike policy | `Scaling-1-to-10k.md` |
| Measurable? | MFU target 40–60% [I: reported range] | `Interaction.md` |

**MFU = achieved FLOPs / (peak FLOPs × wall time)**. MegaScale: 55.2%
at 175B/12,288 GPUs [F: 2402.15627]. DeepSeek-V3: ~30–40% [I: back out
from 2.788M H800-GPU-hours, 14.8T tokens, 671B/37B-act MoE — see
Interaction.md §cost model; the paper does not state MFU directly].
**[E] Hand check on DeepSeek-V3 (MFU):**
MFU is defined against the **6·N·D** forward+backward FLOPs.
activated N ≈ 37e9, D = 1.48e13 tokens:
- 6·N·D = 6 × 37e9 × 1.48e13 = **3.29e24 FLOP** [E]
- Time = 2.788e6 GPU-hours × 3600 s = 1.004e10 s
- H800 peak BF16 ≈ 989 TFLOP (H100-class compute; H800 matches H100
  on FLOPs, cuts NVLink) [F: vendor spec — H100 SXM]
- Ideal FLOPs in that time = 989e12 × 1.004e10 = **9.93e24** [E]
- **MFU ≈ 3.29e24 / 9.93e24 ≈ 33%** [E]
Interpretation [I]: ~33% on the raw 6·N_act·D/peak/wall-clock
basis (wall-clock = 2.788M GPU-h / 2048 GPUs = 1,361 h
[E]) is a *low* reading on the activated-FLOPs basis — the
dense-model reference range is 40–60% [I: MegaScale 55.2%
at 175B dense, F: 2402.15627]. The gap is explained by MoE
AllToAll overhead + 57 days of stability overhead [I].
Cross-check in `Interaction.md`. (Caveat: assumes H800 = H100 peak FLOPs and
dense-equivalent 6·N·D despite sparsity; treat as order-of-magnitude,
not a published figure.)

## What "done" looks like (stage transitions)

```
pretrain (this page)
   → SFT (supervised fine-tune on instruction data; ~10^6–10^7 examples)
   → (optional RM) → PPO / DPO / GRPO alignment   [Post-Training/]
   → (optional RLVR / RL loop)                     [Post-Training/]
   → (optional distillation to smaller model)      [Post-Training/]
```

**2025–26 shift [I: consistent across open reports]:** the *pretraining
budget* is now a smaller fraction of total compute; DeepSeek-V3.2 and
Kimi K2 both report heavy post-training RL scaling, and the open-weights
frontier moved from "better base" to "better alignment + agentic data
synthesis". [F: 2512.02556 (V3.2: "scaling post-training compute");
2507.20534 (K2: "large-scale agentic data synthesis pipeline" +
"joint RL stage").]

## Failure modes (the checklist)

1. **Loss spike** — one step's loss jumps; usually a bad data shard or
   a numerics edge case. Policy: rollback + skip shard.
2. **NaN** — underflow/overflow in BF16/FP8; usually a kernel bug or
   LR too high. Policy: roll back, audit the kernel.
3. **Straggler GPU** — one node 20% slower (thermal, ECC, IB retry
   storm); AllReduce waits on the slowest. Policy: detect + replace
   (MegaScale §5–7 [F: 2402.15627]).
4. **Comm hang** — NCCL deadlock on a flaky link; policy: timeout +
   rank-dump + reschedule.
5. **Data pipeline starvation** — dataloader can't keep up at
   10^7 tokens/step; policy: pre-tokenized sharded dataset,
   multiple readers, prefetch. [I: standard]

## Key takeaways

1. Pretraining = data × model × optimizer × schedule × infrastructure;
   each has a binding constraint (duplicates / compute budget /
   numerics / token count / MFU).
2. The 2024–26 frontier moved to **FP8 + MoE + Muon-class optimizers +
   zero-spike discipline**; DeepSeek-V3 (0 irrecoverable spikes,
   2.788M H800-hours) and Kimi K2 (0 spikes, MuonClip) are the
   reference runs.
3. **Post-training is now where the frontier moves** — pretraining
   converged; the 2025–26 reports spend more on RL + synthetic agentic
   data than the previous generation did.

## References (ids verified live 2026-08-20 unless marked)

DeepSeek-V3 `2412.19437` · DeepSeek-V3.2 `2512.02556` · Kimi K2
`2507.20534` · Qwen3 `2505.09388` · Llama 3 `2407.21783` · Llama 4
`2601.11659` · FineWeb `2406.17557` · DataComp-LM `2406.11794` ·
DoReMi `2305.10429` · RedPajama `2411.12372` · Lee et al. dedup
`2107.06499` · Adam `1412.6980` · AdamW `1711.05101` · Mixed-precision
`1712.01192` · MegaScale `2402.15627`. UNVERIFIED this session: Pile
`2101.00037` (wrong candidate), The Stack, Muon (covered under Kimi
K2 `2507.20534`), 3D-parallelism id, DeepSpeed OSDI'20 arXiv id.
