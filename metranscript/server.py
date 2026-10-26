import json
import logging
import os
import re
import secrets
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from metranscript import agenda, desktop, detect, enhance, mail, store
from metranscript.capture import Recorder, list_devices
from metranscript.transcribe import Transcriber, check_ready

log = logging.getLogger("metranscript")
INDEX = Path(__file__).parent / "web" / "index.html"
LANGS = {"pt", "en"}
MAX_BODY = 2_000_000
PORT = int(os.environ.get("ATA_PORT", "8765"))
HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
BUSY = {"recording", "transcribing", "enhancing"}
URL = f"http://127.0.0.1:{PORT}/"
# One-time tokens behind the "Record" button of a reminder; the page can't start a reminder recording without one.
reminder_tokens: dict[str, tuple[str, str | None, float]] = {}
TOKEN_TTL = 1800
watcher: agenda.Watcher | None = None
server: ThreadingHTTPServer | None = None


class Session:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.phase = "idle"
        self.meeting_id: str | None = None
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
                "error": self.error or (self.recorder.warning if self.recorder else None)
                or (self.transcriber.error if self.transcriber else None),
                "devices": dict(self.recorder.devices) if self.recorder else None,
            }
        # Also reported while recording, so the page can mark that mic session as already handled.
        if snap["phase"] not in ("transcribing", "enhancing"):
            snap["detected"] = detect.detected()
        return snap


# ponytail: one global session, one person records one meeting at a time
session = Session()


def on_reminder(event: dict, minutes: int, reminder: int) -> None:
    title, message = desktop.reminder_text(event, minutes)
    action = None
    if reminder == agenda.LAST_REMINDER:
        token = secrets.token_urlsafe(16)
        now = time.time()
        for old in [t for t, (_, _, exp) in reminder_tokens.items() if exp < now]:
            del reminder_tokens[old]
        reminder_tokens[token] = (event["title"], event.get("app"), now + TOKEN_TTL)
        action = ("Record", f"{URL}?record={token}")
    desktop.notify(title, message, URL, action)


def quit_app() -> None:
    with session.lock:
        if session.phase in BUSY:
            raise RuntimeError("Stop the recording and wait for the summary before quitting.")
    threading.Thread(target=server.shutdown, daemon=True).start()


def switch_device(track: str, name: str) -> None:
    with session.lock:
        recorder = session.recorder
    if session.phase != "recording" or recorder is None:
        raise RuntimeError("No recording in progress.")
    recorder.switch(track, name)


MEETING_APPS = {"Meet", "Zoom", "Teams", "Chrome", "Edge", "Firefox", "Brave", "Arc"}


def start(title: str, lang: str, private: bool, mic: str | None = None, speakers: str | None = None,
          app: str | None = None) -> str:
    with session.lock:
        if session.phase == "recording":
            raise RuntimeError("A meeting is already being recorded.")
        if session.phase in BUSY:
            raise RuntimeError("The previous meeting is still being processed. Wait for its summary to be ready.")
        check_ready()
        meeting_id = store.create(title, lang, private, app=app)
        try:
            recorder = Recorder(store.meeting_dir(meeting_id), mic, speakers)
        except Exception as e:
            shutil.rmtree(store.meeting_dir(meeting_id))
            log.exception("Could not open audio")
            raise RuntimeError(f"Could not open the microphone or system audio: {e}") from None
        session.phase, session.meeting_id = "recording", meeting_id
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
        if self.path.split("?", 1)[0] == "/":
            return self._send(200, INDEX.read_bytes(), "text/html")
        if self.path == "/api/agenda":
            return self._send(200, {"configured": bool(agenda.ics_urls()), "events": watcher.events if watcher else [],
                                    "error": watcher.error if watcher else None})
        if self.path == "/api/settings":
            return self._send(200, {"autostart": desktop.autostart_enabled()})
        if self.path == "/api/devices":
            # ponytail: a short-lived PortAudio session on the HTTP thread; fine for listing, never used to record
            return self._guard(lambda: self._send(200, list_devices()))
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
                app = body.get("app")
                reminder = body.get("reminder")
                if reminder is not None:
                    title, reminder_app, expires = reminder_tokens.pop(reminder, ("", None, 0))
                    app = app or reminder_app
                    if expires < time.time():
                        raise ValueError("This reminder link has expired.")
                if lang not in LANGS:
                    raise ValueError("Language must be pt or en.")
                if not isinstance(title, str):
                    raise ValueError("Title must be text.")
                if not isinstance(private, bool):
                    raise ValueError("private must be true or false.")
                mic, speakers = body.get("mic"), body.get("speakers")
                if app is not None and app not in MEETING_APPS:
                    raise ValueError("Unknown meeting app.")
                if not all(d is None or isinstance(d, str) for d in (mic, speakers)):
                    raise ValueError("Device names must be text.")
                self._send(200, {"id": start(title.strip()[:200], lang, private, mic or None, speakers or None, app)})
            return self._guard(run)
        if self.path == "/api/stop":
            return self._guard(lambda: (stop(), self._send(200)))
        if self.path == "/api/devices":
            def run():
                body = self._body()
                track, name = body.get("track"), body.get("name")
                if track not in ("mic", "system") or not isinstance(name, str) or not name:
                    raise ValueError("Send track (mic or system) and a device name.")
                switch_device(track, name)
                self._send(200, session.snapshot()["devices"])
            return self._guard(run)
        if self.path == "/api/quit":
            return self._guard(lambda: (quit_app(), self._send(200)))
        if self.path == "/api/settings":
            def run():
                enabled = self._body().get("autostart")
                if not isinstance(enabled, bool):
                    raise ValueError("autostart must be true or false.")
                try:
                    desktop.set_autostart(enabled)
                except OSError as e:
                    raise RuntimeError(f"Could not change the Windows startup setting: {e}") from None
                self._send(200, {"autostart": desktop.autostart_enabled()})
            return self._guard(run)
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
    global server, watcher
    # pythonw (start with Windows) has no console, so log to a file there.
    logfile = None if sys.stderr else store.ROOT.parent / "metranscript.log"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", filename=logfile)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        log.info("MeTranscript is already running at %s", URL)
        return
    store.ROOT.mkdir(exist_ok=True)
    watcher = agenda.Watcher(store.ROOT / "reminders-sent.json", on_reminder)
    log.info("MeTranscript running at %s", URL)
    server.serve_forever()


if __name__ == "__main__":
    main()
