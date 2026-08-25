# Practical Labs
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.
Commands target the 2026-08 snapshot (NCCL 2.31.x, NIXL v1.4.0, UCCL main,
nccl-tests master). Every command: **what it does → expected output → what to
look for → common failure mode**.

## 1. NCCL with nccl-tests
### 1.0 Build
```bash
git clone https://github.com/NVIDIA/nccl-tests.git && cd nccl-tests
make -j MPI=1                 # what: builds all_reduce_perf etc. (+ MPI if MPI=1)
                               # expected: build/bin/{all_reduce_perf,all_gather_perf,...}
                               # look for: clean build, no "NCCL not found" (link system NCCL or set NCCL_DIR)
                               # failure: "NCCL.h not found" → install the NCCL dev package or -DNCCL_DIR
```
### 1.1 Single-GPU-node tests (1, 2, 8 GPUs)
```bash
./build/bin/all_reduce_perf -b 1K -e 1G -f 4 -g 1    # -g: GPUs per process
./build/bin/all_reduce_perf -b 1K -e 1G -f 4 -g 2
./build/bin/all_reduce_perf -b 1K -e 1G -f 4 -g 8
# what: sweeps sizes 1K→1G (×4 steps) for AllReduce; -g N = N GPUs
# expected: a table per run
# look for: busbw plateauing near the link's effective bandwidth
#   (NVLink ~900 GB/s-class; PCIe lower); algbw growing with N while busbw stays flat
# failure: busbw in the single-digit GB/s with 8 GPUs → transport fell back
#   (check `NCCL_DEBUG=INFO` for "Using network Socket")
```
Other collectives: `all_gather_perf`, `reduce_scatter_perf`, `broadcast_perf` —
same flags, different ops; run the battery, not just AllReduce ([16 §2]).
### 1.2 Two-node / multi-node MPI
```bash
# node A (rank 0):  # node B (rank 1):
mpirun -np 16 -npernode 8 \
  -H nodeA:8,nodeB:8 \
  --mca btl_tcp_if_include eth0 \
  ./build/bin/all_reduce_perf -b 1K -e 1G -f 4
# what: 16 ranks across 2 nodes via MPI; the OOB/bootstrap uses eth0
# expected: an 8-GPU-per-node table, busbw ~ inter-node effective bandwidth
# look for: the intra-node vs inter-node gap; NVLS "enabled" lines when in-domain
# failure: hang at init → OOB network split (NCCL_SOCKET_IFNAME / MPI interface);
#   "bootstrap" timeouts across firewalls
```
Single-process-per-GPU (no MPI): `NCCL_COMM_BLOCKING=1 ./all_reduce_perf -g 16`
on a 16-GPU node, or torchrun-style launch [I: nccl-tests launch modes].

