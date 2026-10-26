import unittest
from unittest import mock
from xml.etree import ElementTree

from metranscript import desktop

EVENT = {"title": "Weekly sync", "start": "2026-10-26T14:00:00-03:00", "app": "Meet"}


class DesktopTest(unittest.TestCase):
    def test_reminder_text(self):
        self.assertEqual(desktop.reminder_text(EVENT, 30), ("Weekly sync", "In 30 min, at 14:00 (Meet)"))
        self.assertEqual(desktop.reminder_text(EVENT, 2), ("Weekly sync", "Starts in 2 min (Meet)"))

    def test_toast_xml_keeps_hostile_text_as_data(self):
        hostile = '$(Start-Process calc) `whoami` "@ </text><text>x'
        xml = desktop.toast_xml(hostile, "msg & <b>", "http://127.0.0.1:8765/", ("Record", "http://127.0.0.1:8765/?record=a&b=1"))
        root = ElementTree.fromstring(xml)
        texts = [t.text for t in root.iter("text")]
        self.assertEqual(texts, [hostile, "msg & <b>"])
        self.assertEqual(root.find("actions/action").get("arguments"), "http://127.0.0.1:8765/?record=a&b=1")

    def test_launcher_uses_windowless_python(self):
        cmd = desktop.launcher()
        self.assertIn("pythonw.exe", cmd)
        self.assertTrue(cmd.endswith('start.pyw"'))

    def test_autostart_toggle_round_trip(self):
        with mock.patch.object(desktop, "RUN_NAME", "MeTranscriptUnitTest"):
            desktop.set_autostart(True)
            self.assertTrue(desktop.autostart_enabled())
            desktop.set_autostart(False)
            self.assertFalse(desktop.autostart_enabled())
            desktop.set_autostart(False)


if __name__ == "__main__":
    unittest.main()
