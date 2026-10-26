---
description: Turns a CEO request into a briefing, PRD and technical tickets, stopping to ask when there's relevant ambiguity.
---

CEO request: $ARGUMENTS

Run this chain, in order, using the Agent tool to invoke each subagent:

1. **`analista-demanda`** (demand analyst) — produce the Briefing (template in the
   agent's file). If the goal, affected user or acceptance criteria can't be filled in
   with confidence, stop here and ask the CEO before continuing (don't move forward on
   assumptions).
2. **`product-manager`** — from the approved briefing, produce PRD + stories +
   acceptance criteria + prioritized backlog. If any "pending decision" from the
   briefing blocks the scope, stop and escalate to the CEO.
3. **`tech-lead`** — from the PRD, produce architecture + small technical tickets
   (max. 5 active at a time, see `CLAUDE.md`), each already routed to the right agent via
   the table in `CLAUDE.md`.

At the end, present to the CEO:
- the briefing,
- the summarized PRD,
- the list of ready technical tickets, each with its responsible agent indicated,
- any pending decision that still needs approval before running `/ticket`.

Don't implement anything at this stage — the goal is to come out with tickets ready for
`/ticket <id-or-description>`.
