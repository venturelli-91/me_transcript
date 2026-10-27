import json
import os
import unittest
from unittest import mock

from metranscript import google, mail, server, settings
from tests.http_case import ServerCase

KEY = "sk-very-secret-key-9876"
SECRET = "fake-client-secret-9876"
CID = "1.apps.googleusercontent.com"


class ConfigRoutesTest(ServerCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        dotenv = settings.ROOT / ".env"
        self.addCleanup(lambda: dotenv.unlink(missing_ok=True))

    def test_get_reports_what_is_set_and_never_a_secret(self):
        status, body = self.call("GET", "/api/config")
        self.assertEqual(status, 200)
        self.assertFalse(any(f["set"] for f in body.values()))
        settings.write_env({"DEEPSEEK_API_KEY": KEY, "GOOGLE_CLIENT_ID": CID, "GOOGLE_CLIENT_SECRET": SECRET})
        status, body = self.call("GET", "/api/config")
        text = json.dumps(body)
        for secret in (KEY, SECRET):
            self.assertNotIn(secret, text)
        self.assertEqual(body["GOOGLE_CLIENT_ID"], {"set": True, "locked": False, "value": CID})
        self.assertTrue(body["DEEPSEEK_API_KEY"]["set"])

    def test_put_saves_validates_and_removes(self):
        status, body = self.call("PUT", "/api/config", {"DEEPSEEK_API_KEY": KEY, "GOOGLE_CLIENT_ID": CID})
        self.assertEqual(status, 200)
        self.assertNotIn(KEY, json.dumps(body))
        self.assertEqual(settings.env("DEEPSEEK_API_KEY"), KEY)
        status, body = self.call("PUT", "/api/config", {"DEEPSEEK_API_KEY": None})
        self.assertEqual((status, body["DEEPSEEK_API_KEY"]["set"]), (200, False))
        self.assertEqual(settings.env("GOOGLE_CLIENT_ID"), CID)

    def test_put_rejects_bad_input_without_echoing_it(self):
        cases = [
            ({"NOT_A_KEY": "x"}, "Unknown setting."),
            ({"DEEPSEEK_API_KEY": 5}, "Each value must be text or null."),
            ({"DEEPSEEK_API_KEY": KEY + "\nGOOGLE_CLIENT_ID=evil"}, "The value must be a single line."),
            ({"GOOGLE_CLIENT_ID": "nope"}, "The client ID ends with .apps.googleusercontent.com."),
            ({"GOOGLE_CLIENT_SECRET": "has space"}, "The client secret has no spaces."),
            ({"GMAIL_ADDRESS": "me@gmail.com"}, "Unknown setting."),
        ]
        for payload, message in cases:
            status, body = self.call("PUT", "/api/config", payload)
            self.assertEqual((status, body["error"]), (400, message), payload)
            self.assertNotIn(KEY, json.dumps(body))
        self.assertIsNone(settings.env("DEEPSEEK_API_KEY"))
        self.assertIsNone(settings.env("GOOGLE_CLIENT_ID"))
        self.assertEqual(self.call("PUT", "/api/config", [])[0], 400)

    def test_a_failed_save_is_reported_as_a_message(self):
        with mock.patch.object(settings, "write_env", side_effect=OSError("disk full")):
            status, body = self.call("PUT", "/api/config", {"DEEPSEEK_API_KEY": KEY})
        self.assertEqual((status, body["error"]), (409, "Could not save the .env file."))
        self.assertNotIn(KEY, json.dumps(body))

    def test_nothing_is_written_when_one_value_is_invalid(self):
        status, _ = self.call("PUT", "/api/config", {"DEEPSEEK_API_KEY": KEY, "GOOGLE_CLIENT_ID": "nope"})
        self.assertEqual(status, 400)
        self.assertIsNone(settings.env("DEEPSEEK_API_KEY"))

    def test_a_windows_environment_variable_locks_its_field(self):
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-from-windows"}):
            status, body = self.call("GET", "/api/config")
            self.assertTrue(body["DEEPSEEK_API_KEY"]["locked"])
            status, body = self.call("PUT", "/api/config", {"DEEPSEEK_API_KEY": KEY})
            self.assertEqual(status, 409)
            self.assertIn("Windows environment variable", body["error"])
            self.assertNotIn("sk-from-windows", json.dumps(body))

    def test_saving_a_google_setting_refreshes_the_watcher(self):
        fake = mock.Mock(last_fetch="old")
        with mock.patch.object(server, "watcher", fake):
            self.call("PUT", "/api/config", {"GOOGLE_CLIENT_ID": CID})
        self.assertIsNone(fake.last_fetch)
        fake.last_fetch = "old"
        with mock.patch.object(server, "watcher", fake):
            self.call("PUT", "/api/config", {"MEETING_KEYWORDS": "Meet"})
        self.assertEqual(fake.last_fetch, "old")

    def test_config_routes_are_guarded(self):
        self.assertEqual(self.call("GET", "/api/config", headers={"Host": "evil.com"})[0], 403)
        self.assertEqual(self.call("PUT", "/api/config", {}, headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.call("POST", "/api/config/test-email", {}, headers={"Host": "evil.com"})[0], 403)

    def test_test_email_route(self):
        status, body = self.call("POST", "/api/config/test-email", {})
        self.assertEqual(status, 409)
        self.assertIn("not configured", body["error"])
        google._save("me@gmail.com", "1//refresh")
        self.addCleanup(lambda: google._file().unlink(missing_ok=True))
        with mock.patch.object(mail, "send") as send:
            self.assertEqual(self.call("POST", "/api/config/test-email", {}), (200, {}))
        sent = send.call_args.args[0]
        self.assertIn("test", sent["title"].lower())
        with mock.patch.object(mail, "send", side_effect=RuntimeError("Cannot reach Gmail. Check your connection and send again.")):
            status, body = self.call("POST", "/api/config/test-email", {})
        self.assertEqual((status, body["error"]), (409, "Cannot reach Gmail. Check your connection and send again."))


if __name__ == "__main__":
    unittest.main()
