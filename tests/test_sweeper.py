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
