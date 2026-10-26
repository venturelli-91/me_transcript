import winreg

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


def detected() -> dict | None:
    for path in (STORE, STORE + r"\NonPackaged"):
        try:
            entries = list(_entries(path))
        except OSError:
            continue
        for name, start, stop in entries:
            app = app_name(name)
            if app and start and not stop:
                return {"app": app, "key": f"{name}:{start}"}
    return None
