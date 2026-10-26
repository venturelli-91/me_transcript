import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import icalendar

from metranscript import agenda

BRT = timezone(timedelta(hours=-3))
ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:weekly@test
SUMMARY:Weekly sync
DTSTART:20261019T170000Z
DTEND:20261019T173000Z
RRULE:FREQ=WEEKLY;BYDAY=MO
X-GOOGLE-CONFERENCE:https://meet.google.com/abc-defg-hij
END:VEVENT
BEGIN:VEVENT
UID:zoom@test
SUMMARY:Client call
DTSTART:20261026T190000Z
DTEND:20261026T200000Z
DESCRIPTION:Join here: https://us02web.zoom.us/j/123456789?pwd=x\\nThanks
END:VEVENT
BEGIN:VEVENT
UID:nolink@test
SUMMARY:Lunch
DTSTART:20261026T150000Z
DTEND:20261026T160000Z
END:VEVENT
BEGIN:VEVENT
UID:allday@test
SUMMARY:Holiday
DTSTART;VALUE=DATE:20261026
DTEND;VALUE=DATE:20261027
LOCATION:https://meet.google.com/xyz-xyzx-xyz
END:VEVENT
BEGIN:VEVENT
UID:declined@test
SUMMARY:Optional demo
DTSTART:20261026T180000Z
DTEND:20261026T183000Z
LOCATION:https://teams.microsoft.com/l/meetup-join/abc
ATTENDEE;PARTSTAT=DECLINED:mailto:Me@gmail.com
END:VEVENT
BEGIN:VEVENT
UID:weekly@test
RECURRENCE-ID:20261026T170000Z
SUMMARY:Weekly sync
DTSTART:20261026T170000Z
DTEND:20261026T173000Z
STATUS:CANCELLED
X-GOOGLE-CONFERENCE:https://meet.google.com/abc-defg-hij
END:VEVENT
END:VCALENDAR
"""
NOW = datetime(2026, 10, 26, 13, 0, tzinfo=BRT)  # 16:00 UTC


class AgendaTest(unittest.TestCase):
    def test_upcoming_keeps_only_timed_linked_accepted_future_events(self):
        events = agenda.upcoming([ICS], NOW, "me@gmail.com")
        self.assertEqual([(e["title"], e["start"], e["app"]) for e in events], [
            ("Client call", "2026-10-26T16:00-03:00", "Zoom"),  # today's weekly sync is cancelled
        ])
        self.assertEqual(agenda.meeting_link(icalendar.Calendar.from_ical(ICS).walk("VEVENT")[1]),
                         "https://us02web.zoom.us/j/123456789?pwd=x")

    def test_declined_only_filtered_for_my_address(self):
        titles = [e["title"] for e in agenda.upcoming([ICS], NOW, "someone@else.com")]
        self.assertIn("Optional demo", titles)

    def test_recurring_occurrences_have_distinct_keys(self):
        a = agenda.upcoming([ICS], NOW + timedelta(days=7))[0]
        b = agenda.upcoming([ICS], NOW + timedelta(days=14))[0]
        self.assertEqual((a["title"], b["title"]), ("Weekly sync", "Weekly sync"))
        self.assertNotEqual(a["key"], b["key"])
        self.assertTrue(a["key"].endswith("+00:00"))

    def test_only_https_feeds(self):
        with mock.patch.object(agenda, "env", lambda name: " https://a/x.ics, file:///etc/passwd ,http://b,"):
            self.assertEqual(agenda.ics_urls(), ["https://a/x.ics"])

    def test_due_fires_each_reminder_once(self):
        event = {"key": "k", "title": "T", "start": "2026-10-26T14:00:00-03:00", "app": "Meet", "link": "x"}
        sent: set[str] = set()
        at = lambda h, m: datetime(2026, 10, 26, h, m, tzinfo=BRT)
        self.assertEqual(agenda.due([event], at(13, 20), sent), [])
        self.assertEqual([(m, r) for _, m, r in agenda.due([event], at(13, 30), sent)], [(30, 30)])
        self.assertEqual(agenda.due([event], at(13, 40), sent), [])
        self.assertEqual([(m, r) for _, m, r in agenda.due([event], at(13, 58), sent)], [(2, 2)])
        self.assertEqual(agenda.due([event], at(13, 59), sent), [])

    def test_late_start_gets_current_reminder_only(self):
        event = {"key": "k", "title": "T", "start": "2026-10-26T14:00:00-03:00", "app": "Meet", "link": "x"}
        fired = agenda.due([event], datetime(2026, 10, 26, 13, 45, tzinfo=BRT), set())
        self.assertEqual([(m, r) for _, m, r in fired], [(15, 30)])
        fired = agenda.due([event], datetime(2026, 10, 26, 13, 59, tzinfo=BRT), set())
        self.assertEqual([(m, r) for _, m, r in fired], [(1, 2)])
        fired = agenda.due([event], datetime(2026, 10, 26, 13, 57, 50, tzinfo=BRT), set())
        self.assertEqual([(m, r) for _, m, r in fired], [(2, 30)])


if __name__ == "__main__":
    unittest.main()
