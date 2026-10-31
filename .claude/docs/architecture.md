# Architecture

## Overview

```
 browser (web/index.html)
      │  polling /api/status (1 s), fetch JSON
      ▼
 server.py ──── store.py ──── meetings/<id>/  (files)
      │
      ├── capture.py    PyAudioWPatch: mic + loopback  → mic.wav, system.wav
      ├── transcribe.py after the stop: 30 s windows → ffmpeg → whisper-cli → segments
      ├── enhance.py    urllib → DeepSeek → summary (summary.md) and chat (chat.json)
      ├── detect.py     winreg ConsentStore → meeting app using the mic?
      └── mail.py       Gmail API (as a connected Google account) → summary to your own email
      ├── google.py     Google sign-in (OAuth + PKCE), DPAPI-protected logins, access tokens, `api()` calls
```

One Python process, no framework. `server.py` is the only module that knows all the
others; the rest don't import each other (except `transcribe` reading the WAVs that
`capture` writes, via file path).

## Modules

| Module | Responsibility | Depends on |
|---|---|---|
| `store.py` | Create/list/read/save a meeting; `transcript.md` format | stdlib |
| `capture.py` | Open mic and loopback, record native WAV, expose audio level | PyAudioWPatch |
| `transcribe.py` | Read new chunks from the WAVs, convert, transcribe, interleave Me/Others, drop speaker echo | ffmpeg, whisper-cli |
| `enhance.py` | Build messages with `prompt.md` and call DeepSeek | stdlib (`urllib`) |
| `detect.py` | Read the registry and report which meeting app has the mic open; for browsers, check their window titles | stdlib (`winreg`, `ctypes`) |
| `server.py` | HTTP, recording session state, orchestration | all of the above |

## Session state
A single `Session` object in `server.py`, guarded by a `threading.Lock`:
`phase` ∈ `idle | recording`, `meeting_id`, `recorder`, `error` for the recording in progress, plus `jobs`:
`{meeting_id: {phase: queued | transcribing | enhancing | error, progress, error}}` for meetings whose recording
already stopped. A finished job is removed; a failed one stays until that meeting is retried or deleted.

ponytail: one recording at a time; processing runs in the background, so the next meeting can be recorded
right away. One whisper run at a time: meetings wait in `_queue` (`_turn()` context manager) and show as `queued`;
`prioritize` moves one to the front and `cancel` takes one out (its WAV is compressed, so it is not resumed and can be
re-transcribed later). A running job cannot be cancelled.

On start, `resume_unfinished()` queues every meeting that has `ended_at` but still a WAV (`store.unfinished()`): the WAV
is only removed once the transcript is done, so a leftover one means the app closed while processing it.

While another meeting is being recorded, a job that ends (summary ready, or failed) shows a silent Windows toast
(`_notify_done`, `desktop.notify(..., silent=True)`) that opens that meeting.

## Meeting flow
1. `POST /api/start` → `store.create()` → `capture.start()`. Nothing is transcribed during the call (DEV-0059).
2. `POST /api/stop` → `capture.stop()` → `_finalize` builds a `Transcriber` and walks the whole audio in windows: each one takes the stretch of
   each WAV (`ffmpeg -ss/-t` → 16 kHz mono) and runs it through Silero VAD (`whisper-vad-speech-segments`); with ≥ 0.5 s of speech, it runs
   `whisper-cli -l <lang> -ot <speech start> -oj` on the window (GPU via Vulkan), at Windows low priority. Output is read as lenient UTF-8,
   decoding loops are collapsed (`collapse_repeats`), a window that fails is skipped (`Transcriber.skipped`). Segments with absolute
   timestamps are appended to `transcript.md` per window, and the job's `progress` (0-1) is exposed in `/api/status`.
   The session is free again as soon as `stop` returns: a new recording can start while this one is processed.
3. Then the job phase becomes `enhancing` →
   `enhance.summarize()` → `summary.md` → job removed. A transcription or summary failure →
   job phase `error` with a message; nothing saved is deleted. A private meeting skips the summary.
4. In an open meeting, each chat message calls `enhance.chat()` (JSON mode): the answer goes
   to `chat.json`; if it includes `summary`, the previous version goes to `summary-history.json` and the new
   text to `summary.md`. "Undo" restores the latest version from the history.

## API contract (JSON, 127.0.0.1 only)

