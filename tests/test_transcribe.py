import unittest
from pathlib import Path
from unittest import mock

from ata import transcribe


def item(start_ms: int, text: str) -> dict:
    return {"offsets": {"from": start_ms, "to": start_ms + 1000}, "text": text}


class TranscribeTest(unittest.TestCase):
    def test_parse_offsets_and_cleans_text(self):
        data = {"transcription": [item(0, " Bom dia,\n pessoal. "), item(4500, " Vamos lá.")]}
        self.assertEqual(transcribe.parse_whisper(data, 60.0, "Eu"), [
            {"t": 60.0, "who": "Eu", "text": "Bom dia, pessoal."},
            {"t": 64.5, "who": "Eu", "text": "Vamos lá."},
        ])

    def test_drops_hallucinations(self):
        data = {"transcription": [item(0, " Legendas pela comunidade Amara.org"), item(1000, " [Música]"),
                                  item(2000, " "), item(3000, " Fechado.")]}
        self.assertEqual([s["text"] for s in transcribe.parse_whisper(data, 0, "Outros")], ["Fechado."])

    def test_speech_spans_from_vad_output(self):
        out = ("Detected 2 speech segments:\n"
               "Speech segment 0: start = 208.00, end = 294.00\n"
               "Speech segment 1: start = 2173.00, end = 3101.00\n")
        self.assertEqual(transcribe.speech_spans(out), [(2.08, 2.94), (21.73, 31.01)])
        self.assertEqual(transcribe.speech_spans("Detected 0 speech segments:\n"), [])

    def test_merge_interleaves_by_time(self):
        me = [{"t": 1.0, "who": "Eu", "text": "a"}, {"t": 9.0, "who": "Eu", "text": "c"}]
        others = [{"t": 5.0, "who": "Outros", "text": "b"}]
        self.assertEqual([s["text"] for s in transcribe.merge(me, others)], ["a", "b", "c"])

    def test_live_failure_resumes_on_finish(self):
        calls, fail = [], [True]

        def fake(wav, start, dur, lang, who):
            calls.append((wav.stem, start))
            if fail[0]:
                raise RuntimeError("whisper-cli.exe falhou")
            return [{"t": start + 1, "who": who, "text": "x"}]

        got = []
        with mock.patch.object(transcribe, "transcribe_window", fake):
            t = transcribe.Transcriber(Path("x"), "pt", recorded=lambda: 40.0, on_segments=got.extend)
            t.thread.join(timeout=5)
            self.assertIn("parou", t.error)
            fail[0] = False
            t.finish(40.0)
        self.assertEqual([s["t"] for s in got if s["who"] == "Eu"], [1.0, 31.0])

    def test_finish_transcribes_remaining_windows(self):
        calls = []
        original = transcribe.transcribe_window
        transcribe.transcribe_window = lambda wav, start, dur, lang, who: calls.append((wav.stem, start, dur)) or []
        try:
            t = transcribe.Transcriber(Path("x"), "pt", recorded=lambda: 0.0, on_segments=lambda s: None)
            t.finish(70.0)
        finally:
            transcribe.transcribe_window = original
        self.assertEqual([c for c in calls if c[0] == "mic"], [("mic", 0.0, 30.0), ("mic", 30.0, 30.0), ("mic", 60.0, 10.0)])


if __name__ == "__main__":
    unittest.main()
