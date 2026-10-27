import http.client
import time
import unittest
from unittest import mock

from metranscript import server, store
from tests.http_case import ServerCase


class RoutesTest(ServerCase):
    def test_page_and_read_routes(self):
        status, html = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("<title>MeTranscript</title>", html)
        self.assertEqual(self.call("GET", "/?record=abc")[0], 200)
        status, listed = self.call("GET", "/api/meetings")
        self.assertEqual((status, type(listed)), (200, list))
        status, body = self.call("GET", "/api/status")
        self.assertEqual((status, body["phase"]), (200, "idle"))
        self.assertEqual(self.call("GET", "/api/agenda")[1], {"configured": False, "events": [], "error": None})

    def test_fonts_are_served_locally_and_confined(self):
        def fetch(path):
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            conn.request("GET", path, headers={"Host": f"127.0.0.1:{self.port}"})
            res = conn.getresponse()
            body = res.read()
            conn.close()
            return res.status, res.getheader("Content-Type"), body

        status, ctype, body = fetch("/fonts/hanken-grotesk-latin.woff2")
        self.assertEqual((status, ctype.split(";")[0], body[:4]), (200, "font/woff2", b"wOF2"))
        self.assertEqual(fetch("/fonts/../server.py")[0], 404)
        self.assertEqual(fetch("/fonts/missing.woff2")[0], 404)
        self.assertEqual(fetch("/fonts/hanken-grotesk-latin.woff2/x")[0], 404)
        _, html = self.call("GET", "/")
        self.assertNotIn("googleapis", html)

    def test_unknown_routes_and_meetings(self):
        self.assertEqual(self.call("GET", "/nope"), (404, {"error": "Not found."}))
        self.assertEqual(self.call("DELETE", "/api/meetings"), (404, {"error": "Not found."}))
        self.assertEqual(self.call("PATCH", "/api/meetings/x")[0], 501)
        self.assertEqual(self.call("POST", "/api/meetings/2026-01-01_0000/nope", {})[0], 404)
        self.assertEqual(self.call("GET", "/api/meetings/2026-01-01_0000"), (404, {"error": "Meeting not found."}))
        self.assertEqual(self.call("GET", "/api/meetings/..%2Fetc")[0], 404)

    def test_guards(self):
        status, body = self.call("GET", "/api/status", headers={"Host": "evil.com"})
        self.assertEqual((status, body["error"]), (403, "Host not allowed."))
        status, body = self.call("POST", "/api/stop", {}, headers={"Content-Type": "text/plain"})
        self.assertEqual((status, body["error"]), (415, "Use Content-Type: application/json."))
        status, body = self.call("POST", "/api/start", raw=b"{nope")
        self.assertEqual((status, body["error"]), (400, "Invalid JSON."))
        self.assertEqual(self.call("POST", "/api/start", raw=b"[]")[1]["error"], "JSON must be an object.")

    def test_start_needs_the_consent_confirmation(self):
        with mock.patch.object(server, "start", return_value="2026-01-01_0900") as start:
            ask = "Confirm that you told the participants this meeting is being recorded."
            self.assertEqual(self.call("POST", "/api/start", {"lang": "en"}), (400, {"error": ask}))
            for wrong in ("yes", "true", 1, False, None):
                self.assertEqual(self.call("POST", "/api/start", {"lang": "en", "consent": wrong})[0], 400, wrong)
            start.assert_not_called()
            self.assertEqual(self.call("POST", "/api/start", {"lang": "en", "consent": True}), (200, {"id": "2026-01-01_0900"}))
        self.assertIs(start.call_args.args[-1], True)

    def test_a_reminder_token_survives_a_refused_start_and_the_typed_title_wins(self):
        server.reminder_tokens["tok"] = ("Standup", "Zoom", time.time() + 60)
        self.addCleanup(server.reminder_tokens.clear)
        with mock.patch.object(server, "start", return_value="2026-01-01_0900") as start:
            self.assertEqual(self.call("POST", "/api/start", {"reminder": "tok"})[0], 400)
            self.assertIn("tok", server.reminder_tokens)
            self.assertEqual(self.call("POST", "/api/start", {"reminder": "tok", "consent": True})[0], 200)
            self.assertEqual(start.call_args.args[:1], ("Standup",))
            self.assertNotIn("tok", server.reminder_tokens)
            server.reminder_tokens["tok2"] = ("Standup", "Zoom", time.time() + 60)
            self.call("POST", "/api/start", {"reminder": "tok2", "title": "My title", "consent": True})
            self.assertEqual(start.call_args.args[:1], ("My title",))

    def test_validation_errors(self):
        self.assertEqual(self.call("POST", "/api/start", {"lang": "fr"})[1]["error"], "Language must be pt or en.")
        self.assertEqual(self.call("POST", "/api/start", {"title": 3})[1]["error"], "Title must be text.")
        self.assertEqual(self.call("POST", "/api/start", {"private": "yes"})[1]["error"], "private must be true or false.")
        self.assertEqual(self.call("POST", "/api/start", {"app": "Slack"})[1]["error"], "Unknown meeting app.")
        self.assertEqual(self.call("POST", "/api/start", {"reminder": "bogus"})[1]["error"], "This reminder link has expired.")
        self.assertEqual(self.call("POST", "/api/devices", {"track": "x", "name": "y"})[0], 400)
        self.assertEqual(self.call("POST", "/api/settings", {"autostart": "yes"})[0], 400)

    def test_idle_state_conflicts(self):
        self.assertEqual(self.call("POST", "/api/stop", {}), (409, {"error": "No recording in progress."}))
        self.assertEqual(self.call("POST", "/api/devices", {"track": "mic", "name": "x"})[0], 409)

    def test_rename_route(self):
        mid = store.create("Before", "pt")
        status, m = self.call("PUT", f"/api/meetings/{mid}/title", {"title": "  After\n title "})
        self.assertEqual((status, m["title"]), (200, "After title"))
        self.assertEqual(self.call("PUT", f"/api/meetings/{mid}/title", {"title": 3})[1]["error"], "Title must be text.")
        self.assertEqual(self.call("PUT", "/api/meetings/2026-01-01_0000/title", {"title": "x"})[0], 404)

    def test_delete_route(self):
        mid = store.create("Delete me", "pt")
        self.assertEqual(self.call("DELETE", f"/api/meetings/{mid}"), (200, {}))
        self.assertEqual(self.call("GET", f"/api/meetings/{mid}")[0], 404)
        self.assertEqual(self.call("DELETE", f"/api/meetings/{mid}")[0], 404)
        self.assertEqual(self.call("DELETE", f"/api/meetings/{mid}", headers={"Host": "evil.com"})[0], 403)

    def test_cannot_delete_a_meeting_that_is_being_recorded_or_processed(self):
        mid = store.create("Busy", "pt")
        for phase in ("recording", "transcribing", "enhancing"):
            with mock.patch.object(server.session, "phase", phase), mock.patch.object(server.session, "meeting_id", mid):
                status, body = self.call("DELETE", f"/api/meetings/{mid}")
            self.assertEqual(status, 409, phase)
            self.assertIn("Stop the recording", body["error"])
        self.assertEqual(self.call("GET", f"/api/meetings/{mid}")[0], 200)
        other = store.create("Other", "pt")
        with mock.patch.object(server.session, "phase", "recording"), mock.patch.object(server.session, "meeting_id", mid):
            self.assertEqual(self.call("DELETE", f"/api/meetings/{other}")[0], 200)

    def test_meeting_routes(self):
        mid = store.create("Routes", "pt")
        self.assertEqual(self.call("PUT", f"/api/meetings/{mid}/notes", {"notes": "- hi"}), (200, {}))
        status, m = self.call("GET", f"/api/meetings/{mid}")
        self.assertEqual((status, m["notes"], m["title"]), (200, "- hi", "Routes"))
        self.assertEqual(self.call("PUT", f"/api/meetings/{mid}/notes", {"notes": 3})[1]["error"], "notes must be text.")
        self.assertEqual(self.call("POST", f"/api/meetings/{mid}/chat", {"message": " "})[0], 400)
        self.assertEqual(self.call("POST", f"/api/meetings/{mid}/chat", {"message": "x" * 4001})[0], 400)
        self.assertEqual(self.call("POST", f"/api/meetings/{mid}/undo", {}), (409, {"error": "There is no previous summary version."}))
        self.assertEqual(self.call("POST", f"/api/meetings/{mid}/email", {})[0], 409)
        self.assertIn(mid, [m["id"] for m in self.call("GET", "/api/meetings")[1]])


if __name__ == "__main__":
    unittest.main()
