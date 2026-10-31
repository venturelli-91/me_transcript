import json
import logging
import os
import re
import secrets
import shutil
import sys
import threading
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from metranscript import agenda, desktop, detect, enhance, google, mail, privacy, report, settings, store, transcribe
from metranscript.capture import Recorder, list_devices
from metranscript.transcribe import Transcriber, check_ready

log = logging.getLogger("metranscript")
INDEX = Path(__file__).parent / "web" / "index.html"
FONTS = INDEX.parent / "fonts"
ABOUT = INDEX.parent / "about"
POLICIES = {"en": "PRIVACY.md", "pt": "PRIVACY.pt.md"}
LANGS = {"pt", "en", "auto"}
MAX_BODY = 2_000_000
PORT = int(os.environ.get("ATA_PORT", "8765"))
HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
PROCESSING = {"queued", "transcribing", "enhancing"}
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
        self.error: str | None = None
        # Meetings after the recording stopped: {id: {"phase": queued|transcribing|enhancing|error, "progress", "error"}}
        self.jobs: dict[str, dict] = {}

    def snapshot(self) -> dict:
        with self.lock:
            snap = {
                "phase": self.phase,
                "meeting_id": self.meeting_id,
                "elapsed": self.recorder.elapsed() if self.recorder else 0,
                "levels": self.recorder.levels() if self.recorder else {"mic": 0.0, "system": 0.0},
                "jobs": {meeting_id: dict(job) for meeting_id, job in self.jobs.items()},
                "error": self.error or (self.recorder.warning if self.recorder else None),
                "devices": dict(self.recorder.devices) if self.recorder else None,
            }
        # Also reported while recording, so the page can mark that mic session as already handled.
        snap["detected"] = detect.detected()
        return snap


# ponytail: one recording at a time; finished recordings are processed in the background by `jobs`
session = Session()
# One whisper run at a time: it is GPU/CPU heavy and must not starve a recording in progress.
_transcribe_lock = threading.Lock()


def _live_ids() -> set[str]:
    """Meetings being recorded or processed; the caller holds session.lock."""
    live = {meeting_id for meeting_id, job in session.jobs.items() if job["phase"] in PROCESSING}
    if session.phase == "recording":
        live.add(session.meeting_id)
    return live


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
        if _live_ids():
            raise RuntimeError("Stop the recording and wait for the summary before quitting.")
    threading.Thread(target=server.shutdown, daemon=True).start()


def switch_device(track: str, name: str) -> None:
    with session.lock:
        recorder = session.recorder if session.phase == "recording" else None
    if recorder is None:
        raise RuntimeError("No recording in progress.")
    recorder.switch(track, name)


MEETING_APPS = {*detect.EXES.values(), *agenda.APPS.values()}


def start(title: str, lang: str, private: bool, mic: str | None = None, speakers: str | None = None,
          app: str | None = None, consented: bool = False) -> str:
    with session.lock:
        if session.phase == "recording":
            raise RuntimeError("A meeting is already being recorded.")
        check_ready()
        meeting_id = store.create(title, lang, private, app=app, consented=consented)
        try:
            recorder = Recorder(store.meeting_dir(meeting_id), mic, speakers)
        except Exception as e:
            shutil.rmtree(store.meeting_dir(meeting_id))
            log.exception("Could not open audio")
            raise RuntimeError(f"Could not open the microphone or system audio: {e}") from None
        session.phase, session.meeting_id = "recording", meeting_id
        session.recorder, session.error = recorder, None
    return meeting_id


def stop() -> None:
    with session.lock:
        if session.phase != "recording":
            raise RuntimeError("No recording in progress.")
        meeting_id, recorder = session.meeting_id, session.recorder
        session.phase, session.meeting_id, session.recorder = "idle", None, None
        session.jobs[meeting_id] = {"phase": "queued", "progress": None, "error": None}
    threading.Thread(target=_finalize, args=(meeting_id, recorder), daemon=True).start()


def _set_progress(meeting_id: str, share: float) -> None:
    with session.lock:
        session.jobs[meeting_id]["progress"] = share


