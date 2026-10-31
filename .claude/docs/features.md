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
- [ ] Update (DEV-0032): instead of deleting, the WAVs are compressed to `mic.opus` / `system.opus`
      (24 kbit/s) and expire after 30 days; a failed compression keeps the WAV.

## F2 — Record and stop
- [ ] The **Record** button starts capture; the **Stop** button ends it. There is no auto-stop.
- [ ] Optional title and language (`pt` default, `en`) chosen before recording.
- [ ] Elapsed time and audio level indicators for both tracks while recording.
- [ ] Only one recording at a time; trying to start another returns a clear error.
- [ ] After stopping, the next meeting can be recorded right away: the previous one is transcribed and
      summarized in the background (one transcription at a time, the rest wait as "queued"), with its
      progress shown on its page and in the index.
- [ ] (DEV-0094) While you record another meeting, a background meeting that finishes (or fails) shows a silent
      Windows notification; clicking it opens that meeting.
- [ ] (DEV-0095) If the app closed while a meeting was being transcribed, it is queued again on the next start.
- [ ] (DEV-0096, DEV-0097) A meeting waiting in the queue has **Transcribe next** (moves it to the front) and
      **Cancel transcription** (takes it out; the audio is kept and **Re-transcribe** still works).
- [ ] (DEV-0098) Under 5 GB of free disk space, the status line warns and points to **Keep audio for (days)**.

## F3 — Two audio tracks
- [ ] `mic.wav` contains only the microphone; `system.wav` contains only system audio
      (loopback of the default output device).
- [ ] Works with Meet (browser), Zoom and Teams with no per-app configuration.

## F4 — Local transcription
- [ ] (DEV-0059) Nothing is transcribed while recording. On stop, each track is transcribed once by whisper.cpp in the chosen
      language, with a progress percentage in the strip and on the meeting page, before the summary.
- [ ] Segments labeled **Me** / **Others**, interleaved by time, are saved to `transcript.md` as each window finishes.
- [ ] (DEV-0058) A window whisper cannot do (a crash, unreadable output) is skipped, logged and marked in the transcript with
      `[this part could not be transcribed]`, so the summary says that part is missing; the others still finish.
      Decoding loops ("e aí e aí e aí") are collapsed to one occurrence.
- [ ] Silent stretches don't produce made-up text ("Subtitles by the community…").
- [ ] (DEV-0031) A window ends in the latest pause of both speakers (at least 0.5 s, after 12 s) instead
      of every 30 s sharp, so words aren't cut.
- [ ] (DEV-0031) Whisper gets a sentence with the protected terms and the end of the previous window
      of the same speaker, so names are spelled consistently.
- [ ] (DEV-0041, DEV-0043) A "Me" line of 4+ words whose words are 70%+ found in the "Others" lines within 5 s is
      dropped as speaker echo, also when the echo is split into fragments; short lines are kept.
- [ ] (DEV-0032) **Re-transcribe** on a meeting with saved audio redoes the transcript (the old one is
      kept as `transcript.previous.md`) and rewrites the summary.

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
- [ ] (DEV-0066) Explain / assess / advise: the chat explains terms, acronyms and processes, points out risks, proposes solutions and gives an
      opinion using the AI's own knowledge. It says first what the meeting said (with timestamps) and then its own part under **My opinion:**
      / **Minha opinião:**, never presents its inference as said by the participants, offers a guess when a term is ambiguous, and does not
      change the summary unless asked. A factual question is still answered only from the transcript.
- [ ] (DEV-0066) Four buttons above the message box (Explain, Risks, Suggestions, Your opinion) send these requests; they follow the language switch.
- [ ] Each chat answer has "Add to summary".
- [ ] "Undo" reverts the summary to the previous version (all versions are kept).
- [ ] Chat saved to `chat.json`; when the meeting is reopened, the conversation continues.
- [ ] No key or network error: clear message, transcript and chat preserved.

## F7 — Meeting alert
- [ ] With the page open, when Zoom, Teams or a browser starts using the microphone,
      a banner appears (plus a system notification, if allowed) with **Record**.
