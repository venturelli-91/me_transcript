import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "meetings"
ID_RE = re.compile(r"\d{4}-\d{2}-\d{2}_\d{4}(-\d+)?")
# ponytail: one global lock for read-modify-write of meeting files; per-meeting locks if it ever contends
WRITE_LOCK = threading.Lock()


def meeting_dir(meeting_id: str) -> Path:
    if not ID_RE.fullmatch(meeting_id) or not (ROOT / meeting_id).is_dir():
        raise KeyError(meeting_id)
    return ROOT / meeting_id


def _write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def create(title: str, lang: str, private: bool = False, now: datetime | None = None) -> str:
    now = now or datetime.now()
    base = now.strftime("%Y-%m-%d_%H%M")
    # ponytail: exists()/mkdir() race ignored, one user records one meeting at a time
    meeting_id, n = base, 1
    while (ROOT / meeting_id).exists():
        n += 1
        meeting_id = f"{base}-{n}"
    folder = ROOT / meeting_id
    folder.mkdir(parents=True)
    _write_meta(folder, {"title": title, "lang": lang, "private": private,
                         "started_at": now.isoformat(timespec="seconds"), "ended_at": None})
    return meeting_id


def _read(folder: Path, name: str) -> str:
    f = folder / name
    return f.read_text(encoding="utf-8") if f.exists() else ""


def _write_meta(folder: Path, meta: dict) -> None:
    _write(folder / "meta.json", json.dumps(meta, ensure_ascii=False, indent=2))


def _meta(folder: Path) -> dict:
    return json.loads((folder / "meta.json").read_text(encoding="utf-8"))


def list_meetings() -> list[dict]:
    if not ROOT.exists():
        return []
    out = []
    for folder in ROOT.iterdir():
        if folder.is_dir() and ID_RE.fullmatch(folder.name) and (folder / "meta.json").exists():
            meta = _meta(folder)
            out.append({
                "id": folder.name,
                "title": meta["title"],
                "started_at": meta["started_at"],
                "has_ata": (folder / "ata.md").exists(),
            })
    return sorted(out, key=lambda m: m["started_at"], reverse=True)


def load(meeting_id: str) -> dict:
    folder = meeting_dir(meeting_id)
    return {
        "id": meeting_id,
        **_meta(folder),
        "notes": _read(folder, "notes.md"),
        "transcript": _read(folder, "transcript.md"),
        "ata": _read(folder, "ata.md"),
        "chat": _read_json(folder, "chat.json"),
        "can_undo": bool(_read_json(folder, "ata-history.json")),
    }


def _read_json(folder: Path, name: str) -> list:
    f = folder / name
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def _write_json(folder: Path, name: str, data: list) -> None:
    _write(folder / name, json.dumps(data, ensure_ascii=False, indent=2))


def save_notes(meeting_id: str, notes: str) -> None:
    (meeting_dir(meeting_id) / "notes.md").write_text(notes, encoding="utf-8")


def save_ata(meeting_id: str, text: str) -> None:
    folder = meeting_dir(meeting_id)
    with WRITE_LOCK:
        previous = _read(folder, "ata.md")
        if previous:
            _write_json(folder, "ata-history.json", _read_json(folder, "ata-history.json") + [previous])
        _write(folder / "ata.md", text)


def undo_ata(meeting_id: str) -> None:
    folder = meeting_dir(meeting_id)
    with WRITE_LOCK:
        history = _read_json(folder, "ata-history.json")
        if not history:
            raise RuntimeError("Não há versão anterior do resumo.")
        _write(folder / "ata.md", history.pop())
        _write_json(folder, "ata-history.json", history)


def append_chat(meeting_id: str, *messages: dict) -> None:
    folder = meeting_dir(meeting_id)
    with WRITE_LOCK:
        _write_json(folder, "chat.json", _read_json(folder, "chat.json") + list(messages))


def format_segment(seg: dict) -> str:
    t = int(seg["t"])
    return f"[{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}] **{seg['who']}:** {' '.join(seg['text'].split())}"


def append_segments(meeting_id: str, segments: list[dict]) -> None:
    with (meeting_dir(meeting_id) / "transcript.md").open("a", encoding="utf-8") as f:
        f.writelines(format_segment(s) + "\n" for s in segments)


def finish(meeting_id: str, now: datetime | None = None) -> None:
    folder = meeting_dir(meeting_id)
    meta = _meta(folder)
    meta["ended_at"] = (now or datetime.now()).isoformat(timespec="seconds")
    _write_meta(folder, meta)


def delete_audio(meeting_id: str) -> None:
    # The transcript is the record; audio is only kept when transcription fails, to allow a retry.
    for name in ("mic.wav", "system.wav"):
        (meeting_dir(meeting_id) / name).unlink(missing_ok=True)
