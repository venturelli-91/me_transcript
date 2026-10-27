import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from metranscript import agenda, google

BRT = timezone(timedelta(hours=-3))
NOW = datetime(2026, 10, 26, 13, 0, tzinfo=BRT)  # 16:00 UTC


def event(id, summary, start, **extra) -> dict:
    return {"id": id, "summary": summary, "start": {"dateTime": start}, **extra}


ITEMS = [
    event("meet1", "Weekly sync", "2026-10-26T14:00:00-03:00", hangoutLink="https://meet.google.com/abc-defg-hij"),
    event("zoom1", "Client call", "2026-10-26T16:00:00-03:00", description="Join here: https://us02web.zoom.us/j/123456789?pwd=x<br>Thanks"),
    event("lunch", "Lunch", "2026-10-26T12:00:00-03:00"),
    {"id": "allday", "summary": "Holiday", "start": {"date": "2026-10-26"}, "location": "https://meet.google.com/xyz-xyzx-xyz"},
    event("declined", "Optional demo", "2026-10-26T18:00:00-03:00", location="https://teams.microsoft.com/l/meetup-join/abc",
          attendees=[{"self": True, "responseStatus": "declined"}, {"responseStatus": "accepted"}]),
    event("cancelled", "Cancelled sync", "2026-10-26T15:00:00-03:00", status="cancelled", hangoutLink="https://meet.google.com/aaa-bbbb-ccc"),
    event("past", "Already started", "2026-10-26T12:30:00-03:00", hangoutLink="https://meet.google.com/ddd-eeee-fff"),
    event("entry", "Via entry point", "2026-10-26T17:00:00Z", conferenceData={"entryPoints": [{"uri": "tel:+1"}, {"uri": "https://meet.google.com/ggg-hhhh-iii"}]}),
    event("naive", "No offset", "2026-10-26T19:00:00", location="https://teams.live.com/meet/123"),
]


class UpcomingTest(unittest.TestCase):
    def test_keeps_only_timed_linked_accepted_future_events_soonest_first(self):
        found = agenda.upcoming(ITEMS, NOW, "me@gmail.com")
        self.assertEqual([(e["title"], e["start"], e["app"]) for e in found], [
            ("Weekly sync", "2026-10-26T14:00-03:00", "Meet"),
            ("Via entry point", "2026-10-26T14:00-03:00", "Meet"),  # 17:00 UTC, shown in local time
            ("Client call", "2026-10-26T16:00-03:00", "Zoom"),
            ("No offset", "2026-10-26T19:00-03:00", "Teams"),  # no offset means local time
        ])
        titles = [e["title"] for e in found]
        for gone in ("Lunch", "Holiday", "Optional demo", "Cancelled sync", "Already started"):
            self.assertNotIn(gone, titles)
        self.assertTrue(all(e["account"] == "me@gmail.com" for e in found))

    def test_the_meeting_link_is_found_in_every_place_google_puts_it(self):
        self.assertEqual(agenda.meeting_link(ITEMS[1]), "https://us02web.zoom.us/j/123456789?pwd=x")
        self.assertEqual(agenda.meeting_link(ITEMS[7]), "https://meet.google.com/ggg-hhhh-iii")
        self.assertEqual(agenda.meeting_link(ITEMS[0]), "https://meet.google.com/abc-defg-hij")
        self.assertIsNone(agenda.meeting_link(ITEMS[2]))
        self.assertIsNone(agenda.meeting_link({"description": None, "location": 5, "conferenceData": {"entryPoints": None}}))

    def test_only_my_own_decline_hides_an_event(self):
        others = event("x", "Demo", "2026-10-26T18:00:00-03:00", location="https://teams.microsoft.com/l/a",
                       attendees=[{"self": False, "responseStatus": "declined"}])
        self.assertEqual([e["title"] for e in agenda.upcoming([others], NOW)], ["Demo"])

    def test_each_occurrence_and_account_has_its_own_key_in_utc(self):
        a = event("series_20261102T170000Z", "Weekly", "2026-11-02T14:00:00-03:00", hangoutLink="https://meet.google.com/a-b-c")
        b = event("series_20261109T170000Z", "Weekly", "2026-11-09T14:00:00-03:00", hangoutLink="https://meet.google.com/a-b-c")
        ka, kb = (agenda.upcoming([x], NOW, "me@gmail.com")[0]["key"] for x in (a, b))
        self.assertNotEqual(ka, kb)
        self.assertTrue(ka.endswith("2026-11-02T17:00:00+00:00"))
        self.assertNotEqual(ka, agenda.upcoming([a], NOW, "other@gmail.com")[0]["key"])

    def test_a_missing_title_gets_a_placeholder(self):
        found = agenda.upcoming([{"id": "x", "start": {"dateTime": "2026-10-26T15:00:00-03:00"}, "hangoutLink": "https://meet.google.com/a-b-c"}], NOW)
        self.assertEqual(found[0]["title"], "Untitled meeting")


class CollectTest(unittest.TestCase):
    def test_events_for_asks_google_for_the_next_day_of_single_events(self):
        with mock.patch.object(google, "api", return_value={"items": ITEMS[:1]}) as api:
            found = agenda.events_for("me@gmail.com", NOW)
        self.assertEqual([e["title"] for e in found], ["Weekly sync"])
        (email, url), kwargs = api.call_args.args, api.call_args.kwargs
        self.assertEqual((email, url), ("me@gmail.com", agenda.EVENTS_URL))
        self.assertEqual(kwargs["params"]["timeMin"], "2026-10-26T13:00:00-03:00")
        self.assertEqual(kwargs["params"]["timeMax"], "2026-10-27T13:00:00-03:00")
        self.assertEqual((kwargs["params"]["singleEvents"], kwargs["params"]["orderBy"]), ("true", "startTime"))

    def test_accounts_are_merged_in_time_order_and_a_failing_one_is_reported(self):
        per = {"a@gmail.com": [event("1", "Late", "2026-10-26T18:00:00-03:00", hangoutLink="https://meet.google.com/a-b-c")],
               "b@gmail.com": [event("2", "Early", "2026-10-26T14:00:00-03:00", hangoutLink="https://meet.google.com/d-e-f")]}

        def fake(email, url, **kw):
            if email == "broken@gmail.com":
                raise google.ReconnectNeeded("Google no longer accepts the login for broken@gmail.com. Sign in again in Settings.")
            if email == "down@gmail.com":
                raise OSError("network secret detail")
            return {"items": per[email]}

        with mock.patch.object(google, "emails", return_value=["a@gmail.com", "broken@gmail.com", "b@gmail.com", "down@gmail.com"]), \
                mock.patch.object(google, "api", fake):
            events, error = agenda.collect(NOW)
        self.assertEqual([(e["title"], e["account"]) for e in events], [("Early", "b@gmail.com"), ("Late", "a@gmail.com")])
        self.assertIn("broken@gmail.com", error)
        self.assertIn("Could not read a calendar", error)
        self.assertNotIn("network secret detail", error)

    def test_no_accounts_means_no_events_and_no_error(self):
        with mock.patch.object(google, "emails", return_value=[]):
            self.assertEqual(agenda.collect(NOW), ([], None))


class DueTest(unittest.TestCase):
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