def _finalize(meeting_id: str, recorder: Recorder) -> None:
    try:
        end = recorder.stop()
        store.finish(meeting_id)
        with _transcribe_lock:
            _set_phase(meeting_id, "transcribing")
            transcriber = Transcriber(store.meeting_dir(meeting_id), store.load(meeting_id)["lang"],
                                      lambda segs: store.append_segments(meeting_id, segs),
                                      lambda share: _set_progress(meeting_id, share))
            transcriber.finish(end)
        if transcriber.skipped:
            log.warning("%s: %d window(s) could not be transcribed", meeting_id, transcriber.skipped)
    except Exception as e:
        log.exception("Could not finish %s", meeting_id)
        return _set_phase(meeting_id, "error", f"Transcription did not finish ({e}). Audio and notes are saved in the meeting folder.")
    _archive_audio(meeting_id)
    _summarize_and_finish(meeting_id)


def _archive_audio(meeting_id: str) -> None:
    """Keep the audio as small Opus files (they expire, see store.expire_audio); a failed encode keeps the WAV.
    AUDIO_KEEP_DAYS=0 keeps no audio at all once the transcript is done."""
    folder = store.meeting_dir(meeting_id)
    keep = settings.days("AUDIO_KEEP_DAYS", store.AUDIO_KEEP_DAYS) > 0
    for track in store.TRACKS:
        wav = folder / f"{track}.wav"
        try:
            if wav.exists():
                if keep:
                    transcribe.to_opus(wav)
                wav.unlink()
        except (RuntimeError, OSError) as e:
            log.warning("Could not compress the audio of %s (%s); the WAV stays", meeting_id, e)


def _summarize_and_finish(meeting_id: str) -> None:
    meeting = store.load(meeting_id)
    if meeting.get("private"):
        return _set_phase(meeting_id, "done")
    _set_phase(meeting_id, "enhancing")
    try:
        store.save_summary(meeting_id, _summary(meeting_id, meeting))
    except Exception as e:
        log.exception("Could not summarize %s", meeting_id)
        return _set_phase(meeting_id, "error", f"Summary not generated: {e} The transcript is saved; use Generate summary.")
    # Still "enhancing" while sending, so a manual click can't race the automatic email.
    _auto_email(meeting_id)
    _set_phase(meeting_id, "done")


def retranscribe(meeting_id: str) -> None:
    with session.lock:
        if meeting_id in _live_ids():
            raise RuntimeError("Wait until this meeting is processed.")
        meeting = store.load(meeting_id)
        if not meeting["has_audio"]:
            raise RuntimeError("This meeting has no saved audio.")
        check_ready()
        session.jobs[meeting_id] = {"phase": "queued", "progress": None, "error": None}
    threading.Thread(target=_retranscribe, args=(meeting_id, meeting["lang"]), daemon=True).start()


def _retranscribe(meeting_id: str, lang: str) -> None:
    try:
        with _transcribe_lock:
            _set_phase(meeting_id, "transcribing")
            store.replace_transcript(meeting_id, transcribe.retranscribe(
                store.meeting_dir(meeting_id), lang, lambda share: _set_progress(meeting_id, share)))
    except Exception as e:
        log.exception("Could not re-transcribe %s", meeting_id)
        return _set_phase(meeting_id, "error", f"Re-transcription failed ({e}). The previous transcript is untouched.")
    _summarize_and_finish(meeting_id)


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


def _notify_done(meeting_id: str, failed: bool) -> None:
    meeting = store.load(meeting_id)
    message = "Processing failed. Open it to see why." if failed else "Transcript ready." if meeting.get("private") else "Summary ready."
    desktop.notify(meeting.get("title") or "Meeting", message, f"{URL}#/m/{meeting_id}", silent=True)


