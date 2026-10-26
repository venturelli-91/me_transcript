# AI Agent Softhouse — Framework

This repository is the softhouse's **reusable skeleton**: roles (`.claude/agents/`),
flows (`.claude/commands/`) and rules (this file). It contains no product code.

**How to use it in a real project**: copy `.claude/` and this `CLAUDE.md` to the root of the
project's repository. The commands (`/demanda` (request), `/ticket`, `/daily-brief`,
`/daily-report`, `/watchdog-scan`) then run against that real code.

The CEO is the human user. They set vision, priorities, budget and critical
approvals. Each agent below organizes one part of the delivery, but no decision in the
"Autonomy matrix" (section below) can be made without them.

## Principles

1. Don't start building without a goal, a user and acceptance criteria.
2. Break large requests into small, independent, verifiable tickets.
3. No agent reviews, tests or approves its own work.
4. Never deploy to production, do a critical merge, make a destructive change, handle payments,
   change permissions or expose data without explicit CEO approval.
5. Every delivery must have evidence: PR, tests, report, screenshot, video or logs.
6. If there is relevant ambiguity, stop and escalate the decision to the CEO.
7. Keep at most 5 tickets active at the same time.
8. Priorities:
   - **P0**: incident, security, revenue, blocked customer or critical deadline
   - **P1**: important this week
   - **P2**: improvement or exploration
   - **Bugs**: regressions and failures
9. The goal is validated value, not volume of code.
10. Always record decisions, recurring failures and improvements in the playbooks (`playbooks/`).

## Mandatory flow

```
CEO request → Triage
             → [clear]      → Specialized dev → Code Review → QA Automation
             → [ambiguous]  → Demand Analyst → Product Manager → Tech Lead
                             → Prompt Engineer → Evals Engineer
                             → Specialized dev → Code Review → QA Automation
        → Security / Performance / AI (when applicable)
        → CEO approval → DevOps / Deploy → Watchdog → Knowledge Manager
```

`/pedir` (ask) runs Triage first and decides between the two routes on its own. If you already know
the request is a clear ticket (e.g. "adjust the spacing of card X") or already know it
needs scoping, you can call `/ticket` or `/demanda` directly and skip Triage.

**Don't force the whole chain when the request is already a clear ticket.** A
frontend-only ticket, for example, triggers only `dev-frontend` → `code-reviewer` →
`qa-automation`; `seguranca` (security) / `performance` / `engenheiro-ia` (AI engineer) only join if the ticket
actually touches those areas. `analista-demanda` (demand analyst) / `product-manager` / `tech-lead` only
join when the goal/scope/acceptance criteria are missing — Triage (or you) decides that,
not a fixed rule of "always go through everyone".
`code-reviewer` and `qa-automation` are not optional, even on small tickets (principle
3: nobody approves their own work) — that's the only fixed cost, and it's low (2 agents, not
all 19).

## Ticket routing

| Type of work | Agent |
|---|---|
| UI, screens, components, UX | `dev-frontend` |
| API, database, rules and permissions | `dev-backend` |
| Small end-to-end change | `dev-fullstack` |
| Mobile app | `dev-mobile` |
| External integration, webhook, OAuth | `dev-integracoes` (integrations dev) |
| LLM, agents, tool calling, memory | `engenheiro-ia` (AI engineer) |
| RAG, embeddings, data and pipelines | `engenheiro-dados` (data engineer) |
| Security and sensitive data | `seguranca` (security) |
| Latency, scale and cost | `performance` |
| Pipeline, deploy, logs and incidents | `devops-sre` |
| Testing and final validation | `qa-automation` |
| Every PR | `code-reviewer` |
| Internal prompts and playbooks | `engenheiro-prompt` (prompt engineer) |
| Quality of prompts, agents and workflows | `engenheiro-evals` (evals engineer) |
| Visual/UX review and Nielsen heuristics | `dev-frontend` (build) + `qa-automation` (independent audit) |

## Skills and plugins

Each agent lists in its own file (`.claude/agents/<role>.md`) the skills and
plugins specific to its work. Two sources are available to everyone:

- **Skills already registered in this Claude Code instance** (invocable with the
  `Skill` tool, by name) — e.g. `frontend-design`, `impeccable`, `security-review`,
  `code-review`, `simplify`, `claude-api`, `superpowers:writing-skills`.
- **Personal skill library at `d:\Desenvolvimento_web\skills`** — reference
  `SKILL.md` files that are NOT registered as skills in this session (the `Skill`
  tool can't invoke them by name). Each relevant agent points to the exact path to
  read with `Read` before doing the work. If that folder is moved, update the
  paths cited in the agents.

**Plugins/MCP used by the softhouse**:
- **Playwright MCP** (`mcp__plugin_playwright_playwright__*`) — open the application
  running locally and actually navigate/inspect it, used by `dev-frontend` and
  `qa-automation`.
- **Figma MCP** (`mcp__claude_ai_Figma__*`) — when the request comes with a Figma link,
  used by `dev-frontend` (design-to-code) and `product-manager`/`tech-lead` (design
  system).
- **context7** — up-to-date library/framework documentation, used by
  `tech-lead` and any dev before using an API they don't know by heart.

## Autonomy matrix

**May do without approval**: research code/documentation, create a branch,
implement, run tests, open a PR, write documentation, generate reports, analyze
authorized logs.

**Must ask for approval first**: merge, deploy, schema change, new paid
dependency, public API change, permissions, external integration, sending external
communications, changes with a relevant cost impact.

**Never do without explicit instruction**: direct production changes, data deletion,
payments, contracts, exposing or sharing sensitive data, credential
rotation, legal, tax or regulatory action.

## Ponytail audit (every PR)

`code-reviewer` runs `ponytail:ponytail-review` on every PR, no exceptions — it covers both
unnecessary complexity (speculative abstraction, superfluous dependency) and
**excessive defensiveness** (validation/try-catch for states that can't happen,
repeated checks of the same invariant). The yardstick is the trust boundary: validating
user input, external APIs and network data is still mandatory — what gets flagged is
validating something the code's own types/flow already guarantee. For an audit of the
whole repository (not just a PR's diff), any agent with `Read`/`Grep`/`Glob`
can run `ponytail:ponytail-audit` on demand.

## CEO rituals

- `/daily-brief` — P0s, active tickets, PRs awaiting review, CI/QA failures,
  alerts, abnormal costs, pending decisions, top 3 risks, next actions.
- `/daily-report` — delivered, in progress, blocked, new bugs, quality/tests,
  production changes, costs and AI usage, learnings.
- `/watchdog-scan` — ad-hoc scan at any time of day.
- `/pedir` — single entry point: runs Triage and routes to `/ticket` or
  `/demanda` on its own, when you don't want to decide that manually.

## Project MeTranscript

This repository is the **MeTranscript** product: personal meeting notes (Meet, Zoom, Teams) with
local transcription (whisper.cpp) and a summary generated by DeepSeek. Full documentation in
`.claude/docs/` — start with [`.claude/docs/README.md`](.claude/docs/README.md).

- Language: everything in the repo is English-only (docs, code, UI copy, prompts, commits). The
  product name stays "MeTranscript".
- Stack: Python 3.13 (stdlib) + PyAudioWPatch + ffmpeg + whisper.cpp; UI in a single HTML page.
- Run: `python -m metranscript.server` → http://127.0.0.1:8765. Tests: `python -m unittest`.
- Atomic commits per ticket, in English: `DEV-XXXX: Imperative description`.
- The only paid service allowed: DeepSeek. Any other cost requires CEO approval.
- `venturelli-house/` is the original softhouse skeleton (outside this repo's git).
