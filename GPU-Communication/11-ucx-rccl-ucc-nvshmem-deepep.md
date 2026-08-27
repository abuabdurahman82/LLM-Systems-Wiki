# UCX / RCCL / UCC / NVSHMEM / DeepEP (and friends)
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.
Repo states fetched 2026-08-25 (GitHub API + READMEs).

## 30-Second Explanation
The "everything else" page: the libraries that occupy the taxonomy branches
*around* NCCL/NIXL/UCCL, each with a distinct job. One line each, then the
placement table.

| Library | Branch (taxonomy) | One-liner | 2026-08-25 state [F] |
|---|---|---|---|
| **RCCL** | Collectives | AMD's NCCL-equivalent: same collective API family for AMD GPUs (RCP/ROCm ecosystem) | active (ROCm TheRock builds ship UCCL alongside; RCCL remains the ROCm default) [I: ecosystem posture] |
| **UCX** | P2P / transport | Lower-level *unified communication framework*: abstract primitives over RDMA (IB & RoCE), TCP, GPU, shared memory, network atomics; the "how does data move" layer | active (openucx/ucx, ~1.7k★, pushed 2026-08-25; tested at 1.22.x under NIXL) [F] |
| **UCC** | Collectives (abstraction) | Unified Collective Communication *Library*: plugin-based collective layer over UCX, HPC-origin,
   part of the OpenUCX org (openucx/ucc) — **not** UCCL | active (openucx/ucc, ~312★, pushed 2026-08-20) [F] |
| **NVSHMEM** | P2P / one-sided | OpenSHMEM-based PGAS for GPUs: symmetric memory, one-sided put/get/atomics/signals **from within CUDA kernels**; host+kernel+stream interfaces | active (Apache-2.0; docs at docs.nvidia.com/nvshmem) [F] |
| **DeepEP** | Expert Parallel | DeepSeek's EP comm library: high-throughput + low-latency all-to-all dispatch/combine kernels, FP8 support, JIT; V2 switched from NVSHMEM to **NCCL Gin** backend; 0-SM PP/CP/Engram modes | active (V2; EP up to 2048; pushed 2026-08-20, ~10k★) [F] |
| **MSCCL** / **MSCCL++** | Collectives (programmable) | MSCCL: user-defined collective schedules on NCCL (paper-era). **MSCCL++**: GPU-driven communication stack — programmable, device-side collectives/P2P | active (microsoft/mscclpp, pushed 2026-08-25; CUDA + ROCm test pipelines) [F] |
| **MPI / CUDA-aware MPI** | Collectives (HPC) | The 40-year-old collective standard; CUDA-aware MPI lets communicators point at device buffers (e.g. `MPI_Win_allocate` + GPUDirect) | stable; still the launcher + P2P fabric under many HPC stacks [I] |
| **libfabric** | Transport / fabric API | Open fabrics API (OFI): verbs-like transport abstraction over EFA, IB, sockets, …; the fabric layer AWS EFA is built on | active (OpenFabrics) [F: EFA docs] |
| **GPUDirect RDMA** | Hardware offload | NIC↔HBM DMA, no host bounce — a *capability*, not a library ([03 §2](03-gpu-network-architecture.md)) | stable [F: NVIDIA GDR docs] |
| **GPUDirect Storage (GDS)** | Hardware offload | NVMe↔HBM DMA (cuFile); NIXL's `cuda_gds`/`gds_mt` backends ride it; GDS MT adds multi-threaded transfer | active [F: NVIDIA GDS docs; NIXL tree] |
| **SHARP / NVLS** | In-network offload | In-network reduction: SHARP on IB switches, NVLS on NVSwitch ([06](06-nccl-rdma-sharp.md)) | hardware-gated [F] |
| **InfiniBand / RoCE / EFA** | Physical fabric | The two RDMA fabrics + AWS's SRD-based fabric ([03 §5](03-gpu-network-architecture.md), [16](16-performance-benchmarking.md) network chapter) | — |

## 1. UCX — the "how data moves" framework
**What:** abstract communication primitives that exploit the best of available
hardware and offloads — RDMA (IB & RoCE), TCP, GPUs, shared memory, network
atomic operations [F: openucx README].
**Where it sits:** *below* the collective layer. NCCL/UCCL-UCC all need a
transport; UCX is one (very mature) implementation of "move data between
endpoints efficiently". NIXL's default network backend is UCX
([07 NIXL Deep Dive](07-nixl-deep-dive.md)); UCC uses it as its plugin
transport; MPI vendors use it as the MTL.
**When:** you want a transport with the widest hardware coverage and no
application-level collectives; or you're building *another* library (NIXL, UCC)
on top.
**Vs UCCL:** UCX = general transport framework (no GPU-collective semantics).
UCCL-Tran = GPU collective engine with a *software-defined* transport of its own
(spraying/CC) — UCCL is *in the same problem space as NCCL* but UCX is
*one of NCCL's possible underlays* [I: layering argument].

