# Research Radar — GPU Systems & LLM Inference (6–12 month watchlist)
`LAST_UPDATED: 2026-08-21 · Status: live page, re-verify quarterly` · A maturity-classified
radar of what's worth tracking. Every paper listed below was **title/ID-verified against the
arXiv API on 2026-08-21** (ids + dates + first author shown). Where a claim is a **vendor
number** I say so; where I have only the abstract/title I say "direction from title — read
to confirm." No benchmark results are asserted from memory.

## 30-Second Explanation
Four maturity buckets:
- **Production-ready** — in vLLM/SGLang/TRT-LLM today, or the substrate everyone runs on.
- **Emerging** — deployed in at least one real system, or a strong 2025 paper with a
  working prototype; expect it in engines within 6–12 months.
- **Research-stage** — solid paper, clear idea, but not yet in a production engine.
- **Experimental** — early / speculative / architecture-specific; high risk, high upside.
The rule: **vendor claims are hypotheses until independently reproduced** (see
`Perf-Experiment-Template.md`). Track the *direction*, not the headline number.

## Production-ready (the substrate)
- **FlashAttention (1/2/3)** — the reference exact attention; FA-3 exploits Hopper TMA/
  async. [F: arXiv:2205.14135, 2307.08691, 2407.08608] In every engine.
- **PagedAttention + continuous batching** (vLLM) + **RadixAttention** (SGLang) — the KV +
  scheduling substrate. [F: arXiv:2309.06180, 2312.07104]
- **Triton / cuBLASLt / CUTLASS** — the kernel-ecosystem substrate. [F: repos]
- **NCCL + NVL72** — the collective + scale-up substrate. [F: NVIDIA]
> These are "done" in the sense that the *idea* is settled; the *kernels* still improve.

## Emerging (in a real system or a strong 2025–26 paper)
- **Prefill/decode disaggregation** — production in vLLM/SGLang/TRT-LLM; the research
  frontier is the **KV-transfer + routing** layer. Watch: FlowKV (disaggregated KV transfer
  & scheduling, [F: arXiv:2504.03775]); HexGen-2 (disaggregated, heterogeneous,
  [F: arXiv:2502.07903]); Cronus (heterogeneous GPU clusters via partial disaggregation,
  [F: arXiv:2509.17357]); "When Does Disaggregation Pay?" (a simulation that *bounds* when
  P/D split wins, [F: arXiv:2608.03741]) — useful as a decision tool, not a vendor claim.
- **KV-cache scheduling / placement** — the new hot layer now that P/D is default. Watch:
  Pallas (proactive KV migration, [F: arXiv:2608.16477]); PRISM (scheduling–memory co-design,
  [F: arXiv:2605.08581]); dynamic KV placement in heterogeneous memory ([F: arXiv:2508.13231]).
- **Speculative decoding (native MTP)** — EAGLE-class in engines; the frontier is **batch
  spec-decode done right** ([F: arXiv:2510.22876]) and hybrid/self-spec for non-autoregressive
  or agentic loops ([F: arXiv:2605.01106]).
- **FP4 / NVFP4 inference** — Tensor-Core-native on Hopper/Blackwell; the research question
  is *where* it hurts quality. Watch: layer/block sensitivity of NVFP4 ([F: arXiv:2603.08747]);
  ThriftAttention (mixed-precision FP4 attention for long context, [F: arXiv:2605.23081]);
  4-bit attention w/ QAT ([F: arXiv:2603.00040]). **Vendor numbers (NVIDIA FP4 throughput) are
  [F: vendor spec] — treat as a ceiling, not an achieved result.**
- **MoE serving on the network** — EP + AllToAll is production; the frontier is **expert
  placement + bandwidth-adaptive MoE**. Watch: MAPLE (layer-wise expert allocation,
  [F: arXiv:2608.15299]); FreeToken (edge-native MoE, bandwidth-adaptive execution,
  [F: arXiv:2608.16157]).
