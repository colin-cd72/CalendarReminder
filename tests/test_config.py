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
