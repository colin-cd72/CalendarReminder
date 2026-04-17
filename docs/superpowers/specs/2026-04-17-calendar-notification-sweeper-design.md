# Calendar Notification Sweeper — Design

**Date:** 2026-04-17
**Owner:** deford@gmail.com
**Status:** Design approved, pending spec review

## Problem

Google Calendar auto-inserts two classes of events that generate unwanted notifications:

1. **Gmail-extracted events** — flights, hotel reservations, restaurant bookings, package deliveries.
2. **Reclaim-created events** — tasks, habits, decompress blocks, buffer time, travel-time blocks, personal-sync blocks.

These events are useful to *see* on the calendar but produce noise when they fire notifications. Real meetings and appointments should continue to notify normally. Google Calendar's built-in per-category notification settings are either too coarse or don't cover both sources uniformly.

## Goal

A local, scheduled tool that, once a day, sweeps upcoming calendar events and removes notifications from events matching high-confidence "auto-insert" fingerprints. Everything else — real meetings, manually created appointments, anything the rules don't match — is left completely untouched.

**Non-goals:**
- Not deleting events.
- Not modifying anything about the event other than `reminders`.
- Not trying to positively classify "important" meetings. Silence is opt-in via rules; keep is the default.

## Approach

A Python CLI script authenticating to Google Calendar via OAuth, run daily by Windows Task Scheduler on the user's local PC. Classification rules live in a user-editable YAML config. Every matched event is logged with the rule that caught it, enabling after-the-fact review and rule tuning.

Rejected alternatives:
- **Google Calendar built-in settings only** — too coarse; can't selectively handle the Reclaim + Gmail combination and can't catch edge cases.
- **Hybrid (settings + logging script)** — adds complexity without a clear win once we're already building a script.

## Architecture

**Runtime shape:** one stateless CLI script. Each run: authenticate → fetch upcoming events → classify each → patch the ones matching silence rules → log → exit. No daemon, no server.

