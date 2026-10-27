# ADR-0009: Google sign-in (OAuth + PKCE) for the summary email and the calendars

**Date**: 2026-10-27
**Status**: accepted
**Deciders**: CEO, Claude

## Context
Sending the summary needed a Gmail app password and the reminders needed a secret iCal address per calendar, all pasted by hand into `.env`
or Settings. The CEO wanted to authenticate inside the app and to merge the agendas of several personal Google accounts. The app is local,
Windows-only, stdlib-only and may be downloaded by others.

## Decision
- "Sign in with Google" using the OAuth 2.0 authorization code flow with PKCE. The app's own server is the loopback redirect
  (`http://127.0.0.1:<port>/oauth/google`) of a **Desktop-app client that each user creates once in their own Google Cloud project** (client ID and
  secret pasted in Settings). Scopes: `openid email`, `gmail.send`, `calendar.events.readonly`.
- Calendars: the Calendar API (`events.list`, primary calendar) for every connected account, merged. Email: the Gmail API, from the account chosen as
  sender, to itself; no attachment.
- Logins (refresh tokens) in `google-accounts.json` encrypted with Windows DPAPI; access tokens only in memory.
- All calls with `urllib` (no new dependency); `icalendar` and `recurring-ical-events` are removed.

## Alternatives considered
- **Keep the app password and the iCal address**: simplest, but it is the friction the CEO wants gone, and it needs one secret per account.
- **A Google client shipped in the repo**: no setup for users, but the sensitive scopes would need Google's verification (a long process) and the
  secret would be public; every download would share one quota.
- **A Google client library (`google-auth`, `google-api-python-client`)**: less code of our own, but a large dependency tree for a few calls.

## Consequences
### Positive
- One click per account, several accounts, least privilege (send only, read-only calendar), revocable from the app and from the Google Account.
### Negative
- A one-time Google Cloud setup. An unverified app is capped at 100 accounts and shows Google's warning; in "Testing" mode the login expires after 7 days
  (the README says to publish the app).
- Our own small OAuth code to maintain (reviewed for state/PKCE, token handling and error messages).
### Risks
- Any program running as the same Windows user can decrypt the stored logins (DPAPI's model). Windows only.
