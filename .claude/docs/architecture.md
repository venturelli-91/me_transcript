# Architecture

## Overview

```
 browser (web/index.html)
      │  polling /api/status (1 s), fetch JSON
      ▼
 server.py ──── store.py ──── meetings/<id>/  (files)
      │
      ├── capture.py    PyAudioWPatch: mic + loopback  → mic.wav, system.wav
      ├── transcribe.py thread: 30 s chunks → ffmpeg → whisper-cli → segments
      ├── enhance.py    urllib → DeepSeek → summary (summary.md) and chat (chat.json)
      ├── detect.py     winreg ConsentStore → meeting app using the mic?
      └── mail.py       smtplib (Gmail, app password) → summary to your own email
```

One Python process, no framework. `server.py` is the only module that knows all the
others; the rest don't import each other (except `transcribe` reading the WAVs that
`capture` writes, via file path).

## Modules

| Module | Responsibility | Depends on |
|---|---|---|
| `store.py` | Create/list/read/save a meeting; `transcript.md` format | stdlib |
| `capture.py` | Open mic and loopback, record native WAV, expose audio level | PyAudioWPatch |
| `transcribe.py` | Read new chunks from the WAVs, convert, transcribe, interleave Me/Others | ffmpeg, whisper-cli |
| `enhance.py` | Build messages with `prompt.md` and call DeepSeek | stdlib (`urllib`) |
| `detect.py` | Read the registry and report which meeting app has the mic open | stdlib (`winreg`) |
| `server.py` | HTTP, recording session state, orchestration | all of the above |

## Session state
A single `Session` object in `server.py`, guarded by a `threading.Lock`:
`phase` ∈ `idle | recording | transcribing | enhancing | done | error`, `meeting_id`,
`started_at`, `segments`, `levels`, `error`.

ponytail: one global session — the app is for one person, one meeting at a time.

## Meeting flow
1. `POST /api/start` → `store.create()` → `capture.start()` → `transcribe` starts its thread.
2. Every 30 s, the transcription thread takes the new stretch of each WAV
   (`ffmpeg -ss/-t` → 16 kHz mono) and runs it through Silero VAD (`whisper-vad-speech-segments`); with ≥ 0.5 s of speech, it runs
   `whisper-cli -l <lang> -ot <speech start> -oj` on the window (GPU via Vulkan), at Windows
   low priority. Segments with
   absolute timestamps go to `Session.segments` and to `transcript.md`.
3. `POST /api/stop` → `capture.stop()` → transcribe the rest → `phase = enhancing` →
   `enhance.summarize()` → `summary.md` → `phase = done`. A transcription or summary failure →
   `phase = error` with a message; nothing saved is deleted. A private meeting skips the summary.
4. In an open meeting, each chat message calls `enhance.chat()` (JSON mode): the answer goes
   to `chat.json`; if it includes `summary`, the previous version goes to `summary-history.json` and the new
   text to `summary.md`. "Undo" restores the latest version from the history.

## API contract (JSON, 127.0.0.1 only)

| Method and route | Body | Response |
|---|---|---|
| `GET /` | — | `web/index.html` |
| `GET /api/status` | — | `{phase, meeting_id, elapsed, levels:{mic,system}, segments:[...], detected, error}` |
| `GET /api/meetings` | — | `[{id, title, started_at, has_summary}]` |
| `GET /api/meetings/<id>` | — | `{id, title, lang, private, started_at, ended_at, notes, transcript, summary, chat, can_undo}` |
| `POST /api/start` | `{title?, lang: "pt"\|"en", private?: bool}` | `{id}` · `409` if already recording |
| `POST /api/stop` | — | `{}` (processing continues in the background) |
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
- `meta.json`: `{"title", "lang", "private", "started_at", "ended_at", "emailed_at"?, "email_error"?}`
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
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | — (optional; enable sending the summary by email) |

`metranscript/settings.py` (`env()`) reads variables from the environment and, if missing, from `.env`.

## Calendar reminders and background mode (DEV-0013)
- `agenda.py`: fetches the secret iCal address(es) every 5 min, expands recurrences
  (`recurring-ical-events`), keeps linked/timed/accepted future events (`upcoming()`), and decides
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
| `GET /api/agenda` | — | `{configured, events: [{key, title, start, app, link}], error}` |
| `GET /api/settings` | — | `{autostart}` |
| `POST /api/settings` | `{autostart: bool}` | `{autostart}` |
| `POST /api/quit` | — | `{}` · `409` while recording or processing |

| Variable | Default |
|---|---|
| `GOOGLE_CALENDAR_ICS` | — (secret iCal address; comma-separated for several calendars) |

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
  Opus files older than 30 days at start. `POST /api/meetings/<id>/retranscribe` decodes the saved audio,
  replaces the transcript (`transcript.previous.md` keeps the old one) and rewrites the summary; `409` if busy
  or there is no audio.

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
- `settings.py`: `FIELDS` (the four editable keys and whether each is secret), `validate()` (single line,
  no spaces in the DeepSeek key, a full email address, `https://` calendar addresses; error messages never
  contain the value), `status()` (`set` / `locked` / `value` only for the non-secret Gmail address) and
  `write_env()` (replaces the file atomically through `.env.tmp`, keeps unrelated lines, drops duplicates).
- `server.save_config()` validates every field before writing once; a key set in the Windows environment
  is refused with `409`; saving the calendar address resets the watcher so it re-reads at once.

| Method and route | Body | Response |
|---|---|---|
| `GET /api/config` | — | `{NAME: {set, locked, value}}` (value only for `GMAIL_ADDRESS`) |
| `PUT /api/config` | `{NAME: "value" \| null}` | same shape · `400` invalid · `409` locked |
| `POST /api/config/test-email` | — | `{}` · `409` with the reason if the email can't be sent |
