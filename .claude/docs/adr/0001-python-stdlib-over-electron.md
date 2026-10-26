# ADR-0001: Python stdlib + local page instead of Electron

**Date**: 2026-10-26
**Status**: accepted
**Deciders**: CEO, Claude

## Context
another note-taking app is an Electron app (~250 MB) with native modules in Rust and C++. The CEO asked for
something simple, without overengineering, that they can maintain themselves. Windows audio and
Whisper have the best support in Python.

## Decision
One Python process using the stdlib (`http.server`, `winreg`, `urllib`, `wave`,
`threading`) serving a single HTML page on `127.0.0.1`.

## Alternatives Considered

### Electron
- **Pros**: same base as another note-taking app; `getDisplayMedia` gives loopback for free.
- **Cons**: heavy, complex build and packaging.
- **Why not**: the CEO explicitly vetoed it.

### Tauri
- **Pros**: lightweight, native app.
- **Cons**: requires Rust and a build toolchain.
- **Why not**: build complexity with no gain for a single user.

### Local Next.js
- **Pros**: the CEO's usual stack.
- **Cons**: native audio capture and subprocesses are worse in Node; unnecessary build step.
- **Why not**: the hard part (audio/whisper) is better in Python.

## Consequences
### Positive
- One Python dependency (PyAudioWPatch); runs with `python -m metranscript.server`.
### Negative
- The page must be open to see the meeting alert.
### Risks
- Network exposure: mitigated by listening only on `127.0.0.1`.
