# 17 — LLM Autoscaling for Reliability

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

Scaling an LLM platform correctly requires signals that reflect *actual serving
pressure* (tokens, queues, KV), not just CPU. Autoscaling is a reliability
control: if it reacts too late (cold start, model load) the platform misses SLOs;
if it scales too eagerly it wastes expensive GPUs. See also
`Inference/Production-Serving/11-autoscaling-and-capacity-planning.md`.

## Why CPU-based HPA is weak for LLMs

CPU utilization does not reflect the bottleneck. An LLM replica can be
**saturated on decode memory bandwidth or KV** while CPU is nearly idle (GPU does
the work), or **queuing requests** with spare CPU. Scaling on CPU therefore:
- misses the *real* saturation (KV/decode/memory),
- over-reacts to non-bottleneck noise,
- and fails to protect TTFT (the constraint that actually matters).

## Compare candidate signals

| Signal | What it reflects | Autoscaling usefulness |
|---|---|---|
| **CPU** | host work (tokenize, Python, scheduling) | weak — not the LLM bottleneck |
| **GPU utilization** | compute busy % | useful but not the whole story (decode is BW-bound) |
| **Queue depth** | waiting requests | strong leading indicator ([08](08-queueing-theory-for-llm-sre.md)) |
| **TTFT** | latency vs target | strong outcome signal — scale to hold TTFT |
| **KV utilization** | the scarce resource | strong capacity signal ([12](12-kv-cache-reliability.md)) |
| **Tokens/sec** | real throughput | moderate — needs SLO context |
| **Goodput** | requests meeting SLO ([03](03-goodput-vs-throughput.md)) | best *outcome* signal |

**Best practice** ([I]): scale on a *combination* — queue depth / KV utilization
(hard capacity) plus demand (tokens/sec), gated by TTFT (outcome). Autoscale to
keep TTFT within SLO while leaving KV headroom; scale down when all signals drop.

## Scale-up / down mechanics and costs

| Event | What happens | Reliability concern |
|---|---|---|
| **Scale up** | add replicas | time to *ready* matters (see below) |
| **Scale down** | remove replicas | don't strand in-flight/queued work (drain) |
| **Cold start** | container → model loaded | minutes, not seconds |
| **Model load time** | weights to VRAM | the dominant cold-start cost |
| **GPU scheduling delay** | k8s places the GPU pod | scarce-schedulable capacity waits |
| **Image pull** | pull engine image | network-bound on a busy node |
| **Kernel compilation** | TRT-LLM/custom kernel build | one-time, can be long |
| **Cache warmup** | prefill/prefix cache warm | else first requests are slow |

Because **scale-up is slow** (model load ≫ request timescale), reactive autoscaling
alone is dangerous near SLO boundaries — by the time you react and load, the
budget is burnt.

## Autoscaling modes

- **Reactive** — respond to current metrics. Simple, but latency in the loop
  (slow to add GPUs) can miss TTFT SLO.
- **Predictive** — forecast demand from history/schedule (e.g. business hours,
  batch jobs) and scale *ahead*. Necessary when model-load time is long.
- **Scheduled** — scale on a fixed calendar (cron). Good for known periodic
  demand; combined with predictive/reactive for the rest.

## Reliability practice (`[I]`)

1. **Scale on queue/KV/goodput, not CPU.**
2. **Pre-warm capacity** for expected peaks (predictive/scheduled) — model-load
   latency makes pure reactive dangerous.
3. **Drain before scale-down** — let in-flight work finish, don't cut cables.
4. **Bound scale-down lag** to avoid oscillation in noisy demand.
5. **Keep headroom** under strict TTFT SLOs (ρ < 1, [08](08-queueing-theory-for-llm-sre.md)).

## Related

`03-goodput-vs-throughput.md` · `08-queueing-theory-for-llm-sre.md` ·
`12-kv-cache-reliability.md` · `18-kubernetes-for-llm-sre.md` ·
`Inference/Production-Serving/11-autoscaling-and-capacity-planning.md`

## Key takeaways

1. CPU-based HPA misses the LLM bottleneck (KV/decode/memory/queue).
2. Scale on queue depth, KV utilization, goodput, gated by TTFT.
3. Cold start / model load is the reliability bottleneck of scale-up — pre-warm.
4. Use predictive + scheduled + reactive together; drain before scale-down.
