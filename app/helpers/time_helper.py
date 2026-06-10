from datetime import datetime, timezone


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with timezone info."""
    return datetime.now(timezone.utc).isoformat()
