# Calendar Notification Sweeper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows tray app (packaged as a single `.exe`) that silences notifications on Gmail-extracted and Reclaim-created Google Calendar events daily, while leaving real meetings untouched.

**Architecture:** Core is a pure Python sweep (classify → patch reminders) driven by two entry points: a CLI (`main.py`) for dev/debug, and a tray app (`tray.py`) for the shipping product. The tray runs on login, owns a background timer (once every 24h), and exposes *Sweep now*, *Dry run*, *Open log*, *Open config*, *Quit* via a right-click menu. When packaged (PyInstaller one-file), config/credentials/token/logs live in `%APPDATA%\CalendarReminder\`.

**Tech Stack:** Python 3.10+, `google-api-python-client`, `google-auth-oauthlib`, `PyYAML`, `pystray`, `Pillow`, `pytest`, PyInstaller (build-time only).

---

## File map

| Path | Purpose |
|---|---|
| `requirements.txt` | pinned dependencies (includes pystray, Pillow, pyinstaller) |
| `config.yaml` | shipped template — silence rules, never-silence list, scan window |
| `icon.ico` | generated at build time (not committed) for tray + exe icon |
| `CalendarReminder.spec` | PyInstaller one-file recipe |
| `calendar_reminder/__init__.py` | package marker (empty) |
| `calendar_reminder/paths.py` | resolve runtime dirs (frozen vs dev) |
| `calendar_reminder/config.py` | load + validate YAML config |
| `calendar_reminder/classify.py` | pure classifier: `classify(event, config)` |
| `calendar_reminder/auth.py` | OAuth flow + token refresh, returns Calendar service |
| `calendar_reminder/sweeper.py` | fetch events, apply classifier, patch reminders, emit log lines |
| `calendar_reminder/tray.py` | pystray UI, internal daily timer, first-run dialog, state.json |
| `main.py` | CLI entry: argparse flags, wires modules together |
| `tests/__init__.py` | package marker (empty) |
| `tests/test_classify.py` | unit tests for classifier |
| `tests/test_config.py` | unit tests for config loader |
| `tests/test_paths.py` | unit tests for paths module |
| `tests/test_sweeper.py` | unit tests for sweeper (fake service) |
| `logs/` (dev) / `%APPDATA%\CalendarReminder\logs\` (packaged) | runtime log output |

---

## Task 1: Project skeleton + dependencies

**Files:**
- Create: `requirements.txt`
- Create: `calendar_reminder/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `requirements.txt`**

```
google-api-python-client==2.149.0
google-auth-oauthlib==1.2.1
google-auth-httplib2==0.2.0
PyYAML==6.0.2
pystray==0.19.5
Pillow==10.4.0
pytest==8.3.3
pyinstaller==6.11.0
```

- [ ] **Step 2: Create empty `calendar_reminder/__init__.py`**

(empty file)

- [ ] **Step 3: Create empty `tests/__init__.py`**

(empty file)

- [ ] **Step 4: Create/activate venv and install**

```bash
cd "D:\Calendar Reminder"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Expected: packages install, no errors.

- [ ] **Step 5: Verify pytest runs (empty suite)**

```bash
pytest
```

Expected: `no tests ran in 0.XXs` — exit 5 (no tests collected) is fine.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt calendar_reminder/__init__.py tests/__init__.py
git commit -m "chore: add project skeleton and dependencies"
```

---

## Task 2: Classifier — Tier 1 rule: `eventType == fromGmail` (TDD)

**Files:**
- Create: `calendar_reminder/classify.py`
- Create: `tests/test_classify.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_classify.py`:

```python
from calendar_reminder.classify import classify


MIN_CONFIG = {
    "silence_rules": [
        {"name": "gmail_auto_events", "match": {"eventType": "fromGmail"}},
    ],
    "never_silence": {"title_contains": [], "calendar_ids": []},
}


def test_gmail_auto_event_is_silenced():
    event = {
        "id": "e1",
        "summary": "Flight UA1234 to SFO",
        "eventType": "fromGmail",
    }
    action, rule = classify(event, MIN_CONFIG)
    assert action == "silence"
    assert rule == "gmail_auto_events"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_classify.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'calendar_reminder.classify'`.

- [ ] **Step 3: Minimal implementation**

Create `calendar_reminder/classify.py`:

```python
def classify(event, config):
    for rule in config.get("silence_rules", []):
        match = rule.get("match", {})
        if "eventType" in match and event.get("eventType") == match["eventType"]:
            return ("silence", rule["name"])
    return ("keep", None)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_classify.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add calendar_reminder/classify.py tests/test_classify.py
git commit -m "feat(classify): silence events with eventType=fromGmail"
```

---

## Task 3: Classifier — Reclaim by organizer (TDD)

**Files:**
- Modify: `calendar_reminder/classify.py`
- Modify: `tests/test_classify.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_classify.py`:

```python
RECLAIM_ORG_CONFIG = {
    "silence_rules": [
        {"name": "reclaim_by_organizer",
         "match": {"organizer_email_endswith": "@reclaim.ai"}},
    ],
    "never_silence": {"title_contains": [], "calendar_ids": []},
}


def test_reclaim_organizer_is_silenced():
    event = {
        "id": "e2",
        "summary": "Focus Time",
        "organizer": {"email": "bot@reclaim.ai"},
    }
    action, rule = classify(event, RECLAIM_ORG_CONFIG)
    assert action == "silence"
    assert rule == "reclaim_by_organizer"


def test_non_reclaim_organizer_is_kept():
    event = {
        "id": "e3",
        "summary": "1:1 with Sarah",
        "organizer": {"email": "sarah@example.com"},
    }
    action, rule = classify(event, RECLAIM_ORG_CONFIG)
    assert action == "keep"
    assert rule is None
```

- [ ] **Step 2: Run tests — new test fails**

```bash
pytest tests/test_classify.py -v
```

Expected: `test_reclaim_organizer_is_silenced` FAILS.

- [ ] **Step 3: Extend implementation**

Replace the body of `classify` in `calendar_reminder/classify.py`:

```python
def classify(event, config):
    for rule in config.get("silence_rules", []):
        match = rule.get("match", {})

        if "eventType" in match and event.get("eventType") == match["eventType"]:
            return ("silence", rule["name"])

        if "organizer_email_endswith" in match:
            suffix = match["organizer_email_endswith"]
            email = (event.get("organizer") or {}).get("email", "")
            if email.endswith(suffix):
                return ("silence", rule["name"])

    return ("keep", None)
```

- [ ] **Step 4: Run tests to verify all pass**

```bash
pytest tests/test_classify.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add calendar_reminder/classify.py tests/test_classify.py
git commit -m "feat(classify): silence by organizer email suffix"
```

---

## Task 4: Classifier — Reclaim by extendedProperties (TDD)

**Files:**
- Modify: `calendar_reminder/classify.py`
- Modify: `tests/test_classify.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_classify.py`:

```python
EXT_PROP_CONFIG = {
    "silence_rules": [
        {"name": "reclaim_by_extended_property",
         "match": {"has_extended_property_prefix": "reclaim"}},
    ],
    "never_silence": {"title_contains": [], "calendar_ids": []},
}


def test_extended_property_prefix_is_silenced():
    event = {
        "id": "e4",
        "summary": "Habit: Daily walk",
        "extendedProperties": {
            "private": {"reclaim-event-category": "habit"}
        },
    }
    action, rule = classify(event, EXT_PROP_CONFIG)
    assert action == "silence"
    assert rule == "reclaim_by_extended_property"


def test_missing_extended_properties_is_kept():
    event = {"id": "e5", "summary": "Lunch"}
    action, rule = classify(event, EXT_PROP_CONFIG)
    assert action == "keep"
```

- [ ] **Step 2: Run tests — new test fails**

```bash
pytest tests/test_classify.py -v
```

Expected: `test_extended_property_prefix_is_silenced` FAILS.

- [ ] **Step 3: Extend implementation**

Add another branch inside the loop in `calendar_reminder/classify.py`, after the organizer branch:

