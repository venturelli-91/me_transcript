import json
import logging
import os
import re
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from metranscript import detect, enhance, mail, store
from metranscript.capture import Recorder
from metranscript.transcribe import Transcriber, check_ready

log = logging.getLogger("metranscript")
INDEX = Path(__file__).parent / "web" / "index.html"
LANGS = {"pt", "en"}
MAX_BODY = 2_000_000
PORT = int(os.environ.get("ATA_PORT", "8765"))
HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
BUSY = {"recording", "transcribing", "enhancing"}


class Session:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.phase = "idle"
        self.meeting_id: str | None = None
        self.lang = "pt"
        self.recorder: Recorder | None = None
        self.transcriber: Transcriber | None = None
        self.segments: list[dict] = []
        self.error: str | None = None

    def snapshot(self) -> dict:
        with self.lock:
            snap = {
                "phase": self.phase,
                "meeting_id": self.meeting_id,
                "elapsed": self.recorder.elapsed() if self.recorder else 0,
                "levels": self.recorder.levels() if self.recorder else {"mic": 0.0, "system": 0.0},
                # ponytail: full segment list every poll, fine for a few hours of meeting
                "segments": list(self.segments),
                "detected": None,
                "error": self.error or (self.transcriber.error if self.transcriber else None),
            }
        # Also reported while recording, so the page can mark that mic session as already handled.
        if snap["phase"] not in ("transcribing", "enhancing"):
            snap["detected"] = detect.detected()
        return snap


# ponytail: one global session, one person records one meeting at a time
session = Session()


def start(title: str, lang: str, private: bool) -> str:
    with session.lock:
        if session.phase == "recording":
            raise RuntimeError("A meeting is already being recorded.")
        if session.phase in BUSY:
            raise RuntimeError("The previous meeting is still being processed. Wait for its summary to be ready.")
        check_ready()
        meeting_id = store.create(title, lang, private)
        try:
            recorder = Recorder(store.meeting_dir(meeting_id))
        except Exception as e:
            shutil.rmtree(store.meeting_dir(meeting_id))
            log.exception("Could not open audio")
            raise RuntimeError(f"Could not open the microphone or system audio: {e}") from None
        session.phase, session.meeting_id, session.lang = "recording", meeting_id, lang
        session.recorder, session.segments, session.error = recorder, [], None
        # 1 s margin: the newest audio may still be in the WAV writer's buffer
        session.transcriber = Transcriber(store.meeting_dir(meeting_id), lang, lambda: recorder.elapsed() - 1.0,
                                          lambda segs: _add_segments(meeting_id, segs))
    return meeting_id


def _add_segments(meeting_id: str, segments: list[dict]) -> None:
    store.append_segments(meeting_id, segments)
    with session.lock:
        session.segments.extend(segments)


def stop() -> None:
    with session.lock:
        if session.phase != "recording":
            raise RuntimeError("No recording in progress.")
        session.phase = "transcribing"
        meeting_id, recorder, transcriber = session.meeting_id, session.recorder, session.transcriber
        session.recorder = session.transcriber = None
    threading.Thread(target=_finalize, args=(meeting_id, recorder, transcriber), daemon=True).start()


def _finalize(meeting_id: str, recorder: Recorder, transcriber: Transcriber) -> None:
    try:
        end = recorder.stop()
        store.finish(meeting_id)
        transcriber.finish(end)
    except Exception as e:
        log.exception("Could not finish %s", meeting_id)
        return _set_phase("error", f"Transcription did not finish ({e}). Audio and notes are saved in the meeting folder.")
    try:
        store.delete_audio(meeting_id)
    except OSError:
        log.warning("Could not delete audio of %s (file in use?)", meeting_id)
    meeting = store.load(meeting_id)
    if meeting.get("private"):
        return _set_phase("done")
    _set_phase("enhancing")
    try:
        store.save_summary(meeting_id, enhance.summarize(meeting))
    except Exception as e:
        log.exception("Could not summarize %s", meeting_id)
        return _set_phase("error", f"Summary not generated: {e} The transcript is saved; use Generate summary.")
    # Still "enhancing" while sending, so a manual click can't race the automatic email.
    _auto_email(meeting_id)
    _set_phase("done")


def _auto_email(meeting_id: str) -> None:
    meeting = store.load(meeting_id)
    if not mail.configured() or meeting.get("private") or not meeting["summary"] or meeting.get("emailed_at"):
        return
    try:
        mail.send(meeting)
    except RuntimeError as e:
        log.warning("Email for %s not sent: %s", meeting_id, e)
        return store.set_email_status(meeting_id, str(e))
    store.set_email_status(meeting_id)


def _set_phase(phase: str, error: str | None = None) -> None:
    with session.lock:
        session.phase, session.error = phase, error


def _sendable(meeting_id: str) -> dict:
    with session.lock:
        if session.meeting_id == meeting_id and session.phase in BUSY:
            raise RuntimeError("Wait: this meeting is still being recorded, transcribed or summarized.")
    meeting = store.load(meeting_id)
    if meeting.get("private"):
        raise RuntimeError("Private meeting: nothing from it is sent to the AI or by email.")
    return meeting


