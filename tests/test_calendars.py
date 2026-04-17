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
