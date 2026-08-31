# 15 — Systems & Infrastructure: Memory, Distributed KD, Teacher Topologies, API vs Open-Weight
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
Distillation changes infrastructure twice: during training (teacher serving, student
training, sometimes both at once with logit firehoses between them) and after (the
whole point — much smaller inference). This page quantifies the inference win with
machine-checked memory tables, then engineers the training side: online vs offline
teachers, distributed logit transfer, teacher-side TP/PP/EP, API vs open-weight
teachers, and enterprise/sovereign deployment patterns.

## Inference impact: what changes when you deploy the student

Measure before/after on your traffic; the shape of the win (all [E], computed this
session from the parameter table below):

| Metric | What distillation changes | Where the number comes from |
|---|---|---|
| Parameters | 671B → 7B = **96× fewer** [E] | compression ratio, `17` |
| Weight memory | 1,250 GiB → 13.0 GiB BF16 [E] | table below |
| Model load time | ≈ linear in weight bytes | PCIe/NVMe bandwidth-bound [I] |
| TTFT | prefill ≈ params-proportional at fixed hw | roofline: `Inference/Roofline.md` |
| TPOT / tok/s | decode is weight-bandwidth-bound → ~96× fewer bytes | roofline |
| requests/s per GPU | capacity × (memory freed) — KV + weights both shrink | `KV-Cache/README.md` |
| power / J per token | fewer weight reads per token | decode-bandwidth argument |
| $/1M tokens | the product of all the above | `17` §break-even |

## Weight-memory tables ([E] — weights only; add KV-cache + workspace separately)

| Params | BF16 (2 B) | FP8/INT8 (1 B) | NVFP4/INT4 (0.5 B) |
|---|---|---|---|
| 1.5B | 2.8 GiB | 1.4 GiB | 0.7 GiB |
| 7B | 13.0 GiB | 6.5 GiB | 3.3 GiB |
| 8B | 14.9 GiB | 7.5 GiB | 3.7 GiB |
| 14B | 26.1 GiB | 13.0 GiB | 6.5 GiB |
| 32B | 59.6 GiB | 29.8 GiB | 14.9 GiB |
| 70B | 130.4 GiB | 65.2 GiB | 32.6 GiB |
| 671B | 1,249.8 GiB | 624.9 GiB | 312.5 GiB |

**Do not confuse the three memory pools** [I: recurring ops error]:
1. **Weights** — the table above.
2. **KV cache** — per-token, per-layer, grows with context and batch: canonical
   constants in `KV-Cache/README.md` (8B-GQA ≈ 128 KiB/token; 70B-class ≈ 320 KiB/token
   [E: wiki constants bank]).
3. **Runtime workspace** — activations, CUDA graphs, fragmentation; engine-dependent
   headroom (GBs at 7B-class, more with long context).

A "7B fits an 8 GB card @INT4" claim (3.3 GiB weights) still needs room for KV +
workspace; a "fits" claim without the KV math is marketing [I].

## GPU deployment-topology impact

```
70B BF16  → 2–4× 24 GB / 2× 48 GB GPUs (TP)  … or 1× 48 GB @INT4
671B MoE  → multi-node; EP + all-to-all      (→ GPU-Systems/MoE-Expert-Parallelism.md)
32B dense → 1× workstation (48–64 GB) or 2× 24 GB @TP
7B dense  → 1× consumer GPU (even @BF16 on 24 GB)
1.5B      → laptop / edge
```

Distillation is the *only* compression axis that changes the topology class this way —
quantization shaves the same model; distillation gives you a different model with a
different topology (→ `16`).

## Distributed distillation training (teacher + student live)

```
GPU Group A                      GPU Group B
  Teacher (TP/PP/EP as needed)     Student trainer
        │                               ▲
        └── logits / top-K / text �──────┘
             (NCCL / RDMA / storage)
```

Requirements [I: engineering analysis]:
- **Interconnect:** full-logit transfer is brutal (§logit transfer below); top-K or
  text payloads fit on ordinary networks.
- **NCCL groups:** keep teacher-TP collectives and student collectives in separate
  communicator groups to avoid interleaving stalls (`GPU-Systems/NCCL.md`).
- **Storage:** precomputed logits → multi-TB object storage (see `05` §storage math);
  text datasets are trivial.
- **Scheduling:** teacher passes are forward-only (no optimizer state) — they can
  time-share GPUs with student training in low-memory regimes at a throughput cost.

## Online vs offline teacher

| | Offline (precompute) | Online (live) |
|---|---|---|
| What | teacher outputs/logits stored, then training | teacher serves during training |
| Storage | large for logits; small for text | none |
| GPU cost | one-time teacher burst | teacher GPUs reserved for the whole run |
| Flexibility | frozen responses (no re-scoring) | any loss on any state; on-policy possible |
| On-policy KD | impossible | required |
| Throughput | dataloader-bound | teacher-forward-bound; needs high-BW serving |
| Reproducibility | dataset-pinned | pinned by config (harder) |

