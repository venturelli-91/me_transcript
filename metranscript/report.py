import html
import os
import re
import subprocess
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path

BROWSERS = [
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
]
CSS = """@page { size: A4; margin: 22mm 20mm; }
body { font: 11pt/1.55 "Segoe UI", Arial, sans-serif; color: #1a1613; }
h1 { font-size: 22pt; margin: 0 0 4pt; letter-spacing: -0.02em; }
h2 { font-size: 14pt; margin: 18pt 0 4pt; }
h3, h4 { font-size: 12pt; margin: 14pt 0 3pt; }
.meta { color: #6b625a; margin: 0 0 14pt; }
p, ul { margin: 0 0 8pt; }
li { margin-bottom: 3pt; }
code { font-family: Consolas, monospace; }"""


def meta_line(meeting: dict) -> str:
    start = datetime.fromisoformat(meeting["started_at"])
    parts = [start.strftime("%Y-%m-%d %H:%M")]
    if meeting.get("ended_at"):
        minutes = max(1, round((datetime.fromisoformat(meeting["ended_at"]) - start).total_seconds() / 60))
        parts.append(f"{minutes} min")
    if meeting.get("app"):
        parts.append(meeting["app"])
    return " · ".join(parts)


def title_of(meeting: dict) -> str:
    return " ".join((meeting["title"] or "Untitled meeting").split())


def markdown(meeting: dict) -> str:
    return f"# {title_of(meeting)}\n\n{meta_line(meeting)}\n\n{meeting['summary'].strip()}\n"


def _inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return re.sub(r"(^|[^*])\*([^*]+)\*", r"\1<em>\2</em>", text)


def _body(md: str) -> str:
    out, in_list = [], False
    for line in md.splitlines():
        heading = re.match(r"(#{1,3})\s+(.*)", line)
        item = re.match(r"\s*(?:[-*]|\d+\.)\s+(.*)", line)
        if in_list and not item:
            out.append("</ul>")
            in_list = False
        if heading:
            level = len(heading.group(1)) + 1
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
        elif item:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(item.group(1))}</li>")
        elif line.strip():
            out.append(f"<p>{_inline(line.strip())}</p>")
    return "\n".join(out + ["</ul>"] * in_list)


def page(meeting: dict) -> str:
    return (f'<!doctype html><html lang="{"pt" if meeting.get("lang") == "pt" else "en"}"><meta charset="utf-8">'
            f"<title>{html.escape(title_of(meeting))}</title><style>{CSS}</style>"
            f'<h1>{html.escape(title_of(meeting))}</h1><p class="meta">{html.escape(meta_line(meeting))}</p>'
            f"{_body(meeting['summary'])}</html>")


def browser() -> str | None:
    return next((p for p in map(os.path.expandvars, BROWSERS) if Path(p).is_file()), None)


def pdf(meeting: dict) -> bytes:
    """Print the report with the browser Windows already has (Edge, or Chrome): no extra dependency."""
    exe = browser()
    if not exe:
        raise RuntimeError("The PDF needs Microsoft Edge or Google Chrome installed. Download the Markdown instead.")
    with tempfile.TemporaryDirectory(prefix="metranscript-pdf-") as tmp:
        source, target = Path(tmp) / "report.html", Path(tmp) / "report.pdf"
        source.write_text(page(meeting), encoding="utf-8")
        try:  # ponytail: a browser that hangs after writing the file loses it to the timeout
            subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={Path(tmp) / 'profile'}",
                            f"--print-to-pdf={target}", source.as_uri()], capture_output=True, timeout=60, check=False)
        except subprocess.TimeoutExpired:
            raise RuntimeError("The PDF took too long to generate. Try again, or download the Markdown.") from None
        if not target.is_file():
            raise RuntimeError("Could not generate the PDF. Download the Markdown instead.")
        return target.read_bytes()


def filename(meeting: dict, ext: str) -> str:
    slug = unicodedata.normalize("NFKD", title_of(meeting)).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", slug).strip("-")[:60] or "meeting"
    return f"{slug}-{meeting['started_at'][:10]}.{ext}"