## 2. Reading nccl-tests output
```
#    size     count    type   redop    root   algbw   busbw   #wrong
#     (B)     (floats)                              (GB/s)  (GB/s)
       8192      2048     float     none     -0    0.004   0.004      N/A
      32768       8192     float     none     -0    0.017   0.030      N/A
     131072      32768     float     none     -0    0.066   0.115      N/A
     524288     131072     float     none     -0    0.224   0.392      N/A
   2097152     524288     float     none     -0    0.744   1.302      N/A
```
- **size** — bytes moved by the collective (per rank's buffer).
- **count** — element count (size / element-size).
- **time/algbw** — the app-visible bandwidth: `size / time`.
- **busbw** — the *link*-utilization bandwidth: for AllReduce,
  `algbw × 2(N−1)/N` [E: factors from 02 — 1.0 @ N=2, 1.75 @ N=8, 1.969 @ N=64,
  1.998 @ N=1024]. **busbw is the number to compare against the physical link**
  — algbw grows with N; busbw should not exceed the link
  [F: nccl-tests README; 16 §3].
- **#wrong** — correctness check (N/A for reduce-none ops).
The α/β crossover is visible in the table: algbw rises slowly at small sizes
(latency-bound), then climbs toward the plateau (bandwidth-bound)
([02 §3; 16 §4](16-performance-benchmarking.md)).

## 3. NIXL lab (two-node, GPU→GPU)
```bash
# both nodes:
pip install nixl           # what: installs the NIXL Python API + libs (incl. UCX)
                           # expected: nixl importable; CUDA 12/13 backend auto-selected
                           # look for: the correct CUDA backend for your PyTorch build
                           # failure: import error → match the CUDA version to PyTorch's
```
Minimal two-GPU transfer (official examples shape; prefer the repo's
`examples/` for the live API):
```text
GPU 0                              GPU 1
 ├── create agent                   ├── create agent
 ├── register HBM buffer (VRAM)     ├── register HBM buffer (VRAM)
 ├── getPublicData / conn info  ───► ├── loadRemoteMD
 ├── build READ/WRITE desc    ◄───── ┘
 ├── postXfer (async)
 │      └── RDMA over GDR  ─────────►  bytes land in GPU1 HBM
 └── checkXfer → DONE (+ notification to app)
```
```python
# what: agent + registration + one-sided write + poll (shape of the real API;
#       exact signatures from the repo examples / python_api.md)
import nixl
agent   = nixl.Agent("prefill")           # NB API entry
handle  = agent.register_memory(kvp_hbm, mem_type="VRAM")
# exchange metadata with the peer agent (point-to-point or via ETCD), then:
req     = agent.create_xfer("WRITE", local_desc, remote_desc, remote_agent)
agent.post_xfer(req)                      # async — returns immediately
while agent.check_xfer(req) != "DONE": pass
# expected: DONE; GPU1's buffer holds the prefill KV
# look for: transfer time ≈ bytes / link BW (4.0 GiB @ 50 GB/s ≈ 85.9 ms [E])
# failure: stuck INPROG → backend selection / metadata / notification support
#   ([07 §4; 17 §5](07-nixl-deep-dive.md))
```
### 3.1 NIXLBench
```bash
# from the repo: benchmark/nixlbench (README there is the authoritative guide)
nixlbench --mem gpu --mem-size 1G --iter 100   # (illustrative flags; see docs)
# what: NIXL's official microbenchmark — latency + bandwidth across backends
# expected: per-backend latency/bandwidth numbers
# look for: the RDMA/UCX backend hitting near line-rate; setup-overhead column
# failure: numbers far below the app → micro vs app gap (setup, chunking,
#   overlap) [16 §1; 08 §6]
```
KV-specific: **KVBench** (`benchmark/kvbench/docs`) for KV-shaped workloads —
the "if available, include KV-specific benchmarking" requirement
[../Networking/README.md; F: NIXL tree].

## 4. UCCL lab
```bash
git clone https://github.com/uccl-project/uccl.git && cd uccl
source scripts/bootstrap.sh     # what: uv + py3.12 venv + dev tools (or conda path)
# then per sub-project:
#  collective/rdma  → run nccl-tests against UCCL-Tran on your IB/RoCE fabric
#  p2p              → P2P throughput on RDMA/GPU-IPC
#  ep               → DeepEP-compatible dispatch/combine on MoE
```
- **UCCL-Collective (R DMA)**: run the *same* nccl-tests sweep as §1.1 but with
  the UCCL-Tran library, then compare busbw to NCCL on the **identical** fabric
  and sizes — a reproducible NCCL-vs-UCCL comparison.
- **What to look for**: where UCCL-Tran wins (its design targets: multi-path /
  lossy / multi-vendor) and where it ties NCCL; record both.
- **Labeling discipline** (the user's requirement):
  ```text
  Upstream project-reported result      ← UCCL README's 2.5×/3.7× AllReduce figures
  Independently reproducible benchmark  ← your §4 nccl-tests A/B on YOUR fabric
  ```
  Never present the project-reported numbers as your own [10 §1; 14 §5].
- **UCCL-EP**: run the EP sub-project's dispatch/combine on a MoE layer;
  compare against DeepEP (if NVIDIA/IB) for the "reproducible vs NCCL/DeepEP"
  comparison [14 §5].
- **Common failure mode**: wrong sub-project for the NIC class (rdma vs efa vs
  afxdp) → [09 §6; 17 §5](09-uccl-deep-dive.md).

## 5. Benchmark methodology (the fair framework)
- **Microbenchmarks** measure the communication subsystem (nccl-tests,
  NIXLBench, ucx_perftest, ib_write_bw). **Application benchmarks** measure the
  actual LLM (TTFT, ITL, tokens/sec, step time, MFU, MoE throughput, KV-transfer
  latency) [16 §1].
- **Sweep** sizes 1 KB → 1 GB (the 16 §2 list) and scales 2/8/2/4 nodes.
- **Capture** latency, algbw, busbw, goodput, GPU/NIC/CPU utilization, tail
  (p99/p999), setup overhead.
- **Workload battery** — training AllReduce, TP AllReduce/AllGather, MoE
  all-to-all (with & without imbalance), P/D KV transfer — *not* AllReduce only
  [16 §2].
- **Hold constant**: fabric, topology, build, protocol, overlap policy — vary
  one thing at a time.
- **Connect to app metrics** — every micro number states the app-metric it
  feeds (step time, TTFT, tok/s) [16 §1].

## Key Takeaways
1. nccl-tests is the NCCL lab: build, sweep 1K→1G on 1/2/8 GPUs, then 2-node
   MPI; read **busbw** (link view), not just algbw.
2. The 2(N−1)/N factor is why busbw stays flat as algbw grows with N
   [E: 02's table].
3. NIXL lab = agent → register → metadata → post → poll; NIXLBench for
   micro, KVBench for KV-shaped; prefer the repo's official examples.
4. UCCL lab = run the *same* nccl-tests sweep under UCCL-Tran vs NCCL on the
   same fabric; label project-reported vs independently reproduced.
5. A fair framework holds fabric/topology/build/protocol/overlap constant and
   reports the app-metric translation for every micro number.

## Related
[16 Performance Benchmarking](16-performance-benchmarking.md) ·
[17 Troubleshooting](17-troubleshooting.md) ·
`../Labs/README.md` · `../GPU-Systems/Labs.md`

## References
- nccl-tests — https://github.com/NVIDIA/nccl-tests (fetched 2026-08-25) [F]
- NIXL Python API + NIXLBench + KVBench —
  https://github.com/ai-dynamo/nixl/blob/main/docs/python_api.md,
  /benchmark/nixlbench, /benchmark/kvbench [F]
- UCCL sub-project READMEs (collective/rdma, efa, afxdp, p2p, ep) +
  scripts/bootstrap.sh [F]
- `../Networking/README.md`, `../Labs/README.md` (internal)
