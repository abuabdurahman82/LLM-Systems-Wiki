# Kubernetes & Slurm on AI Fabrics
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: Kubernetes network-plumbing (Multus/SR-IOV) docs, NVIDIA Network Operator, NCCL user guide, Slurm topology docs; fetched 2026-08-25.

## 30-Second Explanation
An AI pod needs **two networks at once**: the cluster management/service net (its `eth0`, normal
CNI) and a **secondary RDMA net** (`net1`) that reaches the GPU fabric at lossless speed. That
second dataplane is layered on with **Multus CNI** + an RDMA-capable secondary CNI (SR-IOV /
host-device/RDMA-shared), an **RDMA device plugin** to hand HCAs-or-VFs to pods, and a
**NetworkAttachmentDefinition** per fabric. On the HPC side, **Slurm schedules topologically** so a
job's ranks land *inside one fat-tree tier* (one leaf/block, then one partition) instead of being
scattered across spines — because every cross-spine hop adds latency to a latency-multiplying
collective. Both stacks exist to make **the scheduler respect the fabric**.

## The two-network model (Kubernetes)
### Pod networking model
```text
          POD
   ┌───────────────────┐
   │  eth0  (service   │  <- cluster net via default CNI (Calico/Cilium)
   │        net)       │     management, control, image pull, logs
   ├───────────────────┤
   │  net1  (RDMA       │  <- secondary net via Multus (secondary CNI)
   │        dataplane)  │     HCA/VF with a backend IP, GPUDirect path
   └───────────────────┘
```
**Multus CNI** is the meta-plugin that attaches that second interface; a pod references its
secondary network(s) through the `k8s.v1.cni.cncf.io/networks` annotation, naming a
**NetworkAttachmentDefinition** (the CR that defines the secondary network: type, master interface,
IPAM) [F: multus-cni]. `eth0` carries the management plane; `net1` carries gradients/collectives —
that split is the entire dataplane-isolation story.

### SR-IOV CNI / NVIDIA Network Operator
- **SR-IOV CNI + SR-IOV Network Device Plugin** carve the physical NIC into VFs and advertise them
  as allocatable resources [F: k8snetworkplumbingwg]. 
- The **NVIDIA Network Operator** automates the whole stack — NVIDIA drivers, the device plugin,
  and the secondary-network components — with CRDs like `NicClusterPolicy`, `HostDeviceNetwork`,
  and `IPoIBNetwork` to deliver RDMA + GPUDirect into pods [F: Mellanox/network-operator].
- The **RDMA shared device plugin** multiplexes many pods over the physical PF (`/dev/infiniband`)
  when per-pod VF isolation is overkill — a common choice for dedicated training clusters [F:
  k8s-rdma-shared-dev-plugin].

### RDMA device plugin & IPAM
The device plugin exposes each HCA/VF as an Extended Resource (e.g. `nvidia.com/gpu` +
`<reg>.com/rdma`), so the scheduler only places pods that asked for RDMA onto nodes that can serve
it. The backend (RDMA) IP comes from the NAD's **IPAM**: usually a **BGP-assigned /32** (routed
per-pod, ideal for RoCEv2 because each pod gets a routable address) or **host-local** (a static
range per node) [I: common NAD IPAM configs]. The *service* IP comes from the cluster net; these
are separate address pools, never conflated. In a rail-optimized fabric the backend IPs are often
placed so that each rail is a distinct subnet — keep the NAD's IPAM consistent with that so NCCL's
rail detection sees what you wired [I].

### Concrete NAD + annotation (the wiring in one example)
```yaml
# tenant-a-roce NAD: a secondary net on the RoCE fabric with its own IPAM
apiVersion: k8s.cni.cncf.io/v1
kind: NetworkAttachmentDefinition
metadata:
  name: tenant-a-roce
spec:
  config: |
    { "cniVersion": "0.3.1",
      "type": "sriov",
      "master": "ens1np0",              # HCA PF the VFs come from
      "ipam": { "type": "host-local", "subnet": "10.10.1.0/24" } }
```
```yaml
# pod asks for the secondary net (eth0 stays on the cluster CNI)
metadata:
  annotations:
    k8s.v1.cni.cncf.io/networks: tenant-a-roce   # -> pod.net1 = RDMA dataplane
    k8s.v1.cni.cncf.io/networks-status: ""        # (runtime fills in status)
```
That one annotation + NAD is the entire "second network" mechanism: Multus sees the annotation,
invokes the SR-IOV/host-device CNI for the secondary iface, and the pod ends up with `eth0`
(management) + `net1` (RDMA, IPAM-isolated per tenant) [F: multus-cni; config shape [A]].

