import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage

from ata.settings import env

HOST, PORT = "smtp.gmail.com", 465


def configured() -> bool:
    return bool(env("GMAIL_ADDRESS") and env("GMAIL_APP_PASSWORD"))


def build(meeting: dict, address: str) -> EmailMessage:
    title = " ".join((meeting["title"] or "Untitled meeting").split())
    when = datetime.fromisoformat(meeting["started_at"]).strftime("%Y-%m-%d %H:%M")
    msg = EmailMessage()
    msg["Subject"] = f"Ata: {title} ({when})"
    msg["From"] = msg["To"] = address
    msg.set_content(meeting["summary"])
    msg.add_attachment(meeting["transcript"].encode("utf-8"), maintype="text", subtype="markdown",
                       filename="transcript.md")
    return msg


def send(meeting: dict) -> None:
    address, password = env("GMAIL_ADDRESS"), env("GMAIL_APP_PASSWORD")
    if not (address and password):
        raise RuntimeError("Email not configured: set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env.")
    try:
        # smtplib's default context skips certificate checks; without this the app password could go to an impostor.
        with smtplib.SMTP_SSL(HOST, PORT, timeout=30, context=ssl.create_default_context()) as smtp:
            smtp.login(address, password)
            smtp.send_message(build(meeting, address))
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError("Gmail rejected the login: check GMAIL_ADDRESS and the app password.") from None
    except (smtplib.SMTPException, OSError):
        raise RuntimeError("Cannot reach Gmail. Check your connection and send again.") from None
