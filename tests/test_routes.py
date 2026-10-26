import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from metranscript import server, store


class RoutesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.patches = [mock.patch.object(store, "ROOT", Path(cls.tmp.name)), mock.patch.object(server, "watcher", None)]
        for p in cls.patches:
            p.start()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        server.HOSTS.add(f"127.0.0.1:{cls.port}")
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        for p in cls.patches:
            p.stop()
        cls.tmp.cleanup()

    def call(self, method, path, body=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json", **(headers or {})}
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        conn.request(method, path, body=data, headers=h)
        res = conn.getresponse()
        payload = res.read()
        conn.close()
        ctype = res.getheader("Content-Type", "")
        return res.status, (json.loads(payload) if "json" in ctype else payload.decode())

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

    def test_unknown_routes_and_meetings(self):
        self.assertEqual(self.call("GET", "/nope"), (404, {"error": "Not found."}))
        self.assertEqual(self.call("DELETE", "/api/meetings")[0], 501)
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
        self.assertEqual(self.call("GET", "/api/meetings")[1][0]["id"], mid)


if __name__ == "__main__":
    unittest.main()
