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

    def test_reads_real_registry(self):
        result = detect.detected()
        self.assertTrue(result is None or set(result) == {"app", "key"})


if __name__ == "__main__":
    unittest.main()