| Method and route | Body | Response |
|---|---|---|
| `GET /` | — | `web/index.html` |
| `GET /api/status` | — | `{phase: "idle"\|"recording", meeting_id, elapsed, levels:{mic,system}, devices, jobs:{<id>:{phase, progress, error}}, detected, error, low_disk_gb}` (`low_disk_gb` is `null` unless under 5 GB is free) |
| `GET /api/meetings` | — | `[{id, title, started_at, has_summary}]` |
| `GET /api/meetings/<id>` | — | `{id, title, lang, private, started_at, ended_at, notes, transcript, summary, chat, can_undo}` |
| `POST /api/start` | `{title?, lang: "pt"\|"en", private?: bool}` | `{id}` · `409` if already recording |
| `POST /api/stop` | — | `{}` (processing continues in the background) |
| `POST /api/meetings/<id>/prioritize` | — | `{}` · `409` unless that meeting is `queued` |
| `POST /api/meetings/<id>/cancel` | — | `{}` · `409` unless that meeting is `queued` |
| `PUT /api/meetings/<id>/notes` | `{notes}` | `{}` |
| `POST /api/meetings/<id>/summary` | — | updated meeting (regenerates the summary; synchronous) |
| `POST /api/meetings/<id>/chat` | `{message}` (1–4000 characters) | updated meeting |
| `PUT /api/meetings/<id>/title` | `{title}` | updated meeting |
| `DELETE /api/meetings/<id>` | — | `{}` · `409` while that meeting is recording or processing |
| `POST /api/meetings/<id>/undo` | — | updated meeting · `409` if there is no previous version |
| `POST /api/meetings/<id>/email` | — | updated meeting · `409` if private, no summary, or send failure |

Every write requires a local `Host` and `Content-Type: application/json` (blocks DNS rebinding and
POSTs from other sites).

Segment: `{"t": 83.2, "who": "Me" | "Others", "text": "..."}` (`t` in seconds since the start).

## On-disk formats
- `meta.json`: `{"title", "lang", "private", "started_at", "ended_at", "consent_at", "emailed_at"?, "email_error"?}`
  (local ISO 8601). The meeting `GET` adds `email_configured`.
- `chat.json`: `[{"role": "user"|"assistant", "content", "changed_summary"?}]`.
- `summary-history.json`: previous summary versions (stack for "Undo").
- Writes are atomic (`.tmp` + `os.replace`) under a global lock.
- `transcript.md`: one line per segment — `[00:01:23] **Others:** text`.
- `notes.md`, `summary.md`: free-form Markdown.
- `mic.wav`, `system.wav`: 16-bit PCM in the device's native format, only during recording.
  Deleted when transcription finishes successfully (~1.4 GB/h saved); kept if it fails.

## Configuration
| Variable | Default |
|---|---|
| `DEEPSEEK_API_KEY` | — (required for summary and chat; read from the environment or `.env`) |
| `ATA_WHISPER` | `bin/vulkan/whisper-cli.exe` (local Vulkan build) |
| `ATA_THREADS` | `4` |
| `ATA_MODEL` | `models/ggml-large-v3-turbo-q5_0.bin` |
| `ATA_VAD` | `models/ggml-silero-v5.1.2.bin` |
| `ATA_PORT` | `8765` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | — (your Google Cloud client; enables the Google sign-in) |
| `MEETING_KEYWORDS` | `Meet,Zoom,Teams` (words a browser window title needs for its mic use to raise the alert) |

`metranscript/settings.py` (`env()`) reads variables from the environment and, if missing, from `.env`.

## Calendar reminders and background mode (DEV-0013)
- `agenda.py`: every 5 min asks the Calendar API (`events.list`, primary calendar, `singleEvents=true`, next 24 h) for each connected Google account
  (`collect()`, merged by time, an account that fails is reported without hiding the others), keeps linked/timed/accepted future events (`upcoming()`), and decides
  which reminders are due (`due()`: 30 min, then 2 min; one per occurrence, persisted in
  `meetings/reminders-sent.json`). Runs in a `Watcher` thread started by `server.main()`.
- `desktop.py`: Windows notifications (constant PowerShell script + XML in an env var; event text is
  never code) and the `HKCU\...\Run` autostart value
  (`pythonw.exe start.pyw`, no console; logs go to `metranscript.log`).
- The 2-minute reminder's "Record" button opens `/?record=<token>`; the page posts the token to
  `/api/start` (`reminder` field), which maps it to the event title and discards it.
- A second instance (port in use) exits quietly, so autostart plus a manual start never conflict.

| Method and route | Body | Response |
|---|---|---|
| `GET /api/agenda` | — | `{configured, events: [{key, title, start, app, account}], error}` |
| `GET /api/settings` | — | `{autostart}` |
| `POST /api/settings` | `{autostart: bool}` | `{autostart}` |
| `POST /api/quit` | — | `{}` · `409` while recording or processing |