Decision rule [I]: response/reasoning distillation → offline; anything GKD/OPD-shaped →
online with a replay buffer to amortize (→ `19`).

## Distributed logit transfer (the bandwidth wall)

Teacher GPU → student GPU, full distribution per position:

```
150K vocab × 2 B (FP16) = 0.29 MiB / token [E]
   × 4K context  = 1.14 GiB / sequence [E]
   × batch 32    = 36.6 GiB / step-per-link [E]
```
At 400 GbE (≈50 GB/s effective, wiki constants) that single step-link needs ~0.8 s
[E] — logit KD at scale forces one of: **top-K payloads** (~375–500× cut, `05`),
**quantized logits** (FP8: 2× cut), **colocation** (NVLink: 900 GB/s → 0.5 ms for the
canonical 32 MB pattern [F: house NCCL page]), or **pipeline overlap**
(prefetch next batch's logits during current step).

## When the teacher itself is distributed (TP/PP/EP)

Large teachers need serving-side parallelism before distillation even starts:
- **TP:** teacher forward per micro-batch; TP degree raises its AllReduce traffic per
  step (`GPU-Systems/Tensor-Parallelism.md`) — schedule teacher passes in waves.
- **PP:** teacher pipeline bubbles interact badly with student-step sync
  [I: keep teacher as a service, not a pipeline peer].
- **EP (MoE teachers):** expert all-to-all dominates; run teacher generation in
  large-batch bursts (amortize all-to-all), store results, train offline
  (this is exactly R1's shape: generate 800K samples, then SFT [F: arXiv:2501.12948]).

## Distilling from API models (black-box) — legal first

Technically trivial (prompt → response → SFT, → `06`). Legally/contractually **verify
before designing the pipeline**:

- **ToS output-use terms:** providers differ on whether outputs may train competing
  models; some prohibit it explicitly, some permit with conditions, terms change over
  time — this section deliberately does not name current terms; check the provider's
  current agreement [A: deliberate non-assertion].
- **Model license vs service terms:** open-weight *teachers* carry their own license
  (e.g. community licenses with use restrictions) — the teacher's license governs
  weights; the *service* terms govern API outputs; both may apply.
- **Practical pattern:** record permission basis in the model card (→ `14` §lineage).

## Open-weight teacher distillation

| Dimension | Open-weight teacher | API teacher |
|---|---|---|
| Logits/features | yes (white-box possible) | rare (some expose top logprobs) |
| Reproducibility | checkpoint-pinned | service-version-dependent |
| Privacy/data governance | data never leaves your perimeter | data leaves; compliance question |
| Cost at scale | your GPUs (amortized) | per-token, linear |
| Deployment | host it (TP/PP/EP as needed) | none |
| Licensing | read the license (use restrictions exist) | ToS |

Local hosting also unlocks: temperature sweeps, hidden-state access, seeded sampling,
custom scoring — the white-box toolbox (→ `05`).

## Enterprise & sovereign patterns

**Enterprise domain student:**
```
General teacher (open or API)
   + enterprise knowledge (docs, tickets, domain corpora)
   + verified domain data (SME-reviewed traces)
   ↓
Domain student (7–32B) → on-prem serving (vLLM/SGLang/TRT-LLM)
```
Telecom/finance/healthcare/legal/cyber variants differ by verification method and
compliance surface, not by the distillation mechanics (→ `07`, `13`).

**Sovereign / disconnected AI:**
```
Frontier teacher (run once, on your terms)
   ↓ secure distillation pipeline (air-gapped data, lineage `14`)
Smaller domain model
   ↓ private GPU cloud — no external inference dependency
```
Distillation's unique property for sovereign use: capability, once transferred into
weights, no longer requires the teacher, the API, or the network [I]. Cost model →
`17` §break-even; platform governance → `Platform-Economics/24-data-governance.md`.

## Related
- `17-benchmarking.md` — the cost/break-even model this page's hardware facts feed
- `16-distillation-vs-compression.md` — the quantized-student stack
- `KV-Cache/README.md` — the KV pool that completes the memory picture
- `GPU-Systems/MoE-Expert-Parallelism.md` — serving MoE teachers
- `Distributed-Inference/Overview.md` — cluster platform view of teacher serving
- `Platform-Economics/29-local-vs-api-economics.md` — the buy-vs-host analog

## Key Takeaways
- The inference win is structural: 96× fewer weight bytes at 671B→7B changes
  topology class, not just latency [E].
- Memory claims need three pools: weights + KV + workspace; the tables here are
  weights only [E].
- Logit KD at scale is a bandwidth problem: top-K, quantization, or colocation — pick one.
- Offline teacher for response/reasoning KD; online teacher for on-policy methods;
  MoE teachers want burst-then-store.
- Legal basis (ToS/model license) is a design input, not an afterthought; open-weight
  teachers are the sovereign default.
