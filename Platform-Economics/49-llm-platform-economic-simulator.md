# 49 — LLM Platform Economic Simulator

`LAST_UPDATED: 2026-08-24` · Status: lab/tool page

## 30-Second Explanation

The **economic simulator** ([scripts/economic_simulator.py](scripts/economic_simulator.py))
turns the section's cost model into an interactive number machine. You input the
hardware/cost/demand knobs and it outputs **$/GPU-hour, $/1M tokens, $/request,
$/tenant, monthly platform cost, and the cloud/local break-even**, across
**Private GPU / Public GPU / Cloud API / Hybrid** scenarios. Messing with the
numbers is the fastest way to internalize why utilization, SLO headroom, and
model mix dominate cost ([03](03-llm-inference-unit-economics.md),
[05](05-gpu-utilization-economics.md), [31](31-capacity-planning.md)).

## Inputs

| Group | Inputs |
|---|---|
| **Hardware** | GPU price, GPU power (W), number of GPUs |
| **Model/serving** | model size, tokens/sec (prefill & decode), utilization |
| **Demand** | requests/day, input tokens, output tokens |
| **Cloud** | cloud API pricing ($/1M in/out/cached), cloud GPU $/hr |
| **Other** | staff cost, availability/redundancy headroom |

## Outputs

- $/GPU-hour (fully loaded, utilization-adjusted)
- $/1M tokens (in/out)
- $/request
- $/tenant
- **monthly platform cost** — the **variable/marginal** token cost at the stated
  sizing **and demand**, *not* the all-in fixed bill. The fixed node reservation
  (e.g. **$8,703/mo** for an 8×H100) is shown separately via the **break-even**
  output — the two are different sums and must not be conflated.
- **break-even cloud/local volume** ([29-local-vs-api-economics](29-local-vs-api-economics.md))

## Scenarios

1. **Private GPU** — fully-loaded on-prem at your utilization.
2. **Public GPU** — cloud GPU instance cost per hour.
3. **Cloud API** — pure metered API spend.
4. **Hybrid** — fixed private base + cloud burst overflow ([28](28-cloud-bursting-economics.md)).

## How to run it

```bash
cd scripts
python3 economic_simulator.py          # defaults
python3 economic_simulator.py --json scenario.json  # custom scenario
```

Edit the `ASSUMPTIONS` / `SCENARIOS` dicts at the top of
`economic_simulator.py`, or paste a JSON scenario. Every number printed is
computed from the declared assumptions (no hidden constants) — **re-run after
any price change** ([54-economics-formulas](54-economics-formulas.md)).

> ⚠️ The simulator produces **ILLUSTRATIVE** numbers for learning, with stated
> assumptions and a price-date. It is **not** a replacement for your provider's
> current quote or your own measured throughput.

## Related

[03-llm-inference-unit-economics](03-llm-inference-unit-economics.md) ·
[04-capex-vs-opex-ai-platform](04-capex-vs-opex-ai-platform.md) ·
[29-local-vs-api-economics](29-local-vs-api-economics.md) ·
[54-economics-formulas](54-economics-formulas.md) ·
[scripts/economic_foundation.py](scripts/economic_foundation.py)

## Key takeaways

1. The simulator makes the cost model interactive and assumption-explicit.
2. Inputs: hardware, model/serving, demand, cloud, staff, headroom.
3. Outputs: $/GPU-hr, $/1M, $/req, $/tenant, monthly cost, break-even.
4. It is a teaching tool — re-verify against provider quotes and real throughput.
