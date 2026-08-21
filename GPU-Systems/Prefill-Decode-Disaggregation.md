# Prefill/Decode Disaggregation (P/D Split)
`LAST_UPDATED: 2026-08-21 · Status: core page` · Builds on `../Inference/
Prefill-Decode-Disaggregation.md` (the existing page) and the router work in
`Load-Balancing.md`; the system designs are in `Distributed-Architectures.md` and
`Case-Studies.md`.

## 30-Second Explanation
Prefill and decode are **opposite workloads** — prefill is compute-bound (large GEMMs,
Tensor Cores), decode is bandwidth-bound (streaming weights+KV). Cramming both onto the
same GPUs makes each steal the other's resource: a big prefill stalls decodes (TTFT
spikes), and a wall of decodes starves prefills. **Disaggregation** runs them on
**separate GPU pools** — a compute-optimized prefill cluster and a bandwidth-optimized
decode cluster — and moves the freshly-computed **KV cache** between them over the
fabric. The price is the **KV transfer**, which must be fast enough that it doesn't
eat the latency you saved.

```
                 ┌─────────────────────────┐
   requests  ──► │  ROUTER / SCHEDULER     │  (balance remaining work,
                 └─────────────┬───────────┘   prefix-aware; Load-Balancing.md)
                               │
        ┌──────────────────────┴──────────────────────┐
        ▼                                             ▼
┌───────────────────┐  KV transfer (RDMA/   ┌───────────────────┐
│  PREFILL CLUSTER  │  NVLink/NVL72)        │  DECODE CLUSTER   │
│  compute-optimized│ ─────────────────────► │  bandwidth-optimized│
│  big GEMMs, FA    │   (GPUDirect RDMA)    │  stream weights+KV │
│  (Tensor Cores)   │                       │  (HBM BW bound)    │
└───────────────────┘                       └───────────────────┘
```

## What
A **P/D-disaggregated** serving system has:
1. **Prefill pool** — GPUs dedicated to processing prompts (compute-bound).
2. **Decode pool** — GPUs dedicated to generating tokens (bandwidth-bound).
3. **KV transfer path** — moves the prefill's KV cache from prefill GPU to the
   decode GPU(s) that will continue the sequence.
4. **A coordinator** — assigns requests, places KV, routes decodes, handles failures.

## Why
- **Resource isolation:** prefill GPUs stay at high Tensor-Core util; decode GPUs stay
  at high HBM-BW util. Neither starves the other.
- **Independent scaling:** add prefill capacity for TTFT SLOs; add decode capacity for
  throughput/ITL SLOs — separately.
- **Different hardware fits:** prefill wants peak FLOPS (B200/GB200); decode wants
  bandwidth + HBM capacity (H200/B200) — you can buy different SKUs per pool.
- **Better KV placement:** the decode pool's KV is managed purely for decode (paged,
  quantized, evicted) without prefill's churn.

## How — the KV transfer (the crux)
After prefill, the decode GPU needs the full KV cache of the prompt. Its size:
```
KV bytes = 2 · L · B · h_kv · d_h · S · b        (per request)
```
For a 27B-class model (L=32, GQA h_kv=8, d_h=128, b=2), that is **128 KiB/token**, so:
- S=4096 → **0.5 GiB** · S=16k → **2.0 GiB** · S=128k → **16.0 GiB**. [E: arithmetic]
(If the model were MHA with h_kv=64 instead of GQA-8, these are 8× larger — which is
exactly why GQA exists, `../KV-Cache/README.md`.)

The transfer path and its bandwidths [F: `../Hardware/README.md`]:
| Path | Bandwidth | When |
|---|---|---|
| Shared HBM (same GPU) | HBM (~3.35 TB/s) | no transfer (same device) |
| NVLink intra-node | ~900 GB/s | decode GPU in same node |
| NVL72 | NVLink-domain | same 72-GPU domain |
| PCIe | ~64 GB/s | host bounce (slow) |
| RDMA (IB/RoCE) | ~50 GB/s/link × N | cross-node (GPUDirect) |

**Transfer time ≈ KV_bytes / effective_BW.** At S=4096 (0.5 GiB) over 50 GB/s RDMA →
~10.7 ms; over 900 GB/s NVLink → ~0.6 ms. At S=128k (16 GiB) over 50 GB/s RDMA →
~344 ms; over NVLink → ~19 ms — **at long context the transfer becomes a real latency
component**, which is why long-context P/D needs NVLink/NVL72, quantized (FP8) KV to
halve the bytes, or hierarchical KV placement. [E: arithmetic]

**GPUDirect RDMA** moves the KV straight from the prefill GPU's HBM to the decode
GPU's HBM, bypassing host memory — essential for low-latency transfer [F: NVIDIA].