### GPUDirect in containers
`nvidia-peermem` must be loaded on the **host kernel** (`modprobe nvidia-peermem`; the container
runtime must expose the GPU peer-memory device) so the GPU and the NIC's DMAs can see each
other's memory (peer-memory). Together with `NCCL_NET_GDR_LEVEL`, it lets data flow GPU→NIC→fabric
without a host bounce buffer, which is what makes containerized NCCL hit near-line-rate [F:
NCCL user guide; nvidia-peermem [A]]. Verify it engaged by checking `nvidia-smi topo -p2p` and that
NCCL reports a GDR-capable path rather than falling back to a host staging buffer [I].

## Topology-aware scheduling (Slurm)
Slurm models the network as a **tree** (`topology.conf` — `SwitchName`/switch hierarchy at each
level of the Clos) and can constrain allocation with `--switches`, `--exclusive=topo`,
`--segment`, and GRES GPU placement [F: Slurm topology docs]. The mapping that matters:
- **block ≈ leaf** (a coherent switch group with no spine hop between members),
- **partition ≈ rail** (for rail-optimized fabrics, ranks on one rail share a dedicated leaf plane)
  [I: mapping to the fat-tree/rail model in `./42` / `./38`].

### Worked placement example
```text
Fabric: 2-tier leaf-spine, 1:1, 16 spines.
  Each leaf: 16 uplinks (one to each of the 16 spines) + 16 downlinks (radix 32)
    → 8 leaves × 16 downlinks = 128 endpoint slots = 128 GPUs (8 GPUs/node,
      rail-optimized: one rail-NIC per GPU).  So one leaf = 16 endpoints = 2 nodes.
Desired: 16-GPU job (2 nodes × 8 GPUs)
   GOOD: both nodes' 16 endpoints under ONE leaf  → 0 spine hops between peers
   BAD : endpoints split leaf-A(8)/leaf-B(8)      → every collective crosses
          leaf-A → spine → leaf-B
```
**Scheduler job**, for example: `srun --switches=1 --exclusive=topo --nodes=2 --gpus-per-node=8
--ntasks-per-node=8 <job>` tells Slurm to keep the 2 nodes under one switch tier (`--switches=1`)
and place one rank per GPU/NIC (`--ntasks-per-node=8`) [F: Slurm topology/run options]. This puts
the whole job inside one leaf first.

### Why topology-aware placement matters
Cross-spine vs same-leaf traffic changes the **fraction of bytes that traverse spines** [I]. On a
1:1 fabric every hop is 100% utilized only if endpoints are spread; but for *latency-bound* AI
collectives, the cost of a spine hop is the added propagation/queueing delay on a path that is
already the critical tail.
[E] Ring AllReduce time = `2(n-1)/n · M/B + 2(n-1)·α`. The latency term grows **linearly in n**, so
co-locating ranks on few leaves keeps α small; scattering them across spines adds per-cross-spine
hops to the latency budget of *every* one of the many small collectives (tensor-parallel does ~2
AllReduces per layer [I]). A topology-unaware scheduler produces fragmented placements that
turn a rail-optimized fabric into a crossbar-thrasher: [I] expect measurably worse busbw and tail
latency when ranks straddle a power-of-two boundary the fabric was designed around.

### Why the scheduler placement changes network efficiency (cross-spine vs same-leaf)
- **Same-leaf traffic** stays under one leaf: no spine uplink is consumed, α stays minimal.
- **Cross-leaf traffic** consumes (and competes for) spine uplinks and adds a hop of store-and-forward
  latency per spine crossing [I]. With many collectives per step, even +1 µs of α × `2(n-1)` ring
  steps × dozens of collectives adds real step time [E mechanism; exact µs are config-specific and
  not fabricated here].