- [ ] Never starts recording on its own.
- [ ] Doesn't repeat the alert for the same microphone session.
- [ ] (DEV-0040, DEV-0042) A browser only raises the alert when one of its own windows has a meeting word
      (whole word) in the title; the words come from `MEETING_KEYWORDS` (default Meet, Zoom, Teams), editable in Settings.
      Zoom and Teams don't need a title.

## F8 — Summary by email (Gmail)
CEO decision (2026-10-26): receive the summary in their own personal Gmail, automatically. Since DEV-0068 to DEV-0073 it is sent through the
Gmail API from a Google account connected with "Sign in with Google" (no app password).

- [ ] When a meeting's first summary is ready, it is sent from the chosen Google account
      to itself: subject "MeTranscript: <title> (yyyy-mm-dd HH:MM)", body = summary, no attachment (the transcript is not shown anywhere).
- [ ] Sent once per meeting; "Regenerate" and chat edits don't resend.
- [ ] A "Email it to me" button sends the current version whenever the user wants.
- [ ] A meeting flagged private by an older version is never sent.
- [ ] A send failure shows "Email not sent: reason" and doesn't affect the summary.
- [ ] With no connected account, the feature is off.

## F9 — Calendar reminders
CEO decision (2026-10-26): reminders before meetings, read from Google Calendar. Since DEV-0070 the events come from the Google Calendar API,
for every account connected with "Sign in with Google" (primary calendars, merged).

- [ ] 30 minutes before a calendar event that has a Meet, Zoom or Teams link, a Windows notification
      shows the title, time and app. A late start still gets it ("In 15 min").
- [ ] 2 minutes before, a second notification with a **Record** button that opens MeTranscript and
      starts recording with the event title.
- [ ] Ignores events without a meeting link, all-day events, declined events and past events.
- [ ] Each reminder fires once per occurrence, even across restarts.
- [ ] "Upcoming meetings" in the sidebar lists the next linked meetings (24 h) of all connected accounts, merged by time; with two or more
      accounts each row shows which account it comes from.
- [ ] "Run in background and start with Windows" toggle and a "Quit MeTranscript" button on the page.
- [ ] With no connected account, reminders are off with a hint in the sidebar; an account whose login Google no longer accepts shows an error there
      and "Sign in again" in Settings.

## F10 — Choose audio devices
CEO decision (2026-10-26): after a recording silently used the webcam microphone (Windows switched
the default when the headset connection dropped), the user can pick devices. Nothing is remembered.

- [ ] Recorder shows **Microphone** and **Speakers / headphones** selects with the current WASAPI
      devices; the Windows default is marked "(default)" and preselected every time.
- [ ] "Refresh devices" re-reads the list.
- [ ] Devices can be switched **during** a recording without stopping it; the track keeps one clock
      (the gap is padded with silence) and the transcript continues as "Me"/"Others".
- [ ] A device with a different sample rate than the running recording is refused with a clear message.
- [ ] If a device stops delivering audio mid-recording, the status line asks to pick another one.

## F11 — Index / Meeting / Recording UI
- [ ] (DEV-0037) Dark theme via a **Dark / Light** button in the top bar, saved in `localStorage`, applied before first paint. Tokens live in `:root[data-theme="dark"]`; `--btn`/`--on-btn` invert for buttons and the user chat bubble, while `--dark` (record strip, detected banner) stays a dark surface. While recording, the same button sits in the recording strip, so it never disappears.
CEO decision (2026-10-26): ArchiPro-inspired navigation and palette with a proportional type scale;
direction "E · Index" chosen among five mockups. Full design:
[specs/2026-10-26-ui-redesign-design.md](specs/2026-10-26-ui-redesign-design.md).

