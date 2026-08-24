# Lab 11 — Small-Model Cascade vs Large-Model-Only

`LAST_UPDATED: 2026-08-24` · Concept: cascade routing · Builds on
[../11-economic-model-routing](../11-economic-model-routing.md).

## Goal
Compare **cascade (cheap-first, escalate)** against **always-large** expected
cost, and find how escalation rate and costs shift the winner.

## Approach (computation)
```python
def cascade(P_ok, C_small, C_large):
    return P_ok*C_small + (1-P_ok)*(C_small + C_large)
P_ok, Cs, Cl = 0.8, 0.0004, 0.004
print("cascade   :", cascade(P_ok,Cs,Cl))   # 0.00120
print("always-lrg:", Cl)                    # 0.00400 -> ~70% cheaper
```

Sweep `P_ok` 0.5→0.95 and show the saving grows with small-model reliability.

## Expected result
At P_ok=0.8, cascade ≈ **$0.0012/req vs $0.004** always-large (**~70% saving**).
The saving scales with how often the small model suffices.

## Interpretation
Cascade captures most of the cheap path without surrendering quality — the
premium model still catches the hard cases ([11](../11-economic-model-routing.md),
[12](../12-quality-cost-latency-frontier.md)). The *risk* is a small model that is
confidently wrong (mis-gates) — that's why you need evals
([Evaluation-Engineering/](../..)/Evaluation-Engineering/README.md).

## Verify
At what `P_ok` does cascade tie always-large? (Answer: when P_ok = (Cs+Cl−Cl)/… →
cascade ≈ Cl when P_ok·Cs + (1−P_ok)(Cs+Cl) = Cl → P_ok·Cs + Cs + Cl − P_ok·Cs − P_ok·Cl = Cs+Cl−P_ok·Cl = Cl → Cs = P_ok·Cl → P_ok = Cs/Cl = 0.1; i.e. cascade wins for all P_ok > Cs/Cl.)
