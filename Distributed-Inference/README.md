# Distributed Inference — Parallelism Dimensions
`LAST_UPDATED: 2026-08-16` · Status: core page

## 30-Second Explanation
A model that doesn't fit one GPU (or needs more bandwidth than one GPU has) is split.
Each split strategy trades off communication volume vs latency vs memory vs model-size
headroom. Know each pattern's **collective** (AllReduce/AllGather/AllToAll) — that's what
the network pays for.

## The six dimensions

### 1. Data Parallelism (DP)
- Split the **batch**, replicate the model. Each GPU sees different requests.
- Communication: essentially none for inference (no gradient sync); sync only for
  distributed KV/prefix state if used.
- Use: many GPUs each holding a full model (or shards) → throughput.
- Inference twist: DP replicas + **router** = the default multi-GPU serving topology.

### 2. Tensor Parallelism (TP)
- Split **each layer's weight matrices** across GPUs (col/row-parallel GEMM).
- Communication: **2 AllReduce per layer** (one after QKV/attention, one after MLP)
  [F: Megatron-LM arXiv:1909.08053]. Latency-critical → needs the fastest fabric (NVLink).
- Memory: weight / TP per GPU. Model-size benefit: linear.
- Hardware: intra-node NVLink first; cross-node TP is painful (AllReduce every layer at
  line-rate). [I: standard practice]

### 3. Pipeline Parallelism (PP)
- Split **layers** across GPUs; each stage holds a slice; micro-batches flow.
- Communication: **point-to-point** activations between stages (small).
- Memory: weight / PP per GPU.
- Cost: **bubble** — idle time unless micro-batch pipeline (GPipe arXiv:1811.06965,
  PipeDream, 1F1B) keeps stages busy. Inference PP: bubble ≈ prefill latency per request.
- Use: very large models; multi-node when NVLink isn't available.

### 4. Sequence / Context Parallelism (SP/CP)
- Split the **sequence** (prompt) across GPUs; each holds K/V for a chunk; attention
  gathered via **AllToAll** (Ring Attention [F: arXiv:2211.12876; DeepSpeed Ulysses
  arXiv:2309.14509]) or ring-rotation.
- Memory: KV / SP.
- Use: ultra-long context on many GPUs; the backbone of 1M+ context serving.
- Communication: AllToAll per attention layer (or ring rotations) — bandwidth-hungry.

### 5. Expert Parallelism (EP) — MoE only
- Split the **experts** across GPUs; each token routed to its expert's GPU.
- Communication: **AllToAll** (dispatch + combine) — the MoE bottleneck.
- Memory: expert weights / EP.
- Use: MoE models (Mixtral, DeepSeek, Qwen-MoE, GPT-OSS). Wide EP + KV-aware placement.
- [F: TRT-LLM wide-EP; SGLang large-scale EP (96×H100 DeepSeek blog)]

### 6. Expert-Data / Hybrid (EP+TP, EP+PP)
- Practical stacks: **TP within node (NVLink) + EP/PP across nodes** [I: standard 2024+
  practice; Megatron-Core, TRT-LLM, SGLang all expose these knobs].

## Communication → hardware (the mapping)
| Collective | Pattern | Best fabric |
|---|---|---|
| AllReduce | TP (2×/layer) | NVLink/NVSwitch (intra-node) |
| AllToAll | EP, CP | NVLink or fast RDMA (InfiniBand/RoCE) |
| AllGather | FSDP/ZeRO-3 param gather (training) | NVLink/RDMA |
| ReduceScatter | ZeRO-1 gradient partition (training) | NVLink/RDMA |
| P2P | PP stages | any |
| KV transfer | P/D disaggregation | RDMA / NVL72 |

## Per-dimension summary (inference)
| Dimension | Comm | Latency effect | Memory effect | Model-size benefit | Hardware req |
|---|---|---|---|---|---|
| DP | ~0 | none | none (replica) | none | any |
| TP | AllReduce ×2/layer | high (needs NVLink) | weight/GPU ÷ TP | linear | intra-node NVLink |
| PP | P2P | bubble ∝ stages | weight/GPU ÷ PP | linear | cross-node OK |
| CP/SP | AllToAll/ring | attention cost | KV/GPU ÷ CP | context ↑ | fast fabric |
| EP | AllToAll | MoE dispatch | experts/GPU ÷ EP | MoE scale | fast fabric |

## Related
`Networking/README.md` · `Inference/Prefill-Decode-Disaggregation.md` ·
`Hardware/README.md` · `Labs/Lab-8` (TP sweep).

## Key Takeaways
TP = latency (NVLink-bound). EP/CP = bandwidth (AllToAll). PP = capacity (cross-node).
DP = scale-out (router-bound). The best stack composes them: TP intra-node, EP/PP
cross-node, DP via router.
