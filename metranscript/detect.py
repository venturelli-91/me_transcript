import ctypes
import re
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
DEFAULT_KEYWORDS = ["Meet", "Zoom", "Teams"]


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


USER32 = ctypes.WinDLL("user32")
KERNEL32 = ctypes.WinDLL("kernel32")
USER32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
USER32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
USER32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
USER32.IsWindowVisible.argtypes = [wintypes.HWND]
USER32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
KERNEL32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
KERNEL32.OpenProcess.restype = wintypes.HANDLE
KERNEL32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _exe_of(hwnd) -> str:
    pid = wintypes.DWORD()
    USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = KERNEL32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        buf, size = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
        return buf.value.rsplit("\\", 1)[-1].lower() if KERNEL32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)) else ""
    finally:
        KERNEL32.CloseHandle(handle)


def window_titles(exe: str) -> list[str]:
    """Titles of the visible windows owned by `exe` (e.g. chrome.exe)."""
    titles = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def collect(hwnd, _):
        length = USER32.GetWindowTextLengthW(hwnd)
        if length and USER32.IsWindowVisible(hwnd) and _exe_of(hwnd) == exe:
            buf = ctypes.create_unicode_buffer(length + 1)
            USER32.GetWindowTextW(hwnd, buf, length + 1)
            titles.append(buf.value)
        return True

    USER32.EnumWindows(collect, 0)
    return titles


def meeting_window(exe: str) -> bool:
    words = [w.strip() for w in (settings.env("MEETING_KEYWORDS") or "").split(",") if w.strip()] or DEFAULT_KEYWORDS
    pattern = re.compile(r"\b(?:" + "|".join(map(re.escape, words)) + r")\b", re.I)
    # ponytail: only the active tab's title is visible; a meeting in a background tab is not detected
    return any(pattern.search(t) for t in window_titles(exe))


def detected() -> dict | None:
    for path in (STORE, STORE + r"\NonPackaged"):
        try:
            entries = list(_entries(path))
        except OSError:
            continue
        for name, start, stop in entries:
            app = app_name(name)
            if app and start and not stop and (app not in BROWSERS or meeting_window(name.rsplit("#", 1)[-1].lower())):
                return {"app": app, "key": f"{name}:{start}"}
    return None
