# 32 — Blameless Postmortems

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

A postmortem is how an incident becomes a **system improvement**. Blameless means
the goal is to fix the *system*, not punish the *person* — so people report openly,
systemic causes surface, and the same incident does not recur.

## The template

| Section | What it captures |
|---|---|
| **Summary** | one paragraph: what happened, impact, severity |
| **Impact** | users, requests, SLO, cost, duration |
| **Timeline** | timestamped, from detection to resolution (from [30](30-llm-incident-response.md)) |
| **Detection** | how it was noticed (which alert/dashboard/user) |
| **Root cause** | the fundamental trigger |
| **Contributing factors** | what made it worse (headroom, config, process) |
| **What worked** | mitigations/runbooks/roles that helped |
| **What failed** | gaps (alerting, probes, capacity, quality checks) |
| **Corrective actions** | concrete, owned, dated fixes |
| **Prevention** | how to stop recurrence (and catch the class of failure) |

## How to run one (`[I]`)

1. **Schedule promptly** while memory is fresh; include all roles and SMEs.
2. **Focus on system factors**, not individual blame — ask "what allowed this?"
   repeatedly down to a systemic cause.
3. **Use the taxonomy** ([09](09-llm-failure-taxonomy.md)) to classify and detect
   trends across incidents.
4. **Check both axes** — infrastructure failures *and* silent quality failures
   ([24](24-quality-observability.md)); "answers became wrong" needs quality SLIs
   in the timeline, not just HTTP logs.
5. **Write actions with owners + dates**, and follow up — a postmortem with no
   owned actions is a meeting, not an improvement.
6. **Update runbooks and tests** from the findings ([31](31-production-runbooks.md),
   [29](29-chaos-engineering-for-llms.md)).

## Blameless in practice

- Language: "the probe was too strict" not "Alice set a bad probe."
- Outcome: corrective actions reduce the *class* of failure, so the team improves.
- Norm: near-misses and contributing factors are encouraged, not penalized.

## Related

`09-llm-failure-taxonomy.md` · `24-quality-observability.md` ·
`30-llm-incident-response.md` · `31-production-runbooks.md` ·
`Labs/12-create-a-production-incident-and-postmortem.md`

## Key takeaways

1. Postmortems turn incidents into system improvements.
2. Template covers summary, impact, timeline, detection, root cause, contributing
   factors, what worked/failed, corrective actions, prevention.
3. Blameless = fix the system, not the person — so causes surface openly.
4. Include BOTH infra and quality axes; every corrective action needs an owner+date.
