# Distributed Inference Communication
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
Serving a big model across GPUs generates three *different* communication
streams at the same time: **in-layer collectives** (TP/PP/CP — NCCL), **KV-cache
movement between prefill and decode workers** (NIXL), and **expert
dispatch/combine for MoE** (UCCL-EP/DeepEP). This page places each stream, and
documents how each serving engine (vLLM, SGLang, TensorRT-LLM, Dynamo, llm-d)
wires its communication, per upstream docs — no guessing.

## 1. The three streams
```text
STREAM A — in-layer collectives (every token, every layer)
   TP AllReduce ×2/layer, PP Send/Recv, CP AllGather/P2P  →  NCCL (NVLink)

STREAM B — KV-cache movement (per request, once)
   prefill → decode handoff; prefix fetch; tier offload/onload  →  NIXL (UCX/UCCL/GDS)

STREAM C — expert parallel (MoE layers, per micro-batch)
   token dispatch → expert GEMM → combine  →  UCCL-EP / DeepEP (RDMA, GPU-driven)
```
They differ in **cadence** (every-token vs once-per-request vs every-microbatch),
**size** (KiB–MB vs GiB vs MB with non-uniform sizes), and **synchronicity**
(collective-synchronous vs asynchronous one-sided vs collective-but-dynamic).
That's why no single library covers all three — they are *different branches of
the taxonomy* ([01 §3](01-why-communication-matters.md)), not one job with three
names.

## 2. Tensor-parallel serving (Stream A, the baseline)
```text
              Transformer Layer
                     │
          ┌──────────┴─────────┐
          ▼                    ▼
        GPU0                  GPU1
          │                    │
          └──── AllReduce ─────┘
                     │
                     ▼
                Next Layer
```
- Two AllReduces per layer (attention output projection; MLP output projection)
  — activation-sized (h×b×2B; for h=8192, b=1: 32 KiB each, ~56 KiB ring
  traffic per layer [E: 2(N−1)/N × 32 KiB at N=8, see 05 §8]), microseconds on
  NVLink → TP is *cheap when intra-node* and *expensive cross-node* (the
  classic argument against cross-node TP)
  [../GPU-Systems/Tensor-Parallelism.md].
