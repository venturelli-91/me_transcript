import difflib
import os
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_TERMS = 500
MAX_TERM = 100
FUZZY = 0.8
PLACEHOLDER_RE = re.compile(r"\[[A-Z]+_\d+\]")
_UNITS = "k|mil|milhões|milhão|bilhões|bilhão|million|billion|reais|dólares|dollars|euros"
# Checked in this order; the first match of a stretch of text wins. Digits-only ids need 9+ digits, see Mask.apply.
PATTERNS = [
    ("SECRET", re.compile(r"\b(?:sk|pk|ghp|xox[abp])[-_][A-Za-z0-9_-]{16,}|\b[0-9a-f]{32,}\b")),
    ("LINK", re.compile(r"(?:https?://|www\.)[^\s<>\"')\]]*[^\s<>\"')\].,;:!?]")),
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("AMOUNT", re.compile(rf"(?:R\$|US\$|\$|€|£)\s?\d(?:[\d.,]*\d)?(?:\s?(?:{_UNITS}|m|bn)\b)?"
                          rf"|\b\d(?:[\d.,]*\d)?\s?(?:{_UNITS})\b", re.I)),
    ("ID", re.compile(r"\+?\d[\d ()./-]{7,}\d")),
]


def fold(text: str) -> str:
    """Lowercase without accents, one character per character so positions still line up with the original."""
    return "".join(unicodedata.normalize("NFD", c)[0].lower() for c in text)


def _parse(text: str) -> list[str]:
    seen, out = set(), []
    for line in text.splitlines():
        term = " ".join(line.split())
        if term and not term.startswith("#") and fold(term) not in seen:
            seen.add(fold(term))
            out.append(term)
    return out


def terms() -> list[str]:
    path = ROOT / "sensitive-terms.txt"
    return _parse(path.read_text(encoding="utf-8")) if path.exists() else []


def save_terms(text: str) -> list[str]:
    cleaned = _parse(text)
    if len(cleaned) > MAX_TERMS:
        raise ValueError(f"Add at most {MAX_TERMS} terms.")
    if any(len(t) > MAX_TERM for t in cleaned):
        raise ValueError(f"Each term must have at most {MAX_TERM} characters.")
    path = ROOT / "sensitive-terms.txt"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("".join(t + "\n" for t in cleaned), encoding="utf-8")
    os.replace(tmp, path)
    return cleaned


class Mask:
    """Swaps sensitive text for codes like [TERM_1] before it goes to the AI, and back in what comes back.

    One Mask per request keeps a code pointing at the same thing across every message of that request.
    """

    def __init__(self) -> None:
        self._terms = sorted(terms(), key=len, reverse=True)
        self._codes: dict[tuple[str, str], str] = {}
        self._originals: dict[str, str] = {}

    def __len__(self) -> int:
        return len(self._codes)

    def _code(self, kind: str, key: str, original: str) -> str:
        if (kind, key) not in self._codes:
            code = f"[{kind}_{sum(k == kind for k, _ in self._codes) + 1}]"
            self._codes[(kind, key)] = code
            self._originals[code] = original
        return self._codes[(kind, key)]

    def apply(self, text: str) -> str:
        folded = fold(text)
        spans: list[tuple[int, int, str, str, str]] = []

        def add(a: int, b: int, kind: str, key: str, original: str) -> None:
            if not any(a < e and s < b for s, e, *_ in spans):
                spans.append((a, b, kind, key, original))

        # Contacts and values first, so a term inside an email or link hides the whole thing, not a piece of it.
        for kind, rx in PATTERNS:
            for m in rx.finditer(text):
                if kind != "ID" or sum(c.isdigit() for c in m.group()) >= 9:
                    add(m.start(), m.end(), kind, fold(m.group()), m.group())
        for term in self._terms:
            key = fold(term)
            for m in re.finditer(rf"(?<!\w){re.escape(key)}(?!\w)", folded):
                add(m.start(), m.end(), "TERM", key, term)
        # Whisper often misspells a name; a close single-word match is treated as the name itself.
        singles = [(fold(t), t) for t in self._terms if " " not in t and len(t) >= 5]
        for m in re.finditer(r"\w{5,}", folded):
            for key, term in singles:
                if (m.group()[0] == key[0] and abs(len(m.group()) - len(key)) <= 2
                        and difflib.SequenceMatcher(None, m.group(), key).ratio() >= FUZZY):
                    add(m.start(), m.end(), "TERM", key, term)
                    break
        out, pos = [], 0
        for a, b, kind, key, original in sorted(spans):
            out += [text[pos:a], self._code(kind, key, original)]
            pos = b
        return "".join(out) + text[pos:]

    def restore(self, text: str) -> str:
        return PLACEHOLDER_RE.sub(lambda m: self._originals.get(m.group(), m.group()), text)
