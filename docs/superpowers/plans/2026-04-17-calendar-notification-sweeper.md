# Calendar Notification Sweeper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI that, when run daily, silences notifications on Gmail-extracted and Reclaim-created Google Calendar events while leaving real meetings untouched.

**Architecture:** Stateless CLI. Each run: authenticate via OAuth → fetch upcoming events → classify via YAML rules → patch `reminders` on matches → log → exit. Four modules: `classify` (pure, unit-tested), `config` (YAML load), `auth` (OAuth), `sweeper` (orchestration). CLI entry `main.py`. Scheduled daily via Windows Task Scheduler.

**Tech Stack:** Python 3.10+, `google-api-python-client`, `google-auth-oauthlib`, `PyYAML`, `pytest`.

---

## File map

| Path | Purpose |
|---|---|
| `requirements.txt` | pinned dependencies |
| `config.yaml` | silence rules + never-silence allow-list + scan window |
| `calendar_reminder/__init__.py` | package marker (empty) |
| `calendar_reminder/config.py` | load + validate YAML config |
| `calendar_reminder/classify.py` | pure classifier: `classify(event, config)` |
| `calendar_reminder/auth.py` | OAuth flow + token refresh, returns Calendar service |
| `calendar_reminder/sweeper.py` | fetch events, apply classifier, patch reminders, emit log lines |
| `main.py` | CLI entry: argparse flags, wires modules together |
| `tests/__init__.py` | package marker (empty) |
| `tests/test_classify.py` | unit tests for classifier |
| `tests/test_config.py` | unit tests for config loader |
| `logs/` | runtime log output (gitignored) |

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
pytest==8.3.3
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

## Task 16: Windows Task Scheduler registration

**Files:** none (external config).

- [ ] **Step 1: Open Task Scheduler**

Start → "Task Scheduler" → Task Scheduler Library → right-click → Create Task… (not "Create Basic Task" — we need the richer form).

- [ ] **Step 2: General tab**

- Name: `Calendar Reminder Sweep`
- "Run whether user is logged on or not": checked
- "Run with highest privileges": unchecked

- [ ] **Step 3: Triggers tab**

Add trigger:
- Daily
- Start: tomorrow at 06:00
- Recur every: 1 day

- [ ] **Step 4: Actions tab**

Add action:
- Action: Start a program
- Program/script: `D:\Calendar Reminder\.venv\Scripts\pythonw.exe`
- Add arguments: `main.py`
- Start in: `D:\Calendar Reminder`

- [ ] **Step 5: Settings tab**

- "Allow task to be run on demand": checked
- "Run task as soon as possible after a scheduled start is missed": checked
- "If the task fails, restart every": 1 hour, up to 3 attempts

- [ ] **Step 6: Save (will prompt for Windows password)**

- [ ] **Step 7: Run-on-demand test**

Right-click the task → Run. Wait a few seconds. Check `logs/sweep-YYYY-MM-DD.log` for a fresh run entry.

- [ ] **Step 8: Commit any tweaks to config.yaml that came out of live runs**

```bash
git status
git add config.yaml   # if it changed
git commit -m "chore(config): tune silence rules after live validation"
```

---

## Self-review (executed while writing this plan)

**Spec coverage check:**
- Problem + goal → addressed end-to-end.
- Architecture/components (classify, config, auth, sweeper, main) → one task each, plus skeleton (Task 1), gitignore (Task 11), cloud setup (Task 12), verification (Tasks 13–15), scheduler (Task 16).
- Classification rules: Tier 1 gmail (Task 2), Tier 1 reclaim organizer (Task 3), Tier 1 extendedProperties (Task 4), Tier 3 title regex (Task 5), never_silence (Task 6). ✓
- Idempotency → covered by `_already_silenced` check in Task 9, verified in Task 14 Step 3.
- Error handling (5xx/429 retry, token expiry, malformed event, malformed config) → retry logic in `_patch_silence`, per-event try/except in sweep loop, FileNotFoundError for missing credentials, ValueError for bad config.
- Logging format matches spec. End-of-run SUMMARY matches spec.
- OAuth scope limited to `calendar.events`. ✓
- Scheduler config (6 AM daily, pythonw, run-whether-logged-on, missed-run catchup) → Task 16. ✓
- Rollout plan (dry-run 7d → live 7d → dry-run 30d → live 30d → schedule) → Tasks 13 → 14 → 15 → 16. ✓
- Tests (classify unit tests with fixtures, no live-API tests) → Tasks 2–6, plus sweeper test with fake service. ✓

**Placeholder scan:** no TBD/TODO/"implement later". Every step that modifies code shows the actual code.

**Type consistency:** `classify(event, config) -> (str, str|None)` used consistently; `sweep(service, config, dry_run=False, days_override=None)` used consistently. `_calendarId` injected in sweeper and referenced in classifier — consistent.

---

## Execution handoff

Plan complete. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks
2. **Inline Execution** — run tasks in this session with checkpoints

Pick one.
