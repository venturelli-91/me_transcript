import json
import logging
import os
import re
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ata import detect, enhance, mail, store
from ata.capture import Recorder
from ata.transcribe import Transcriber, check_ready

log = logging.getLogger("ata")
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
            raise RuntimeError("Já existe uma reunião sendo gravada.")
        if session.phase in BUSY:
            raise RuntimeError("A reunião anterior ainda está sendo processada. Aguarde a ata ficar pronta.")
        check_ready()
        meeting_id = store.create(title, lang, private)
        try:
            recorder = Recorder(store.meeting_dir(meeting_id))
        except Exception as e:
            shutil.rmtree(store.meeting_dir(meeting_id))
            log.exception("Falha ao abrir o áudio")
            raise RuntimeError(f"Não foi possível abrir o microfone ou o áudio do sistema: {e}") from None
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
            raise RuntimeError("Nenhuma gravação em andamento.")
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
        log.exception("Falha ao finalizar %s", meeting_id)
        return _set_phase("error", f"A transcrição não terminou ({e}). O áudio e as notas estão salvos na pasta da reunião.")
    try:
        store.delete_audio(meeting_id)
    except OSError:
        log.warning("Não foi possível apagar o áudio de %s (arquivo em uso?)", meeting_id)
    meeting = store.load(meeting_id)
    if meeting.get("private"):
        return _set_phase("done")
    _set_phase("enhancing")
    try:
        store.save_ata(meeting_id, enhance.summarize(meeting))
    except Exception as e:
        log.exception("Falha ao gerar o resumo de %s", meeting_id)
        return _set_phase("error", f"Resumo não gerado: {e} A transcrição está salva; use Gerar resumo.")
    # Still "enhancing" while sending, so a manual click can't race the automatic email.
    _auto_email(meeting_id)
    _set_phase("done")


def _auto_email(meeting_id: str) -> None:
    meeting = store.load(meeting_id)
    if not mail.configured() or meeting.get("private") or not meeting["ata"] or meeting.get("emailed_at"):
        return
    try:
        mail.send(meeting)
    except RuntimeError as e:
        log.warning("E-mail de %s não enviado: %s", meeting_id, e)
        return store.set_email_status(meeting_id, str(e))
    store.set_email_status(meeting_id)


def _set_phase(phase: str, error: str | None = None) -> None:
    with session.lock:
        session.phase, session.error = phase, error


def _sendable(meeting_id: str) -> dict:
    with session.lock:
        if session.meeting_id == meeting_id and session.phase in BUSY:
            raise RuntimeError("Aguarde: esta reunião ainda está sendo gravada, transcrita ou resumida.")
    meeting = store.load(meeting_id)
    if meeting.get("private"):
        raise RuntimeError("Reunião sigilosa: nada dela é enviado para a IA.")
    return meeting


def summarize(meeting_id: str) -> dict:
    store.save_ata(meeting_id, enhance.summarize(_sendable(meeting_id)))
    _auto_email(meeting_id)
    return load(meeting_id)


def email(meeting_id: str) -> dict:
    meeting = _sendable(meeting_id)
    if not meeting["ata"]:
        raise RuntimeError("Gere o resumo antes de enviar por e-mail.")
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
        store.save_ata(meeting_id, result["summary"])
    store.append_chat(meeting_id, {"role": "user", "content": message},
                      {"role": "assistant", "content": result["reply"], "changed_summary": bool(result["summary"])})
    return load(meeting_id)


def undo(meeting_id: str) -> dict:
    store.undo_ata(meeting_id)
    return load(meeting_id)


MEETING_RE = re.compile(r"/api/meetings/([^/]+)(/notes|/ata|/chat|/undo|/email)?")


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
            raise ValueError("Tamanho do corpo inválido.")
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            raise ValueError("JSON inválido.") from None
        if not isinstance(data, dict):
            raise ValueError("JSON deve ser um objeto.")
        return data

    def _trusted(self, write: bool) -> bool:
        # Blocks DNS rebinding (Host) and cross-site form posts (JSON forces a CORS preflight we never answer).
        if self.headers.get("Host") not in HOSTS:
            self._send(403, {"error": "Host não permitido."})
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
        self._send(404, {"error": "Não encontrado."})

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
                    raise ValueError("Idioma deve ser pt ou en.")
                if not isinstance(title, str):
                    raise ValueError("O título deve ser texto.")
                if not isinstance(private, bool):
                    raise ValueError("private deve ser true ou false.")
                self._send(200, {"id": start(title.strip()[:200], lang, private)})
            return self._guard(run)
        if self.path == "/api/stop":
            return self._guard(lambda: (stop(), self._send(200)))
        m = MEETING_RE.fullmatch(self.path)
        if m and m.group(2) == "/ata":
            return self._guard(lambda: self._send(200, summarize(m.group(1))))
        if m and m.group(2) == "/email":
            return self._guard(lambda: self._send(200, email(m.group(1))))
        if m and m.group(2) == "/undo":
            return self._guard(lambda: self._send(200, undo(m.group(1))))
        if m and m.group(2) == "/chat":
            def run():
                message = self._body().get("message")
                if not isinstance(message, str) or not message.strip() or len(message) > 4000:
                    raise ValueError("Escreva uma mensagem de até 4000 caracteres.")
                self._send(200, chat(m.group(1), message.strip()))
            return self._guard(run)
        self._send(404, {"error": "Não encontrado."})

    def do_PUT(self) -> None:
        if not self._trusted(write=True):
            return
        m = MEETING_RE.fullmatch(self.path)
        if m and m.group(2) == "/notes":
            def run():
                notes = self._body().get("notes")
                if not isinstance(notes, str):
                    raise ValueError("notes deve ser texto.")
                store.save_notes(m.group(1), notes)
                self._send(200)
            return self._guard(run)
        self._send(404, {"error": "Não encontrado."})

    def _guard(self, fn) -> None:
        try:
            fn()
        except KeyError:
            self._send(404, {"error": "Reunião não encontrada."})
        except RuntimeError as e:
            self._send(409, {"error": str(e)})
        except ValueError as e:
            self._send(400, {"error": str(e)})


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    log.info("Ata em http://127.0.0.1:%d", PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
