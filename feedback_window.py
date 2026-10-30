"""Leave Feedback window (Tk). Reusable: needs the feedback_kit package and a FeedbackConfig.

    open_feedback_window(parent, config, colors={"bg", "panel", "fg", "accent", "muted"})

Nothing is collected or sent until the user presses Send. System information is
only gathered when its box is ticked, and the exact text is shown first.
"""
import dataclasses
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from feedback_kit import (REPORT_TYPES, Report, collect_system_info, format_system_info, send_report, validate)

DEFAULT_COLORS = {"bg": "#1e1e1e", "panel": "#2a2a2a", "fg": "#e0e0e0", "accent": "#0e639c", "muted": "#888888"}


def open_feedback_window(parent, config, colors=None):
    c = {**DEFAULT_COLORS, **(colors or {})}
    existing = getattr(parent, "_feedback_win", None)
    if existing is not None and existing.winfo_exists():
        existing.lift()
        existing.focus_force()
        return existing

    win = tk.Toplevel(parent)
    parent._feedback_win = win
    win.title("Leave Feedback")
    win.configure(bg=c["bg"])
    win.geometry("560x640")
    win.minsize(460, 520)
    win.transient(parent)

    def label(text, **kw):
        return tk.Label(win, text=text, bg=c["bg"], fg=kw.pop("fg", c["fg"]), anchor="w",
                        font=kw.pop("font", ("Segoe UI", 9)), **kw)

    def entry(var):
        return tk.Entry(win, textvariable=var, bg=c["panel"], fg=c["fg"], insertbackground=c["fg"],
                        relief=tk.FLAT, font=("Segoe UI", 10))

    label("Report type").pack(fill=tk.X, padx=14, pady=(14, 2))
    type_labels = [lab for lab, _t in REPORT_TYPES]
    type_var = tk.StringVar(value=type_labels[0])
    ttk.Combobox(win, textvariable=type_var, values=type_labels, state="readonly").pack(fill=tk.X, padx=14)

    label(f"Application: {config.app_name}    Version: {config.app_version}", fg=c["muted"]).pack(fill=tk.X, padx=14, pady=(8, 0))

    label("Your name (optional)").pack(fill=tk.X, padx=14, pady=(8, 2))
    name_var = tk.StringVar()
    entry(name_var).pack(fill=tk.X, padx=14, ipady=3)

    label("Title").pack(fill=tk.X, padx=14, pady=(8, 2))
    title_var = tk.StringVar()
    title_entry = entry(title_var)
    title_entry.pack(fill=tk.X, padx=14, ipady=3)
    label("e.g. UI is not working, Application crashes on startup, Feature suggestion: custom themes",
          fg=c["muted"], font=("Segoe UI", 8)).pack(fill=tk.X, padx=14)

    label("Description").pack(fill=tk.X, padx=14, pady=(8, 2))
    desc = tk.Text(win, height=8, bg=c["panel"], fg=c["fg"], insertbackground=c["fg"], relief=tk.FLAT,
                   wrap=tk.WORD, font=("Segoe UI", 10))
    desc.pack(fill=tk.BOTH, expand=True, padx=14)

    include_var = tk.BooleanVar(value=False)
    spec_box = tk.Text(win, height=6, bg=c["panel"], fg=c["muted"], relief=tk.FLAT, wrap=tk.WORD,
                       font=("Consolas", 9), state=tk.DISABLED)
    spec_state = {"text": None, "info": {}}

    def show_specs(text):
        spec_box.configure(state=tk.NORMAL)
        spec_box.delete("1.0", tk.END)
        spec_box.insert("1.0", text)
        spec_box.configure(state=tk.DISABLED)

    def toggle_specs():
        if not include_var.get():
            spec_box.pack_forget()
            return
        spec_box.pack(fill=tk.X, padx=14, pady=(4, 0), before=status_label)
        if spec_state["text"] is not None:
            show_specs("This will be sent with your report:\n\n" + spec_state["text"])
            return
        show_specs("Reading your computer's specifications...")
        result = {}

        def work():
            result["info"] = collect_system_info(config.app_version)

        t = threading.Thread(target=work, daemon=True)
        t.start()

        def poll():
            if not win.winfo_exists():
                return
            if t.is_alive():
                win.after(150, poll)
                return
            spec_state["info"] = result.get("info", {})
            spec_state["text"] = "\n".join(format_system_info(spec_state["info"]))
            if include_var.get():
                show_specs("This will be sent with your report:\n\n" + spec_state["text"])
        poll()

    tk.Checkbutton(win, text="Include my computer specifications (OS, CPU, GPU, RAM, architecture)",
                   variable=include_var, command=toggle_specs, bg=c["bg"], fg=c["fg"], selectcolor=c["panel"],
                   activebackground=c["bg"], activeforeground=c["fg"], anchor="w",
                   font=("Segoe UI", 9)).pack(fill=tk.X, padx=14, pady=(8, 0))

    status_label = tk.Label(win, text="", bg=c["bg"], fg=c["muted"], anchor="w", font=("Segoe UI", 9),
                            wraplength=520, justify=tk.LEFT)
    status_label.pack(fill=tk.X, padx=14, pady=(6, 0))

    buttons = tk.Frame(win, bg=c["bg"])
    buttons.pack(fill=tk.X, padx=14, pady=12)
    send_btn = tk.Button(buttons, text="Send", bg=c["accent"], fg="#ffffff", relief=tk.FLAT, cursor="hand2",
                         font=("Segoe UI", 9, "bold"), width=10)
    send_btn.pack(side=tk.RIGHT)
    tk.Button(buttons, text="Cancel", bg=c["panel"], fg=c["fg"], relief=tk.FLAT, cursor="hand2",
              width=10, command=win.destroy).pack(side=tk.RIGHT, padx=(0, 8))

    def form():
        index = type_labels.index(type_var.get()) if type_var.get() in type_labels else len(type_labels) - 1
        return Report(type_index=index, name=name_var.get(), title=title_var.get(),
                      description=desc.get("1.0", tk.END),
                      system=spec_state["info"] if include_var.get() and spec_state["text"] else {})

    def deliver(cfg, report, on_done):
        """Send off the UI thread; on_done(SendResult) runs back on it."""
        result = {}

        def work():
            try:
                result["r"] = send_report(cfg, report)
            except Exception as e:                       # never let a thread die silently
                result["r"] = type("R", (), {"ok": False, "message": f"Could not send ({e}).", "method": ""})()
        t = threading.Thread(target=work, daemon=True)
        t.start()

        def poll():
            if not win.winfo_exists():
                return
            if t.is_alive():
                win.after(150, poll)
                return
            on_done(result["r"])
        poll()

    def open_email_app(report):
        """The kit's no-relay path: the user's own mail app opens with the report."""
        send_btn.configure(state=tk.DISABLED)
        status_label.configure(text="Opening your email app...")

        def done(r):
            send_btn.configure(state=tk.NORMAL)
            status_label.configure(text="")
            (messagebox.showinfo if r.ok else messagebox.showwarning)("Send by email", r.message, parent=win)
            if r.ok:
                win.destroy()
        deliver(dataclasses.replace(config, endpoint=""), report, done)

    def send():
        report = form()
        problems = validate(report)
        if problems:
            messagebox.showwarning("Check the form", "\n".join(problems), parent=win)
            return
        if include_var.get() and spec_state["text"] is None:
            status_label.configure(text="Still reading your specifications, try again in a moment.")
            return
        if not config.endpoint:
            open_email_app(report)
            return
        send_btn.configure(state=tk.DISABLED)
        status_label.configure(text="Sending...")

        def done(r):
            if r.ok:
                messagebox.showinfo("Feedback sent", r.message, parent=win)
                win.destroy()
                return
            send_btn.configure(state=tk.NORMAL)
            status_label.configure(text="")
            if messagebox.askyesno("Could not send",
                                   f"{r.message}\n\nOpen your email app with the report instead?", parent=win):
                open_email_app(report)
        deliver(config, report, done)

    send_btn.configure(command=send)
    win.bind("<Escape>", lambda e: win.destroy())
    title_entry.focus_set()
    return win
