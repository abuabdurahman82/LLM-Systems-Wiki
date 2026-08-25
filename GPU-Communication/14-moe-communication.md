# MoE Communication
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
Mixture-of-Experts changes network design at the root: the communication
pattern is no longer a *fixed schedule of symmetric collectives* but a
**per-token, per-batch, asymmetric all-to-all** whose sizes the router decides
at runtime. Dense models move *parameters/activations* on a known choreography;
MoE moves *tokens* to *wherever their experts live*. This page: why, the
dispatch/combine pipeline, the implications for fabric design, and the two
libraries built specifically for it (DeepEP, UCCL-EP).

## 1. Dense vs MoE communication
```text
Dense model
→ mostly predictable collectives
   (AllReduce per TP layer; AllGather/ReduceScatter for ZeRO; Send/Recv for PP)

MoE
→ dynamic token → expert traffic
→ All-to-All
→ potential hotspots
→ variable message sizes
```
The structural differences [../GPU-Systems/MoE-Expert-Parallelism.md; I]:
1. **Destinations are data-dependent** — the router's top-k choices decide each
   token's GPUs; the pattern changes every forward pass.
2. **Sizes are non-uniform** — expert load is skewed (some experts hot, some
   cold); the all-to-all's per-destination sizes are unbalanced.
3. **Two all-to-alls per MoE layer** — **dispatch** (tokens → experts) and
   **combine** (expert outputs → tokens), back-to-back.
4. **On the critical path every micro-batch** — not "per step" like DP
   gradients; EP traffic repeats per layer × per micro-batch.

## 2. The dispatch/combine pipeline
```text
                  Tokens
                    │
                   Router
                    │
       ┌────────────┼────────────┐
       ▼            ▼            ▼
    Expert 1     Expert 7     Expert 23
      GPU0          GPU4          GPU7
```
```text
Tokens
   │
Dispatch
   │
All-to-All / Expert routing     (tokens physically move to the GPU holding their expert)
   │
Experts compute                 (small GEMMs, expert-local)
   │
Combine
   │
All-to-All (return)             (expert outputs move back to the token owners)
   │
Output
```
Worked sizes [E]: with `T` tokens per rank, hidden dim `d`, top-k experts, FP8
dispatch: dispatch moves ~T×d bytes total, distributed across N−1 peers (≈
T×d×(N−1)/N per link in the balanced case; real traffic is unbalanced). For
T=8192, d=7168, FP8: ~58.7 MB per rank in the balanced case [E: 8192×7168 B];
combine is the same order in BF16 (×2) ≈ 117 MB [E]. These are *per all-to-all*
— and they happen every MoE layer.

## 3. Why expert parallel needs specialized communication
- **GPU-driven communication** — dispatch/combine are on the latency-critical
  path of every token; a CPU proxy round-trip per all-to-all would dominate.
  Both DeepEP and UCCL-EP post the RDMA work *from the GPU* (IBGDA-class)
  [F: DeepEP V2 NCCL-Gin backend; UCCL-EP "IBGDA-level performance"].
- **IBGDA where applicable** — InfiniBand GPU-Direct Async: the GPU's kernel
  posts work directly to the NIC queue pair and polls completions — zero CPU on
  the data path. This is the DeepEP-V1 (NVSHMEM) and V2 (NCCL Gin) substrate,
  and UCCL-EP's target performance [I: IBGDA model; F: DeepEP README].
- **CPU-proxy approaches** — the portable fallback (e.g. plain NCCL
  send/recv, or UCCL-EP on NICs without IBGDA-class support): correct but
  higher-latency; the floor for heterogeneous fleets [10 §3.3].
- **Dynamic traffic** — no static schedule; the library must handle arbitrary
  per-destination sizes every batch.
- **Non-uniform message sizes** — a hot expert receives more tokens; the
  all-to-all can't assume symmetry (unlike AllReduce).
- **Load imbalance** — the classic MoE pathologies:
  - *token-level* (router skew) → one NIC/GPU oversubscribed;
  - *sequence-level* (some requests hit hot experts) → tail latency;
  - mitigations: auxiliary loss / capacity factor at the *model* layer, and
    flow control / buffering at the *communication* layer
    [../GPU-Systems/MoE-Expert-Parallelism.md; I].
- **Dispatch + combine symmetry** — both all-to-alls must complete before the
  next layer's compute; a slow dispatch serializes the whole layer.

## 4. Network implications
- **NIC bandwidth** — EP traffic is bandwidth-hungry *and* latency-sensitive;
  rail-optimized topologies + one-NIC-per-GPU keep dispatch local to the rail
  ([03 §3](03-gpu-network-architecture.md)).
- **Congestion & hotspots** — skewed traffic concentrates on a few NICs; this is
  exactly the "single-path-of-congestion" UCCL-Tran's 256-path spraying targets
  ([09 §3](09-uccl-deep-dive.md)) — and why flow control matters more for EP
  than for symmetric collectives.
- **Transport choice** — IBGDA (IB) is the performance ceiling; EFA (AWS) is
  covered by UCCL-EP / NCCL-GDA (2.31); plain NCCL send/recv is the portable
  floor [06; 10 §3.4].
