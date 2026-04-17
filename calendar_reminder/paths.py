import os
import sys
from pathlib import Path


def _is_frozen():
    return bool(getattr(sys, "frozen", False))


def app_data_dir():
    """Base directory for user-specific runtime data."""
    if _is_frozen():
        base = os.environ.get("APPDATA", "")
        return Path(base) / "CalendarReminder"
    return Path.cwd()


def config_path():
    return app_data_dir() / "config.yaml"


def credentials_path():
    return app_data_dir() / "credentials.json"


def token_path():
    return app_data_dir() / "token.json"


def state_path():
    return app_data_dir() / "state.json"


def log_dir():
    return app_data_dir() / "logs"


def ensure_app_data_dir():
    app_data_dir().mkdir(parents=True, exist_ok=True)
    log_dir().mkdir(parents=True, exist_ok=True)
