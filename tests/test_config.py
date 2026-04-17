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
