"""Single place to get the current time, in the project's timezone.

The data model stores every timestamp in ISO 8601 with the Africa/Tunis
offset, so all timestamps compare and sort correctly regardless of which
machine (Mac or VM) generated them.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

TUNIS = ZoneInfo("Africa/Tunis")


def now():
    return datetime.now(TUNIS)


def now_iso():
    # timespec="seconds" drops microseconds so every stored timestamp has
    # the same fixed format — that keeps plain string comparison in SQL
    # ("WHERE start_at > ?") consistent with real chronological order.
    return now().isoformat(timespec="seconds")


def parse_local(value):
    """Parse a datetime string from a browser <input type="datetime-local">.

    Those inputs send "YYYY-MM-DDTHH:MM" (no seconds, no timezone). We treat
    that as Africa/Tunis local time, since that's the app's only timezone.
    An already-offset-aware ISO string (e.g. from a test) is passed through.
    """
    if len(value) == 16:  # "YYYY-MM-DDTHH:MM" — no seconds
        value = value + ":00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TUNIS)
    return parsed