## Audio device selection (DEV-0014)
- `capture.list_devices()` lists WASAPI microphones and output devices (via their `[Loopback]` twins).
- `Recorder(folder, mic, speakers)` opens the named devices (or the defaults). **All PortAudio calls run
  on one long-lived Recorder thread** fed by a job queue: WASAPI binds streams to the COM apartment of
  the thread that initialized PortAudio, so opening a stream later from an HTTP thread fails with
  `-9999 Unanticipated host error`. The same thread pads silence and watches for dead streams.
- `Recorder.switch(track, name)` opens the new stream first and only then closes the old one; mono/stereo
  are converted on the fly (`convert_channels`); a different sample rate is refused.
- PortAudio enumerates devices once per session: a device plugged in mid-recording appears in the next one.

| Method and route | Body | Response |
|---|---|---|
| `GET /api/devices` | — | `{mics: [{name, default}], speakers: [{name, default}]}` |
| `POST /api/devices` | `{track: "mic"\|"system", name}` | devices in use · `409` if not recording, not found or incompatible |

`POST /api/start` also accepts optional `mic` and `speakers` names; `/api/status` reports `devices` in use.

## Page structure (DEV-0016)
- One `metranscript/web/index.html`, hash-routed: `#/` (Index) and `#/m/<id>` (Meeting article, or the
  live view when that meeting is being recorded). Unknown ids return to `#/` with a sticky error.
- `/api/meetings` also returns `ended_at`, `private`, `app` and `has_next_steps`
  (`store.NEXT_STEPS_RE`; `store.load()` also returns `summary_body` and `next_steps`, split by `store.split_summary()`).
- `POST /api/start` accepts an optional `app` (from the detected-meeting banner or a calendar event).
- The recording strip is driven by the 1 s `/api/status` poll and pinned on every route; when the
  recording finishes, the page opens that meeting's article.

## Transcription windows and audio (DEV-0031, DEV-0032)
- Each window is analyzed first (ffmpeg clip + Silero VAD for both tracks); `pick_cut` ends it in the latest
  pause of the union of both speakers' speech, then whisper runs with `-ot <speech start> -d <to the cut>`.
- `--prompt` = "This meeting mentions <terms>." (language of the meeting) + the last 200 characters of that
  speaker's previous window.
- After a successful transcription the WAVs become Opus (`transcribe.to_opus`) and `store.expire_audio()` removes
  Opus files older than `AUDIO_KEEP_DAYS` (default 30) at start and every 6 hours (`server._retention_loop`). `POST /api/meetings/<id>/retranscribe` decodes the saved audio,
  replaces the transcript (`transcript.previous.md` keeps the old one) and rewrites the summary; `409` if busy
  or there is no audio.

## Local fonts, browser detection and echo (DEV-0039 to DEV-0043)
- Fonts: `GET /fonts/<name>.woff2` serves the two Hanken Grotesk subsets and the JetBrains Mono subset (timecodes, numbers) in `metranscript/web/fonts/` (with `OFL-HankenGrotesk.txt` and `OFL-JetBrainsMono.txt`);
  only direct children of that folder with a `.woff2` suffix are served, the query string is ignored, and the page's
  CSP is `font-src 'self'`, so the page makes no request outside `127.0.0.1`.
- About page: `GET /about/<name>.png` serves the fictional screenshots in `metranscript/web/about/` (same whitelist rules as the fonts, `.png` only, CSP `img-src 'self' data:`); `GET /api/policy?lang=en|pt` returns `PRIVACY.md` or `PRIVACY.pt.md` (anything else falls back to English).
- Detection: for a browser executable, `detect.meeting_window(exe)` lists the visible top-level windows owned by that
  process (`EnumWindows` + `QueryFullProcessImageNameW`) and matches `MEETING_KEYWORDS` as whole words, any case.
  Only the active tab's title is visible, so a meeting in a background tab is missed.
- Echo: `transcribe.merge` drops a "Me" segment of 4+ words when 70%+ of its words are found, in order, in the
  "Others" segments within 5 s (`ECHO_SHARE`, `ECHO_GAP`, `ECHO_MIN_WORDS`). It sees one window at a time, so an echo
  whose original is in the previous window is not caught.

