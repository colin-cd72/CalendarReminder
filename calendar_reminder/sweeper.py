import datetime as dt
import logging
import time

from googleapiclient.errors import HttpError

from calendar_reminder.classify import classify


log = logging.getLogger("calendar_reminder")


def _now_utc():
    return dt.datetime.now(dt.timezone.utc)


def _list_events(service, calendar_id, time_min, time_max):
    events = []
    page_token = None
    while True:
        resp = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token,
            maxResults=250,
        ).execute()
        for ev in resp.get("items", []):
            ev["_calendarId"] = calendar_id
            events.append(ev)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return events


def _already_silenced(event):
    reminders = event.get("reminders") or {}
    return reminders.get("useDefault") is False and not reminders.get("overrides")


def _patch_silence(service, calendar_id, event_id):
    body = {"reminders": {"useDefault": False, "overrides": []}}
    for attempt in range(3):
        try:
            service.events().patch(
                calendarId=calendar_id, eventId=event_id, body=body,
            ).execute()
            return True
        except HttpError as e:
            status = getattr(e, "status_code", None) or getattr(e.resp, "status", None)
            if status in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise


def collect_silence_candidates(service, config, days_override=None):
    """Fetch and classify events. Return a list of actionable silence candidates
    (already-silenced events are excluded).

    Each candidate is a dict: {id, summary, cal_id, rule}.
    """
    days = days_override if days_override is not None else config["scan"]["days_ahead"]
    calendar_ids = config["scan"].get("calendars") or ["primary"]
    now = _now_utc()
    time_min = now.isoformat()
    time_max = (now + dt.timedelta(days=days)).isoformat()

    events = []
    for cal_id in calendar_ids:
        events.extend(_list_events(service, cal_id, time_min, time_max))

    candidates = []
    for ev in events:
        action, rule = classify(ev, config)
        if action == "silence" and not _already_silenced(ev):
            candidates.append({
                "id": ev.get("id", "?"),
                "summary": ev.get("summary", ""),
                "cal_id": ev.get("_calendarId", "primary"),
                "rule": rule,
            })
    return candidates


def patch_events(service, candidates):
    """Silence each event in the list. Returns counts dict."""
    silenced = 0
    errors = 0
    for item in candidates:
        try:
            _patch_silence(service, item["cal_id"], item["id"])
            silenced += 1
            log.info('SILENCED | evt=%s | "%s" | rule=%s',
                     item["id"], item["summary"], item["rule"])
        except Exception as exc:
            errors += 1
            log.error('ERROR | evt=%s | "%s" | exc=%s',
                      item["id"], item["summary"], exc)
    return {"silenced": silenced, "errors": errors}


def sweep(service, config, dry_run=False, days_override=None):
    """Run one sweep. Returns counts dict."""
    days = days_override if days_override is not None else config["scan"]["days_ahead"]
    calendar_ids = config["scan"].get("calendars") or ["primary"]
    now = _now_utc()
    time_min = now.isoformat()
    time_max = (now + dt.timedelta(days=days)).isoformat()

    counts = {"scanned": 0, "silenced": 0, "kept": 0, "skipped": 0, "errors": 0}
    start = time.monotonic()

    events = []
    for cal_id in calendar_ids:
        events.extend(_list_events(service, cal_id, time_min, time_max))

    for ev in events:
        counts["scanned"] += 1
        summary = ev.get("summary", "")
        ev_id = ev.get("id", "?")
        cal_id = ev.get("_calendarId", "primary")
        try:
            action, rule = classify(ev, config)
            if action == "silence":
                if _already_silenced(ev):
                    counts["skipped"] += 1
                    log.info('SKIP | evt=%s | "%s" | reason=already_silenced', ev_id, summary)
                    continue
                if dry_run:
                    counts["silenced"] += 1
                    log.info('DRY-RUN-SILENCE | evt=%s | "%s" | rule=%s', ev_id, summary, rule)
                else:
                    _patch_silence(service, cal_id, ev_id)
                    counts["silenced"] += 1
                    log.info('SILENCED | evt=%s | "%s" | rule=%s', ev_id, summary, rule)
            else:
                counts["kept"] += 1
                log.debug('KEPT | evt=%s | "%s" | rule=none', ev_id, summary)
        except Exception as exc:
            counts["errors"] += 1
            log.error('ERROR | evt=%s | "%s" | exc=%s', ev_id, summary, exc)

    duration = time.monotonic() - start
    log.info(
        "SUMMARY: scanned=%d silenced=%d kept=%d skipped=%d errors=%d duration=%.1fs",
        counts["scanned"], counts["silenced"], counts["kept"],
        counts["skipped"], counts["errors"], duration,
    )
    return counts
