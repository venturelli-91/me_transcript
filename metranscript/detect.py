import ctypes
import winreg
from ctypes import wintypes

from metranscript import settings

STORE = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
EXES = {
    "zoom.exe": "Zoom",
    "ms-teams.exe": "Teams",
    "teams.exe": "Teams",
    "chrome.exe": "Chrome",
    "msedge.exe": "Edge",
    "firefox.exe": "Firefox",
    "brave.exe": "Brave",
    "arc.exe": "Arc",
}
BROWSERS = {"Chrome", "Edge", "Firefox", "Brave", "Arc"}
DEFAULT_KEYWORDS = "Meet,Zoom,Teams"


def app_name(key_name: str) -> str | None:
    if key_name.lower().startswith("msteams_"):
        return "Teams"
    return EXES.get(key_name.rsplit("#", 1)[-1].lower())


def _value(key, name: str) -> int:
    try:
        return winreg.QueryValueEx(key, name)[0]
    except FileNotFoundError:
        return 0


def _entries(path: str):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as parent:
        for i in range(winreg.QueryInfoKey(parent)[0]):
            name = winreg.EnumKey(parent, i)
            with winreg.OpenKey(parent, name) as key:
                yield name, _value(key, "LastUsedTimeStart"), _value(key, "LastUsedTimeStop")


def window_titles() -> list[str]:
    user32 = ctypes.windll.user32
    titles = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def collect(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd)
        if length and user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            titles.append(buf.value)
        return True

    user32.EnumWindows(collect, 0)
    return titles


def meeting_window() -> bool:
    words = [w.strip().lower() for w in (settings.env("MEETING_KEYWORDS") or DEFAULT_KEYWORDS).split(",") if w.strip()]
    # ponytail: only the active tab's title is visible; a meeting in a background tab is not detected
    return any(w in t.lower() for t in window_titles() for w in words)


def detected() -> dict | None:
    for path in (STORE, STORE + r"\NonPackaged"):
        try:
            entries = list(_entries(path))
        except OSError:
            continue
        for name, start, stop in entries:
            app = app_name(name)
            if app and start and not stop and (app not in BROWSERS or meeting_window()):
                return {"app": app, "key": f"{name}:{start}"}
    return None
