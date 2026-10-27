import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The keys the Settings page may edit, and whether each one is a secret (never sent back to the page).
FIELDS = {
    "DEEPSEEK_API_KEY": True,
    "GOOGLE_CLIENT_ID": False,
    "GOOGLE_CLIENT_SECRET": True,
    "MEETING_KEYWORDS": False,
    "AUDIO_KEEP_DAYS": False,
    "MEETING_KEEP_DAYS": False,
}
DAY_LIMITS = {"AUDIO_KEEP_DAYS": (0, 3650), "MEETING_KEEP_DAYS": (1, 3650)}
MAX_VALUE = 2000
_WRITE_LOCK = threading.Lock()


def env(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    dotenv = ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name and value.strip():
                return value.strip().strip("\"'")
    return None


def whole_days(value: str) -> bool:
    return value.isascii() and value.isdigit()  # str.isdigit() alone accepts digits such as "²" that int() rejects


def days(name: str, default: int) -> int:
    """A retention setting in days; a missing or unreadable value means the default."""
    raw = env(name)
    return min(int(raw), 3650) if raw and whole_days(raw) else default


def validate(name: str, value: str) -> str:
    """Return the cleaned value or raise ValueError with a message that never contains the value."""
    if name not in FIELDS:
        raise ValueError("Unknown setting.")
    value = value.strip()
    if not value:
        raise ValueError("The value is empty.")
    if len(value) > MAX_VALUE:
        raise ValueError("The value is too long.")
    if any(c in value for c in "\r\n\0"):
        raise ValueError("The value must be a single line.")
    if value[0] in "\"'" or value[-1] in "\"'":
        raise ValueError("The value can't start or end with a quote.")  # env() strips surrounding quotes
    if name in DAY_LIMITS:
        low, high = DAY_LIMITS[name]
        if not whole_days(value) or not low <= int(value) <= high:
            raise ValueError(f"Enter a whole number of days from {low} to {high}.")
        return str(int(value))
    if name == "GOOGLE_CLIENT_ID" and not value.endswith(".apps.googleusercontent.com"):
        raise ValueError("The client ID ends with .apps.googleusercontent.com.")
    if name == "GOOGLE_CLIENT_SECRET" and " " in value:
        raise ValueError("The client secret has no spaces.")
    if name == "DEEPSEEK_API_KEY" and " " in value:
        raise ValueError("The DeepSeek key has no spaces.")
    return value


def status() -> dict:
    """What is configured, without any secret value. `locked` = a Windows environment variable overrides .env."""
    return {
        name: {"set": bool(env(name)), "locked": bool(os.environ.get(name)), "value": None if secret else env(name)}
        for name, secret in FIELDS.items()
    }


def write_env(updates: dict[str, str | None]) -> None:
    """Set (value) or remove (None) keys in .env, keeping every other line, and replace the file atomically."""
    dotenv = ROOT / ".env"
    with _WRITE_LOCK:
        lines = dotenv.read_text(encoding="utf-8").splitlines() if dotenv.exists() else []
        out, handled = [], set()
        for line in lines:
            key = line.partition("=")[0].strip()
            if key not in updates:
                out.append(line)
            elif key not in handled:
                handled.add(key)
                if updates[key] is not None:
                    out.append(f"{key}={updates[key]}")
            # a repeated key keeps only its first (updated) line
        out += [f"{k}={v}" for k, v in updates.items() if k not in handled and v is not None]
        tmp = dotenv.with_name(".env.tmp")
        try:
            tmp.write_text("".join(line + "\n" for line in out), encoding="utf-8")
            os.replace(tmp, dotenv)
        finally:
            tmp.unlink(missing_ok=True)  # a failed write must not leave the secrets in a stray file
