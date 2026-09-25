"""Central place for settings that change between the Mac and the VM.

Everything is read from environment variables so we never hard-code a path
or address that only makes sense on one machine (course requirement: no
macOS-specific code).
"""

import os
from pathlib import Path

# Project root: the folder that contains run.py, static/, data/, etc.
BASE_DIR = Path(__file__).resolve().parent.parent

# On the Mac we bind to 127.0.0.1 (only this machine can connect).
# On the Ubuntu Server VM we run: HOST=0.0.0.0 PORT=8000 python3 run.py
# so the client VMs on the intnet network can reach it.
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

DB_PATH = DATA_DIR / "studybridge.db"

# Used from Step 2 onward.
SESSION_LIFETIME_HOURS = int(os.environ.get("SESSION_LIFETIME_HOURS", "8"))

# Reject request bodies larger than this (413). Must comfortably exceed the
# base64-inflated size of the largest legitimate upload: a 5 MB PDF letter
# becomes ~6.7 MB once base64-encoded and wrapped in JSON, so this needs
# real headroom above MAX_LETTER_SIZE, not just a round "big enough" number.
MAX_BODY_SIZE = int(os.environ.get("MAX_BODY_SIZE", str(8 * 1024 * 1024)))  # 8 MB

# Recommendation letters (Step 8): max size of the decoded PDF file itself.
MAX_LETTER_SIZE = 5 * 1024 * 1024  # 5 MB

# Socket timeout (Step 9): a client that goes silent mid-request (or never
# sends one) can't hold a server thread open forever.
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "30"))
