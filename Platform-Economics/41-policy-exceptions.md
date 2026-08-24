# 41 — Policy Exceptions

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

Even well-governed platforms hit legitimate exceptions ("this tenant really does
need premium GPU access for a research burst"). The failure is **permanent,
undocumented exceptions** granted informally. The fix is a **governed exception
workflow** — a request carries justification, cost/SECURITY impact, an approver,
**an expiry date**, and a review — so exceptions are *temporary, visible,
bounded, and reversible* instead of quietly becoming permanent policy drift
([27-policy-as-code](27-policy-as-code.md),
[55-governance-antipatterns](55-governance-antipatterns.md)).

## Exception workflow (example)

```
Request (tenant asks for premium GPU / cloud / model access)
  ↓
Business justification        (why the base policy is insufficient)
  ↓
Cost impact                   (FinOps: how much this will cost)
  ↓
Security review               (Security: data/residency/isolation impact, [23][24])
  ↓
Approval                      (the accountable owner, [40])
  ↓
Expiry date                   (when it lapses automatically)
  ↓
Review                        (renew or revoke; metered outcome)
```

### Worked example
Tenant `acme/research` asks for **premium GPU access** for a 30-day model eval:
justification = "want to benchmark 70B models for a pilot"; cost impact =
"~$X over the window"; security review = "no sensitive data, local pool OK";
approval = Business Owner; **expiry = 30 days**; review = auto-flag for renewal.

## Why expiry matters

An exception without an **expiry date** is how documented policy silently decays:
the special access stays on forever, cost and risk accrue unnoticed, and when it
finally shows up it's a surprise. Expiry forces **deliberate renewal** — each
renewal re-answers the justification, so the exception stays *justified*.

## Governance notes [I]

- **Exceptions are to code, not to people:** grant an exception by adding a
  scoped, **expiring policy override** ([27-policy-as-code](27-policy-as-code.md)),
  never by disabling the policy engine.
- **Audit every exception** — who, why, until when, what it cost
  ([42-multi-tenant-observability](42-multi-tenant-observability.md)).
- **Track exception metrics** (count, growth, renewal rate) — a platform with a
  rising exception backlog has a policy problem, not an exception problem.

## Related

[27-policy-as-code](27-policy-as-code.md) ·
[40-llm-platform-governance-model](40-llm-platform-governance-model.md) ·
[55-governance-antipatterns](55-governance-antipatterns.md) ·
[26-model-access-control](26-model-access-control.md)

## Key takeaways

1. Legitimate exceptions exist; the failure is permanent, undocumented ones.
2. Route exceptions through justification → cost → security → approval → expiry → review.
3. Every exception needs an expiry date and a review to stay justified.
4. Grant exceptions as expiring policy overrides, and audit them all.
