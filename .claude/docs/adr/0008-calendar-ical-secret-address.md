# ADR-0008: Calendar reminders from the Google Calendar secret iCal address

**Date**: 2026-10-26
**Status**: accepted
**Deciders**: CEO, Claude

## Context
The CEO wants a reminder 30 minutes and 2 minutes before each meeting that has a video link
(Meet, Zoom, Teams), with a way to start recording from the 2-minute one. The app is local, has no
account and no server of its own, and until now only ran while the user had it open.

## Decision
- Read the calendar from its **secret address in iCal format** (`GOOGLE_CALENDAR_ICS` in `.env`,
  comma-separated for several calendars), fetched with `urllib` every 5 minutes.
- Expand recurring events with `icalendar` + `recurring-ical-events` (free); keep only timed events
  with a meeting link that the user did not decline (attendee matching `GMAIL_ADDRESS`).
- Show native Windows notifications through a **constant** PowerShell script that loads toast XML from
  an environment variable (text XML-escaped in Python). `winotify` was tried and dropped: it formats
  titles into an expandable PowerShell here-string, so an invite titled `$(...)` would run code.
  The 2-minute one has a "Record" button that
  opens the page with a one-time token, so a link from elsewhere can't start a recording.
- Optional background mode: a `HKCU\...\Run` value launching `pythonw.exe start.pyw`, toggled from
  the page, plus a "Quit MeTranscript" button. No tray icon.

## Alternatives Considered

### Google Calendar API with OAuth
- **Pros**: precise, instant updates; standard scopes.
- **Cons**: Google Cloud project, consent screen, local OAuth flow, token storage, Google client libraries.
- **Why not**: far more moving parts for a read-only personal feed.

### Parse iCal by hand
- **Pros**: no dependency.
- **Cons**: recurrence rules, exceptions and time zones are where hand-written parsers break.
- **Why not**: weekly meetings are the common case; a free, focused library is the safer call.

### Tray icon (`pystray`)
- **Pros**: familiar "quit" affordance.
- **Cons**: two more dependencies (`pystray`, Pillow) and an extra UI surface.
- **Why not**: the page already hosts the toggle and the quit button.

## Consequences
### Positive
- No login flow; disabling is deleting one line from `.env`.
- Nothing from the calendar leaves the machine.
### Negative
- Calendar changes show up within ~5 minutes, not instantly.
- The secret address grants read access to the whole calendar; it lives only in `.env`.
- Reminders only fire while MeTranscript is running.
### Risks
- Secret address leaked: reset it in Google Calendar settings ("Reset" next to the secret address).
