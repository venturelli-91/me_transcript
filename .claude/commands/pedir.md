---
description: Single entry point for any CEO request — runs Triage and automatically routes to /ticket (direct) or /demanda (needs scoping).
---

CEO request: $ARGUMENTS

1. Invoke the `triagem` (triage) subagent with the request above.
2. If triage concludes the request **is already clear enough for a direct ticket**:
   invoke the `ticket` skill (`Skill(skill: "ticket")`) passing the summarized ticket
   triage produced, already indicating the suggested agent/area.
3. If triage concludes **scope is missing** (goal, user, acceptance criteria):
   invoke the `demanda` skill (`Skill(skill: "demanda")`) passing the original request
   and what triage identified as missing, so the Demand Analyst doesn't redo work
   already done.
4. If triage identifies **more than one area** in the same request, warn the CEO and
   suggest splitting it into separate tickets before proceeding — don't run both chains
   at the same time without confirmation.

Use `/pedir` as the default when you're not sure whether the request is already a
ticket or still needs scoping. If you (the CEO) already know exactly what you want and
which area, you can go straight to `/ticket` or `/demanda` and skip triage.