- **Collective communication planning** — NCCL is the substrate; the research is **adaptive /
  planned collectives + observability**. Watch: planning + runtime adaptation for distributed
  LLM collectives ([F: arXiv:2608.15118]); NIXT (NCCL inspector/observability, [F: arXiv:2608.01449]);
  non-uniform network access characterization ([F: arXiv:2608.00867]).

## Research-stage (solid paper, not yet in an engine)
- **Attention alternatives (linear / hybrid)** — the long-context + decode challenge. Watch:
  systematic analysis of hybrid linear attention ([F: arXiv:2507.06457]); ReGLA (refined gated
  linear attention, [F: arXiv:2502.01578]); exact-flow linear attention ([F: arXiv:2512.12602]).
  High upside for decode bandwidth; quality is the open question.
- **Hardware/attention co-design** — fusing FlashAttention into the datapath. Watch:
  SystolicAttention (FlashAttention fused in a single systolic array, [F: arXiv:2507.11331]);
  low-cost FlashAttention w/ fused exp/mult hardware ([F: arXiv:2505.14314]). Architecture-specific.
- **Scheduling / SLO-aware fleet** — multi-tier SLA + operator-level provisioning. Watch:
  multi-tier SLA scheduling ([F: arXiv:2608.16336]); OpScale (operator-level autoscaling,
  [F: arXiv:2608.13499]); SLO-aware fleet configuration ([F: arXiv:2608.19659]).
- **Heterogeneous GPU serving** — mixing GPU classes (compute nodes + bandwidth nodes, or
  different gens). Watch: HYDRA (chiplet DSE for hybrid LLM serving, [F: arXiv:2608.19395]);
  "From LLM Inference to Agentic Workloads" (characterization, [F: arXiv:2608.15127]).

## Experimental (early / high-risk)
- **GPU execution-model changes** — thread-register decoupled tensor execution
  ([F: arXiv:2608.19628]) — pre-architecture; likely years from a shipping SM.
- **AI-for-kernels / multi-agent kernel optimization** — LLM agents that *write* kernels
  (KernelArc, [F: arXiv:2608.17071]); rl-triton (Triton kernels for RL, [F: arXiv:2608.17641]).
  Interesting, not a production path yet.
- **Non-GPU / edge serving** — pre-compiled pipeline shards on Intel AI PC ([F: arXiv:2608.19147]);
  FlashAttention for scalable-vector (RISC-V) ([F: arXiv:2608.18656]). Different hardware,
  different roofline.

## The 6–12 month watchlist (ranked by "likely to hit production")
1. **KV-aware P/D routing** — the bottleneck P/D disaggregation just created. (FlowKV, Pallas, PRISM.)
2. **FP4/NVFP4 quantized GEMM + attention** — the next quant step once HBM pressure is the #1 limit.
3. **Native MTP / batch speculative decoding** — decode-latency without a separate draft model.
4. **Bandwidth-adaptive MoE** — expert placement that moves with the fabric.
5. **SLO-aware multi-tier schedulers** — the serving-system layer above the engines.
6. **Adaptive/planned NCCL + observability** — collective planning + a "NIXT" for the fabric.
7. **Hybrid linear attention** — if quality catches up, the decode-bandwidth game changer.

## Vendor-claim vs independent (the discipline)
- **Vendor spec** ([F: vendor spec]) — NVIDIA FP4/NVFP4 TFLOPS, NVLink BW, NVL72 domain
  size. These are *capabilities*, not *achieved serving results*. Cross-check against
  `../Hardware/README.md`.
- **Vendor benchmark** — never an [E]. Treat as a hypothesis to reproduce (`Perf-Experiment-Template.md`).
- **Independent / measured** — only claim [E] when you (or a cited independent source)
  ran it. Everything else is [I: direction from title — read to confirm].

## Related
`Research-Lineage.md` (where each of these sits in the idea chain) ·
`../Latest-Research/2026-08.md` (dated notes) · `Perf-Experiment-Template.md` (how to
reproduce a claim) · `Cross-Layer-Optimization.md` (which layer each advance moves the
bottleneck to) · `Diagnostics.md` (how you'd detect the new bottleneck once the old one
is fixed).
