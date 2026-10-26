# UI redesign — "Index" direction (DEV-0015)

**Date**: 2026-10-26 · **Decided by**: CEO (direction, palette, navigation, chat width) · **Builder calls** are marked *(call)*.

## Why
The current single page (dark green "deck", sidebar, tabs) works but feels too plain, and the
experience is not good yet. The CEO likes **archipro.co.nz**: its **navigation and palette** — an
editorial, magazine-like site — but finds its typography **disproportionate** (measured: headlines
79–99 px next to 6.5–10.5 px text, nothing in between). Among five mockups he chose **E · Index**: meetings as a
large numbered typographic list, each meeting opening as a long article with numbered sections.

## Goals
- Look and feel of ArchiPro: warm off-white and white surfaces, near-black and gray text, pill
  buttons, ~21 px rounded cards, generous whitespace, parenthesised labels such as `(01) Summary`,
  a loose `→` arrow, regular-weight (400) grotesque type with tight tracking on large sizes.
- A **proportional type scale** (each step ≈1.25×): 12 label · 14 interface · 16 reading · 20 section ·
  28 title · 40 display (display used sparingly). No text below 12 px.
- Navigation built around three screens: **Index** (home), **Meeting** (article), **Recording** (live).
- Keep every existing feature working (see "Feature inventory").

## Non-goals
- No backend changes beyond what the UI strictly needs (ideally none).
- No new JS framework, bundler or build step; stays one `index.html` with inline CSS/JS.
- No dark mode, no photography (the app has no images; colour comes only from the record red).

## Anti-goals
- Copying ArchiPro's extreme size jumps or its 7 px text.
- Hiding live state: while recording, the clock, devices and levels must always be visible.
- Regressions in accessibility: WCAG AA contrast (gray text ≥ 4.5:1 on its background), visible focus,
  keyboard access, `prefers-reduced-motion`, works at 400 px wide.

## Palette and type
| Token | Value | Use |
|---|---|---|
| `--bg` | `#FBF8F3` | page background (warm off-white) |
| `--surface` | `#FFFFFF` | top bar, cards, drawer |
| `--ink` | `#181818` | primary text |
| `--gray` | `#6B6B6B` | secondary text, labels (≥ 5:1 on `--bg`) |
| `--line` | `#E7E2DA` | hairlines, card borders |
| `--pill` | `#E5E5E5` | default pill button |
| `--dark` | `#2B2B2B` | primary pill, active filter, recording strip |
| `--rec` | `#C8412F` | record button, live indicators only |

