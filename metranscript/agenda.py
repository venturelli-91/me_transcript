import json
import logging
import re
import threading
import time
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import icalendar
import recurring_ical_events

from metranscript.settings import env

log = logging.getLogger("metranscript")
LINK_RE = re.compile(r"https://(?:meet\.google\.com|[\w.-]*zoom\.us|teams\.microsoft\.com|teams\.live\.com)/[^\s\"'<>\\]+")
APPS = {"meet.google.com": "Meet", "zoom.us": "Zoom", "teams.": "Teams"}
REMINDERS = (timedelta(minutes=30), timedelta(minutes=2))
LAST_REMINDER = int(REMINDERS[-1].total_seconds() // 60)
REFRESH = timedelta(minutes=5)
HORIZON = timedelta(hours=24)
MAX_ICS = 10_000_000


def ics_urls() -> list[str]:
    return [u.strip() for u in (env("GOOGLE_CALENDAR_ICS") or "").split(",") if u.strip().startswith("https://")]


def meeting_link(event) -> str | None:
    for field in ("X-GOOGLE-CONFERENCE", "LOCATION", "DESCRIPTION", "URL"):
        match = LINK_RE.search(str(event.get(field, "")))
        if match:
            return match.group(0)
    return None


def app_of(link: str) -> str:
    return next(name for host, name in APPS.items() if host in link)


def declined(event, me: str | None) -> bool:
    if not me:
        return False
    attendees = event.get("ATTENDEE", [])
    for a in attendees if isinstance(attendees, list) else [attendees]:
        if str(a).lower() == f"mailto:{me.lower()}" and a.params.get("PARTSTAT") == "DECLINED":
            return True
    return False


def upcoming(ics_texts: list[bytes], now: datetime, me: str | None = None) -> list[dict]:
    """Timed events with a meeting link between now and now + HORIZON, soonest first. `now` is local aware."""
    out = []
    for text in ics_texts:
        for event in recurring_ical_events.of(icalendar.Calendar.from_ical(text)).between(now, now + HORIZON):
            start = event.get("DTSTART").dt
            link = meeting_link(event)
            if (not isinstance(start, datetime) or not link or declined(event, me)
                    or str(event.get("STATUS", "")).upper() == "CANCELLED"):
                continue
            start = start.astimezone(now.tzinfo) if start.tzinfo else start.replace(tzinfo=now.tzinfo)
            if start <= now:
                continue
            out.append({
                # UTC in the key so a DST change doesn't make the same occurrence look new.
                "key": f"{event.get('UID')}@{start.astimezone(timezone.utc).isoformat()}",
                "title": " ".join(str(event.get("SUMMARY", "Untitled meeting")).split()),
                "start": start.isoformat(timespec="minutes"),
                "app": app_of(link),
            })
    return sorted(out, key=lambda e: e["start"])


def due(events: list[dict], now: datetime, sent: set[str]) -> list[tuple[dict, int, int]]:
    """(event, minutes left, reminder in minutes) for every reminder that should fire now and hasn't yet."""
    out = []
    for e in events:
        left = datetime.fromisoformat(e["start"]) - now
        for i, offset in enumerate(REMINDERS):
            closer = REMINDERS[i + 1] if i + 1 < len(REMINDERS) else timedelta(0)
            reminder = int(offset.total_seconds() // 60)
            tag = f"{e['key']}#{reminder}"
            # A late start still gets the reminder it is inside of, but never one already superseded.
            if closer < left <= offset and tag not in sent:
                out.append((e, max(1, round(left.total_seconds() / 60)), reminder))
                sent.add(tag)
    return out


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=20) as res:
        data = res.read(MAX_ICS + 1)
    if len(data) > MAX_ICS:
        raise ValueError("calendar feed larger than 10 MB")
    return data


class Watcher:
    def __init__(self, state: Path, notify: Callable[[dict, int, int], None]) -> None:
        self.state, self.notify = state, notify
        self.events: list[dict] = []
        self.error: str | None = None
        self.last_fetch: datetime | None = None
        try:
            self.sent: set[str] = set(json.loads(state.read_text(encoding="utf-8"))) if state.exists() else set()
        except (OSError, ValueError):
            log.warning("Ignoring unreadable %s", state.name)
            self.sent = set()
        threading.Thread(target=self._loop, daemon=True).start()

    def _refresh(self, now: datetime) -> None:
        urls = ics_urls()
        if not urls:
            self.events, self.error = [], None
            return
        try:
            self.events = upcoming([fetch(u) for u in urls], now, env("GMAIL_ADDRESS"))
            self.error = None
        except Exception as e:
            log.warning("Could not read the calendar: %s", type(e).__name__)  # the message may contain the secret URL
            self.error = "Could not read the calendar. Check the calendar address in Settings and your connection."

    def _tick(self) -> None:
        now = datetime.now().astimezone()
        if self.last_fetch is None or now - self.last_fetch >= REFRESH:
            self.last_fetch = now
            self._refresh(now)
        fired = due(self.events, now, self.sent)
        for event, minutes, reminder in fired:
            self.notify(event, minutes, reminder)
        if fired:
            keep = {e["key"] for e in self.events}
            self.sent = {t for t in self.sent if t.rsplit("#", 1)[0] in keep}
            self.state.write_text(json.dumps(sorted(self.sent)), encoding="utf-8")

    def _loop(self) -> None:
        while True:
            # One bad pass (disk, notification, odd event) must not end reminders for the rest of the session.
            try:
                self._tick()
            except Exception:
                log.exception("Calendar reminder pass failed")
            time.sleep(20)
