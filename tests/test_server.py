import unittest
from unittest import mock

from metranscript import server

EVENT = {"key": "k", "title": "Weekly sync", "start": "2026-10-26T14:00:00-03:00", "app": "Meet"}


class MeetingAppsTest(unittest.TestCase):
    def test_accepts_every_app_the_detector_or_the_calendar_can_report(self):
        for app in [*server.detect.EXES.values(), *server.agenda.APPS.values()]:
            self.assertIn(app, server.MEETING_APPS)
        self.assertNotIn("Slack", server.MEETING_APPS)


class ReminderTokenTest(unittest.TestCase):
    def setUp(self):
        server.reminder_tokens.clear()

    def test_two_minute_reminder_token_carries_title_and_app(self):
        with mock.patch.object(server.desktop, "notify") as notify:
            server.on_reminder(EVENT, 2, 2)
        url = notify.call_args.args[3][1]
        token = url.split("record=", 1)[1]
        title, app, _expires = server.reminder_tokens[token]
        self.assertEqual((title, app), ("Weekly sync", "Meet"))

    def test_thirty_minute_reminder_has_no_record_button(self):
        with mock.patch.object(server.desktop, "notify") as notify:
            server.on_reminder(EVENT, 30, 30)
        self.assertIsNone(notify.call_args.args[3])
        self.assertEqual(server.reminder_tokens, {})


if __name__ == "__main__":
    unittest.main()
