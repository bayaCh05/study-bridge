# Study Bridge

A tutoring and advising web platform, built as a school project with **Python's built-in `http.server`
module only** (no Django/Flask/FastAPI).

## Status

All 10 steps done: bare HTTP server, database, auth, management CRUD, tutor availability, booking,
session reports, office hours, recommendation letters, graceful handling of server/network issues, and
final polish (consistent navigation, success/error feedback, empty states, dashboard counts).

## Features per role

| Role | Can do |
|---|---|
| **Student** | Browse tutors and their free slots and book one; see all own bookings and their status; request office hours with an advisor and see the advisor's response; download recommendation letters written for them |
| **Tutor** | Add/delete availability slots (no overlaps, future only); accept/decline incoming bookings; cancel a confirmed booking; mark a past confirmed session complete with an attendance + notes report |
| **Advisor** | See all office-hour requests addressed to them and accept/reject with an optional comment; upload a PDF recommendation letter for a student; see letters they've uploaded |
| **Management** | Full CRUD on students/tutors/advisors/management accounts (filter/search, create, edit, deactivate/reactivate, delete); cannot deactivate or delete themselves |

Cross-cutting: session-cookie authentication with role-based access on every API route, and graceful
handling of server-down / network-down conditions (see "Manual test scenarios" below).

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

so other machines on the network can reach it — see "Deploying on 3 physical machines (mobile hotspot)"
below for the actual grading-demo setup, or `http://192.168.100.10:8000` for the original VirtualBox
`intnet` setup.

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

## Deploying on 3 physical machines (mobile hotspot)

For the "Good"/"Prestigious" grading tiers, the demo runs on **3 real physical machines** (not just
VirtualBox VMs) joined to the same **mobile hotspot** Wi-Fi network — one machine runs the server, the
other two act as clients. The app needs no separate "client install": a client machine only needs a web
browser, since the server serves the HTML/CSS/JS itself.

**1. Join all 3 machines to the same hotspot.** Turn on the phone's (or laptop's) mobile hotspot, and
connect all 3 machines (or their VMs, bridged — not NAT — to the host's Wi-Fi) to that same Wi-Fi network.

**2. On the server machine**, find the IP address the hotspot assigned it:

```bash
ip addr show | grep "inet "
```

Look for the address on the Wi-Fi interface (not `127.0.0.1`), e.g. `192.168.43.117`. This address can
change each time the hotspot is (re)joined — unlike the fixed `192.168.100.10` used on the VirtualBox
`intnet`, a hotspot hands out addresses by DHCP, so re-check it if the server is restarted on a different
network.

**3. On the server machine**, seed demo data (first time only) and run the server bound to all interfaces:

```bash
python3 -m studybridge.seed        # first time only
HOST=0.0.0.0 PORT=8000 python3 run.py
```

If a firewall is active (`sudo ufw status`), open the port:

```bash
sudo ufw allow 8000/tcp
```

**4. On each client machine**, confirm it can reach the server, then open it in a browser:

```bash
ping 192.168.43.117                        # replace with the server's actual IP
curl http://192.168.43.117:8000/health     # expect {"status": "ok", "database": "ok"}
```

Then open `http://192.168.43.117:8000/` in a browser and log in with one of the [demo accounts](#demo-accounts)
— each client machine should use a **different role** so the simultaneous-use scenarios in the grading
rubric are actually demonstrated (e.g. client 1 logs in as the student, client 2 as the tutor or advisor).

**5. Repeat the Step 9 network-issue scenarios across real machines**, not just VirtualBox cable toggles:
kill the server process, turn off the server machine's Wi-Fi, or have it leave the hotspot — each client's
offline banner should appear within ~10s and clear once connectivity returns.

**Prestigious tier (MITM demo):** this only works because the traffic is **plain HTTP, not HTTPS** — do
not add TLS to the server. A third physical machine on the same hotspot can run a MITM tool (e.g.
`arpspoof` + `wireshark`, or `ettercap`) to capture the plaintext login request between a client and the
server and show the credentials in the clear. This is a separate, explicit step to set up when you're
ready to rehearse it — ask then and we'll go through it together.

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
