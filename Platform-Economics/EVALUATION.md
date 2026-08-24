# Platform-Economics — Evaluator Review & Adjudication Record

`LAST_UPDATED: 2026-08-24` · Independent evaluator pass (per section workflow).

## Process
An **independent adversarial evaluator** (qwen38-nvfp4, separate context — the
configured independent endpoint) challenged the section as a FinOps engineer, an
AI-infrastructure architect, a security architect, a CFO, and an application
owner; re-ran both calculator scripts; recomputed every `$` figure against
script output; and verified page↔page consistency and date/ILLUSTRATIVE
labeling across all 57 pages + README + 15 labs. Per the workflow, **criticism
is adjudicated, not auto-accepted**: each finding below was independently
re-verified against the files/scripts before disposition.

## Findings & adjudication

| ID | Sev | Area | Finding | Verdict | Disposition |
|---|---|---|---|---|---|
| F1 | High | Numeric consistency | `07` prefill/decode table still showed pre-fix values ($0.20/$0.24 @20%, $0.06/$0.07 @70%) contradicting `03` and the script. | **ACCEPTED** | Fixed to script-correct $0.07/$0.08 @20%, $0.02/$0.02 @70% (matches 03 + foundation). |
| F2 | Med | Queueing | M/M/1 P99 used the queue-**wait** formula; true M/M/1 P99 **sojourn** = `Ts·ln(100)/(1−ρ)` is ~2.7× larger at low ρ (1.1 s→2.9 s @ρ=0.2); single-server model is a simplification for batched multi-GPU serving. Self-consistent, direction/knee correct. | **ACCEPTED** | Fixed formula to sojourn P99; updated pages 05 + lab-02 and the script; added explicit "M/M/1 is an order-of-magnitude simplification, not an SLA predictor" caveat. |
| F3 | Med | Simulator | `scenario_private/public` "monthly" is **marginal token cost**, not the fixed node bill ($252 vs $8,703/mo) — conflates variable vs fixed. | **ACCEPTED** | Relabeled output "marginal $/mo … EXCLUDES fixed reservation"; page 49 states the distinction and that break-even carries the fixed bill. |
| F4 | Med | Labeling | Pages 10 + lab-12 `$` figures lacked explicit ILLUSTRATIVE/date. | **ACCEPTED** | Added price-date/illustrative labels to both. |
| F5 | Low | Formula↔code | Break-even text had a `− Local Marginal Cost` term the scripts drop (local marginal ≈ 0). | **ACCEPTED** | Clarified that local marginal ‖0 vs API and the term drops; note when it must not be dropped. |
| F6 | Low | Routing | Page 22's $0.01/$0.07/$0.40 router costs aren't tied to the price tables (illustrative but unexplained). | **ACCEPTED** | Added a note that they are deliberately-rounded long/high-output illustrative per-request figures, distinct from the 1500/500-token shape. |
| F7 | Low | Security | Page 23 "memory isolation" row over-stated hard isolation for soft/shared tenancy (no per-tenant process boundary on a shared GPU). | **ACCEPTED** | Reworded: engine-logical isolation (cache/KV scoping) for soft tiers; hard process/GPU boundary only in hard-isolation tiers. |
| F8 | Low | Rounding | README "neocloud ~$3" vs precise $2.99–3.99 range. | **ACCEPTED** (consistent) | Left as-is (matches the range stated on page 03). |
| F9 | Low | Pricing | Page 06 "3–5×" output/input ratio misses the ~6× outlier (gpt-5.6-sol). | **ACCEPTED** | Added the "up to ~6×" outlier with the $30/$5 example. |

## Evaluator-confirmed correct (no change needed)
Pages 03/04/05/17/29/08/43/44/54 + README + labs 01–03/10/11 matchup the
script: $1.49/$2.13/$7.45/$1.57/$2.98/$14.90/$1.66 per GPU-hr; $245k capex;
$8,703/mo node; break-even 16.6M/1.2M/0.39M req/mo; cascade $0.0012/req ~70%;
cache $0.03/1M; agent $0.0142, 27×; energy ~$0.07/GPU-hr ≈5% of nominal
(capex+ops dominate). Both scripts run clean; all 57 pages + README carry a
date/ILLUSTRATIVE header.

## Author-side independent audit (all PASS, machine-checked)
M/M/1 sojourn P99 recomputed independently; cascade tie P* = C_small/C_large =
0.1; break-even arithmetic; utilization table; cache ROI — all re-derived, not
taken on the evaluator's word.

## Policy
"**Do not automatically accept criticism.**" Every finding above was accepted
only after independent re-verification (file read or script re-run). F1–F9 all
reproduced/verified; there were no REFUTED findings this pass.
