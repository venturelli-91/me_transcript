# UI Redesign ("Index") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the MeTranscript page in the ArchiPro-inspired "Index" direction (Index list → Meeting article with resizable chat → pinned Recording strip) without losing any existing feature.

**Architecture:** Two small backend additions (optional `app` per meeting; richer `/api/meetings`), then the single `metranscript/web/index.html` is rewritten as hash-routed views (`#/`, `#/m/<id>`) on top of the existing JS helpers (`api`, `esc`, `markdown`, notes autosave, polling) and the unchanged API.

**Tech Stack:** Python 3.13 stdlib server, one HTML file with inline CSS/JS (no framework, no build), Google Fonts (one grotesque), Playwright MCP for UI verification, `python -m unittest`.

**Spec:** `.claude/docs/specs/2026-10-26-ui-redesign-design.md` (read it with this plan; mockups in `.superpowers/brainstorm/2042-1793052431/content/navigation-v2.html` option E and `index-detail.html`).

## Global Constraints
- Everything in English (UI copy, code, docs, commits). Commits `DEV-XXXX: Imperative description`, no Claude co-author/trailer.
- Tokens exactly: `--bg #FBF8F3`, `--surface #FFFFFF`, `--ink #181818`, `--gray #6B6B6B`, `--line #E7E2DA`, `--pill #E5E5E5`, `--dark #2B2B2B`, `--rec #C8412F`.
- Type scale exactly 12 / 14 / 16 / 20 / 28 / 40 px; nothing below 12 px; weight 400 (500 for small UI labels/buttons); tracking −0.02 em at 20 px, −0.03 em at ≥ 28 px; reading text 16 px / 1.6, max ~72 ch.
- Font: one free Google Fonts grotesque close to Neue Haas (Schibsted Grotesk or Hanken Grotesk), fallback `"Helvetica Neue", Helvetica, Arial, sans-serif`. Not Inter.
- Card radius ~21 px; buttons are pills; labels in parentheses, e.g. `(01) Summary`.
- WCAG AA contrast, visible focus, keyboard access, `prefers-reduced-motion`, no horizontal scroll at 400 px; drawer becomes a stacked section under 860 px.
- Single `index.html`, inline CSS/JS, CSP unchanged (fonts.googleapis.com / fonts.gstatic.com already allowed).
- Chat drawer: default 380 px, min 320 px, max `min(50vw, 640px)`, double-click handle → 380, ←/→ on focused handle ±16 px, width in `localStorage["metranscript.drawerWidth"]` (wrapped in try/catch).

## Review Focus
- A meeting with no summary and/or empty transcript (private, failed, or still processing) → article shows clear empty states, no `(02)`, no JS error. Tested in Task 4.
- A very long title (up to 200 chars) → wraps in Index row, article title and recording strip without overflow at 400 px. Tested in Task 2 and Task 3.
- Next-steps heading variants (`## Next steps`, `## Próximos passos`, different case, trailing spaces, `###`, missing) → split only on the `##` match, otherwise whole summary in `(01)`. Tested in Task 1 (server) and Task 4 (page).
- Reload or open `#/m/<id>` for a deleted/unknown meeting → back to Index with a sticky error, not a blank page. Tested in Task 2.
- Recording started elsewhere (banner, reminder `?record=`, another tab) while a Meeting article is open → strip appears on top, the article stays usable, stop opens the recorded meeting. Tested in Task 3.

---

### Task 1: Backend — meeting app and richer list (DEV-0015)

**Files:**
- Modify: `metranscript/store.py` (`create`, `list_meetings`; new `NEXT_STEPS_RE`, `has_next_steps`)
- Modify: `metranscript/server.py` (`start` and `/api/start` accept `app`)
- Test: `tests/test_store.py`

**Interfaces:**
- Produces: `store.create(title: str, lang: str, private: bool = False, now: datetime | None = None, app: str | None = None) -> str` (stores `"app"` in meta); `store.list_meetings() -> list[dict]` with keys `id, title, started_at, ended_at, private, app, has_summary, has_next_steps`; `store.NEXT_STEPS_RE` = `re.compile(r"^##[ \t]+(next steps|próximos passos)[ \t]*$", re.I | re.M)`; `store.has_next_steps(summary: str) -> bool`.
- Produces: `POST /api/start` body field `app` (optional; one of `"Meet"`, `"Zoom"`, `"Teams"`, `"Chrome"`, `"Edge"`, `"Firefox"`, `"Brave"`, `"Arc"` — anything else → 400 `"Unknown meeting app."`).

