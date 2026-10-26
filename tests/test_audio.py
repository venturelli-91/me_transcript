import os
import time
import unittest
import wave
from pathlib import Path
from unittest import mock

from metranscript import enhance, server, store, transcribe
from tests.http_case import ServerCase


def write_wav(path: Path, seconds: float = 1.0) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * int(16000 * seconds))


class AudioStoreTest(ServerCase):
    def meeting(self) -> str:
        return store.create("Kickoff", "en")

    def test_load_reports_whether_audio_is_saved(self):
        mid = self.meeting()
        self.assertFalse(store.load(mid)["has_audio"])
        (store.meeting_dir(mid) / "mic.opus").write_bytes(b"x")
        self.assertTrue(store.load(mid)["has_audio"])

    def test_replace_transcript_keeps_the_previous_one(self):
        mid = self.meeting()
        store.append_segments(mid, [{"t": 1, "who": "Me", "text": "old"}])
        store.replace_transcript(mid, [{"t": 2, "who": "Others", "text": "new"}])
        folder = store.meeting_dir(mid)
        self.assertIn("new", (folder / "transcript.md").read_text(encoding="utf-8"))
        self.assertIn("old", (folder / "transcript.previous.md").read_text(encoding="utf-8"))

    def test_old_audio_expires_and_recent_audio_stays(self):
        old, recent = self.meeting(), store.create("Other", "en")
        for mid, age_days in ((old, 31), (recent, 5)):
            f = store.meeting_dir(mid) / "mic.opus"
            f.write_bytes(b"x")
            when = time.time() - age_days * 86400
            os.utime(f, (when, when))
        (store.meeting_dir(old) / "mic.wav").write_bytes(b"x")  # a WAV means transcription failed: never expired
        store.expire_audio()
        self.assertEqual(sorted(p.name for p in store.meeting_dir(old).glob("mic.*")), ["mic.wav"])
        self.assertTrue((store.meeting_dir(recent) / "mic.opus").exists())


class TranscribeAudioTest(unittest.TestCase):
    def test_to_opus_compresses_speech_next_to_the_wav(self):
        with mock.patch.object(transcribe, "_run", return_value="") as run:
            out = transcribe.to_opus(Path("m/mic.wav"))
        self.assertEqual(out, Path("m/mic.opus"))
        args = run.call_args.args[0]
        self.assertIn("libopus", args)
        self.assertEqual(args[-1], str(Path("m/mic.opus")))

    def test_retranscribe_decodes_the_saved_audio_and_merges_both_tracks(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "mic.opus").write_bytes(b"x")
            (folder / "system.wav").write_bytes(b"x")

            def fake_run(args, timeout):
                write_wav(Path(args[-1]))
                return ""

            def fake_clip(clip, spans, cut, lang, who, offset, prompt):
                return [{"t": 0.5 if who == "Others" else 0.2, "who": who, "text": lang}]

            with mock.patch.object(transcribe, "_run", fake_run), \
                    mock.patch.object(transcribe, "analyze", lambda wav, start, dur, tmp: (tmp / "c.wav", [(0, 1)])), \
                    mock.patch.object(transcribe, "transcribe_clip", fake_clip):
                segments = transcribe.retranscribe(folder, "pt")
        self.assertEqual([(s["who"], s["text"]) for s in segments], [("Me", "pt"), ("Others", "pt")])

    def test_retranscribe_without_audio_says_so(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(RuntimeError, "no saved audio"):
            transcribe.retranscribe(Path(tmp), "en")


class ServerAudioTest(ServerCase):
    def meeting(self, wavs: bool = False) -> str:
        mid = store.create("Kickoff", "en")
        store.append_segments(mid, [{"t": 1, "who": "Me", "text": "old words"}])
        if wavs:
            for track in ("mic", "system"):
                (store.meeting_dir(mid) / f"{track}.wav").write_bytes(b"x")
        return mid

    def test_audio_is_compressed_and_the_wav_removed(self):
        mid = self.meeting(wavs=True)

        def fake(wav):
            wav.with_suffix(".opus").write_bytes(b"o")
            return wav.with_suffix(".opus")

        with mock.patch.object(transcribe, "to_opus", fake):
            server._archive_audio(mid)
        self.assertEqual(sorted(p.name for p in store.meeting_dir(mid).glob("*.*") if p.suffix in (".wav", ".opus")),
                         ["mic.opus", "system.opus"])

    def test_a_failed_compression_keeps_the_wav(self):
        mid = self.meeting(wavs=True)
        with mock.patch.object(transcribe, "to_opus", side_effect=RuntimeError("ffmpeg failed")):
            server._archive_audio(mid)
        self.assertTrue((store.meeting_dir(mid) / "mic.wav").exists())

    def test_retranscribe_replaces_the_transcript_and_regenerates_the_summary(self):
        mid = self.meeting()
        store.save_summary(mid, "## Old")
        new = [{"t": 3, "who": "Others", "text": "better words"}]
        with mock.patch.object(transcribe, "retranscribe", return_value=new), \
                mock.patch.object(enhance, "_complete", return_value="## New"):
            server._retranscribe(mid, "en")
        loaded = store.load(mid)
        self.assertIn("better words", loaded["transcript"])
        self.assertEqual((loaded["summary"], loaded["can_undo"]), ("## New", True))
        self.assertEqual(server.session.phase, "done")

    def test_failed_retranscription_keeps_the_old_transcript(self):
        mid = self.meeting()
        with mock.patch.object(transcribe, "retranscribe", side_effect=RuntimeError("whisper-cli.exe failed")):
            server._retranscribe(mid, "en")
        self.assertIn("old words", store.load(mid)["transcript"])
        self.assertEqual(server.session.phase, "error")
        self.assertIn("previous transcript is untouched", server.session.error)

    def test_route_refuses_a_meeting_without_audio(self):
        mid = self.meeting()
        server._set_phase("idle")
        status, body = self.call("POST", f"/api/meetings/{mid}/retranscribe", {})
        self.assertEqual((status, body["error"]), (409, "This meeting has no saved audio."))


if __name__ == "__main__":
    unittest.main()
