# Code standards

## Principles
- **Ponytail ladder**: does it need to exist? → already here? → stdlib? → native feature?
  → already-installed dependency? → one line? → only then the minimum.
- No speculative abstraction: no interface with a single implementation, factory, plugin
  or config for a value that never changes.
- Few files, each with a clear responsibility (see `architecture.md`).

## Python
- Python 3.13, PEP 8, type hints on public functions, `pathlib.Path` for paths.
- Small functions; a module exposes plain functions, a class only when there is real state
  (e.g. a recording in progress).
- No comments explaining WHAT the code does. Comments only for a non-obvious WHY.
- A deliberate shortcut gets `# ponytail:` with its ceiling and upgrade path.
- Log with `logging`, never `print` in product code. Never log the API key.

## Errors and validation
- Validate at the **trust boundary**: HTTP body, DeepSeek response, subprocess output
  (ffmpeg, whisper-cli), Windows registry.
- Inside the code, trust the invariant — no try/except for impossible states.
- An error that prevents the summary never deletes notes or transcript; it goes to `Session.error` and
  shows up in the UI.

## Frontend
- One `index.html` with inline CSS and JS, no framework and no build step.
- `fetch` + polling; no WebSocket.
- Basic accessibility: labels, visible focus, contrast, `aria-live` on the status.

## Tests
- stdlib `unittest`, in `tests/test_<module>.py`. Run: `python -m unittest`.
- Test pure logic (store, Me/Others merge, registry parser, prompt assembly).
  Audio and network are validated manually/by QA, not with elaborate mocks.

## Commits
- One commit per `backlog.md` ticket, atomic, in English:
  `DEV-0004: Add dual-track audio capture`.
- `Co-Authored-By` footer when generated with Claude.
- Never commit `meetings/`, `bin/`, `models/`, `.env`.

## Language
- Everything in the repo is in English: docs, code, comments, UI copy, prompts, commits.
  The product name stays "MeTranscript".

## Process (softhouse)
Per ticket: dev for the right role → `code-reviewer` (+ `ponytail:ponytail-review`) →
`qa-automation` → commit. Nobody reviews their own work.