```python
        if "has_extended_property_prefix" in match:
            prefix = match["has_extended_property_prefix"]
            private = (event.get("extendedProperties") or {}).get("private") or {}
            if any(k.startswith(prefix) for k in private.keys()):
                return ("silence", rule["name"])
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_classify.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add calendar_reminder/classify.py tests/test_classify.py
git commit -m "feat(classify): silence by extendedProperties key prefix"
```

---

## Task 5: Classifier — title regex (TDD)

**Files:**
- Modify: `calendar_reminder/classify.py`
- Modify: `tests/test_classify.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_classify.py`:

```python
TITLE_REGEX_CONFIG = {
    "silence_rules": [
        {"name": "travel_title_patterns",
         "match": {"title_regex": "^(Travel Time|Travel to|Flight )"}},
    ],
    "never_silence": {"title_contains": [], "calendar_ids": []},
}


def test_title_regex_matches():
    event = {"id": "e6", "summary": "Travel Time to SFO"}
    action, rule = classify(event, TITLE_REGEX_CONFIG)
    assert action == "silence"
    assert rule == "travel_title_patterns"


def test_title_regex_non_match_is_kept():
    event = {"id": "e7", "summary": "Dentist appointment"}
    action, rule = classify(event, TITLE_REGEX_CONFIG)
    assert action == "keep"


def test_missing_title_does_not_crash():
    event = {"id": "e8"}
    action, rule = classify(event, TITLE_REGEX_CONFIG)
    assert action == "keep"
```

- [ ] **Step 2: Run — new tests fail**

```bash
pytest tests/test_classify.py -v
```

Expected: 2 failures (`test_title_regex_matches`, `test_missing_title_does_not_crash`).

- [ ] **Step 3: Add import + branch**

At the top of `calendar_reminder/classify.py`:

```python
import re
```

Add another branch inside the rule loop, after the extendedProperties branch:

```python
        if "title_regex" in match:
            title = event.get("summary") or ""
            if re.search(match["title_regex"], title):
                return ("silence", rule["name"])
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_classify.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add calendar_reminder/classify.py tests/test_classify.py
git commit -m "feat(classify): silence by title regex"
```

---

## Task 6: Classifier — `never_silence` override (TDD)

**Files:**
- Modify: `calendar_reminder/classify.py`
- Modify: `tests/test_classify.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_classify.py`:

```python
NEVER_SILENCE_CONFIG = {
    "silence_rules": [
        {"name": "gmail_auto_events", "match": {"eventType": "fromGmail"}},
    ],
    "never_silence": {
        "title_contains": ["IMPORTANT"],
        "calendar_ids": ["work-cal@group.calendar.google.com"],
    },
}


def test_never_silence_by_title_substring():
    event = {
        "id": "e9",
        "summary": "IMPORTANT: Flight to Tokyo",
        "eventType": "fromGmail",
    }
    action, rule = classify(event, NEVER_SILENCE_CONFIG)
    assert action == "keep"


def test_never_silence_by_calendar_id():
    event = {
        "id": "e10",
        "summary": "Auto event",
        "eventType": "fromGmail",
        "_calendarId": "work-cal@group.calendar.google.com",
    }
    action, rule = classify(event, NEVER_SILENCE_CONFIG)
    assert action == "keep"
```

- [ ] **Step 2: Run — two new tests fail**

```bash
pytest tests/test_classify.py -v
```

- [ ] **Step 3: Add never_silence check at top of classify**

Replace `classify` in `calendar_reminder/classify.py` so it checks `never_silence` before iterating rules:

```python
import re


def classify(event, config):
    never = config.get("never_silence") or {}
    title = event.get("summary") or ""

    for needle in never.get("title_contains") or []:
        if needle in title:
            return ("keep", None)

    cal_id = event.get("_calendarId")
    if cal_id and cal_id in (never.get("calendar_ids") or []):
        return ("keep", None)

    for rule in config.get("silence_rules", []):
        match = rule.get("match", {})

        if "eventType" in match and event.get("eventType") == match["eventType"]:
            return ("silence", rule["name"])

        if "organizer_email_endswith" in match:
            suffix = match["organizer_email_endswith"]
            email = (event.get("organizer") or {}).get("email", "")
            if email.endswith(suffix):
                return ("silence", rule["name"])

        if "has_extended_property_prefix" in match:
            prefix = match["has_extended_property_prefix"]
            private = (event.get("extendedProperties") or {}).get("private") or {}
            if any(k.startswith(prefix) for k in private.keys()):
                return ("silence", rule["name"])

        if "title_regex" in match:
            if re.search(match["title_regex"], title):
                return ("silence", rule["name"])

    return ("keep", None)
```

Note: `_calendarId` is an underscore-prefixed field we inject in `sweeper.py` before calling `classify`, since it isn't in the Google event resource directly.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_classify.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add calendar_reminder/classify.py tests/test_classify.py
git commit -m "feat(classify): honor never_silence overrides"
```

---

## Task 7: Config loader + `config.yaml` (TDD)

**Files:**
- Create: `calendar_reminder/config.py`
- Create: `tests/test_config.py`
- Create: `config.yaml`

- [ ] **Step 1: Write failing test**

Create `tests/test_config.py`:

```python
from pathlib import Path
from calendar_reminder.config import load_config


def test_load_config_returns_dict_with_expected_keys(tmp_path):
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "silence_rules:\n"
        "  - name: test_rule\n"
        "    match:\n"
        "      eventType: fromGmail\n"
        "never_silence:\n"
        "  title_contains: []\n"
        "  calendar_ids: []\n"
        "scan:\n"
        "  days_ahead: 30\n"
        "  include_past: false\n"
    )
    cfg = load_config(str(yaml_path))
    assert cfg["silence_rules"][0]["name"] == "test_rule"
    assert cfg["scan"]["days_ahead"] == 30
    assert cfg["never_silence"]["title_contains"] == []


def test_load_config_missing_file_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        load_config(str(tmp_path / "does-not-exist.yaml"))


def test_load_config_rejects_missing_silence_rules(tmp_path):
    import pytest
    yaml_path = tmp_path / "bad.yaml"
    yaml_path.write_text("scan:\n  days_ahead: 30\n")
    with pytest.raises(ValueError, match="silence_rules"):
        load_config(str(yaml_path))
```

- [ ] **Step 2: Run — fails (module missing)**

```bash
pytest tests/test_config.py -v
```

- [ ] **Step 3: Implement loader**

Create `calendar_reminder/config.py`:

```python
import yaml


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if not isinstance(cfg, dict):
        raise ValueError("config.yaml must be a mapping at the top level")

    if "silence_rules" not in cfg or not isinstance(cfg["silence_rules"], list):
        raise ValueError("config.yaml missing required key: silence_rules (list)")

    cfg.setdefault("never_silence", {})
    cfg["never_silence"].setdefault("title_contains", [])
    cfg["never_silence"].setdefault("calendar_ids", [])
    cfg.setdefault("scan", {})
    cfg["scan"].setdefault("days_ahead", 30)
    cfg["scan"].setdefault("include_past", False)

    return cfg
```

- [ ] **Step 4: Create `config.yaml` at project root**

```yaml
silence_rules:
  - name: gmail_auto_events
    match:
      eventType: fromGmail

  - name: reclaim_by_organizer
    match:
      organizer_email_endswith: "@reclaim.ai"

  - name: reclaim_by_extended_property
    match:
      has_extended_property_prefix: "reclaim"

  - name: travel_title_patterns
    match:
      title_regex: "^(Travel Time|Travel to|Flight )"

never_silence:
  title_contains: []
  calendar_ids: []

scan:
  days_ahead: 30
  include_past: false
