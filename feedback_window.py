"""Leave Feedback window (Tk). Reusable: needs feedback.py and a FeedbackConfig.

    open_feedback_window(parent, config, colors={"bg", "panel", "fg", "accent", "muted"})

Nothing is collected or sent until the user presses Send. System information is
only gathered when its box is ticked, and the exact text is shown first.
"""
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

import feedback

DEFAULT_COLORS = {"bg": "#1e1e1e", "panel": "#2a2a2a", "fg": "#e0e0e0", "accent": "#0e639c", "muted": "#888888"}


def open_feedback_window(parent, config, colors=None, settings=None):
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
    type_labels = [lab for _k, lab, _t in feedback.REPORT_TYPES]
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
    spec_state = {"text": None, "job": 0}

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
            result["text"] = feedback.system_text(feedback.collect_system(), config)

        t = threading.Thread(target=work, daemon=True)
        t.start()

        def poll():
            if not win.winfo_exists():
                return
            if t.is_alive():
                win.after(150, poll)
                return
            spec_state["text"] = result.get("text", "")
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
        key = next((k for k, lab, _t in feedback.REPORT_TYPES if lab == type_var.get()), "other")
        return {"type": key, "name": name_var.get(), "title": title_var.get(),
                "description": desc.get("1.0", tk.END)}

    def system():
        return spec_state["text"] if include_var.get() and spec_state["text"] else None

    def open_email_app(report):
        url = feedback.mailto_url(config.to_address, feedback.build_subject(config, report),
                                  feedback.build_body(config, report, system()))
        try:
            webbrowser.open(url)
        except Exception:
            pass
        win.clipboard_clear()
        win.clipboard_append(feedback.build_body(config, report, system()))
        messagebox.showinfo(
            "Send by email",
            f"Your email app should open with the report addressed to {config.to_address}. "
            "Press Send there.\n\nThe full report is also copied to your clipboard in case it did not open.",
            parent=win)
        win.destroy()

    def send():
        report = form()
        problems = feedback.validate(report)
        if problems:
            messagebox.showwarning("Check the form", "\n".join(problems), parent=win)
            return
        if include_var.get() and spec_state["text"] is None:
            status_label.configure(text="Still reading your specifications, try again in a moment.")
            return
        relay = feedback.load_relay_url(settings, getattr(parent, "base_dir", None))
        if not feedback.relay_ok(relay):
            open_email_app(report)
            return
        payload = feedback.build_payload(config, report, system())
        send_btn.configure(state=tk.DISABLED)
        status_label.configure(text="Sending...")
        result = {}

        def work():
            result["r"] = feedback.send_via_relay(relay, payload)

        t = threading.Thread(target=work, daemon=True)
        t.start()

        def poll():
            if not win.winfo_exists():
                return
            if t.is_alive():
                win.after(150, poll)
                return
            ok, message = result.get("r", (False, "Unknown error."))
            if ok:
                messagebox.showinfo("Feedback sent", message, parent=win)
                win.destroy()
                return
            send_btn.configure(state=tk.NORMAL)
            status_label.configure(text="")
            if messagebox.askyesno("Could not send",
                                   f"{message}\n\nOpen your email app with the report instead?", parent=win):
                open_email_app(report)
        poll()

    send_btn.configure(command=send)
    win.bind("<Escape>", lambda e: win.destroy())
    title_entry.focus_set()
    return win
