import logging
import os
import subprocess
import sys
import winreg
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from metranscript.settings import ROOT

log = logging.getLogger("metranscript")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "MeTranscript"
APP_ID = "MeTranscript"
# Constant script: event text never becomes PowerShell code, it only arrives as XML data in an env var.
TOAST_SCRIPT = (
    "$ErrorActionPreference='Stop';"
    "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]>$null;"
    "[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime]>$null;"
    "$x=New-Object Windows.Data.Xml.Dom.XmlDocument;$x.LoadXml($env:METRANSCRIPT_TOAST);"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:METRANSCRIPT_APP_ID)"
    ".Show([Windows.UI.Notifications.ToastNotification]::new($x))"
)


def toast_xml(title: str, message: str, url: str, action: tuple[str, str] | None = None) -> str:
    actions = ""
    if action:
        actions = (f'<actions><action content={quoteattr(action[0])} activationType="protocol" '
                   f'arguments={quoteattr(action[1])}/></actions>')
    return (f'<toast activationType="protocol" launch={quoteattr(url)}><visual><binding template="ToastGeneric">'
            f"<text>{escape(title)}</text><text>{escape(message)}</text></binding></visual>{actions}</toast>")


def _register_app_id() -> None:
    # Unpackaged apps need an AppUserModelId with a display name for Windows to show their toasts.
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{APP_ID}") as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "MeTranscript")


def notify(title: str, message: str, url: str, action: tuple[str, str] | None = None) -> None:
    try:
        _register_app_id()
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", TOAST_SCRIPT],
            env={**os.environ, "METRANSCRIPT_TOAST": toast_xml(title, message, url, action), "METRANSCRIPT_APP_ID": APP_ID},
            check=True, capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        log.exception("Could not show the Windows notification")


def reminder_text(event: dict, minutes: int) -> tuple[str, str]:
    at = datetime.fromisoformat(event["start"]).strftime("%H:%M")
    when = "Starts in 2 min" if minutes <= 2 else f"In {minutes} min, at {at}"
    return event["title"], f"{when} ({event['app']})"


def launcher() -> str:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw}" "{ROOT / "start.pyw"}"'


def autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, RUN_NAME)[0] == launcher()
    except FileNotFoundError:
        return False


def set_autostart(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, launcher())
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass
