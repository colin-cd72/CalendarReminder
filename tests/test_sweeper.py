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
