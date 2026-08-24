# Production Operations — LLM Reliability, SRE & Production Operations Engineering

`LAST_UPDATED: 2026-08-23` · Status: core section · Home for the
**LLM Reliability, SRE & Production Operations Engineering** handbook.

> **How to keep production LLM systems fast, available, correct, cost-efficient, and recoverable.**

## 30-Second Explanation

Reliability for an LLM system is **not** the same as reliability for a normal
REST service. A normal request is *request → compute → response*. An LLM
request is *tokenize → queue → prefill → KV-cache allocation → decode loop →
possibly tools / RAG / agents → streamed response* — and every one of those
stages introduces its own failure modes. A "slow answer" is not one thing; it
can be an overloaded gateway, router imbalance, prefill congestion, decode
contention, KV exhaustion, GPU throttling, an NCCL issue, slow retrieval, an
overloaded vector DB, a tool timeout, a downstream provider degredation, an
overlong context, or just network congestion.

**Reliability is the discipline of making the user-visible outcome good **
**despite** any single layer in that stack failing.

## The reliability stack

```
USER EXPERIENCE
       ↓
MODEL QUALITY
       ↓
AGENT / RAG / HARNESS
       ↓
INFERENCE ENGINE
       ↓
GPU / MEMORY
       ↓
NETWORK
       ↓
STORAGE
       ↓
KUBERNETES / ORCHESTRATION
       ↓
PHYSICAL INFRASTRUCTURE
```

A user-visible failure can originate at **any** layer. Deciding "which layer is
failing" is the central skill of the operations engineer, and it is why good
**observability** (see [20-llm-observability-stack](20-llm-observability-stack.md))
is not optional. The same symptom recurs throughout this section: *a failure in
one layer looks like a symptom in another.*

## What "reliable" means for an LLM system (the capstone)

A production LLM system is **reliable** only when it is all four at once:

- it **responds** (availability)
- **within the required latency** (performance)
- **with acceptable quality** (correctness / model quality)
- **without violating resource or cost constraints** (capacity / cost)

The capstone page [41-the-reliable-llm-system](41-the-reliable-llm-system.md)
turns these into the final mental model.

## How this section is organized

- **Part 1 (pages 01–07) — Foundations & metrics:** what reliability means,
  SLI/SLO/SLA, goodput, the four golden signals, latency engineering, error
  budgets, capacity planning.
- **Part 2 (pages 08–16) — Failure & infrastructure engineering:** queueing,
  failure taxonomy, GPU reliability, distributed inference failures, KV-cache
  reliability, overload/admission control, retries/timeouts/circuit breakers,
  fallback engineering, routing reliability.
- **Part 3 (pages 17–24) — Platform & observability:** autoscaling, Kubernetes,
  health checks, observability stack, dashboards, alerting, tracing, quality
  observability.
- **Part 4 (pages 25–35) — Release & incident practice:** model release
  engineering, shadow testing, canaries, regression testing, chaos engineering,
  incident management, runbooks, postmortems, cost reliability, agent SRE, RAG SRE.
- **Part 5 (pages 36–41) — Scale-out & synthesis:** multi-region, disaster
  recovery, reference architecture, the 80/20 guide, zero-to-hero, capstone.
- **Labs:** 12 hands-on labs with safe synthetic workloads.

## Relationship to the rest of the Wiki

This section is the **operations/SRE discipline**. It deliberately does not
re-derive the deep mechanics that already live elsewhere; it *consumes* them:

| Topic | Where it lives | What this section adds |
|---|---|---|
| Routing & scheduling hierarchy (L0–L3) | `Inference/Production-Serving/` | Reliability framing, failure modes, golden signals |
| Queueing theory | `Inference/Production-Serving/04-queueing-theory-80-20.md` | Operator trade-offs (utilization vs tail latency), admission control |
| GPU internals, kernels, diagnostics | `GPU-Systems/` | GPU *failure engineering* (Xid/ECC/throttling), DCGM ops |
| KV-cache mechanics | `KV-Cache/`, `Inference/` | KV as a *reliability resource* (exhaustion, fragmentation, churn) |
| Distributed inference (TP/PP/EP/DP) | `Distributed-Inference/`, `GPU-Systems/` | Distributed *failure modes* (straggler, NCCL timeout, hang) |
| Evaluation discipline | `Evaluation-Engineering/` | Quality regression testing, quality observability |
| Agent / harness | `Agents/`, `Harness-Engineering/`, `Context-Engineering/` | Agent SRE (runaway loops, budgets), harness reliability |
| RAG pipeline | `RAG/`, `Evaluation-Engineering/RAG-Evaluation.md` | RAG SRE (freshness, retrieval, grounding) |
| Serving engines | `Serving-Engines/` | Engine observability, health checks, release engineering |
| Networking / NCCL / NVLink | `Networking/`, `GPU-Systems/NCCL.md` | Distributed failure diagnosis |

## Provenance

Same scheme as the whole Wiki: `[F]` verified primary source, `[E]` empirically
measured in this environment, `[I]` author inference stated as such, `[A]`
assumption, `UNVERIFIED` not validated. NVIDIA Xid/ECC and DCGM claims in
[10-gpu-reliability](10-gpu-reliability.md) are tagged `[F]` against
docs.nvidia.com (verified 2026-08-23). **No SLO values, benchmark results,
product behaviours, or GPU error meanings are invented** — every quantitative
recommendation states its assumptions.

## Which model wrote / reviewed this

Drafted by the **DeepSeek V4 Flash** agent (main model, local vLLM on dual DGX
Spark GB10). Independently reviewed in the Qwen3.8 27B reviewer role (local
vLLM on the RTX 5090 workstation) per group; every review finding adjudicated
— see the review records at the bottom of the relevant pages and the final
report.

## Reading guide

- **New SRE / platform engineer:** 01 → 02 → 03 → 04 → 05 → 20 → 22 → 30 → 31 → 32.
- **Inference engineer going ops:** 05 → 07 → 10 → 11 → 12 → 20 → 21 → 28.
- **Reliability leadership / design:** 02 → 06 → 38 → 39 → 40 → 41.
- **Hands-on:** start at `Labs/` after pages 01–07.

## Key takeaways

1. A user-visible failure can originate at **any** layer of the stack.
2. **Goodput** (work that satisfies the SLO and quality bar) matters more than
   raw throughput.
3. **Availability ≠ useful output** — quality, correctness and cost are first-class.
4. **Observability is a control loop**, not a dashboard: signals must drive
   routing, scaling, admission and alerting.
5. Every optimization and every model/prompt/router/RAG/kernel change is a
   **release** and needs regression testing.
