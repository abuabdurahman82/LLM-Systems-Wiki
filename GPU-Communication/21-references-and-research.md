# References & Research (and Provenance Audit)
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
Every fast-moving claim in this section was verified against primary sources on
**2026-08-25** (the fetch date). This page lists the source set, separates
stable / recently-introduced / experimental / roadmap functionality, and —
because this section was seeded from a detailed external prompt that itself
asserted many facts about NIXL/UCCL/NCCL — provides a **provenance audit** of
the prompt's load-bearing claims against the primaries: CONFIRMED / CORRECTED /
UNVERIFIED, with the source cited. Discrepancies are the value.

## 1. The source set (all fetched 2026-08-25 unless noted)
**NCCL (NVIDIA):**
- GitHub repo + master README — https://github.com/NVIDIA/nccl (version
  v2.31.2-1) [F]
- NCCL 2.31.2 User Guide: env vars, types (`ncclConfig_t`), CUDA Graphs,
  device API (GIN/GDA) — https://docs.nvidia.com/deeplearning/nccl/user-guide/
  docs/ [F]
- Release notes: NCCL 2.31.2 (CFT, per-collective config, GIN GDA, EFA GDA PR
  #2273), nccl-ep v0.1.0 (libnccl_ep.so, LSA+GIN, CUDA-Graph handles),
  nccl4py [F]
- nccl-tests — https://github.com/NVIDIA/nccl-tests [F]
- NCCL Roadmap issue #2272 (EFA GDA "coming in 2.31") [F]

**NIXL (NVIDIA, ai-dynamo):**
- GitHub repo + README (v1.4.0; ETCD; GDS; CUDA 12/13; UCX 1.22.x; GDRCopy) —
  https://github.com/ai-dynamo/nixl [F]
- BackendGuide (NB/SB API, descriptor table, lifecycle, dynamicity) —
  `docs/BackendGuide.md` [F]
- Plugin tree `src/plugins`: ucx, cuda_gds, gds_mt, libfabric, posix, obj,
  azure_blob, hf3fs, infinia, gusli, mooncake, gpunetio, uccl [F]
- NIXLBench + KVBench docs — `benchmark/nixlbench`, `benchmark/kvbench` [F]
- NVIDIA developer blog: "Enhancing Distributed Inference Performance with the
  NVIDIA Inference Transfer Library" (framework list: Dynamo, TRT-LLM, vLLM,
  SGLang, Ray, LMCache) [F]

**UCCL (uccl-project):**
- GitHub repo + README (components, 256-path spraying, dual CC, selective
  repeat, adoptions: NeMo/NIXL/llm-d/Primus/TheRock; roadmap; benchmark
  figures) — https://github.com/uccl-project/uccl (created 2025-01-06;
  Apache-2.0; ~1.5k★; pushed 2026-08-23) [F]
- UCCL-Tran: "An Extensible Software Transport Layer for GPU Networking",
  arXiv:2504.17307 (OSDI'26) [F]
- UCCL-EP: "Portable Expert-Parallel Communication" (OSDI'26) [F: README
  bibtex]
- NIXL release 0.9.0 (UCCL-P2P as RDMA backend) [F]
- llm-d v0.5 release notes (UCCL-based transport resilience; 2026-02)
  [F: llm-d GitHub]

**Adjacent libraries:**
- DeepEP — https://github.com/deepseek-ai/DeepEP (V2: NCCL Gin backend, EP2048,
  0-SM PP/CP/Engram, V3-like 24→4–6 SM, buffer-size note, FP8, JIT; ~10k★;
  pushed 2026-08-20) [F]
- NVSHMEM — https://github.com/NVIDIA/nvshmem (OpenSHMEM-based PGAS; host/
  kernel/stream interfaces) [F]
- UCX — https://github.com/openucx/ucx (~1.7k★; RDMA IB/RoCE, TCP, GPU, SHM,
  net atomics) [F]
- UCC — https://github.com/openucx/ucc ("Unified Collective Communication
  Library"; ~312★; pushed 2026-08-20) [F]
- MSCCL++ — https://github.com/microsoft/mscclpp (GPU-driven comm stack;
  pushed 2026-08-25) [F]
- GPUDirect RDMA — https://docs.nvidia.com/cuda/gpudirect-rdma/ [F]
- GPUDirect Storage — https://docs.nvidia.com/gds/ [F]
- AWS EFA — AWS documentation (SRD, GDA, libfabric) [F]
- Mellanox/NVIDIA networking (SHARP, NDR/XDR, adaptive routing, DCQCN, packet
  spraying) [F: vendor pages]

**Engines:**
- vLLM NixlConnector guide — https://docs.vllm.ai/en/stable/features/
  nixl_connector_usage/ [F]
