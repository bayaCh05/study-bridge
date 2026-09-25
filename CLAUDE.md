# CLAUDE.md — Study Bridge (Python `http.server`)

You are Claude Code, helping a student build **Study Bridge**, a tutoring and advising web platform, as a school
project. **Course requirement: the server must be built with Python's built-in `http.server` module.** No web
frameworks (no Django, Flask, FastAPI, etc.).

The student is learning. Build the app **one step at a time**, explain what you did and why, and **stop at the end of
every step** so they can test it, understand it, and commit it.

## The app

Four roles, each with its own dashboard after login:

| Role        | Can do |
|-------------|--------|
| Student     | Book a tutoring session from a tutor's free slots; request an office-hour appointment with an advisor; see their bookings and requests; download recommendation letters written for them |
| Tutor       | Submit availability slots; accept / decline / cancel bookings; write a session report after a session |
| Advisor     | Accept / reject office-hour requests; upload recommendation letters for a student |
| Management  | Add, edit, deactivate and remove students, tutors and advisors (full CRUD); see all bookings |

Cross-cutting requirements: **authentication** (login, logout, role-based access) and graceful handling of
**server down** and **network issues**.

## Deployment context

The app is developed on a MacBook (Apple M2, macOS), then deployed on an **Ubuntu Server VM** at `192.168.100.10`
(VirtualBox internal network `intnet`). Two **Ubuntu Desktop client VMs** open it in their web browser at
`http://192.168.100.10:8000`. So:
- The server must bind to a configurable host/port: `127.0.0.1:8000` on the Mac, `0.0.0.0:8000` on the VM.
- Nothing macOS-specific in the code. Paths via `pathlib`.

## Stack — standard library only

- Python 3.10+ (check with `python3 --version`). **Do not use the `cgi` module** (removed in Python 3.13).
- `http.server.ThreadingHTTPServer` + a `BaseHTTPRequestHandler` subclass.
- `sqlite3` for the database (one file, `data/studybridge.db`), with foreign keys on.
- `hashlib.pbkdf2_hmac` + `secrets` for password hashing and session tokens; `hmac.compare_digest` for comparisons.
- `http.cookies`, `json`, `urllib.parse`, `logging`, `unittest`, `threading`, `datetime`, `base64`.
- Front end: static **HTML + CSS + vanilla JavaScript** served by the same server. Pages call a **JSON API** with
  `fetch`. Optional Bootstrap 5 via CDN for styling is fine **only if the client VMs have internet** (they do, via NAT);
  otherwise plain CSS.
- No `pip install` needed to run the app. Everything above is built in.

## Architecture

```
Browser (Client VM)  ──HTTP──▶  ThreadingHTTPServer (Server VM)
   HTML/JS pages                   ├── /static/...    → serves files from static/
   fetch('/api/...')               ├── /api/...       → router → handler functions → sqlite3
                                   └── /health        → server + DB status
```

- **Pages** (`/`, `/login`, `/student`, `/tutor`, `/advisor`, `/management`) are static HTML files. Their JS loads data
  from the API. Display user data with `textContent`, never `innerHTML`, to prevent XSS.
- **API** returns JSON only, with correct HTTP status codes (200, 201, 400, 401, 403, 404, 405, 409, 413, 500, 503).
  Error format: `{"error": "human readable message"}`.
- **Routing**: a small router that maps `(method, path pattern)` → function, supporting path parameters like
  `/api/bookings/{id}`. Unknown path → 404, known path wrong method → 405.

## Project layout (target)

```
study-bridge/
├── CLAUDE.md
├── README.md
├── run.py                 # entry point: python3 run.py
├── studybridge/
│   ├── __init__.py
│   ├── config.py          # HOST, PORT, DB path, session lifetime, max body size (from env vars)
│   ├── server.py          # handler class, static files, request/response helpers, error handling
│   ├── router.py          # route registration and matching
│   ├── db.py              # connection helper, schema creation, transactions
│   ├── schema.sql
│   ├── auth.py            # password hashing, sessions, current user, role guard
│   ├── seed.py            # demo users: python3 -m studybridge.seed
│   └── api/
│       ├── auth_api.py
│       ├── management.py
│       ├── tutoring.py    # availability, bookings, reports
│       └── advising.py    # office hours, letters
├── static/
│   ├── css/style.css
│   ├── js/api.js          # shared fetch wrapper (timeouts, errors, offline banner)
│   ├── index.html  login.html  student.html  tutor.html  advisor.html  management.html
│   └── offline.html
├── data/                  # SQLite db + uploaded letters (git-ignored)
├── logs/                  # (git-ignored)
└── tests/
```

## Data model (SQLite)

- **users**: id, full_name, email (unique), password_hash, salt, role (`student`/`tutor`/`advisor`/`management`,
  CHECK constraint), is_active, created_at.
