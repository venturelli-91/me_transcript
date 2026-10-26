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