- [ ] Index: numbered list (oldest = 01, newest first), filters All / This week / With next steps.
- [ ] Record sheet: title, language, devices (defaults preselected).
- [ ] Recording strip pinned on every page: clock, stop, devices + levels, Back to recording.
- [ ] Meeting article: (01) Summary, (02) Next steps (split from the summary), (03) Notes. The transcript is not shown (DEV-0065).
- [ ] Chat drawer: default 380 px, drag 320 px – min(50vw, 640 px), double-click resets, ←/→ keys,
      width remembered per browser; `[hh:mm:ss]` timestamps in the answers are plain text (they point at the recording).
- [ ] Works at 400 px (drawer stacks under the article), WCAG AA contrast, keyboard access.

## F11b — Look and language (DEV-0047, DEV-0048)
- [ ] Square-ish controls (4 px) and 6 px cards; only the Record button is round; filters are underlined tabs.
- [ ] Timecodes, dates and meeting numbers use JetBrains Mono (served locally); the meeting page opens with its number as a large numeral.
- [ ] (DEV-0050) While recording: red top edge, a pulsing dot (still under reduced motion), a 40 px clock, tick-style level meters
      per track and the tab title `● mm:ss MeTranscript`.
- [ ] (DEV-0057) A footer on every page shows the MIT license line with a link to `LICENSE`, and the LinkedIn, WhatsApp and
      Gmail logos in their brand colors (Simple Icons, CC0) plus a globe for the portfolio, as inline SVG with no external request until clicked;
      labels follow the language switch.
- [ ] (DEV-0059, DEV-0065) While recording, the page shows the notes and a quiet note that the transcript is made after you stop; the
      meeting page does not show the transcript at all (it stays in `transcript.md` for the summary, the chat and the email attachment).
- [ ] An **EN | PT-BR** switch in the top bar and the recording strip changes every page text without a reload; the choice
      is kept in the browser (first visit follows the browser language); dates follow the chosen language.

## F15 — Consent reminder and retention (DEV-0055 to DEV-0058)
- [ ] The record sheet has an unchecked **I told the participants that this meeting is being recorded** box that must be checked to
      start; the server refuses `/api/start` without `consent: true`; the time is kept as `consent_at` in `meta.json`.
- [ ] **Copy a recording notice** (sheet) and **Copy notice** (recording strip) copy a short English + Portuguese message.
- [ ] A calendar reminder's Record button opens the record sheet (with the consent box) instead of starting at once.
- [ ] Settings → Retention: audio days (0-3650, `0` keeps no audio) and, optionally, delete whole meetings after N days; a finished
      meeting older than that is removed at start and every 6 hours; a meeting being recorded is never removed.
- [ ] `PRIVACY.md` explains what is stored, what is sent, how long it is kept and that consent is the user's responsibility.

## F17 — A fuller, more accurate summary (DEV-0061)
- [ ] The summary has an Overview, one section per topic (3-8 full-sentence bullets with context, positions, numbers and outcome), Open questions,
      Decisions and, always last, Next steps (the page splits on that heading).
- [ ] Names and acronyms follow the notes and the form the context makes most plausible ("GCP" for "IGCP"); nothing is expanded or guessed unless the speakers said it; a doubtful word is
      kept and marked "(?)"; repeated or garbled fragments are ignored.
- [ ] The summary request uses temperature 0.2 and up to 8000 output tokens; the chat prompt has the same accuracy rules.

## F12 — Rename and delete a meeting
From the ponytail audit (2026-10-26): the only way to remove a meeting was deleting its folder by hand.

- [ ] **Rename** on the article swaps the title for an input: Enter saves, Esc cancels, blur saves; the
      title is trimmed, whitespace collapsed, capped at 200 characters; the Index shows it.
- [ ] **Delete** opens a confirmation ("…will be removed from this computer. This can't be undone.");
      the focus starts on Cancel; confirming removes the whole meeting folder and returns to the Index.
- [ ] A meeting that is being recorded, transcribed or summarized cannot be deleted (the button is
      disabled and the API answers `409`).
- [ ] Deleting an older meeting renumbers the ones after it in the Index (numbers are by age).

## F13 — Settings page for the keys
Follow-up from the ponytail audit (2026-10-26): pasting keys into a file by hand was the main friction.

