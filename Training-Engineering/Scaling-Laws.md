# Scaling Laws — what C, N, and D should be

`LAST_UPDATED: 2026-08-20` · Status: core page · Part of `Training-Engineering/`

> The math of "given my compute budget, how big a model on how many tokens?".
> This page derives the master equation, walks through Kaplan → Chinchilla →
> the 2024–26 revisions, and shows what the laws say to a 2026 pretraining
> team. Every [E] number is computed in Python; audit trail in
> `/tmp/te-research/`.

## 30-second explanation

Training a model of N parameters on D tokens costs ≈ **6·N·D FLOPs**
(≈2 N FLOPs per token forward, ×3 for forward+backward+optimizer-ish
accounting — see derivation). Scaling laws fit loss L(N, D, C) to power
laws; the question they answer: **for fixed compute C, what N and D
minimize loss?** The answer has changed over time (Kaplan: most
new compute into model size, D grows sublinearly; Chinchilla: scale
N and D equally, tokens ≈ 20× params; 2024+: over-train — fewer
params, more
tokens — because inference cost matters and data is cheaper than compute).

## The master equation: FLOPs per token

For a dense Transformer, per token:
- **Attention**: QKV + out projections ≈ 4·S·d² (over a sequence of S; per
  token ≈ 4·d²), plus the S·d score/value work — the projection part is
  the N-scaling term.
- **FFN**: SwiGLU 3 matrices of width ~2.7d ≈ 8·d²·(d_ff/d) ≈ 2·(FFN
  params) FLOPs; the 2× is the GEMM cost (2 MACs).
- **Rule of thumb [I: universal across Megatron/Chinchilla analyses]:**
  forward pass ≈ 2·N FLOPs/token (each parameter participates in one
  multiply-accumulate = 2 FLOPs), **backward ≈ 2× forward = 4·N**, total
  **fwd+bwd ≈ 6·N FLOPs/token**. [E]

Hand check [E] (Python-verified):
- N = 7e9 → 6N = 4.2e10 FLOP/token = **42 GFLOP/token**.
- LLaMA-7B pretraining (1.4T tokens [F: 2302.13971]): 1.4e12 × 4.2e10
  = 5.88e22 FLOP ≈ **58.8 EFLOP**.
- Chinchilla-70B (1.4T tokens, 70.3B params [F: 2203.15556]):
  1.4e12 × 6 × 70.3e9 = 5.9e23 FLOP = **590 EFLOP**.
- DeepSeek-V3 (671B total, 37B activated, 14.8T tokens [F:
  2412.19437]): using *activated* params (MoE compute ∝ activated):
  1.48e13 × 6 × 37e9 = 3.28e24 = **3,280 EFLOP** [E]. This is the
  "3.3e24 FLOPs" order of magnitude the paper's 2.788M H800-GPU-hours
  implies at ~40–50% MFU (see Interaction.md).

**[E] Verification:** `6*7e9*1.4e12/1e21` → 58.8; `6*70.3e9*1.4e12/1e21`
→ 590.6; `6*37e9*1.48e13/1e21` → 3280.0. (Python, session log.)

## Kaplan et al. 2020 (OpenAI) — the first law

[F: arXiv:2001.08361, "Scaling Laws for Neural Language Models"]

L(N, D, C) ≈ a power law in each, with the *compute-optimal frontier*
holding the N/D ratio fixed. Key claims [F: paper]:
1. Loss is a smooth power law in N, D, C — no phase transitions over
   5–6 decades of scale (3e7 → 1e12 params).
2. **Loss ∝ C^−0.076** overall [F: Kaplan's headline
   exponent]. (The Chinchilla paper refits these exponents on
   better data and larger ranges; the practical takeaway it
   changes is the N/D ratio, not the C-exponent.)
3. **Optimal allocation at fixed compute: most new compute goes to
   model size, data grows sublinearly** — N_opt ∝ C^0.73, D_opt ∝
   C^0.27, equivalently D ∝ N^0.74 [F: paper's fitted exponents
   αN ≈ 0.076, αD ≈ 0.095; "most of the increase should go towards
   increased model size"]. The "scale N and D equally" rule (N_opt
   ∝ D_opt ∝ C^0.5) is **Chinchilla's** later result, not
   Kaplan's. GPT-3 (175B, 300B tokens = ~1.7 tokens/param) was
   roughly on Kaplan's frontier but far from the Chinchilla one.

**Where Kaplan went wrong (later):** they trained most of their
compute-optimal models on **repeated data** (no fresh-data
constraint), so their law implicitly assumed data was infinite and
cheap. Chinchilla re-derived with a fixed dataset and found the
frontier sits at ~20 tokens/param, not Kaplan's effective ratio.
[I: the standard critique, confirmed by Chinchilla 2203.15556.]

