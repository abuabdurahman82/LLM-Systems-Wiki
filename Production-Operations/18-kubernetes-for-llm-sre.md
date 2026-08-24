# 18 — Kubernetes for LLM SRE

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

Kubernetes is the orchestration layer of the reliability stack. For LLM
workloads its job is harder than for web apps: GPUs are scarce, models are
heavy, startup is slow, and a badly designed **probe can make an outage worse**
— removing a healthy-but-slow-loading replica is worse than leaving it to warm up.

## Probes

| Probe | Question it answers | For LLM workloads |
|---|---|---|
| **Startup probe** | is the process *starting*? | model load / kernel compile can take minutes; a generous startup probe avoids killing warm-up |
| **Liveness probe** | is the process *alive*? | should only reflect "process alive / not deadlocked" — see [19](19-llm-health-checks.md) |
| **Readiness probe** | is it *ready to receive traffic*? | should reflect *model loaded + enough resources*, not just process up |

### Why poorly designed liveness probes make outages worse

If the liveness probe is too strict (e.g. it fails when the replica is merely
*busy* or slow-loading), k8s **kills and restarts** a replica that was actually
working. That: (1) discards in-flight KV and requests, (2) forces an expensive
re-load, (3) removes capacity precisely when under load → cascading shortage and
retries. **Liveness must track "alive," not "healthy/latency-SLO"**; readiness
should carry the load/health logic, and deep health belongs in the service, not
in k8s probes ([19](19-llm-health-checks.md)).

## Workload kinds & scheduling

| Concept | Purpose | LLM note |
|---|---|---|
| **PodDisruptionBudget (PDB)** | cap how many pods can be down during voluntary disruptions | protect GPU pods during node drains/updates |
| **PriorityClass** | order scheduling/preemption | interactive > batch; admission ties in ([13](13-overload-protection.md)) |
| **Node affinity / taints & tolerations** | bind pods to GPU nodes | keep inference on GPU nodes; avoid CPU-scheduled inference |
| **GPU scheduling** | request `nvidia.com/gpu` via Device Plugin | via GPU Operator; scarce, wait-sensitive ([17](17-llm-autoscaling-reliability.md)) |
| **Rolling updates** | gradual pod replacement | use maxUnavailable=0 / small surge so capacity persists |
| **StatefulSet (where applicable)** | stable identity/ordering | for sharded/ranked inference where identity matters |
| **Deployment** | stateless replicas | default for inference replicas behind the router |
| **Job** | run-to-completion | for eval/offline/batch workloads, canaries |

## GPU Operator

The **NVIDIA GPU Operator** (`[F]` NVIDIA docs) automates the deployment of the
GPU driver, the device plugin, the container runtime hook, DCGM/dcgm-exporter,
and other components into Kubernetes as their own DaemonSets/StatefulSets,
instead of requiring manual driver install per node. For an LLM SRE this means:
GPU nodes self-provision driver + device plugin + telemetry, and `nvidia.com/gpu`
becomes schedulable consistently. (Details/versions verified against official
NVIDIA GPU Operator docs; treat version specifics as `[F]` only against the
current doc.)

## Reliability practice (`[I]`)

1. **Right-sizing probes** — startup generous, liveness = alive only, readiness =
   model ready + resources; never make liveness tip on load.
2. **PDB + PriorityClass** on GPU workloads so maintenance doesn't evaporate capacity.
3. **Rolling updates** that preserve capacity (surge or maxUnavailable=0) and
   respect cache warm-up.
4. **Drain before removal** — coordinate scale-down with in-flight completion
   ([17](17-llm-autoscaling-reliability.md)).
5. **Rely on GPU Operator** for driver/plugin/telemetry provisioning instead of
   manual node surgery.

## Related

`13-overload-protection.md` · `17-llm-autoscaling-reliability.md` ·
`19-llm-health-checks.md` · `20-llm-observability-stack.md` ·
`29-chaos-engineering-for-llms.md`

## Key takeaways

1. Probes must be right-sized: a strict liveness probe can *cause* an outage by
   killing busy/slow-loading replicas.
2. Liveness = alive; readiness = model ready + resources; deep health is in-service.
3. GPU Operator automates driver/device-plugin/telemetry for GPU nodes.
4. Use PDB/priority/rolling-update discipline to preserve GPU capacity during
   maintenance.
