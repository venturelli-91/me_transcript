---
description: Generates the end-of-day Daily Delivery Report and triggers the Knowledge Manager to record new learnings.
---

Invoke the `watchdog` subagent to gather what changed today (commits, merged PRs,
CI, costs) and build the report below. Then, if there's a new learning (a recurring
failure, a relevant decision, a pattern that paid off), invoke `gestor-conhecimento`
(knowledge manager) to record it in `playbooks/` before closing the report.

```
# Daily Delivery Report
## Delivered
## In progress
## Blocked
## New bugs
## Quality and tests
## Production changes
## AI costs and usage
## Learnings added to playbooks
```
