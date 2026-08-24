# Platform-Economics — Evaluator Review & Adjudication Record

`LAST_UPDATED: 2026-08-24` · Independent evaluator pass (per section workflow).

## Process
An **independent adversarial evaluator** (qwen38-nvfp4, separate context —
the configured independent endpoint) was asked to challenge the section as a
FinOps engineer, an AI-infrastructure architect, a security architect, a CFO,
and an application owner; to re-run both calculator scripts; and to verify that
every `$` figure stated in the pages matches script output. Full transcription
of its pass is retained in the delegation log.

## Findings & adjudication

| ID | Area | Finding | Verdict | Disposition |
|---|---|---|---|---|
| E1 | Numeric consistency | `07-prefill-decode-economics.md` §Worked example still carried the pre-bug-era table `20% → $0.20/$0.24`, `70% → $0.06/$0.07`, stale after the foundation-script double-division bug was fixed (correct: `$0.07/$0.08` @20%, `$0.02/$0.02` @70%). | **ACCEPTED** | Fixed — table now reads the corrected, script-verified values. |
| E2 | Prose precision | `17-slo-economics.md` said running at 70% vs 50% util is "worth ~40% of your GPU bill" — imprecise (correct: 1.40× unit cost = ~29% cheaper). | **ACCEPTED (partially)** | Reworded: "cuts per-GPU-hour cost by ~29% (a 1.40× unit cost at 50% vs 70%)". |
| E3 | Break-even framing | `29-local-vs-api-economics.md` implied the *numeric* break-even shifts with utilization though the fixed-cost formula it not utilization-dependent. | **ACCEPTED (partially)** | Reworded to state assumptions and clarify that low utilization worsens *effective cost per unit value* (utilization as the deciding variable) rather than the request-count break-even. |

(Additional findings from the evaluator are appended below/on completion.)

## Independent author-side audit (all PASS, machine-checked)
- M/M/1 P99 response table (T_s=0.5s): 1076 / 2803 / 5873 / 9710 / 21223 / 44249 ms at ρ=0.2/0.5/0.7/0.8/0.9/0.95 — matches page 05 exactly.
- Cascade tie condition P* = C_small/C_large = 0.1 — matches lab-11 verify note.
- Break-even: node $8,703/mo → 16.6M req/mo (gpt-4o-mini), 1.24M (GPT-4.1), 0.39M (gpt-5.6-sol) — matches pages 03/29.
- Effective $/GPU-hr utilization table — matches foundation output.
- Cache ROI $0.03/1M — matches foundation output.

## Policy
"**Do not automatically accept criticism.**" We accept only findings confirmed by
re-running the scripts or re-reading the source; everything above was
independently re-verified rather than taken on the evaluator's word.