## Google accounts (DEV-0068 to DEV-0073, ADR-0009)
- `google.py`: `start_login(port)` builds the Google address (code flow, PKCE S256, random `state` kept 10 min in memory, `prompt=select_account consent`,
  scopes `openid email gmail.send calendar.events.readonly`); Google redirects to `http://127.0.0.1:<port>/oauth/google`, handled by `server._google_outcome`,
  which calls `finish_login` (state checked once, code traded at `oauth2.googleapis.com/token`, every permission required or the login is revoked,
  the address read from the `id_token` of that TLS reply) and answers with a 302 to `/?google=connected|denied|error#/settings` (no detail in the URL).
- Storage: `google-accounts.json` `{accounts: [{email, token}], send_from}`; each refresh token is protected with DPAPI (`CryptProtectData`, current
  user, UI forbidden) and base64'd; a damaged file is set aside as `.bad` before any change, an unreadable one blocks the change. Access tokens live only in
  memory (`access_token()`, refreshed 60 s before they expire). `invalid_grant` or an undecryptable login marks the account `needs_reconnect`.
- `api(email, url, params=, body=)` is the one way to call Google (Bearer token, one retry after a 401); `agenda.collect` and `mail.send` use it.
- Routes: `GET /api/google` `{configured, accounts: [{email, sender, needs_reconnect}]}`, `POST /api/google/login` `{url}`, `POST /api/google/sender` and
  `/api/google/disconnect` `{email}` -> `{accounts, revoked}`, `GET /oauth/google`.
- A refused request with a body (403/404/415) now drains that body first (`Handler._drain`): closing with unread data made Windows reset the connection
  and clients (and a flaky test) saw an error instead of the status.

## Consent and retention (DEV-0055 to DEV-0058)
- `POST /api/start` requires `consent: true` (`400` otherwise, checked after the other validations); `start(..., consented=True)` stamps
  `consent_at` in `meta.json`. A calendar reminder link no longer starts a recording by itself: it opens the record sheet with the
  token, so the confirmation is asked there too.
- The page's **Copy a recording notice** (sheet) and **Copy notice** (strip) write a fixed bilingual message to the clipboard.
- `AUDIO_KEEP_DAYS` (default 30, `0` = no audio kept: `_archive_audio` deletes the WAVs instead of compressing them) and
  `MEETING_KEEP_DAYS` (unset = keep) are read with `settings.days()`. `server._retention_loop` runs `store.expire_audio` and
  `store.expire_meetings` at start and every 6 hours; `expire_meetings` only touches meetings that have an `ended_at` and skips the
  one in the session.

## Sensitive data protection (DEV-0029)
- `privacy.Mask` is created per DeepSeek request. `apply()` swaps text for codes (`[TERM_n]`, `[EMAIL_n]`,
  `[LINK_n]`, `[AMOUNT_n]`, `[ID_n]`, `[SECRET_n]`) and `restore()` puts the originals back in the reply and
  summary. Patterns run first so a term inside an email hides the whole email; then listed terms (longest
  first, case and accent insensitive, whole words) and single-word fuzzy matches (`difflib`, ratio 0.8).
- Review hardening (DEV-0033): matching runs on a folded copy (NFKD, no accents, no invisible characters, positions
  mapped back), multi-word terms allow any separator or a transcript line prefix between words, every pattern repeat
  is bounded and overlap uses a byte map so a 300k-character transcript stays fast, text that already looks like a
  code is hidden too, terms need 3+ characters.
- Terms live in `sensitive-terms.txt` (git-ignored); `GET/PUT /api/privacy` with `{terms}`.
- `store.set_protected()` keeps the biggest count in `meta.protected`; the article shows it.
- The email to the user's own Gmail is not masked on purpose.

## Settings page (DEV-0026)
- `settings.py`: `FIELDS` (the six editable keys and whether each is secret), `validate()` (single line,
  no spaces in the secrets, a client ID ending in `.apps.googleusercontent.com`, day counts in range; error messages never
  contain the value), `status()` (`set` / `locked` / `value` only for the non-secret fields) and
  `write_env()` (replaces the file atomically through `.env.tmp`, keeps unrelated lines, drops duplicates).
- `server.save_config()` validates every field before writing once; a key set in the Windows environment
  is refused with `409`; saving the calendar address resets the watcher so it re-reads at once.

| Method and route | Body | Response |
|---|---|---|
| `GET /api/config` | — | `{NAME: {set, locked, value}}` (value only for the non-secret fields) |
| `PUT /api/config` | `{NAME: "value" \| null}` | same shape · `400` invalid · `409` locked |
| `POST /api/config/test-email` | — | `{}` · `409` with the reason if the email can't be sent |
