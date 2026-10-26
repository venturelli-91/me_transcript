import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage

from ata.settings import env

HOST, PORT = "smtp.gmail.com", 465


def configured() -> bool:
    return bool(env("GMAIL_ADDRESS") and env("GMAIL_APP_PASSWORD"))


def build(meeting: dict, address: str) -> EmailMessage:
    title = " ".join((meeting["title"] or "Reunião sem título").split())
    when = datetime.fromisoformat(meeting["started_at"]).strftime("%d/%m %H:%M")
    msg = EmailMessage()
    msg["Subject"] = f"Ata: {title} ({when})"
    msg["From"] = msg["To"] = address
    msg.set_content(meeting["ata"])
    msg.add_attachment(meeting["transcript"].encode("utf-8"), maintype="text", subtype="markdown",
                       filename="transcricao.md")
    return msg


def send(meeting: dict) -> None:
    address, password = env("GMAIL_ADDRESS"), env("GMAIL_APP_PASSWORD")
    if not (address and password):
        raise RuntimeError("E-mail não configurado: preencha GMAIL_ADDRESS e GMAIL_APP_PASSWORD no .env.")
    try:
        # smtplib's default context skips certificate checks; without this the app password could go to an impostor.
        with smtplib.SMTP_SSL(HOST, PORT, timeout=30, context=ssl.create_default_context()) as smtp:
            smtp.login(address, password)
            smtp.send_message(build(meeting, address))
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError("O Gmail recusou o login: confira GMAIL_ADDRESS e a senha de app.") from None
    except (smtplib.SMTPException, OSError):
        raise RuntimeError("Sem conexão com o Gmail. Verifique a internet e envie de novo.") from None