```

- [ ] **Step 5: Run tests**

```bash
pytest -v
```

Expected: all previous tests + 3 new config tests pass.

- [ ] **Step 6: Commit**

```bash
git add calendar_reminder/config.py tests/test_config.py config.yaml
git commit -m "feat(config): add YAML loader and starting config"
```

---

## Task 8: OAuth / auth module

**Files:**
- Create: `calendar_reminder/auth.py`

Note: `auth.py` does I/O + browser flow; it's not unit-testable without mocking the entire Google stack (overkill for this project). We verify it works via the end-to-end dry run in Task 13.

- [ ] **Step 1: Implement auth module**

Create `calendar_reminder/auth.py`:

```python
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def get_service(credentials_path="credentials.json", token_path="token.json"):
    """Return an authenticated Google Calendar API service.

    On first run, opens a browser for the user to approve access.
    Subsequent runs refresh the stored token automatically.
    """
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    f"Missing OAuth client secret at {credentials_path}. "
                    "Download it from Google Cloud Console (OAuth client -> Desktop app)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds, cache_discovery=False)
```

- [ ] **Step 2: Commit (no test yet — covered by end-to-end in Task 13)**

```bash
git add calendar_reminder/auth.py
git commit -m "feat(auth): OAuth flow and service builder"
```

---

## Task 9: Sweeper — fetch + classify + log (dry-run capable)

**Files:**
- Create: `calendar_reminder/sweeper.py`

The sweeper uses the service built by `auth.get_service()`. We keep it testable by having `sweep()` accept the service as an argument (dependency injection), so any test can pass a fake.

- [ ] **Step 1: Implement sweeper module**

Create `calendar_reminder/sweeper.py`:

```python
import datetime as dt
import logging
import time

from googleapiclient.errors import HttpError

from calendar_reminder.classify import classify


log = logging.getLogger("calendar_reminder")


def _now_utc():
    return dt.datetime.now(dt.timezone.utc)


def _list_events(service, calendar_id, time_min, time_max):
    events = []
    page_token = None
    while True:
        resp = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token,
            maxResults=250,
        ).execute()
        for ev in resp.get("items", []):
            ev["_calendarId"] = calendar_id
            events.append(ev)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return events


def _already_silenced(event):
    reminders = event.get("reminders") or {}
    return reminders.get("useDefault") is False and not reminders.get("overrides")


def _patch_silence(service, calendar_id, event_id):
    body = {"reminders": {"useDefault": False, "overrides": []}}
    for attempt in range(3):
        try:
            service.events().patch(
                calendarId=calendar_id, eventId=event_id, body=body,
            ).execute()
            return True
        except HttpError as e:
            status = getattr(e, "status_code", None) or getattr(e.resp, "status", None)
            if status in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise


def sweep(service, config, dry_run=False, days_override=None):
    """Run one sweep. Returns counts dict."""
    days = days_override if days_override is not None else config["scan"]["days_ahead"]
    now = _now_utc()
    time_min = now.isoformat()
    time_max = (now + dt.timedelta(days=days)).isoformat()

    counts = {"scanned": 0, "silenced": 0, "kept": 0, "skipped": 0, "errors": 0}
    start = time.monotonic()

    events = _list_events(service, "primary", time_min, time_max)

    for ev in events:
        counts["scanned"] += 1
        summary = ev.get("summary", "")
        ev_id = ev.get("id", "?")
        try:
            action, rule = classify(ev, config)
            if action == "silence":
                if _already_silenced(ev):
                    counts["skipped"] += 1
                    log.info('SKIP | evt=%s | "%s" | reason=already_silenced', ev_id, summary)
                    continue
                if dry_run:
                    counts["silenced"] += 1
                    log.info('DRY-RUN-SILENCE | evt=%s | "%s" | rule=%s', ev_id, summary, rule)
                else:
                    _patch_silence(service, "primary", ev_id)
                    counts["silenced"] += 1
                    log.info('SILENCED | evt=%s | "%s" | rule=%s', ev_id, summary, rule)
            else:
                counts["kept"] += 1
                log.debug('KEPT | evt=%s | "%s" | rule=none', ev_id, summary)
        except Exception as exc:
            counts["errors"] += 1
            log.error('ERROR | evt=%s | "%s" | exc=%s', ev_id, summary, exc)

    duration = time.monotonic() - start
    log.info(
        "SUMMARY: scanned=%d silenced=%d kept=%d skipped=%d errors=%d duration=%.1fs",
        counts["scanned"], counts["silenced"], counts["kept"],
        counts["skipped"], counts["errors"], duration,
    )
    return counts
```

- [ ] **Step 2: Add targeted unit test for sweeper with a fake service**

Create `tests/test_sweeper.py`:

```python
from calendar_reminder.sweeper import sweep


class FakeEvents:
    def __init__(self, items, patched):
        self._items = items
        self._patched = patched

    def list(self, **kwargs):
        return _Exec({"items": self._items})

    def patch(self, calendarId, eventId, body):
        self._patched.append((calendarId, eventId, body))
        return _Exec({})


class _Exec:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class FakeService:
    def __init__(self, items):
        self.patched = []
        self._events = FakeEvents(items, self.patched)

    def events(self):
        return self._events


MIN_CONFIG = {
    "silence_rules": [{"name": "gmail_auto_events", "match": {"eventType": "fromGmail"}}],
    "never_silence": {"title_contains": [], "calendar_ids": []},
    "scan": {"days_ahead": 7, "include_past": False},
}


def test_sweep_silences_matching_event_and_skips_already_silenced():
    items = [
        {"id": "a", "summary": "Flight", "eventType": "fromGmail",
         "reminders": {"useDefault": True}},
        {"id": "b", "summary": "Already quiet", "eventType": "fromGmail",
         "reminders": {"useDefault": False, "overrides": []}},
        {"id": "c", "summary": "Real meeting",
         "reminders": {"useDefault": True}},
    ]
    svc = FakeService(items)
    counts = sweep(svc, MIN_CONFIG, dry_run=False)
    assert counts == {"scanned": 3, "silenced": 1, "kept": 1, "skipped": 1, "errors": 0}
    assert svc.patched == [
        ("primary", "a", {"reminders": {"useDefault": False, "overrides": []}})
    ]


def test_sweep_dry_run_does_not_patch():
    items = [
        {"id": "a", "summary": "Flight", "eventType": "fromGmail",
         "reminders": {"useDefault": True}},
    ]
    svc = FakeService(items)
    counts = sweep(svc, MIN_CONFIG, dry_run=True)
    assert counts["silenced"] == 1
    assert svc.patched == []
```

- [ ] **Step 3: Run all tests**

```bash
pytest -v
```

Expected: all prior tests + 2 new sweeper tests pass.

- [ ] **Step 4: Commit**

```bash
git add calendar_reminder/sweeper.py tests/test_sweeper.py
git commit -m "feat(sweeper): fetch, classify, and patch reminders with dry-run"
```

---

## Task 10: CLI entry (`main.py`)

**Files:**
- Create: `main.py`

- [ ] **Step 1: Implement CLI**

Create `main.py` at the project root:

```python
import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

from calendar_reminder.auth import get_service
from calendar_reminder.config import load_config
from calendar_reminder.sweeper import sweep


def _setup_logging(log_dir, verbose):
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"sweep-{date.today().isoformat()}.log"

    fmt = logging.Formatter("%(asctime)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    file_h = logging.FileHandler(log_path, encoding="utf-8")
    file_h.setFormatter(fmt)
    stream_h = logging.StreamHandler(sys.stdout)
    stream_h.setFormatter(fmt)

    logger = logging.getLogger("calendar_reminder")
    logger.handlers.clear()
    logger.addHandler(file_h)
    logger.addHandler(stream_h)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)


