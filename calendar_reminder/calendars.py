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


def show_sweep_progress(worker_fn, title="Calendar Reminder"):
    """Show a progress window while running worker_fn in a background thread.
    When worker_fn finishes, the window displays a summary of the counts dict.
    User clicks Close to dismiss. Returns the counts dict (or None if it failed).
    """
    import threading
    import traceback
    import tkinter as tk
    from tkinter import ttk

    result = {"counts": None, "error": None, "done": False}

    def worker():
        try:
            result["counts"] = worker_fn()
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"
        result["done"] = True

    window = tk.Tk()
    window.title(title)
    window.geometry("440x300")

    frame = tk.Frame(window, padx=22, pady=18)
    frame.pack(fill="both", expand=True)

    status_label = tk.Label(
        frame, text="Running sweep…", font=("", 11), justify="left",
    )
    status_label.pack(pady=(8, 14), anchor="w")

    progress = ttk.Progressbar(frame, mode="indeterminate", length=380)
    progress.pack(pady=4)
    progress.start(10)

    detail_label = tk.Label(
        frame, text="Fetching events from your calendars…",
        font=("", 9), fg="#555", justify="left", wraplength=380,
    )
    detail_label.pack(pady=(10, 4), anchor="w")

    btn_frame = tk.Frame(frame)
    btn_frame.pack(side="bottom", pady=10)
    close_btn = tk.Button(btn_frame, text="Close", command=window.destroy, state="disabled")
    close_btn.pack()

    def check_done():
        if not result["done"]:
            window.after(150, check_done)
            return
        progress.stop()
        progress.pack_forget()
        detail_label.pack_forget()
        if result["error"]:
            status_label.config(
                text=f"Sweep failed:\n\n{result['error']}",
                fg="#b00", wraplength=380,
            )
        else:
            c = result["counts"]
            status_label.config(
                text=(
                    "✅  Sweep complete\n\n"
                    f"   Scanned:   {c['scanned']} events\n"
                    f"   Silenced:  {c['silenced']}\n"
                    f"   Kept:      {c['kept']} (real meetings)\n"
                    f"   Skipped:   {c['skipped']} (already silent)\n"
                    f"   Errors:    {c['errors']}"
                ),
                font=("Consolas", 10),
            )
        close_btn.config(state="normal")

    threading.Thread(target=worker, daemon=True).start()
    window.after(150, check_done)
    window.mainloop()

    return result["counts"]


def preview_sweep_dialog(candidates):
    """Show candidates in a checkbox list. Returns the approved subset, or None if cancelled.

    Each candidate is a dict with at least: id, summary, cal_id, rule.
    Checkboxes are pre-checked. User unchecks any to spare, clicks Silence or Cancel.
    """
    import tkinter as tk
    from tkinter import ttk

    result = {"cancelled": True, "confirmed": []}

    root = tk.Tk()
    root.title("Calendar Reminder — Preview changes")
    root.geometry("640x580")

    tk.Label(
        root,
        text=f"{len(candidates)} event(s) matched silence rules and will have their notifications cleared:",
        wraplength=600, justify="left", font=("", 10, "bold"),
    ).pack(padx=12, pady=(12, 4), anchor="w")

    tk.Label(
        root,
        text="Uncheck any you'd rather keep notifying.",
        wraplength=600, justify="left", fg="#555",
    ).pack(padx=12, pady=(0, 10), anchor="w")

    container = tk.Frame(root, bd=1, relief="sunken")
    container.pack(fill="both", expand=True, padx=12)
    canvas = tk.Canvas(container, highlightthickness=0)
    sb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    scroll_frame = tk.Frame(canvas)
    scroll_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    def _wheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _wheel)

    vars_by_idx = {}
    for i, c in enumerate(candidates):
        v = tk.BooleanVar(value=True)
        text = f'{c.get("summary") or "(no title)"}   —   rule: {c.get("rule", "?")}'
        tk.Checkbutton(
            scroll_frame, text=text, variable=v, anchor="w", padx=6, pady=1,
        ).pack(anchor="w", fill="x")
        vars_by_idx[i] = v

    btn_frame = tk.Frame(root)
    btn_frame.pack(fill="x", padx=12, pady=12)

    def on_silence():
        result["cancelled"] = False
        result["confirmed"] = [candidates[i] for i, v in vars_by_idx.items() if v.get()]
        root.destroy()

    def on_cancel():
        result["cancelled"] = True
        root.destroy()

    tk.Button(btn_frame, text="Cancel", command=on_cancel).pack(side="right", padx=(6, 0))
    tk.Button(
        btn_frame, text="Silence checked events", command=on_silence, default="active",
    ).pack(side="right")

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()

    if result["cancelled"]:
        return None
    return result["confirmed"]


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
