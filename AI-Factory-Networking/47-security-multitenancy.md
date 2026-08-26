# Security & Multi-Tenancy in AI Fabrics
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: NVIDIA InfiniBand security overview & guidelines, UEC 1.0 spec (TSS), Kubernetes network-plumbing docs, NVIDIA Network Operator; fetched 2026-08-25.

## 30-Second Explanation
A GPU cloud that sells **RDMA to many tenants** must make tenants unable to read or disrupt each
other *on the fabric*, not just at the host. There is no free lunch: **InfiniBand** has native
partitioning (P_Key, M_Key, Q_Key) but **no in-fabric authentication — any port can claim any
identity** [F: NVIDIA IB security doc]; **RoCE/Ethernet** isolates with VLAN/VRF + ACLs + QoS
classes, but its losslessness machinery (PFC/ECN) is per-traffic-class, so you must not let two
tenants share one PFC domain; and the **newest transports (UET)** ship security as a first-class
spec feature (TSS: AEAD, secure domains). This page maps isolation onto each fabric, then gives a
"GPU cloud exposing RDMA to tenants safely" architecture and checklist.

## Threat model (what "tenant isolation" must stop)
Before the fabric, define the adversaries [I]:
- **Rogue tenant reads** — one tenant's NIC sniffing another's RDMA traffic on a shared link.
- **Rogue tenant disrupts** — one tenant's incast/lossless behavior pausing or congesting another's.
- **Rogue identity** — a port claiming another node's GUID/LID/MAC and splitting its traffic.
- **Host compromise** — a broken tenant VM issuing privileged management frames.
Each fabric below answers these differently; none answers "reads" without extra crypto [I/F].

### Isolation mechanisms vs. what they stop
| Mechanism | Stops | Does NOT stop |
|---|---|---|
| P_Key partition (IB) | tenant→tenant reachability | snooping within a partition |
| M_Key (IB) | rogue Subnet-Management ops | data-plane eavesdrop |
| VLAN/VRF (Eth) | tenant→tenant routing | sharing losslessness / QoS |
| VXLAN/EVPN overlay | tenant→tenant L2/L3 | buffer/LOS interactions |
| per-tenant DSCP/TC | shared PFC/ECN coupling [A] | — |
| SR-IOV VF | device-level sharing | misconfig / VF escape [I] |
| MACsec / TSS crypto | data-plane eavesdrop | nothing (adds cost/keys) |

## Isolation per fabric
### InfiniBand (native)
- **P_Key partitioning** — every BTH carries a 16-bit P_Key; receivers filter on validity; the SM
  can **enforce** on switch ports so only allowed partitions forward [F: NVIDIA IB security doc].
  Default partition `0x7FFF` includes all nodes; tenants move to admin partitions `0x0001–0x7FFE`.
  This answers "tenant can't reach tenant" but not "tenant can't snoop within its own partition".
- **M_Key (management key)** — gates **Subnet Management** access: who may send SM/SMP
  management traffic and who may change a port's LID/state or issue privileged subnet
  operations. (Memory-window access is a *data-plane* key — R_Key/L_Key + protection
  domain — not M_Key.) M_Key isolation keeps non-privileged nodes from running rogue
  subnet-management operations.
- **Q_Key (UD)** — for Unreliable Datagram service, the Q_Key in the DETH validates who may talk to
  a QP; part of UD encapsulation isolation.
- **SM-level controls** — the Subnet Manager sets partitions, QoS/SL policy, routing; the SM is the
  single control point, so *controlling the SM is controlling the fabric*. Protect SM/UFM access,
  and keep its P_Key full-membership privileged.
- **Hard truth:** P_Key/M_Key/Q_Key are *isolation* and *capability gating*, not *authentication/
  encryption* — InfiniBand has no built-in in-fabric authentication and typically no per-tenant
  encryption; anyone with physical/switch access and the right P_Key can read traffic. [F: NVIDIA
  IB security doc]

### Ethernet / RoCE (segmentation + QoS)
- **VLAN / VRF** — split tenants at L2 (VLAN) and L3 (VRF) so one tenant cannot route into another.
- **ACLs** — filter between tenant segments and block unwanted control-plane traffic (e.g. unknown
  multicast, management protocols).
