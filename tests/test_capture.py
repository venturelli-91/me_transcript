import unittest
from array import array

from metranscript.capture import convert_channels


def pcm(*samples: int) -> bytes:
    return array("h", samples).tobytes()


class CaptureTest(unittest.TestCase):
    def test_same_channels_untouched(self):
        data = pcm(1, 2, 3, 4)
        self.assertIs(convert_channels(data, 2, 2), data)

    def test_stereo_to_mono_keeps_first_channel(self):
        self.assertEqual(convert_channels(pcm(10, -10, 20, -20), 2, 1), pcm(10, 20))

    def test_mono_to_stereo_duplicates(self):
        self.assertEqual(convert_channels(pcm(5, 6, 7), 1, 2), pcm(5, 5, 6, 6, 7, 7))


if __name__ == "__main__":
    unittest.main()
