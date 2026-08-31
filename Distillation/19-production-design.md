# 19 — Production Design: KD Pipelines, On-Policy Loops, Frameworks & Lineage
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
Taking distillation to production means two architectures (offline KD pipeline and the
on-policy loop), a framework landscape mapped honestly against what each actually
supports, distributed-training realities (teacher+student in one estate, logit
transfer, TP/PP/EP teachers), and model lineage as a governed artifact. This page is
the production blueprint that the technique pages (`06`–`13`) plug into.

## Production distillation architecture (offline pattern)

```
                    ┌─────────────────┐
Prompts ────────── ▶│ Teacher Cluster │
                    └────────┬────────┘
                             ▼
                   Synthetic Responses
                             ▼
                    ┌─────────────────┐
                    │ Quality Filter  │
                    └────────┬────────┘
                ┌────────────┼────────────┐
                ▼            ▼            ▼
            Verifier       Dedup        Safety screen
                └────────────┼────────────┘
                             ▼
                     Training Dataset
                             ▼
                    ┌─────────────────┐
                    │ Student Trainer │
                    └────────┬────────┘
                             ▼
                        Evaluation
                             ▼
                          Registry
                             ▼
                     vLLM / SGLang / TRT-LLM
```
Design notes [I]:
- **Teacher cluster** is burst-shaped (generate → idle); schedule it like a batch
  workload (`15` §online-vs-offline).
- **Quality gate is a pipeline, not a step** — verifier/dedup/safety run as stages with
  pass-rate metrics and quarantine buckets (`14`).
- **Registry** stores weights + lineage + eval reports; serving pulls only
  registry-blessed artifacts (`14` §lineage).

## On-policy production loop (OPD serving pattern)

```
Student generates trajectory
        ▼
Teacher / verifier feedback  (scoring service)
        ▼
Replay / training buffer
        ▼
Optimization (student trainer)
        ▼
Updated Student �─▶ (rolling deploy / shadow eval)
```

| Concern | Production answer |
|---|---|
| Cost | teacher is the run-rate driver — batch scoring, top-K payloads, replay re-use (`10`) |
| Synchronization | decouple via buffer: generation workers → queue → trainer; never lock-step [I] |
| Teacher availability | teacher as a service with SLO; fallback = verifier-only reward (degraded mode) |
| Stale feedback | version-tag teacher in the buffer; drop or re-score on teacher update |
| Distributed training | student trainer independent of rollout fleet; standard FSDP/DeepSpeed |
| Safety valve | rolling deploy + shadow eval before promotion (`Production-Operations` release practice) |

## Framework ecosystem (verify support before relying on it — do not assume)

| Framework | SFT/response KD | Logit KD | Online/on-policy (GKD) | Reasoning-distill fit | Notes |
|---|---|---|---|---|---|
| HF Transformers | ✅ | manual (custom loss) | — | ✅ data-side | the substrate |
| TRL | ✅ SFTTrainer | ⚠️ custom trainer | ✅ **GKDTrainer** | ✅ | first-party GKD [F: TRL docs] |
| Axolotl | ✅ | ❌ (as shipped) | ❌ | ✅ data-side | config-driven SFT |
| LLaMA-Factory | ✅ | ⚠️ partial/experimental | ⚠️ | ✅ data-side | broad model zoo |
| Unsloth | ✅ (LoRA-first) | ⚠️ | 🚧 | ✅ data-side | single-GPU speed |
| DeepSpeed | engine (any) | ✅ via custom losses | ✅ possible | engine | ZeRO for the student trainer |
| Megatron-LM | ✅ | ✅ (logit-distill tooling) | ⚠️ | ✅ | large-scale pretraining-grade |
| NVIDIA NeMo | ✅ | ✅ (KD features) | ⚠️ | ✅ | enterprise pipeline + distillation in NGC tooling [F: vendor docs — verify version] |
| OpenRLHF / verl | RL-first | ⚠️ | ✅ (RL-loop KD / teacher-reward patterns) | ✅ | on-policy home turf |
| vLLM/SGLang/TRT-LLM | — serving side — | — | — | — | teacher *serving* + student *deployment* |

