# Coding Agents (the SWE flagship)
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
Coding agents (sustained, multi-file, test-driven software work) are the flagship
application of agentic engineering — and the one with the cleanest
*measurement surface*: every step is checkable (lint, type-check, tests, git diff).
The 2023–2026 arc: SWE-bench (2023, ~2% solved) → agent-computer interfaces
(2024) → Verified subset + frontier models (2024, 40–50%+) → trained
RL-for-SWE + long-horizon agents (2025–26). [F: arXiv:2310.06770; the 40–50%+
figure is a vendor number, unverified [I]]

## Why SWE became *the* agent domain (three structural reasons)
1. **Dense, cheap feedback** — compiler/tests give a pass/fail signal every
   step; the compounding-error problem
   (`Agentic-AI-Evolution.md` § compounding-error math) is most tractable here
   because failures are *locally detectable*.
2. **Verifiable final state** — "the test suite passes" is a goal predicate;
   RLVR (`../Post-Training/Alignment-RLHF.md`) applies directly.
3. **Economic leverage** — one SWE-hour of agent work is worth hours of human
   time; the cost ceiling for token spend is far above chat.

## The benchmark lineage
| Benchmark | arXiv / source | What it measures | Notes |
|---|---|---|---|
| SWE-bench | arXiv:2310.06770 [F] | real GitHub issues, full-repo context | best-2023 ~1.96% [F: abstract]; full set has label noise |
| SWE-bench Verified | OpenAI, 2024-08 (vendor release; openai.com returns 403 to automated fetch — the subset is documented via arXiv:2512.10218 below [F]) | ~500 human-verified subset | the de-facto headline number for coding models |
| SWE-bench Verified (paper) | arXiv:2512.10218 [F] | analysis: agent ability vs model memory | documents memorization confound risk |
| SWE-Gym | arXiv:2412.21139 [F] | training env + verifiers for SWE agents | RL/RLVR data factory |
| Commit0 | arXiv:2412.01769 [F] | library generation from scratch | tests as spec; repo-level |
| SWE-agent | arXiv:2405.15793 [F] | agent-computer interface (ACI) | interface design as first-class variable |
| Terminal-Bench | arXiv:2601.11868 [F] | hard CLI tasks in containers | 2026-era long-horizon |
| TheAgentCompany | arXiv:2412.14161 [F] | long business/IT tasks (consequential) | beyond SWE |

## The agent-computer interface (the underrated variable)
SWE-agent's central empirical claim: **the ACI — how the agent sees the repo and
issues its commands — the paper's central empirical result: a purpose-built
agent-computer interface (ACI) dramatically changes agent performance
(SWE-bench pass@1 12.5% vs ~3–5% for prior non-interactive / generic-CLI
baselines [F: abstract]). [I: "matters as much as the model" is the wiki's
synthesis of that result + the Model-vs-Harness decomposition, not the paper's
verbatim claim]
Design elements [I: synthesized from the paper + production harnesses]:
- **Search, not cat** — a `search` tool (grep/ripgrep-like) over thousands of
  files beats dumping files; the agent explores *by intent*, not by scroll.
- **Bounded edits** — a `diff`-based edit tool (search/replace blocks with
  context) instead of full-file rewrites: fewer token errors, easier diffs.
- **State-preserving shell** — a persistent environment (cd, env vars survive)
  so multi-command sequences work like a human terminal.
- **Grounded feedback** — exit codes, stderr, test summaries formatted as
  *short* structured results (a failing test's full traceback is a context bomb;
  a 5-line summary + "full output available" is not — see
  `../Context-Engineering/Context-Compaction.md`).

## The production stack (2026 shape)
```
[human: task spec]
      ↓
[planner: plan + task graph]            ← optional explicit plan
      ↓
[editor loop]  ┌─ search / read / edit / shell / test tools (MCP or native)
      │         └─ sandbox (container / git worktree)   ← Harness-Engineering/Sandboxing
      ↓
[verifier: test suite, linter, type-checker]  ← execution-based ground truth
      ↓ (fail → diagnose → retry, with failure log in context)
[deliver: git diff + summary + test report]
```
Key production decisions [I: engineering synthesis]:
- **Git worktree / branch isolation** — parallel agents on separate worktrees;
  the merge step is where conflicts surface (a *merge-reconciler* pattern — a
  neutral third-party LLM resolving two agent branches' conflicting edits — is
  common practice; cf. `Multi-Agent-Systems.md` § failure modes).
