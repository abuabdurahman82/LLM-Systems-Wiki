# Prefill/Decode Disaggregation
`LAST_UPDATED: 2026-08-16` · Status: core page

## 30-Second Explanation
Run prefill and decode on **different GPUs (or node pools)**: prefill GPUs process prompts
in parallel; decode GPUs stream tokens; the KV cache is **transferred** from prefill →
decode once, instead of being re-read from HBM in the same step forever. Separates two
workloads with opposite characteristics (compute-bound vs bandwidth-bound) so each pool
can be tuned and scaled independently.

## The pipeline
```
Request → Router → Prefill GPU (compute K,V, logits) → KV transfer → Decode GPU (stream tokens)
```

## Why it matters (first principles)
- Prefill and decode want different hardware, different batch sizes, different kernel
  configs (CUDA-graph batch lists), different KV footprints. Co-located, they interfere
  (chunked-prefill stalls decode steps; big prefills spike ITL).
- Disaggregation gives each stage its own roofline operating point. [I]
- **KV-aware routing/scheduling** becomes first-class: place decode where the KV landed
  (or send KV to the idlest decode). [F: literature]

## Research & systems lineage
- **DistServe** (Zhong et al. 2024, OSDI'24, arXiv:2401.09670) [F] — formalizes
  prefill/decode as separable SLOs; joint scheduling of TTFT and TPOT.
- **Splitwise** (Patel et al. 2024, ISCA'24, arXiv:2311.18698) [F] — prefill/decode
  placement + KV over high-bandwidth fabric (InfiniBand).
- **Mooncake** (Moonshot AI, 2024, "Kimi" production, arXiv:2407.00079) [F] — production
  disaggregated serving at scale; KVCache-centric "context pool"; the reference
  production architecture for KV-aware scheduling.
- **vLLM disaggregated prefill/decode** [F: vLLM docs] — KV transfer via shared memory /
  NIXL / RDMA; "disaggregated prefill, decode, and encode" (encoder for multimodal too).
- **SGLang PD disaggregation** [F: SGLang blog/docs] — program-aware; DeepSeek 96×H100
  deployment blog.
- **TRT-LLM disaggregated serving** [F: docs] — most production-hardened in the NVIDIA
  ecosystem.
- **NVIDIA Dynamo** [F: GitHub/docs] — the 2025 production framework: router (SM gateway),
  prefill/decode pools, KV-aware KV transfer over RDMA, LLM-aware autoscaling, token-
  level streaming; pairs with TensorRT-LLM kernels.
- **llm-d** [F: GitHub (Red Hat / Google / NVIDIA / Intel et al., 2025)] — Kubernetes-native
  disaggregated serving; KV-aware leader election, P/D pools as K8s workloads, RDMA
  transfer; the "disaggregated inference on k8s" reference.

## KV transfer — the physics
| Path | Bandwidth | Notes |
|---|---|---|
| shared memory (same host) | ~100+ GB/s | cheapest; same-node P/D |
| NVLink | ~900 GB/s (H100 x8) | intra-node; NVL72 raises this dramatically |
| PCIe | ~64 GB/s (5.0 x16) | host bounce, slower |
| **InfiniBand / RoCE (RDMA)** | ~50 GB/s (400G NDR) | cross-node standard; GPUDirect RDMA avoids host copies [F: NVIDIA] |
| SHARP / in-network reduction | — | collective offload; helps training > serving |

KV size = `2·L·h_kv·d_h·S·b` (`KV-Cache/README.md`). At 128k ctx, GQA, FP16: ~16 GiB per
request → cross-node transfer time matters; NVL72-class fabrics make intra-pod transfer
nearly free, reshaping the "how far apart can P/D be" question. [I]

## Bottlenecks & open problems
1. **KV transfer latency** vs decode start — pipeline the transfer with early decode
   (speculative decode of the first few tokens). [I]
2. **KV-aware routing** — send request to the decode GPU whose pool has the most free KV;
   Mooncake's context pool is the template. [F]
3. **Failure domains** — P or D dies mid-transfer → preemption & KV re-fetch. [I]
4. **Economics** — two pools cost more hardware; win shows up in SLO attainment (P99
   TTFT/TPOT), not average tokens/$. [I]

## Related
`Inference/Continuous-Batching.md` · `Networking/README.md` (RDMA, GPUDirect) ·
`Distributed-Inference/README.md` · `Labs/` (P/D lab is Lab-12-adjacent; see roadmap).

## Key Takeaways
Disaggregation = decoupling two roofline regimes. The hard part isn't the split — it's
**KV transfer** and **KV-aware scheduling**. Mooncake / Dynamo / llm-d are the three
production references (2024–2026).
