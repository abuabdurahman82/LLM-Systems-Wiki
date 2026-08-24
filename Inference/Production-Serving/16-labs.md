# Labs — Ten Hands-On Experiments
`LAST_UPDATED: 2026-08-22` · Status: labs page · Run on the home-lab stack
from [01](01-production-serving-overview.md): vLLM DeepSeek V4 Flash @
`10.1.1.51:8888` (2× Spark GB10, 1M ctx), vLLM Qwen3.8-27B @
`10.1.1.60:8888` (RTX 5090, 256k ctx), LiteLLM gateway @ `127.0.0.1:4000`,
Hermes profiles `default` / `deepseek-main`, the routing simulator in
`~/llm-router-research/sim/` (`llmsim.py`, `benchmark.py`, `rate_scan.py`,
`workloads.py`), and the `~/long-prompt-stress/` harness pattern.

Each lab: goal → do → observe → which page it exercises. Pins for all labs:
record engine version, model id, arrival pattern, and length distributions —
unpinned results are not comparable (deep-dive §7).

## Lab 1 — Measure your heterogeneity (page 02)
**Goal:** know your service-time CV before choosing any policy.
**Do:** pull prompt/completion token counts from LiteLLM's Postgres
(`LiteLLM_SpendLogs` / request logs) or from Hermes session state; compute
mean/P50/P90/P99 and CV of S and n.
```bash
WK=$(cat ~/litellm-gateway/.warp-key)
curl -s http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer $WK" -H 'Content-Type: application/json' \
  -d '{"model":"qwen38-nvfp4","messages":[{"role":"user","content":"ping"}],"max_tokens":8}'
# then aggregate usage.prompt_tokens / completion_tokens from logs
```
**Observe:** if CV(S) or CV(n) > 0.5, count-based balancing is leaking tail
latency. This number gates how much of pages 03–06 you need.

