# 05 — Logit, Top-K, Feature and Attention Distillation (+ Storage Math, Cross-Tokenizer, MoE→Dense)
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
When you can open the teacher, the richest signals are its *internal numbers*: the
next-token distribution at every position (logits), the hidden states flowing through
its layers, and its attention patterns. Logit KD trains the student to reproduce the
teacher's full distribution — much denser supervision than final text — but 150K-token
vocabularies make naive storage and transfer impractical, hence top-K compression.
Feature/attention KD transfers intermediate geometry instead. This page carries all the
white-box machinery plus the systems problems: storage, cross-tokenizer alignment, and
MoE→dense distillation.

## Logit distillation

```
Teacher ─▶ vocabulary distribution (150K+ entries/position)
                        │
                        ▼  KL at every position
Student ─▶ matching distribution
```

Why logits beat text: a sampled token is one draw; the distribution is the teacher's
*entire belief state* — every plausible continuation with its weight. It is "dark
knowledge" at token scale (→ `02`). Training signal per example is O(V) instead of O(1),
which is why logit KD typically needs far fewer sequences for similar quality — and
far more infrastructure.

The loss is the KL family from `03`, usually with temperature T (often T=1 for LLMs —
the vocabulary is already huge and flat relative to 1000-class ImageNet [I]), plus the
standard CE term on true tokens to anchor the student to ground truth:

```
L = CE(y_true, student) + α · KL( softmax(z_T /T) ∥ softmax(z_S /T) )
```

## The storage problem (the numbers that kill naive logit KD)

Every position of every stored sequence needs a full vocabulary distribution:

- Vocabulary V = 150,000; sequence length S = 4,096; N = 1M training sequences.
- **[E]** Full logits per token @FP32 = 150,000 × 4 B = **0.57 MiB** (@FP16: 0.29 MiB).
- **[E]** One 4K sequence @FP16 = 0.29 MiB × 4,096 ≈ **1.14 GiB**.
- **[E]** 1M such sequences ≈ **1.14 PiB-equivalent** (1,144,000 GiB ≈ 1,117 TiB) —
  clearly impractical to store, let alone stream through a training dataloader.

(Computed with the storage block in `15-systems-and-infrastructure.md`; same numbers
there. Bandwidth story is identical — see §distributed logit transfer.)

## Top-K logit distillation

Keep only the teacher's K largest probabilities per position:

```
top-K entry = (token_id: 4 B, prob: 2–4 B) → 6–8 B/token for K entries
```

| K | Per-token payload [E] | 4K-seq payload [E] | 1M seqs [E] | Notes |
|---|---|---|---|---|
| 10 | 60–80 B | ~0.23–0.31 MiB | ~230–305 GiB | sharp modes only |
| 50 | 300–400 B | ~1.2–1.6 MiB | ~1.2–1.6 TiB | common default region |
| 100 | 600–800 B | ~2.3–3.1 MiB | ~2.3–3.1 TiB | ~99%+ of mass on typical LLM dists [I] |
| 1000 | 6–8 KiB | ~23–31 MiB | ~23–31 TiB | diminishing returns |

