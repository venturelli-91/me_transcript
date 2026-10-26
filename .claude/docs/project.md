# Project

## Why
The CEO uses another note-taking app daily to take meeting notes. another note-taking app only accepts corporate
email addresses, and the block is enforced on their server — there is no way around it. The solution is
a tool of our own: personal, no account, and no third-party dependency other than the LLM.

## User
One person: the CEO, on their own Windows desktop, always wearing headphones, in Google Meet,
Zoom and Microsoft Teams meetings, in Portuguese or English.

## What it is
A local program (Python) with a single browser page (`127.0.0.1:8765`):

1. It alerts you when a meeting app starts using the microphone — or you start it with the button.
2. It records two tracks: **Me** (microphone) and **Others** (system audio).
3. It transcribes in chunks during the meeting, locally, with whisper.cpp.
4. You write short notes while you talk.
5. When you stop, DeepSeek summarizes the **ideas by topic** and the next steps.
6. You chat with the meeting: ask something specific (the answer cites the timestamp of the passage),
   ask it to add something to the summary or to rephrase it — and you can undo.

## Goals
- Replace another note-taking app in the CEO's daily use for Meet, Zoom and Teams.
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
- Being a another note-taking app clone — name, design and flow are our own.
- Recording without the user telling it to.
