from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def conversation_title(conversation: dict) -> str:
    title = " ".join((conversation.get("title") or "").split())
    return title or "Nueva conversación"


def _local_datetime(value: str, timezone_name: str) -> datetime:
    local_timezone = ZoneInfo(timezone_name)
    updated = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return updated.astimezone(local_timezone)


def conversation_group(value: str, timezone_name: str, now: datetime | None = None) -> str:
    updated = _local_datetime(value, timezone_name)
    today = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(timezone_name)).date()
    if updated.date() == today:
        return "Hoy"
    if updated.date() == today - timedelta(days=1):
        return "Ayer"
    return "Anteriores"


def conversation_date(value: str, timezone_name: str, now: datetime | None = None) -> str:
    updated = _local_datetime(value, timezone_name)
    local_timezone = ZoneInfo(timezone_name)
    today = (now or datetime.now(timezone.utc)).astimezone(local_timezone).date()
    if updated.date() == today:
        return f"Hoy, {updated:%H:%M}"
    if updated.date() == today - timedelta(days=1):
        return f"Ayer, {updated:%H:%M}"
    return f"{updated:%d/%m/%Y · %H:%M}"
