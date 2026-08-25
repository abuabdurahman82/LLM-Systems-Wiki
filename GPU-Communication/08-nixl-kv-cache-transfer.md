# NIXL for KV-Cache Transfer
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
In prefill/decode disaggregation, the KV cache is the **only payload that crosses
the wire between prefill and decode workers** — and it is big, it moves once per
request, and its transfer time directly adds to time-to-first-token (TTFT).
NIXL is the transport layer for exactly this handoff (UCX/UCCL/GDS underneath).
This page: the size math, the latency budget, the stack, and why it beats
"just use NCCL Send/Recv".

## 1. The disaggregation architecture
```text
                       Load Balancer
                            │
                  ┌─────────┴─────────┐
                  │                   │
                  ▼                   ▼
          Prefill Cluster        Decode Cluster
          GPU GPU GPU            GPU GPU GPU
                  │                   ▲
                  │                   │
                  └──── KV Cache ─────┘
                          │
                       NIXL / UCCL
```
- **Prefill**: compute-bound — runs the long prompt through attention, produces
  the full KV.
- **Decode**: memory-bound — generates one token at a time, streaming.
- **The KV handoff**: after prefill, the request's KV (up to gigabytes) must be
  in the decode worker's HBM before its first generated token.
- **TTFT** (time to first token) = prefill time + KV-transfer time + queueing.
  **ITL** (inter-token latency) is unaffected by the transfer *if* it finishes
  before decode starts — which is why the transfer must overlap with prefill
  completion and the decode warmup.
- **KV-cache size** — canonical 8B-GQA model: 128 KiB/token, 4.0 GiB at 32k
  context, 122.07 GiB at 1M context [E: 2·L·H_kv·d_h·b formula in
  01-why-communication-matters.md]. 70B-class GQA (L=80, 8 KV heads): 320
  KiB/token → 1.25 GiB at 4k context [E: 1280 MiB].
- **Tail latency**: a slow KV transfer for one request becomes that request's
  p99 TTFT; asynchronous + overlapped transfers are what keep p99 close to p50.

## 2. Worked example: how much KV moves, how long does it take
Canonical request: 8B GQA model, 32k prompt, KV = 4.0 GiB [E].

| Link | Time to move 4.0 GiB | Notes |
|---|---|---|
| NVLink ~900 GB/s | **4.77 ms** [E] | intra-node P/D on one box |
| 400 Gb/s IB/RoCE (50 GB/s) | **85.9 ms** [E] | consistent with `../GPU-Systems/Prefill-Decode-Disaggregation.md` (0.5 GiB → ~10.7 ms over the same 50 GB/s) |
| 200 Gb/s | 171.8 ms [E] | |
| 100 GbE (12.5 GB/s) | 343.6 ms [E] | same scale as its 16 GiB → ~344 ms over 50 GB/s [E] |
| 25 GbE | 1374.4 ms [E] | ~1.4 s — now a visible TTFT tax |
| 10 GbE | 3436 ms [E] | 3.4 s — P/D disaggregation loses its point |

The 4k-context 70B-class case (1.25 GiB) at 400 Gb/s: ~27 ms [E: 1.25 GiB / 50
GB/s]. The takeaway shape: **KV transfer time = KV bytes ÷ effective link
bandwidth**, and effective bandwidth is 60–80% of line rate on a healthy RDMA
fabric [I: typical GDR measurements]. With a cache-hit ratio h (fraction of the
the prompt already resident on the decode side), only (1−h) of the KV moves: at
h=0.9 over 100 GbE, 4.0 GiB → 0.4 GiB → 34.4 ms [E: 0.4 GiB ÷ 12.5 GB/s;
`../GPU-Systems/Prefill-Decode-Disaggregation.md` ships 36.1 ms under its
~effective-bandwidth convention — same shape, slightly different clock].
economic argument for **KV-aware routing**: route to the worker with the most
cached prefix and you buy back (1−h) × transfer time.

## 3. The stack, layer by layer
```text
vLLM / SGLang / Dynamo application (KV connector / KVBM)
      │
      ▼
NIXL agent (buffer lists: prefill HBM KV blocks → decode HBM KV blocks)
      │
      ├── UCX backend        (RDMA/GPUDirect over IB/RoCE; shared memory intra-node)
      ├── UCCL backend       (P2P with multipathing/congestion control; EFA via libfabric)
      └── GDS backend        (when a tier is NVMe: storage↔HBM)
      │
      ▼
GPUDirect RDMA (NIC↔HBM, no host bounce)
      │
      ▼
InfiniBand / RoCE / EFA
```
- **vLLM**: `NixlConnector` in `--kv-transfer-config` (producer/consumer roles,
  optional `backends: ["LIBFABRIC"]`, `bidirectional_kv_xfer` for multi-turn,
  GB-series multi-instance via VMM registration; heterogeneous KV layout is
  experimental) [F: docs.vllm.ai NixlConnector guide, fetched 2026-08-25].
- **Dynamo**: KVBM routes prefill outputs to decode workers; NIXL underneath
  [F: Dynamo README capability table].
