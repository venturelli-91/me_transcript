# Privacy

MeTranscript is a personal tool that runs on your own computer. This page says what it stores, what it sends
out, and what is your responsibility. The README has the same information in a shorter form.

## What it stores, and where

Everything lives in plain files in the project folder, on your computer:

| Where | What |
|---|---|
| `meetings/<date>/` | The audio (compressed, see below), the transcript, your notes, the summary, the chat and `meta.json` (title, language, times, and when you confirmed you had told the participants) |
| `.env` | Your keys (DeepSeek, Gmail app password, calendar address) in plain text |
| `sensitive-terms.txt` | The names you asked it to hide |

Nothing is uploaded anywhere automatically, and the app has no analytics or telemetry. The page it shows only talks
to `127.0.0.1`.

## What it sends out

| To | What | When |
|---|---|---|
| DeepSeek | The transcript, your notes and the chat, after contacts, amounts, IDs, keys and your protected terms are swapped for codes | Only when a summary is generated or you use the chat |
| Your own Gmail | The summary and the transcript, with real names | Only if you configured Gmail |
| Google Calendar | Your calendar is read through your secret iCal address | Only if you configured it |

Audio is never sent anywhere: it is transcribed on your computer. The protection mask has limits (it only hides
what matches its patterns or your list), so do not rely on it for secrets it cannot recognise.

## How long it keeps things

- Compressed audio is kept for **30 days** so you can re-transcribe, then deleted. In Settings → **Retention** you can
  change the number of days, or set it to **0** to delete the audio as soon as the transcript is ready.
- Whole meetings (notes, transcript, summary and chat) are kept until you delete them, unless you set
  **Delete whole meetings after (days)** in Settings. The check runs when the app starts and every six hours.
- You can delete one meeting at any time from its page. Deleting the project folder removes everything.

## Consent is your responsibility

MeTranscript has no bot and the other people on the call are not told by the program that they are being
recorded. Recording a conversation without the consent of the people in it is restricted or illegal in many places.

To help you remember, the app:

- asks you to confirm **"I told the participants that this meeting is being recorded"** before every recording,
  and keeps the time of that confirmation in the meeting's `meta.json`;
- gives you a **Copy a recording notice** button with a short bilingual message to paste into the meeting chat.

This is a reminder and a record, not legal protection: the checkbox only says that you did it. The rules differ
between countries and states, so check the ones that apply to you. This is not legal advice.

## Your data

Because everything is a file, you can open, copy, move or delete any of it yourself. To revoke access to the
optional integrations, delete the app password in your Google Account and reset the secret calendar address in
Google Calendar.