- [ ] **Step 1: Write failing tests** in `tests/test_store.py`:
  - `test_list_has_rich_fields`: create with `app="Meet"`, `private=True`, finish, save summary `"## Topic\n- a\n\n## Next steps\n- Me: x"` → listed item has `app == "Meet"`, `private is True`, `ended_at` not None, `has_summary is True`, `has_next_steps is True`.
  - `test_next_steps_heading_variants`: `has_next_steps` is True for `"## Next steps"`, `"## próximos passos  "`, `"x\n## NEXT STEPS\n- y"`; False for `"### Next steps"`, `"## Next steps and risks"`, `""`.
  - `test_old_meta_without_app_or_private`: write a `meta.json` without `app`/`private` → `list_meetings()` returns `app is None`, `private is False`.
- [ ] **Step 2: Run** `python -m unittest tests.test_store -v` → the three tests FAIL.
- [ ] **Step 3: Implement** the store changes (old metas read with `.get`), and in `server.py` pass `app` from `/api/start` through `start(...)` to `store.create`.
- [ ] **Step 4: Run** `python -m unittest` → all pass.
- [ ] **Step 5: Commit** (include the spec and this plan) `DEV-0015: Store the meeting app and enrich the meetings list`.

### Task 2: Shell, tokens and Index view (DEV-0016)

**Files:**
- Modify: `metranscript/web/index.html` (rewrite markup/CSS; keep and reuse existing helpers `api`, `esc`, `inline`, `markdown`, `clock`, notes save functions, `poll/refresh`, agenda/settings/quit/devices loaders)

**Interfaces:**
- Consumes: `/api/meetings` fields from Task 1; existing `/api/agenda`, `/api/settings`, `/api/quit`, `/api/status`.
- Produces (JS): `route()` reading `location.hash` (`""|"#/"` → Index, `"#/m/<id>"` → Meeting); `renderIndex(items)`; `openRecordSheet(prefill?: {title?: string, reminder?: string, app?: string})` (implemented in Task 3, stub that does nothing here); `showError(msg)` sticky status (reuse current `notice` logic) shown in the top bar status area; `numbering(items) -> Map<id, number>` with oldest = 1, zero-padded to 2 digits.

- [ ] **Step 1: Tokens + type scale + font** as `:root` variables and utility classes per Global Constraints; load the chosen Google Font with `display=swap`.
- [ ] **Step 2: Top bar**: left `Meetings` (→ `#/`) and `Upcoming (n)` (toggles the upcoming panel), centre wordmark `MeTranscript`, right red pill `● Record` (→ `openRecordSheet()`); a status line area under the bar for `showError` messages.
- [ ] **Step 3: Index view**: header `(Index – N meetings)`; filter pills `All` · `This week` (started_at within the last 7 days) · `With next steps` (`has_next_steps`) · `Private` (`private`); rows `NN · title (28 px) · app · date`, newest first, titles of meetings without summary in `--gray`; row is a focusable link to `#/m/<id>`; empty state "No meetings yet. Press Record to start your first one."
- [ ] **Step 4: Upcoming panel** (from top-bar link) reusing `loadAgenda` output with each event's `Record` pill calling `openRecordSheet({title, app})`; **Settings** block at the end of the Index: autostart toggle + `Quit MeTranscript` (reuse existing handlers).
- [ ] **Step 5: Router errors**: unknown/deleted `#/m/<id>` → `location.hash = "#/"` + `showError("That meeting no longer exists.")`.
- [ ] **Step 6: Verify with Playwright** at 1280 px and 400 px: Index renders the live list with stable numbers (create order), each filter narrows the list, a 200-char title wraps without horizontal scroll (`document.documentElement.scrollWidth <= innerWidth`), `#/m/does-not-exist` returns to Index with the error, keyboard Tab reaches filters and rows. Screenshots `.playwright-mcp/dev16-*.png`.
- [ ] **Step 7: Commit** `DEV-0016: Add the Index view and the new visual system`.

### Task 3: Record sheet and pinned recording strip (DEV-0017)

**Files:**
- Modify: `metranscript/web/index.html`

**Interfaces:**
- Consumes: `/api/start` (`title, lang, private, mic, speakers, reminder?, app?`), `/api/stop`, `/api/devices` GET/POST, `/api/status` (`phase, meeting_id, elapsed, levels, devices, detected, segments, error`).
- Produces (JS): `openRecordSheet(prefill)` (real implementation); `renderStrip(status)`; live view rendered in the Meeting route when `status.phase === "recording" && status.meeting_id === id`.

