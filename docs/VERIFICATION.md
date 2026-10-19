# Study Bridge — Verification Report

Verified 2026-10-20 against a live local instance (not just from memory/code review).

## Automated test suite

```bash
python3 -m unittest discover tests
```

**69/69 tests passing.** Covers schema constraints, auth, role guards, management CRUD, tutor
availability, concurrent booking (two real threads, exactly one succeeds), session reports, office
hours, letter upload/download, and simulated server/DB failure handling (500/503).

## Status codes — confirmed against the running server

| Code | Meaning | Verified by |
|---|---|---|
| 200 | OK | Every login, list, accept/decline, logout |
| 201 | Created | Creating a user, an availability slot |
| 400 | Bad request | Overlapping tutor slot rejected |
| 401 | Unauthorized | No session, and session after logout |
| 403 | Forbidden | Student hitting a management-only endpoint |
| 404 | Not found | Unknown route |
| 405 | Method not allowed | Wrong HTTP verb on a real route |
| 409 | Conflict | Duplicate email, double-booking the same slot |
| 413 | Payload too large | Oversized request body |
| 500 / 503 | Server/DB error | Covered by `tests/test_step9_resilience.py`'s simulated-failure tests |

## Full feature walkthrough — 36/36 checks passed

- **Auth**: all 4 roles log in, session cookie works, logout invalidates it
- **Management**: list/filter users, create, edit, deactivate, reactivate, delete, duplicate-email rejected
- **Tutor**: add availability, overlap rejected, accept/decline bookings
- **Student**: see tutors' free slots, book one, see it move from pending → confirmed, double-booking rejected
- **Office hours**: student requests, advisor accepts with a comment, student sees the update
- **Letters**: advisor uploads a PDF, student downloads it
- **Access control**: wrong role → 403, no session → 401, confirmed on protected routes
- **All 6 pages** (`/`, `/login`, `/student`, `/tutor`, `/advisor`, `/management`) load with 200

## Known caveat

Everything above is verified at the HTTP/API level and via the automated test suite. The pages have
not been visually rendered in an actual browser in this verification pass — only HTTP responses were
checked, not pixel-level layout/CSS. Given the pages are plain HTML/CSS with no complex layout this is
low-risk, but worth a quick manual look before the live demo.
