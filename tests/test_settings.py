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


if __name__ == "__main__":
    unittest.main()
