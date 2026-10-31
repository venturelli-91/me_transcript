import unittest
from array import array
from unittest import mock

from metranscript.capture import Recorder, convert_channels


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


class FakeStream:
    def __init__(self):
        self.closed = False

    def stop_stream(self):
        pass

    def close(self):
        self.closed = True


class PauseTest(unittest.TestCase):
    def setUp(self):
        self.rec = object.__new__(Recorder)
        self.rec.t0, self.rec.paused_at, self.rec._paused_total = 100.0, None, 0.0
        self.rec.streams = {"mic": FakeStream(), "system": FakeStream()}
        self.rec.tracks = {"mic": None, "system": None}
        self.rec.devices = {"mic": "Mic", "system": "Speakers"}
        self.clock = mock.patch("metranscript.capture.time.monotonic", return_value=110.0)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_pause_closes_streams_and_freezes_the_clock(self):
        streams = list(self.rec.streams.values())
        self.rec._pause()
        self.assertTrue(all(s.closed for s in streams))
        self.assertEqual(self.rec.streams, {})
        self.now.return_value = 150.0
        self.assertEqual(self.rec.elapsed(), 10.0)

    def test_resume_reattaches_and_leaves_out_the_paused_time(self):
        self.rec._pause()
        self.now.return_value = 140.0
        with mock.patch.object(self.rec, "_find", side_effect=lambda track, name: (track, name)), \
                mock.patch.object(self.rec, "_attach") as attach:
            self.rec._resume()
        attach.assert_has_calls([mock.call("mic", ("mic", "Mic")), mock.call("system", ("system", "Speakers"))])
        self.assertIsNone(self.rec.paused_at)
        self.now.return_value = 145.0
        self.assertEqual(self.rec.elapsed(), 15.0)

    def test_pause_and_resume_twice_do_nothing(self):
        self.rec._resume()
        self.assertIsNone(self.rec.paused_at)
        self.rec._pause()
        frozen = self.rec.paused_at
        self.now.return_value = 120.0
        self.rec._pause()
        self.assertEqual(self.rec.paused_at, frozen)

    def test_failed_resume_stays_paused(self):
        self.rec._pause()
        self.now.return_value = 140.0
        with mock.patch.object(self.rec, "_find", side_effect=RuntimeError("Device not found: Mic.")):
            with self.assertRaises(RuntimeError):
                self.rec._resume()
        self.assertEqual(self.rec.paused_at, 110.0)
        self.assertEqual(self.rec._paused_total, 0.0)
        self.assertEqual(self.rec.elapsed(), 10.0)

    def test_no_padding_while_paused(self):
        self.rec._pause()
        self.rec.tracks = {"system": mock.Mock()}
        self.rec._pad_and_check()
        self.rec.tracks["system"].pad_to.assert_not_called()


if __name__ == "__main__":
    unittest.main()
