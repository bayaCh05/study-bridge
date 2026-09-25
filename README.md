# Study Bridge

A tutoring and advising web platform, built as a school project with **Python's built-in `http.server`
module only** (no Django/Flask/FastAPI).

## Status

Step 0 done: bare HTTP server, static file serving, health check, routing skeleton, error handling.

## Requirements

- Python 3.10+
- No `pip install` needed — everything used is in the standard library.

## Run it

```bash
python3 run.py
```

Then open http://127.0.0.1:8000/ in a browser.

Environment variables (all optional, default shown):

```bash
HOST=127.0.0.1 PORT=8000 python3 run.py
```

On the Ubuntu Server VM, this becomes:

```bash
HOST=0.0.0.0 PORT=8000 python3 run.py
```

so the client VMs on the network can reach it at `http://192.168.100.10:8000`.

## Test it

```bash
python3 -m unittest discover tests
```

## Architecture

```
Browser (Client VM)  ──HTTP──▶  ThreadingHTTPServer (Server VM)
   HTML/JS pages                   ├── /static/...    → serves files from static/
   fetch('/api/...')               ├── /api/...       → router → handler functions → sqlite3
                                   └── /health        → server + DB status
```

## Project layout

```
study-bridge/
├── run.py
├── studybridge/
│   ├── config.py    # HOST, PORT, paths (from env vars)
│   ├── server.py    # request handler, static files, JSON helpers, error handling
│   └── router.py    # route registration and matching
├── static/
│   ├── index.html
│   └── css/style.css
└── tests/
```
