# LLM Safety & Security
`LAST_UPDATED: 2026-08-16` · Status: core section

## 30-Second Explanation
LLMs create new attack surfaces (the model *reads untrusted text and acts*), and old
ones (extraction, poisoning). This page covers the taxonomy + mitigations; treat every
entry as evolving rapidly [I: 2025–26 state].

## Threat taxonomy
| Threat | Description | Mitigations |
|---|---|---|
| **Prompt injection** | malicious instructions hidden in user/web/tool content hijack behavior | instruction hierarchy; untrusted-content tagging; output filters; least-privilege tools |
| **Jailbreaking** | bypass safety refusals | red-teaming, RLHF refusals, watermarking (Claude text watermark [F: Anthropic 2026-08]), jailbreak severity scoring (Glasswing framework [F: Anthropic 2026-06]) |
| **Data leakage** | model recites training data / leaks context across users | memorization bounds, output filters, KV isolation per request |
| **Model extraction** | query the API to clone a model | rate limiting, noisy outputs, IP on API use |
| **Tool abuse** | agent misuses/mis-scopes tools | sandboxing, permission tiers, human-in-loop for high-impact actions |
| **Agent privilege escalation** | agent gains capabilities beyond grant | least privilege, egress control, action allowlists |
| **RAG poisoning** | poisoned documents → poisoned answers | source trust tiers, document signing, retrieval provenance |
| **Training-data poisoning** | malicious content in pretraining data | data filters, dedup, provenance tracking |
| **Unsafe code execution** | agent-generated code with side effects | sandboxes, no-network defaults, diff review |
| **Sandbox escape** | agent escapes its execution sandbox | kernel isolation, seccomp, resource caps |

## The agent-era shift (2025–26)
Agentic AI raised stakes: an agent with tools + autonomy is a *remote code executor
driven by text*. The dominant 2025–26 research/industry focus is
**prompt-injection-resistant agent design**: separate "control plane" (trusted) from
"data plane" (untrusted content the model reasons about); verifier agents for high-impact
actions; and evals that measure injection resistance (AgentDojo-class benchmarks [F:
arXiv:2406.13352]).

## Defense-in-depth checklist (production)
1. Isolate untrusted content (mark it, fence it, never let it speak in the "user" voice).
2. Least-privilege tools per task; high-impact actions gated.
3. Sandbox code execution (no network, no secrets, capped resources).
4. Verify high-stakes outputs with an independent model/evaluator.
5. Log + replay everything; watermark sensitive outputs where feasible.
6. Red-team continuously; track jailbreak-severity metrics (the Glasswing-style
   industry framework [F: 2026]).

## Related
`Agents/README.md` · `Harness-Engineering/README.md` · `Evaluation/README.md`.

## Key Takeaways
The model is the least trustworthy component in the stack; the system (harness,
sandbox, permissions, verification) is where safety actually lives.