def summarize(meeting_id: str) -> dict:
    store.save_summary(meeting_id, enhance.summarize(_sendable(meeting_id)))
    _auto_email(meeting_id)
    return load(meeting_id)


def email(meeting_id: str) -> dict:
    meeting = _sendable(meeting_id)
    if not meeting["summary"]:
        raise RuntimeError("Generate the summary before emailing it.")
    try:
        mail.send(meeting)
    except RuntimeError as e:
        store.set_email_status(meeting_id, str(e))
        raise
    store.set_email_status(meeting_id)
    return load(meeting_id)


def load(meeting_id: str) -> dict:
    return {**store.load(meeting_id), "email_configured": mail.configured()}


def chat(meeting_id: str, message: str) -> dict:
    result = enhance.chat(_sendable(meeting_id), message)
    if result["summary"]:
        store.save_summary(meeting_id, result["summary"])
    store.append_chat(meeting_id, {"role": "user", "content": message},
                      {"role": "assistant", "content": result["reply"], "changed_summary": bool(result["summary"])})
    return load(meeting_id)


def undo(meeting_id: str) -> dict:
    store.undo_summary(meeting_id)
    return load(meeting_id)


MEETING_RE = re.compile(r"/api/meetings/([^/]+)(/notes|/summary|/chat|/undo|/email)?")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        log.debug(fmt, *args)

    def _send(self, status: int, body: object = None, content_type: str = "application/json") -> None:
        data = body if isinstance(body, bytes) else json.dumps(body if body is not None else {}, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 <= length <= MAX_BODY:
            raise ValueError("Invalid body size.")
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON.") from None
        if not isinstance(data, dict):
            raise ValueError("JSON must be an object.")
        return data

    def _trusted(self, write: bool) -> bool:
        # Blocks DNS rebinding (Host) and cross-site form posts (JSON forces a CORS preflight we never answer).
        if self.headers.get("Host") not in HOSTS:
            self._send(403, {"error": "Host not allowed."})
            return False
        if write and self.headers.get_content_type() != "application/json":
            self._send(415, {"error": "Use Content-Type: application/json."})
            return False
        return True

    def do_GET(self) -> None:
        if not self._trusted(write=False):
            return
        if self.path == "/":
            return self._send(200, INDEX.read_bytes(), "text/html")
        if self.path == "/api/status":
            return self._send(200, session.snapshot())
        if self.path == "/api/meetings":
            return self._send(200, store.list_meetings())
        m = MEETING_RE.fullmatch(self.path)
        if m and not m.group(2):
            return self._guard(lambda: self._send(200, load(m.group(1))))
        self._send(404, {"error": "Not found."})

    def do_POST(self) -> None:
        if not self._trusted(write=True):
            return
        if self.path == "/api/start":
            def run():
                body = self._body()
                lang = body.get("lang", "pt")
                title = body.get("title", "")
                private = body.get("private", False)
                if lang not in LANGS:
                    raise ValueError("Language must be pt or en.")
                if not isinstance(title, str):
                    raise ValueError("Title must be text.")
                if not isinstance(private, bool):
                    raise ValueError("private must be true or false.")
                self._send(200, {"id": start(title.strip()[:200], lang, private)})
            return self._guard(run)
        if self.path == "/api/stop":
            return self._guard(lambda: (stop(), self._send(200)))
        m = MEETING_RE.fullmatch(self.path)
        if m and m.group(2) == "/summary":
            return self._guard(lambda: self._send(200, summarize(m.group(1))))
        if m and m.group(2) == "/email":
            return self._guard(lambda: self._send(200, email(m.group(1))))
        if m and m.group(2) == "/undo":
            return self._guard(lambda: self._send(200, undo(m.group(1))))
        if m and m.group(2) == "/chat":
            def run():
                message = self._body().get("message")
                if not isinstance(message, str) or not message.strip() or len(message) > 4000:
                    raise ValueError("Write a message of up to 4000 characters.")
                self._send(200, chat(m.group(1), message.strip()))
            return self._guard(run)
        self._send(404, {"error": "Not found."})

    def do_PUT(self) -> None:
        if not self._trusted(write=True):
            return
        m = MEETING_RE.fullmatch(self.path)
        if m and m.group(2) == "/notes":
            def run():
                notes = self._body().get("notes")
                if not isinstance(notes, str):
                    raise ValueError("notes must be text.")
                store.save_notes(m.group(1), notes)
                self._send(200)
            return self._guard(run)
        self._send(404, {"error": "Not found."})

    def _guard(self, fn) -> None:
        try:
            fn()
        except KeyError:
            self._send(404, {"error": "Meeting not found."})
        except RuntimeError as e:
            self._send(409, {"error": str(e)})
        except ValueError as e:
            self._send(400, {"error": str(e)})


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    log.info("MeTranscript running at http://127.0.0.1:%d", PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