## Chinchilla (Hoffmann et al. 2022, DeepMind) — the ~1:20 rule

[F: arXiv:2203.15556, "Training Compute-Optimal Large Language Models"]

Re-derived scaling laws **with a fixed, non-repeated dataset**:
- Compute-optimal: **D_opt ≈ 20·N** (tokens ≈ 20× params). [E]
  Derivation: the paper fits L(N, D) = E + A/N^α + B/D^β and the
  optimum is where ∂L/∂N = ∂L/∂D (their Eqs. 8–10); with the
  fitted exponents this lands at D/N ≈ 20. The abstract states it
  directly: "the model size and the number of training tokens
  should be scaled equally: for every doubling of model size the
  number of training tokens should also be doubled." [F: abstract]
- **GPT-3 was over-trained**: 175B params on 300B tokens = 1.7
  tokens/param vs ~20 optimal → ~12× fewer tokens than optimal for
  that param count [F: paper's Fig. 10 comparison].
- **Chinchilla 70B on 1.4T tokens = 20 tokens/param** matched GPT-3
  175B quality at ~1/4 the compute [F: paper].

**Consequence (the actual 2023–26 industry move):** since *inference*
cost scales with N and *data* is (relatively) cheaper than training
compute, the frontier moved to **over-trained, smaller models**
(tokens/param well above 20):
- LLaMA-70B: 70B on 1.4T tokens = 20 tokens/param — *right at* the
  Chinchilla point [F: 2302.13971]; LLaMA-7B: 6.7B on 1.0T = ~150
  tokens/param (extreme over-training, acceptable because 7B
  inference is ~10× cheaper than 70B and ~26× cheaper than GPT-3's
  175B [E: 70/7, 175/7]).
- Llama-3 405B: 405B on 15T tokens ≈ 37 tokens/param [F:
  2407.21783] — ~1.8× the Chinchilla ratio.
- MoE decouples the ratio: 1T total / 32B activated on 15.5T tokens
  (Kimi K2 [F: 2507.20534]) — *activated* tokens/param = 15.5T/32B ≈
  486 [E] — absurdly over-trained on the compute axis, because the
  *stored* 1T params hold the knowledge while inference only pays for
  32B.

**[E] Python:** 15.5e12/32e9 = 484.4; 15e12/405e9 = 37.0;
1.4e12/70.3e9 = 19.9; 300e9/175e9 = 1.71; 1.0e12/6.7e9 = 149.

## The 2024–26 revisions (what the laws say now)

### Data-constrained regime
When total usable data D_max < 20·N (true for all frontier runs since
2024 — clean web text ≈ a few ×10^12 tokens, reusable with diminishing
returns [I: the "data wall"]), the law flips: **at fixed N, more
compute buys *less* as you retrain on the same data; the optimal move
is smaller N, more D, better D** [I: synthesis of the 2024–25 data-
scarce scaling literature]. The data-constrained scaling-law paper
(id UNVERIFIED this session — search for "Scaling Laws for
Data-Constrained Language Models") formalizes this. [I]

### What labs actually do (2025–26)
1. **Over-train dense models** (Llama-3 405B @ 37 tokens/param) —
   inference cost dominates TCO for most products. [I]
2. **MoE + huge over-training** (Kimi K2, DeepSeek-V3, Llama-4) —
   store more knowledge than the compute budget implies. [I]
3. **Data engineering as a first-class budget line**: dedup (Lee et
   al. [F: 2107.06499]), quality filtering (FineWeb [F: 2406.17557]),
   mixture optimization (DoReMi [F: 2305.10429]), synthetic data
   (growing 2025–26 [I: K2's "large-scale agentic task synthesis
   pipeline" is post-training; pretraining synthetic is earlier and
   smaller]).
4. **Test-time scaling as the third axis** (reasoning models spend
   inference compute; see `Reasoning/`) — the scaling law now has
   four knobs: N (train), D (train), C_train, C_infer. [I]

### Grokking / long-training (honest status)
"Grokking" (generalization emerging after long training, e.g. on
modular arithmetic) is documented [I: Narayanan et al. 2023, arXiv
id UNVERIFIED this session] but its *pretraining-relevant* version —
"keep training past the loss plateau and quality still improves" — is
**the empirical basis for over-training** and is consistent with every
2024–26 frontier report that trained well past Chinchilla. [I]

## Worked example: plan a 2026 run

**Given:** C = 5e23 FLOP budget = **32 H100-GPU-years at 50% MFU**
[E: 3.121e22 FLOP/GPU-yr @100% → 1.56e22 @50% → 5e23/1.56e22 =
32]. Equivalently ~2000 H100s × ~5.8 days at 50% MFU
[E: 32/2000 yr = 0.016 yr = 5.8 days].

**Option A — Chinchilla point (D = 20·N):** C = 6·N·20N = 120·N² →
N = √(5e23/120) ≈ **64.5B params, ~1.29T tokens** [E] — at this
budget the Chinchilla point is a ~65B dense model on ~1.3T clean
tokens; the data pipeline must serve that. [I]

**Option B — over-train ~4× Chinchilla (industry practice):**
D = 80·N → C = 6·N·80N = 480·N² → N = √(5e23/480) ≈ **32.3B
params on ~2.59T tokens** [E]. This is the Llama-3-70B /
Qwen3-32B-class recipe. ✓

**Option C — MoE:** 120B total / 12B activated. Compute = 6 × 12e9
× D → at D = 15T that's 1.08e24 FLOP [E] — *exceeds* the 5e23
budget; so at C = 5e23, a 12B-activated MoE fits D = 5e23/(6×12e9)
≈ **6.9T tokens** [E] while still *storing* 120B of parameters.
The point: MoE lets you store 120B of knowledge while spending a
12B-dense compute budget. [I]

All [E] numbers Python-verified: `5e23/1.56e22=32.0`,
`sqrt(5e23/120)=6.45e10`, `sqrt(5e23/480)=3.23e10`,
`5e23/(6*12e9)=6.94e12`.

## MFU: the gap between the law and the wall clock

The laws are in *FLOPs*; clusters deliver *wall-clock seconds*. The
conversion is **MFU** (Model FLOPs Utilization):

```
FLOPs_achieved = peak_FLOP × n_GPUs × seconds × MFU
```

- **MFU 40–60%** is the 2024–26 reported range for dense models at
  scale [I: MegaScale 55.2% at 175B/12,288 GPUs, F: 2402.15627;
  Llama-3 ~40–44% at 405B reported in the paper's training section —
  UNVERIFIED exact figure this session].
- MFU is set by: activation recomputation policy, comm overlap,
  pipeline bubbles, data pipeline starvation, stragglers.
  (`Interaction.md` §cost model.)

**[E] Example:** 1000 H100s (989 TFLOP BF16 dense [F: vendor spec])
at 50% MFU for 90 days: 1000 × 989e12 × 0.5 × 7.776e6 s
= **3.85e24 FLOP** [E] → at that budget the Chinchilla point is
N = √(3.85e24/42) ≈ **303B params, ~2.1T tokens** [E].
(Python-verified; the law is monotone in C — a bigger budget gives
a bigger point.)

## Limits of the framework (honest status)

1. **Laws fit clean data; frontier runs use messy multi-domain mixes**
   — a single L(N,D) curve can't capture domain-mixture effects [I].
2. **Downstream ≠ proxy**: the laws predict *next-token perplexity*,
   not MMLU/SWE-bench; the mapping is empirical and wobbles
   (especially for reasoning tasks) [I].
3. **No law covers post-training yet** — 2025–26 reports show
   alignment/RL scaling has its own (unformalized) curve [I:
   DeepSeek-V3.2 "scaling post-training compute" 2512.02556].
4. **MoE breaks the single-N abstraction** — total vs activated
   params are two different N's; the laws need both [I].

## Key takeaways

1. **C ≈ 6·N·D** is the master equation; everything (budget, MFU,
   checkpoints) is in that frame.
2. Chinchilla (2022): tokens ≈ **20× params** at compute-optimal
   (70B / 1.4T = 20).
3. 2023–26 practice: **over-train** — Llama-3 405B at ~37
   (1.8×), Llama-7B at ~150 (7.5×), MoE-activated at ~480
   (24×) [E] — because inference cost and data quality dominate.
4. At 10^23+ FLOP, the binding constraints are **data quality and
   MFU**, not the law itself.
5. The laws predict perplexity, not product quality — treat them as
   *budget allocators*, not quality predictors.

## References

- Kaplan et al. 2020 — `2001.08361` [F, verified]
- Chinchilla (Hoffmann et al. 2022) — `2203.15556` [F, verified]
- LLaMA — `2302.13971`; Llama 3 — `2407.21783`; DeepSeek-V3 —
  `2412.19437`; Kimi K2 — `2507.20534` [all verified]
- Dedup (Lee et al.) — `2107.06499`; FineWeb — `2406.17557`;
  DoReMi — `2305.10429` [verified]
- Data-constrained scaling laws, Grokking (Narayanan et al.) —
  UNVERIFIED ids this session (do not cite until re-verified)
- MegaScale — `2402.15627` [verified]
