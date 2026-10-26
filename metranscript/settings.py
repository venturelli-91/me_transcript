import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