- Dynamo README (KVBM table: SGLang 🚧 / TRT-LLM ✅ / vLLM ✅; orchestration
  framing) — https://github.com/ai-dynamo/dynamo [F]
- llm-d GitHub (v0.5: UCCL transport resilience, ~3.1k tok/s/B200 wide-EP,
  50k tok/s on 16×16 P/D — *project-reported*) + FS-backend blog (offloading
  connector, GDS/NIXL roadmap) [F]
- SGLang docs (NIXL connector) + NVIDIA blog framework list [F]
- TRT-LLM docs (TP/PP/MoE; NIXL in disaggregated executor) [F: NVIDIA blog;
  TRT-LLM docs]
- PyTorch distributed docs (NCCL backend default) [F]

**Internal cross-links (verified on disk 2026-08-25):**
`../GPU-Systems/{NCCL.md, Topology.md, Scale-Up-vs-Scale-Out.md, Multi-Node.md,
Tensor-Parallelism.md, Pipeline-Parallelism.md, MoE-Expert-Parallelism.md,
Prefill-Decode-Disaggregation.md, Case-Studies.md, vLLM.md, SGLang.md,
TensorRT-LLM.md, Diagnostics.md, Labs.md, _STYLE.md}`;
`../Distributed-Inference/{Overview.md, NVIDIA-Dynamo.md, Dynamo-vs-llm-d.md,
llm-d.md, README.md}`; `../Networking/README.md`; `../KV-Cache/README.md`;
`../Training-Engineering/{Parallelism.md, Scaling-1-to-10k.md}`;
`../Labs/README.md`; `../Benchmarks/README.md`.

## 2. Stability classification (as of 2026-08-25)
| Stable | Recently introduced | Experimental | Roadmap/proposed |
|---|---|---|---|
| NCCL ring/tree/LL/LL128; NVLS (2.17+); CollNet/SHARP; GDR; CUDA Graphs; user buffer registration; multi-rail; PXN | NCCL Device API/GIN (2.28), GDA backends; CFT (Blackwell+CUDA13.3, 2.31); per-collective config (2.31); NCCL EP; EFA GDA (2.31); multi-rank-per-GPU (2.30) | NCCL RMA plugin slot; NCCL EP maturity; UCCL sub-project matrices (EFA p4d-only, AFXDP ENA/VirtIO) | UCCL TPU/Trainium EP; UCCL "re-architect NCCL"; NIXL object-store maturity; llm-d NIXL/GDS KV offloading |
| NIXL agent/UCX/GDS/posix/obj; NIXLBench; vLLM NixlConnector; Dynamo KVBM-over-NIXL | NIXL v1.4.0; ETCD metadata; uccl/mooncake/hf3fs/infinia/gusli/gpunetio/azure_blob backends; KVBench | NIXL GDS-MT, gpunetio, gusli maturity | NIXL as the umbrella for storage vendors |
| UCCL-Tran RDMA (NVIDIA/Broadcom NICs); UCCL-EP (NVIDIA+Broadcom+EFA, AMD); UCCL-P2P RDMA | UCCL in NIXL (release 0.9.0), NeMo, Primus, TheRock; llm-d v0.5 | UCCL EFA collectives beyond p4d; GCP TCP-X; ENA/VirtIO AFXDP | UCCL TPU/Trainium; SM-efficient paths |
| DeepEP V1 (NVSHMEM) | DeepEP V2 (NCCL Gin, ElasticBuffer, EP2048, 0-SM modes) | DeepEP Engram/PP/CP (experimental), elastic buffers | DeepEP all-gather updates / reduce-scatter for DP/TP |
| GDR, GDS, SHARP, NVLS, IBGDA | EFA GDA (NCCL 2.31); CFT | EFA GDA performance coverage (SPCX DDP) | — |

## 3. Provenance audit — the seed prompt's load-bearing claims
This section was authored from a detailed external specification that asserted
facts about the libraries. Each load-bearing assertion, checked against the
primaries above on 2026-08-25:

