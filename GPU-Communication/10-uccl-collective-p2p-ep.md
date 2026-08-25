# UCCL Collective / P2P / EP
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
This page is the "what each UCCL component actually does and when you'd pick it"
page. UCCL-Tran is a **drop-in NCCL/RCCL replacement** whose transport is
re-architected in software (256-path spraying, dual congestion control,
selective-repeat); UCCL-P2P is a **NIXL-style initiator/target engine** aimed at
800 Gbps-class NICs; UCCL-EP is a **DeepEP-compatible expert-parallel layer**
that runs on heterogeneous (NVIDIA+AMD) hardware at IBGDA-level performance
[F: uccl README + OSDI'26, fetched 2026-08-25]. All three keep the incumbent
*APIs* so apps don't change — UCCL changes what happens under the API.

## 1. UCCL-Tran (collectives)
**What:** the same collective API as NCCL/RCCL (`ncclAllReduce` & friends),
different engine.
**Why:** NCCL's network transports push big transfers over 1–few paths →
"single-path-of-congestion" in datacenter fabrics; UCCL-Tran sprays packets over
abundant paths in software [F: README high-level design].
**How (the four capabilities):**
- packet spraying with **up to 256 paths** (software, not relying on NIC/switch
  offloads);
- **latency-based CC** *and* **receiver-driven CC** (two complementary
  controllers);
- **selective repeat** loss recovery → usable on **lossy Ethernet** (public
  clouds, legacy NICs) instead of only PFC-tuned lossless fabrics;
- heterogeneous GPU/NIC support (NVIDIA/AMD GPUs; NVIDIA/Broadcom NICs on the
  RDMA path; EFA and ENA/VirtIO on dedicated sub-projects) [F: README].
**When:** your fabric is lossy or multi-vendor, you're on AMD, or you want
software-defined CC/multipathing; it is a *replacement*, so you switch the whole
CCL layer.
**Upstream-reported numbers (label: vendor/project benchmark, not independent):**
- 6× HGX (2 racks, 8×400G CX-7 RoCE, 8× H100): AllReduce up to **2.5×** NCCL
  [F: README].
- 2× AWS `g4dn.8xlarge` (1×50G ENA, T4): AllReduce up to **3.7×** NCCL
  [F: README].
These are the project's own measurements on its own targets (incl. a non-RDMA
setup) — treat as "the case it was designed for", and re-benchmark on *your*
fabric per [19 Practical Labs](19-practical-labs.md).
**NCCL/RCCL plugin model:** the integration point is the CCL API itself
(drop-in), plus NCCL's plugin ecosystem where relevant; the sub-projects
(`collective/rdma`, `collective/efa`, `collective/afxdp`) are the transport
flavors [F: README quick-start].