- Pipeline parallel (if the model doesn't fit TP-wise): Send/Recv of
  activations at stage boundaries — latency-sensitive, bubble-dominated
  [../GPU-Systems/Pipeline-Parallelism.md].
- Context parallel: ring-attention passes KV blocks P2P/AllGather
  [../Inference/Prefill-Decode-Disaggregation.md].
- Multi-node serving = the same streams, with Stream A's cross-node hops on the
  fabric (and the known latency cost) [../Distributed-Inference/Overview.md].

## 3. KV-cache movement (Stream B)
Full treatment: [08 NIXL for KV-Cache Transfer](08-nixl-kv-cache-transfer.md).
Summary: prefill computes the KV; decode must hold it; the handoff is an
asynchronous, one-sided, bulk copy — the exact fit for NIXL's agent + buffer
lists + notifications, with UCX/UCCL/GDS as backends and GDR for HBM↔HBM.
Worked numbers: 4.0 GiB @ 400 Gb/s ≈ 85.9 ms [E]; h=0.9 prefix hit @ 100 GbE:
343.6 → 34.4 ms [E] — KV-aware routing is a communication win.

## 4. MoE EP (Stream C)
Full treatment: [14 MoE Communication](14-moe-communication.md). Summary:
per-token routing → all-to-all dispatch/combine; specialized libraries (DeepEP
V2 on NCCL Gin; UCCL-EP portable across vendors) at IBGDA-class performance;
load imbalance is the enemy.

## 5. Engine-by-engine communication map (verified 2026-08-25)
Format: `Engine ─ TP ─ PP ─ KV transfer ─ EP ─ data movement`.

### 5.1 vLLM
- **TP** → NCCL (via torch.distributed process groups; the engine's default
  distributed backend) [I: vLLM distributed docs].
- **PP** → NCCL Send/Recv between pipeline stages [I].
- **KV transfer** → **`NixlConnector`** in `--kv-transfer-config`
  (`kv_role: kv_producer/kv_consumer`; optional `backends: ["LIBFABRIC"]`,
  `bidirectional_kv_xfer` for multi-turn, GB-series multi-instance via VMM
  registration; heterogeneous KV layout = experimental)
  [F: docs.vllm.ai NixlConnector guide, fetched 2026-08-25]. Also
  LMCacheConnector, MooncakeConnector, and the native Offloading Connector for
  CPU/storage tiers [F: vLLM docs/RFCs].
- **EP** → tensor-parallel groups host experts (EP is expressed through TP
  groups + all-to-all inside attention-free layers); no dedicated EP library in
  the stock engine [I: vLLM MoE implementation].
- **Data movement** → NIXL (KV) + native offloading (CPU/storage tiers)
  [F: vLLM RFC #38260 (multi-tier offloading)].

### 5.2 SGLang
- **TP** → NCCL (torch.distributed) [I: SGLang docs].
- **PP** → limited/secondary; SGLang's focus is TP + its RadixAttention prefix
  cache [I].
- **KV transfer** → **NIXL connector** (community contribution; PD disaggregated
  serving uses it) [F: SGLang docs — "NIXL connector available"; NVIDIA
  developer blog lists SGLang among NIXL frameworks].
- **EP** → DeepEP-based EP for MoE models (SGLang + DeepEP is the documented
  MoE-EP path) [I: SGLang MoE docs; verify per release].
- **Data movement** → NIXL (KV) + RadixAttention prefix caching (in-GPU
  prefix reuse, reducing the KV that must move at all)
  [../GPU-Systems/SGLang.md].

### 5.3 TensorRT-LLM
- **TP** → NCCL (built-in, engine-optimized collectives) [F: TRT-LLM docs].
- **PP** → supported in engine builds (pipeline parallelism) [I: TRT-LLM docs].
- **KV transfer** → **NIXL integration in the executor layer for
  disaggregated builds** (Dynamo/TRT-LLM disaggregated serving; NVIDIA lists
  TRT-LLM among NIXL frameworks) [F: NVIDIA developer blog NIXL section;
  Dynamo README backend table shows KVBM ✅ for TensorRT-LLM].
- **EP** → TRT-LLM's MoE executor (expert parallelism inside the engine)
  [I: TRT-LLM MoE docs].
- **Data movement** → NIXL (KV), its own GEMM/attention kernels elsewhere
  [../GPU-Systems/TensorRT-LLM.md].

### 5.4 NVIDIA Dynamo
- **Role** — the *orchestration* layer above the engines: it does not replace
  vLLM/SGLang/TRT-LLM; it turns them into a coordinated multi-node system
  (KV-aware routing, disaggregation, multi-tier KV, scaling)
  [F: Dynamo README, fetched 2026-08-25].
- **TP** → delegated to the backend engine (NCCL) [I].
- **PP** → delegated to the engine [I].
- **KV transfer** → **KVBM (KV Block Manager)** routes prefill outputs to
  decode workers **using NIXL underneath** (KVBM: vLLM ✅, TRT-LLM ✅,
  SGLang 🚧) [F: Dynamo README capability table].
- **EP** → backend-engine dependent [I].
- **Data movement** → NIXL + KVBM + multi-tier KV caching; "Dynamo orchestrates
  inference workloads, coordinating vLLM, SGLang, Mistral.rs, TensorRT-LLM, and
  other serving backends" [F: DDN/NVIDIA materials on NIXL+Dynamo].

### 5.5 llm-d
- **Role** — distributed inference platform (vLLM + Kubernetes) for production;
  open (Red Hat/IBM/Google et al.) [F: llm-d GitHub, fetched 2026-08-25].
- **TP** → vLLM/NCCL underneath [I].
- **KV transfer** → vLLM Offloading Connector + **FS backend** (KV blocks to
  shared storage, async, parallel; GDS + NIXL backend integration on the
  roadmap) [F: llm-d blog "Native KV Cache Offloading to Any Filesystem",
  fetched 2026-08-25]. **v0.5 (2026-02): "UCCL-based transport resilience"** —
  UCCL-P2P in production for KV transport [F: llm-d GitHub news].
- **EP** → wide-EP validated at ~3.1k tok/s per B200 decode GPU; up to 50k
  output tok/s on a 16×16 B200 P/D topology (project-reported benchmark)
  [F: llm-d v0.5 release notes — vendor/project-reported, not independent].
- **Data movement** → offloading connector + NIXL/GDS path (roadmap)
  [F: llm-d blog next-steps].

### 5.6 PyTorch (the substrate)
- `torch.distributed` process groups → NCCL backend on NVIDIA (the default);
  Gloo/mpi for CPU/HPC [F: PyTorch docs]. Every engine above inherits its TP
  collectives from this layer — which is why "engine TP → NCCL" is the repeated
  answer [I: engine docs + PyTorch docs].

## 6. Where each stream "lives" (the map the Central Question asks for)
```text
vLLM
 │
Tensor Parallel ────── NCCL
 │
Prefill/Decode ─────── NIXL
 │                       │
 │                       ├── UCX
 │                       └── UCCL
 │
MoE ────────────────── UCCL-EP / DeepEP
 │
 ▼
GPUDirect RDMA
 │
 ▼
InfiniBand / RoCE / EFA
```
Reading it: TP traffic is *collective, intra-layer* → NCCL; P/D traffic is
*asynchronous bulk KV* → NIXL, whose backend is fabric-dependent (UCX over
IB/RoCE; UCCL over EFA/multi-vendor; GDS when a tier is NVMe); MoE traffic is
*dynamic all-to-all* → EP-specialized libraries; all three converge on GDR over
the fabric. The layer doing the *actual byte movement* is always the bottom
(GDR + NIC + fabric) — the upper layers decide **what, from where, to where, and
with what choreography** ([15 §4](15-nccl-vs-nixl-vs-uccl.md)).

## Key Takeaways
1. Three streams, three branches, three cadences — no library owns all three;
   that's the design, not a gap.
2. Engine TP/PP = NCCL (inherited from torch.distributed or the engine's
   native path); the *interesting* per-engine differences are the KV and EP
   paths.
3. vLLM's NixlConnector, Dynamo's KVBM-over-NIXL, llm-d's offloading connector
   (+ UCCL transport in v0.5), SGLang's NIXL connector, TRT-LLM's NIXL
   executor: the KV-movement answer is converging on NIXL + backends.
4. EP: DeepEP (NVIDIA-first, NCCL Gin) vs UCCL-EP (portable, EFA/AMD) — fleet
   decides.
5. "Which layer moves the bytes?" — always GDR+NIC+fabric; the upper layers are
   choreography.

## Related
[08 NIXL for KV-Cache Transfer](08-nixl-kv-cache-transfer.md) ·
[14 MoE Communication](14-moe-communication.md) ·
[15 NCCL vs NIXL vs UCCL](15-nccl-vs-nixl-vs-uccl.md) ·
`../Distributed-Inference/Overview.md` · `../Distributed-Inference/NVIDIA-Dynamo.md`

## References
- vLLM NixlConnector guide — https://docs.vllm.ai/en/stable/features/nixl_connector_usage/ (fetched 2026-08-25) [F]
- Dynamo README (KVBM table) — https://github.com/ai-dynamo/dynamo (fetched 2026-08-25) [F]
- llm-d GitHub + v0.5 notes + FS-backend blog (fetched 2026-08-25) [F]
- NVIDIA developer blog NIXL (framework list incl. SGLang/TRT-LLM/Ray/LMCache) [F]
- `../GPU-Systems/{vLLM,SGLang,TensorRT-LLM}.md`, `../Distributed-Inference/*` (internal)