Reconstruction: train KL only over the top-K support plus the true token, or renormalize
with a smoothed tail [Research Result: the "FKD / streaming KD" line (arXiv:2306.08543
era) and DistiLLM's storage-friendly formulation, arXiv:2402.03898]. Compression vs full
FP16 @K=100: ≈ **375–500×** [E].

## Feature / hidden-state distillation

Match intermediate representations, not just outputs:

```
Teacher layer 12   →  projection  →  ↘
Teacher layer 24   →  projection  →  ✕  MSE/cosine  →  student update
Teacher layer 36   →  projection  →  ↘          ↑
                                              matches
Student layer 4    Student layer 8    Student layer 12
```

- **Layer mapping:** teacher and student depths differ; choose correspondences
  (uniform, last-K, or learned). Patient KD showed *repeatedly* matching a small set of
  intermediate layers + the final layer beats final-only for BERT students
  [F: arXiv:1908.09355].
- **Projection layers:** dimensions differ (e.g. d=4096 teacher vs 2048 student) — insert
  trainable linear projections (then discard). MiniLM matched the teacher's last
  transformer layer hidden states via such projections [F: arXiv:2002.10957].
- **Dimensionality mismatch and width differences** make cross-width KD work but
  cross-*architecture* KD is best-effort: what survives is "representational shape,"
  not exact features [I].
- Attention distillation (TinyBERT's second loss: match attention matrices layer-by-layer
  [F: arXiv:1909.10351]) mattered in the BERT era because attention structure was the
  cheapest "how the model thinks" signal available; modern LLM practice mostly prefers
  logits + hidden states, with attention-KD as a niche [I: synthesis].

## Cross-architecture distillation

Teacher MoE-Transformer → student dense-Transformer (or 70B → 7B across families):

- **Survives the jump:** input→output behavior (text mapping), reasoning patterns in
  traces, task-level skills.
- **Does not survive exactly:** expert routing (no student equivalent), exact feature
  geometry, calibration details (→ `14` §calibration).
- MoE→dense is the flagship 2026 case (→ §MoE→dense below).

## Cross-tokenizer distillation

Teacher tokenizer ≠ student tokenizer is a real systems boundary:

- **Logit KD breaks:** teacher token i ≠ student token i; distributions are over
  different vocabularies with different segmentations of the *same text*. Workarounds
  (rarely worth it [I]): train on the intersection of vocabularies via aligned tokenizers;
  probabilistic alignment via unigram segmentation; or distill through a shared
  intermediate (English/semantics).
- **Feature KD breaks similarly** — activations are per-teacher-token.
- **Response/sequence KD is immune:** text is text. This is a major reason
  response-based distillation dominates cross-family practice (R1-Distill spans Qwen and
  Llama students from one teacher [F: arXiv:2501.12948]).
- Same-family (Qwen→Qwen) keeps tokenizers aligned and makes white-box KD directly
  applicable.

## MoE → dense distillation

The DeepSeek-style flagship: 671B-total MoE (~37B activated per token) → 32B dense
student:

| Dimension | 671B MoE teacher | 32B dense student |
|---|---|---|
| Total params | 671B | 32B [E: 21× smaller] |
| Active params/token | ~37B | 32B |
| Weight memory BF16 | ~1,250 GiB (≈1.22 TiB) [E] | ~59.6 GiB [E] |
| Serving topology | multi-node; expert parallelism + all-to-all | single workstation (2×H100/4×A2-class) |
| Communication | expert-parallel all-to-all per layer | standard TP only |
| Latency profile | batch-sensitive (all-to-all) | predictable |
| Ops complexity | high (EP, expert balancing, fault domains) | low |

Why distillation can *eliminate* MoE serving complexity: the student never inherits
routing; it learns the *function* the routed ensemble computed. You pay in peak
capability on the long tail (capacity gap, `01`) and in losing the MoE's per-token
parameter efficiency — but gain single-node deployment, standard kernels, and
predictable latency. → `16-distillation-vs-compression.md` for the quantized version of
this comparison.

## Distributed logit transfer (preview)

When teacher and student train on different GPUs, the "dataset" is a firehose:
150K-dim distributions per position per step. Options: top-K sparse payloads (~6–8 B/
token @K=100 [E]), FP8/INT8-quantized logits, or colocating teacher and student in one
job to skip the network. Full treatment → `15-systems-and-infrastructure.md`.

## Related
- `03-distillation-losses.md` — the divergence math this page plugs into
- `04-distillation-taxonomy.md` — where white-box KD sits in the master map
- `15-systems-and-infrastructure.md` — GPU topologies, bandwidth, online-vs-offline teacher
- `Model-Architectures/Mixture-of-Experts.md` — how MoE teachers are built and served
- `Model-Architectures/Attention-Head-Designs.md` — GQA/MQA students vs MHA teachers
- `KV-Cache/README.md` — the serving-side memory that shrinks with the student

## Key Takeaways
- Logit KD is the densest practical signal — O(V) supervision per position — and
  immediately hits storage/bandwidth walls; top-K (50–100) is the standard compromise
  (~375–500× vs full FP16 [E]).
- Feature/attention KD transfers internal geometry; patient multi-layer matching beats
  final-only; attention matching is mostly a BERT-era tool.
- Cross-tokenizer reality: text-level distillation is the only portable KD across model
  families.
- MoE→dense distillation is a deployment-topology weapon: trade expert-parallel
  multi-node serving for a single-workstation dense student.
