"""Importing this package registers all API routes on the shared router."""

from studybridge.api import auth_api  # noqa: F401
from studybridge.api import management  # noqa: F401
from studybridge.api import tutoring  # noqa: F401
from studybridge.api import advising  # noqa: F401
