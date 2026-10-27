import base64
from datetime import datetime
from email.message import EmailMessage

from metranscript import google

SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def configured() -> bool:
    return google.send_account() is not None


def build(meeting: dict, address: str) -> EmailMessage:
    title = " ".join((meeting["title"] or "Untitled meeting").split())
    when = datetime.fromisoformat(meeting["started_at"]).strftime("%Y-%m-%d %H:%M")
    msg = EmailMessage()
    msg["Subject"] = f"MeTranscript: {title} ({when})"
    msg["From"] = msg["To"] = address
    msg.set_content(meeting["summary"])
    return msg


def send(meeting: dict) -> None:
    """Email the summary to the user's own address, from the Google account chosen in Settings."""
    address = google.send_account()
    if not address:
        raise RuntimeError("Email not configured: sign in with Google in Settings.")
    raw = base64.urlsafe_b64encode(build(meeting, address).as_bytes()).decode()
    try:
        google.api(address, SEND_URL, body={"raw": raw})
    except google.ReconnectNeeded as e:
        raise RuntimeError(str(e)) from None
    except google.GoogleError as e:
        if e.status in (401, 403):
            raise RuntimeError(f"Gmail refused to send from {address}. Sign in again in Settings and allow sending email.") from None
        raise RuntimeError(f"Gmail could not send the message ({e.status}). Try again.") from None
