import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from metranscript import settings


class SettingsTest(unittest.TestCase):
    def test_env_then_dotenv(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(settings, "ROOT", Path(tmp)), \
                mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(settings.env("A"))
            (Path(tmp) / ".env").write_text('A="from-file"\nB=\nC = x y \n', encoding="utf-8")
            self.assertEqual(settings.env("A"), "from-file")
            self.assertIsNone(settings.env("B"))
            self.assertEqual(settings.env("C"), "x y")
            os.environ["A"] = "from-env"
            self.assertEqual(settings.env("A"), "from-env")


class DaysTest(unittest.TestCase):
    def test_days_falls_back_to_the_default_for_anything_unreadable(self):
        for raw, expected in ((None, 30), ("", 30), ("abc", 30), ("²", 30), ("١٢", 30), ("-5", 30), ("0", 0), ("45", 45), ("99999999999999999999999999", 3650)):
            env = {} if raw is None else {"AUDIO_KEEP_DAYS": raw}
            with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(settings, "ROOT", Path("/nonexistent")):
                if raw is None:
                    os.environ.pop("AUDIO_KEEP_DAYS", None)
                self.assertEqual(settings.days("AUDIO_KEEP_DAYS", 30), expected, raw)


if __name__ == "__main__":
    unittest.main()
