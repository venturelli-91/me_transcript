import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("metranscript")
ROOT = Path(__file__).resolve().parent.parent
WHISPER = Path(os.environ.get("ATA_WHISPER", ROOT / "bin" / "vulkan" / "whisper-cli.exe"))
VAD_CLI = WHISPER.with_name("whisper-vad-speech-segments.exe")
MODEL = Path(os.environ.get("ATA_MODEL", ROOT / "models" / "ggml-large-v3-turbo-q5_0.bin"))
VAD = Path(os.environ.get("ATA_VAD", ROOT / "models" / "ggml-silero-v5.1.2.bin"))
CHUNK = 30.0
MIN_SPEECH = 0.5
SEGMENT_RE = re.compile(r"start = ([\d.]+), end = ([\d.]+)")
# The Vulkan build runs the model on the GPU; CPU threads only feed it, so few are enough.
THREADS = os.environ.get("ATA_THREADS", "4")
TRACKS = {"mic": "Me", "system": "Others"}
# Whisper invents these on near-silent audio; the VAD catches most, this catches the rest.
HALLUCINATIONS = {
    "legendas pela comunidade amara.org",
    "obrigado por assistir.",
    "thanks for watching!",
    "thank you for watching.",
    "[música]",
    "[music]",
    "(música)",
    "...",
}


def check_ready() -> None:
    missing = [str(p) for p in (WHISPER, VAD_CLI, MODEL, VAD) if not p.exists()]
    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg no PATH")
    if missing:
        raise RuntimeError(f"Transcription unavailable, missing: {', '.join(missing)}. See the README.")


def is_hallucination(text: str) -> bool:
    t = text.strip().lower()
    return not t or t in HALLUCINATIONS or (t.startswith(("[", "(")) and t.endswith(("]", ")")))


def parse_whisper(data: dict, offset: float, who: str) -> list[dict]:
    out = []
    for item in data.get("transcription", []):
        text = " ".join(item["text"].split())
        if not is_hallucination(text):
            out.append({"t": round(offset + item["offsets"]["from"] / 1000, 2), "who": who, "text": text})
    return out


def speech_spans(vad_output: str) -> list[tuple[float, float]]:
    return [(float(a) / 100, float(b) / 100) for a, b in SEGMENT_RE.findall(vad_output)]


def merge(*tracks: list[dict]) -> list[dict]:
    return sorted((s for t in tracks for s in t), key=lambda s: s["t"])


def _run(args: list[str], timeout: int) -> str:
    try:
        # Below-normal priority: the video call always wins the CPU.
        return subprocess.run(args, check=True, capture_output=True, timeout=timeout,
                              creationflags=subprocess.BELOW_NORMAL_PRIORITY_CLASS).stdout.decode(errors="replace")
    except subprocess.CalledProcessError as e:
        tail = e.stderr.decode(errors="replace").strip()[-300:]
        raise RuntimeError(f"{Path(args[0]).name} failed: {tail}") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{Path(args[0]).name} did not respond within {timeout} s") from None


def transcribe_window(wav: Path, start: float, duration: float, lang: str, who: str) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        clip = Path(tmp) / "clip.wav"
        _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
              "-i", str(wav), "-ac", "1", "-ar", "16000", str(clip)], timeout=60)
        # VAD only gates the window: whisper's own --vad shifts timestamps of speech that follows a pause.
        spans = speech_spans(_run([str(VAD_CLI), "-vm", str(VAD), "-f", str(clip), "-np"], timeout=60))
        if sum(b - a for a, b in spans) < MIN_SPEECH:
            return []
        # Whisper stamps the first sentence at 0 s when the clip opens with silence; start it where speech starts.
        skip_ms = str(int(max(0.0, spans[0][0] - 0.3) * 1000))
        base = Path(tmp) / "out"
        _run([str(WHISPER), "-m", str(MODEL), "-f", str(clip), "-l", lang, "-t", THREADS,
              "-ot", skip_ms, "-oj", "-of", str(base), "-np"], timeout=300)
        return parse_whisper(json.loads(base.with_suffix(".json").read_text(encoding="utf-8")), start, who)


class Transcriber:
    def __init__(self, folder: Path, lang: str, recorded: Callable[[], float],
                 on_segments: Callable[[list[dict]], None]) -> None:
        self.folder, self.lang, self.recorded, self.on_segments = folder, lang, recorded, on_segments
        self.done = 0.0
        self.error: str | None = None
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _window(self, end: float) -> None:
        # ponytail: fixed 30 s cuts can split a word at the boundary; overlap windows if that hurts quality
        segments = merge(*(transcribe_window(self.folder / f"{track}.wav", self.done, end - self.done, self.lang, who)
                           for track, who in TRACKS.items()))
        self.done = end
        if segments:
            self.on_segments(segments)

    def _loop(self) -> None:
        while not self.stopping.wait(1.0):
            if self.recorded() - self.done >= CHUNK:
                try:
                    self._window(self.done + CHUNK)
                except Exception as e:
                    log.exception("Live transcription failed")
                    self.error = f"Live transcription stopped ({e}). Audio is still being recorded."
                    return

    def finish(self, end: float) -> None:
        self.stopping.set()
        self.thread.join()
        while end - self.done > 0.5:
            self._window(min(end, self.done + CHUNK))
