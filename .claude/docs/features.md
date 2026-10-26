# Features

## F1 — Meetings as folders
Each meeting is a folder `meetings/YYYY-MM-DD_HHMM/` with `meta.json`, `notes.md`,
`transcript.md`, `summary.md`, `mic.wav`, `system.wav`.

- [ ] Creating a meeting creates the folder and `meta.json` (`title`, `lang`, `started_at`).
- [ ] Meetings are listed in descending date order.
- [ ] Opening an old meeting shows notes, transcript and summary.
- [ ] Two meetings in the same minute don't collide (`-2` suffix).
- [ ] CEO decision (2026-10-26): `mic.wav` and `system.wav` are deleted as soon as transcription
      finishes successfully; the record is `transcript.md`. If transcription fails, the audio is kept.

## F2 — Record and stop
- [ ] The **Record** button starts capture; the **Stop** button ends it. There is no auto-stop.
- [ ] Optional title and language (`pt` default, `en`) chosen before recording.
- [ ] Elapsed time and audio level indicators for both tracks while recording.
- [ ] Only one recording at a time; trying to start another returns a clear error.

## F3 — Two audio tracks
- [ ] `mic.wav` contains only the microphone; `system.wav` contains only system audio
      (loopback of the default output device).
- [ ] Works with Meet (browser), Zoom and Teams with no per-app configuration.

## F4 — Local transcription
- [ ] Every ~30 s, each track's new audio is transcribed by whisper.cpp in the chosen language.
- [ ] Segments labeled **Me** / **Others**, interleaved by time, appear on the page
      during the meeting.
- [ ] On stop, the remaining chunks are transcribed before the summary.
- [ ] Silent stretches don't produce made-up text ("Subtitles by the community…").

## F5 — Notes
- [ ] Free-text area during and after the meeting, saved automatically to
      `notes.md` (no save button).
- [ ] A subtle "saved" indicator.

## F6 — Summary and chat with the meeting (DeepSeek)
CEO decision (2026-10-26): the app summarizes the ideas by topic and the user chats with
it to ask, quote or rephrase — instead of meeting notes with fixed sections.

- [ ] When transcription finishes, it generates `summary.md`: one `##` per topic discussed, with the ideas,
      numbers and who argued for what, and at the end "Next steps" (owner: task, deadline).
- [ ] Notes are optional; when present, their points get more space.
- [ ] Written in the meeting's language.
- [ ] Message box per meeting: a specific question gets a short answer with the
      `[hh:mm:ss]` timestamp of the passages; a change request rewrites the summary and says what changed.
- [ ] Each chat answer has "Add to summary".
- [ ] "Undo" reverts the summary to the previous version (all versions are kept).
- [ ] Chat saved to `chat.json`; when the meeting is reopened, the conversation continues.
- [ ] No key or network error: clear message, transcript and chat preserved.

## F7 — Meeting alert
- [ ] With the page open, when Zoom, Teams or a browser starts using the microphone,
      a banner appears (plus a system notification, if allowed) with **Record**.
- [ ] Never starts recording on its own.
- [ ] Doesn't repeat the alert for the same microphone session.

## F8 — Summary by email (Gmail)
CEO decision (2026-10-26): receive the summary in their own personal Gmail, automatically.

- [ ] When a meeting's first summary is ready, it is sent from the user's Gmail
      to themselves: subject "MeTranscript: <title> (dd/mm HH:MM)", body = summary, attachment `transcript.md`.
- [ ] Sent once per meeting; "Regenerate" and chat edits don't resend.
- [ ] A "Email it to me" button sends the current version whenever the user wants.
- [ ] A private meeting is never sent.
- [ ] A send failure shows "Email not sent: reason" and doesn't affect the summary.
- [ ] Without `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD` in `.env`, the feature is off with a subtle notice.
