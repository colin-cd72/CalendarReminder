# Calendar Notification Sweeper — Design

**Date:** 2026-04-17
**Owner:** deford@gmail.com
**Status:** Design approved. Revised 2026-04-17 to ship as a Windows tray app packaged as a standalone `.exe` (Option D).

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

A Windows tray application, packaged as a single `.exe` via PyInstaller, that authenticates to Google Calendar via OAuth and runs the sweep once daily on an internal timer. The tray gives the user a visible entry point (sweep-now, open log, open config) without interfering with the default unattended behavior. Classification rules live in a user-editable YAML config in `%APPDATA%\CalendarReminder\`. The same codebase exposes a CLI (`main.py`) for headless/dev use.

Rejected alternatives:
- **Google Calendar built-in settings only** — too coarse; can't selectively handle the Reclaim + Gmail combination and can't catch edge cases.
- **Pure CLI with Windows Task Scheduler** — works, but the user explicitly asked for an app with a visible on-screen presence.
- **Full GUI window** — overkill for rarely-touched configuration; tray is enough.

## Architecture

**Runtime shape:** a long-running tray process that launches at Windows login and lives in the system tray. A background timer thread checks hourly whether the last sweep was ≥24h ago and triggers one if so. The tray menu also lets the user fire a sweep or dry-run on demand. Each individual sweep is still the stateless pattern from the original design: authenticate → fetch upcoming events → classify each → patch the ones matching silence rules → log → return counts. No daemon service, no server, no cloud.

**Source layout** (dev tree; same as GitHub repo):

```
calendar_reminder/
  __init__.py
  paths.py             # Resolves runtime dirs (frozen vs dev)
  config.py            # Loads + validates config.yaml
  classify.py          # Pure classifier function
  auth.py              # OAuth + service builder
  sweeper.py           # Fetch, classify, patch, log
  tray.py              # pystray UI, daily timer, first-run dialog
main.py                # CLI entry (dev + headless fallback)
config.yaml            # Default/template config (shipped with exe)
icon.ico               # Tray + exe icon
CalendarReminder.spec  # PyInstaller build recipe
tests/
  __init__.py
  test_classify.py
  test_config.py
  test_sweeper.py
requirements.txt
.gitignore
```

**Runtime data layout** (per-user; created on first run by the tray app):

```
%APPDATA%\CalendarReminder\
  config.yaml          # Live config (copied from shipped template on first run)
  credentials.json     # OAuth client secret (user drops this in — see setup)
  token.json           # OAuth user token (written by auth.py on first consent)
  state.json           # {"last_sweep_at": "2026-04-17T06:01:02Z"}
  logs\
    sweep-YYYY-MM-DD.log
```

Both locations matter: the **source layout** is what we build and test, the **runtime data layout** is where the packaged exe reads and writes. `paths.py` returns the right base directory for the current mode by checking `sys.frozen`.

**Component responsibilities:**

| File | Responsibility |
|---|---|
| `paths.py` | `app_data_dir()` returns `%APPDATA%\CalendarReminder` when frozen, `Path.cwd()` when running from source. Also convenience helpers for config/creds/token/state/log paths. |
| `config.py` | `load_config(path)`: parse YAML, validate required keys, fill defaults. |
| `classify.py` | Pure function `classify(event, config) -> ("silence", rule_name) | ("keep", None)`. |
| `auth.py` | `get_service(credentials_path, token_path)`: OAuth flow + token refresh, returns authenticated Calendar service. |
| `sweeper.py` | `sweep(service, config, dry_run=False, days_override=None) -> counts dict`. Orchestrates fetch → classify → patch → log. |
| `tray.py` | System-tray UI (pystray). Menu actions, daily timer thread, first-run setup dialog, state.json management. |
| `main.py` | Argparse CLI. Calls `sweep()` once and exits. Used for dev, debug, and headless runs. |
| `CalendarReminder.spec` | PyInstaller one-file recipe. Entry point: `tray.py`. Bundles `icon.ico` and the shipped `config.yaml` template. |

**Idempotency:** events whose `reminders.overrides` is already empty and `useDefault` is already `false` are logged as SKIP and not patched. Running the sweep 10 times in a row has the same effect as running it once.

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

## Tray UI

The tray icon appears immediately when `CalendarReminder.exe` launches. Left-click is a no-op; right-click opens the menu:

| Menu item | Action |
|---|---|
| Sweep now | Runs a live sweep in a background thread. Tooltip updates to "Sweeping…" then "Last: HH:MM (silenced N)". |
| Sweep now (dry run) | Same, but `dry_run=True` — nothing is patched. |
| Open today's log | Opens `%APPDATA%\CalendarReminder\logs\sweep-YYYY-MM-DD.log` in the default editor (`os.startfile`). |
| Open config | Opens `%APPDATA%\CalendarReminder\config.yaml` in the default editor. |
| Quit | Exits the tray process. No sweeps until next login or manual relaunch. |

Menu actions always run sweeps on a worker thread so the tray icon stays responsive. Concurrent sweep requests are rejected with a balloon-tip notification ("Sweep already in progress").

## Scheduling (in-app timer)

The tray app owns the schedule. Logic, running on a background thread:

```
every 60 minutes:
    read state.json -> last_sweep_at
    if now - last_sweep_at >= 24h:
        run sweep(dry_run=False)
        on success: write now to state.json
