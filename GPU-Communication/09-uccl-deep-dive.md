# UCCL Deep Dive
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.
Verified against `uccl-project/uccl` main branch + OSDI'26 papers (fetched 2026-08-25).

## 30-Second Explanation
**UCCL** is an efficient, open-source (Apache-2.0) communication library for GPUs
covering all three branches of this section's taxonomy — **collectives, P2P
(KV-cache / RL weight transfer), and expert parallel (EP, e.g. IBGDA)** — with two
design goals: **flexibility** for fast-evolving ML workloads and **portability**
across heterogeneous GPUs and NICs [F: uccl-project/uccl README, fetched
2026-08-25]. It is developed at UC Berkeley (Sky Computing Lab) and UC Davis
(ArtSy lab), supported by AMD, AWS, Broadcom, CloudLab, Google Cloud, IBM, Lambda,
and Mibura [F: README]. Two OSDI'26 papers describe it: *UCCL-Tran* (the software
transport layer, arXiv:2504.17307) and *UCCL-EP* (portable expert-parallel
communication) [F: README bibtex].

> **Do not confuse UCCL with UCC.** "UCC" (Unified Collective Communication, the
> `ucc` project — openucx/ucc) is a *different* library — a collective-abstraction
> layer over UCX. UCCL (this page) is the UC Berkeley/Davis GPU stack. The
> taxonomy in [01](01-why-communication-matters.md) deliberately lists both, on
> different rows.

## 1. The three components
```text
                    UCCL
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
   Collective       P2P       Expert Parallel
   (UCCL-Tran)   (UCCL-P2P)     (UCCL-EP)
```

| Component | Role | Drop-in for | Key differentiator |
|---|---|---|---|
| **UCCL-collective (UCCL-Tran)** | GPU collectives | **NCCL/RCCL** (same API, no app changes) | re-architected *software* transport: packet spraying (256 paths), latency-based + receiver-driven congestion control, selective-repeat loss recovery [F: README + arXiv:2504.17307] |
| **UCCL-P2P** | initiator/target transfers | NIXL-style P2P | built for next-gen 800 Gbps NICs; multi-threaded transfer engines [F: README] |
| **UCCL-EP** | expert-parallel dispatch/combine | **DeepEP-compatible API** | runs DeepEP-style EP on *heterogeneous* hardware (NVIDIA+AMD GPUs; NVIDIA/Broadcom/EFA NICs) at IBGDA-level performance [F: README] |

The sub-projects on disk map to transport class [F: README quick-start]:
- `collective/rdma` — collectives for NVIDIA/AMD GPUs + IB/RoCE RDMA NICs
  (NVIDIA & Broadcom NICs today).
- `collective/efa` — collectives for AWS EFA (p4d.24xlarge today; on
  p5/p5e/p5en/p6 the official `aws-ofi-nccl` NCCL plugin already performs well).
- `collective/afxdp` — collectives for **non-RDMA** NICs (AWS ENA, IBM VirtIO).
- `p2p` — P2P for RDMA NICs + GPU IPCs (NVIDIA/AMD GPUs; NVIDIA/Broadcom NICs).
- `ep` — EP for MoE training & inference with DeepEP-compatible APIs
  (NVIDIA/AMD GPUs; NVIDIA/Broadcom/EFA NICs).

## 2. Origins & project status (authoritative framing)
- **Academic, open-source, multi-vendor** — not a single-vendor product. The
  "portability" goal means it deliberately targets the *non-NVIDIA* corner that
  vendor stacks skip: AMD MI300X + Broadcom Thor-2 (P2P), EFA, GCP TCP-X, plain
  TCP, ENA/VirtIO [F: README roadmap + adoptions].
- **Newly active** — repo created 2025-01-06, ~1.5k stars, pushed 2026-08-23
  [F: GitHub API, fetched 2026-08-25]. Treat as **recently-introduced /
  rapidly-evolving**: feature matrix below is the 2026-08 snapshot, not a stable
  contract.
- **Peer-reviewed core** — the transport layer (UCCL-Tran) and EP layer
  (UCCL-EP) are OSDI'26, so the load-bearing claims have a primary paper
  (arXiv:2504.17307 for the transport) rather than only a blog.
- **Adopted in production stacks** — see §5; this is what elevates it above a
  research prototype for our purposes.

## 3. The philosophy that differs from NCCL
NCCL's network transports (kernel TCP + RDMA) stream large volumes over **one or
a few paths**; in a datacenter that concentrates load onto a single
congested path ("single-path-of-congestion") [F: README high-level design].
UCCL-Tran instead:
1. **Software transport layer** — re-architects the CCL layer while *keeping NCCL
   APIs*, so apps drop in unchanged [F: README].
2. **Packet spraying across many paths** — up to **256 paths** in software, using
   abundant ECMP paths to dodge a hot one [F: README + arXiv:2504.17307]. This is
   the "multipathing" the user's prompt flags as a UCCL strength.
3. **Advanced congestion control** — latency-based *and* receiver-driven CC
   [F: README].
