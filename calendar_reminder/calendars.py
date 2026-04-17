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


def pick_calendars_dialog(calendars, currently_selected=None):
    """Show a tkinter modal with checkboxes. Returns list of selected calendar IDs.

    If the user closes the window without clicking Save, returns currently_selected
    (or an empty list) to avoid silently clearing their existing choice.
    """
    import tkinter as tk
    from tkinter import ttk

    pre_selected = set(currently_selected or [])
    result = {"saved": False, "ids": list(pre_selected)}

    root = tk.Tk()
    root.title("Calendar Reminder — Select Calendars")
    root.geometry("560x560")

    header = tk.Label(
        root,
        text="Check the calendars you want swept for notification noise.",
        wraplength=520, justify="left", font=("", 10, "bold"),
    )
    header.pack(padx=12, pady=(12, 4), anchor="w")

    sub = tk.Label(
        root,
        text="Auto-events like flights, hotels, and Reclaim blocks get silenced.\nReal meetings and appointments are never touched.",
        wraplength=520, justify="left", fg="#555",
    )
    sub.pack(padx=12, pady=(0, 10), anchor="w")

    container = tk.Frame(root, bd=1, relief="sunken")
    container.pack(fill="both", expand=True, padx=12)

    canvas = tk.Canvas(container, highlightthickness=0)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    scroll_frame = tk.Frame(canvas)
    scroll_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    vars_by_id = {}
    for c in calendars:
        default_on = c["id"] in pre_selected if pre_selected else bool(c.get("primary"))
        v = tk.BooleanVar(value=default_on)
        primary_mark = "  ⭐ primary" if c.get("primary") else ""
        text = f"{c['summary']}{primary_mark}"
        tk.Checkbutton(
            scroll_frame, text=text, variable=v, anchor="w", padx=6, pady=1,
        ).pack(anchor="w", fill="x")
        vars_by_id[c["id"]] = v

    btn_frame = tk.Frame(root)
    btn_frame.pack(fill="x", padx=12, pady=12)

    def select_all():
        for v in vars_by_id.values():
            v.set(True)

    def clear_all():
        for v in vars_by_id.values():
            v.set(False)

    def on_save():
        result["ids"] = [cid for cid, v in vars_by_id.items() if v.get()]
        result["saved"] = True
        root.destroy()

    def on_cancel():
        root.destroy()

    tk.Button(btn_frame, text="Select All", command=select_all).pack(side="left")
    tk.Button(btn_frame, text="Clear All", command=clear_all).pack(side="left", padx=6)
    tk.Button(btn_frame, text="Cancel", command=on_cancel).pack(side="right", padx=(6, 0))
    tk.Button(btn_frame, text="Save", command=on_save, default="active").pack(side="right")

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()

    return result["ids"]
