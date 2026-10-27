# Project

## Why
The CEO takes meeting notes every day and wanted a tool of their own: personal, no account, no bot in the call, and no
third-party dependency other than the LLM.

## User
One person: the CEO, on their own Windows desktop, usually wearing headphones (speakers also work), in Google Meet,
Zoom and Microsoft Teams meetings, in Portuguese or English.

## What it is
A local program (Python) with a single browser page (`127.0.0.1:8765`):

1. It alerts you when a meeting app starts using the microphone — or you start it with the button.
2. It records two tracks: **Me** (microphone) and **Others** (system audio).
3. When you stop, it transcribes the audio locally, once, with whisper.cpp (nothing runs during the call).
4. You write short notes while you talk.
5. Then DeepSeek writes a complete summary of the **ideas by topic**, the decisions and the next steps.
6. You chat with the meeting: ask something specific (the answer cites the timestamp of the passage),
   ask it to add something to the summary or to rephrase it — and you can undo. You can also ask it to explain what you do not
   understand, point out risks, suggest solutions and give its opinion on the processes.

## Goals
- Be the CEO's daily tool for meeting notes in Meet, Zoom and Teams.
- Recurring cost: only the DeepSeek API.
- Everything stored locally, in Markdown readable outside the app.

## Non-goals (for now)
Cross-meeting search, multiple templates, calendar, sharing, cloud sync,
per-participant identification, live word-by-word transcription, login,
installer.

## Anti-goals (failure even if it works)
- Paying for any service other than DeepSeek.
- Becoming a heavy project (Electron, web framework, database).
- Joining the meeting as a bot.
- Copying another product — name, design and flow are our own.
- Recording without the user telling it to.
