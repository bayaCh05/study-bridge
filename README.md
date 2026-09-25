# Study Bridge

A tutoring and advising web platform, built as a school project with **Python's built-in `http.server`
module only** (no Django/Flask/FastAPI).

## Status

Steps 0-9 done: bare HTTP server, database, auth, management CRUD, tutor availability, booking,
session reports, office hours, recommendation letters, and graceful handling of server/network issues.
(Full per-role feature writeup and polish come in Step 10.)

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

Other environment variables (all optional):

| Variable | Default | Meaning |
|---|---|---|
| `SESSION_LIFETIME_HOURS` | `8` | How long a login session stays valid |
| `MAX_BODY_SIZE` | `8388608` (8 MB) | Reject request bodies larger than this (413) |
| `REQUEST_TIMEOUT_SECONDS` | `30` | Socket timeout so a stuck client can't hold a thread forever |

## Demo accounts

Run `python3 -m studybridge.seed` to create one demo user per role (safe to re-run; it skips existing
emails and prints the passwords to the console):

| Role | Email | Password |
|---|---|---|
| Student | student@studybridge.test | student123 |
| Tutor | tutor@studybridge.test | tutor123 |
| Advisor | advisor@studybridge.test | advisor123 |
| Management | management@studybridge.test | management123 |

## Test it

```bash
python3 -m unittest discover tests
```

## Manual test scenarios (server down / network issues)

These aren't practical to automate, so test them by hand:

- **Stop the server while a page is open.** With a dashboard open in the browser, kill the `python3 run.py`
  process. Within ~10s a red banner should appear: "Server unreachable — check your network or try again
  later." It should disappear again once the server is restarted.
- **Unplug the VM network cable.** On the Ubuntu Server VM in VirtualBox, uncheck "Cable connected" on
  Adapter 2 while a client VM has a page open. Same banner should appear; re-checking the cable should make
  it go away.
- **Rename the DB file while running.** `mv data/studybridge.db data/studybridge.db.bak` while the server is
  running, then try any action that touches the database — it should fail with a clear "Service temporarily
  unavailable" message (503), not a stack trace or a hang. `GET /health` should also report
  `"database": "down"`. Renaming it back should make everything work again immediately (no restart needed).
- **Trigger the offline banner from the browser's own network state:** DevTools → Network tab → set to
  "Offline". The banner should appear immediately via the browser's `offline` event, without waiting for a
  failed request.

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
