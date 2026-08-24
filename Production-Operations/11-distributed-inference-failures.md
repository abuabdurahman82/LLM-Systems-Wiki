# 11 — Distributed Inference Failures

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

Distributed inference spreads one request across many GPUs (TP/PP/EP/DP). That
turns a *single-GPU* failure model into a **team-of-workers** model in which one
slow or lost participant can stall an entire request and, worse, cause a cluster
of requests to retry — a cascading failure.

## Why one slow worker can slow an entire distributed request

In **tensor parallelism (TP)** a single forward/backward step is *synchronised*
across ranks via collectives (AllReduce/AllGather). Every collective waits for
the **slowest rank** — so a single straggler directly inflates the latency of
*every* request that touches it. This is the fundamental reason distributed
inference has **tail-latency amplification**: the request is only as fast as its
slowest participant, and queues/interference make "slowest" worse than "average."

## Failure catalogue

| Failure | What it is | Typical signal |
|---|---|---|
| **Worker loss** | a rank/process dies | pod/process exit, connection refused |
| **Rank failure** | a specific rank errors out | NCCL rank error, CUDA error on that device |
| **NCCL timeout** | collective doesn't complete in time | `NCCL timeout`, watchdog abort |
| **Collective hang** | AllReduce/AllGather blocks forever | stuck request, no progress, high util on some ranks |
| **Network partition** | ranks can't reach each other | connection errors, timeout |
| **Slow rank / straggler** | one rank much slower | high latency despite healthy-looking aggregate |
| **Partial rack failure** | subset of nodes/GPUs lost | degraded TP/PP group, half the requests error |
| **KV transfer failure** | P/D disaggregation KV handoff fails | disaggregated prefill→decode handoff error |
| **P/D disaggregation failure** | prefill/decode pool issues | mismatch, KV handoff, scheduler imbalance |

## Failure implications per parallelism strategy (`[I]`)

| Strategy | Failure footprint | Implication |
|---|---|---|
| **TP** (tensor parallel) | one request spans N ranks in lockstep | any rank loss/hang kills the whole request; strongest tail coupling |
| **PP** (pipeline parallel) | request passes through stages | a slow stage adds latency; a stage loss stalls the pipeline |
| **EP** (expert parallel, MoE) | per-token all-to-all for experts | comm-bound; NCCL/all-to-all failures stall decode; straggler expert hurts |
| **DP** (data parallel) | each replica serves independent requests | most fault-tolerant: losing one replica just loses its requests (with replication) |

General rule: the more *internally synchronized* a strategy is (TP > PP > EP ≈
all-to-all per token), the more a single failure becomes a whole-request failure,
and the more important fast failure detection + restart becomes.

## Operational mitigations (`[I]`)

1. **Fast failure detection** — don't wait for a request to hang; monitor NCCL
   health, rank heartbeat, and collective progress.
2. **Straggler control** — watch per-rank latency and utilization; a hot/slow
   rank skews every TP request (`GPU-Systems/Tensor-Parallelism.md`).
3. **Timeouts with rollback** — bound NCCL/collective time and fail the request
   rather than hang it indefinitely.
4. **Replicate across DP** — keep data-parallel copies so losing a TP group
   doesn't lose all of a model class.
5. **Drain-and-rebuild** — on worker loss, rebuild the group cleanly; a
   half-dead group causes repeated retries → retry storm ([14](14-retries-timeouts-circuit-breakers.md)).
6. **Trace the request** across ranks with rank/replica ids ([23](23-llm-tracing.md)).

## Related

`09-llm-failure-taxonomy.md` · `10-gpu-reliability.md` ·
`14-retries-timeouts-circuit-breakers.md` · `Distributed-Inference/README.md` ·
`GPU-Systems/Tensor-Parallelism.md` · `GPU-Systems/MoE-Expert-Parallelism.md` ·
`Networking/README.md` (NCCL/NVLink)

## Key takeaways

1. TP couples every request to its slowest rank — tail-latency amplification.
2. One slow/lost worker can stall an entire distributed request and cascade into
   retries.
3. TP > PP > EP ≈ all-to-all differ in failure footprint and coupling.
4. Fast detection, bounded timeouts, DP replication and clean group rebuild
   are the mitigations.
