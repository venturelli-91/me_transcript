# ADR-0006: Meeting detection via the Windows ConsentStore

**Date**: 2026-10-26
**Status**: accepted
**Deciders**: Claude

## Context
another note-taking app uses a native Rust module (`MicActivityTrackerV2`) and a UI Automation
executable to detect meetings. Windows already records which apps are using the
microphone in
`HKCU\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone`.

## Decision
`detect.py` reads this key with `winreg` on every `/api/status` poll (1 s), outside the session lock. Entries with `LastUsedTimeStop == 0`
have the mic open; if the executable is Zoom, Teams or a browser, the page shows an alert.

## Alternatives Considered

### Process list / window titles
- **Pros**: identifies Meet by the tab title.
- **Cons**: an open process isn't a meeting; titles vary.
- **Why not**: microphone usage is the most faithful "meeting started" signal.
- **Update (DEV-0040, DEV-0042)**: titles are now a filter on top of the microphone signal, for browsers only: the
  alert needs one of that browser's own visible windows to have a meeting word in the title (`MEETING_KEYWORDS`).
  Zoom and Teams are still unconditional.

### UI Automation (like another note-taking app)
- **Pros**: high accuracy.
- **Cons**: fragile, per-platform native code.
- **Why not**: disproportionate complexity.

## Consequences
### Positive
- Zero dependencies, few lines.
### Negative
- A browser using the microphone doesn't necessarily mean Meet: an acceptable false
  positive, since it's only an alert.
### Risks
- The key format changes in a Windows update; the parser test catches it.
