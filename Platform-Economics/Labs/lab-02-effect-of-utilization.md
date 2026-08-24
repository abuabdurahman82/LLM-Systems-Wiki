# Lab 2 — Calculate the Effect of Utilization

`LAST_UPDATED: 2026-08-24` · Concept: utilization economics · Builds on
[../05-gpu-utilization-economics](../05-gpu-utilization-economics.md).

## Goal
Quantify how utilization converts fixed GPU cost into unit cost, and where the
latency cliff begins.

## Approach
1. From `economic_foundation.py`, table Effective $/GPU-hr at 10–95% utilization.
2. Compute the **multiplier** = 1/utilization (a 20% fleet pays 5× the 100% rate).
3. Re-run the M/M/1 P99 section to see latency blow up past ρ≈0.7.

## Run
```bash
cd ../scripts && python3 economic_foundation.py | grep -A8 "UTILIZATION IMPACT"
```

## Expected result (ILLUSTRATIVE)
| util | eff $/GPU-hr | ×nominal |
|---|---|---|
| 20% | $7.45 | 5× |
| 50% | $2.98 | 2× |
| 70% | $2.13 | 1.4× |
| 95% | $1.57 | 1.05× |

Latency (M/M/1, T_s=0.5s): P99 ≈ 5.9s @70%, 21s @90%, 44s @95%.

## Interpretation
Cost falls with utilization, but **interactive latency SLOs cap how high you
can push it**; the optimum is not 100%. Find the ρ where goodput/$ is max
([05](../05-gpu-utilization-economics.md), [43](../43-goodput-economics.md)).

## Verify
Why does doubling util roughly halve unit cost? Because the fixed bill is spread
over ~2× the productive hours.
