import os
import threading
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

    def test_archive_audio_compresses_by_default_and_keeps_nothing_when_days_is_zero(self):
        for days, compressed in ((None, True), ("30", True), ("0", False), ("²", True)):
            mid = self.meeting()
            wav = store.meeting_dir(mid) / "mic.wav"
            write_wav(wav)
            env = {"AUDIO_KEEP_DAYS": days} if days is not None else {}
            with mock.patch.dict(os.environ, env), mock.patch.object(transcribe, "to_opus") as to_opus:
                if days is None:
                    os.environ.pop("AUDIO_KEEP_DAYS", None)
                server._archive_audio(mid)
            self.assertEqual(to_opus.called, compressed, days)
            self.assertFalse(wav.exists(), days)

    def test_archive_audio_keeps_the_wav_when_compression_fails(self):
        mid = self.meeting()
        wav = store.meeting_dir(mid) / "mic.wav"
        write_wav(wav)
        with mock.patch.object(transcribe, "to_opus", side_effect=RuntimeError("ffmpeg failed")):
            server._archive_audio(mid)
        self.assertTrue(wav.exists())

    def test_retention_pass_skips_only_a_meeting_that_is_being_processed(self):
        with mock.patch.object(store, "expire_audio") as audio, mock.patch.object(store, "expire_meetings") as meetings, \
                mock.patch.dict(os.environ, {"AUDIO_KEEP_DAYS": "7", "MEETING_KEEP_DAYS": "90"}):
            with mock.patch.object(server.session, "jobs", {"m1": {"phase": "error"}}):
                server._retention_pass()
            meetings.assert_called_with(90, skip=set())
            audio.assert_called_with(7)
            with mock.patch.object(server.session, "jobs", {"m1": {"phase": "transcribing"}, "m3": {"phase": "queued"}}), \
                    mock.patch.object(server.session, "phase", "recording"), mock.patch.object(server.session, "meeting_id", "m2"):
                server._retention_pass()
            meetings.assert_called_with(90, skip={"m1", "m2", "m3"})

    def test_retention_pass_survives_a_failing_step_and_does_nothing_without_a_meeting_limit(self):
        with mock.patch.object(store, "expire_audio", side_effect=OSError("disk")), \
                mock.patch.object(store, "expire_meetings") as meetings, mock.patch.dict(os.environ, {"MEETING_KEEP_DAYS": "30"}):
            server._retention_pass()
            meetings.assert_called_once()
        with mock.patch.object(store, "expire_audio"), mock.patch.object(store, "expire_meetings") as meetings:
            os.environ.pop("MEETING_KEEP_DAYS", None)
            server._retention_pass()
            meetings.assert_not_called()

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

    def test_an_empty_re_transcription_never_replaces_the_transcript(self):
        mid = self.meeting()
        store.append_segments(mid, [{"t": 1, "who": "Me", "text": "keep me"}])
        with self.assertRaises(RuntimeError):
            store.replace_transcript(mid, [])
        self.assertIn("keep me", store.load(mid)["transcript"])

    def test_a_locked_audio_file_does_not_stop_the_app_from_starting(self):
        mid = self.meeting()
        f = store.meeting_dir(mid) / "mic.opus"
        f.write_bytes(b"x")
        os.utime(f, (0, 0))
        with mock.patch.object(Path, "unlink", side_effect=PermissionError("in use")):
            store.expire_audio()

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
        self.assertNotIn(mid, server.session.jobs)

    def test_failed_retranscription_keeps_the_old_transcript(self):
        mid = self.meeting()
        with mock.patch.object(transcribe, "retranscribe", side_effect=RuntimeError("whisper-cli.exe failed")):
            server._retranscribe(mid, "en")
        self.assertIn("old words", store.load(mid)["transcript"])
        self.assertEqual(server.session.jobs[mid]["phase"], "error")
        self.assertIn("previous transcript is untouched", server.session.jobs[mid]["error"])

    def test_route_refuses_a_meeting_without_audio(self):
        mid = self.meeting()
        status, body = self.call("POST", f"/api/meetings/{mid}/retranscribe", {})
        self.assertEqual((status, body["error"]), (409, "This meeting has no saved audio."))

    def test_stop_moves_the_meeting_to_a_job_and_frees_the_session_for_the_next_recording(self):
        prev = self.meeting()
        with mock.patch.object(server.session, "jobs", {}), mock.patch.object(server.session, "phase", "recording"), \
                mock.patch.object(server.session, "meeting_id", prev), mock.patch.object(server.session, "recorder", mock.Mock()), \
                mock.patch.object(server, "_finalize"), mock.patch.object(server, "check_ready"), \
                mock.patch.object(server, "Recorder"):
            server.stop()
            self.assertEqual((server.session.phase, server.session.jobs[prev]["phase"]), ("idle", "queued"))
            nxt = server.start("Next", "en", False)
            self.assertEqual((server.session.phase, server.session.meeting_id), ("recording", nxt))
            self.assertIn(prev, server.session.jobs)

    def test_a_finished_background_job_notifies_silently_only_while_recording(self):
        mid = self.meeting()
        for phase, notified in (("recording", True), ("idle", False)):
            with mock.patch.object(server.session, "jobs", {mid: {"phase": "enhancing"}}), \
                    mock.patch.object(server.session, "phase", phase), mock.patch.object(server.desktop, "notify") as notify:
                server._set_phase(mid, "done")
            self.assertEqual(notify.called, notified, phase)
        self.assertEqual(notify.call_args, None)
        with mock.patch.object(server.session, "jobs", {}), mock.patch.object(server.session, "phase", "recording"), \
                mock.patch.object(server.desktop, "notify") as notify:
            server._set_phase(mid, "error", "boom")
        title, message, url = notify.call_args.args
        self.assertEqual((title, message, url), ("Kickoff", "Processing failed. Open it to see why.", f"{server.URL}#/m/{mid}"))
        self.assertTrue(notify.call_args.kwargs["silent"])

    def test_a_queued_job_waits_for_the_running_transcription_then_finishes(self):
        mid = self.meeting()
        job = {"phase": "queued", "progress": None, "error": None}
        with mock.patch.object(server.session, "jobs", {mid: job}), \
                mock.patch.object(transcribe, "retranscribe", return_value=[{"t": 3, "who": "Others", "text": "words"}]), \
                mock.patch.object(enhance, "_complete", return_value="## New"):
            with server._transcribe_lock:
                worker = threading.Thread(target=server._retranscribe, args=(mid, "en"))
                worker.start()
                time.sleep(0.2)
                self.assertEqual(server.session.jobs[mid]["phase"], "queued")
            worker.join(5)
            self.assertNotIn(mid, server.session.jobs)


if __name__ == "__main__":
    unittest.main()
