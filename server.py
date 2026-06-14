"""Minimal iCloud CalDAV MCP server (stdio).

Tools: list_calendars, list_events, create_event, delete_event, list_reminders.
Credentials read from env: ICLOUD_USER, ICLOUD_APP_PASSWORD.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import caldav
from caldav.lib.error import NotFoundError
from mcp.server.fastmcp import FastMCP


def _load_secrets():
    from pathlib import Path
    p = Path(__file__).parent.parent / "secrets.env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

_load_secrets()

USER = os.environ["ICLOUD_USER"]
PWD = os.environ["ICLOUD_APP_PASSWORD"]
URL = os.environ.get("ICLOUD_CALDAV_URL", "https://caldav.icloud.com/")

mcp = FastMCP("icloud-cal")

_client = None
_principal = None


def principal():
    global _client, _principal
    if _principal is None:
        _client = caldav.DAVClient(url=URL, username=USER, password=PWD)
        _principal = _client.principal()
    return _principal


def find_calendar(name: str):
    for cal in principal().calendars():
        if cal.get_display_name() == name:
            return cal
    raise ValueError(f"Calendar not found: {name}")


@mcp.tool()
def list_calendars() -> list[dict]:
    """List all calendars on the iCloud account."""
    return [{"name": c.get_display_name(), "url": str(c.url)} for c in principal().calendars()]


@mcp.tool()
def list_events(days_ahead: int = 14, calendar: Optional[str] = None) -> list[dict]:
    """List events within `days_ahead` days from now, optionally filtered by calendar name."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days_ahead)
    cals = [find_calendar(calendar)] if calendar else principal().calendars()
    out = []
    for cal in cals:
        try:
            evs = cal.search(start=now, end=end, event=True, expand=True)
        except Exception:
            continue
        for ev in evs:
            v = ev.vobject_instance.vevent
            s = getattr(v, "dtstart", None)
            summ = getattr(v, "summary", None)
            loc = getattr(v, "location", None)
            uid = getattr(v, "uid", None)
            out.append({
                "calendar": cal.get_display_name(),
                "start": s.value.isoformat() if s and hasattr(s.value, "isoformat") else str(s.value if s else ""),
                "summary": summ.value if summ else "",
                "location": loc.value if loc else "",
                "uid": uid.value if uid else "",
                "url": str(ev.url),
            })
    out.sort(key=lambda x: x["start"])
    return out


@mcp.tool()
def create_event(
    calendar: str,
    summary: str,
    start: str,
    end: str,
    location: str = "",
    description: str = "",
) -> dict:
    """Create an event. `start`/`end` are ISO-8601 (e.g. 2026-06-10T18:00:00+03:00)."""
    cal = find_calendar(calendar)
    ev = cal.save_event(
        dtstart=datetime.fromisoformat(start),
        dtend=datetime.fromisoformat(end),
        summary=summary,
        location=location or None,
        description=description or None,
    )
    return {"url": str(ev.url), "ok": True}


@mcp.tool()
def delete_event(url: str) -> dict:
    """Delete an event by its URL (from list_events / create_event)."""
    try:
        ev = caldav.Event(client=principal().client, url=url)
        ev.delete()
        return {"ok": True}
    except NotFoundError:
        return {"ok": False, "error": "not found"}


@mcp.tool()
def list_reminders(calendar: Optional[str] = None, include_completed: bool = False) -> list[dict]:
    """List VTODO items (Apple Reminders)."""
    cals = [find_calendar(calendar)] if calendar else principal().calendars()
    out = []
    for cal in cals:
        try:
            todos = cal.todos(include_completed=include_completed)
        except Exception:
            continue
        for t in todos:
            v = t.vobject_instance.vtodo
            summ = getattr(v, "summary", None)
            due = getattr(v, "due", None)
            status = getattr(v, "status", None)
            out.append({
                "calendar": cal.get_display_name(),
                "summary": summ.value if summ else "",
                "due": str(due.value) if due else "",
                "status": status.value if status else "",
                "url": str(t.url),
            })
    return out


if __name__ == "__main__":
    mcp.run()
