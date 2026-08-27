# LLM Systems Wiki — A Living Encyclopedia of Large Language Models

> **Status:** LIVING · **LAST_UPDATED:** 2026-08-26 · **SOURCE_DATE:** 2026-08-16 · **RESEARCH_STATUS:** initial build complete; current-coverage sections verified against live sources on 2026-08-16
>
> How it reads: `MATH → TRANSFORMERS → TRAINING → POST-TRAINING → REASONING → INFERENCE → OPTIMIZATION → DISTRIBUTED SYSTEMS → AGENTS → HARNESS ENGINEERING → CURRENT RESEARCH`

---

## What's new
- **2026-08-26 — `Distributed-Inference/Implementation/` PART 2 (Distributed Inference Infrastructure: NVIDIA Dynamo + llm-d + NIXL, 7 files):** part 2 of the Disaggregated-Inference + Distributed-Infrastructure series, building on the PART-1 `KV-Cache/` conceptual areas. Six implementation pages + landing explain **how** the five cluster jobs (route/place/move/scale/fail) are concretely built, mapped 1:1 to the PART-1 concepts (no re-derivation, heavily cross-linked): `01-distributed-kv.md` (paged blocks + `(tier,node,rank)` placement; steady-state demand `λ·KV·(1−h)`; [E] 1000 req/s / 4 GiB / h=0.8 → ~859 GB/s — 17× one 400 GbE link; tier session capacity HBM ~2 vs CPU ~16 vs NVMe hundreds) · `02-offload-and-tiering.md` (tier-migration control loop; Dynamo KVBM ✅TRT-LLM/✅vLLM/🚧SGLang vs llm-d tiered prefix cache + index) · `03-kv-aware-routing.md` (Dynamo global radix-tree registry + `--no-router-kv-events` prediction mode vs llm-d Proxy+EPP + event-driven index + online XGBoost predictor; hit-*fraction*-not-binary scoring with (1−h) tables) · `04-pd-orchestration.md` (the four-step P/D loop; Dynamo pools+Planner/AIConfigurator vs llm-d Variants+HPA/KEDA/WVA) · `05-global-kv-state.md` (the substrate: router-owned radix registry vs event-driven index; eventual-consistency/staleness) · `06-nixl-transfer.md` (NIXL user-shape buffer-list flow, one-sided WRITE, plugins; **ROCm/vendor-neutral build note verified this session against NIXL main README — a forward drift from the 08-25 GPU-Communication pages**). Only the objective per-concept pages were created; Dynamo/llm-d capability pages (`NVIDIA-Dynamo.md`/`llm-d.md`/`Dynamo-vs-llm-d.md`/`Overview.md`/section README) deepened with PART-2 cross-links. All [E] computed this session reusing the canonical 128 KiB/token + 4 GiB@32k constants (no drift).
- **2026-08-26 — `KV-Cache/` extended into the Caching Architecture knowledge area (PART 1: Disaggregated Inference + LLM Cache; 5 new deep-dive pages + section landing):** the KV cache as a unified *distributed, tiered, shared, paged memory object*. New `KV-Cache/README.md` (knowledge-area map: allocate → share → move → tier → trim → compress → route, plus the memory equation and KV-quantization) · `Architecture-Overview.md` (the unified model + the two-pillar framing: the caching stack ↔ disaggregated inference, meeting at the **KV transfer**; decision map, cross-cutting failure modes) · `Paged-KV-Cache.md` (PagedAttention SOSP'23: block pools/tables, ~60–80%→~4% waste, the three fragmentation kinds, block-size 16-vs-64 trade-off, block-level sparsity, paged-aware kernels) · `Prompt-and-Prefix-Caching.md` (the reuse stack: hash-APC vs RadixAttention vs LCP; the prompt/prefix/KV/prompt-caching terminology; hit *fraction* not binary; stable-prefix ordering; LMCache / connectors; measured 8.7× Lab-13) · `Distributed-KV-Cache.md` (sharded vs disaggregated vs replicated KV; transfer physics [E]: 4 GiB @32k = 4.8 ms NVLink / ~89 ms 100GbE; Mooncake / Dynamo / llm-d; consistency) · `Hierarchical-Offloading.md` (tiered HBM→DRAM→NVMe→remote budget [E] incl. 16 GiB moves: ~19 ms NVLink / ~191 ms DRAM / ~2.45 s Gen4; offload+prefetch, OasisKV/FlexGen; Mooncake context pool, Dynamo KVBM, llm-d 13.9×, SGLang/vLLM connectors). **Deliberately non-duplicating:** disaggregated inference, prefill/decode, KV-aware routing and their economics stay in `Inference/`, `GPU-Systems/`, `Distributed-Inference/`, `Production-Serving/` and are cross-linked, not re-derived. All [E] numbers machine-verified this session (128 KiB/token, 1/4/16 GiB @ 8k/32k/128k, 320 KiB/token 70B, transfer tables).
- **2026-08-25 — `AI-Factory-Networking/` section (55 pages):** AI Networking: From RDMA Fundamentals to InfiniBand, RoCE, Ultra Ethernet and Gigascale AI Fabrics — the complete network stack that connects GPUs for training, fine-tuning, distributed inference and AI factories. The 80/20 zero-to-hero arc: why AI networking is different (JCT physics, east-west elephant flows, tail latency) → the five-network taxonomy (scale-up NVLink/NVSwitch/UALink, scale-out, management, storage, DCI) → RDMA fundamentals (verbs, PD/MR/QP/CQ lifecycle) → operations and transports (SEND/RECV, RDMA WRITE/READ, one-sided vs two-sided; RC/UC/UD/DC) → InfiniBand zero to hero (architecture, SDR→XDR speed generations, addressing, QP state machines, packet format, credit flow control, VL/SL, Subnet Manager, routing/topologies/partitions, adaptive routing, SHARP, GPUDirect RDMA + NCCL over IB) → RoCE deep dive (RoCEv1/v2 packet anatomy, why losslessness must be engineered, PFC/ECN/DCQCN, CC landscape DCQCN/TIMELY/HPCC/Swift, lossless fabric reference design) → the vendor fabric landscape (NVIDIA Spectrum-X, Arista Etherlink, Cisco, Juniper, Broadcom merchant silicon, cloud fabrics) → Ultra Ethernet/UET (consortium, 1.0→1.0.3 spec timeline, UET transport PDCs/RUD/ROD/RUDI, NSCC/RCCC congestion control, in-network collectives, LLR) → workload-aware networking (collectives, MoE all-to-all, training vs inference, disaggregated serving) → the ops layer (NIC/SuperNIC, rail-optimized & multi-plane, buffers, telemetry, physical layer, Clos math, bandwidth calculations, benchmarking) → troubleshooting (RDMA/IB, RoCE/NCCL symptom tables) → security/tenancy, Kubernetes/Slurm, design decision tree, myths, complete packet journeys, three reference architectures, 16 hands-on labs, 100 interview/design questions, and a one-page cheat sheet. All [E] numbers from a machine-verified constants bank (2026-08-25); vendor claims tagged and dated; UET facts sourced to spec 1.0.3 (Jul 16, 2026). Start at `AI-Factory...
- **2026-08-25 — `GPU-Communication/` section (21 pages):** GPU Communication & Data Movement for Distributed LLM Systems — the three-branch taxonomy (Collectives / Point-to-Point / Memory-Data Movement + Expert Parallel), NCCL deep dive (2.31.2: GIN/GDA, CFT, NVLS, SHARP, NCCL EP), NIXL deep dive (v1.4.0: agent + 12 backend plugins, KV-cache transfer physics), UCCL deep dive (UC Berkeley/Davis, OSDI'26: UCCL-Tran/P2P/EP, NIXL backend, llm-d v0.5), the adjacent libraries (UCX/RCCL/UCC/NVSHMEM/DeepEP/MSCCL++/MPI/libfabric/GDS), training vs inference vs MoE communication, the engine-by-engine comm map (vLLM/SGLang/TRT-LLM/Dynamo/llm-d, verified 2026-08-25), the NCCL-vs-NIXL-vs-UCCL matrix, benchmarking (IB/RoCE/EFA + multi-rail + overlap), troubleshooting (2.31.2 env-var toolkit + decision tree), the architecture decision guide, hands-on labs (nccl-tests/NIXLBench/UCCL), and a provenance audit of the seed spec (17 CONFIRMED / 2 CORRECTED). Start at `GPU-Communication/README.md`.
- **2026-08-24 — Inference-Engineering extension: 8 new pages across `Serving-Engines/` + `Distributed-Inference/`:** the layer-stack mental model (`Serving-Engines/Engine-Landscape.md` — engines vs packaging vs distributed platforms), two new engine deep dives (`Llama-CPP.md` — GGUF/GGML, backend matrix, layer placement, quantization; `NVIDIA-NIM.md` — NIM LLM 2.x packaging layer: nim-llm + nimlib + vLLM, verified against docs.nvidia.com 2026-08-24), the seven-way matrix + decision guide (`Engine-Mega-Comparison.md`), and the cluster-platform layer (`Distributed-Inference/Overview.md` — the five cluster jobs, KV-transfer physics, P/D break-even; `NVIDIA-Dynamo.md` — v1.4.x, Rust frontend/router/planner, KVBM, NIXL; `llm-d.md` — CNCF v0.8/v0.9, K8s-native Router Proxy+EPP, InferencePool/Variant, KV indexer/offloader, XGBoost latency predictor; `Dynamo-vs-llm-d.md` — verified head-to-head across 25 dimensions). All [E] arithmetic machine-verified; arXiv IDs re-verified live (DistServe `2401.09670`, DeepSeek-R1 `2501.12948`); independent evaluator pass with per-flag adjudication.
- **2026-08-24 — `Platform-Economics/` section (57 pages + 15 labs + simulators):** Multi-Tenant LLM Platform Economics & Governance — turning expensive shared AI infrastructure into a fair, secure, measurable, sustainable platform. Unit economics (GPU-hour→token→request→tenant), CAPEX/OPEX, utilization & queueing economics, token/prefill-vs-decode/KV-cache/batching economics, model & routing economics, the quality/cost/latency frontier, tenant metering, showback→chargeback maturity, pricing models, service tiers, SLO economics, fairness & the noisy-neighbor problem, quotas, admission control, budget-aware routing, tenant isolation, data/model/policy governance, cloud bursting, local-vs-API break-even, capacity planning & forecasting, FinOps, waste detection, agent/evaluator/RAG/long-context/multimodal economics, goodput, energy, failure cost, GPUaaS & Kubernetes tenancy, a reference architecture, an economic simulator, cases, an 80/20 guide, a 0→10 zero-to-hero path, formulas, anti-patterns, and open questions. Start at `Platform-Economics/README.md`.
- **2026-08-23 — `Production-Operations/` section (41 pages + 12 labs):** LLM Reliability, SRE & Production Operations Engineering — what reliability means for LLMs, SLI/SLO/SLA, goodput as a first-class metric, the four golden signals extended for LLMs, latency engineering, error budgets (incl. a quality error budget), capacity planning, queueing 80/20, a full failure taxonomy, GPU failure engineering (Xid/ECC/DCGM, verified against NVIDIA docs), distributed inference failures, KV-cache reliability, overload/admission control, retries/circuit breakers, fallback engineering, routing failure modes, autoscaling, Kubernetes, health-check design, observability stack, dashboards, alerting, tracing, quality observability, release engineering, shadow/canary/regression testing, chaos engineering, incident management, runbooks, postmortems, cost as an SRE signal, agent SRE, RAG SRE, multi-region, disaster recovery, a reliability reference architecture, a 10-point 80/20 guide, a 0→10 Zero-to-Hero path, and a capstone mental model; plus 12 safe hands-on labs. Drafted by the DeepSeek V4 Flash main model; reviewed in the Qwen3.8 27B reviewer role (see final report). Start at `Production-Operations/README.md`.
- **2026-08-22 — `Inference/Production-Serving/` section (16 pages):** production LLM serving, routing & scheduling as a zero-to-hero + 80/20 handbook — the L0–L3 scheduling hierarchy, "balance remaining work, not requests", the ERW equation, queueing-theory 80/20, router architectures, cache-aware and P/D-disaggregated routing, admission control, autoscaling, observability/SLOs, multi-tenancy, a production-router comparison matrix, failure-mode catalog, and 10 labs on the home-lab stack. Start at `Inference/Production-Serving/01-production-serving-overview.md`.
- **2026-08-21 — `GPU-Systems/` section (12 pages):** a zero-to-hero GPU/CUDA/kernel engineering handbook for LLM inference — GPU architecture, bandwidth-vs-compute reasoning, CUDA from zero, GEMMs, the kernel stack, inference-engine internals, multi-GPU execution, prefill/decode disaggregation, cross-layer optimization, load balancing, and a perf-experiment template. Start at `GPU-Systems/README.md`.
- **2026-08-20 — `Training-Engineering/` section (7 pages):** training at scale as a first-class discipline — model anatomy, pretraining recipe, scaling laws, 5-axis parallelism, 1→10k-GPU scaling, architecture↔hardware interaction; 52/52 citations verified, all [E] numbers machine-audited.
- **2026-08-19 — `Evaluation-Engineering/` section (16 pages):** evaluation as an engineering discipline — benchmark design, contamination, reasoning/coding/agent/long-context/RAG/serving/safety/multimodal eval, LLM-as-judge, human eval, statistics.
- **2026-08-19 — Mission extension:** new `Graph-Engineering/` section (5 pages) plus deepened `Agents/` (7 pages), `Context-Engineering/` (4 pages), and `Harness-Engineering/` (5 pages).
- **2026-08-18 — Deep-dive: LLM router signals** — should a production router consider queue backlog, remaining work, and KV/prefix-cache state? First-principles thesis with a Python-verified routing example; three-pass adversarial review.
- **2026-08-18 — `Post-Training/Alignment-RLHF.md`:** full SFT → reward-model → PPO-RLHF → DPO → RLAIF → RLVR lineage with the math; 16 verified primary-source citations.
- **2026-08-18 — Inference optimization promoted into the wiki:** `Inference/Inference-Optimization.md` core page + the optimization-ladder deep-dive from the live measurement session.
- **2026-08-17 — Deep-dive: P/D disaggregation** — quantitative break-even model, KV-transfer fabric physics (RDMA/RoCE/IB/NVLink), measurement design, deployment decision tree.
- **2026-08-17 — Lab 13:** executed prefix-cache causal measurement — 8.7× TTFT cold→warm on an 8k identical prefix.
- **2026-08-16 — Initial build:** 33 sections / 48 content pages, milestones timeline (1948–2026), 10 lineage maps, glossary, Zero-to-Hero + 80/20 learning paths, 12 hands-on labs.

Full history: `CHANGELOG.md`.

---

## What this is

A structured, cross-linked technical knowledge base covering the evolution of LLMs from
foundational ideas (information theory, perceptrons, backpropagation, word embeddings, RNNs,
seq2seq, attention) to the state of the art as of **2026-08-16** (verified against live
primary sources on that date).

For every major topic the wiki answers:
- **what** happened / what it is
- **why** it mattered — the technical problem it solved
- **how** it works — mechanism + mathematics
- **what limitations remained**
- **what research followed** (see `Research-Lineage/`)
- **how it changed** modern architecture, training, inference, agents, or deployment

## How this wiki is built
Inspired by Andrej Karpathy's *llm-wiki*, this wiki is researched, written, and maintained
by a **Hermes agent** running on a home lab:

- **Primary model:** Qwen 3.8 27B, served on an RTX 5090 workstation
- **Delegate model:** DeepSeek V4 Flash, served on dual DGX Spark GB10 machines

## Audience
AI engineers · inference engineers · researchers · infrastructure architects · graduate students · zero-to-advanced learners.
`Learning-Path/` gives a levelled route through everything.

## Source policy (strict)
Claims carry a tag:

| Tag | Meaning |
|---|---|
| `[F]` | Verified primary source (paper / official docs / official blog / repo) — link given |
| `[E]` | Empirically verified in this environment (measurement / computation) |
| `[I]` | Inference by the author (stated as such, not presented as fact) |
| `[A]` | Assumption |
| `UNVERIFIED` | Could not be verified at research time — do not rely on it |

**Never:** invented paper names, authors, dates, model sizes, benchmark scores, or citations.
Marketing claims are labelled *vendor claim* and are never presented as independent results.

## Source tiers
1. Original research papers (peer-reviewed first: NeurIPS, ICML, ICLR, ACL, EMNLP, MLSys, OSDI, SOSP, USENIX)
2. arXiv preprints (labelled preprint)
3. Official model technical reports
4. Official GitHub repos
5. Official engineering documentation
6. Official company research blogs
7. Reputable secondary analysis (only when 1–6 are insufficient, labelled as such)

Key source orgs: arXiv · OpenAI · Anthropic · Google DeepMind · Meta AI · Microsoft · Alibaba/Qwen · DeepSeek · Mistral · xAI · Hugging Face · vLLM · SGLang · NVIDIA TRT-LLM/Dynamo · llm-d · PyTorch · JAX · Megatron-LM · DeepSpeed.

## Layout (top level)

```
LLM-Wiki/
├── README.md                  ← you are here
├── CHANGELOG.md               ← maintenance log (required per protocol §48)
├── Milestones.md              ← major milestones dashboard (§36)
├── AI-Accelerator/            ← FIRST-CLASS (2026-08-24): 31-page AI chip & architecture engineering — why specialized chips, memory wall, six flagships (NVIDIA/AMD/TPU/Cerebras/Groq/Trainium), scheduling, interconnects, numerics, roofline, rack-scale, ecosystems, decision tree, 80/20, zero-to-hero, provenance audit
├── Foundations/               ← pre-LLM history: information theory → RNN → seq2seq → attention
├── Transformer/               ← first-principles learning path (tokens→logits, math, toy examples)
├── Model-Architectures/       ← encoder/decoder, MoE, MHA/MQA/GQA, RoPE/ALiBi, RMSNorm, SwiGLU, SSM, hybrids
├── Training/                  ← data, pretraining, scaling laws, distributed training, comms (overview)
├── Training-Engineering/      ← FIRST-CLASS (2026-08-20): model anatomy, pretraining recipe, scaling-law math, 5-axis parallelism, 1→10k-GPU scaling, architecture/hardware/memory/network interaction — [F]/[I]/[E]-tagged, Python-audited
├── Post-Training/             ← SFT, RLHF/PPO, DPO, GRPO, RLAIF, distillation, alignment & RLHF lineage
├── Production-Operations/     ← FIRST-CLASS (2026-08-23): LLM Reliability, SRE & Production Operations — SLI/SLO/SLA, goodput, golden signals, latency/error-budget/capacity engineering, failure taxonomy, GPU/distributed/KV reliability, overload/retries/fallback/routing, autoscaling/K8s/health/observability/dashboards/alerting/tracing/quality, releases/shadow/canary/regression/chaos/incidents/runbooks/postmortems, cost/agent/RAG SRE, multi-region/DR, reference architecture, 80/20 + Zero-to-Hero + capstone, 12 labs
├── Platform-Economics/         ← FIRST-CLASS (2026-08-24): Multi-Tenant LLM Platform Economics & Governance — unit economics, CAPEX/OPEX, utilization/queueing, token/KV/batching economies, model & routing economics, Q-C-L frontier, metering, showback/chargeback, pricing, tiers, SLO economics, fairness/noisy-neighbor, quotas, admission, budget routing, isolation, data/model/policy governance, cloud burst, local-vs-API, capacity/forecasting, FinOps, waste, agents/evaluators/RAG/context/multimodal, goodput, energy, failure cost, GPUaaS/K8s, reference arch, simulator, 80/20 + Zero-to-Hero + decision framework + formulas + anti-patterns, 15 labs
├── Reasoning/                 ← CoT, ToT, ReAct, process supervision, test-time compute, RL for reasoning
├── Inference/                 ← The Life of a Token, Roofline, continuous batching, P/D disaggregation (+ Deep-Dives/), metrics, inference optimization, Production-Serving/ (routing & scheduling handbook, 2026-08-22)
├── KV-Cache/                  ← Caching Architecture knowledge area (2026-08-26): memory equation, paged KV (PagedAttention), prompt/prefix caching, distributed KV, hierarchical offloading, eviction, quantization — the cache as a distributed/tiered/shared/paged object
├── Attention/                 ← attention taxonomy (architecture vs kernel vs memory strategy)
├── Quantization/              ← FP16/BF16/FP8/INT8/INT4/FP4, GPTQ/AWQ/SmoothQuant/GGUF/NVFP4
├── Speculative-Decoding/      ← draft-verify, Medusa, EAGLE, MTP, production practice
├── Serving-Engines/           ← engine layer: vLLM, SGLang, TensorRT-LLM (+ GPU-Systems deep dives), llama.cpp, NIM, Engine-Landscape (layer stack), 7-way Mega-Comparison
├── Distributed-Inference/     ← DP/TP/PP/EP/CP/SP with comm patterns + cluster platforms (Dynamo, llm-d, P/D, KV transfer) + Implementation/ (PART 2, 2026-08-26: how the five jobs are built — distributed KV, offload, routing, P/D, global KV state, NIXL)
├── Agents/                    ← LLM→tool use→agent→multi-agent→coding agents→protocols (MCP/A2A)
├── Harness-Engineering/       ← system scaffolding; model-vs-harness question
├── Context-Engineering/       ← prompt vs context vs harness; budgets, long-context reality, compaction, memory
├── Graph-Engineering/         ← KGs/GraphRAG, GNNs, reasoning-as-search, agent-workflow graphs
├── GPU-Systems/               ← FIRST-CLASS (2026-08-21): 40-page GPU arch → CUDA kernels → memory → GEMM/Tensor-Cores → inference engines (vLLM/SGLang/TRT-LLM) → multi-GPU/distributed (TP/PP/EP/MoE/NCCL) → profiling/diagnostics → 11 reference architectures + 12 hands-on labs
├── GPU-Communication/         ← NEW (2026-08-25): 21-page communication-stack handbook — NCCL/NIXL/UCCL + UCX/RCCL/UCC/NVSHMEM/DeepEP, the 3-branch taxonomy, RDMA/IB/RoCE/EFA, benchmarking, troubleshooting, decision guide, labs
├── RAG/                       ← full pipeline + advanced RAG (hybrid, graph, agentic, self-RAG)
├── Multimodal/                ← text/image/audio/video/speech/robotics strategies
├── Evaluation/                ← benchmark reference: families, contamination, saturation
├── Evaluation-Engineering/    ← the discipline: fundamentals, benchmark design, reasoning/coding/agent/long-context/RAG/serving/safety/multimodal eval, LLM-as-judge, human eval, statistics
├── Open-Source-Models/        ← Qwen, Llama/Meta, DeepSeek, Mistral, Gemma, OLMo, Falcon, BLOOM…
├── Frontier-Models/           ← GPT-5.x, Claude (Opus 5/Sonnet 5/Fable 5/Mythos 5), Gemini 3.x (verified 2026-08)
├── Hardware/                  ← GPU archs, HBM, NVLink/NVSwitch, PCIe, InfiniBand, RoCE, DPU
├── Networking/                ← NCCL, RDMA, collectives, SHARP, GPUDirect — tied to TP/EP/PD
├── AI-Factory-Networking/     ← NEW (2026-08-25): 55-page AI networking handbook — RDMA → InfiniBand → RoCEv2 → AI Ethernet → Ultra Ethernet/UET → gigascale fabrics (Clos math, vendor fabrics, PFC/ECN/DCQCN, NCCL-driven GPU fabrics, labs, 100 interview questions)
├── Research-Papers/           ← structured paper database (§33 format)
├── Research-Lineage/          ← idea-influence maps (Transformer→MHA→MQA→GQA, etc.)
├── Latest-Research/           ← rolling dashboard (7/30/90 days) + monthly pages (YYYY-MM.md)
├── Benchmarks/                ← what each benchmark tests / does not test
├── Glossary/                  ← cross-linked term index
├── Learning-Path/             ← Zero-to-Hero levels 0–8 + 80/20 guide
└── Labs/                      ← 12 hands-on research labs (hypothesis→commands→interpretation)
```

## Reading guide
- **Zero to hero:** start `Foundations/` → `Transformer/` → `Inference/The-Life-of-a-Token.md` → `KV-Cache/` → `Training/` → `Post-Training/` → `Reasoning/` → `Agents/` → `Latest-Research/`.
- **Agent engineer:** `Agents/Agentic-AI-Evolution.md` → `Agents/Tool-Use.md` → `Agents/Agent-Loops-and-Reasoning-Strategies.md` → `Context-Engineering/` → `Harness-Engineering/Harness-Anatomy.md` → `Agents/Coding-Agents.md` → `Graph-Engineering/`.
- **Inference engineer:** `Serving-Engines/Engine-Landscape.md` (the layer stack: engines vs packaging vs platforms) → `Inference/The-Life-of-a-Token.md` → `Inference/Roofline.md` → `Inference/Inference-Optimization.md` (what to apply FIRST, measured) → `Attention/` → `KV-Cache/` → `Serving-Engines/` (the big three's deep dives live in `GPU-Systems/`) → `Serving-Engines/Engine-Mega-Comparison.md` (7-way matrix + decision guide) → `Distributed-Inference/Overview.md` (cluster jobs + KV transfer) → `Distributed-Inference/NVIDIA-Dynamo.md` + `llm-d.md` + `Dynamo-vs-llm-d.md` → `Quantization/` → `Speculative-Decoding/`.
- **GPU systems / infrastructure engineer:** `GPU-Systems/Architecture.md` (SIMT, warps, memory, latency-hiding) → `GPU-Systems/Bandwidth-vs-Compute.md` (the roofline + ridge) → `GPU-Systems/GEMM.md` + `Tensor-Cores.md` → `GPU-Systems/Kernel-Stack.md` → `GPU-Systems/Inference-Engines.md` + `vLLM`/`SGLang`/`TensorRT-LLM` → `GPU-Systems/Multi-GPU.md` + `Tensor-Parallelism` + `MoE-Expert-Parallelism` → `GPU-Systems/Distributed-Architectures.md` (11 topologies) → `GPU-Systems/Diagnostics.md` + `Profiling.md` → `GPU-Systems/Labs.md` (do it). Full ordered path: `GPU-Systems/Zero-to-Hero-Path.md`.
- **AI infrastructure architect / LLM systems engineer (communication):** `GPU-Communication/01-why-communication-matters.md` (the taxonomy) → `02-collective-communication-fundamentals.md` (the 7 collectives + α+β) → `03-gpu-network-architecture.md` (topology ladder + GDR) → `04-nccl-deep-dive.md` + `05` + `06` (NCCL 2.31.2) → `07-nixl-deep-dive.md` + `08-nixl-kv-cache-transfer.md` (KV physics) → `09-uccl-deep-dive.md` + `10` (collectives/P2P/EP) → `11` (the adjacent libraries) → `12`/`13`/`14` (training/inference/MoE comm) → `15-nccl-vs-nixl-vs-uccl.md` (the matrix) → `18-architecture-decision-guide.md` (pick a stack) → `17-troubleshooting.md` + `19-practical-labs.md` (run + debug it).
- **AI/HPC network architect:** `AI-Factory-Networking/01-why-ai-networking-is-different.md` (JCT physics) → `02` (five-network taxonomy) → `03`–`04` (RDMA fundamentals + ops/transports) → `05`–`15` (InfiniBand zero-to-hero: architecture, speeds, addressing, QPs, packets, credits, SM, routing, SHARP, GPUDirect + NCCL) → `16`–`23` (RoCE deep dive: PFC, ECN, DCQCN, lossless design) → `24`–`32` (vendor fabrics + Ultra Ethernet/UET) → `33`–`36` (collectives, MoE, training vs inference) → `42`–`44` (Clos math, bandwidth calcs, benchmarking) → `45`–`46` (troubleshooting) → `49` (decision tree) → `52` (reference architectures) → `53` (labs) → `55` (cheat sheet).
- **AI chip / hardware engineer:** `AI-Accelerator/01-why-ai-needs-specialized-chips.md` (why DSA) → `03-memory-wall-and-data-movement.md` (the wall) → `04-how-to-analyze-an-ai-chip.md` (the method) → `15-ai-chip-design-philosophies.md` + `16-hardware-vs-software-scheduling.md` (the two axes) → `21-ai-accelerator-comparison.md` (the two matrices) → `23-roofline-across-ai-architectures.md` (the model) → `22-workload-to-chip-mapping.md` + `27-how-to-choose-ai-hardware.md` (the decision) → `29-ai-chip-zero-to-hero.md` (the 10-level path). Section: `AI-Accelerator/README.md`.
- **SRE / platform / ops engineer:** `Production-Operations/01-llm-reliability-overview.md` → `02-sli-slo-sla-for-llms.md` → `03-goodput-vs-throughput.md` → `04-llm-golden-signals.md` → `05-production-latency-debugging.md` → `20-llm-observability-stack.md` → `22-alerting-strategy.md` → `30-llm-incident-response.md` → `31-production-runbooks.md` → `32-blameless-postmortems.md`, then the failure/reliability deep-dives (`10`–`16`) and scale-out (`36`–`37`). Companion roadmap: `Production-Operations/39-llm-sre-80-20.md` + `40-llm-sre-zero-to-hero.md`.
- **Platform owner / FinOps / AI-infra architect:** `Platform-Economics/01-multi-tenant-llm-platform-overview.md` → `51-multi-tenant-llm-platform-80-20.md` → `03-llm-inference-unit-economics.md` → `05-gpu-utilization-economics.md` → `13-tenant-metering.md` → `14-showback-chargeback.md` → `15-llm-platform-pricing-models.md` → `18-tenant-fairness.md` → `20-quota-engineering.md` → `22-budget-aware-routing.md` → `24-data-governance.md` → `27-policy-as-code.md` → `40-llm-platform-governance-model.md` → `48-enterprise-multi-tenant-llm-platform.md` → then the formulas (`54`) + simulator (`49`) + labs. Companion: `52-multi-tenant-platform-zero-to-hero.md`.
- **Researcher:** `Research-Papers/` → `Research-Lineage/` → `Evaluation/` → `Evaluation-Engineering/` → `Latest-Research/` → open questions in each section.
- **Evaluation engineer:** `Evaluation-Engineering/Evaluation-Fundamentals.md` → `Model-Evaluation.md` → `Benchmark-Design.md` → `Statistical-Evaluation.md` → the domain pages (`Agent-Tool-Use-Evaluation`, `RAG-Evaluation`, `Harness-Serving-Evaluation`, …) → `LLM-as-a-Judge.md` / `Human-Evaluation.md` (scorer calibration).

## The ten questions this wiki must answer
1. How did modern LLMs evolve? → `Milestones.md`, `Foundations/`, `Model-Architectures/`
2. Why were the important innovations invented? → every page's *Why This Exists / Problem It Solves*
3. How do modern LLMs work internally? → `Transformer/`, `Inference/The-Life-of-a-Token.md`
4. How are they trained? → `Training/`
5. How are they served efficiently? → `Inference/`, `Serving-Engines/`, `Distributed-Inference/`
6. How do reasoning models work? → `Reasoning/`
7. How do agents extend models? → `Agents/`, `Harness-Engineering/`, `Context-Engineering/`
8. What are the major research milestones? → `Milestones.md`
9. What is the current state of the art? → `Latest-Research/`, `Frontier-Models/`, `Open-Source-Models/`
10. What directions are emerging next? → `Latest-Research/README.md` radar, open-question lists

## Maintenance protocol (living wiki, §48)
On any update:
1. discover new research (arXiv API + vendor news); 2. diff against existing pages; 3. update **only affected sections**; 4. preserve historical context; 5. add new papers to `Research-Papers/`; 6. update `Milestones.md` when justified; 7. update lineage maps; 8. run the evaluator model (DeepSeek class, independent endpoint) on important changed pages and record its verdict; 9. record the change in `CHANGELOG.md` with `LAST_UPDATED` on the page.

## Verified-current snapshot (2026-08-16)
Frontier (primary sources): OpenAI GPT-5.6 series incl. "Ultrafast" Sol mode (openai.com RSS, 2026-08-13); Anthropic Claude Opus 5 (2026-07-24), Sonnet 5 (2026-06-30), plus Fable 5 / Mythos 5 tiers (anthropic.com/news); Google Gemini 3.7 Flash (Aug 2026, deepmind.google). Open-weights: Meta Muse Glimmer 30B Apache-2.0 (2026-08-10, HF blog); HuggingFace *State of Open Models: Summer 2026* (2026-08-14): Chinese-lab open model ceiling 754B–2.78T params; NVIDIA Nemotron 3 Ultra 561B; Qwen as de-facto community base model. DeepSeeK/xAI latest releases: UNVERIFIED at research time.

## Contributing
Contributions, corrections and research references are welcome.

## License
MIT License — see `LICENSE`.
