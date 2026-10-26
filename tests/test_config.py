import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from metranscript import settings

SECRETS = {
    "DEEPSEEK_API_KEY": "sk-secret-deepseek-1234",
    "GMAIL_APP_PASSWORD": "abcd efgh ijkl mnop",
    "GOOGLE_CALENDAR_ICS": "https://calendar.google.com/calendar/ical/me/private-SECRETTOKEN/basic.ics",
}


class ConfigTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for p in (mock.patch.object(settings, "ROOT", self.root), mock.patch.dict(os.environ, {}, clear=True)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def dotenv(self) -> str:
        return (self.root / ".env").read_text(encoding="utf-8")


class WriteEnvTest(ConfigTestCase):
    def test_updates_appends_removes_and_keeps_the_rest(self):
        (self.root / ".env").write_text(
            "# my keys\nDEEPSEEK_API_KEY=old\nOTHER=1\nGMAIL_ADDRESS=a@b.c\nDEEPSEEK_API_KEY=dup\n", encoding="utf-8")
        settings.write_env({"DEEPSEEK_API_KEY": "sk-new", "GMAIL_ADDRESS": None, "GOOGLE_CALENDAR_ICS": "https://x/y.ics"})
        self.assertEqual(self.dotenv(), "# my keys\nDEEPSEEK_API_KEY=sk-new\nOTHER=1\nGOOGLE_CALENDAR_ICS=https://x/y.ics\n")
        self.assertEqual(settings.env("DEEPSEEK_API_KEY"), "sk-new")
        self.assertIsNone(settings.env("GMAIL_ADDRESS"))

    def test_creates_the_file_and_leaves_no_temp_file(self):
        settings.write_env({"GMAIL_ADDRESS": "me@x.com"})
        self.assertEqual(self.dotenv(), "GMAIL_ADDRESS=me@x.com\n")
        self.assertEqual([p.name for p in self.root.iterdir()], [".env"])

    def test_removing_the_last_key_leaves_an_empty_file(self):
        settings.write_env({"GMAIL_ADDRESS": "me@x.com"})
        settings.write_env({"GMAIL_ADDRESS": None})
        self.assertEqual(self.dotenv(), "")


class WriteEnvSafetyTest(ConfigTestCase):
    def test_a_failed_write_leaves_the_old_file_and_no_temp_file(self):
        (self.root / ".env").write_text("GMAIL_ADDRESS=old@x.com\n", encoding="utf-8")
        with mock.patch.object(settings.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                settings.write_env({"GMAIL_ADDRESS": "new@x.com"})
        self.assertEqual(self.dotenv(), "GMAIL_ADDRESS=old@x.com\n")
        self.assertEqual([p.name for p in self.root.iterdir()], [".env"])

    def test_concurrent_writes_keep_every_key(self):
        import threading
        def writer(name, value):
            for i in range(60):
                settings.write_env({name: f"{value}{i}"})
        threads = [threading.Thread(target=writer, args=(n, v)) for n, v in
                   [("DEEPSEEK_API_KEY", "sk-"), ("GMAIL_ADDRESS", "me@x.com#")]]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(settings.env("DEEPSEEK_API_KEY"), "sk-59")
        self.assertEqual(settings.env("GMAIL_ADDRESS"), "me@x.com#59")


class ValidateTest(ConfigTestCase):
    def test_accepts_and_trims_good_values(self):
        self.assertEqual(settings.validate("GMAIL_ADDRESS", "  me@gmail.com "), "me@gmail.com")
        self.assertEqual(settings.validate("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop"), "abcd efgh ijkl mnop")
        self.assertEqual(settings.validate("DEEPSEEK_API_KEY", "sk-abc"), "sk-abc")
        ics = "https://a/x.ics, https://b/y.ics"
        self.assertEqual(settings.validate("GOOGLE_CALENDAR_ICS", ics), ics)

    def test_rejects_bad_values_without_echoing_them(self):
        bad = [
            ("DEEPSEEK_API_KEY", "sk-a\nGMAIL_ADDRESS=evil@x.com"),
            ("DEEPSEEK_API_KEY", "sk-a\rb"),
            ("DEEPSEEK_API_KEY", "sk with spaces"),
            ("DEEPSEEK_API_KEY", "   "),
            ("DEEPSEEK_API_KEY", "x" * 3000),
            ("GMAIL_APP_PASSWORD", '"quoted-start'),
            ("GMAIL_APP_PASSWORD", "quoted-end'"),
            ("GMAIL_ADDRESS", "not-an-email"),
            ("GOOGLE_CALENDAR_ICS", "http://insecure/x.ics"),
            ("GOOGLE_CALENDAR_ICS", "https://a/x.ics,file:///etc/passwd"),
            ("NOT_A_KEY", "x"),
        ]
        for name, value in bad:
            with self.assertRaises(ValueError, msg=name) as ctx:
                settings.validate(name, value)
            if value.strip():
                self.assertNotIn(value.strip(), str(ctx.exception))


class StatusTest(ConfigTestCase):
    def test_status_never_contains_secret_values(self):
        settings.write_env({**SECRETS, "GMAIL_ADDRESS": "me@gmail.com"})
        status = settings.status()
        dumped = json.dumps(status)
        for secret in SECRETS.values():
            self.assertNotIn(secret, dumped)
        self.assertNotIn("SECRETTOKEN", dumped)
        self.assertEqual(status["GMAIL_ADDRESS"], {"set": True, "locked": False, "value": "me@gmail.com"})
        self.assertEqual(status["DEEPSEEK_API_KEY"], {"set": True, "locked": False, "value": None})

    def test_unset_and_locked(self):
        self.assertEqual(settings.status()["GMAIL_ADDRESS"], {"set": False, "locked": False, "value": None})
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-from-windows"}):
            self.assertEqual(settings.status()["DEEPSEEK_API_KEY"], {"set": True, "locked": True, "value": None})


if __name__ == "__main__":
    unittest.main()