**Directory layout** (`D:\Calendar Reminder\`):

```
calendar_reminder/
  main.py              # CLI entry point
  auth.py              # OAuth token load/refresh/store
  classify.py          # Pure function: event -> ("silence", reason) | ("keep", None)
  sweeper.py           # Fetches events, calls classifier, patches reminders
  config.yaml          # User-editable silence rules
  credentials.json     # OAuth client secret (gitignored)
  token.json           # User OAuth token (gitignored)
  logs/                # Daily log files (gitignored)
    sweep-YYYY-MM-DD.log
  tests/
    test_classify.py   # Unit tests for classifier
  requirements.txt
  .gitignore
```

**Component responsibilities:**

| File | Responsibility |
|---|---|
| `main.py` | CLI. Flags: `--dry-run`, `--days N` (default 30), `--verbose`. |
| `auth.py` | One public function `get_service()` that returns an authenticated `googleapiclient` service. Handles first-run browser flow and token refresh. |
| `classify.py` | Pure function `classify(event, config) -> ("silence", rule_name) | ("keep", None)`. No side effects; easily unit-tested. |
| `sweeper.py` | Orchestration: fetch events for window, call `classify` per event, patch reminders when silenced and not already empty, emit log lines. |
| `config.yaml` | Silence rules, never-silence allow-list, scan window settings. |

**Idempotency:** events whose `reminders.overrides` is already empty and `useDefault` is already false are logged as SKIP and not patched. Running the script 10 times in a row has the same effect as running it once.

## Classification rules

Rule of thumb: if an event matches *any* silence rule, its reminders are cleared. If it matches none, it's left alone. `never_silence` matches override silence rules.

```yaml
# config.yaml
silence_rules:
  # Tier 1 — Gmail-extracted events (flights, hotels, reservations, packages)
  - name: gmail_auto_events
    match:
      eventType: fromGmail

  # Tier 1 — Reclaim, identified by organizer domain
  - name: reclaim_by_organizer
    match:
      organizer_email_endswith: "@reclaim.ai"

  # Tier 1 — Reclaim, identified by its custom metadata
  - name: reclaim_by_extended_property
    match:
      has_extended_property_prefix: "reclaim"

  # Tier 3 — Title safety net
  - name: travel_title_patterns
    match:
      title_regex: "^(Travel Time|Travel to|Flight )"

never_silence:
  title_contains: []       # e.g. ["IMPORTANT", "DO NOT MISS"]
  calendar_ids: []         # e.g. ["work-cal@group.calendar.google.com"]

scan:
  days_ahead: 30
  include_past: false
```

**Reliability of each signal:**

| Tier | Signal | Catches | Reliability |
|---|---|---|---|
| 1 | `eventType == "fromGmail"` | Flights, hotels, reservations, packages | ~100% |
| 1 | `organizer.email` ends with `@reclaim.ai` | All Reclaim events | ~100% |
| 1 | `extendedProperties.private` has key prefixed `reclaim` | Backup signal for Reclaim events in case organizer domain changes | ~100% |
| 3 | Title regex | Anything the Tier 1 signals miss | Fuzzy — last resort |

**What "silence" does:** sets `reminders.useDefault = false` and `reminders.overrides = []`. No other event field is modified.

## Data flow

```
1. main.py parses CLI args
2. auth.py returns authenticated service (refreshes token if needed)
3. sweeper.py calls events.list() with timeMin=now, timeMax=now+days_ahead
4. For each event:
   a. classify(event, config) -> (action, rule_name)
   b. If action == "silence" and reminders not already empty:
      - (unless --dry-run) call events.patch(id, body={reminders:{useDefault:false, overrides:[]}})
      - log SILENCED line
   c. If action == "silence" but reminders already empty: log SKIP
   d. If action == "keep": log KEPT (only in --verbose mode)
5. Print end-of-run SUMMARY; exit 0
```

## Error handling

Principle: never crash the whole sweep for one bad event or transient failure.

| Failure | Response |
|---|---|
| Network blip / HTTP 5xx | Exponential backoff: 1s, 2s, 4s. Give up on that event, continue sweep. |
| HTTP 429 (rate limit) | Backoff + retry. Volume is tiny (<100 events/day); unlikely. |
| Token expired / revoked | Log clearly, exit nonzero. Next interactive run re-does the browser flow. |
| Malformed event (missing fields) | Log SKIP with reason, do not touch, continue. |
| Malformed `config.yaml` | Fail fast at startup with a readable message. No sweep runs. |

## Logging

File: `logs/sweep-YYYY-MM-DD.log`, append mode (multiple runs per day accumulate).

Format — one line per event:

```
2026-04-17 06:00:01 | SILENCED | evt=abc123 | "Flight UA1234 to SFO" | rule=gmail_auto_events
2026-04-17 06:00:01 | KEPT     | evt=def456 | "1:1 with Sarah"       | rule=none
2026-04-17 06:00:01 | SKIP     | evt=xyz789 | "Focus Time"           | reason=already_silenced
2026-04-17 06:00:02 | ERROR    | evt=err001 | "..."                  | exc=HttpError 500
```

End-of-run summary line:

```
2026-04-17 06:00:03 | SUMMARY: scanned=87 silenced=23 kept=58 skipped=5 errors=1 duration=2.3s
```

A tiny cleanup step at the top of each run deletes log files older than 30 days.

## Authentication

- **OAuth client type:** Desktop app (Google Cloud Console)
- **Scope:** `https://www.googleapis.com/auth/calendar.events`
  - Grants read + patch for events only. No access to calendar lists, free/busy, or other user data.
- **First run:** opens system browser → user approves → token saved to `token.json`.
- **Subsequent runs:** `token.json` auto-refreshes; no browser prompt.
- **`credentials.json` and `token.json` are gitignored.**

## Scheduling

Windows Task Scheduler task:

- **Trigger:** Daily at 06:00 local time.
- **Action:** `pythonw.exe D:\Calendar Reminder\main.py` (no console window).
- **Settings:** "Run whether user is logged on or not", "If task is missed, run as soon as possible".
- **Kill switch:** disable the task in Task Scheduler; no other rollback needed.

## Testing

- **`tests/test_classify.py`** — unit tests for the classifier. Pure function, no mocks, no network. Fixtures cover:
  - Each silence rule matching
  - An event matching no rule (expect KEEP)
  - An event matching a silence rule but also `never_silence` (expect KEEP)
  - Edge cases: missing `organizer`, missing `extendedProperties`, empty title, non-string title fields
- **No live-API tests.** The built-in `--dry-run` mode against the real calendar is the integration test — it uses real data shapes without any risk of mutation.
- **Run:** `pytest` from the project root.

## Rollout plan

```
Day 0  → python main.py --dry-run --days 7
         Review logs/sweep-*.log. Confirm nothing "real" got matched.

Day 0  → python main.py --days 7
         Live run on a narrow window. Open Google Calendar, spot-check.

Day 1  → python main.py --dry-run
         Full 30-day dry run.

Day 1  → python main.py
         Full 30-day live run.

Day 1  → Enable the scheduled task in Windows Task Scheduler.
```

If the log shows a real meeting being silenced, add its title substring or the calendar ID to `never_silence` in `config.yaml` and re-run. No code changes needed.

## Out of scope

- Silencing based on event body/description content analysis.
- Touching recurring-event masters (we only modify individual instances inside the scan window).
- A GUI or web UI.
- Cross-account support (single Google account only).
- Any form of positive "meeting detection" heuristics — silence rules are the only logic.
