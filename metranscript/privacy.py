import difflib
import os
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_TERMS = 500
MIN_TERM = 3
MAX_TERM = 100
PLACEHOLDER_RE = re.compile(r"\[[A-Z]+_\d+\]")
LOOKS_LIKE_CODE_RE = re.compile(r"\[[a-z]+_\d+\]")  # the same, on folded (lowercase) text
_UNITS = "k|mil|milhões|milhão|bilhões|bilhão|million|billion|reais|dólares|dollars|euros"
# Patterns run on the folded text, in this order; the first match of a stretch wins. Every repeat is bounded so
# a long run of text can't make the matching slow. Digit-only ids need 9+ digits, see Mask.apply.
PATTERNS = [
    ("SECRET", re.compile(r"\b(?:sk|pk|ghp|xox[abp])[-_][a-z0-9_-]{16,200}|\b[0-9a-f]{32,200}\b")),
    ("LINK", re.compile(r"(?:https?://|www\.)[^\s<>\"')\]]{0,500}[^\s<>\"')\].,;:!?]")),
    ("EMAIL", re.compile(r"[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){1,5}")),
    ("AMOUNT", re.compile(rf"(?:r\$|us\$|\$|€|£)\s?\d(?:[\d.,]{{0,20}}\d)?(?:\s?(?:{_UNITS}|m|bn)\b)?"
                          rf"|\b\d(?:[\d.,]{{0,20}}\d)?\s?(?:{_UNITS})\b")),
    ("ID", re.compile(r"\+?\d[\d ()./-]{7,30}\d")),
]
# A name can be split by a line break and the next transcript line's "[hh:mm:ss] **Who:**" prefix.
SEPARATOR = r"(?:\[\d\d:\d\d:\d\d\]\s{0,3}\*\*\w{1,20}:\*\*|[\W_])+"
# Letters Whisper swaps for each other when it spells a name by ear.
SOUND_ALIKE = {"c": "k", "k": "k", "q": "k"}


def fold(text: str) -> tuple[str, list[int]]:
    """Lowercase, no accents, no invisible characters, compatibility forms flattened (fullwidth -> ASCII).

    Returns the folded text and, for each folded character, its index in the original.
    """
    out, index = [], []
    for i, c in enumerate(text):
        for d in unicodedata.normalize("NFKD", c).lower():
            if unicodedata.category(d) not in ("Mn", "Cf"):
                out.append(d)
                index.append(i)
    return "".join(out), index


def _parse(text: str) -> list[str]:
    seen, out = set(), []
    for line in text.splitlines():
        term = " ".join(line.split())
        key = fold(term)[0]
        if term and not term.startswith("# ") and term != "#" and key not in seen:
            seen.add(key)
            out.append(term)
    return out


def terms() -> list[str]:
    path = ROOT / "sensitive-terms.txt"
    return _parse(path.read_text(encoding="utf-8-sig")) if path.exists() else []


def save_terms(text: str) -> list[str]:
    cleaned = _parse(text.lstrip("\ufeff"))
    if len(cleaned) > MAX_TERMS:
        raise ValueError(f"Add at most {MAX_TERMS} terms.")
    if any(not MIN_TERM <= len(t) <= MAX_TERM for t in cleaned):
        raise ValueError(f"Each term must have between {MIN_TERM} and {MAX_TERM} characters.")
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
        self._terms = []
        for term in sorted(terms(), key=len, reverse=True):
            key = fold(term)[0]
            if key:
                words = key.split(" ")
                self._terms.append((term, key, re.compile(r"(?<!\w)" + SEPARATOR.join(map(re.escape, words)) + r"(?!\w)")))
        # Single-word terms by their first letter (sound-alikes share a bucket), for the misspelling check.
        self._singles: dict[str, list[tuple[str, str]]] = {}
        for term, key, _ in self._terms:
            if " " not in key and len(key) >= 4:
                self._singles.setdefault(SOUND_ALIKE.get(key[0], key[0]), []).append((term, key))
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
        folded, index = fold(text)
        taken = bytearray(len(folded))
        spans: list[tuple[int, int, str, str, str]] = []

        def add(m_start: int, m_end: int, kind: str, key: str, original: str | None = None) -> None:
            if not any(taken[m_start:m_end]):
                taken[m_start:m_end] = b"\x01" * (m_end - m_start)
                a, b = index[m_start], index[m_end - 1] + 1
                while b < len(text) and unicodedata.category(text[b]) in ("Mn", "Cf"):
                    b += 1  # a trailing accent mark or zero-width character belongs to the hidden word
                spans.append((a, b, kind, key, original if original is not None else text[a:b]))

        # Text that already looks like a code is hidden too, so a stored [TERM_1] can't be mistaken for a real one.
        for m in LOOKS_LIKE_CODE_RE.finditer(folded):
            add(m.start(), m.end(), "RAW", m.group())
        # Contacts and values first, so a term inside an email or link hides the whole thing, not a piece of it.
        for kind, rx in PATTERNS:
            for m in rx.finditer(folded):
                if kind != "ID" or sum(c.isdigit() for c in m.group()) >= 9:
                    add(m.start(), m.end(), kind, text[index[m.start()]:index[m.end() - 1] + 1])
        for term, key, rx in self._terms:
            for m in rx.finditer(folded):
                add(m.start(), m.end(), "TERM", key, term)
        # Whisper often misspells a name; a close single-word match is treated as the name itself.
        if self._singles:
            for m in re.finditer(r"\w{4,}", folded):
                word = m.group()
                for term, key in self._singles.get(SOUND_ALIKE.get(word[0], word[0]), ()):
                    ratio = 0.8 if len(key) >= 5 else 0.75
                    if abs(len(word) - len(key)) <= 2 and difflib.SequenceMatcher(None, word, key).ratio() >= ratio:
                        add(m.start(), m.end(), "TERM", key, term)
                        break
        out, pos = [], 0
        for a, b, kind, key, original in sorted(spans):
            out += [text[pos:a], self._code(kind, key, original)]
            pos = b
        return "".join(out) + text[pos:]

    def restore(self, text: str) -> str:
        return PLACEHOLDER_RE.sub(lambda m: self._originals.get(m.group(), m.group()), text)
