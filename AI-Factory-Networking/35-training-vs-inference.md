# Distributed Training vs Inference Networking
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: research-workloads training/inference analysis, section [E] constants bank (KV-cache rows); fetched 2026-08-25.

## 30-Second Explanation
Training and inference place **opposite demands** on the fabric, and conflating them is a
common design error. **Distributed training** is a stream of **synchronized collectives**
(AllReduce / AllGather / ReduceScatter) that are **repeated, deterministic, and
bandwidth-bound for large messages** (latency-bound only for small ones); a step is
ms-scale and tolerant of a few µs of latency because compute overlaps collectives —
**tail bandwidth near the `0.95 × link` ceiling (the ring's busbw saturates AT the link rate,
normalized by the `2(n-1)/n` wire factor) is the goal**. **Distributed inference**
splits into **prefill** (compute-bound; the model's tensor-parallel collectives dominate)
and **decode** (memory/KV-bound; short, latency-critical per-request traffic). The
distinct inference cost is **KV-cache movement** — in disaggregated serving, prefill
workers must ship the KV cache to decode workers **within one decode step** (e.g. Llama-3‑70B
GQA **320 KiB/token**, **1.25 GiB** for a 4096-token sequence, **26.8 ms** to transfer over
50 GB/s [E]). The requirements table at the bottom sums up why a *training-optimized* fabric
and an *inference-optimized* one can differ. See the collective primitives in
[./33-collective-communication.md](./33-collective-communication.md) and the MoE/AllToAll
flavor in [./34-moe-all-to-all.md](./34-moe-all-to-all.md).

## Distributed training — synchronized collectives
Training is one AllReduce (or its ZeRO AllGather/ReduceScatter relatives) per step,
repeated identically tens of thousands of times [I]. Properties:
- **Synchronized**: every rank blocks on the same collective; the slowest rank gates the
  step → **tail bandwidth** (worst-case path) decides JCT, not mean [I].
- **Repeated & deterministic**: the identical traffic pattern recurs every step, so
  routing/hash imbalance compounds rather than averages out [I].
- **Bandwidth-bound for large messages**: the gradient/parameter volumes are
  multi-MB-to-GB; time ≈ `2(n-1)/n × M / B` (./33), so **link bandwidth** dominates [E].
- **Latency-sensitive for small messages**: TP all-reduces, pipeline activations, and
  small ZeRO chunks are latency-bound (`α` matters). Small + frequent = the tail-latency
  regime [I].

```text
  Training step (data parallel), repeated n steps:
     forward ─► AllReduce(grads, M) ─► optimizer ─► next step
     The fabric carries the SAME large AllReduce over and over: bandwidth-bound, steady,
     deterministic, tail-gated.
```

## Distributed inference — prefill vs decode
Inference is a **latency-critical, user-facing** workload split into two regimes [F/A:
prefill/decode standard (see also [Prefill-Decode-Disaggregation.md](../Inference/Prefill-Decode-Disaggregation.md))]:

| Regime | Domain | Network signature |
|---|---|---|
| **Prefill** | compute-bound (large batch, long sequence, matmul-heavy) | **Tensor-parallel collective traffic** (model shards must reduce across TP ranks); large but amortized |
| **Decode** | memory/KV-bound (one token at a time; reads KV + weights) | **short requests**, TP/EP traffic, latency-critical |

Because decode is *one token at a time*, per-request messages are small and the binding
constraint is **latency and effective bandwidth under concurrency**, not raw bulk
throughput [I]. **Expert-parallel (EP) traffic** (see ./34) appears when an
MoE-inference model routes tokens to expert ranks — an all-to-all dispatch/combine even on
the decode path [I].

## KV-cache transfer — disaggregated serving
Modern serving **disaggregates prefill and decode**: prefill workers compute the KV cache;
the **KV cache must be shipped to decode workers** before generation continues.
KV bytes per token = `2 × L × H_kv × D_h × bytes` (L=layers, H_kv=KV heads, D_h=head dim)
[E]. Real Llama-3‑70B uses **GQA (8 KV heads × 128)**, giving [F: Sitepoint/Spheron; E]:

```
  Llama-3-70B GQA  KV/token = 2·80·8·128·2 B = 327,680 B = 320.0 KiB   [E bank]
  Llama-3-70B MHA  KV/token = 2·80·8192·2 B  = 2,621,440 B = 2.50 MiB  [E bank, contrast]
  4096-token seq   GQA = 1.25 GiB ;  MHA = 10.00 GiB                    [E bank]
  GQA 4096-tok over 400Gb/s (50 GB/s) = 1.25 GiB / 50 GB/s = 26.8 ms    [E bank]
```

**Budget rule [A/I]:** the KV transfer is a **one-time, per-request cost** (not per token), so
it should be hidden under the request's first decode steps (overlap the transfer with the
decode worker's warm-up / previous-token generation) — the budget is `KV_transfer ≲` a few
decode steps, not literally one. A 26.8 ms KV ship, against a ~10–30 ms decode step, is a
non-trivial slice of the request's first few steps — at large batch/sequence or over slower
uplinks it becomes the serialization bottleneck; the rule is *KV_transfer < a few decode steps*
[A model, widely accepted].

```text
  Disaggregated serving (prefill → decode):
   [Prefill worker]  compute K/V for the request
        │  KV-cache transfer over the fabric (GQA 1.25 GiB @ 4096 tok)
        ▼
   [Decode worker]   generate tokens, reading the shipped KV each step
        │
        └─ each decode step is latency-critical (user-perceivable ms), NOT ms-scale-tolerant
```

## Request latency sensitivity
The single biggest difference in *engineering stakes* [I]:
- **Training step** is ms-scale and *internal* — a few µs of extra collectives latency is
  amortized over a ≥ms step; nobody sits watching.
- **Inference latency is user-perceivable** — a decode token takes ~tens of ms; every
  added ms is perceived, and tail requests (under load) are what users feel. So inference
  cares about **p99 tail latency under concurrency**, while training cares about
  **sustained bus bandwidth + tail bandwidth**.

## Requirements comparison — and what it means for fabric choice
| Requirement | Distributed training | Distributed inference |
|---|---|---|
| Primary pattern | AllReduce / AllGather / ReduceScatter (steady, reducible) | Prefill: TP collectives; Decode: short requests; KV transfer (P2P/one-to-one) |
| Message sizes | large (bandwidth-bound) + small (latency-bound) | short per-token; KV = MB–GB transfers |
| Latency tolerance | high (step-level, overlaps compute) | **low** (user-perceivable ms; p99 matters) |
| Batch contiguity | contiguous, fully-synchronized | concurrent, many independent requests |
| Fabric goal | busbw near `0.95 × link` [E] | low tail latency + bandwidth under concurrency; KV ship speed |
| Sensitivity to incast/skew | moderate (AllReduce is spread) | **high** (EP all-to-all in ./34; KV to hot decode worker) |
| Satellite feature | AllToAll for MoE/context (./34) | KV cache movement + EP all-to-all |

**Fabric-choice implication [I/A]:** a training-oriented fabric optimizes *collective
busbw* and *rail* layout (./42); an inference-oriented one must additionally optimize
*point-to-point KV transport latency*, *all-to-all* (MoE inference), and *tail under
concurrency*. The same InfiniBand/RoCE/UET transport (./31) can host both, but tuning
(CC aggressiveness, rail allocation, oversubscription, buffer headroom) differs — and
UET's unordered spraying + receiver-credit incast control (./32) matter most on the
inference/AllToAll side [I].

## Lab — hand-calculable check [E]
```
# KV-cache budget: does it fit the decode step?
kv = 2*80*8*128*2        # 327680 B/token (Llama-3-70B GQA, bank row)
seq = 4096               # tokens
bytes_total = kv*seq/2**30        # ~1.25 GiB (bank: 1.25 GiB)
t = bytes_total/ (50e9/2**30)     # over 50 GB/s → ~26.8 ms (bank: 26.8 ms)
print(bytes_total, t)             # expect (1.25, 26.8)
```
Then on an inference cluster measure the **decode step time** vs KV transfer; if
`t > decode_step`, KV ship is the bottleneck *by this budget rule* [A].

> **Where this fits.** Collective math: [./33-collective-communication.md](./33-collective-communication.md);
> MoE/AllToAll: [./34-moe-all-to-all.md](./34-moe-all-to-all.md); the software that moves
> these bytes: [./36-communication-libraries.md](./36-communication-libraries.md) and
> [../GPU-Communication/README.md](../GPU-Communication/README.md); disaggregated serving
> detail: [Prefill-Decode-Disaggregation.md](../Inference/Prefill-Decode-Disaggregation.md).

## Key Takeaways
1. **Training** is synchronized, repeated, deterministic collectives — bandwidth-bound for large messages (time ≈ `2(n-1)/n × M / B`), latency-bound for small ones; **tail bandwidth** near the `2(n-1)/n` lower bound is the goal. [E/I]
2. **Inference** splits into **prefill** (compute-bound; tensor-parallel collective traffic) and **decode** (memory/KV-bound; short, latency-critical per-request traffic). [F/A]
3. **KV-cache transfer is the distinct inference cost**: Llama-3-70B GQA = 320 KiB/token, 1.25 GiB @ 4096 tokens, **26.8 ms** over 50 GB/s — must ship within one decode step (budget rule `KV_transfer < decode_time`). [E/A]
4. Training steps are ms-scale and internal (a few µs is amortized); inference latency is **user-perceivable** — so decode cares about **p99 tail under concurrency**, training about sustained bus bandwidth. [I]
5. The same transport hosts both, but tuning differs (CC aggressiveness, rail allocation, oversubscription, buffer headroom); UET's spraying + receiver-credit incast control matter most on the inference/AllToAll side. [I]

## Related
- [33-collective-communication.md](./33-collective-communication.md) — the collective math behind training traffic.
- [34-moe-all-to-all.md](./34-moe-all-to-all.md) — MoE/AllToAll, including expert-parallel traffic on the decode path.
- [36-communication-libraries.md](./36-communication-libraries.md) — the software moving these bytes, incl. NIXL KV ships.
- [README.md](../GPU-Communication/README.md) — the GPU-side software map.
- [Prefill-Decode-Disaggregation.md](../Inference/Prefill-Decode-Disaggregation.md) — disaggregated serving detail.
- [55-cheat-sheet.md](./55-cheat-sheet.md) — quick reference across the section.

## References
- research-workloads training/inference analysis [I].
- Sitepoint/Spheron — Llama-3-70B GQA/MHA KV-cache figures [F].
- [E] AFN constants bank — KV-cache rows (320 KiB/token GQA, 2.5 MiB MHA, 1.25/10 GiB @ 4096, 26.8 ms over 50 GB/s).
