def list_user_calendars(service):
    """Return writable calendars: [{id, summary, primary, accessRole}, ...]"""
    resp = service.calendarList().list().execute()
    out = []
    for item in resp.get("items", []):
        if item.get("accessRole") not in ("owner", "writer"):
            continue
        out.append({
            "id": item["id"],
            "summary": item.get("summary", "(no name)"),
            "primary": item.get("primary", False),
            "accessRole": item["accessRole"],
        })
    return out


def pick_calendars_interactive(calendars):
    """Prompt via stdin. Returns list of selected calendar IDs."""
    print("\nAvailable calendars:")
    for i, c in enumerate(calendars, 1):
        primary = " (primary)" if c["primary"] else ""
        print(f"  [{i}] {c['summary']} — {c['id']} [{c['accessRole']}]{primary}")

    while True:
        raw = input("\nPick (comma-separated numbers, or 'all'): ").strip()
        if raw.lower() == "all":
            return [c["id"] for c in calendars]
        try:
            indices = [int(x.strip()) for x in raw.split(",") if x.strip()]
            if indices and all(1 <= i <= len(calendars) for i in indices):
                return [calendars[i - 1]["id"] for i in indices]
        except ValueError:
            pass
        print("Invalid input. Try again.")