def _set_phase(meeting_id: str, phase: str, error: str | None = None) -> None:
    with session.lock:
        if phase == "done":
            session.jobs.pop(meeting_id, None)
        else:
            session.jobs[meeting_id] = {"phase": phase, "progress": 0.0 if phase == "transcribing" else None, "error": error}
        recording = session.phase == "recording"
    # Only while another meeting is being recorded: otherwise the page itself shows the result.
    if recording and phase in ("done", "error"):
        _notify_done(meeting_id, phase == "error")


def _sendable(meeting_id: str) -> dict:
    with session.lock:
        if meeting_id in _live_ids():
            raise RuntimeError("Wait: this meeting is still being recorded, transcribed or summarized.")
    meeting = store.load(meeting_id)
    if meeting.get("private"):
        raise RuntimeError("Private meeting: nothing from it is sent to the AI or by email.")
    return meeting


def _summary(meeting_id: str, meeting: dict) -> str:
    mask = privacy.Mask()
    text = enhance.summarize(meeting, mask)
    store.set_protected(meeting_id, len(mask))
    return text


def summarize(meeting_id: str) -> dict:
    store.save_summary(meeting_id, _summary(meeting_id, _sendable(meeting_id)))
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


def download_report(meeting_id: str, kind: str) -> tuple[bytes, str, str]:
    meeting = store.load(meeting_id)
    if not meeting["summary"].strip():
        raise ValueError("There is no summary to download yet.")
    if kind == "md":
        return report.markdown(meeting).encode(), "text/markdown", report.filename(meeting, "md")
    return report.pdf(meeting), "application/pdf", report.filename(meeting, "pdf")


def chat(meeting_id: str, message: str) -> dict:
    mask = privacy.Mask()
    result = enhance.chat(_sendable(meeting_id), message, mask)
    store.set_protected(meeting_id, len(mask))
    if result["summary"]:
        store.save_summary(meeting_id, result["summary"])
    store.append_chat(meeting_id, {"role": "user", "content": message},
                      {"role": "assistant", "content": result["reply"], "changed_summary": bool(result["summary"])})
    return load(meeting_id)


def rename_meeting(meeting_id: str, title: str) -> dict:
    store.rename(meeting_id, title)
    return load(meeting_id)


def delete_meeting(meeting_id: str) -> None:
    with session.lock:
        if meeting_id in _live_ids():
            raise RuntimeError("Stop the recording and wait for the summary before deleting this meeting.")
        session.jobs.pop(meeting_id, None)
    store.delete(meeting_id)


def save_config(updates: dict) -> dict:
    """Validate everything first, then write once; secret values never leave this function."""
    clean = {}
    for name, value in updates.items():
        if name not in settings.FIELDS:
            raise ValueError("Unknown setting.")
        if value is not None and not isinstance(value, str):
            raise ValueError("Each value must be text or null.")
        if os.environ.get(name):
            raise RuntimeError(f"{name} is set as a Windows environment variable, which overrides this page.")
        clean[name] = None if value is None else settings.validate(name, value)
    if clean:
        try:
            settings.write_env(clean)
        except OSError:
            raise RuntimeError("Could not save the .env file.") from None
    if any(name.startswith("GOOGLE_") for name in clean):
        _refresh_agenda()
    return settings.status()


def send_test_email() -> None:
    mail.send({"title": "MeTranscript test email", "started_at": datetime.now().isoformat(timespec="seconds"),
               "summary": "If you can read this, MeTranscript can email your summaries.", "transcript": ""})


def undo(meeting_id: str) -> dict:
    store.undo_summary(meeting_id)
    return load(meeting_id)


