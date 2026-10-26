import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "meetings"
ID_RE = re.compile(r"\d{4}-\d{2}-\d{2}_\d{4}(-\d+)?")


def meeting_dir(meeting_id: str) -> Path:
    if not ID_RE.fullmatch(meeting_id) or not (ROOT / meeting_id).is_dir():
        raise KeyError(meeting_id)
    return ROOT / meeting_id


def create(title: str, lang: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    base = now.strftime("%Y-%m-%d_%H%M")
    # ponytail: exists()/mkdir() race ignored, one user records one meeting at a time
    meeting_id, n = base, 1
    while (ROOT / meeting_id).exists():
        n += 1
        meeting_id = f"{base}-{n}"
    folder = ROOT / meeting_id
    folder.mkdir(parents=True)
    _write_meta(folder, {"title": title, "lang": lang, "started_at": now.isoformat(timespec="seconds"), "ended_at": None})
    return meeting_id


def _read(folder: Path, name: str) -> str:
    f = folder / name
    return f.read_text(encoding="utf-8") if f.exists() else ""


def _write_meta(folder: Path, meta: dict) -> None:
    (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


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
    }


def save_notes(meeting_id: str, notes: str) -> None:
    (meeting_dir(meeting_id) / "notes.md").write_text(notes, encoding="utf-8")


def save_ata(meeting_id: str, text: str) -> None:
    (meeting_dir(meeting_id) / "ata.md").write_text(text, encoding="utf-8")


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