- **VXLAN / EVPN overlays** — scale-out L2/L3 segmentation over the shared underlay; each tenant
  gets its own VNI/VRF. ECN bits are preserved across VXLAN encap/decap (RFC 6040-style) so DCQCN
  still works over the overlay [F: IP Infusion VXLAN/DCQCN]. Overlays isolate *routing*, not *LOS*.
- **QoS class isolation** — **PFC and ECN are per-traffic-class (per-TC), not per-tenant by
  default.** Two tenants placed in the *same* lossless TC share one PFC domain: a slow receiver in
  tenant A pauses the shared priority and stalls tenant B ([I] — this is the PFC head-of-line
  mechanism; [F: 802.1Qbb per-priority pause]). Assign each tenant its own DSCP→TC/priority so
  losslessness is *not* shared [A]. This is the Ethernet fabric's version of P_Key.
- **Optional crypto** — for "tenant can't snoop on links in their own segment", layer **MACsec**
  (L2) or route over an encrypted overlay [I]; RoCEv2 itself has no native encryption.

### Virtualization (host-level)
- **SR-IOV VF/PF** — carve a physical NIC into virtual functions; each tenant pod gets a VF with
  its own queues/priority. VFs are the unit you hand out.
- **vDPA** — a virtio data-path-acceleration model that passes RDMA-capable devices to VMs/pods
  with near-native performance, retaining some paravirt isolation benefits.
- **GPU RDMA passthrough** — pass the GPU (and its RDMA NIC path) through to the VM so GPUDirect
  works inside the tenant VM.
- **IOMMU** — mandatory for safe device assignment; note IOMMU in *passthrough* mode is what GPUDirect
  needs [F: NVIDIA GDS/GPU troubleshooting], which trades some DMA isolation for performance — keep
  `iommu=pt` only where the whole node is trusted.

### Kubernetes (orchestration level)
- **Device plugins** expose RDMA VFs as allocatable resources (e.g. `nvidia.com/gpu`,
  `intel.com/sriov`, or the RDMA shared device plugin) so the scheduler can place pods that need
  RDMA onto nodes with HCAs [F: sriov-network-device-plugin / Mellanox k8s-rdma-shared-dev-plugin].
- **NetworkAttachmentDefinition (NAD) per tenant** — the Multus CR that defines a secondary
  network (type, master iface, IPAM); each tenant references its own NAD via the
  `k8s.v1.cni.cncf.io/networks` annotation, giving per-tenant dataplane isolation [F: multus-cni].
- **IPAM isolation** — each tenant's NAD configures its own IPAM (host-local / BGP / range), so
  backend RDMA IPs do not collide across tenants and one tenant cannot masquerade in another's
  address space.

## GPU cloud exposing RDMA to tenants — architecture
```text
Tenant A (P_Key A / VRF A / TC A)        Tenant B (P_Key B / VRF B / TC B)
        │ HCA VF via device plugin               │ HCA VF via device plugin
        ▼ NAD-a (host-local IPAM)                ▼ NAD-b (host-local IPAM)
   [nvidia-peermem GPU RDMA]                [nvidia-peermem GPU RDMA]
        │                                        │
        ▼                                        ▼
   ┌─────────────────── leaf switch ─────────────────────┐
   │  P_Key enforcement (IB) / ACL+VLAN+VRF (Eth)        │
   │  per-tenant DSCP→TC  ·  per-tenant PFC isolation    │
   └───────────────────────┬─────────────────────────────┘
                           ▼
                spine / multi-plane fabric
        (no shared PFC domain between tenants)   [A]
```
Checklist [A] for a safe RDMA-exposing GPU cloud:
- [ ] **Per-tenant P_Key (IB)** or **per-tenant VRF/VLAN (Eth)** so control/data plane are partitioned.
- [ ] **Per-tenant DSCP/TC** so each tenant's lossless queues are independent — never share one PFC domain between tenants [A].
- [ ] **Monitoring isolation** — per-tenant counters/telemetry (PFC/ECN, utilization) not crossed.
- [ ] **No shared PFC domain between tenants** — even if two tenants run RoCE, keep their traffic classes separate [A].
- [ ] **Fabric authentication where it matters** — see residual risks below; add MACsec/802.1X on Ethernet, or move to a security-inclusive transport.
- [ ] **Host hardening** — IOMMU appropriate to trust, `nvidia-peermem` only where the node is trusted [I].