MEETING_RE = re.compile(r"/api/meetings/([^/]+)(/notes|/title|/summary|/chat|/pin|/archive|/undo|/email|/retranscribe|/report\.md|/report\.pdf)?")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        log.debug(fmt, *args)

    def handle_one_request(self) -> None:
        self._consumed = False
        super().handle_one_request()

    def _drain(self) -> None:
        """Read a request body nobody asked for. Answering and closing with unread data makes Windows reset the connection,
        and the client sees an error instead of the 403, 404 or 415 we sent."""
        self._consumed = True
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return
        if 0 < length <= MAX_BODY:
            self.rfile.read(length)

    def _send(self, status: int, body: object = None, content_type: str = "application/json", filename: str | None = None) -> None:
        if self.command in ("POST", "PUT", "PATCH", "DELETE") and not self._consumed:
            self._drain()
        data = body if isinstance(body, bytes) else json.dumps(body if body is not None else {}, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type if content_type == "application/pdf" else f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _body(self) -> dict:
        self._consumed = True
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
        path = self.path.split("?", 1)[0]
        if self.path.split("?", 1)[0] == "/oauth/google":
            return self._redirect(f"/?google={_google_outcome(urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query))}#/settings")
        font = FONTS / path.removeprefix("/fonts/") if path.startswith("/fonts/") else None
        if font and font.parent == FONTS and font.suffix == ".woff2" and font.is_file():
            return self._send(200, font.read_bytes(), "font/woff2")
        image = ABOUT / path.removeprefix("/about/") if path.startswith("/about/") else None
        if image and image.parent == ABOUT and image.suffix == ".png" and image.is_file():
            return self._send(200, image.read_bytes(), "image/png")
        if path == "/api/policy":
            lang = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("lang", ["en"])[0]
            file = INDEX.parent.parent.parent / POLICIES.get(lang, POLICIES["en"])
            if not file.is_file():
                file = INDEX.parent.parent.parent / POLICIES["en"]
            return self._guard(lambda: self._send(200, {"markdown": file.read_text(encoding="utf-8")}))
        if self.path == "/api/agenda":
            return self._send(200, {"configured": bool(google.emails()), "events": watcher.events if watcher else [],
                                    "error": watcher.error if watcher else None})
        if self.path == "/api/settings":
            return self._send(200, {"autostart": desktop.autostart_enabled()})
        if self.path == "/api/devices":
            # ponytail: a short-lived PortAudio session on the HTTP thread; fine for listing, never used to record
            return self._guard(lambda: self._send(200, list_devices()))
        if self.path == "/api/config":
            return self._send(200, settings.status())
        if self.path == "/api/privacy":
            return self._send(200, {"terms": privacy.terms()})
        if self.path == "/api/google":
            return self._send(200, {"configured": google.configured(), "accounts": google.accounts()})
        if self.path == "/api/status":
            return self._send(200, session.snapshot())
        if self.path == "/api/meetings":
            return self._send(200, store.list_meetings())
        m = MEETING_RE.fullmatch(self.path)
        if m and m.group(2) in ("/report.md", "/report.pdf"):
            def run():
                data, ctype, name = download_report(m.group(1), "pdf" if m.group(2).endswith("pdf") else "md")
                self._send(200, data, ctype, name)
            return self._guard(run)
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
                    token_title, reminder_app, expires = reminder_tokens.get(reminder, ("", None, 0))
                    if expires < time.time():
                        raise ValueError("This reminder link has expired.")
                    app = app or reminder_app
                    if not (isinstance(title, str) and title.strip()):
                        title = token_title
                if lang not in LANGS:
                    raise ValueError("Language must be pt, en or auto.")
                if not isinstance(title, str):
                    raise ValueError("Title must be text.")
                if not isinstance(private, bool):
                    raise ValueError("private must be true or false.")
                mic, speakers = body.get("mic"), body.get("speakers")
                if app is not None and app not in MEETING_APPS:
                    raise ValueError("Unknown meeting app.")
                if not all(d is None or isinstance(d, str) for d in (mic, speakers)):
                    raise ValueError("Device names must be text.")
                if body.get("consent") is not True:
                    raise ValueError("Confirm that you told the participants this meeting is being recorded.")
                meeting_id = start(title.strip()[:200], lang, private, mic or None, speakers or None, app, True)
                reminder_tokens.pop(reminder, None)  # only a recording that really started uses up the one-time token
                self._send(200, {"id": meeting_id})
            return self._guard(run)
        if self.path == "/api/stop":
            return self._guard(lambda: (stop(), self._send(200)))
        if self.path == "/api/google/login":
            return self._guard(lambda: self._send(200, {"url": google.start_login(PORT)}))
        if self.path in ("/api/google/sender", "/api/google/disconnect"):
            def run():
                email = self._body().get("email")
                if not isinstance(email, str):
                    raise ValueError("email must be text.")
                revoked = True
                if self.path.endswith("sender"):
                    google.set_sender(email)
                else:
                    revoked = google.disconnect(email)
                    _refresh_agenda()
                self._send(200, {"accounts": google.accounts(), "revoked": revoked})
            return self._guard(run)
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
        if self.path == "/api/config/test-email":
            return self._guard(lambda: (send_test_email(), self._send(200)))
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
        if m and m.group(2) == "/retranscribe":
            return self._guard(lambda: (retranscribe(m.group(1)), self._send(200)))
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

    def do_DELETE(self) -> None:
        if not self._trusted(write=True):
            return
        m = MEETING_RE.fullmatch(self.path)
        if m and not m.group(2):
            return self._guard(lambda: (delete_meeting(m.group(1)), self._send(200)))
        if m and m.group(2) == "/chat":
            return self._guard(lambda: (store.clear_chat(m.group(1)), self._send(200, load(m.group(1)))))
        self._send(404, {"error": "Not found."})

    def do_PUT(self) -> None:
        if not self._trusted(write=True):
            return
        if self.path == "/api/config":
            return self._guard(lambda: self._send(200, save_config(self._body())))
        if self.path == "/api/privacy":
            def run():
                text = self._body().get("terms")
                if not isinstance(text, str):
                    raise ValueError("terms must be text, one term per line.")
                self._send(200, {"terms": privacy.save_terms(text)})
            return self._guard(run)
        m = MEETING_RE.fullmatch(self.path)
        if m and m.group(2) == "/title":
            def run():
                title = self._body().get("title")
                if not isinstance(title, str):
                    raise ValueError("Title must be text.")
                self._send(200, rename_meeting(m.group(1), title))
            return self._guard(run)
        if m and m.group(2) in ("/pin", "/archive"):
            def run():
                flag = {"/pin": "pinned", "/archive": "archived"}[m.group(2)]
                value = self._body().get(flag)
                if not isinstance(value, bool):
                    raise ValueError(f"{flag} must be true or false.")
                store.set_flag(m.group(1), flag, value)
                self._send(200, load(m.group(1)))
            return self._guard(run)
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


def _refresh_agenda() -> None:
    """Read the calendars on the watcher's next pass instead of in up to 5 minutes."""
    if watcher:
        watcher.last_fetch = None


def _google_outcome(query: dict) -> str:
    """What the page should tell the user after Google sent them back here; the details go to the log, never to the URL."""
    one = lambda key: query.get(key, [""])[0]
    if one("error"):
        return "denied" if one("error") == "access_denied" else "error"
    try:
        google.finish_login(PORT, one("code"), one("state"))
    except (RuntimeError, OSError, ValueError) as e:
        log.warning("Google sign-in failed: %s", type(e).__name__ if not isinstance(e, RuntimeError) else e)
        return "error"
    _refresh_agenda()
    return "connected"


def _retention_pass() -> None:
    """Expire old audio and, if set, old meetings; a meeting being recorded or processed is left alone."""
    with session.lock:
        live = _live_ids()
    try:
        store.expire_audio(settings.days("AUDIO_KEEP_DAYS", store.AUDIO_KEEP_DAYS))
    except Exception:
        log.exception("Audio retention failed")
    try:
        if keep := settings.days("MEETING_KEEP_DAYS", 0):
            store.expire_meetings(keep, skip=live)
    except Exception:
        log.exception("Meeting retention failed")


def _retention_loop() -> None:
    """At start and every few hours, for an app left running."""
    while True:
        _retention_pass()
        time.sleep(6 * 3600)


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
    threading.Thread(target=_retention_loop, daemon=True).start()
    watcher = agenda.Watcher(store.ROOT / "reminders-sent.json", on_reminder)
    log.info("MeTranscript running at %s", URL)
    server.serve_forever()


if __name__ == "__main__":
    main()