The practical rule: make the allocation *hit fabric power-of-two boundaries* (leaf/block/rail) so
the scheduler's choice of "where" becomes the network's choice of "how fast".

## "Scheduling respects the fabric" checklist
- [ ] `topology.conf` mirrors the real Clos: each leaf is a `SwitchName`/`Switch` entry; block-to-rail mapping documented [F: Slurm topology.conf].
- [ ] Topology-aware allocation enabled (`--switches`/`--segment`/`--exclusive=topo`) so a whole job lands in one tier when it fits.
- [ ] Job sizes aligned to fabric power-of-two blocks (leaf/block/rail) to avoid straddling spine boundaries.
- [ ] GRES + GPU count set (`--gpus-per-node`, `--ntasks-per-node`) so rank count matches NICs per node.
- [ ] Node/rank affinity (`--ntasks-per-node`, `--cpus-per-task`) keeps ranks on the NIC's NUMA node for GPUDirect.
- [ ] In K8s: each fabric has its own NAD; device plugin advertises the correct HCA/VF resource count.
- [ ] Verify after scheduling: measure nccl-tests busbw per placement; confirm it tracks 0.95·link [E].

## Related
- [47-security-multitenancy.md](./47-security-multitenancy.md) — device plugins, NAD per tenant, IPAM isolation.
- [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) — leaf/spine/rail arithmetic the placement maps onto.
- [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md) — rail semantics for the block≈leaf, partition≈rail mapping.
- [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md) — measuring whether placement actually helped (busbw).
- [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md) — what the placed collective actually moves.


## Key Takeaways
1. An AI pod needs two networks at once: `eth0` on the cluster/management net plus a secondary RDMA
   dataplane (`net1`) layered on with Multus + an RDMA-capable secondary CNI; that orchestration-net
   vs dataplane-net split is the entire dataplane-isolation story.
2. The mechanism is three pieces — an RDMA device plugin advertises HCAs/VFs as allocatable
   resources, a NetworkAttachmentDefinition defines the secondary network (type, master iface,
   IPAM), and the `k8s.v1.cni.cncf.io/networks` annotation attaches it: one annotation + one NAD is
   the whole "second network."
3. Backend RDMA IPs come from the NAD's IPAM (BGP-assigned /32 per-pod ideal for RoCEv2, or
   host-local); keep them a separate pool from service IPs and consistent with the rail subnets so
   NCCL's rail detection sees what you actually wired.
4. GPUDirect in containers needs `nvidia-peermem` loaded and the right `NCCL_NET_GDR_LEVEL`; verify
   with `nvidia-smi topo -p2p` and that NCCL reports a GDR-capable path instead of a host staging
   buffer.
5. Slurm's job is to make the scheduler respect the fabric: model the Clos as a tree in
   `topology.conf`, use `--switches`/`--exclusive=topo`, and align job sizes to fabric
   power-of-two blocks — co-locating ranks on one leaf keeps α small because the ring latency term
   `2(n-1)·α` grows linearly in n.

## References
- Kubernetes network-plumbing / Multus CNI docs — secondary networks and NADs.
- SR-IOV CNI + SR-IOV network device plugin (k8snetworkplumbingwg).
- NVIDIA Network Operator — NicClusterPolicy/HostDeviceNetwork/IPoIBNetwork CRDs.
- k8s-rdma-shared-dev-plugin — PF multiplexing for dedicated clusters.
- NCCL user guide — GPUDirect/GDR (`NCCL_NET_GDR_LEVEL`), rail detection.
- Slurm topology / topology.conf and run-option docs — `--switches`, `--exclusive=topo`, `--segment`.
- [E] Ring AllReduce time = 2(n-1)/n · M/B + 2(n-1)·α (latency term linear in n); busbw target
  0.95·link (busbw = algbw × 2(n-1)/n normalizes a saturated ring to link rate).
