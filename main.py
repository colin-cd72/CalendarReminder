import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

from calendar_reminder.auth import get_service
from calendar_reminder.config import load_config
from calendar_reminder.sweeper import sweep


def _setup_logging(log_dir, verbose):
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"sweep-{date.today().isoformat()}.log"

    fmt = logging.Formatter("%(asctime)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    file_h = logging.FileHandler(log_path, encoding="utf-8")
    file_h.setFormatter(fmt)
    stream_h = logging.StreamHandler(sys.stdout)
    stream_h.setFormatter(fmt)

    logger = logging.getLogger("calendar_reminder")
    logger.handlers.clear()
    logger.addHandler(file_h)
    logger.addHandler(stream_h)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)


def _rotate_logs(log_dir, keep_days=30):
    if not log_dir.exists():
        return
    from time import time
    cutoff = time() - keep_days * 86400
    for p in log_dir.glob("sweep-*.log"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sweep auto-inserted Google Calendar notifications.")
    parser.add_argument("--dry-run", action="store_true", help="Log what would change, don't modify events.")
    parser.add_argument("--days", type=int, default=None, help="Scan window override (days ahead).")
    parser.add_argument("--verbose", action="store_true", help="Include KEPT events in log output.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    args = parser.parse_args(argv)

    project_root = Path(__file__).parent
    os.chdir(project_root)

    log_dir = project_root / "logs"
    _setup_logging(log_dir, args.verbose)
    _rotate_logs(log_dir)

    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2

    try:
        service = get_service()
    except FileNotFoundError as e:
        print(f"Auth error: {e}", file=sys.stderr)
        return 3

    counts = sweep(service, cfg, dry_run=args.dry_run, days_override=args.days)
    return 0 if counts["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
