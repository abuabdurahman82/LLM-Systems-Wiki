# Lab 1 — Calculate Cost per Million Tokens

`LAST_UPDATED: 2026-08-24` · Concept: unit economics · Builds on
[../03-llm-inference-unit-economics](../03-llm-inference-unit-economics.md) and
[../scripts/economic_foundation.py](../scripts/economic_foundation.py).

## Goal
Compute $/1M tokens (prefill & decode) for a self-hosted model and compare to
an API price. See how utilization changes it.

## Approach
1. Read the fully-loaded $/GPU-hr computation in
   `economic_foundation.py` (`onprem_gpu_hour`).
2. Use: `$/1M = (1e6 / tok_s) * ($/GPU-hr / 3600)`.
3. Compare prefill vs decode at 20% / 70% / 95% utilization.

## Run
```bash
cd ../scripts && python3 economic_foundation.py | sed -n '/1M TOKENS/,/req/p'
```

## Expected result (ILLUSTRATIVE)
- At **70% util**: prefill ≈ **$0.02/1M**, decode ≈ **$0.02/1M**.
- At **20% util**: ≈ **$0.07/1M** — utilization roughly triples unit cost.
- API reference (2026): GPT-4.1 **$2/$8** per 1M.

## Interpretation
Self-hosted marginal token cost is *tiny* vs API at good utilization — the gap
is the **fixed-cost-vs-metered** difference ([03](../03-llm-inference-unit-economics.md),
[29](../29-local-vs-api-economics.md)). What you don't see here is the idle tax:
change `utilization` and watch $/1M move.

## Verify
Recompute by hand for one row and confirm it matches the script.
