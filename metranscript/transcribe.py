import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import wave
from collections.abc import Callable
from difflib import SequenceMatcher
from pathlib import Path

from metranscript import privacy

log = logging.getLogger("metranscript")
ROOT = Path(__file__).resolve().parent.parent
WHISPER = Path(os.environ.get("ATA_WHISPER", ROOT / "bin" / "vulkan" / "whisper-cli.exe"))
VAD_CLI = WHISPER.with_name("whisper-vad-speech-segments.exe")
MODEL = Path(os.environ.get("ATA_MODEL", ROOT / "models" / "ggml-large-v3-turbo-q5_0.bin"))
VAD = Path(os.environ.get("ATA_VAD", ROOT / "models" / "ggml-silero-v5.1.2.bin"))
CHUNK = 30.0
MIN_SPEECH = 0.5
# A window ends in a pause of at least MIN_GAP seconds, but never before MIN_WINDOW seconds, so words aren't cut.
MIN_GAP = 0.5
MIN_WINDOW = 12.0
VOCAB_MAX = 300
# A plain sentence works better than a bare list: a list makes Whisper drop punctuation and capitals.
INTRO = {"en": "This meeting mentions {}.", "pt": "Esta reunião menciona {}."}
TAIL = 200
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


ECHO_GAP = 5.0
ECHO_RATIO = 0.7
ECHO_MIN_WORDS = 4


def is_echo(seg: dict, others: list[dict]) -> bool:
    """Speakers playing the call get picked up by the mic, so the same sentence lands in "Me" a moment later."""
    if len(seg["text"].split()) < ECHO_MIN_WORDS:
        return False
    text = seg["text"].lower()
    return any(abs(seg["t"] - o["t"]) <= ECHO_GAP and SequenceMatcher(None, text, o["text"].lower()).ratio() >= ECHO_RATIO
               for o in others)


def merge(*tracks: list[dict]) -> list[dict]:
    segments = [s for t in tracks for s in t]
    others = [s for s in segments if s["who"] == "Others"]
    # ponytail: text similarity, no real echo cancellation; a real "Me" line that repeats Others almost verbatim is lost
    return sorted((s for s in segments if s["who"] != "Me" or not is_echo(s, others)), key=lambda s: s["t"])


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


def to_opus(wav: Path) -> Path:
    """Speech at 24 kbit/s is ~11 MB per hour per track, enough to transcribe again later."""
    out = wav.with_suffix(".opus")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libopus", "-b:a", "24k",
          "-application", "voip", str(out)], timeout=600)
    return out


def retranscribe(folder: Path, lang: str) -> list[dict]:
    """Transcribe a finished meeting again from its saved audio (WAV or Opus)."""
    sources = {track: next((f for ext in (".wav", ".opus") if (f := folder / f"{track}{ext}").exists()), None)
               for track in TRACKS}
    if not all(sources.values()):
        raise RuntimeError("This meeting has no saved audio.")
    with tempfile.TemporaryDirectory() as tmp:
        length = 0.0
        for track, src in sources.items():
            wav = Path(tmp) / f"{track}.wav"
            _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "16000", str(wav)], timeout=600)
            with wave.open(str(wav)) as w:
                length = max(length, w.getnframes() / w.getframerate())
        segments: list[dict] = []
        Transcriber(Path(tmp), lang, recorded=lambda: 0.0, on_segments=segments.extend).finish(length)
        return sorted(segments, key=lambda s: s["t"])


def union(*tracks: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for a, b in sorted(span for t in tracks for span in t):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def pick_cut(spans: list[tuple[float, float]], duration: float) -> float:
    """Where to end a window: the middle of the latest pause in everyone's speech, else the whole window."""
    if not spans or spans[-1][1] <= duration - MIN_GAP:
        return duration
    cut = duration
    for (_, end), (start, _) in zip(spans, spans[1:]):
        if start - end >= MIN_GAP and end >= MIN_WINDOW:
            cut = end + (start - end) / 2
    return cut


def vocabulary() -> str:
    """The user's protected terms, so Whisper spells them right."""
    out = ""
    for term in privacy.terms():
        if len(out) + len(term) + 2 > VOCAB_MAX:
            break
        out += (", " if out else "") + term
    return out


def analyze(wav: Path, start: float, duration: float, tmp: Path) -> tuple[Path, list[tuple[float, float]]]:
    clip = tmp / f"{wav.stem}.wav"
    _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
          "-i", str(wav), "-ac", "1", "-ar", "16000", str(clip)], timeout=60)
    # VAD only gates the window: whisper's own --vad shifts timestamps of speech that follows a pause.
    return clip, speech_spans(_run([str(VAD_CLI), "-vm", str(VAD), "-f", str(clip), "-np"], timeout=60))


def transcribe_clip(clip: Path, spans: list[tuple[float, float]], cut: float, lang: str, who: str,
                    offset: float, prompt: str) -> list[dict]:
    spans = [(a, min(b, cut)) for a, b in spans if a < cut]
    if sum(b - a for a, b in spans) < MIN_SPEECH:
        return []
    # Whisper stamps the first sentence at 0 s when the clip opens with silence; start it where speech starts.
    skip = max(0.0, spans[0][0] - 0.3)
    base = clip.with_name(f"{clip.stem}-out")
    args = [str(WHISPER), "-m", str(MODEL), "-f", str(clip), "-l", lang, "-t", THREADS,
            "-ot", str(int(skip * 1000)), "-d", str(int((cut - skip) * 1000)), "-oj", "-of", str(base), "-np"]
    if prompt:
        args += ["--prompt", prompt]
    _run(args, timeout=300)
    return parse_whisper(json.loads(base.with_suffix(".json").read_text(encoding="utf-8")), offset, who)


class Transcriber:
    def __init__(self, folder: Path, lang: str, recorded: Callable[[], float],
                 on_segments: Callable[[list[dict]], None]) -> None:
        self.folder, self.lang, self.recorded, self.on_segments = folder, lang, recorded, on_segments
        self.done = 0.0
        self.tail = dict.fromkeys(TRACKS.values(), "")
        self.error: str | None = None
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _window(self, end: float, final: bool = False) -> None:
        duration = end - self.done
        with tempfile.TemporaryDirectory() as tmp:
            found = {who: analyze(self.folder / f"{track}.wav", self.done, duration, Path(tmp))
                     for track, who in TRACKS.items()}
            cut = duration if final else pick_cut(union(*(spans for _, spans in found.values())), duration)
            tracks = []
            for who, (clip, spans) in found.items():
                # The vocabulary and the end of what this person just said keep names and sentences consistent.
                names = vocabulary()
                prompt = " ".join(filter(None, [INTRO[self.lang].format(names) if names else "", self.tail[who]]))
                tracks.append(transcribe_clip(clip, spans, cut, self.lang, who, self.done, prompt))
        for segs in tracks:
            if segs:
                self.tail[segs[-1]["who"]] = " ".join(s["text"] for s in segs)[-TAIL:].strip()
        self.done += cut
        if segments := merge(*tracks):
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
            window_end = min(end, self.done + CHUNK)
            self._window(window_end, final=window_end == end)
