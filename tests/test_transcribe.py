import unittest
from pathlib import Path
from unittest import mock

from metranscript import transcribe


def item(start_ms: int, text: str) -> dict:
    return {"offsets": {"from": start_ms, "to": start_ms + 1000}, "text": text}


class TranscribeTest(unittest.TestCase):
    def test_parse_offsets_and_cleans_text(self):
        data = {"transcription": [item(0, " Good morning,\n everyone. "), item(4500, " Let's start.")]}
        self.assertEqual(transcribe.parse_whisper(data, 60.0, "Me"), [
            {"t": 60.0, "who": "Me", "text": "Good morning, everyone."},
            {"t": 64.5, "who": "Me", "text": "Let's start."},
        ])

    def test_drops_hallucinations(self):
        data = {"transcription": [item(0, " Legendas pela comunidade Amara.org"), item(1000, " [Música]"),
                                  item(2000, " "), item(3000, " Deal.")]}
        self.assertEqual([s["text"] for s in transcribe.parse_whisper(data, 0, "Others")], ["Deal."])

    def test_speech_spans_from_vad_output(self):
        out = ("Detected 2 speech segments:\n"
               "Speech segment 0: start = 208.00, end = 294.00\n"
               "Speech segment 1: start = 2173.00, end = 3101.00\n")
        self.assertEqual(transcribe.speech_spans(out), [(2.08, 2.94), (21.73, 31.01)])
        self.assertEqual(transcribe.speech_spans("Detected 0 speech segments:\n"), [])

    def test_bracketed_noise_is_dropped_without_listing_each_one(self):
        for text in ["[music]", "[Música]", "(música)", "(applause)", "[ Silence ]"]:
            self.assertTrue(transcribe.is_hallucination(text), text)
        self.assertFalse(transcribe.is_hallucination("The [music] plan is ready"))

    def test_merge_interleaves_by_time(self):
        me = [{"t": 1.0, "who": "Me", "text": "a"}, {"t": 9.0, "who": "Me", "text": "c"}]
        others = [{"t": 5.0, "who": "Others", "text": "b"}]
        self.assertEqual([s["text"] for s in transcribe.merge(me, others)], ["a", "b", "c"])

    def test_union_merges_overlapping_speech_of_both_tracks(self):
        self.assertEqual(transcribe.union([(0, 5), (12, 14)], [(4, 8), (10, 12)]), [(0, 8), (10, 14)])
        self.assertEqual(transcribe.union([], []), [])

    def test_pick_cut_ends_the_window_in_the_latest_silence(self):
        self.assertEqual(transcribe.pick_cut([(0, 10), (10.2, 15), (16, 29.9)], 30.0), 15.5)

    def test_pick_cut_keeps_the_full_window_when_there_is_no_usable_silence(self):
        self.assertEqual(transcribe.pick_cut([], 30.0), 30.0)
        self.assertEqual(transcribe.pick_cut([(0, 5), (6, 12)], 30.0), 30.0)      # silent tail already
        self.assertEqual(transcribe.pick_cut([(0, 3), (4, 29.9)], 30.0), 30.0)    # gap too early
        self.assertEqual(transcribe.pick_cut([(0, 29.9)], 30.0), 30.0)            # one long stretch

    def test_vocabulary_lists_the_terms_within_the_limit(self):
        with mock.patch.object(transcribe.privacy, "terms", return_value=["Acme Corp", "Falcon", "x" * 400, "Last"]):
            self.assertEqual(transcribe.vocabulary(), "Acme Corp, Falcon")
        with mock.patch.object(transcribe.privacy, "terms", return_value=[]):
            self.assertEqual(transcribe.vocabulary(), "")

    def test_window_prompt_has_the_vocabulary_and_the_tail_of_the_previous_window(self):
        calls = []

        def fake_clip(clip, spans, cut, lang, who, offset, prompt):
            calls.append((who, offset, cut, prompt))
            return [{"t": offset + 1, "who": who, "text": f"{who} said something about Falcon " * 10}]

        with mock.patch.object(transcribe, "analyze", lambda wav, start, dur, tmp: (tmp / "c.wav", [(0, 10), (10.2, 15), (16, 29.9)])),                 mock.patch.object(transcribe, "transcribe_clip", fake_clip),                 mock.patch.object(transcribe.privacy, "terms", return_value=["Falcon"]):
            t = transcribe.Transcriber(Path("x"), "en", recorded=lambda: 0.0, on_segments=lambda s: None)
            t.finish(55.0)
        me = [c for c in calls if c[0] == "Me"]
        self.assertEqual([c[1:3] for c in me], [(0.0, 15.5), (15.5, 15.5), (31.0, 24.0)])
        intro = "This meeting mentions Falcon."
        self.assertEqual(me[0][3], intro)
        self.assertTrue(me[1][3].startswith(intro + " ") and me[1][3].endswith("Falcon"))
        self.assertLessEqual(len(me[1][3]), len(intro) + 1 + transcribe.TAIL)

    def test_live_failure_resumes_on_finish(self):
        calls, fail = [], [True]

        def fake_clip(clip, spans, cut, lang, who, offset, prompt):
            calls.append((who, offset))
            if fail[0]:
                raise RuntimeError("whisper-cli.exe failed")
            return [{"t": offset + 1, "who": who, "text": "x"}]

        got = []
        with mock.patch.object(transcribe, "analyze", lambda wav, start, dur, tmp: (tmp / "c.wav", [(0, 29.9)])),                 mock.patch.object(transcribe, "transcribe_clip", fake_clip):
            t = transcribe.Transcriber(Path("x"), "pt", recorded=lambda: 40.0, on_segments=got.extend)
            t.thread.join(timeout=5)
            self.assertIn("stopped", t.error)
            fail[0] = False
            t.finish(40.0)
        self.assertEqual([s["t"] for s in got if s["who"] == "Me"], [1.0, 31.0])

    def test_finish_transcribes_remaining_windows(self):
        calls = []
        with mock.patch.object(transcribe, "analyze", lambda wav, start, dur, tmp: (tmp / "c.wav", [(0, dur)])),                 mock.patch.object(transcribe, "transcribe_clip",
                                  lambda clip, spans, cut, lang, who, offset, prompt: calls.append((who, offset, cut)) or []):
            t = transcribe.Transcriber(Path("x"), "pt", recorded=lambda: 0.0, on_segments=lambda s: None)
            t.finish(70.0)
        self.assertEqual([c for c in calls if c[0] == "Me"], [("Me", 0.0, 30.0), ("Me", 30.0, 30.0), ("Me", 60.0, 10.0)])


if __name__ == "__main__":
    unittest.main()
