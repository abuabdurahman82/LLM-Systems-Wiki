# Lab 3 — On-Prem vs Cloud Break-Even

`LAST_UPDATED: 2026-08-24` · Concept: build-vs-buy · Builds on
[../29-local-vs-api-economics](../29-local-vs-api-economics.md) and
[../49-llm-platform-economic-simulator](../49-llm-platform-economic-simulator.md).

## Goal
Find the request volume at which an on-prem node (fixed cost) breaks even
against a variable-rate API, and watch utilization move it.

## Approach
1. `Break-even req/mo = Fixed monthly local cost / API $/req`.
2. Run the simulator's four scenarios and read its break-even.
3. Change `utilization` and the `api_alternative_*` prices; watch the volume move.

## Run
```bash
cd ../scripts && python3 economic_simulator.py
# vary utilization:
printf '{"utilization":0.5}' > /tmp/hy.json && python3 economic_simulator.py --scenario hybrid --json /tmp/hy.json
```

## Expected result (ILLUSTRATIVE)
- Fixed 8×H100 node ≈ **$8,703/mo**.
- vs gpt-4o-mini-class API (~$0.0005/req): **~16.6M req/mo**.
- vs GPT-4.1-class ($0.007/req): **~1.2M req/mo**.

## Interpretation
Against a *cheap* API, ownership only wins at massive volume; against a
*premium* model the break-even is low. Lower utilization raises the volume
needed (idle tax). Add residency and reliability as non-cost factors
([24](../24-data-governance.md), [45](../45-cost-of-failure.md)).

## Verify
Halve the API price and recompute break-even by hand — it should double.
