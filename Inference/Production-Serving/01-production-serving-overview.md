# Production Serving Overview — The Request Path and the Scheduling Hierarchy
`LAST_UPDATED: 2026-08-22` · Status: core page · Section home for the
**Production LLM Serving, Routing & Scheduling** handbook.

## 30-Second Explanation
A production LLM platform is not "a model behind an API." It is a **chain of
schedulers**, each deciding at a different granularity:

```
User / Agent
  ↓
L0  API Gateway        auth, quotas, model-name routing, retries     (per account)
  ↓
L1  LLM Router         pick WHICH replica/pool runs this request     (per request)
  ↓
L2  Engine Scheduler   pick WHICH requests run THIS iteration        (per decode step)
  ↓
L3  Cluster Autoscaler pick HOW MANY replicas exist                  (per minute)
```

The core principle of the whole section: **do not balance requests — balance
remaining work** (see [02-requests-are-not-equal](02-requests-are-not-equal.md)).
Every layer above exists because the layer below cannot see the whole picture:
the gateway doesn't know GPU state, the router doesn't schedule iterations, the
engine doesn't know the other replicas, and none of them can add GPUs.

## What each level owns

| Level | Scope | Timescale | Decides | Concrete examples |
|---|---|---|---|---|
| **L0 Gateway** | tenant/account | per request (ms) | authN/Z, per-tenant RPM/TPM quota, model-name → pool mapping, retry policy | LiteLLM proxy, Envoy AI Gateway, Kong/NGINX + auth plugin |
| **L1 Router** | replica pool | per request (ms budget) | which replica (or P/D pair) serves this request; admission | llm-d EPP, Dynamo router, SGLang router, Gateway API Inference Extension |
| **L2 Engine** | one replica | per iteration (5–50 ms) | which queued/running requests get this step's compute; preemption; KV paging | vLLM, SGLang, TensorRT-LLM schedulers |
| **L3 Autoscaler** | cluster | per minute | replica count per pool; capacity shape (P/D ratio, hardware class) | K8s HPA/KEDA on custom metrics, Dynamo SLA planner |

Two properties make this hierarchy work:
1. **Information decreases as you go up.** L2 sees per-token state; L1 sees
   per-replica scalar summaries; L3 sees minutes-scale aggregates. Each level
   must make good decisions on *lossy* state — this is why L1 scoring uses
   cheap scalar signals, not batch internals
   (see [06-router-architectures](06-router-architectures.md)).
2. **Authority decreases as you go down.** L3 cannot route a request; L1
   cannot preempt a running decode; L0 cannot see KV pressure. Designs that
   violate this (router trying to shape chunk schedules, gateway doing
   KV-aware routing) collapse under their own coupling.

## The feedback loop
Observability flows back **up** the hierarchy: engines export per-replica
metrics (queue depth, KV utilization, cache hit rate, TTFT/TPOT histograms),
the router consumes the scalars it needs at ≥10 Hz, and the autoscaler consumes
minutes-scale aggregates (goodput at SLO, KV headroom trend). See
[12-observability-and-slos](12-observability-and-slos.md). A platform where
metrics flow but no layer *acts* on them is load-balanced by hope.

## The running example in this section
The home-lab stack documented across this Wiki is a minimal instance of the
full hierarchy:

- **L0**: LiteLLM gateway (`127.0.0.1:4000`) — auth, per-key RPM/TPM quotas.
- **L1**: LiteLLM routing strategies today; the labs in
  [16-labs](16-labs.md) build toward remaining-work routing.
- **L2**: two vLLM engines — DeepSeek V4 Flash @ `10.1.1.51:8888`
  (2× DGX Spark GB10) and Qwen3.8-27B @ `10.1.1.60:8888` (RTX 5090).
- **L3**: manual (a human reads dashboards and starts containers).

Two production workloads run on it: the **Hermes agent** (primary model Qwen,
delegate DeepSeek — profile `default`; invertible via profile `deepseek-main`)
and this Wiki's evaluator workflow. Labs reference this stack throughout.

## 80/20
If you read one page: requests differ by orders of magnitude in remaining work,
so every scheduling level must estimate *work*, not count *requests*. L0
protects tenants, L1 places requests, L2 batches iterations, L3 adds capacity —
and the whole system is only as good as the signals flowing upward.

## How to read this section
- **Foundations (02–05)**: why requests are unequal, how to estimate remaining
  work, the queueing theory that governs latency, and the policy zoo.
- **Mechanisms (06–11)**: router architectures, the engine's own scheduler,
  cache-aware routing, P/D-disaggregated routing, admission control,
  autoscaling.
- **Operations (12–16)**: metrics and SLOs, multi-tenancy, a comparison matrix
  of production routers, failure modes, and ten hands-on labs.

Numbers tagged [E] are Python-verified (audit trail referenced per page);
[F] = fetched primary source; [A] = engineering assumption; [I] = inference.
The mathematically rigorous treatment of routing signals lives in the companion
deep-dive: `../Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md` — this
section cites it instead of re-deriving it.

## Related
`../The-Life-of-a-Token.md` · `../Continuous-Batching.md` ·
`../Prefill-Decode-Disaggregation.md` · `../../GPU-Systems/Load-Balancing.md` ·
`../../Serving-Engines/README.md` · `../Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md`

## Key Takeaways
1. Production serving is a **hierarchy of schedulers** (L0–L3) with decreasing
   information and increasing scope.
2. The unifying principle: **balance remaining work, not requests**.
3. Signals must flow upward (metrics) for decisions to flow downward (routing,
   batching, scaling) — observability is part of the control loop, not an
   afterthought.
