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
