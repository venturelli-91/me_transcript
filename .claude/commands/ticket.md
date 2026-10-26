---
description: Implements a technical ticket by routing it to the right dev, then enforces independent code review and QA, never merging/deploying on its own.
---

Ticket: $ARGUMENTS

Run this chain, in order, using the Agent tool:

1. Check the routing table in `CLAUDE.md` and pick the correct dev subagent
   (`dev-frontend`, `dev-backend`, `dev-fullstack`, `dev-mobile`, `dev-integracoes`,
   `engenheiro-ia` or `engenheiro-dados`). If the ticket doesn't make clear which agent
   to use, ask the CEO instead of guessing.
2. Invoke the chosen dev with the full ticket. It must deliver a small PR, tests,
   summary, validation instructions and risks/open items.
3. Invoke **`code-reviewer`** (never the same agent that implemented it) on the
   resulting PR — this mandatorily includes the Ponytail audit (unnecessary complexity
   **and** excessive defensiveness, see `code-reviewer.md`). If it returns
   "blocking comments", go back to step 2 before continuing.
4. Invoke **`qa-automation`** on the PR approved in review. If "rejected", go back to
   step 2 with the reported bugs.
5. If the ticket touches security, sensitive data, performance/cost or AI, also invoke
   `seguranca` / `performance` / `engenheiro-ia` (whichever applies) before step 6.

6. Stop here. List for the CEO: what was implemented, evidence (tests, review, QA),
   and what's strictly missing for approval — merge and/or deploy never happen without
   explicit CEO approval in this conversation (autonomy matrix in `CLAUDE.md`). Only
   after approval, if a deploy is involved, invoke `devops-sre`.