## When
- **High-concurrency SLOs** where prefill and decode interfere (chat, agentic).
- **Long-context** (where KV transfer is large and you have NVLink/NVL72 to make it
  cheap).
- **Heterogeneous hardware** (different SKUs per phase).
- **Not** when: single-GPU, low concurrency, or the fabric is too slow for the KV
  transfer (a PCIe/RoCE-only cluster at long context → transfer-bound, don't split).

## Scheduling, routing, and cache placement
- **KV-aware routing:** send a request to a decode GPU that already holds (or is
  closest to) its prefix KV → smaller transfer (`Load-Balancing.md`).
- **Hierarchical KV:** keep hot prefixes in the decode pool's local cache; only transfer
  the delta. (Mooncake's KVCache-centric design [F: arXiv:2407.00079].)
- **Chunked prefill + P/D:** prefill in chunks so decodes on the same (or neighbor)
  GPUs aren't fully stalled; but true P/D isolates them anyway.
- **Failure handling:** if a decode GPU dies, its in-flight KV must be re-routed
  (re-transfer from the prefill pool or a replica).

## Failure modes
- **Transfer-bound:** fabric too slow for the KV size → P/D is slower than co-located.
  (Fix: NVLink/NVL72, hierarchical KV, quantize KV to FP8.)
- **KV re-compute on decode failure:** re-running prefill is expensive; need KV
  redundancy or fast re-transfer.
- **Load imbalance between pools:** prefill pool over-subscribed (TTFT SLO) while
  decode pool idles (or vice versa). (Fix: independent autoscaling, `Load-Balancing.md`.)
- **Prefix cache fragmentation:** the shared prefix is on the prefill pool but the
  decode pool is cold → transfer the full prefix every time. (Fix: pin shared prefixes
  on the decode side.)

## Representative systems
- **DistServe** — disaggregates prefill/decode for goodput-optimized serving; shows the
  two phases have different SLOs and should be placed separately [F: arXiv:2401.09670,
  OSDI'24].
- **Mooncake** (Kimi) — a **KVCache-centric** disaggregated architecture; the KV cache is
  the first-class citizen, with a pooled DRAM+HBM KV layer and KV-aware routing
  [F: arXiv:2407.00079, FAST'25].
- **Splitwise** — phase-splitting (prefill vs decode) with phase-aware bin-packing
  [F: arXiv:2311.18677, ISCA'24].
- **NVIDIA Dynamo** — orchestration layer for disaggregated serving over TRT-LLM
  [F: repo].
- **vLLM / SGLang** — both now expose **disaggregated serving** modes (prefill/decode
  separation) in addition to co-located serving.
- **llm-d** — K8s-native disaggregated serving [F: repo].

## Hardware impact
- **Prefill pool:** Tensor-Core util high; HBM BW moderate.
- **Decode pool:** HBM BW util high; Tensor Cores moderate.
- **Fabric:** the KV transfer is a **bulk RDMA** operation; it competes with any
  AllReduce/AllToAll on the same links → plan the fabric budget for KV.

## Inference impact
- **TTFT:** isolated prefill → no decode interference → lower, more predictable TTFT.
- **ITL:** isolated decode → no prefill stalls → lower P99 ITL.
- **Throughput:** independent scaling → higher goodput at SLO.
- **Cost:** you can right-size each pool (cheaper decode hardware) and buy the right
  SKU per phase.

## How to measure it
- **TTFT/ITL P99** co-located vs disaggregated (same load) — the P99 delta is the win.
- **KV transfer time** (log the RDMA completion time vs the hand-computed
  `KV_bytes/BW`).
- **Prefill/decode GPU util** separately (should be high in their respective roof).
- **Fabric util** during KV transfer (is it stealing from AllReduce?).
- **Goodput at SLO** before/after.

## Related
`Load-Balancing.md` · `Distributed-Architectures.md` · `Multi-Node.md` ·
`Scale-Up-vs-Scale-Out.md` · `NCCL.md` · `../Inference/Prefill-Decode-Disaggregation.md` ·
`../Inference/Roofline.md` · `../KV-Cache/README.md` · `Case-Studies.md` (CASE 9).

## Key Takeaways
1. **Prefill (compute) and decode (bandwidth) are opposite workloads** — isolate them.
2. **The KV transfer is the price**; its time ≈ `KV_bytes / fabric_BW`. At long context,
   it dominates → need NVLink/NVL72 or hierarchical KV.
3. **Route KV-aware** (decode GPU already has the prefix) to shrink the transfer.
4. **DistServe/Mooncake/Splitwise** are the reference designs; measure before adopting.