## Residual risks
- **InfiniBand has no in-fabric authentication**: P_Key numbering is not a secret and traversal is
  not authenticated; a rogue endpoint on the right partition can snoop. [F: NVIDIA IB security doc]
- **UET ships TSS** — end-to-end Authenticated Encryption (AEAD, default AES-GCM-256 with 16B ICV),
  Secure Domains with group keying, and replay protection are **in the UET spec** [F: UEC 1.0 spec
  §3.4 / author paper §3.4]. That is a meaningful step up from IB/RoCE's reliance on L2 measures —
  but as of 2026-08 TSS hardware is early [I]; treat it as roadmap-grade for most clouds.
- **O(N) state vs connectionless** — UET deliberately avoids per-endpoint connection state via
  ephemeral PDCs, which is what makes its virtualization story scale; the tradeoff is that
  per-tenant ordering/state semantics differ from connected QPs [F: UEC spec §3.1.1].
- **Single-controller trust (IB SM / fabric manager)** — a compromised SM reshapes partitions and
  routing; protect it as a crown jewel [I].

## Related
- [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md) — P_Key mismatch as a failure mode.
- [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md) — DSCP/TC and why shared TCs break isolation.
- [48-kubernetes-slurm.md](./48-kubernetes-slurm.md) — device plugins, NADs, and IPAM in detail.
- [31-uetch-deep-dive.md](./31-uetch-deep-dive.md) — UET TSS, secure domains, connectionless PDCs.
- [49-design-decision-tree.md](./49-design-decision-tree.md) — IB vs RoCE vs UET security posture in context.


## Key Takeaways
1. Tenant isolation *on the fabric* is not host isolation: a GPU cloud selling RDMA to many tenants
   must stop reads, disruption, identity spoof, and host-compromise on the wire, and there is no
   free lunch — IB has native partitioning but no in-fabric authentication.
2. InfiniBand isolates with P_Key (reachability, default 0x7FFF), M_Key (Subnet-Management access),
   and Q_Key (UD); the SM is the single control point — controlling the SM is controlling the
   fabric — but none of these authenticates or encrypts against in-partition snooping.
3. Ethernet/RoCE isolates with VLAN/VRF + ACLs + per-tenant DSCP→TC; critically, PFC and ECN are
   *per-traffic-class*, so two tenants sharing one lossless TC share one PFC domain (a slow
   receiver in one can pause and stall the other) — never share a PFC domain between tenants.
4. Virtualize with SR-IOV VFs / vDPA / GPU passthrough behind the right IOMMU mode, and orchestrate
   with per-tenant NetworkAttachmentDefinitions + device plugins + isolated IPAM so backend RDMA
   addresses and dataplanes stay separate.
5. Crypto is the step from isolation to confidentiality: MACsec or encrypted overlays on Ethernet
   (RoCEv2 has no native encryption); UET's TSS (AEAD AES-GCM-256, secure domains, replay
   protection) is in-spec but early silicon as of mid-2026.

## References
- NVIDIA InfiniBand security overview & guidelines — P_Key/M_Key/Q_Key, no in-fabric authentication.
- IEEE 802.1Qbb — per-priority pause (why tenants sharing a TC share a PFC domain).
- IP Infusion VXLAN/DCQCN — ECN-bit preservation across overlays (RFC 6040-style).
- Kubernetes network-plumbing / multus-cni docs — NADs, per-tenant annotation + IPAM.
- SR-IOV network device plugin; NVIDIA Network Operator / k8s-rdma-shared-dev-plugin — HCA/VF allocation.
- UEC 1.0 spec §3.4 (TSS) and §3.1.1 — AEAD, secure domains, connectionless PDCs.