```

- **Auto-start on Windows login:** a `.lnk` shortcut is placed in the user's Startup folder (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`) by the first-run flow.
- **If the PC is off:** the timer naturally catches up — the next tick after login sees a stale `last_sweep_at` and runs.
- **Kill switch:** right-click tray → Quit. To disable permanently, delete the Startup shortcut (the first-run flow can also do this via an "Unregister auto-start" dev CLI flag).

## First-run setup flow

On tray launch, the app:

1. Ensures `%APPDATA%\CalendarReminder\` exists.
2. If `config.yaml` is missing there, copies the shipped template.
3. Checks for `credentials.json` in that directory.
4. If missing: shows a tkinter dialog with step-by-step OAuth client setup instructions and two buttons — "Open Google Cloud Console" (launches browser to the credentials page) and "I've placed credentials.json — Continue". The dialog blocks until the file exists or the user cancels.
5. If `token.json` is missing: the first actual sweep (triggered by the user from the menu) will open the consent browser. No forced pre-consent — we let the user control the timing.
6. On first successful sweep, creates the Startup shortcut if it doesn't exist.

## Packaging

- **Tool:** PyInstaller, one-file mode.
- **Spec:** `CalendarReminder.spec` at project root. Entry point `tray.py`. Bundles `icon.ico` and the template `config.yaml`. Windowed (no console).
- **Build:** `pyinstaller CalendarReminder.spec` → produces `dist\CalendarReminder.exe`.
- **Distribution:** the `.exe` alone is enough — no installer. User double-clicks; it self-initializes `%APPDATA%\CalendarReminder\`, prompts for credentials, adds the Startup shortcut.
- **Not shipped in the exe:** `credentials.json`, `token.json`, `state.json`, logs. All user-specific, all stay in `%APPDATA%`.

## Testing

- **`tests/test_classify.py`** — unit tests for the classifier. Pure function, no mocks, no network. Fixtures cover:
  - Each silence rule matching
  - An event matching no rule (expect KEEP)
  - An event matching a silence rule but also `never_silence` (expect KEEP)
  - Edge cases: missing `organizer`, missing `extendedProperties`, empty title, non-string title fields
- **No live-API tests.** The built-in `--dry-run` mode against the real calendar is the integration test — it uses real data shapes without any risk of mutation.
- **Run:** `pytest` from the project root.

## Rollout plan

All validation happens via the CLI (`main.py`) against the dev tree — same process as before. The tray app and packaging come *after* the logic is proven.

```
Phase 1 — validate core (CLI, source tree)
  python main.py --dry-run --days 7    # review narrow dry-run
  python main.py --days 7               # live narrow run; spot-check Calendar
  python main.py --dry-run              # full 30-day dry-run
  python main.py                        # full 30-day live run

Phase 2 — wrap in tray app (still running from source)
  python -m calendar_reminder.tray      # smoke-test the tray UI
                                        # exercise: Sweep now, Dry run, Open log, Open config, Quit

Phase 3 — package and install
  pyinstaller CalendarReminder.spec     # build dist\CalendarReminder.exe
  Run dist\CalendarReminder.exe         # first-run dialog, Startup shortcut install
  Log out, log back in                  # confirm tray auto-starts
```

If the log shows a real meeting being silenced, add its title substring or the calendar ID to `never_silence` in `%APPDATA%\CalendarReminder\config.yaml` (edit via tray → "Open config") and re-run. No code changes or re-packaging needed — config is read on every sweep.

## Out of scope

- Silencing based on event body/description content analysis.
- Touching recurring-event masters (we only modify individual instances inside the scan window).
- A full GUI window (tray only; no main window, no rule editor UI).
- Auto-updater for the `.exe` (rebuild + redistribute manually when needed).
- Cross-account support (single Google account only).
- Any form of positive "meeting detection" heuristics — silence rules are the only logic.
- Code signing the `.exe` (Windows SmartScreen may flag on first run; the user clicks through).
