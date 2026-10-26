import os
import smtplib
import ssl
import unittest
from unittest import mock

from ata import mail

MEETING = {"title": "Kickoff\nBcc: x@evil.com", "started_at": "2026-10-26T14:30:00",
           "ata": "## Prazo\n- sexta", "transcript": "[00:00:01] **Outros:** Oi.\n"}
CREDS = {"GMAIL_ADDRESS": "eu@gmail.com", "GMAIL_APP_PASSWORD": "abcd efgh ijkl mnop"}


class MailTest(unittest.TestCase):
    def test_build_message(self):
        msg = mail.build(MEETING, "eu@gmail.com")
        self.assertEqual(msg["Subject"], "Ata: Kickoff Bcc: x@evil.com (26/10 14:30)")
        self.assertIsNone(msg["Bcc"])
        self.assertEqual((msg["From"], msg["To"]), ("eu@gmail.com", "eu@gmail.com"))
        body, attachment = list(msg.iter_parts())
        self.assertIn("## Prazo", body.get_content())
        self.assertEqual(attachment.get_filename(), "transcricao.md")
        self.assertEqual(attachment.get_payload(decode=True).decode("utf-8"), MEETING["transcript"])

    def test_untitled_meeting(self):
        self.assertTrue(mail.build({**MEETING, "title": ""}, "eu@gmail.com")["Subject"].startswith("Ata: Reunião sem título"))

    def test_configured(self):
        with mock.patch.object(mail, "env", lambda name: None):
            self.assertFalse(mail.configured())
            with self.assertRaisesRegex(RuntimeError, "não configurado"):
                mail.send(MEETING)
        with mock.patch.dict(os.environ, CREDS):
            self.assertTrue(mail.configured())

    def test_send_success_and_errors_hide_password(self):
        with mock.patch.dict(os.environ, CREDS):
            with mock.patch("smtplib.SMTP_SSL") as smtp:
                mail.send(MEETING)
            session = smtp.return_value.__enter__.return_value
            session.login.assert_called_once_with("eu@gmail.com", "abcd efgh ijkl mnop")
            session.send_message.assert_called_once()
            self.assertEqual(smtp.call_args.kwargs["timeout"], 30)
            context = smtp.call_args.kwargs["context"]
            self.assertEqual((context.verify_mode, context.check_hostname), (ssl.CERT_REQUIRED, True))

            for err, text in [(smtplib.SMTPAuthenticationError(535, b"bad"), "recusou o login"),
                              (ConnectionRefusedError(), "Sem conexão"),
                              (smtplib.SMTPServerDisconnected(), "Sem conexão")]:
                with mock.patch("smtplib.SMTP_SSL", side_effect=err):
                    with self.assertRaisesRegex(RuntimeError, text) as ctx:
                        mail.send(MEETING)
                self.assertNotIn("abcd", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