4. **Efficient loss recovery** — selective repeat, so it can run on **lossy
   Ethernet** (public clouds with legacy NICs), not only lossless
   InfiniBand/PFC fabrics [F: README].
Net effect: the transport is a *software-defined fabric abstraction* on top of
the NIC, rather than a thin verbs wrapper — which is why it ports across NIC
vendors (NVIDIA, Broadcom, EFA, ENA, VirtIO) that a single-vendor stack would not
bother to support.

## 4. What each branch is for (pointers)
- **UCCL-Tran** → replace NCCL/RCCL for collectives when your fabric is
  lossy/Ethernet-heavy, multi-vendor, or you want software-defined CC. Full
  detail + benchmarks: [10](10-uccl-collective-p2p-ep.md).
- **UCCL-P2P** → KV-cache / weight transfer; it is literally a **NIXL backend**
  (see [07 §7](07-nixl-deep-dive.md) and the "complement, not competitor" point).
- **UCCL-EP** → MoE dispatch/combine on mixed NVIDIA+AMD + EFA/Broadcom;
  DeepEP-compatible so DeepEP workloads can run on heterogeneous hardware
  ([14 MoE Communication](14-moe-communication.md)).

## 5. Adoptions (as of 2026-08-25) [F: README]
- **NVIDIA NeMo** agent framework — UCCL-EP for expert-parallel communication.
- **NVIDIA NIXL** — UCCL-P2P integrated as an RDMA backend (NIXL release 0.9.0).
- **llm-d** (Red Hat/IBM/Google) — UCCL-P2P for KV-cache transfer
  (llm-d v0.5, 2026-02: "UCCL-based transport resilience").
- **AMD Primus** training framework — UCCL-EP.
- **AMD TheRock** build platform — UCCL-Tran, UCCL-EP, UCCL-P2P.
The pattern: UCCL shows up exactly where heterogeneity or lossy/Ethernet fabrics
are the hard part (AMD GPUs, EFA, mixed-vendor EP) — consistent with its
portability goal.

## 6. Version/stability posture
- **Stable-ish:** UCCL-Tran collectives over RDMA (NVIDIA/Broadcom NICs), UCCL-EP
  over RDMA (NVIDIA/Broadcom/EFA), UCCL-P2P over RDMA (NVIDIA/Broadcom).
- **Newer:** EFA collectives (p4d today; p5-family recommends `aws-ofi-nccl`
  instead), AFXDP non-RDMA collectives (ENA/VirtIO), GCP TCP-X P2P.
- **Roadmap (proposed, not shipped):** TPU/Trainium EP; re-architecting NCCL to
  "unleash network hardware"; more SM-efficient paths; better KV engine
  [F: README road-map].
- **Experimental:** anything tagged in the sub-READMEs; the "re-architecting
  NCCL" item is explicitly in progress, not GA.

## 7. How to think about UCCL in one line
> NCCL is the incumbent GPU collective engine (NVIDIA-optimized, NCCL API).
> UCCL is the *portable, software-transport, multi-vendor* challenger that keeps
> the NCCL API for collectives, adds a NIXL-style P2P engine, and ships a
> DeepEP-compatible EP layer — so the same workload can run across NVIDIA and
> AMD GPUs and across IB/RoCE/EFA/Ethernet.

## Key Takeaways
1. UCCL = 3 branches in one repo: **UCCL-Tran** (collectives, NCCL-API
   drop-in), **UCCL-P2P** (NIXL-style), **UCCL-EP** (DeepEP-compatible).
2. Its signature is the **software transport layer**: 256-path packet spraying,
   latency- + receiver-driven CC, selective-repeat loss recovery — it runs on
   lossy Ethernet, not only lossless IB.
3. **Portability is the product** — NVIDIA *and* AMD GPUs, NVIDIA/Broadcom/EFA/
   ENA/VirtIO NICs; that's the niche vendor stacks leave open.
4. It is **complementary to NIXL** (UCCL-P2P is a NIXL backend) and a
   **drop-in for NCCL** (same collectives API) — not a "third NCCL".
5. Treat it as **recently-introduced**: OSDI'26 papers back the core, but the
   feature matrix is a 2026-08 snapshot that will move.

## Related
[10 UCCL Collective / P2P / EP](10-uccl-collective-p2p-ep.md) ·
[07 NIXL Deep Dive §7](07-nixl-deep-dive.md) ·
[11 UCX/RCCL/UCC/NVSHMEM/DeepEP](11-ucx-rccl-ucc-nvshmem-deepep.md) ·
[14 MoE Communication](14-moe-communication.md)

## References
- UCCL repo + README (components, design, adoptions, roadmap) —
  https://github.com/uccl-project/uccl (fetched 2026-08-25) [F]
- UCCL-Tran: "An Extensible Software Transport Layer for GPU Networking" —
  arXiv:2504.17307, OSDI'26 [F]
- UCCL-EP: "Portable Expert-Parallel Communication" — OSDI'26 [F: README bibtex]
- NIXL release 0.9.0 (UCCL-P2P as RDMA backend); llm-d v0.5 blog [F]
- uccl-project.org site — https://uccl-project.github.io/ [F]