Legend: ✅ shipped · ⚠️ partial/experimental — verify in your version · 🚧 in progress ·
❌ not as shipped. This table is the most *version-sensitive* artifact in the section;
treat it as a checklist to re-validate per release [I: table discipline].

## Distributed distillation training (the estate view)

```
GPU Group A: Teacher  (TP / PP / EP as its size demands)
        │      forward-only; burst-friendly
        │  logits(top-K) / text / scores
        ▼   NCCL (intra-group) + RDMA/ethernet (inter-group) or object storage
GPU Group B: Student trainer (FSDP/ZeRO, optimizer states)
```
- **Memory:** teacher needs inference-only footprint (no optimizer states);
  student trainer needs training footprint (`15` §memory).
- **Interconnect:** full-logit streaming needs NVLink-class paths; top-K/text fits
  Ethernet (`05`, `15`).
- **Pipeline design:** teacher as a *service* (HTTP/gRPC or NCCL-aware producer) keeps
  trainer code standard; avoids PP-coupling with the teacher's own pipeline
  (`15` §TP/PP/EP).

## Online vs offline teacher (production decision table)

| Factor | Offline teacher | Online teacher |
|---|---|---|
| Storage | large (logits) / small (text) | minimal |
| GPU cost | burst; then free | reserved whole run |
| Flexibility | frozen targets | any loss, any state |
| On-policy | no | required |
| Throughput | dataloader-bound | teacher-serving-bound |
| Reproducibility | dataset-pinned ✅ | config-pinned |

## Model lineage (the governed artifact)

Template (JSON-ish, store alongside weights in the registry):

```json
{
  "student": {"base": "<hf-id>", "size": "7B", "license": "<id>"},
  "teacher": {"model": "<name@version/hash>", "access": "open-weight|api",
              "output_use_permission": "<ToS/license citation, date checked>"},
  "prompt_dataset": {"source": "<id>", "size": 800000, "license": "<id>"},
  "generation": {"temp": 0.8, "top_p": 0.95, "n_samples": 4, "dates": "..."},
  "filtering": {"rules": ["verify-answer", "lang-consistency", "dedup"],
                "pass_rates": {"raw": 1.0, "verified": 0.61}},
  "training": {"code": "<repo@commit>", "framework": "<name@version>",
               "config": "<yaml>", "seeds": [1], "hardware": "<class>"},
  "evaluation": {"benchmarks": {...}, "harness": "<name@version>",
                 "generation_settings": {...}, "date": "2026-08-27"},
  "known_limitations": ["factual QA degraded", "EN-centric"]
}
```
[Consolidates `14` §lineage; mirrors `Production-Operations` release-artifact practice.]

## Failure-ready operations
- Wire the `14` failure-mode catalog into runbooks (each mitigation is a runbook action).
- Quality regression gates in CI: benchmark ladder + safety eval + calibration check
  (ECE) on every student release (`17`, `14`).
- Keep a teacher-outage mode: training continues offline from the buffer; generation
  queues drain later (OPD loop resilience [I]).

## Related
- `17-benchmarking.md` — the CI gates this page wires
- `14-data-generation-and-verification.md` — the quality gates and lineage content
- `10-on-policy-distillation.md` — the loop's algorithmic core
- `Production-Operations/README.md` — release, canary, and SRE practice around these pipelines
- `Serving-Engines/README.md` — the deployment endpoints (vLLM/SGLang/TRT-LLM)
- `Platform-Economics/33-ai-finops.md` — the cost governance view of teacher clusters

## Key Takeaways
- Two production shapes: the offline KD pipeline (burst teacher → gated dataset →
  train → registry) and the on-policy loop (buffered student rollouts → teacher
  scoring → optimize).
- Framework support for KD is uneven — TRL's `GKDTrainer` and the RL frameworks own
  on-policy; the SFT frameworks own response distillation; verify per version.
- Teacher as a service + replay buffer is the resilient production pattern.
- Lineage is not optional: permission basis, filters, and eval settings make a
  distilled model governable and reproducible.