| # | Seed claim | Disposition | Primary evidence |
|---|---|---|---|
| A1 | "UCCL is a unified/next-gen GPU communication stack from 'the UCCL project'" | **CONFIRMED, with attribution precision** | `uccl-project/uccl` (UC Berkeley Sky Lab + UC Davis ArtSy; Apache-2.0; created 2025-01-06; OSDI'26 papers). Not a single-vendor "project" — it's a multi-vendor academic open-source effort |
| A2 | UCCL has three areas: Collective ("UCCL-Tran"), P2P, Expert Parallel (UCCL-EP) | **CONFIRMED** | README component list: UCCL-collective (UCCL-Tran), UCCL-P2P, UCCL-EP |
| A3 | UCCL-Tran is "a drop-in replacement for NCCL/RCCL" | **CONFIRMED** | README: "drop-in replacement for NCCL/RCCL (e.g., requiring no changes to application code)" |
| A4 | UCCL transports: RDMA, RoCE, InfiniBand, EFA, heterogeneous GPU/NIC | **CONFIRMED (2026-08 snapshot)** | Sub-projects: rdma (NVIDIA/Broadcom NICs), efa (p4d.24xlarge), afxdp (ENA/VirtIO); P2P "RDMA (NVIDIA, Broadcom), AWS EFA, GCP TCPX, TCP"; EP "Nvidia, AWS EFA, Broadcom" + AMD GPUs |
| A5 | NIXL "Inference Xfer Library", agent + backend plugins (UCX, GDS, libfabric, storage) | **CONFIRMED** | NIXL README + BackendGuide (NB/SB API, plugin list incl. ucx/cuda_gds/libfabric/posix/obj + hf3fs/infinia/mooncake/azure_blob/gusli/gpunetio) |
| A6 | NIXL core concepts: Agent, Memory Segment, Registration, Metadata, Transfer Descriptor, Transfer Request, Notifications, Backend Plugin | **CONFIRMED** | BackendGuide defines all eight (mem types DRAM/VRAM/BLK/FILE/OBJ; one-sided READ/WRITE; `supportsNotif`) |
| A7 | NIXL transfer lifecycle: create → register → metadata → descriptor → prep → async post → poll/notify → completion | **CONFIRMED** | BackendGuide agent flow (prep once / post many; DONE-repost; estimateXferCost) |
| A8 | "NIXL + UCCL: Application → NIXL → UCCL P2P Backend → RDMA/TCP/TCP-X/EFA" | **CONFIRMED** | NIXL `src/plugins/uccl`; NIXL release 0.9.0 "UCCL-P2P as an RDMA backend"; UCCL P2P transports incl. TCP-X (GCP) + EFA |
| A9 | NIXL + Dynamo: prefill/decode workers, KV over NIXL→UCX→GDR | **CONFIRMED** | Dynamo README (KVBM ✅ vLLM/TRT-LLM); NIXL README ("targeted for accelerating point to point communications in AI inference frameworks such as NVIDIA Dynamo") |
| A10 | UCCL-EP: GPU-driven, IBGDA where applicable, CPU-proxy fallback, dynamic/non-uniform traffic, dispatch/combine | **CONFIRMED** | README ("DeepEP atop of heterogeneous hardware … achieving IBGDA-level performance"; EP roadmap: flow control, all NIC vendors, AMD) |
| A11 | DeepEP: "specialized expert-parallel communication" | **CONFIRMED** | DeepEP README (EP focus; high-throughput + low-latency all-to-all dispatch/combine; FP8; V2 on NCCL Gin) |
| A12 | NVSHMEM: PGAS / one-sided GPU communication | **CONFIRMED** | NVSHMEM README ("partitioned global address space … one-sided communication from within CUDA kernels") |
| A13 | NCCL "topology-aware … collectives *and* P2P Send/Recv" | **CONFIRMED** | NCCL README ("all-reduce, all-gather, reduce, broadcast, reduce-scatter, as well as any send/receive based communication pattern") |
| A14 | NCCL advanced features list (multi-NIC, multi-rail, PXN, CollNet, SHARP, NVLS/NVLink SHARP, user buffer registration, CUDA Graph, one-sided/device API/GPU-initiated) | **CONFIRMED** (all present; version-gates stated in [04](04-nccl-deep-dive.md)) | env page + types page + deviceapi page + 2.31 release notes |
| A15 | NCCL env vars (NCCL_DEBUG, NCCL_DEBUG_SUBSYS, NCCL_SOCKET_IFNAME, NCCL_IB_HCA) "research the latest before publishing" | **CONFIRMED current at 2.31.2** | env.html fetched 2026-08-25: all four present; [17](17-troubleshooting.md) lists the full current set + newer GIN/RMA/MNNVL/RAS additions |
| A16 | vLLM uses NIXL as a KV connector; Dynamo KVBM; SGLang NIXL; TRT-LLM NIXL; llm-d | **CONFIRMED** | vLLM NixlConnector docs; Dynamo README; SGLang docs/NVIDIA blog; NVIDIA blog framework list; llm-d v0.5 (UCCL transport) |
| A17 | "Do not describe all of these technologies as collective communication libraries" | **CONFIRMED as a correct warning** — taxonomy built around it (01 §3); UCC ≠ UCCL trap handled (01; 11 §3) | — |
| A18 | Seed's transfer-time convention (KV move over links) | **CORRECTED for internal consistency** | Seed-era numbers (88.7/360.9 ms) used a line-rate-vs-effective convention; this section's [E] numbers use effective bandwidth (4.0 GiB @ 50 GB/s = 85.9 ms; @ 12.5 GB/s = 343.6 ms; h=0.9 → 34.4 ms) and are *cross-checked* against `../GPU-Systems/Prefill-Decode-Disaggregation.md`'s own convention (0.5 GiB → ~10.7 ms; h=0.9 → 36.1 ms). Both shipped, each labeled with its convention (08 §2) |
| A19 | Seed's "4.8 ms 32MB AllReduce" framing (inherited from the house NCCL page) | **CORRECTED** | The 4.8 ms reference in `../GPU-Systems/NCCL.md` corresponds to a *4.0 GiB* move over the 900 GB/s NVLink aggregate [E], not a 32 MB AllReduce (a 32 MB ring AllReduce on NVLink is ≈ 62 µs [E]). [05 §8] now states both correctly instead of conflating them |
| A20 | Seed's NIXL "supported plugin ecosystem" diagram (UCX/GDS/libfabric/UCCL/Storage) | **CONFIRMED, non-exhaustive** | Seed itself asked to validate against upstream: the live tree has 12+ backends (incl. mooncake, hf3fs, infinia, azure_blob, gusli, gpunetio) — [07 §2] shows the validated, wider list |

**Where the seed was right (said plainly):** the taxonomy (A17), the
complementarity framing (A8/A9), the NIXL/UCCL/NCCL component descriptions
(A2–A14, A16), and the "verify against upstream, don't assume the diagram is
exhaustive" instruction (A20). The two numeric/labeling corrections (A18, A19)
are exactly the rounding/label drift the house style warns about — caught by
this audit, fixed in [05 §8](05-nccl-algorithms-transport.md) and
[08 §2](08-nixl-kv-cache-transfer.md).

## 4. "Verified as of" statements (the fast-movers)
- **NCCL:** v2.31.2-1 feature set (GIN/GDA, CFT, per-collective config, NCCL EP,
  EFA GDA) — verified 2026-08-25. GIN device API since 2.28; NVLS since 2.17;
  multi-rank-per-GPU since 2.30 (experimental).
- **NIXL:** v1.4.0; plugin tree + ETCD + KVBench — verified 2026-08-25.
- **UCCL:** main-branch feature matrix (rdma/efa/afxdp sub-projects; P2P TCP-X;
  EP EFA/Broadcom/AMD; adoptions NeMo/NIXL/llm-d/Primus/TheRock) — verified
  2026-08-25. Treat the matrix as a *snapshot*, not a contract.
- **DeepEP:** V2 (NCCL Gin, EP2048, 0-SM modes) — verified 2026-08-25.
- **llm-d:** v0.5 (2026-02; UCCL transport resilience; project-reported perf)
  — verified 2026-08-25.
- **Engine KV/EP integrations** (vLLM NixlConnector flags; Dynamo KVBM table;
  llm-d offloading connector + GDS/NIXL roadmap) — verified 2026-08-25.

## 5. Benchmark-result honesty (the "never invent" rule)
All performance figures in this section are either (a) machine-computed [E]
this session (KV sizes, transfer times, 2(N−1)/N factors, TP AllReduce bytes),
or (b) **project-reported** and labeled as such: UCCL 2.5×/3.7× AllReduce
(README), DeepEP "matches/exceeds bandwidth limits" (README, V3 config),
llm-d v0.5 ~3.1k tok/s/B200 & 50k tok/s 16×16 P/D (release notes). None are
presented as independent measurements. [19](19-practical-labs.md) defines the
independent-reproduction protocol.

## Key Takeaways
1. One fetch date (2026-08-25) covers the whole fast-mover set — NCCL 2.31.2,
   NIXL v1.4.0, UCCL main, DeepEP V2, llm-d v0.5, engine docs.
2. Stable / recently-introduced / experimental / roadmap are separated (§2) —
   the 2.31 NCCL features, NIXL's newer backends, and UCCL's sub-project matrix
   are the "watch" items.
3. The provenance audit (§3) is 20 claims: 17 CONFIRMED (some with precision
   added), 2 CORRECTED (A18 line-rate convention; A19 the 4.8 ms label), 1
   explicitly-not-a-claim (A17 taxonomy warning, upheld).
4. The two corrections are the section's self-check: label drift and
   rounding drift, both caught and fixed before publish.
5. Vendor numbers are labeled vendor/project-reported, never independent (§5).

## Related
[15 NCCL vs NIXL vs UCCL](15-nccl-vs-nixl-vs-uccl.md) ·
[18 Architecture Decision Guide](18-architecture-decision-guide.md) ·
[README](README.md)

## References
See §1 for the full, dated source set. This page *is* the reference list for
the section.