- **GPU-driven networking** — the modern EP design trend: the communication is
  a *kernel* that talks to the NIC directly, not a library call that a host
  thread proxies. This is the "device-initiated" end of NCCL's 2.28+/2.31
  Device API / GIN / CFT line ([04 §7](04-nccl-deep-dive.md)) [I: synthesis].

## 5. DeepEP vs UCCL-EP (the two EP specialists)
| | DeepEP | UCCL-EP |
|---|---|---|
| Backend | **NCCL Gin** (V2; header-only, reuses NCCL comms); V1 was NVSHMEM | GPU-driven across **NVIDIA/Broadcom/EFA** NICs |
| GPUs | NVIDIA | NVIDIA **+ AMD** |
| API | its own (V2 `ElasticBuffer`) | **DeepEP-compatible** |
| SM cost | V3-like training 24 → 4–6 SMs; 0-SM modes for PP/CP/Engram | IBGDA-level [F: both READMEs, fetched 2026-08-25] |
| Scale | up to **EP2048** | EP32 demonstrated on p5en (8×H200 + 16×200G EFA) [F] |
| Sweet spot | NVIDIA-first max performance | Heterogeneous fleets (mixed vendors, EFA) |
They are *substitutes at the EP branch* — pick by fleet
([10 §3.4](10-uccl-collective-p2p-ep.md), [18](18-architecture-decision-guide.md)).
(Also new: NVIDIA's own **NCCL EP** extension — `libnccl_ep.so`, dispatch/combine
on LSA+GIN, CUDA-Graph-compatible handles — adds a third, NCCL-native option
[04 §7; F: NCCL EP release notes].)

## 6. Practical architecture: a large MoE cluster
```text
            MoE Router
                │
         Token Dispatch
                │
            UCCL-EP / DeepEP
                │
      ┌─────────┼──────────┐
      ▼         ▼          ▼
    GPU0       GPU5       GPU13
   Expert A   Expert B    Expert C
```
Why EP communication is the hardest branch:
- It's the only branch where the *application* (the router) dictates the
  communication *and* the communication is *collective* — the two properties
  that usually don't coexist.
- The all-to-all is on the per-token critical path → latency budget is
  microseconds-to-hundreds-of-µs, where GDA/IBGDA vs proxy is a 5–10× factor
  [I].
- Imbalance is *model* behavior, not *fabric* failure — so you can't "fix" it
  with a better NIC alone; you need capacity factors + flow control + possibly
  expert replication [../GPU-Systems/MoE-Expert-Parallelism.md; I].
- It's where GPU-driven networking first became load-bearing in production
  (DeepEP on DeepSeek fleets; UCCL-EP on AWS EFA) — the proof that
  device-initiated communication is not a research toy [I].

## 7. Failure modes
- **Expert hotspot** — one GPU/NIC saturated; other ranks' all-to-all waits.
  Symptom: p99 latency >> p50, one rail at line rate, others idle
  [../GPU-Systems/MoE-Expert-Parallelism.md].
- **Wrong EP library for the fabric** — e.g. DeepEP (IBGDA) on a non-IB fabric
  → fall back to UCCL-EP (EFA) or CPU-proxy NCCL [10 §3.3; 18].
- **SM over-allocation** — the EP comm kernel grabs too many SMs and starves
  the expert GEMMs; DeepEP V2's analytical SM sizing + UCCL-EP's IBGDA
  (zero/few SM) exist to keep this under control [F: DeepEP README].
- **Buffer sizing** — DeepEP V2 "buffer size consumption is larger than V1";
  undersized buffers force fallbacks/aborts [F: DeepEP README notes].

## Key Takeaways
1. MoE comm = dynamic, asymmetric, per-token all-to-all (dispatch + combine) on
   the per-layer critical path — structurally unlike dense collectives.
2. The answer is **GPU-driven** (IBGDA/NCCL-Gin/UCCL-EP), not host-proxied,
   because the budget is microseconds.
3. Load imbalance is a *model* problem that the *communication layer* must
   absorb (buffering, flow control, capacity factors).
4. DeepEP (NVIDIA-first, NCCL Gin) vs UCCL-EP (portable, EFA/AMD) vs NCCL EP
   (native) — three options now; fleet + fabric decide.
5. EP is where "device-initiated networking" went from feature to
   load-bearing production path.

## Related
[10 UCCL Collective / P2P / EP](10-uccl-collective-p2p-ep.md) ·
[13 Distributed Inference Communication](13-distributed-inference-communication.md) ·
[18 Architecture Decision Guide](18-architecture-decision-guide.md) ·
`../GPU-Systems/MoE-Expert-Parallelism.md`

## References
- DeepEP README (V2, NCCL Gin, 0-SM modes, EP2048, V3-like 24→4–6 SM, buffer note,
  perf config) — https://github.com/deepseek-ai/DeepEP (fetched 2026-08-25) [F]
- UCCL README (UCCL-EP, p5en EP32, EFA/Broadcom/AMD) [F]
- NCCL EP release notes (libnccl_ep.so, LSA+GIN, CUDA-Graph handles) [F]
- `../GPU-Systems/MoE-Expert-Parallelism.md` (internal)
