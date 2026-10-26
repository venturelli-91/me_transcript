---
description: Generates today's Daily CEO Brief, using the Watchdog to gather the project's real state.
---

Invoke the `watchdog` subagent to scan the current project (git, CI, PRs, tickets,
AI costs when they can be measured) and build the brief below. If any source isn't
available in this environment (e.g., `gh` not configured), say so instead of making up
data.

```
# Daily CEO Brief
## P0
## Active tickets
## PRs awaiting review
## CI and QA failures
## Alerts and incidents
## Abnormal costs
## Pending CEO decisions
## Top 3 risks
## Recommended next actions
```
