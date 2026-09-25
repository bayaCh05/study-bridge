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
    return now().isoformat()
