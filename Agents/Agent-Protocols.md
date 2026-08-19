# Agent Protocols (MCP, A2A, and the interop layer)
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
Before 2024, every agent was a bespoke glue of prompts + tool-call JSON that
only worked with one model's API shape. 2024–2026 added two open standards that
decouple agents from (a) *tools* and (b) *other agents*: **MCP** (Model Context
Protocol — the USB-C of agent↔tool wiring) and **A2A** (agent-to-agent
messaging). Together they are the "networking layer" of agentic AI
(`../Graph-Engineering/` treats the topology they enable).

## Why a protocol layer was needed (the pre-MCP mess)
The N×M problem: N agents × M tool servers = N×M bespoke integrations. A coding
agent that wanted 40 SaaS tools needed 40 hand-written tool-call adapters, each
in a different JSON dialect, each re-authing differently. [I] MCP collapses this
to **N + M**: any MCP client (agent) speaks one protocol; any MCP server (tool)
exposes one endpoint. The same shape as HTTP solved for web clients/servers.

## MCP (Model Context Protocol)
- **Origin:** Anthropic, announced 2024-11 [F: github.com/modelcontextprotocol
  — open standard; spec schema versioned 2024-11-05, 2025-03-26, 2025-06-18, 2025-11-25 (verified live against the spec repo 2026-08-19)]; adopted by
  OpenAI, Google, Microsoft and the major agent stacks through 2025 [F: vendor
  announcements; vendor-claim for "everywhere" adoption].
- **Shape:** a JSON-RPC-ish protocol over stdio (local) or HTTP (remote) with
  three primitive *server-exposed* capabilities [F: spec]:
  1. **tools** — callable functions (the classic tool-call surface),
  2. **resources** — addressable data (files, DB rows) the agent can read,
  3. **prompts** — reusable prompt templates the server offers.
- **Transport:** stdio for local (spawn a process per server — the model
  context "plugin" model), Streamable HTTP for remote; auth via HTTP headers /
  OAuth for remote [F: spec].
- **What it standardizes:** tool *discovery* (the client lists available tools +
  schemas — killing `../Agents/Tool-Use.md` § Seam 1), *invocation*, *results*,
  and *errors*. What it does **not** standardize: the model, the agent loop, or
  multi-agent coordination (that's A2A's lane).
- **The 2025 security wake-up:** early MCP servers ran as full-privilege local
  processes with unvetted tool code → prompt-injection-to-RCE was a live risk
  (several public incidents in 2025 [I: well-documented; treat specific counts as
  vendor-claim]). The mitigation stack: server sandboxing, tool allow-lists,
  human-confirm on write-ops, signed server bundles (`../Safety/`,
  `../Harness-Engineering/Sandboxing.md`).
- **Ecosystem:** thousands of community servers (DB, SaaS, search, browser)
  [F: directories]; the "MCP server" became a product category.

## A2A (Agent-to-Agent protocol)
- **Origin:** Google, open-sourced 2025-04 with IBM + ~50 partners [F:
  a2aprotocol.ai]; now an open standard under the Linux Foundation [F:
  announcement].
- **Shape:** an HTTP-based protocol where each agent exposes an **Agent Card**
  (a JSON manifest: name, capabilities, endpoint, auth) — analogous to MCP's
  tool-listing but at *agent* granularity. Messaging is task-centric: a client
  agent opens a **task** with a message; the server agent replies with status /
  artifacts, possibly asynchronously over long horizons (push notifications /
  webhooks for long-running work) [F: spec].
- **Why it's separate from MCP:** MCP answers "how do I call a *tool*?" A2A
  answers "how does one *agent* delegate to / collaborate with another *agent*
  (which may itself run a different model/vendor)"? The A2A server hides its
  internals — the client sees capabilities, not the other agent's prompts.
- **Relation to the MAS literature:** A2A is the *standardized* version of the
  orchestrator-worker and delegation patterns in `Multi-Agent-Systems.md` —
  except cross-organization. Pre-A2A, delegation only worked inside one
  framework (AutoGen agents could only talk to AutoGen agents).

## How the two compose (the 2026 topology)
```
 [agent A] ──MCP──▶ [tool server: DB, search, SaaS]   (intra-organization)
 [agent A] ──A2A──▶ [agent B (vendor X)]              (inter-agent, cross-org)
                       └──MCP──▶ [its own tool servers]  (B's private wiring)
```
MCP = the *edge* (agent↔tool). A2A = the *backbone* (agent↔agent). A production
system can use both: each agent wires its own tools via MCP and coordinates with
peers via A2A, keeping its tool graph private. [I: synthesis of both specs]

## What the protocols do *not* solve
1. **Trust / authn-authz semantics** — MCP/A2A give you a channel; the policy
   ("which agent may call which tool, with which data scope") is your
   application layer. `../Safety/`.
2. **Capability discovery quality** — an Agent Card / tool list is a *claim*;
   the agent must still verify a tool does what its schema says (the
   `../Agents/Tool-Use.md` § Seam 3 problem persists across the protocol).
3. **Observability / debugging** — distributed agent graphs are hard to trace;
   the 2026 practice is structured logging + a trace store per task
   (`../Graph-Engineering/Agent-Workflow-Graphs.md` § observability).
4. **Cost / fairness** — the protocol has no metering; cross-org agent
   economics (who pays for B's tokens when A delegates to B?) is
   application-level.

## Design lessons for anyone building an interop surface
1. **Manifests over code** — a declarative capability list (Agent Card / tool
   schema) beats a programmatic one for discoverability + security review.
2. **Errors as data** — both specs model errors as structured payloads with a
   *hint*, not free text (consistent with `../Agents/Tool-Use.md` § schema
   design).
3. **Async first for long horizons** — A2A's task model assumes responses can
   take minutes/hours; the 2024 MCP era (synchronous request/response) hit this
   wall on agent tasks and added streaming/async patterns.
4. **Version the schema, not the endpoint** — MCP's dated schema versions
   (2024-11-05 → 2025-11-25; verified live 2026-08-19) [F] let servers declare
   capabilities per version; a single endpoint, many schemas.

## Related
`Tool-Use.md` · `Multi-Agent-Systems.md` · `../Graph-Engineering/Agent-Workflow-Graphs.md` ·
`../Safety/README.md` · `../Networking/README.md` (transport-level context).

## Key Takeaways
MCP (agent↔tool) and A2A (agent↔agent) are the networking layer of agentic AI:
they turn the N×M integration problem into N+M, standardize discovery, and —
critically — let agents from different vendors coordinate. They solve the
*channel*, not *trust, policy, or economics* — those remain the application
layer's job.