## Lab 2 — Policy bake-off in the simulator (pages 04, 05)
**Goal:** see least-connections vs token-queue vs cache-aware diverge on a
bursty mixed workload.
**Do:** extend `~/llm-router-research/sim/workloads.py` with a bursty
heterogeneous trace (Poisson bursts, S ∈ {128, 3k, 32k}, n̂ ∈ {32, 600, 4k});
run the three policies via `benchmark.py`; repeat at λ = 0.5×, 0.8×, 0.95× of
simulated capacity using `rate_scan.py`.
**Observe:** P99 TTFT spread between policies grows with λ and with CV; at
low load all policies converge (that's the cliff, page 04, in disguise).

## Lab 3 — Hand-computed ERW vs simulation (page 03)
**Goal:** validate the ERW decomposition end-to-end.
**Do:** take the [03](03-estimating-remaining-work.md) worked example
(S=3000, n̂=600, hit=2400 on A, 90k-token queue on B); reproduce both replicas
in the sim; compare predicted ERW (3.20 s vs 5.57 s [E]) against simulated
realized latency.
**Observe:** ranking should match even when absolute values drift; the gap
tells you which sim constant (TPR, step-time curve) is miscalibrated.

## Lab 4 — Find the cliff on real hardware (page 04)
**Goal:** measure the utilization cliff on a real vLLM replica.
**Do:** sweep Poisson λ against `10.1.1.60:8888` (Qwen) with a fixed workload
(e.g. S=2k, n=256), from ρ≈0.3 to overload; record P50/P99 TTFT per λ. Keep
concurrency and output length fixed so ρ is the only variable.
**Observe:** P99 stretch should grow superlinearly past ρ≈0.7–0.8; compare
the measured curve against the `1/(1−ρ)` reference and the PK `(1+C²)/2`
correction. Where the measured curve breaks upward earlier than the model is
your KV-capacity knee starting to bind.

## Lab 5 — Prefix-cache-aware routing (pages 05, 08)
**Goal:** measure the TTFT delta of cache-aware placement (deep-dive H1).
**Do:** build a workload with a fixed 2–4k-token shared system prompt and
varying suffixes; control hit rate (0/40/80%) by shuffling which replicas see
which prefix; route once round-robin, once cache-affinity-pinned. The vLLM
engines expose prefix-cache hit metrics (`/metrics`) to confirm the hit rate
realized.
**Observe:** TTFT on hits should drop toward the uncached-suffix-only cost
(e.g. 3k@80% hit ≈ 17 ms-class prefill vs 85 ms cold [E, 7B reference — expect
different absolute numbers on 27B/5090; measure, don't assume]).

## Lab 6 — KV-pressure misrouting (pages 03, 10)
**Goal:** show least-connections routing into a KV-pressured replica.
**Do:** using the `~/long-prompt-stress/` harness pattern, start a few very
long-context decodes against one engine (DeepSeek @ 10.1.1.51 has 1M ctx —
plenty of headroom to play with); watch `gpu_cache_usage` on `/metrics` climb;
then send short requests under least-connections and observe them land on the
pressured replica anyway.
**Observe:** TTFT/TPOT degradation on the pressured replica while its
*connection count* still looks fine — the same-connections trap (02), live.
Fix by adding the KV-headroom filter and re-run.

## Lab 7 — Output-length predictor calibration (page 03)
**Goal:** build and calibrate n̂.
**Do:** from Lab 1's logs, fit per-class (chat / agent-task / eval) empirical
output-length quantiles; no model needed — a per-class P50/P90 table is the
80/20. Score calibration: fraction of realized outputs above the P90 estimate.
**Observe:** P90-based KV reservation vs mean-based: count preemption events
in an overload replay (Lab 9 setup) — deep-dive H3 expects ≥50% fewer
preemptions at ≤5% goodput cost [open hypothesis — your number decides].

## Lab 8 — Staleness and herd behavior (page 06)
**Goal:** quantify how state age degrades routing.
**Do:** in the sim, inject state-update delays of 0/50/200 ms into the scorer
and run a bursty trace; measure misroute rate (chosen vs realized-best
replica) and placement oscillation. Then toggle anticipatory accounting.
**Observe:** misroute rate grows with staleness; anticipatory accounting
should remove the placement pile-up at the metrics period without fresh
metrics.

## Lab 9 — Admission control under overload (page 10)
**Goal:** convert an overload collapse into clean partial errors.
**Do:** drive λ > capacity at one replica (sim first, then carefully against
a real engine with a hard client cap). Variant A: no admission control.
Variant B: reject when predicted queue delay > TTFT SLO (token-queue estimate
only). Track admitted-set P99, rejection rate, retry amplification.
**Observe:** variant A: everyone's latency dies together. Variant B: admitted
P99 stays ~flat as rejection rises. Measure the rejection rate you paid.

## Lab 10 — Evaluator workflow dry-run (page EVALUATION)
**Goal:** rehearse this section's own adversarial review loop.
**Do:** send one page (start with 03) to the evaluation model — DeepSeek V4
Flash @ `10.1.1.51:8888` (or via the Hermes `evaluator` alias) — with the
prompt: *"Adversarially review this engineering document. Flag: numeric
errors, internal inconsistencies, overclaims vs cited evidence. Return flags
as a numbered list with severity."* Verify each flag independently in Python
before applying (the deep-dive's pass-1 flag 6 shows the evaluator can itself
be wrong).
**Observe:** record accepted/refuted flags; that record becomes this
section's `EVALUATION.md` adjudication appendix.

## Related
[01-production-serving-overview](01-production-serving-overview.md) ·
[04-queueing-theory-80-20](04-queueing-theory-80-20.md) ·
`../../Benchmarks/` · `../../Evaluation-Engineering/Harness-Serving-Evaluation.md` ·
`../Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md` §7 (H1–H5)

## Key Takeaways
1. Labs 1–4 characterize your workload and hardware; 5–9 test each mechanism;
   10 rehearses the review loop.
2. Pin model, engine, λ, and length distributions — or your numbers won't
   replicate.
3. The sim (`~/llm-router-research/sim`) is for policy iteration; real
   engines are for validation. Do both, in that order.