- **Step budgets + progress checkpoints** — auto-commit every k steps; a failed
  run can be resumed from the last green checkpoint.
- **Human-in-the-loop gates** — confirm-before-push / confirm-before-dependency
  change; the agent proposes, the human disposes on irreversible actions
  (`../Safety/`).
- **Model routing** — cheap model for search/summarize, frontier model for
  plan/edit; the `../Inference/Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md`
  router economics apply directly to agent step routing.

## Training SWE capability (2024–2026)
- **AgentTuning** (arXiv:2310.12823 [F]): SFT on agent trajectories established
  that generalized agent abilities can be *injected* by data.
- **SWE-Gym** (arXiv:2412.21139 [F]) + **Agent Q** (arXiv:2408.07199 [F]):
  RL pipelines — train in the environment with verifiable rewards (tests),
  i.e. RLVR at repo scale. The 2025+ frontier: SWE performance is increasingly
  *trained in* rather than scaffolded (`Agentic-AI-Evolution.md` § Phase 5).
- **Memorization risk**: SWE-bench Verified analysis
  (arXiv:2512.10218 [F]) — some "solved" issues may reflect model *memory* of
  the repo rather than ability; benchmark hygiene matters (held-out,
  recently-added issues).

## Economics (hand-computable, 2026 shape)
A hard SWE task: ~50–150 steps. At 8k in/step + 0.4k out/step, $3/M in + $15/M
out [A: prices]:
- 50 steps = 400k in + 20k out = 420k tokens ≈ $1.50 base [E: 8000·50·3/1e6 =
  $1.20 + 400·50·15/1e6 = $0.30]; 150 steps ≈ $4.50. Call it **$1.5–5 per hard
  task** with retries and long-context re-reads [A: the 1.5–3× multiplier is an
  assumption — agents re-read context and retry failed steps; retries dominate
  the cost, so we price it as a range, not a computation].
- vs human: a 4-h engineer task at loaded $50–150/h = $200–600.
- **Break-even**: agent cost is ~0.25–2.25% of human cost even after the
  1.5–3× retry/long-context overhead above [E: $1.5–4.5 ÷ $200–600 → 0.25–2.25%]
  — the economic case is not close; the
  *quality/reliability* case is the real constraint (wrong-but-passing-tests is
  the danger, not cost).

## Failure taxonomy (SWE-specific)
1. **Wrong-but-green** — a test suite that doesn't cover the change; the agent
   "passes" with a subtle regression. Mitigation: reviewer agent + human gate
   on public APIs.
2. **Scope creep** — the agent refactors the world to make its one fix compile.
   Mitigation: diff-size limits, "minimal change" prompt + harness check.
3. **Dependency drift** — upgrading a dep to make a test pass. Confirm-gate on
   lockfile changes.
4. **Context loss on big repos** — 100k-file repos exceed even long contexts;
   retrieval (grep-first) + module maps are mandatory (`Tool-Use.md` § Seam 1).
5. **Merge conflicts at rejoin** — parallel agents editing overlapping files;
   the worktree pattern moves the conflict to a detectable, resolvable point.

## Related
`Agentic-AI-Evolution.md` · `Tool-Use.md` · `Agent-Evaluation.md` ·
`../Harness-Engineering/Sandboxing.md` · `../Harness-Engineering/Context-Management.md` ·
`../Post-Training/Alignment-RLHF.md` (RLVR).

## Key Takeaways
SWE is the flagship because feedback is dense and the final state is verifiable.
The stack: search-first ACI, sandboxed worktrees, execution-based verification,
step budgets, and trained (not just prompted) SWE capability. Cost is never the
constraint — reliability is.