- **sessions**: token (primary key, random 32 bytes hex), user_id, created_at, expires_at.
- **availability**: id, tutor_id, start_at, end_at (ISO datetimes). Future only, end > start, no overlap per tutor.
- **bookings**: id, student_id, availability_id (**UNIQUE** → prevents double booking), subject, status
  (`pending`/`confirmed`/`declined`/`cancelled`/`completed`), created_at, updated_at.
- **session_reports**: id, booking_id (UNIQUE), attended (0/1), notes, created_at.
- **office_hour_requests**: id, student_id, advisor_id, requested_at, reason, status
  (`pending`/`accepted`/`rejected`), advisor_comment, created_at, updated_at.
- **letters**: id, advisor_id, student_id, title, stored_filename, original_filename, size_bytes, uploaded_at.
  Files stored in `data/letters/` with random names, never under `static/`.

Time zone: store datetimes in ISO 8601 with the `Africa/Tunis` offset (use `zoneinfo`).

## Rules for you (Claude Code)

1. **One step at a time.** At the end of a step, print: what you built, files touched, how to test it by hand (commands,
   URLs, demo accounts), and the test command. Then **stop and wait** for the student to say "next".
2. **Explain as you go** in simple terms, especially HTTP concepts when they first appear: request line, method, headers,
   body, status codes, `Content-Type`, `Content-Length`, cookies, why threading matters.
3. **Tests for every step** with `unittest` (`python3 -m unittest discover tests`). Tests start the real server on a
   random free port in a background thread, use a temporary database, and call it with `urllib.request`.
4. **Commit at the end of each step** (`Step N: ...`), after asking the student.
5. **Security by default:**
   - Every API route declares which roles may call it; check the session on every request.
   - Users only see and change their own data; always check ownership of IDs from the URL or body.
   - SQL: **parameterized queries only** (`?` placeholders). Never build SQL with f-strings.
   - Session cookie: `HttpOnly`, `SameSite=Strict`, `Path=/`, expires after 8 hours. Delete the session row on logout.
   - Static file serving must block path traversal (`..`, absolute paths): resolve the path and confirm it stays inside
     `static/`.
   - Reject request bodies larger than the configured max (413). Reject non-JSON bodies on JSON routes (415).
   - Never return stack traces to the client. Log them server-side, send `{"error": "Internal server error"}`.
6. Readable over clever. Small functions. English names. Comments only where the "why" isn't obvious.
7. Don't add features beyond this file without asking. If something is ambiguous, ask one question.
8. Never commit `data/`, `logs/`, `__pycache__/`, `.env`.

---

## Steps

### Step 0 — Bare HTTP server
- `run.py`, `config.py` (HOST, PORT from env with defaults `127.0.0.1` / `8000`), `server.py`, `router.py`.
- Handler with `do_GET`, `do_POST`, `do_PUT`, `do_DELETE`; helpers `send_json(status, data)`, `read_json()`,
  `send_file(path)` with correct `Content-Type`.
- Serve `static/index.html` at `/` and files under `/static/`.
- `GET /health` → `{"status": "ok"}`.
- 404 and 405 handling; catch-all 500 handler; request logging with method, path, status, duration.
- Graceful shutdown on Ctrl+C.
- `.gitignore`, `README.md`, `git init`.
- **Explain:** what happens when the browser opens `http://127.0.0.1:8000/` (TCP connection → request → handler → response).
- **Tests:** `/` returns 200 HTML; `/health` returns JSON; unknown path 404; `/static/../run.py` blocked.

