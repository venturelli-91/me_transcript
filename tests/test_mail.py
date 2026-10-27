import base64
import email
import unittest
from email import policy
from unittest import mock

from metranscript import google, mail

MEETING = {"title": "Kickoff\nBcc: x@evil.com", "started_at": "2026-10-26T14:30:00",
           "summary": "## Deadline\n- Friday", "transcript": "[00:00:01] **Others:** Hi.\n"}


class MailTest(unittest.TestCase):
    def test_build_message_has_the_summary_and_no_attachment(self):
        msg = mail.build(MEETING, "me@gmail.com")
        self.assertEqual(msg["Subject"], "MeTranscript: Kickoff Bcc: x@evil.com (2026-10-26 14:30)")
        self.assertIsNone(msg["Bcc"])
        self.assertEqual((msg["From"], msg["To"]), ("me@gmail.com", "me@gmail.com"))
        self.assertIn("## Deadline", msg.get_content())
        self.assertFalse(msg.is_multipart())
        self.assertNotIn("Hi.", msg.as_string())

    def test_untitled_meeting(self):
        self.assertTrue(mail.build({**MEETING, "title": ""}, "me@gmail.com")["Subject"].startswith("MeTranscript: Untitled meeting"))

    def test_configured_follows_the_connected_sender(self):
        with mock.patch.object(google, "send_account", return_value=None):
            self.assertFalse(mail.configured())
            with self.assertRaisesRegex(RuntimeError, "not configured"):
                mail.send(MEETING)
        with mock.patch.object(google, "send_account", return_value="me@gmail.com"):
            self.assertTrue(mail.configured())

    def test_send_posts_the_message_as_the_chosen_account(self):
        with mock.patch.object(google, "send_account", return_value="me@gmail.com"), mock.patch.object(google, "api", return_value={"id": "1"}) as api:
            mail.send(MEETING)
        (account, url), kwargs = api.call_args.args, api.call_args.kwargs
        self.assertEqual((account, url), ("me@gmail.com", mail.SEND_URL))
        sent = email.message_from_bytes(base64.urlsafe_b64decode(kwargs["body"]["raw"]), policy=policy.default)
        self.assertEqual((sent["From"], sent["To"]), ("me@gmail.com", "me@gmail.com"))
        self.assertIsNone(sent["Bcc"])
        self.assertIn("Friday", sent.get_content())

    def test_failures_become_clear_messages(self):
        cases = [(google.ReconnectNeeded("Google no longer accepts the login for me@gmail.com. Sign in again in Settings."), "Sign in again"),
                 (google.GoogleError(403, "PERMISSION_DENIED"), "refused to send"), (google.GoogleError(401, "UNAUTHENTICATED"), "refused to send"),
                 (google.GoogleError(500, "backendError"), "could not send the message \\(500\\)"),
                 (RuntimeError("Cannot reach Google. Check your connection and try again."), "Cannot reach Google")]
        for error, text in cases:
            with self.subTest(error=str(error)), mock.patch.object(google, "send_account", return_value="me@gmail.com"), \
                    mock.patch.object(google, "api", side_effect=error), self.assertRaisesRegex(RuntimeError, text):
                mail.send(MEETING)


if __name__ == "__main__":
    unittest.main()