- [ ] `#/settings` (top bar) lists the DeepSeek key, the Google client ID and secret with the connected Google accounts (DEV-0073), the meeting-alert
      words, the retention days and the protected terms, plus the background-mode toggle and Quit.
- [ ] Secrets are never sent back: each shows "Saved" / "Not set"; the Google client ID is shown in full.
- [ ] Save writes only the filled fields to `.env`, keeps every other line, and applies without restart
      (the calendars are re-read right away after a Google change).
- [ ] **Remove** deletes a key; invalid values are rejected with a clear message (single line, a client ID ending in
      `.apps.googleusercontent.com`, no spaces in the secrets) and nothing is written. The old `GMAIL_*` and `GOOGLE_CALENDAR_ICS` keys are unknown now.
- [ ] A key set as a Windows environment variable is shown as locked.
- [ ] (DEV-0040) The browser window words (`MEETING_KEYWORDS`) are a fifth, non-secret field; an empty or
      separators-only value falls back to the defaults.
- [ ] **Send a test email** sends one message from the chosen Google account to itself.

## F18 — Google accounts (DEV-0068 to DEV-0073)
- [ ] **Sign in with Google** (Settings -> Google accounts) opens Google's consent page (OAuth code flow with PKCE, redirect to the app's own
      `/oauth/google`) and, on return, lists the account; it needs the Google Cloud client ID and secret first.
- [ ] Several accounts can be connected; one is marked as the sender of the summaries (the first by default); **Disconnect** removes the account and
      asks Google to cancel its login (the page says when Google did not confirm).
- [ ] Logins are stored in `google-accounts.json`, encrypted with Windows DPAPI; the page and `/api/*` never receive a token or the client secret.
- [ ] A refused or partial consent (not every permission ticked), a stale or replayed sign-in link and a login Google no longer accepts end in a short,
      clear message and save nothing (or mark the account "Sign in again").

## F19 — About and privacy pages (DEV-0078 to DEV-0080)
- [ ] **About** (top bar and footer, `#/about`) explains the app in plain words, with screenshots of fictional meetings in the page language, what leaves the computer, the consent reminder and a **Get started** button.
- [ ] **Get started** opens Settings with a short notice when the DeepSeek key is not set; otherwise it opens the record sheet.
- [ ] **Privacy** (footer, `#/privacy`) shows the full policy (`PRIVACY.md`, or `PRIVACY.pt.md` in Portuguese); the empty Index links to About.

## F20 — Pin a meeting and clear its chat (DEV-0083)
- [ ] **Pin to top** (meeting page) keeps a meeting first in the Index with a "Pinned" mark; **Unpin** restores date order. Meeting numbers do not change.
- [ ] **Clear chat** (chat drawer, two clicks to confirm) deletes only the conversation with the AI; notes, summary and transcript stay.

## F21 — Download the report (DEV-0084)
- [ ] **Download** (meeting page, next to the summary actions) offers **PDF** or **Markdown (.md)**: title, date, duration, app and the summary (with its next steps). The transcript and the chat are not included.
- [ ] The PDF is printed by the Microsoft Edge or Google Chrome already on Windows (`GET /api/meetings/<id>/report.pdf`); without one, the page says to download the Markdown (`report.md`) instead. A meeting without a summary has the button disabled.

## F22 — Archive and reopen meetings (DEV-0085)
- [ ] **Archive** (meeting page) takes a meeting out of All, This week and With next steps and counts it out of the Index total; the **Archived** filter lists archived meetings and **Unarchive** brings one back. Nothing is deleted and the numbers do not change.

## F23 — Shorter chat answers and a times switch (DEV-0087)
- [ ] The chat answers briefly, in plain paragraphs without section headings or bullet lists, and goes deeper only when asked; **My opinion** stays a separate paragraph.
- [ ] **Hide times** / **Show times** (chat header) removes the `[hh:mm:ss]` citations from the answers on screen; the stored chat keeps them and the choice is remembered in the browser.
