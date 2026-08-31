# 18 — Practical Labs: Home Lab, 2× DGX Spark, RTX PRO 6000, and the Hands-On Project
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
Four labs, one skill: build your own reasoning-distilled LLM end to end. Lab A uses a
home-lab GPU; Lab B designs for two DGX Sparks; Lab C targets an RTX PRO 6000
Blackwell-class machine; Lab D is the full iterative project (teacher → verified data →
student → eval → error mining → on-policy → quantize → serve). Every lab is runnable at
each scale's honest limits, and every [E] number was computed this session.

## What's practical on which hardware [A: capability classes, validate per model]

| Device class | Practical student SFT | Practical teacher duty | Notes |
|---|---|---|---|
| RTX 5090 (32 GB) | 7–14B LoRA/QLoRA; 7B full FT (tight) | 7–14B inference; 32B @NVFP4 inference | one-GPU home default |
| RTX 4090 (24 GB) | 7B LoRA/QLoRA | 7B inference; 14B @INT4 | same shape |
| RTX PRO 6000 Blackwell (96 GB) | 14–32B full FT; 32B+ LoRA | 32B BF16 inference; 70B @FP8/INT4 | the serious single-card |
| DGX Spark GB10 (128 GB unified) | 7–14B full FT; 32B LoRA (bandwidth-limited) | 32B BF16; 70B @FP8/INT4 inference | unified memory; two units change the math (Lab B) |
| Mac (64–128 GB unified) | 7–14B QLoRA (MLX ecosystem) | 14–32B inference | throughput-limited |
| Edge (Jetson-class) | — | ≤3B @INT4 inference | deployment only |

Memory ceilings from the [E] tables in `15` §memory: 7B BF16 = 13.0 GiB,
14B = 26.1 GiB, 32B = 59.6 GiB (weights only; add optimizer states ×3–4 for full FT
[F: AdamW fp32 states convention], ×~1.3 for LoRA).

## Lab A — Home-lab reasoning distillation (one RTX 5090/4090)

**Goal:** verified-reasoning distillation into a 7B student.

```
Teacher (remote: API or a bigger box)
   ↓ 1. collect 1–5K prompts (math GSM8K-style + code + general)
   ↓ 2. teacher × 4 samples/prompt, temp 0.7–1.0
   ↓ 3. verify: answer-match (math), unit tests (code)
   ↓ 4. select best trace/problem; clean (→ `14` checklist)
   ↓ 5. SFT student 7B (LoRA r=16–64 or full if 32 GB)
   ↓ 6. eval: MATH-500 subset, IFEval, base-vs-SFT-vs-distilled
```
- Teacher options ranked by convenience [A]: (a) remote box via vLLM OpenAI-compatible
  endpoint (`Serving-Engines/vLLM.md`), (b) API teacher (check ToS → `15`), (c) local
  32B @NVFP4 for a weaker-but-free teacher.
- Training stack [A: versions move — pin yours]: Axolotl or LLaMA-Factory or TRL SFTTrainer;
  Unsloth for single-GPU speed.
- Expected outcome [I]: GSM8K-class accuracy lift of several points over base at 7B with
  1–5K verified traces — enough to feel the mechanism, far from the R1-scale result.

## Lab B — Two-DGX-Spark distillation lab

128 GB unified memory each; limited cross-node bandwidth (10–25 GbE class [A]) —
design for data movement minimization.

**Experiment A — split roles:**
```
Spark-1: teacher serving (32B BF16, or 70B @FP8/INT4)
Spark-2: student SFT (7–14B)  ← data over Ethernet, once
```
The teacher pays its cost *once* per dataset (offline pattern, `15` §online-vs-offline).

**Experiment B — generate-then-train (offline):** teacher bursts a full dataset to
NVMe/object storage on Spark-1; Spark-2 trains from files while Spark-1 idles or
generates more. Cross-node bandwidth stops mattering; this is the pragmatic default.

**Experiment C — quantized teacher, dense student:** teacher = 70B @FP8/INT4 on
unified memory; student = 7B/14B dense.

**The lab's real question:** online teacher + student training vs offline dataset?
At Spark-class interconnects, **offline wins on throughput** [I: bandwidth argument in
`15` §distributed logit transfer]; online only wins if you need on-policy scoring
(then use top-K/text payloads and a replay buffer, `10`/`19`).

## Lab C — RTX PRO 6000 / Blackwell single-card lab

96 GB changes the choices:
- **BF16 full FT** up to 14B; 32B full FT is possible with activation checkpointing +
  FSDP-over-CPU-RAM [A]; 32B LoRA comfortable.
- **FP8 training** (Blackwell FP8 tensor cores) doubles effective throughput where
  supported [A: framework support varies — verify your stack].
- **LoRA/QLoRA response distillation:** 32B students at QLoRA — practical, cheap.
- Honest note: **LoRA-based response distillation is not full classical KD** — no logit
  matching, adapter capacity only — but as an implementation of verified-trace transfer
  it is extremely effective per dollar [I: consistent with `06` framing].
- Measure: tokens/s at each precision; acceptance of FP8 vs BF16 quality on MATH-500.

## Lab D — Build your own reasoning-distilled LLM (the full project)

```
Teacher → Prompt corpus → Synthetic reasoning generation → Verification
   → Cleaning → Train/val/test split → Student SFT → Evaluation
   → Error analysis → Iterative distillation → Quantization → Serving
   → Benchmarking
```
Reproducibility contract [A: house style]: config-driven (YAML), seeds pinned,
data lineage recorded (`14` §lineage), every table in the final report regenerable
from one command.

## Student error mining (the loop that makes it iterative)

```
Student benchmark failures
        ↓
cluster failure modes (domain, length, tool, format)
        ↓
generate targeted teacher data for weak clusters
        ↓
retrain → re-evaluate → repeat
```
This turns distillation from a one-shot recipe into a control loop [I]; it is also the
cheapest quality lever after verification (`07`).

## Curriculum distillation (optional stage)
Order the training mix easy → hard (by verifier-measured difficulty). Expected effect:
stability, not miracles [Research Result: `07` §curriculum].

## Active distillation (optional stage)
Route only high-uncertainty prompts to the teacher (self-consistency disagreement or
verifier failure as the trigger). Teacher spend drops for the same student quality
[I: `07` §active]. This is the lab-scale version of `19` §OPD routing.

## Iterative improvement plan (map to Lab D stages)

| Phase | Addition | Expected delta |
|---|---|---|
| 1 | Response distillation | the base lift |
| 2 | Verified reasoning distillation | quality + robustness |
| 3 | Best-of-N teacher data | +1–3 points typical [I] |
| 4 | Student error mining | targets the tail |
| 5 | On-policy KD (GKD/OPD) | fixes drift/long-horizon (`10`) |
| 6 | Quantized deployment | cost cut, small quality check |

## Related
- `17-benchmarking.md` — the measurement discipline these labs feed
- `06/07` — the recipes the labs implement
- `19-production-design.md` — the framework matrix (TRL/Axolotl/LLaMA-Factory/Unsloth)
- `Labs/` — the wiki's 12 general labs (prefix caching, roofline, etc.)
- `Open-Source-Models/README.md` — teacher/student checkpoints to use

## Key Takeaways
- Any 24–32 GB GPU can run a real distillation loop at 7B in a weekend.
- Two Sparks → offline dataset generation beats online co-training at that interconnect.
- LoRA response distillation is "not classical KD" and still the right 80/20 tool.
- Error mining + iteration is what turns a lab into capability.
