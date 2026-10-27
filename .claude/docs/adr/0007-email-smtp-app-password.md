# ADR-0007: Summary by email via Gmail SMTP with an app password

**Date**: 2026-10-26
**Status**: superseded by [ADR-0009](0009-google-sign-in.md)
**Deciders**: CEO, Claude

## Context
The CEO wants to receive each meeting's summary in their own personal Gmail, automatically. Only
to themselves; Drive and other recipients are out of scope for now. The app is local, with no
server of its own and no account.

## Decision
`metranscript/mail.py` sends with `smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context())`
(stdlib; the explicit context is required because `smtplib`'s default doesn't verify the
server certificate — a security review finding), authenticating with
`GMAIL_ADDRESS` + `GMAIL_APP_PASSWORD` from `.env`. Sender and recipient are the same
address. Body = summary in Markdown (plain text); attachment = `transcript.md`. The automatic
send happens once per meeting (`emailed_at` in `meta.json`); resending only via the button.

## Alternatives Considered

### Gmail API with OAuth
- **Pros**: no app password; scope restricted to sending.
- **Cons**: Google Cloud project, consent screen, local OAuth flow, refresh token
  to store, Google dependencies.
- **Why not**: far more moving parts for a single recipient who is the user themselves.

### `mailto:` in the browser
- **Pros**: zero credentials.
- **Cons**: not automatic; URL length limit; no attachment.
- **Why not**: the CEO asked for automatic sending.

## Consequences
### Positive
- Zero new dependencies; turned on and off via `.env`.
- An email failure doesn't affect transcription or summary (orthogonal module, separate status).
### Negative
- An app password grants broad access to the Gmail account; it lives only in the local `.env`.
- Summary and transcript also end up in Gmail (Google).
### Risks
- Google disabling app passwords for personal accounts: migrate to the Gmail API (OAuth).
- Leaked password: revoke it in Google Account → Security → App passwords.
