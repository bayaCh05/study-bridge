#!/usr/bin/env python3
"""Entry point: python3 run.py

Reads HOST/PORT from the environment (see studybridge/config.py) so the
same code runs on the Mac (127.0.0.1:8000) and on the Ubuntu Server VM
(HOST=0.0.0.0 PORT=8000 python3 run.py).
"""

from studybridge.server import run_server

if __name__ == "__main__":
    run_server()