## 2. RCCL — AMD's collective engine
**What:** ROCm's collective communication library — the API-shape equivalent of
NCCL on AMD GPUs (collectives + P2P).
**When:** AMD training/serving is RCCL-native. Note the 2026 nuance: AMD's
TheRock ecosystem also ships **UCCL** (Tran/EP/P2P), so "AMD ⇒ RCCL" is
softening into "AMD ⇒ RCCL or UCCL" for new heterogeneous workloads
[../Networking/README.md; I: ecosystem posture].

## 3. UCC — the collective abstraction layer
**What:** Unified Collective Communication Library — plugin-based collectives
*over UCX* transports, HPC heritage, part of the OpenUCX org
   (openucx/ucc)
   [F: openucx/ucc repo, fetched 2026-08-25].
**When:** HPC-style collectives where you want the abstraction to pick among UCX
transports (SHM, verbs, …) per topology.
**The trap:** UCC ≠ UCCL. Same letters, different projects, different shapes:
UCC = *collective layer over UCX*; UCCL = *GPU collectives + P2P + EP with its
own software transport* ([09](09-uccl-deep-dive.md)). The user-mandated
taxonomy lists both, on purpose, on different rows.

## 4. NVSHMEM — one-sided GPU programming (PGAS)
**What:** OpenSHMEM-based parallel programming interface for GPUs: a
partitioned global address space (PGAS) across GPUs; symmetric memory; one-sided
transfers, atomics, signaling, synchronization, and collectives; **host, CUDA
kernel, and CUDA stream interfaces** — i.e. communication can be initiated from
*inside a kernel* [F: NVIDIA NVSHMEM README, fetched 2026-08-25].
**When:** you are writing custom GPU code that needs one-sided puts/gets at
kernel granularity (e.g. all-to-all kernels, distributed shared memory
semantics) — the substrate that DeepEP **V1** was built on; V2 moved to NCCL
Gin for lightness, and NCCL's own GIN/GDA + CFT now cover much of the same
ground natively ([04 §7](04-nccl-deep-dive.md)) [F: DeepEP README; NCCL 2.31 notes].
**Vs NCCL:** NCCL = *collectives* (group ops, library-managed). NVSHMEM =
*one-sided PGAS programming model* (you structure the communication).
Complementary: many stacks use both.

## 5. DeepEP — the expert-parallel specialist
**What:** DeepSeek's high-performance EP communication library: high-throughput
and low-latency all-to-all GPU kernels for MoE **dispatch and combine**, with
low-precision (FP8) support; kernels JIT-compiled at runtime (no CUDA
compilation at install); designed for zero/minimal SM occupation
[F: DeepEP README, fetched 2026-08-25].
**V2 (current):** complete EP refactoring; **switched from the NVSHMEM backend
to the NCCL Gin backend** (header-only, reuses existing NCCL communicators);
unified high-throughput + low-latency APIs in `ElasticBuffer`; scale-out up to
**EP2048**; analytical SM & QP sizing (no auto-tuning); for V3-like legacy
training, SM usage reduced **24 → 4–6** at equivalent-or-better performance;
"0 SM" modes for Engram (RDMA), PP (RDMA), CP (Copy Engine) — Engram/PP/CP are
experimental [F: DeepEP README news + feature list].
**Performance:** project-reported, V3 config (8K tokens/batch, d=7168, top-8,
FP8 dispatch, BF16 combine): "matches or exceeds hardware bandwidth limits"
across configurations [F: DeepEP README perf section — vendor-reported].
**When:** NVIDIA-centric MoE EP at maximum performance; the baseline that
UCCL-EP targets compatibility with ([10 §3.4](10-uccl-collective-p2p-ep.md)).

## 6. MSCCL / MSCCL++ — programmable collectives
- **MSCCL** — the user-programmable collective *schedule* idea on NCCL
  (define the algorithm yourself; NCCL executes it) [I: MSCCL paper-era].
- **MSCCL++** — Microsoft's **GPU-driven communication stack** for scalable AI:
  device-side programming of collectives/P2P (the "communication as a kernel"
  approach); CUDA + ROCm CI pipelines; active development
  (pushed 2026-08-25) [F: microsoft/mscclpp README, fetched 2026-08-25].