def _rotate_logs(log_dir, keep_days=30):
    if not log_dir.exists():
        return
    from time import time
    cutoff = time() - keep_days * 86400
    for p in log_dir.glob("sweep-*.log"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sweep auto-inserted Google Calendar notifications.")
    parser.add_argument("--dry-run", action="store_true", help="Log what would change, don't modify events.")
    parser.add_argument("--days", type=int, default=None, help="Scan window override (days ahead).")
    parser.add_argument("--verbose", action="store_true", help="Include KEPT events in log output.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    args = parser.parse_args(argv)

    project_root = Path(__file__).parent
    os.chdir(project_root)

    log_dir = project_root / "logs"
    _setup_logging(log_dir, args.verbose)
    _rotate_logs(log_dir)

    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2

    try:
        service = get_service()
    except FileNotFoundError as e:
        print(f"Auth error: {e}", file=sys.stderr)
        return 3

    counts = sweep(service, cfg, dry_run=args.dry_run, days_override=args.days)
    return 0 if counts["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify import-level sanity**

```bash
python -c "import main; print('ok')"
```

Expected: prints `ok`. If it fails, fix the import error before proceeding.

- [ ] **Step 3: Verify `--help` works**

```bash
python main.py --help
```

Expected: help text for the four flags.

- [ ] **Step 4: Run full test suite**

```bash
pytest -v
```

Expected: all tests still pass.

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat(cli): add main.py entry with dry-run, days, verbose flags"
```

---

## Task 10a: Calendar list + interactive picker module (TDD)

**Files:**
- Create: `calendar_reminder/calendars.py`
- Create: `tests/test_calendars.py`
- Modify: `calendar_reminder/auth.py` (expand SCOPES)
- Delete (if exists): `token.json` — old scopes invalidate the stored token; user re-consents on next real run.

- [ ] **Step 1: Expand OAuth scopes in `auth.py`**

Replace the `SCOPES` constant in `calendar_reminder/auth.py` with:

```python
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
]
```

- [ ] **Step 2: Delete any existing `token.json`**

```bash
rm -f "D:/Calendar Reminder/token.json"
```

(If the file doesn't exist, no-op.)

- [ ] **Step 3: Write failing tests**

Create `tests/test_calendars.py`:

```python
from calendar_reminder.calendars import list_user_calendars, pick_calendars_interactive


class _Exec:
    def __init__(self, payload):
        self._p = payload

    def execute(self):
        return self._p


class FakeCalendarList:
    def __init__(self, items):
        self._items = items

    def list(self):
        return _Exec({"items": self._items})


class FakeService:
    def __init__(self, items):
        self._cl = FakeCalendarList(items)

    def calendarList(self):
        return self._cl


def test_list_user_calendars_filters_to_writable():
    svc = FakeService([
        {"id": "primary", "summary": "me@example.com", "primary": True, "accessRole": "owner"},
        {"id": "holidays@group", "summary": "Holidays", "accessRole": "reader"},
        {"id": "reclaim@group", "summary": "Reclaim", "accessRole": "writer"},
    ])
    cals = list_user_calendars(svc)
    assert [c["id"] for c in cals] == ["primary", "reclaim@group"]


def test_list_user_calendars_missing_summary_fallback():
    svc = FakeService([{"id": "x@y", "accessRole": "owner"}])
    cals = list_user_calendars(svc)
    assert cals[0]["summary"] == "(no name)"
    assert cals[0]["primary"] is False


def test_pick_calendars_interactive_comma_separated(monkeypatch):
    cals = [
        {"id": "a", "summary": "A", "primary": False, "accessRole": "owner"},
        {"id": "b", "summary": "B", "primary": False, "accessRole": "owner"},
        {"id": "c", "summary": "C", "primary": False, "accessRole": "owner"},
    ]
    monkeypatch.setattr("builtins.input", lambda _: "1,3")
    selected = pick_calendars_interactive(cals)
    assert selected == ["a", "c"]


def test_pick_calendars_interactive_all(monkeypatch):
    cals = [
        {"id": "a", "summary": "A", "primary": False, "accessRole": "owner"},
        {"id": "b", "summary": "B", "primary": False, "accessRole": "owner"},
    ]
    monkeypatch.setattr("builtins.input", lambda _: "all")
    selected = pick_calendars_interactive(cals)
    assert selected == ["a", "b"]


def test_pick_calendars_interactive_reprompts_on_bad_input(monkeypatch, capsys):
    cals = [
        {"id": "a", "summary": "A", "primary": False, "accessRole": "owner"},
        {"id": "b", "summary": "B", "primary": False, "accessRole": "owner"},
    ]
    inputs = iter(["99", "xyz", "2"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    selected = pick_calendars_interactive(cals)
    assert selected == ["b"]
```

- [ ] **Step 4: Run tests — fails (module missing)**

```bash
.venv/Scripts/pytest.exe tests/test_calendars.py -v
```

- [ ] **Step 5: Implement `calendars.py`**

Create `calendar_reminder/calendars.py`:

```python
def list_user_calendars(service):
    """Return writable calendars: [{id, summary, primary, accessRole}, ...]"""
    resp = service.calendarList().list().execute()
    out = []
    for item in resp.get("items", []):
        if item.get("accessRole") not in ("owner", "writer"):
            continue
        out.append({
            "id": item["id"],
            "summary": item.get("summary", "(no name)"),
            "primary": item.get("primary", False),
            "accessRole": item["accessRole"],
        })
    return out


def pick_calendars_interactive(calendars):
    """Prompt via stdin. Returns list of selected calendar IDs."""
    print("\nAvailable calendars:")
    for i, c in enumerate(calendars, 1):
        primary = " (primary)" if c["primary"] else ""
        print(f"  [{i}] {c['summary']} — {c['id']} [{c['accessRole']}]{primary}")

    while True:
        raw = input("\nPick (comma-separated numbers, or 'all'): ").strip()
        if raw.lower() == "all":
            return [c["id"] for c in calendars]
        try:
            indices = [int(x.strip()) for x in raw.split(",") if x.strip()]
            if indices and all(1 <= i <= len(calendars) for i in indices):
                return [calendars[i - 1]["id"] for i in indices]
        except ValueError:
            pass
        print("Invalid input. Try again.")
```

- [ ] **Step 6: Run tests**

```bash
.venv/Scripts/pytest.exe -v
```

Expected: all prior tests + 5 new calendar tests pass.

- [ ] **Step 7: Commit**

```bash
git add calendar_reminder/calendars.py calendar_reminder/auth.py tests/test_calendars.py
git commit -m "feat(calendars): list and interactive-pick writable calendars"
```

---

## Task 10b: Sweeper iterates configured calendars

**Files:**
- Modify: `calendar_reminder/sweeper.py`
- Modify: `tests/test_sweeper.py`

- [ ] **Step 1: Update `sweep()` to read from `config["scan"]["calendars"]`**

In `calendar_reminder/sweeper.py`, replace the body of `sweep()` with:

```python
def sweep(service, config, dry_run=False, days_override=None):
    """Run one sweep. Returns counts dict."""
    days = days_override if days_override is not None else config["scan"]["days_ahead"]
    calendar_ids = config["scan"].get("calendars") or ["primary"]
    now = _now_utc()
    time_min = now.isoformat()
    time_max = (now + dt.timedelta(days=days)).isoformat()

    counts = {"scanned": 0, "silenced": 0, "kept": 0, "skipped": 0, "errors": 0}
    start = time.monotonic()

    events = []
    for cal_id in calendar_ids:
        events.extend(_list_events(service, cal_id, time_min, time_max))

    for ev in events:
        counts["scanned"] += 1
        summary = ev.get("summary", "")
        ev_id = ev.get("id", "?")
        cal_id = ev.get("_calendarId", "primary")
        try:
            action, rule = classify(ev, config)
            if action == "silence":
                if _already_silenced(ev):
                    counts["skipped"] += 1
                    log.info('SKIP | evt=%s | "%s" | reason=already_silenced', ev_id, summary)
                    continue
                if dry_run:
                    counts["silenced"] += 1
                    log.info('DRY-RUN-SILENCE | evt=%s | "%s" | rule=%s', ev_id, summary, rule)
                else:
                    _patch_silence(service, cal_id, ev_id)
                    counts["silenced"] += 1
                    log.info('SILENCED | evt=%s | "%s" | rule=%s', ev_id, summary, rule)
            else:
                counts["kept"] += 1
                log.debug('KEPT | evt=%s | "%s" | rule=none', ev_id, summary)
        except Exception as exc:
            counts["errors"] += 1
            log.error('ERROR | evt=%s | "%s" | exc=%s', ev_id, summary, exc)

    duration = time.monotonic() - start
    log.info(
        "SUMMARY: scanned=%d silenced=%d kept=%d skipped=%d errors=%d duration=%.1fs",
        counts["scanned"], counts["silenced"], counts["kept"],
        counts["skipped"], counts["errors"], duration,
    )
    return counts
```

Key changes:
- Reads `calendar_ids = config["scan"].get("calendars") or ["primary"]`
- Iterates over each calendar when fetching events
- `_patch_silence` now uses `ev["_calendarId"]` (the calendar we fetched from) instead of hardcoded `"primary"`

- [ ] **Step 2: Add multi-calendar test**

Modify `tests/test_sweeper.py`. Replace the `FakeEvents` class to take per-calendar event dicts, and the `FakeService` to dispatch list calls by calendarId:

```python
from calendar_reminder.sweeper import sweep


class _Exec:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class FakeEvents:
    def __init__(self, per_calendar_items, patched):
        self._per_calendar = per_calendar_items
        self._patched = patched

    def list(self, **kwargs):
        cal_id = kwargs["calendarId"]
        return _Exec({"items": list(self._per_calendar.get(cal_id, []))})

    def patch(self, calendarId, eventId, body):
        self._patched.append((calendarId, eventId, body))
        return _Exec({})


class FakeService:
    def __init__(self, per_calendar_items):
        self.patched = []
        self._events = FakeEvents(per_calendar_items, self.patched)

    def events(self):
        return self._events


MIN_CONFIG_PRIMARY = {
    "silence_rules": [{"name": "gmail_auto_events", "match": {"eventType": "fromGmail"}}],
    "never_silence": {"title_contains": [], "calendar_ids": []},
    "scan": {"days_ahead": 7, "include_past": False, "calendars": ["primary"]},
}

MULTI_CONFIG = {
    "silence_rules": [{"name": "gmail_auto_events", "match": {"eventType": "fromGmail"}}],
    "never_silence": {"title_contains": [], "calendar_ids": []},
    "scan": {"days_ahead": 7, "include_past": False, "calendars": ["primary", "reclaim@group"]},
}


def test_sweep_silences_matching_event_and_skips_already_silenced():
    svc = FakeService({
        "primary": [
            {"id": "a", "summary": "Flight", "eventType": "fromGmail",
             "reminders": {"useDefault": True}},
            {"id": "b", "summary": "Already quiet", "eventType": "fromGmail",
             "reminders": {"useDefault": False, "overrides": []}},
            {"id": "c", "summary": "Real meeting",
             "reminders": {"useDefault": True}},
        ],
    })
    counts = sweep(svc, MIN_CONFIG_PRIMARY, dry_run=False)
    assert counts == {"scanned": 3, "silenced": 1, "kept": 1, "skipped": 1, "errors": 0}
    assert svc.patched == [
        ("primary", "a", {"reminders": {"useDefault": False, "overrides": []}})
    ]


def test_sweep_dry_run_does_not_patch():
    svc = FakeService({
        "primary": [
            {"id": "a", "summary": "Flight", "eventType": "fromGmail",
             "reminders": {"useDefault": True}},
        ],
    })
    counts = sweep(svc, MIN_CONFIG_PRIMARY, dry_run=True)
    assert counts["silenced"] == 1
    assert svc.patched == []


def test_sweep_iterates_multiple_calendars_and_patches_each_on_its_own_calendar():
    svc = FakeService({
        "primary": [
            {"id": "a", "summary": "Flight", "eventType": "fromGmail",
             "reminders": {"useDefault": True}},
        ],
        "reclaim@group": [
            {"id": "r", "summary": "Focus Time", "eventType": "fromGmail",
             "reminders": {"useDefault": True}},
        ],
    })
    counts = sweep(svc, MULTI_CONFIG, dry_run=False)
    assert counts["scanned"] == 2
    assert counts["silenced"] == 2
    assert sorted(svc.patched) == sorted([
        ("primary", "a", {"reminders": {"useDefault": False, "overrides": []}}),
        ("reclaim@group", "r", {"reminders": {"useDefault": False, "overrides": []}}),
    ])


def test_sweep_falls_back_to_primary_when_calendars_missing():
    svc = FakeService({
        "primary": [
            {"id": "a", "summary": "Flight", "eventType": "fromGmail",
             "reminders": {"useDefault": True}},
        ],
    })
    cfg_no_calendars = {
        "silence_rules": [{"name": "gmail_auto_events", "match": {"eventType": "fromGmail"}}],
        "never_silence": {"title_contains": [], "calendar_ids": []},
        "scan": {"days_ahead": 7, "include_past": False},
    }
    counts = sweep(svc, cfg_no_calendars, dry_run=False)
    assert counts["silenced"] == 1
    assert svc.patched == [("primary", "a", {"reminders": {"useDefault": False, "overrides": []}})]
```

- [ ] **Step 3: Run tests**

```bash
.venv/Scripts/pytest.exe -v
```

Expected: all prior tests + new multi-calendar tests pass.

- [ ] **Step 4: Commit**

```bash
git add calendar_reminder/sweeper.py tests/test_sweeper.py
git commit -m "feat(sweeper): iterate over configured calendars, patch on correct one"
```

---

## Task 10c: CLI flags for calendar selection + auto-picker

**Files:**
- Modify: `calendar_reminder/config.py` (add `save_config`)
- Modify: `main.py` (new flags, auto-picker on missing config)
- Modify: `tests/test_config.py` (round-trip test)
- Modify: `config.yaml` — add `scan.calendars: []` template entry

- [ ] **Step 1: Add `save_config` to `config.py`**

Append to `calendar_reminder/config.py`:

```python
def save_config(cfg, path):
    """Write config dict back to YAML. Loses comments (config.yaml is machine-manageable)."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)
```

- [ ] **Step 2: Add round-trip test to `tests/test_config.py`**

Append:

```python
def test_save_and_reload_config_round_trip(tmp_path):
    from calendar_reminder.config import save_config

    path = tmp_path / "roundtrip.yaml"
    cfg = {
        "silence_rules": [{"name": "r", "match": {"eventType": "fromGmail"}}],
        "never_silence": {"title_contains": [], "calendar_ids": []},
        "scan": {"days_ahead": 14, "include_past": False, "calendars": ["primary", "x@y"]},
    }
    save_config(cfg, str(path))
    loaded = load_config(str(path))
    assert loaded["scan"]["calendars"] == ["primary", "x@y"]
    assert loaded["scan"]["days_ahead"] == 14
    assert loaded["silence_rules"][0]["name"] == "r"
```

- [ ] **Step 3: Update `main.py` with new flags**

Edit `main.py`:

Add to imports:

```python
from calendar_reminder.calendars import list_user_calendars, pick_calendars_interactive
from calendar_reminder.config import load_config, save_config
```

(Remove the existing `from calendar_reminder.config import load_config` if it's there separately.)

Add two new flags to the argparse section:

```python
    parser.add_argument("--list-calendars", action="store_true",
                        help="List accessible calendars and exit.")
    parser.add_argument("--select-calendars", action="store_true",
                        help="Run calendar picker, save selection, and exit (no sweep).")
```

Add handling logic AFTER the config load and BEFORE `sweep()`. The full replacement for the `main()` function body (from `parser.add_argument` through `return 0 if counts...`):

```python
def main(argv=None):
    parser = argparse.ArgumentParser(description="Sweep auto-inserted Google Calendar notifications.")
    parser.add_argument("--dry-run", action="store_true", help="Log what would change, don't modify events.")
    parser.add_argument("--days", type=int, default=None, help="Scan window override (days ahead).")
    parser.add_argument("--verbose", action="store_true", help="Include KEPT events in log output.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument("--list-calendars", action="store_true",
                        help="List accessible calendars and exit.")
    parser.add_argument("--select-calendars", action="store_true",
                        help="Run calendar picker, save selection, and exit (no sweep).")
    args = parser.parse_args(argv)

    project_root = Path(__file__).parent
    os.chdir(project_root)

    log_dir = project_root / "logs"
    _setup_logging(log_dir, args.verbose)
    _rotate_logs(log_dir)

    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2

    try:
        service = get_service()
    except FileNotFoundError as e:
        print(f"Auth error: {e}", file=sys.stderr)
        return 3

    if args.list_calendars:
        cals = list_user_calendars(service)
        for c in cals:
            mark = "*" if c["primary"] else " "
            print(f"{mark} {c['id']} | {c['summary']} | {c['accessRole']}")
        return 0

    if args.select_calendars or not cfg["scan"].get("calendars"):
        cals = list_user_calendars(service)
        if not cals:
            print("No writable calendars found.", file=sys.stderr)
            return 4
        selected = pick_calendars_interactive(cals)
        cfg["scan"]["calendars"] = selected
        save_config(cfg, args.config)
        print(f"Saved {len(selected)} calendar(s) to {args.config}")
        if args.select_calendars:
            return 0

    counts = sweep(service, cfg, dry_run=args.dry_run, days_override=args.days)
    return 0 if counts["errors"] == 0 else 1
```

- [ ] **Step 4: Update `config.yaml` template**

Edit `config.yaml` at project root. Change the `scan:` section from:

```yaml
scan:
  days_ahead: 30
  include_past: false
```

to:

```yaml
scan:
  days_ahead: 30
  include_past: false
  calendars: []    # list of calendar IDs to sweep; empty = prompt on first run
```

- [ ] **Step 5: Verify tests still pass**

```bash
.venv/Scripts/pytest.exe -v
```

Expected: all prior tests + new `test_save_and_reload_config_round_trip` pass.

- [ ] **Step 6: Smoke-test `--help`**

```bash
.venv/Scripts/python.exe main.py --help
```

Expected: help text now lists 6 flags including `--list-calendars` and `--select-calendars`.

- [ ] **Step 7: Commit**

```bash
git add main.py calendar_reminder/config.py tests/test_config.py config.yaml
git commit -m "feat(cli): calendar-selection flags and auto-picker on first run"
```

---

## Task 11: Update `.gitignore` for runtime artifacts

**Files:**
- Modify: `.gitignore`

The existing `.gitignore` already covers `credentials.json`, `token.json`, `logs/`, `__pycache__`, `.venv`, and `.pytest_cache`. Verify it's adequate; no changes needed unless something is missing.

- [ ] **Step 1: Read current `.gitignore`**

```bash
cat .gitignore
```

Confirm it lists: `credentials.json`, `token.json`, `logs/`, `*.log`, `__pycache__/`, `*.py[cod]`, `.venv/`, `venv/`, `.pytest_cache/`.

- [ ] **Step 2: If any of those are missing, add them**

If missing, edit `.gitignore` to add the missing lines, then:

```bash
git add .gitignore
git commit -m "chore: ensure runtime artifacts are ignored"
```

If nothing is missing, skip the commit.

---

## Task 12: Google Cloud OAuth setup (user manual step)

**Files:** none (external config).

This task is user-performed in a browser. Document it here so the executing engineer doesn't get stuck.

- [ ] **Step 1: Create Google Cloud project**

Go to https://console.cloud.google.com/ . Create a new project named "Calendar Reminder" (or reuse an existing one).

- [ ] **Step 2: Enable the Google Calendar API**

Navigate: APIs & Services → Library → search "Google Calendar API" → Enable.

- [ ] **Step 3: Configure OAuth consent screen**

Navigate: APIs & Services → OAuth consent screen.
- User type: External (if not in a Google Workspace org) or Internal.
- Add your Gmail as a test user.
- Only add scope `.../auth/calendar.events`.

- [ ] **Step 4: Create OAuth client credentials**

Navigate: APIs & Services → Credentials → Create credentials → OAuth client ID.
- Application type: Desktop app
- Name: "Calendar Reminder CLI"
- Download the JSON as `credentials.json` → save to `D:\Calendar Reminder\credentials.json`.

- [ ] **Step 5: Verify the file is ignored**

```bash
git status
```

Expected: `credentials.json` should NOT appear as untracked. If it does, the `.gitignore` is wrong — fix before continuing.

---

## Task 13: First-run verification — dry run against live calendar

**Files:** none (execution + observation).

- [ ] **Step 1: Activate venv if not already**

```bash
cd "D:\Calendar Reminder"
.venv\Scripts\activate
```

- [ ] **Step 2: Run dry-run on narrow window (7 days)**

```bash
python main.py --dry-run --days 7 --verbose
```

Expected flow:
1. Browser opens for Google OAuth consent (first run only).
2. After approval, script returns to the terminal.
3. Console + `logs/sweep-YYYY-MM-DD.log` show per-event lines.
4. A `SUMMARY:` line at the end.

- [ ] **Step 3: Review `logs/sweep-YYYY-MM-DD.log`**

Open the log. Verify:
- Every event you expected to be silenced has a `DRY-RUN-SILENCE` line.
- No `DRY-RUN-SILENCE` line matches a real meeting/appointment you want to keep notifying.
- No unexpected `ERROR` lines.

If a real event got matched, add it to `never_silence.title_contains` in `config.yaml` and re-run the dry run. Iterate until the log looks correct.

- [ ] **Step 4: Confirm `token.json` now exists and is gitignored**

```bash
ls token.json
git status
```

Expected: `token.json` exists on disk, does not appear in `git status`.

---

## Task 14: First live run (narrow window)

**Files:** none (execution).

- [ ] **Step 1: Run live on 7-day window**

```bash
python main.py --days 7
```

Expected: `SILENCED` lines for each matched event, `SUMMARY:` at end. Exit code 0.

- [ ] **Step 2: Visual spot-check in Google Calendar**

Open Google Calendar in a browser. Click a few of the events the log reported `SILENCED`. Confirm: "Notifications" section shows "None" (or is empty).

Click a real meeting that was reported `KEPT`. Confirm: its notifications are unchanged.

- [ ] **Step 3: Re-run to verify idempotency**

```bash
python main.py --days 7
```

Expected: same matched events now appear as `SKIP | ... | reason=already_silenced`. Silenced count should be 0 (or only newly-appeared events).

---

## Task 15: Full 30-day live run

**Files:** none (execution).

- [ ] **Step 1: Dry run full 30 days**

```bash
python main.py --dry-run --verbose
```

Review the log. Tune `config.yaml` if needed (re-running dry runs until satisfied).

- [ ] **Step 2: Full live run**

```bash
python main.py
```

Expected: exit code 0. Visual spot-check in Calendar.

---

## Task 16: `paths.py` — frozen vs dev runtime dirs (TDD)

**Files:**
- Create: `calendar_reminder/paths.py`
- Create: `tests/test_paths.py`
- Modify: `main.py` to use `paths.py` for log dir and default config

This is a refactor of the existing CLI's path handling. After this task, `main.py` gets its log dir and default config path from `paths.py`. `auth.py` is left alone — callers pass paths in.

- [ ] **Step 1: Write failing test**

Create `tests/test_paths.py`:

```python
from unittest.mock import patch

from calendar_reminder import paths


def test_dev_mode_uses_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(paths.sys, "frozen", False, create=True):
        base = paths.app_data_dir()
    assert base == tmp_path


def test_frozen_mode_uses_appdata(monkeypatch):
    monkeypatch.setenv("APPDATA", "C:\\FakeAppData")
    with patch.object(paths.sys, "frozen", True, create=True):
        base = paths.app_data_dir()
    assert str(base).replace("/", "\\") == "C:\\FakeAppData\\CalendarReminder"


def test_config_path_under_app_data_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(paths.sys, "frozen", False, create=True):
        p = paths.config_path()
    assert p == tmp_path / "config.yaml"


def test_log_dir_under_app_data_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(paths.sys, "frozen", False, create=True):
        p = paths.log_dir()
    assert p == tmp_path / "logs"
```

- [ ] **Step 2: Run — fails (module missing)**

```bash
pytest tests/test_paths.py -v
```

- [ ] **Step 3: Implement `paths.py`**

Create `calendar_reminder/paths.py`:

```python
import os
import sys
from pathlib import Path


def _is_frozen():
    return bool(getattr(sys, "frozen", False))


def app_data_dir():
    """Base directory for user-specific runtime data."""
    if _is_frozen():
        base = os.environ.get("APPDATA", "")
        return Path(base) / "CalendarReminder"
    return Path.cwd()


def config_path():
    return app_data_dir() / "config.yaml"


def credentials_path():
    return app_data_dir() / "credentials.json"


def token_path():
    return app_data_dir() / "token.json"


def state_path():
    return app_data_dir() / "state.json"


def log_dir():
    return app_data_dir() / "logs"


def ensure_app_data_dir():
    app_data_dir().mkdir(parents=True, exist_ok=True)
    log_dir().mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_paths.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Update `main.py` to use `paths.py`**

Replace the `log_dir = project_root / "logs"` line in `main.py` with a `paths.log_dir()` call, and update the default value of `--config` to read from `paths.config_path()` at runtime:

In `main.py`, replace:

```python
project_root = Path(__file__).parent
os.chdir(project_root)

log_dir = project_root / "logs"
_setup_logging(log_dir, args.verbose)
```

with:

```python
from calendar_reminder import paths
paths.ensure_app_data_dir()
_setup_logging(paths.log_dir(), args.verbose)
```

And change the `--config` default:

```python
parser.add_argument("--config", default=None, help="Path to config.yaml (default: app data dir).")
```

Then after parsing args:

```python
config_file = args.config or str(paths.config_path())
```

Pass `config_file` to `load_config()`.

Remove the now-unused `project_root` and `os.chdir` lines (and the `os` and `Path` imports if no longer used).

- [ ] **Step 6: Also update auth invocation in `main.py`**

Replace `get_service()` with `get_service(credentials_path=str(paths.credentials_path()), token_path=str(paths.token_path()))`.

- [ ] **Step 7: Run full test suite and `main.py --help`**

```bash
pytest -v
python main.py --help
```

Expected: all tests pass; help text still sensible.

- [ ] **Step 8: Commit**

```bash
git add calendar_reminder/paths.py tests/test_paths.py main.py
git commit -m "feat(paths): add path resolver and wire CLI through it"
```

---

## Task 17: Tray app (`tray.py`) — UI, timer, first-run dialog

**Files:**
- Create: `calendar_reminder/tray.py`

This module is heavy I/O (icons, threads, tkinter dialog, OS commands). We won't unit-test it directly. We verify by running it and exercising the menu (Task 19).

- [ ] **Step 1: Implement tray module**

Create `calendar_reminder/tray.py`:

```python
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox

import pystray
from PIL import Image, ImageDraw

from calendar_reminder import paths
from calendar_reminder.auth import get_service
from calendar_reminder.config import load_config
from calendar_reminder.sweeper import sweep


log = logging.getLogger("calendar_reminder")

SWEEP_INTERVAL_SEC = 24 * 60 * 60
TIMER_TICK_SEC = 60 * 60


def _make_icon_image():
    img = Image.new("RGB", (64, 64), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), fill="#2e7d32", outline="#1b5e20", width=2)
    d.rectangle((28, 18, 36, 40), fill="white")
    d.rectangle((28, 42, 36, 48), fill="white")
    return img


def _read_state():
    p = paths.state_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(state):
    paths.state_path().write_text(json.dumps(state), encoding="utf-8")


def _setup_logging():
    paths.ensure_app_data_dir()
    log_path = paths.log_dir() / f"sweep-{datetime.now().strftime('%Y-%m-%d')}.log"
    fmt = logging.Formatter("%(asctime)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    file_h = logging.FileHandler(log_path, encoding="utf-8")
    file_h.setFormatter(fmt)
    logger = logging.getLogger("calendar_reminder")
    logger.handlers.clear()
    logger.addHandler(file_h)
    logger.setLevel(logging.INFO)


def _ensure_config_present():
    """Copy shipped template to AppData on first run."""
    target = paths.config_path()
    if target.exists():
        return
    paths.ensure_app_data_dir()
    # Shipped template location differs: source tree uses repo root; frozen exe uses sys._MEIPASS
    if getattr(sys, "frozen", False):
        src = Path(sys._MEIPASS) / "config.yaml"
    else:
        src = Path.cwd() / "config.yaml"
    if src.exists():
        shutil.copy(src, target)


def _prompt_for_credentials():
    """Blocking tkinter dialog. Returns True if user provided credentials.json."""
    root = tk.Tk()
    root.withdraw()
    instructions = (
        "Calendar Reminder needs OAuth credentials to access Google Calendar.\n\n"
        "1. Open https://console.cloud.google.com/apis/credentials\n"
        "2. Create a Desktop app OAuth client (or use an existing one)\n"
        "3. Download the JSON and save it as:\n"
        f"      {paths.credentials_path()}\n"
        "4. Click OK when done."
    )
    while not paths.credentials_path().exists():
        messagebox.showinfo("Calendar Reminder — First-run setup", instructions)
        if not paths.credentials_path().exists():
            if not messagebox.askretrycancel(
                "credentials.json still missing",
                f"Could not find {paths.credentials_path()}.\nRetry?",
            ):
                root.destroy()
                return False
    root.destroy()
    return True


def _install_startup_shortcut():
    """Create a Windows Startup folder shortcut so the app auto-launches on login."""
    if not getattr(sys, "frozen", False):
        return  # dev mode: no shortcut
    startup = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"
    lnk = startup / "CalendarReminder.lnk"
    if lnk.exists():
        return
    target = sys.executable
    ps = (
        f"$s = (New-Object -COM WScript.Shell).CreateShortcut('{lnk}'); "
        f"$s.TargetPath = '{target}'; "
        f"$s.WorkingDirectory = '{Path(target).parent}'; "
        f"$s.Save()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        log.error("Failed to install startup shortcut: %s", e)


class TrayApp:
    def __init__(self):
        self._icon = None
        self._sweep_lock = threading.Lock()
        self._stop = threading.Event()
        self._last_result = "No sweep yet this session"

    def _run_sweep(self, dry_run):
        if not self._sweep_lock.acquire(blocking=False):
            self._icon.notify("A sweep is already running.", "Calendar Reminder")
            return
        try:
            try:
                cfg = load_config(str(paths.config_path()))
                service = get_service(
                    credentials_path=str(paths.credentials_path()),
                    token_path=str(paths.token_path()),
                )
                counts = sweep(service, cfg, dry_run=dry_run)
                suffix = " (dry-run)" if dry_run else ""
                self._last_result = (
                    f"Last: {datetime.now().strftime('%H:%M')} "
                    f"silenced={counts['silenced']} kept={counts['kept']}{suffix}"
                )
                if not dry_run:
                    _write_state({"last_sweep_at": datetime.now(timezone.utc).isoformat()})
            except Exception as e:
                log.exception("Sweep failed")
                self._icon.notify(f"Sweep failed: {e}", "Calendar Reminder")
                self._last_result = f"Last: {datetime.now().strftime('%H:%M')} ERROR"
            finally:
                if self._icon:
                    self._icon.title = f"Calendar Reminder\n{self._last_result}"
        finally:
            self._sweep_lock.release()

    def _on_sweep_now(self, icon, item):
        threading.Thread(target=self._run_sweep, args=(False,), daemon=True).start()

    def _on_dry_run(self, icon, item):
        threading.Thread(target=self._run_sweep, args=(True,), daemon=True).start()

    def _on_open_log(self, icon, item):
        p = paths.log_dir() / f"sweep-{datetime.now().strftime('%Y-%m-%d')}.log"
        if p.exists():
            os.startfile(p)
        else:
            icon.notify("No log yet for today.", "Calendar Reminder")

    def _on_open_config(self, icon, item):
        p = paths.config_path()
        if p.exists():
            os.startfile(p)

    def _on_quit(self, icon, item):
        self._stop.set()
        icon.stop()

    def _timer_loop(self):
        while not self._stop.wait(TIMER_TICK_SEC):
            state = _read_state()
            last = state.get("last_sweep_at")
            due = True
            if last:
                try:
                    last_dt = datetime.fromisoformat(last)
                    age = (datetime.now(timezone.utc) - last_dt).total_seconds()
                    due = age >= SWEEP_INTERVAL_SEC
                except ValueError:
                    pass
            if due:
                self._run_sweep(dry_run=False)

    def run(self):
        _setup_logging()
        _ensure_config_present()
        if not paths.credentials_path().exists():
            if not _prompt_for_credentials():
                return
        _install_startup_shortcut()

        menu = pystray.Menu(
            pystray.MenuItem("Sweep now", self._on_sweep_now, default=True),
            pystray.MenuItem("Sweep now (dry run)", self._on_dry_run),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open today's log", self._on_open_log),
            pystray.MenuItem("Open config", self._on_open_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )
        self._icon = pystray.Icon(
            "CalendarReminder",
            _make_icon_image(),
            f"Calendar Reminder\n{self._last_result}",
            menu,
        )
        threading.Thread(target=self._timer_loop, daemon=True).start()
        self._icon.run()


def main():
    TrayApp().run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify imports**

```bash
python -c "from calendar_reminder import tray; print('ok')"
```

Expected: `ok`. If `pystray` or `Pillow` aren't installed, `pip install -r requirements.txt` and retry.

- [ ] **Step 3: Run the tray app from source**

```bash
python -m calendar_reminder.tray
```

Expected: tray icon appears in the Windows system tray (bottom-right, may be hidden under the `^` arrow). Right-click it — you should see the five menu items plus separators.

- [ ] **Step 4: Exercise the menu**

- Click "Open config" → config.yaml opens in your editor. (In dev mode, this is `D:\Calendar Reminder\config.yaml`.)
- Click "Open today's log" → if no log exists yet, you'll see a notification.
- Click "Sweep now (dry run)" → wait a few seconds, balloon-tip or tooltip updates with last result.
- Click "Quit" → tray icon disappears.

- [ ] **Step 5: Commit**

```bash
git add calendar_reminder/tray.py
git commit -m "feat(tray): system tray app with daily timer and first-run dialog"
```

---

## Task 18: PyInstaller packaging

**Files:**
- Create: `CalendarReminder.spec`

We use a hand-written spec (not the auto-generated one) so the recipe is explicit and diffable.

- [ ] **Step 1: Create the spec**

Create `CalendarReminder.spec` at the project root:

```python
# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe for CalendarReminder tray app.

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['calendar_reminder/tray.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.yaml', '.'),
    ],
    hiddenimports=collect_submodules('pystray') + collect_submodules('PIL'),
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='CalendarReminder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

- [ ] **Step 2: Build the exe**

```bash
cd "D:\Calendar Reminder"
.venv\Scripts\activate
pyinstaller --clean CalendarReminder.spec
```

Expected: build succeeds, `dist\CalendarReminder.exe` created. Build will print warnings — only fail-stops matter.

- [ ] **Step 3: Add build artifacts to `.gitignore`**

Append to `.gitignore` if not already present:

```
build/
dist/
*.spec.bak
```

(Keep `CalendarReminder.spec` tracked — it's source.)

```bash
git add .gitignore CalendarReminder.spec
git commit -m "feat(packaging): add PyInstaller spec for one-file exe"
```

---

## Task 19: End-to-end: run the packaged exe, verify auto-start

**Files:** none (execution + observation).

- [ ] **Step 1: Move existing runtime files into AppData**

Because the exe looks in `%APPDATA%\CalendarReminder\`, we need credentials there:

```bash
mkdir "%APPDATA%\CalendarReminder" 2>nul
copy "D:\Calendar Reminder\credentials.json" "%APPDATA%\CalendarReminder\credentials.json"
copy "D:\Calendar Reminder\token.json" "%APPDATA%\CalendarReminder\token.json"
copy "D:\Calendar Reminder\config.yaml" "%APPDATA%\CalendarReminder\config.yaml"
```

(If you haven't done live CLI runs yet — i.e. `token.json` doesn't exist — skip the token copy. The exe will open the browser on first sweep.)

- [ ] **Step 2: Run the exe manually**

Double-click `D:\Calendar Reminder\dist\CalendarReminder.exe`.

Expected: tray icon appears. If credentials are missing, the first-run dialog fires. Otherwise no dialog.

- [ ] **Step 3: Exercise menu end-to-end**

- "Sweep now (dry run)" → should run against the live calendar.
- "Open today's log" → verifies log landed in `%APPDATA%\CalendarReminder\logs\`.
- "Open config" → opens `%APPDATA%\CalendarReminder\config.yaml`.

- [ ] **Step 4: Verify Startup shortcut was installed**

Open File Explorer at:
```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
```

Expected: `CalendarReminder.lnk` present. Right-click → Properties → Target points at `dist\CalendarReminder.exe`.

- [ ] **Step 5: Reboot or log out / log in**

After logging back in, the tray icon should appear automatically (within a few seconds of login).

- [ ] **Step 6: Verify daily timer fires**

Leave the tray running for >24h (or for a faster check: temporarily edit `SWEEP_INTERVAL_SEC` and `TIMER_TICK_SEC` in `tray.py` to small values, re-run from source with `python -m calendar_reminder.tray`, confirm it fires on the accelerated schedule, then revert).

- [ ] **Step 7: Commit any tweaks that came out of live runs**

```bash
git status
# add/commit any changes (config.yaml tweaks in the source template,
# adjusted hiddenimports in the .spec, etc.)
```

---

## Task 20: Final cleanup and push

- [ ] **Step 1: Full test suite green**

```bash
pytest -v
```

- [ ] **Step 2: Push to remote**

```bash
git push
```

- [ ] **Step 3: Confirm the user-facing artifact**

`D:\Calendar Reminder\dist\CalendarReminder.exe` is the shippable app. It's already linked into Startup; it will auto-launch on next login and run the sweep within 24h.

---

## Self-review (executed while writing this plan)

**Spec coverage check:**
- Problem + goal → addressed end-to-end.
- Core modules (classify, config, auth, sweeper, main) → Tasks 2–10, one task each, plus skeleton (Task 1), gitignore (Task 11), Cloud setup (Task 12), CLI validation (Tasks 13–15).
- **Tray app design additions** → paths (Task 16), tray UI + timer + first-run dialog (Task 17), PyInstaller packaging (Task 18), packaged E2E + Startup shortcut verification (Task 19), final push (Task 20).
- Classification rules: Tier 1 gmail (Task 2), Tier 1 reclaim organizer (Task 3), Tier 1 extendedProperties (Task 4), Tier 3 title regex (Task 5), never_silence (Task 6). ✓
- Idempotency → covered by `_already_silenced` check in Task 9, verified in Task 14 Step 3 and Task 19.
- Error handling (5xx/429 retry, token expiry, malformed event, malformed config) → retry logic in `_patch_silence`, per-event try/except in sweep loop, FileNotFoundError for missing credentials, ValueError for bad config. Tray wraps sweep in try/except and surfaces failures via balloon notification.
- Logging format matches spec. End-of-run SUMMARY matches spec. Log directory path comes from `paths.log_dir()` so packaged + dev modes write to the correct location automatically.
- OAuth scope limited to `calendar.events`. ✓
- Scheduling → in-app timer (24h interval, 1h tick) in Task 17; auto-start via Startup shortcut created by `_install_startup_shortcut()` in Task 17 and verified in Task 19.
- Rollout (dry-run 7d → live 7d → dry-run 30d → live 30d → tray smoke-test → build → packaged E2E) → Tasks 13 → 14 → 15 → 17 (manual exercise) → 18 → 19.
- Tests (classify/config/paths/sweeper unit tests with fixtures, no live-API tests) → Tasks 2–7, 9, 16.

**Placeholder scan:** no TBD/TODO/"implement later". Every step that modifies code shows the actual code.

**Type consistency:** `classify(event, config) -> (str, str|None)` used consistently; `sweep(service, config, dry_run=False, days_override=None)` used consistently; `paths.*()` helpers all return `Path`. Tray converts them to `str` only at API boundaries that require it (`get_service`, `load_config`). `_calendarId` injected in sweeper and referenced in classifier — consistent.

---

## Execution handoff

Plan complete. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks
2. **Inline Execution** — run tasks in this session with checkpoints

Pick one.
