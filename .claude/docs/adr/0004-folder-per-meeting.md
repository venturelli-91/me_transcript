# ADR-0004: A folder of files per meeting instead of a database

**Date**: 2026-10-26
**Status**: accepted
**Deciders**: Claude

## Context
another note-taking app uses encrypted SQLite with FTS5, document/panel tables and cloud
sync. For a single user, with dozens of meetings a month, what matters is being able to open,
read and copy the summaries.

## Decision
`meetings/YYYY-MM-DD_HHMM/` with `meta.json`, `notes.md`, `transcript.md`, `summary.md` and the
WAVs. Listing = listing directories.

## Alternatives Considered

### SQLite
- **Pros**: search and queries.
- **Cons**: schema, migrations, files unreadable outside the app.
- **Why not**: search is out of scope; the file system already handles it.

## Consequences
### Positive
- Summaries readable in Explorer, Obsidian or VS Code; backup is copying the folder.
### Negative
- No search in the app.
### Risks
- With thousands of meetings, listing gets slow. Upgrade: a single JSON index.
