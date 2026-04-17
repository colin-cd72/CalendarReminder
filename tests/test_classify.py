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
