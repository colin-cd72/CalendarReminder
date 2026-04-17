import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox

import pystray
from PIL import Image, ImageDraw

from calendar_reminder import paths
from calendar_reminder.auth import get_service
from calendar_reminder.config import load_config
from calendar_reminder.sweeper import sweep


log = logging.getLogger("calendar_reminder")

SWEEP_INTERVAL_SEC = 24 * 60 * 60
TIMER_TICK_SEC = 60 * 60


def _make_icon_image():
    img = Image.new("RGB", (64, 64), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), fill="#2e7d32", outline="#1b5e20", width=2)
    d.rectangle((28, 18, 36, 40), fill="white")
    d.rectangle((28, 42, 36, 48), fill="white")
    return img


def _read_state():
    p = paths.state_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(state):
    paths.state_path().write_text(json.dumps(state), encoding="utf-8")


def _setup_logging():
    paths.ensure_app_data_dir()
    log_path = paths.log_dir() / f"sweep-{datetime.now().strftime('%Y-%m-%d')}.log"
    fmt = logging.Formatter("%(asctime)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    file_h = logging.FileHandler(log_path, encoding="utf-8")
    file_h.setFormatter(fmt)
    logger = logging.getLogger("calendar_reminder")
    logger.handlers.clear()
    logger.addHandler(file_h)
    logger.setLevel(logging.INFO)


def _ensure_config_present():
    """Copy shipped template to AppData on first run."""
    target = paths.config_path()
    if target.exists():
        return
    paths.ensure_app_data_dir()
    # Shipped template location differs: source tree uses repo root; frozen exe uses sys._MEIPASS
    if getattr(sys, "frozen", False):
        src = Path(sys._MEIPASS) / "config.yaml"
    else:
        src = Path.cwd() / "config.yaml"
    if src.exists():
        shutil.copy(src, target)


def _prompt_for_credentials():
    """Blocking tkinter dialog. Returns True if user provided credentials.json."""
    root = tk.Tk()
    root.withdraw()
    instructions = (
        "Calendar Reminder needs OAuth credentials to access Google Calendar.\n\n"
        "1. Open https://console.cloud.google.com/apis/credentials\n"
        "2. Create a Desktop app OAuth client (or use an existing one)\n"
        "3. Download the JSON and save it as:\n"
        f"      {paths.credentials_path()}\n"
        "4. Click OK when done."
    )
    while not paths.credentials_path().exists():
        messagebox.showinfo("Calendar Reminder — First-run setup", instructions)
        if not paths.credentials_path().exists():
            if not messagebox.askretrycancel(
                "credentials.json still missing",
                f"Could not find {paths.credentials_path()}.\nRetry?",
            ):
                root.destroy()
                return False
    root.destroy()
    return True


def _install_startup_shortcut():
    """Create a Windows Startup folder shortcut so the app auto-launches on login."""
    if not getattr(sys, "frozen", False):
        return  # dev mode: no shortcut
    startup = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"
    lnk = startup / "CalendarReminder.lnk"
    if lnk.exists():
        return
    target = sys.executable
    ps = (
        f"$s = (New-Object -COM WScript.Shell).CreateShortcut('{lnk}'); "
        f"$s.TargetPath = '{target}'; "
        f"$s.WorkingDirectory = '{Path(target).parent}'; "
        f"$s.Save()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        log.error("Failed to install startup shortcut: %s", e)


class TrayApp:
    def __init__(self):
        self._icon = None
        self._sweep_lock = threading.Lock()
        self._stop = threading.Event()
        self._last_result = "No sweep yet this session"

    def _run_sweep(self, dry_run):
        if not self._sweep_lock.acquire(blocking=False):
            self._icon.notify("A sweep is already running.", "Calendar Reminder")
            return
        try:
            try:
                cfg = load_config(str(paths.config_path()))
                service = get_service(
                    credentials_path=str(paths.credentials_path()),
                    token_path=str(paths.token_path()),
                )
                counts = sweep(service, cfg, dry_run=dry_run)
                suffix = " (dry-run)" if dry_run else ""
                self._last_result = (
                    f"Last: {datetime.now().strftime('%H:%M')} "
                    f"silenced={counts['silenced']} kept={counts['kept']}{suffix}"
                )
                if not dry_run:
                    _write_state({"last_sweep_at": datetime.now(timezone.utc).isoformat()})
            except Exception as e:
                log.exception("Sweep failed")
                self._icon.notify(f"Sweep failed: {e}", "Calendar Reminder")
                self._last_result = f"Last: {datetime.now().strftime('%H:%M')} ERROR"
            finally:
                if self._icon:
                    self._icon.title = f"Calendar Reminder\n{self._last_result}"
        finally:
            self._sweep_lock.release()

    def _on_sweep_now(self, icon, item):
        threading.Thread(target=self._run_sweep, args=(False,), daemon=True).start()

    def _on_dry_run(self, icon, item):
        threading.Thread(target=self._run_sweep, args=(True,), daemon=True).start()

    def _on_open_log(self, icon, item):
        p = paths.log_dir() / f"sweep-{datetime.now().strftime('%Y-%m-%d')}.log"
        if p.exists():
            os.startfile(p)
        else:
            icon.notify("No log yet for today.", "Calendar Reminder")

    def _on_open_config(self, icon, item):
        p = paths.config_path()
        if p.exists():
            os.startfile(p)

    def _on_quit(self, icon, item):
        self._stop.set()
        icon.stop()

    def _timer_loop(self):
        while not self._stop.wait(TIMER_TICK_SEC):
            state = _read_state()
            last = state.get("last_sweep_at")
            due = True
            if last:
                try:
                    last_dt = datetime.fromisoformat(last)
                    age = (datetime.now(timezone.utc) - last_dt).total_seconds()
                    due = age >= SWEEP_INTERVAL_SEC
                except ValueError:
                    pass
            if due:
                self._run_sweep(dry_run=False)

    def run(self):
        _setup_logging()
        _ensure_config_present()
        if not paths.credentials_path().exists():
            if not _prompt_for_credentials():
                return
        _install_startup_shortcut()

        menu = pystray.Menu(
            pystray.MenuItem("Sweep now", self._on_sweep_now, default=True),
            pystray.MenuItem("Sweep now (dry run)", self._on_dry_run),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open today's log", self._on_open_log),
            pystray.MenuItem("Open config", self._on_open_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )
        self._icon = pystray.Icon(
            "CalendarReminder",
            _make_icon_image(),
            f"Calendar Reminder\n{self._last_result}",
            menu,
        )
        threading.Thread(target=self._timer_loop, daemon=True).start()
        self._icon.run()


def main():
    TrayApp().run()


if __name__ == "__main__":
    main()
