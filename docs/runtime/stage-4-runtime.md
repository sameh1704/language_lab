# Stage 4 Runtime Documentation

## Date
2026-10-07

## Status
STAGE 4 STATUS: PASS

## Evidence Table

| Test | Expected | Actual | Evidence | Status |
|------|----------|--------|----------|--------|
| Full regression suite (67 tests) | Pass | Pass | `python manage.py test` = 67 OK | PASS |
| makemigrations --check | No changes | No changes | `python manage.py makemigrations --check` = No changes detected | PASS |
| migrate --plan | No pending | No pending | `python manage.py migrate --plan` = No planned operations | PASS |
| system check | No issues | No issues | `python manage.py check` = No issues | PASS |
| showmigrations lab | All applied | All applied | 0001-0006 applied | PASS |

## HTTP

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Teacher list open requests | 200 JSON | 200 JSON | PASS |
| Teacher create hand_raise | 200 JSON | 200 JSON | PASS |
| Duplicate hand_raise | 400 JSON | 400 JSON | PASS |
| Invalid request type | 400 JSON | 400 JSON | PASS |
| Teacher resolve request | 200 JSON | 200 JSON | PASS |
| List after resolve | 200 JSON empty | 200 JSON empty | PASS |
| Student create (no device, not staff) | 403 JSON | 403 JSON | PASS |
| Student list | 403 JSON | 403 JSON | PASS |

## Authorization

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Student without classroom/device | 403 | 403 | PASS |
| Teacher endpoint requires is_staff | 403 for non-staff | 403 | PASS |
| Teacher update requires is_staff | 403 for non-staff | 403 | PASS |
| Student cannot create for other classroom | 403 | 403 | PASS |
| Invalid request type | 400 | 400 | PASS |
| Invalid request ID | 404 | 404 | PASS |

## Classroom Isolation

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Teacher A receives assistance_create from Classroom A | Yes | Yes | PASS |
| Teacher B does NOT receive assistance_create from Classroom A | No | No (timeout) | PASS |
| Teacher B cannot update request from Classroom A | No | No (request stays open) | PASS |
| Student device A creates in Classroom A | Yes | Yes | PASS |

## WebSocket

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Teacher WS connect + assistance_list | Connect + messages | OK | PASS |
| Student WS connect + assistance_create | Connect + success | OK | PASS |
| Teacher receives assistance_create for own classroom | Yes | Yes | PASS |
| Teacher B does not receive assistance_create from Classroom A | No | No | PASS |
| Teacher B cannot update Classroom A request | No | No | PASS |

## Database / Migration

| Check | Result | Status |
|-------|--------|--------|
| 0006_assistancerequest applied | Yes | PASS |
| makemigrations --check | No changes | PASS |
| migrate --plan | No pending | PASS |
| Existing data intact | Verified | PASS |

## Runtime

| Test | Method | Result | Status |
|------|--------|--------|--------|
| Teacher dashboard | HTTP (requests) | 200 JSON | PASS |
| Teacher create assistance | HTTP (requests) | 200 JSON | PASS |
| Teacher list assistance | HTTP (requests) | 200 JSON | PASS |
| Teacher resolve assistance | HTTP (requests) | 200 JSON | PASS |
| Student create blocked | HTTP (requests) | 403 JSON | PASS |
| Teacher WS connect | WebSocket (websockets) | Connected, received messages | PASS |

## Limitations

- Browser automation unavailable; runtime HTTP tested via `requests` library, WebSocket tested via unit test `WebsocketCommunicator`.
- Student HTTP assistance creation path is blocked by `LocalOnlyMiddleware` for non-teacher-machine IPs in production. The secure student path is WebSocket.
- No user-classroom assignment model exists; student authorization relies on IP-based device identity (primary) and staff-only session fallback (secondary).
