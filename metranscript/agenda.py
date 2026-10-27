import json
import logging
import re
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from metranscript import google

log = logging.getLogger("metranscript")
LINK_RE = re.compile(r"https://(?:meet\.google\.com|[\w.-]*zoom\.us|teams\.microsoft\.com|teams\.live\.com)/[^\s\"'<>\\]+")
APPS = {"meet.google.com": "Meet", "zoom.us": "Zoom", "teams.": "Teams"}
REMINDERS = (timedelta(minutes=30), timedelta(minutes=2))
LAST_REMINDER = int(REMINDERS[-1].total_seconds() // 60)
REFRESH = timedelta(minutes=5)
HORIZON = timedelta(hours=24)
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
FIELDS = ("items(id,status,summary,start,location,description,hangoutLink,"
          "conferenceData/entryPoints/uri,attendees(self,responseStatus))")


def meeting_link(event: dict) -> str | None:
    entry_points = (event.get("conferenceData") or {}).get("entryPoints") or []
    for text in (event.get("hangoutLink"), *(p.get("uri") for p in entry_points if isinstance(p, dict)),
                 event.get("location"), event.get("description")):
        match = LINK_RE.search(str(text or ""))
        if match:
            return match.group(0)
    return None


def app_of(link: str) -> str:
    return next(name for host, name in APPS.items() if host in link)


def declined(event: dict) -> bool:
    return any(a.get("self") and a.get("responseStatus") == "declined" for a in event.get("attendees") or [] if isinstance(a, dict))


def upcoming(items: list[dict], now: datetime, account: str = "") -> list[dict]:
    """Timed, not cancelled, not declined events with a meeting link after `now`, soonest first. `now` is local aware."""
    out = []
    for event in items:
        stamp = (event.get("start") or {}).get("dateTime")  # an all-day event only has "date"
        link = meeting_link(event)
        if not stamp or not link or event.get("status") == "cancelled" or declined(event):
            continue
        start = datetime.fromisoformat(stamp)
        start = start.astimezone(now.tzinfo) if start.tzinfo else start.replace(tzinfo=now.tzinfo)
        if start <= now:
            continue
        out.append({
            # UTC in the key so a DST change doesn't make the same occurrence look new; the id is already one per occurrence.
            "key": f"{account}:{event.get('id')}@{start.astimezone(timezone.utc).isoformat()}",
            "title": " ".join(str(event.get("summary", "Untitled meeting")).split()),
            "start": start.isoformat(timespec="minutes"),
            "app": app_of(link),
            "account": account,
        })
    return sorted(out, key=lambda e: e["start"])


def events_for(account: str, now: datetime) -> list[dict]:
    reply = google.api(account, EVENTS_URL, params={
        "timeMin": now.isoformat(timespec="seconds"), "timeMax": (now + HORIZON).isoformat(timespec="seconds"),
        "singleEvents": "true", "orderBy": "startTime", "maxResults": 100, "fields": FIELDS})
    return upcoming(reply.get("items") or [], now, account)


def collect(now: datetime) -> tuple[list[dict], str | None]:
    """The upcoming meetings of every connected Google account, merged, and a message if an account could not be read."""
    events, problems = [], []
    for account in google.emails():
        try:
            events += events_for(account, now)
        except google.ReconnectNeeded as e:
            problems.append(str(e))
        except Exception as e:
            log.warning("Could not read the calendar of a Google account: %s", type(e).__name__)
            problems.append("Could not read a calendar. Check your connection and the Google accounts in Settings.")
    return sorted(events, key=lambda e: e["start"]), " ".join(dict.fromkeys(problems)) or None


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

    def _tick(self) -> None:
        now = datetime.now().astimezone()
        if self.last_fetch is None or now - self.last_fetch >= REFRESH:
            self.last_fetch = now
            self.events, self.error = collect(now)
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
