import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from metranscript import settings

SECRETS = {
    "DEEPSEEK_API_KEY": "sk-secret-deepseek-1234",
    "GOOGLE_CLIENT_SECRET": "GOCSPX-secret-client-1234",
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
            "# my keys\nDEEPSEEK_API_KEY=old\nOTHER=1\nGOOGLE_CLIENT_ID=a.apps.googleusercontent.com\nDEEPSEEK_API_KEY=dup\n", encoding="utf-8")
        settings.write_env({"DEEPSEEK_API_KEY": "sk-new", "GOOGLE_CLIENT_ID": None, "MEETING_KEYWORDS": "Meet,Zoom"})
        self.assertEqual(self.dotenv(), "# my keys\nDEEPSEEK_API_KEY=sk-new\nOTHER=1\nMEETING_KEYWORDS=Meet,Zoom\n")
        self.assertEqual(settings.env("DEEPSEEK_API_KEY"), "sk-new")
        self.assertIsNone(settings.env("GMAIL_ADDRESS"))

    def test_creates_the_file_and_leaves_no_temp_file(self):
        settings.write_env({"GOOGLE_CLIENT_ID": "me.apps.googleusercontent.com"})
        self.assertEqual(self.dotenv(), "GOOGLE_CLIENT_ID=me.apps.googleusercontent.com\n")
        self.assertEqual([p.name for p in self.root.iterdir()], [".env"])

    def test_removing_the_last_key_leaves_an_empty_file(self):
        settings.write_env({"GOOGLE_CLIENT_ID": "me.apps.googleusercontent.com"})
        settings.write_env({"GOOGLE_CLIENT_ID": None})
        self.assertEqual(self.dotenv(), "")


class WriteEnvSafetyTest(ConfigTestCase):
    def test_a_failed_write_leaves_the_old_file_and_no_temp_file(self):
        (self.root / ".env").write_text("GOOGLE_CLIENT_ID=old.apps.googleusercontent.com\n", encoding="utf-8")
        with mock.patch.object(settings.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                settings.write_env({"GOOGLE_CLIENT_ID": "new.apps.googleusercontent.com"})
        self.assertEqual(self.dotenv(), "GOOGLE_CLIENT_ID=old.apps.googleusercontent.com\n")
        self.assertEqual([p.name for p in self.root.iterdir()], [".env"])

    def test_concurrent_writes_keep_every_key(self):
        import threading
        def writer(name, value):
            for i in range(60):
                settings.write_env({name: f"{value}{i}"})
        threads = [threading.Thread(target=writer, args=(n, v)) for n, v in
                   [("DEEPSEEK_API_KEY", "sk-"), ("GOOGLE_CLIENT_ID", "me.apps.googleusercontent.com#")]]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(settings.env("DEEPSEEK_API_KEY"), "sk-59")
        self.assertEqual(settings.env("GOOGLE_CLIENT_ID"), "me.apps.googleusercontent.com#59")


class ValidateTest(ConfigTestCase):
    def test_accepts_and_trims_good_values(self):
        self.assertEqual(settings.validate("GOOGLE_CLIENT_ID", "  1.apps.googleusercontent.com "), "1.apps.googleusercontent.com")
        self.assertEqual(settings.validate("GOOGLE_CLIENT_SECRET", "GOCSPX-abc_DEF"), "GOCSPX-abc_DEF")
        self.assertEqual(settings.validate("DEEPSEEK_API_KEY", "sk-abc"), "sk-abc")
        self.assertEqual(settings.validate("AUDIO_KEEP_DAYS", " 0 "), "0")
        self.assertEqual(settings.validate("MEETING_KEEP_DAYS", "90"), "90")
        self.assertEqual(settings.validate("AUDIO_KEEP_DAYS", "007"), "7")

    def test_rejects_bad_values_without_echoing_them(self):
        bad = [
            ("DEEPSEEK_API_KEY", "sk-a\nGOOGLE_CLIENT_ID=evil.apps.googleusercontent.com"),
            ("DEEPSEEK_API_KEY", "sk-a\rb"),
            ("DEEPSEEK_API_KEY", "sk with spaces"),
            ("DEEPSEEK_API_KEY", "   "),
            ("DEEPSEEK_API_KEY", "x" * 3000),
            ("GOOGLE_CLIENT_SECRET", '"quoted-start'),
            ("GOOGLE_CLIENT_SECRET", "quoted-end'"),
            ("GOOGLE_CLIENT_SECRET", "has a space"),
            ("GOOGLE_CLIENT_ID", "not-a-client-id"),
            ("GMAIL_ADDRESS", "me@gmail.com"),  # removed: the app uses the Google login now
            ("GOOGLE_CALENDAR_ICS", "https://a/x.ics"),
            ("NOT_A_KEY", "x"),
        ]
        for name, value in bad:
            with self.assertRaises(ValueError, msg=name) as ctx:
                settings.validate(name, value)
            if value.strip():
                self.assertNotIn(value.strip(), str(ctx.exception))

    def test_retention_days_reject_non_ascii_digits_without_echoing_them(self):
        for value in ("²", "١٢", "٣"):
            with self.assertRaises(ValueError, msg=value) as ctx:
                settings.validate("AUDIO_KEEP_DAYS", value)
            self.assertNotIn(value, str(ctx.exception))

    def test_retention_days_are_whole_numbers_in_range(self):
        for name, value in [("AUDIO_KEEP_DAYS", "-1"), ("AUDIO_KEEP_DAYS", "3651"), ("MEETING_KEEP_DAYS", "0"),
                            ("MEETING_KEEP_DAYS", "ten"), ("MEETING_KEEP_DAYS", "1.5")]:
            with self.assertRaises(ValueError, msg=f"{name}={value}"):
                settings.validate(name, value)


class StatusTest(ConfigTestCase):
    def test_status_never_contains_secret_values(self):
        settings.write_env({**SECRETS, "GOOGLE_CLIENT_ID": "1.apps.googleusercontent.com"})
        status = settings.status()
        dumped = json.dumps(status)
        for secret in SECRETS.values():
            self.assertNotIn(secret, dumped)
        self.assertEqual(status["GOOGLE_CLIENT_ID"], {"set": True, "locked": False, "value": "1.apps.googleusercontent.com"})
        self.assertEqual(status["DEEPSEEK_API_KEY"], {"set": True, "locked": False, "value": None})

    def test_unset_and_locked(self):
        self.assertEqual(settings.status()["GOOGLE_CLIENT_ID"], {"set": False, "locked": False, "value": None})
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-from-windows"}):
            self.assertEqual(settings.status()["DEEPSEEK_API_KEY"], {"set": True, "locked": True, "value": None})


if __name__ == "__main__":
    unittest.main()
