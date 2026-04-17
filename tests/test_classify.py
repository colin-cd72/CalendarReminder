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
