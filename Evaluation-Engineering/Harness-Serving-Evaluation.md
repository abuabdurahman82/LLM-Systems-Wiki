# Harness & Serving Evaluation: goodput, SLOs, and the model-under-load problem

`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation

Two different objects are routinely evaluated under one label: "how good is this model."
Object (a) is the *harness* — the prompt, tool wiring, retry policy, and memory the model
runs inside — judged on task success rate, which is the territory of `../Agents/Agent-Evaluation.md`
and `../Harness-Engineering/Model-vs-Harness.md`. Object (b), the subject of this page, is the
*serving system* — the scheduler, batcher, KV-cache manager, and prefill/decode pipeline —
judged on latency, throughput, and cost. The serving object's headline metric is not raw
throughput but **goodput**: requests/second that meet their SLOs [F: DistServe, arXiv:2401.09670].
Averages are useless at this layer: a queue can keep mean latency flat while P99 explodes,
because queueing time is a nonlinear function of utilization [I]. Every serving number is
therefore a protocol: fixed concurrency, fixed workload mix, fixed duration, and a pinned
serving config — because the model's *quality* can degrade under load, which means the
serving system is not a neutral transport.

## The two objects, kept apart

| Question | Object | Metric family | Home page |
|---|---|---|---|
| Does the agent finish the task? | Harness (prompt, tools, retries, memory) | task success rate | `../Agents/Agent-Evaluation.md` |
| What part of the win is the wrapper? | Harness vs model | ablation of harness layers | `../Harness-Engineering/Model-vs-Harness.md` |
| Does the request meet its latency budget? | Serving system | TTFT/ITL percentiles, goodput, $/token | **this page** |

The interlock matters: a serving change (larger batch, preemption policy) can move task
success rates *and* latency. If your eval only measures one object, the other silently
drifts. [I]

## The SLO stack

The stack, bottom-up [F: definitions per `../Inference/Inference-Metrics.md`]:

1. **TTFT (time to first token)** — dominated by queue time + prefill. The interactive
   "does it feel fast" metric. At B=1 it is mostly prefill time; under load it is mostly
   queue time, which is why TTFT must always be reported at a stated concurrency.
2. **ITL / TPOT (inter-token latency / time per output token)** — the streaming feel,
   dominated by the decode loop. TPOT ≈ (total − TTFT)/output tokens.
3. **Percentiles, not means** — P50/P95/P99 of both TTFT and ITL. SLOs are built on P95/P99;
   the mean is a different statistic and says almost nothing about tail behavior. [I]
4. **Goodput** — SLO-conforming requests/second. Raw throughput counts requests that
   violated the SLO; goodput does not. [F: DistServe arXiv:2401.09670 defines the
   goodput-optimized serving framing.]

### Why averages lie under load

Queueing theory does the work. Little's law, L = λ·W, ties in-flight requests L to arrival
rate λ and mean time-in-system W [I: classical result, used here qualitatively]. The key
nonlinearity is that queueing delay grows roughly like ρ/(1−ρ) as utilization ρ → 1
[M/M/1 intuition — presented as intuition, not an exact model]:

- Arrivals at 10 req/s, service time 0.09 s → ρ ≈ 0.9. Queue is busy but bounded.
- Arrivals at 11 req/s → ρ ≈ 0.99. Mean queue wait is now an order of magnitude larger.

So a system can report a *fine mean latency* at ρ = 0.99 while its P99 is in the seconds:
the mean hides the queue. This is why "mean ITL 40 ms, P99 2.1 s" is a normal, healthy-looking
pair of lies when read alone. [I]

### Hand example: goodput beats throughput [E]

System A serves 200 req/s at target load; 4% of requests violate the SLO (P95 TTFT budget).

- goodput(A) = 200 × (1 − 0.04) = 200 × 0.96 = **192 req/s**.

System B adds capacity, serves 210 req/s, and cuts SLO violations to 1%.

- goodput(B) = 210 × (1 − 0.01) = 210 × 0.99 = **207.9 req/s**.
- Real gain: (207.9 − 192)/192 = 15.9/192 = 0.0828 → **8.3%**.
- Raw throughput gain: (210 − 200)/200 = 0.05 → **5%**.

Reporting "5% more throughput" understates the actual customer-visible improvement (8.3%),
and in the reverse direction a "throughput gain" that *increases* violations is negative
goodput. [E]

## The knobs you are actually evaluating

- **Chunked prefill and continuous batching** — the two scheduler levers that trade TTFT
  against decode stability; a full treatment lives in `../Inference/Continuous-Batching.md`.
  Changing chunk size or admission policy moves the SLO stack, so it is part of the
  *serving config under eval*, not an implementation detail. [I]
- **Prefill/decode disaggregation** — splitting prefill and decode onto different pools
  changes the interference structure entirely. Eval must be run **under the target mix**:
  the ratio of short-chat to long-context requests determines where the win is. See
  `../Inference/Deep-Dives/pd-disaggregation-deep-dive-2026-08-17.md` and
  `../Inference/Prefill-Decode-Disaggregation.md`. A result measured at a 70/30 mix says
  nothing about a 90/10 deployment. [I]
- **Sarathi-Serve** is the canonical public example of managing the throughput–latency
  tradeoff explicitly (chunked-prefill scheduling under latency targets)
  [F: arXiv:2403.02310].
- **Engine choice** — `../Serving-Engines/README.md`; engine differences (scheduler,
  CUDA graph behavior) are part of the config, not noise. [I]

## Quantization is a quality-vs-speed axis, not free speed

Deploying at INT8 or FP4 buys throughput; it spends accuracy. Serving eval therefore must
run the **accuracy battery at the deployed precision** — not just at FP32/BF16 with a
"we'll check accuracy later" footnote. A 2-point MMLU drop at FP4 is a *system decision*
with a measurable cost, not a model bug to be filed somewhere [I; F: MMLU per
arXiv:2009.03300]. Practical split: the serving team owns the latency/cost numbers at the
chosen precision; the eval team owns the accuracy delta at that precision; the release
decision needs both. [I]

## KV-cache pressure: never evaluate at B=1

KV-cache occupancy is the binding constraint at realistic concurrency — what fits, what
evicts, what preempts — and it only exists under load. See `../KV-Cache/README.md`.
An eval run at batch size 1 measures the memory-bandwidth roofline (see
`../Inference/Roofline.md`) and nothing about the system that actually ships. Every
number on this page is meaningless without its concurrency label. [I]

## The model-under-load problem

The serving layer is not a transparent pipe. Under pressure the system preempts requests,
retries failed steps, swaps KV, or re-schedules mid-generation; each of those can change
the output the user sees — a truncated completion, a degraded sampling path, a retried
branch. Model *quality* can therefore degrade under load. Consequence for eval: **pin the
full serving config** (engine + version, batch/chunk settings, preemption policy, cache
limits, replica count, quantization) and treat any change to it as a new system, not a
rerun. If quality and latency are both moving, report them jointly. [I]

## Eval cost and how to structure an SLO test

Serving evals are cheap per token but *expensive in time*: the numbers only mean something
after the queue has reached steady state, so plan for **sustained load at the target
concurrency for 30–60 minutes** per point on the curve [I]. A 2-minute burst measures the
cold start, not the system.

Protocol template [I]:

1. **Workload trace** — a fixed request mix (input lengths, output lengths, modality,
   chat-vs-long-context ratio) derived from production, not synthetic 1-token prompts.
2. **Concurrency ramp** — run at C, 2C, 4C, ... around the target; identify where the
   SLO stack bends.
3. **Steady window** — after a warmup period, capture TTFT/ITL percentiles for 30–60 min.
4. **Report at fixed concurrency** — one table per concurrency point: P50/P95/P99 TTFT,
   P50/P95/P99 ITL, goodput, $/token. Never mix concurrency points in one average. [I]

The same table, with the accuracy battery added at the deployed precision, is the full
serving evaluation. [I]

## Related

- `../Inference/Inference-Metrics.md` — the metric stack this page evaluates against
- `../Inference/Continuous-Batching.md` — chunked prefill and batching mechanics
- `../Inference/Deep-Dives/pd-disaggregation-deep-dive-2026-08-17.md` — prefill/decode split under load
- `../KV-Cache/README.md` — the pressure that only exists at concurrency
- `../Agents/Agent-Evaluation.md` — the other object: task success under a harness

## Key Takeaways

Evaluate the serving system on **goodput, not raw throughput**, at fixed concurrency with
percentiles, not means. Queueing makes the mean a lie: fine mean, exploding P99, is the
normal state near saturation. Pin the entire serving config — including quantization and
preemption — because the model's quality moves under load, making the serving system part
of what is being measured, not just the instrument.
