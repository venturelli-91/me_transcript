import unittest
from unittest import mock

from metranscript import detect


class DetectTest(unittest.TestCase):
    def test_app_name(self):
        cases = {
            "C:#Program Files#Google#Chrome#Application#chrome.exe": "Chrome",
            "C:#Users#PC#AppData#Roaming#Zoom#bin#Zoom.exe": "Zoom",
            "MSTeams_8wekyb3d8bbwe": "Teams",
            "C:#Program Files#obs-studio#bin#64bit#obs64.exe": None,
            "5319275A.WhatsAppDesktop_cv1g1gvanyjgm": None,
        }
        for key, expected in cases.items():
            self.assertEqual(detect.app_name(key), expected, key)

    def test_detects_only_open_meeting_mic(self):
        packaged = [("MSTeams_8wekyb3d8bbwe", 100, 200)]
        nonpackaged = [("C:#x#obs64.exe", 300, 0), ("C:#x#Zoom.exe", 400, 0)]
        with mock.patch.object(detect, "_entries", side_effect=[iter(packaged), iter(nonpackaged)]):
            self.assertEqual(detect.detected(), {"app": "Zoom", "key": "C:#x#Zoom.exe:400"})

    def test_nothing_open(self):
        with mock.patch.object(detect, "_entries", side_effect=[iter([]), iter([("C:#x#chrome.exe", 1, 2)])]):
            self.assertIsNone(detect.detected())

    def test_browser_needs_a_meeting_window(self):
        entries = [("C:#x#chrome.exe", 500, 0)]
        for titles, expected in [(["WhatsApp Web - Google Chrome"], None), (["Weekly sync - Google Meet - Chrome"], "Chrome")]:
            with self.subTest(titles=titles),                     mock.patch.object(detect, "_entries", side_effect=[iter([]), iter(entries)]),                     mock.patch.object(detect, "window_titles", return_value=titles),                     mock.patch.object(detect.settings, "env", return_value=None):
                result = detect.detected()
                self.assertEqual(result and result["app"], expected)

    def test_keywords_come_from_settings(self):
        with mock.patch.object(detect, "window_titles", return_value=["Standup - Whereby"]):
            with mock.patch.object(detect.settings, "env", return_value=None):
                self.assertFalse(detect.meeting_window())
            with mock.patch.object(detect.settings, "env", return_value="whereby, jitsi"):
                self.assertTrue(detect.meeting_window())

    def test_native_apps_ignore_window_titles(self):
        with mock.patch.object(detect, "_entries", side_effect=[iter([]), iter([("C:#x#Zoom.exe", 400, 0)])]),                 mock.patch.object(detect, "window_titles", return_value=[]):
            self.assertEqual(detect.detected()["app"], "Zoom")

    def test_reads_real_window_titles(self):
        self.assertIsInstance(detect.window_titles(), list)

    def test_reads_real_registry(self):
        result = detect.detected()
        self.assertTrue(result is None or set(result) == {"app", "key"})


if __name__ == "__main__":
    unittest.main()