## 2. UCCL-P2P
**What:** NIXL-style **initiator → target** transfer APIs (register, exchange
metadata, post, poll/notify) — the P2P branch of the taxonomy
([01](01-why-communication-matters.md)).
**Why:** designed for the **next-gen 800 Gbps NIC generation** with
**multi-threaded transfer engines** — the shape of a KV/weight transfer engine,
not a collective [F: README].
**How:** RDMA data path + GPU IPC for intra-node; transports today: RDMA
(NVIDIA/Broadcom), **AWS EFA**, **GCP TCP-X**, **TCP** [F: README roadmap:
"Supporting RDMA (NVIDIA, Broadcom), AWS EFA, GCP TCPX, TCP"].
**When:** KV-cache transfer and RL weight transfer in heterogeneous
infrastructure; most commonly *through NIXL* (`src/plugins/uccl`), i.e. the app
talks to NIXL and UCCL is the backend
[07 NIXL Deep Dive §7](07-nixl-deep-dive.md). llm-d v0.5 uses UCCL-P2P directly
for KV-cache transport ("UCCL-based transport resilience") [F: llm-d blog].
**The complementarity point (the user's key example):**
```text
Application
    │
    ▼
   NIXL
    │
    ▼
UCCL P2P Backend
    │
    ├── RDMA
    ├── TCP
    ├── TCP-X
    └── EFA
```
NIXL defines *what* moves (inference data-movement abstraction, heterogeneous
memory); UCCL-P2P provides *how* (the transport implementation). **NIXL and
UCCL are complementary rather than competitors** — the same KV transfer can ride
UCX, UCCL, or GDS underneath one NIXL API [F: NIXL tree `src/plugins/uccl`;
NIXL release 0.9.0 "UCCL-P2P as an RDMA backend"].

## 3. UCCL-EP (expert parallel)
### 3.1 The MoE problem, restated
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
Token routing makes EP traffic structurally unlike dense-model AllReduce:
destinations are per-token, sizes are non-uniform, and the pattern changes every
batch [I: 02 §2.6]. The pipeline is:
```text
Tokens
   │
Dispatch
   │
All-to-All / Expert routing
   │
Experts compute
   │
Combine
   │
Output
```
### 3.2 Why specialized communication
- **Dynamic, non-uniform messages** — no fixed schedule; a router can put 90% of
  tokens on one expert (hotspot) [../GPU-Systems/MoE-Expert-Parallelism.md].
- **Latency + bandwidth both matter** — dispatch is on the critical path of
  every MoE layer; SMs spent on communication are SMs stolen from GEMM.
- **Transport diversity** — production EP fleets include EFA (AWS), Broadcom
  (Thor), NVIDIA IB — a single-vendor EP library can't cover the fleet.
### 3.3 What UCCL-EP provides
- **GPU-driven communication** — IBGDA-level performance (GPU posts/polls the
  RDMA work; no CPU proxy on the data path) while remaining portable across NICs
  [F: README — "achieving IBGDA-level performance"].
- **CPU-proxy fallback** — for NICs/paths without IBGDA-class support, the
  proxy path is the portability floor [I: README design; verify per sub-README].
- **All NIC vendors** — NVIDIA, AWS EFA, Broadcom [F: README roadmap ✅].
- **AMD GPUs too** — EP on MI300X-class hardware [F: README].
- **Flow control** — "better flow control to avoid congestion" is a shipped
  item in the roadmap [F: README].
- **DeepEP-compatible API** — DeepEP workloads can run on heterogeneous
  hardware without a rewrite [F: README sub-project line].
### 3.4 DeepEP vs UCCL-EP (the head-to-head)
| | DeepEP | UCCL-EP |
|---|---|---|
| Origin | DeepSeek (DeepEveryParallel) | UC Berkeley/Davis (OSDI'26) |
| API | its own (V2 `ElasticBuffer`) | **DeepEP-compatible** |
| Backend (V2) | **NCCL Gin** (IBGDA-class; header-only, reuses NCCL comms) | GPU-driven across NVIDIA/Broadcom/**EFA** NICs |
| GPU support | NVIDIA | NVIDIA **+ AMD** |
| SM usage | V2: V3-like training 24 → 4–6 SMs; 0-SM modes for PP/CP/Engram (RDMA/Copy Engine) | IBGDA-level, portable [F: both READMEs] |
| Sweet spot | NVIDIA-first, max performance on IB + NCCL comms | Heterogeneous fleets (mixed vendors, EFA) |
They are **substitutes at the EP layer**, not competitors at different layers —
the decision is fleet-dependent ([18 Architecture Decision Guide](18-architecture-decision-guide.md)).
Both sit under the same taxonomy branch: Expert Parallel.

## 4. Configuration surface (where to start)
- Sub-project READMEs are the live config docs: `collective/rdma/README.md`,
  `collective/efa/README.md`, `collective/afxdp/README.md`, `p2p/README.md`,
  `ep/README.md` [F: README quick-start pointers].
- Dev bootstrap: `scripts/bootstrap.sh` (uv + py3.12 + group sync) or the
  conda path [F: README].
- For a drop-in trial: swap NCCL → UCCL-Tran in the build (same CCL API), then
  A/B with nccl-tests on your fabric — the honest comparison methodology is in
  [19 Practical Labs](19-practical-labs.md) (label project-reported vs
  independently reproduced).

## 5. Failure modes
- **Wrong sub-project for the NIC** — e.g. using `collective/rdma` on ENA →
  fall back to `afxdp` (or `aws-ofi-nccl` on p5-class, per README) [F: README].
- **Lossy fabric without CC tuning** — spraying helps, but selective-repeat
  overhead appears; check CC knobs in the sub-README.
- **EP hotspots** — the transport is not the limiter anymore; it's router
  imbalance ([14 MoE Communication](14-moe-communication.md)).
- **AMD-path maturity** — check the sub-README for which AMD GPU/NIC combos are
  the tested set (MI300X + Thor-2 for P2P) [F: README].

## Key Takeaways
1. UCCL keeps incumbent APIs (NCCL collectives, NIXL-style P2P, DeepEP EP) and
   re-architects the underneath — that's what makes it "drop-in".
2. UCCL-Tran's signature: 256-path spraying + dual CC + selective repeat → runs
   on lossy Ethernet, multi-vendor.
3. UCCL-P2P is a **NIXL backend**: NIXL = what/where, UCCL = how. Complement,
   not competition.
4. UCCL-EP ≈ "portable DeepEP": same job, wider fleet (AMD, EFA, Broadcom);
   DeepEP V2 ≈ "max-performance on NCCL Gin + NVIDIA".
5. Benchmark discipline: upstream numbers (2.5×/3.7× AllReduce) are
   project-reported on project targets — reproduce before trusting on your
   fabric.

## Related
[09 UCCL Deep Dive](09-uccl-deep-dive.md) · [14 MoE Communication](14-moe-communication.md) ·
[19 Practical Labs](19-practical-labs.md) · `../GPU-Systems/MoE-Expert-Parallelism.md`

## References
- UCCL README (component detail, sub-projects, adoptions, benchmark figures,
  roadmap) — https://github.com/uccl-project/uccl (fetched 2026-08-25) [F]
- arXiv:2504.17307 (UCCL-Tran, OSDI'26) [F]
- DeepEP README (V2, NCCL Gin backend, 0-SM modes, V3-like 24→4–6 SM) —
  https://github.com/deepseek-ai/DeepEP (fetched 2026-08-25) [F]
- NIXL tree + release 0.9.0 (UCCL as backend) [F]
- llm-d v0.5 blog (UCCL-P2P KV transport) [F]