Font: a Neue Haas Grotesk-like grotesque at weight 400 (500 for small UI labels/buttons). *(call)*
Load one free Google Fonts grotesque close to Neue Haas (e.g. "Schibsted Grotesk" or "Hanken
Grotesk"; avoid overused faces like Inter), falling back to `"Helvetica Neue", Helvetica, Arial,
sans-serif`. Tracking −0.02 em at 20 px, −0.03 em at 28 px and up.
Reading text 16 px / 1.6 line-height; max line length ~72 ch.

## Screens

### 1. Index (home, `/`)
- **Top bar** (white): left links `Meetings` · `Upcoming (n)`; centre wordmark `MeTranscript`;
  right a red pill `● Record`.
- Header line: `(Index – 24 meetings)`.
- **Filters** as pills: `All` · `This week` · `With next steps` · `Private`. *(call: "With next steps"
  = summary contains a next-steps section; client-side filter.)*
- **List**: one row per meeting — index number `01`, title at 28 px, app (`Meet`/`Zoom`/`Teams`/—),
  date; hairline between rows; hover/focus underlines the title. Meetings without a summary show the
  title in gray. Click/Enter opens the meeting.
- **Upcoming** panel (from DEV-0013): reached from the top-bar link; shows next linked meetings with
  time, app and a `Record` pill; the existing "add GOOGLE_CALENDAR_ICS" hint when not configured.
- **Before recording** (opened by `● Record`): a sheet/panel with title input, language (Portuguese /
  English), private checkbox, **Microphone** and **Speakers / headphones** selects with "Refresh
  devices", and a dark `Start recording` pill. Replaces today's always-visible deck.
- **Settings** (small, end of page or under a `Settings` link): "Run in background and start with
  Windows" toggle and "Quit MeTranscript".

### 2. Meeting (article)
- Top bar shows `← Index` instead of the links.
- Label `(Meeting – 01)`, title 28–40 px, meta line: date, duration, app, language, `Private` or
  `Sent to Gmail` / email status.
- Numbered sections separated by hairlines, each with a left label column:
  `(01) Summary` (rendered Markdown), `(02) Next steps` *(call: extracted from the summary's next-steps
  heading when present; otherwise the section is omitted)*, `(03) Notes` (editable textarea, autosave
  as today), `(04) Transcript` (first ~20 lines + `Show all`).
- Summary actions as pills under (01): `Regenerate` / `Generate summary`, `Undo`, `Email it to me`,
  and the status line (sending / sent / not configured) — same behaviour as today.
- **Chat drawer** "Ask this meeting" on the right: message list, "Add to summary" on answers,
  input pill at the bottom. **Resizable**: default **380 px**, drag handle on its left edge,
  min **320 px**, max **min(50% of viewport, 640 px)**; double-click the handle resets to 380 px;
  width remembered per browser in `localStorage` *(call)*. Keyboard: handle focusable, ←/→ resize by
  16 px. Under 860 px the drawer becomes a full-width section below the article.
- Timestamps like `[00:12:40]` in chat answers are links that scroll to and highlight that line in
  (04) Transcript (expanding it if needed). *(new, small)*
- Private meetings: drawer shows the existing "private" note and is disabled; no email button.

### 3. Recording
- A **dark strip fixed at the top** replaces the top bar while recording: stop button (white ring,
  red square), label `(Recording – <title>)`, clock at 28 px tabular, and on the right
  `Me <mic name>` and `Others <speaker name>` each with a thin level meter; device names are
  clickable to switch device mid-recording (same `/api/devices` flow as DEV-0014).
- Below: two columns — `(Your notes)` textarea and `(Live transcript – updates every ~30 s)` feed
  with `Me` / `Others` labels. Single column under 860 px.
- After stop: strip shows `Finishing the transcript…` / `Writing the summary…`, then the app opens
  the Meeting article for that recording.
- The "meeting detected" banner (DEV-0007) and reminder `?record=` flow (DEV-0013) open the
  Before-recording sheet prefilled (title from the reminder) and start as today.

## Feature inventory (must keep)
Record/stop, title, language, private; device selection and mid-recording switch; live notes with
autosave and failed-save retry; live transcript feed; meeting list; summary render; regenerate, undo,
email; chat with "Add to summary"; meeting-detected banner; calendar upcoming list and reminder
token flow; background/autostart toggle; quit; sticky status errors; all current API calls.

## Constraints
- Same API (`metranscript/server.py`) except the two small additions in "Decisions from the
  builder check" (optional `app` on start; richer `/api/meetings`). Duration is derived in the page
  from `started_at`/`ended_at`.
- `metranscript/web/index.html` stays a single file; CSP unchanged except adding the chosen Google
  Fonts host if needed (already allows fonts.googleapis.com / fonts.gstatic.com).
- Pages are client-side views of one HTML file (hash routes `#/`, `#/m/<id>`) *(call)*; reload keeps
  the current view.

## Decisions from the builder check *(calls)*
1. **Meeting app** (`Meet`/`Zoom`/`Teams`): small backend change — `/api/start` accepts an optional
   `app`, filled from the reminder event or the meeting-detected banner, stored in `meta.json`.
   Manual recordings and older meetings show no app (the column is simply empty, not "—").
2. **List data**: `/api/meetings` also returns `private`, `ended_at`, `app` and `has_next_steps`
   (server checks the summary for the next-steps heading), so the Index needs one request and the
   filters and durations work client-side. Small backend change, covered by store tests.
3. **Browsing while recording is allowed**: the dark recording strip stays pinned on top of every
   route (Index, any Meeting), replacing the top bar; it has a `Back to recording` affordance when
   you are on another page. Stop → the strip shows progress → the recorded meeting's article opens.
4. **Next steps appear once**: the page splits the summary Markdown at its last `##` heading matching
   "Next steps"/"Próximos passos" (case-insensitive); that part renders in `(02) Next steps`, the rest
   in `(01) Summary`. Email and storage keep the full summary. No match → no `(02)` section.
5. **Index numbers are stable**: numbered by age, oldest = `01`, newest has the highest number; the
   list is still sorted newest first. `(Meeting – 24)` keeps identifying the same meeting.

## Left to the builder
Exact spacing values, hover/focus details, the grotesque font choice within the rule above, the
Before-recording sheet's exact form (modal vs inline panel), empty states copy, and motion (one
subtle transition at most, respecting reduced motion).

## Verification
- Playwright pass over the three screens at 1280 px and 400 px; keyboard-only walkthrough;
  contrast check of gray on `--bg`/`--surface`; QA re-runs F2–F10 acceptance criteria.
- `python -m unittest` still green (no backend change expected).