- [ ] **Step 1: Record sheet** (modal dialog with focus trap, Esc closes): title input, Portuguese/English, private checkbox, Microphone + Speakers selects with "Refresh devices" (reuse `loadDevices`/`fillDevices`, defaults preselected every time), dark pill `Start recording` → `POST /api/start` with `app` from prefill; on success navigate to `#/m/<new id>`.
- [ ] **Step 2: Strip** pinned at top on every route while `phase` is `recording|transcribing|enhancing`: stop button (white ring, red square; `aria-label="Stop recording"`), `(Recording – <title>)`, clock 28 px tabular, `Me <mic>` / `Others <speaker>` with level meters; clicking a device name opens a small menu of devices that calls `POST /api/devices` (reuse DEV-0014 handler, sticky error on failure); when not on the recording's article, a `Back to recording` pill; transcribing/enhancing show `Finishing the transcript…` / `Writing the summary…` and disable stop.
- [ ] **Step 3: Live view** on the recording meeting's route: two columns `(Your notes)` (existing autosave) and `(Live transcript – updates every ~30 s)` feed (`Me`/`Others`), single column < 860 px.
- [ ] **Step 4: Entry points**: meeting-detected banner button → `openRecordSheet({app: detected.app})`; `?record=<token>` → start directly with `reminder` (no sheet) as today; phase `recording → done` while on any route → navigate to `#/m/<id>` of that meeting.
- [ ] **Step 5: Verify with Playwright** (always tick Private): start from the sheet with a 200-char title → strip shows it without overflow at 400 px; open another meeting during recording → strip stays, `Back to recording` returns; switch mic from the strip; stop → article of that meeting opens; banner and `?record=bogus` (expired message) still work. Screenshots `.playwright-mcp/dev17-*.png`.
- [ ] **Step 6: Commit** `DEV-0017: Add the record sheet and the pinned recording strip`.

### Task 4: Meeting article and resizable chat drawer (DEV-0018)

**Files:**
- Modify: `metranscript/web/index.html`
- Modify: `.claude/docs/features.md`, `.claude/docs/architecture.md`, `.claude/docs/backlog.md`, `README.md` (UI description and screenshots wording)

**Interfaces:**
- Consumes: `GET /api/meetings/<id>` (`summary, notes, transcript, chat, can_undo, private, email_configured, emailed_at, email_error, started_at, ended_at, lang`), `/summary`, `/undo`, `/email`, `/chat`, `PUT /notes`; `NEXT_STEPS_RE` semantics from Task 1.
- Produces (JS): `splitSummary(md: string) -> {summary: string, nextSteps: string | null}` using the same regex as `store.NEXT_STEPS_RE` (JS: `/^##[ \t]+(next steps|próximos passos)[ \t]*$/im`, split at the **last** match).

- [ ] **Step 1: Article** for `#/m/<id>`: `(Meeting – NN)` (number from Task 2), title, meta line (date, duration from `ended_at − started_at` as `34 min`, app, language, `Private` or email status text from current `mailStatus()`), sections `(01) Summary` (+ pills `Regenerate`/`Generate summary`, `Undo`, `Email it to me`, status), `(02) Next steps` only when `splitSummary` finds it, `(03) Notes` (existing autosave), `(04) Transcript` (first 20 lines + `Show all`; each line gets `id="t-HHMMSS"`).
- [ ] **Step 2: Empty states**: no summary → "No summary yet." + `Generate summary` (hidden for private); empty transcript → "No transcript."; still processing → the strip's progress text, sections disabled.
- [ ] **Step 3: Chat drawer** "Ask this meeting" (reuse current chat send/include/undo logic and private disabling): resizable per Global Constraints (pointer drag on the handle, `role="separator"` `aria-orientation="vertical"` `aria-valuenow`), stacked under the article below 860 px.
- [ ] **Step 4: Timestamp links**: in rendered chat answers, `[HH:MM:SS]` becomes a link that expands `(04)` if needed, scrolls to `#t-HHMMSS` (nearest earlier line if exact one missing) and highlights it for 2 s (no animation under reduced motion).
- [ ] **Step 5: Verify with Playwright**: the test meeting shows `(02)` split out (and a summary without the heading shows no `(02)`); a meeting with no summary/transcript shows empty states without console errors; drawer drag clamps at 320 px and `min(50vw, 640px)`, double-click resets to 380, width survives reload, ←/→ resize via keyboard; timestamp link scrolls to the line; 400 px layout has no horizontal scroll. Screenshots `.playwright-mcp/dev18-*.png`.
- [ ] **Step 6: Docs**: features (UI section rewritten to Index/Meeting/Recording), architecture (routes `#/`, `#/m/<id>`, `splitSummary`, `has_next_steps`), backlog (DEV-0015…0018), README usage steps.
- [ ] **Step 7: Commit** `DEV-0018: Add the meeting article and the resizable chat drawer`.