**When:** research or tuned-kernel workloads where you want to express the
collective schedule in code; complements NCCL (runs in/with it) rather than
replacing the fabric.

## 7. MPI & CUDA-aware MPI
**What:** the HPC collective standard (40+ years of portability). CUDA-aware
MPI lets MPI operations reference **device pointers** (GPUDirect-backed), so
collectives avoid host staging on supported fabrics
[../Networking/README.md; I].
**When:** HPC training stacks, checkpointing, and any environment where MPI is
the launcher + fabric contract. Why it *remains* relevant: portability across
fabrics/HPC vendors, mature topology awareness, and the MPI world's collective
schedules. Why it's *different from NCCL*: NCCL is GPU-native end to end
(kernels on the GPU, topology-aware, NVLink/NVLS/SHARP features MPI can't
express); CUDA-aware MPI keeps the HPC abstraction and borrows GPUDirect
[../Networking/README.md; I].

## 8. libfabric — the fabric API
**What:** Open Fabrics API (OFI): a transport-abstracting layer over EFA,
InfiniBand (verbs), sockets, …; **the layer AWS EFA is built on**
[F: AWS EFA docs].
**Where:** *below* the communication libraries. NCCL reaches EFA via
libfabric-based plugins; NIXL ships a `libfabric` backend
[07 NIXL Deep Dive; F: NIXL tree]; UCCL's EFA support rides it
[09; F]. It is not a "communication library" in the collective sense — it's the
fabric's API.

## 9. GDS / GPUDirect — the hardware offloads (not libraries)
- **GPUDirect RDMA** — NIC↔HBM DMA; the capability that makes "no host bounce"
  true ([03 §2](03-gpu-network-architecture.md)).
- **GPUDirect Storage** — NVMe↔HBM via cuFile; NIXL's `cuda_gds` (and `gds_mt`,
  multi-threaded) backends; llm-d's roadmap includes GDS for KV offloading
  [F: NIXL tree; llm-d blog, fetched 2026-08-25].
Both are *capabilities the libraries exploit* — placing them in the "libraries"
list is the exact category error this section warns against
([01 §3](01-why-communication-matters.md)).

## 10. Placement summary (the mental model)
```text
collective semantics:   NCCL · RCCL · UCCL-Tran · UCC · MSCCL++ · MPI (CUDA-aware)
P2P/one-sided:          NVSHMEM · UCCL-P2P · NIXL (agent) · NCCL Send/Recv
data-movement engine:   NIXL · UCX (transport) · UCC (transport-abstracted collectives)
EP specialists:         DeepEP · UCCL-EP · (NCCL EP)
fabric APIs:            libfabric · verbs
hardware offloads:      GPUDirect RDMA · GDS · SHARP · NVLS
```
Every "which should I use" answer is: *which branch of the taxonomy is the
workload in, then which library owns that branch on your hardware?* —
[18 Architecture Decision Guide](18-architecture-decision-guide.md).

## Key Takeaways
1. One library per branch: RCCL (AMD collectives), UCX (transport), UCC
   (collective layer over UCX), NVSHMEM (one-sided PGAS), DeepEP (EP), MSCCL++
   (programmable GPU collectives), MPI (HPC collectives), libfabric (fabric API).
2. **UCC ≠ UCCL** — the single most common naming confusion in this stack.
3. NVSHMEM is a *programming model*, not a rival to NCCL; DeepEP V2 moved to
   NCCL Gin — the one-sided and collective worlds are converging.
4. GDR/GDS are capabilities, not libraries — don't put them on the "choose a
   library" list.
5. EFA is libfabric-based: any EFA story (NCCL, NIXL, UCCL) is a libfabric
   story underneath.

## Related
[01 Why Communication Matters §3 (taxonomy)](01-why-communication-matters.md) ·
[10 UCCL Collective / P2P / EP](10-uccl-collective-p2p-ep.md) ·
[14 MoE Communication](14-moe-communication.md) · `../Networking/README.md`

## References
- openucx/ucx, openucx/ucc, microsoft/mscclpp, deepseek-ai/DeepEP,
  NVIDIA/nvshmem READMEs + GitHub API state (fetched 2026-08-25) [F]
- AWS EFA documentation (libfabric/SRD) [F]
- NVIDIA GPUDirect RDMA / GDS docs [F]
- `../Networking/README.md` (MPI/IB/RoCE/SHARP/GDR summary; internal)
