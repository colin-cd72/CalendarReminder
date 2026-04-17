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