### Step 1 — Database and seed data
- `schema.sql` with all tables above, foreign keys, CHECK constraints, UNIQUE constraints.
- `db.py`: open a connection per request (sqlite connections aren't shared across threads), `row_factory = sqlite3.Row`,
  `PRAGMA foreign_keys = ON`, `busy_timeout`, a transaction context manager.
- Create the schema at startup if missing.
- `python3 -m studybridge.seed` creates one demo user per role and prints the credentials.
- `/health` now also checks the DB: `{"status": "ok", "database": "ok"}` or **503** with `"database": "down"`.
- **Tests:** schema creates; constraints reject a bad role and a double booking at the DB level.

### Step 2 — Authentication and roles
- Password hashing with `pbkdf2_hmac` (sha256, random salt, 200 000+ iterations).
- `POST /api/login` (email + password → session cookie), `POST /api/logout`, `GET /api/me` (current user + role).
- Inactive users can't log in. Same error message for wrong email or wrong password.
- `require_roles(...)` guard used by every protected route: 401 if not logged in, 403 if wrong role.
- `login.html` + JS: on success, redirect to the page for the user's role. Each role page calls `/api/me` on load and
  sends the user back to `/login` if they get 401, or shows "access denied" on 403.
- **Explain:** cookies and sessions — how the server remembers who you are with a stateless protocol.
- **Tests:** login OK/KO, logout invalidates the session, expired session → 401, wrong role → 403.

### Step 3 — Management CRUD
- API: list users (filter by role, search), create, update, deactivate/reactivate, delete. Management only.
  Management cannot delete or deactivate themselves. Email must be unique (409 on conflict).
- `management.html`: table of users with filter/search, forms to create/edit, confirm before delete.
- **Tests:** only management allowed; unique email enforced; can't delete self.

### Step 4 — Tutor availability
- API: tutor lists own upcoming slots, adds a slot, deletes a slot that has no active booking.
- Validation: future only, end > start, no overlap with the tutor's other slots (400 with a clear message).
- `tutor.html`: list + add form.
- **Tests:** overlap rejected; past slot rejected; tutor can't delete another tutor's slot.

### Step 5 — Booking
- Student API: list tutors and their free future slots; book a slot with a subject → `pending`.
- Tutor API: list own bookings; accept (`confirmed`) or decline (`declined`, slot free again).
- Student or tutor can cancel a pending/confirmed booking before it starts (`cancelled`, slot free again).
- Double booking impossible even with two simultaneous requests: rely on the UNIQUE constraint inside a transaction;
  return **409** "This slot was just taken" on conflict. When a booking is declined/cancelled, the slot must be bookable
  again (explain how you handle the UNIQUE constraint, e.g. deleting the cancelled booking's slot link or a partial
  unique index on active statuses).
- Only valid status transitions allowed (e.g. can't accept a cancelled booking).
- `student.html` and `tutor.html` sections for this.
- **Tests:** concurrent booking test with two threads → exactly one succeeds; ownership checks; invalid transitions → 400/409.

### Step 6 — Session reports
- After a confirmed session has ended, the tutor marks it completed and writes a report (attended + notes).
- Student sees that the session is completed (ask the student whether the notes should be visible to them).
- **Tests:** can't report a future session; only that tutor; one report per booking.

### Step 7 — Office hours
- Student: request office hours with an advisor (time + reason). Advisor: list pending, accept/reject with an optional
  comment. Student sees status + comment.
- **Tests:** only the targeted advisor responds; can't respond twice.

### Step 8 — Recommendation letters
- Advisor uploads a PDF for a student. To avoid parsing multipart by hand, the browser reads the file with `FileReader`
  and sends JSON `{student_id, title, filename, content_base64}`. Server checks: PDF magic bytes `%PDF`, max 5 MB,
  stores the file in `data/letters/` under a random name.
- `GET /api/letters` (own letters by role; management sees all) and `GET /api/letters/{id}/download` with a permission
  check, `Content-Type: application/pdf`, `Content-Disposition: attachment`.
- **Tests:** another student gets 403; non-PDF rejected; oversized upload → 413.

### Step 9 — Server down and network issues
Server side:
- Every handler wrapped: DB errors (`sqlite3.OperationalError`, e.g. locked or missing file) → 503 with a clear
  message, logged. Unexpected errors → 500, logged with traceback, generic message to the client.
- Socket timeout on the server so a stuck client can't hold a thread forever.
- Logging to console and `logs/server.log` (rotating).

Client side (`static/js/api.js`, used by every page):
- `apiFetch()` wrapper with a **timeout** (`AbortController`, e.g. 8 s), **one automatic retry** for GET requests,
  and clear messages: "Server unreachable — check your network or try again later" (network error / timeout),
  "Server error, please try again" (5xx), the API's own message for 4xx.
- A banner that appears when the browser goes offline (`offline`/`online` events) and when `/health` stops answering;
  it polls `/health` every 10 s while down and disappears when the server is back.
- Disable submit buttons while a request is in flight to avoid double submissions.
- **Manual test scenarios to write in README:** stop the server while a page is open; unplug the VM network cable
  (VirtualBox: uncheck "Cable connected" on Adapter 2); rename the DB file while running.
- **Tests:** `/health` returns 503 when the DB is unavailable; handler returns 503 JSON on a simulated DB error.

### Step 10 — Polish, then deploy on the VMs
- Consistent navigation per role, success/error messages after every action, empty states, dashboard counts.
- Update `README.md`: features per role, how to run, demo accounts, tests, the architecture diagram above.
- Deployment on the Ubuntu Server VM (only when the student asks):
  - `git clone` the repo, `HOST=0.0.0.0 PORT=8000 python3 run.py`, seed demo users.
  - Optional `systemd` service so it restarts automatically; `sudo ufw allow 8000/tcp` if the firewall is on.
  - From Client1 and Client2: open `http://192.168.100.10:8000`, log in as different roles at the same time, and
    repeat the network-issue scenarios from Step 9.

---

## How the student will talk to you

- "next" → start the next step.
- "explain X" → explain that part simply, with an example from this project.
- "I got this error: ..." → find the cause, fix it, explain what went wrong.