- **SGLang / TensorRT-LLM / LMCache / llm-d**: NIXL-backed KV paths; llm-d's
  FS backend adds storage offloading with NIXL/GDS integration on its roadmap
  [F: llm-d blog, fetched 2026-08-25].
- **llm-d v0.5 (2026-02)**: "UCCL-based transport resilience" — the UCCL P2P
  backend inside a production P/D deployment
  [F: llm-d GitHub news, fetched 2026-08-25].

## 4. Asynchrony & overlap
```text
BAD (synchronous):
prefill ██████████░░
KV xfer           ████████
decode start                ●
TTFT = prefill + xfer

BETTER (asynchronous, NIXL):
prefill ██████████░░
KV xfer        ████████          (starts as blocks complete; GDR, async post)
decode warmup    ░░░
decode start        ●            (KV ready ≈ prefill end, if link ≥ ~8× prefill throughput)
TTFT ≈ prefill + ε
```
- NIXL's `post` is non-blocking; vLLM/LMCache issue per-block transfers as KV
  blocks finish, poll/notify on completion
  [F: NIXL BackendGuide; vLLM docs "fully asynchronous send/receive"].
- Overlap math: transfer of 4.0 GiB at 50 GB/s takes 85.9 ms [E]; prefill of
  32k tokens on an H100-class box is on the order of ~0.5–1 s [I] — the transfer
  fits *inside* the prefill window by ~10×, so with enough in-flight blocks TTFT
  ≈ prefill time. The budget breaks when (a) the link is 10× slower, or
  (b) the context is 1M (122.07 GiB [E] → 2.44 s at 50 GB/s: no longer hidden
  under prefill).
- Compute/communication overlap is the general principle: see
  [16 Performance Benchmarking](16-performance-benchmarking.md) § overlap.

## 5. Why not "NCCL Send/Recv" for KV transfer?
NCCL *can* do P2P Send/Recv — but NIXL wins the fit for four reasons:
1. **Heterogeneous endpoints** — NCCL's P2P is GPU↔GPU; KV offloading needs
   HBM↔NVMe↔DRAM↔object-store (NIXL's mem-type model) [F: NIXL BackendGuide].
2. **Dynamic peers** — NCCL comms are built at init for a fixed rank set; NIXL
   agents connect on demand with metadata exchange (ETCD), fit to elastic P/D
   pools [F: NIXL BackendGuide].
3. **One-sided, notification-driven** — the decode side's compute stays idle
   until notified; NCCL Send/Recv ties both ends to a stream
   [I: API-shape argument].
4. **Ecosystem integration** — vLLM/Dynamo/LMCache connectors are NIXL-native;
   using raw NCCL means writing the KV block bookkeeping yourself
   [F: vLLM docs; Dynamo README].
(Where NCCL still owns the job: in-layer TP collectives and PP Send/Recv — the
two coexist in one serving stack, see [15](15-nccl-vs-nixl-vs-uccl.md).)

## 6. Benchmarking KV transfer (pointers)
- **NIXLBench** — NIXL's official microbenchmark (latency/bandwidth across
  backends); KVBench for KV-shaped workloads — [19 Practical Labs](19-practical-labs.md).
- **Application-level** — TTFT/ITL of a disaggregated engine with the connector
  enabled vs disabled: the micro vs app benchmark split of
  [16 Performance Benchmarking](16-performance-benchmarking.md).
- **KV-specific metric that matters**: transfer *setup* overhead
  (registration + metadata + first-transfer latency) amortized over the
  requests a worker serves — dominant when contexts are short.

## Key Takeaways
1. KV transfer time = KV bytes ÷ effective bandwidth: 4.0 GiB @ 400 Gb/s ≈ 86 ms
   [E] — the number every P/D design should know cold.
2. KV-aware routing buys back (1−h) × transfer time (h=0.9 @100 GbE: 343.6 →
   34.4 ms [E]) — routing is a communication optimization.
3. Asynchrony + block-level pipelining hides the transfer under prefill when the
   link is ≥ ~8× the prefill throughput.
4. NIXL is the fit for KV because of heterogeneous endpoints, dynamic peers,
   one-sided semantics, and engine-native connectors — not because NCCL's P2P is
   broken.
5. 1M-context KV (122.07 GiB [E]) is the regime where tiered storage (GDS)
   beats fabric bandwidth.

## Related
[07 NIXL Deep Dive](07-nixl-deep-dive.md) ·
[13 Distributed Inference Communication](13-distributed-inference-communication.md) ·
`../GPU-Systems/Prefill-Decode-Disaggregation.md` ·
`../Distributed-Inference/Overview.md`

## References
- vLLM NixlConnector usage guide — https://docs.vllm.ai/en/stable/features/nixl_connector_usage/ (fetched 2026-08-25) [F]
- Dynamo README (KVBM, backends) — https://github.com/ai-dynamo/dynamo [F]
- llm-d v0.5 release notes (UCCL transport resilience) — https://github.com/llm-d/llm-d [F]
- NIXL BackendGuide + KVBench docs [F]
- `../GPU-Systems/Prefill-Decode-Disaggregation.md` (0.5 GiB → ~10.7 ms @ 50 GB/s;
  16 GiB → ~344 ms; h=0.9 → 36.1 ms under its own convention; internal)
