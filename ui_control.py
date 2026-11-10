"""Outside AI tools (Tools > AI tools connection...). Switching it on starts a local,
token-protected channel (control_server.py) that the MCP bridge (blockliner_mcp.py)
talks to, so an AI agent such as Claude Code can read the open project and, if the
user allows, change it. Off by default every time Blockliner starts; the user picks
read-only or read-and-edit, and can require approval of every change.
Requests are answered on the Tk thread, like extension requests. See
docs/design-extensions.md section 14."""
import json
import os
import queue
import sys
import time
import tkinter as tk
from tkinter import messagebox

import control_server as C
import ext_runner
from ui_common import APP_SETTINGS_PATH, DARK_ACCENT, DARK_BG, DARK_BORDER, DARK_FG, DARK_PANEL, get_bundle_path

PUMP_MS = 200
READ_WAIT = 30
EDIT_WAIT = 330                    # an approval prompt may wait for the user


class ControlMixin:

    def install_control(self):
        self._control = None
        self._control_inbox = queue.Queue()
        self.after(PUMP_MS, self._control_pump)

    def control_file_path(self):
        return os.path.join(os.path.dirname(APP_SETTINGS_PATH), "control.json")

    def control_access(self):
        return "edit" if self.settings.get("control_access") == "edit" else "read"

    def control_running(self):
        return self._control is not None and self._control.running

    def start_control(self):
        if self.control_running():
            return
        server = C.ControlServer(self._control_handler, access=self.control_access())
        port, token = server.start()
        C.write_control_file(self.control_file_path(), port, token, server.access)
        self._control = server

    def stop_control(self):
        if self._control is not None:
            self._control.stop()
            self._control = None
        C.remove_control_file(self.control_file_path())

    def set_control_access(self, access):
        self.settings["control_access"] = "edit" if access == "edit" else "read"
        self.save_app_settings()
        if self.control_running():
            self._control.access = self.control_access()
            C.write_control_file(self.control_file_path(), self._control.port, self._control.token, self._control.access)

    # ---- requests: queued from server threads, answered on the Tk thread -------------
    def _control_handler(self, method, params):
        reply = queue.Queue()
        reply.cancelled = False                  # set when the caller gave up: a late approval must not apply the edit
        self._control_inbox.put((method, params, reply))
        wait = EDIT_WAIT if method in C.EDIT_METHODS else READ_WAIT
        try:
            answer = reply.get(timeout=wait)
        except queue.Empty:
            reply.cancelled = True
            raise C.ControlError("busy", "Blockliner did not answer in time")
        if isinstance(answer, ext_runner.ExtensionError):
            raise C.ControlError(answer.code, answer.message)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def _control_pump(self):
        try:
            while True:
                method, params, reply = self._control_inbox.get_nowait()
                if getattr(reply, "cancelled", False):
                    continue                     # the caller already got "busy"; doing it now would double up on a retry
                self._edit_reply = reply
                try:
                    reply.put(self._control_handle(method, params))
                except Exception as e:
                    reply.put(C.ControlError("failed", f"Blockliner could not do that ({e})"))
                finally:
                    self._edit_reply = None
        except queue.Empty:
            pass
        self.after(PUMP_MS, self._control_pump)

    def _control_handle(self, method, params):
        if method == "read_project":
            return self._project_snapshot()
        if method == "list_blocks":
            return {"available_blocks": self._available_blocks()}
        if method == "edit_project":
            return self._apply_project_edits("An AI tool", params.get("edits"),
                                             confirm=bool(self.settings.get("control_confirm", True)))
        if method == "undo":
            return {"ok": bool(self.undo_project())}
        raise C.ControlError("unknown_method", f"unknown method {method!r}")

    # ---- the dialog ----------------------------------------------------------------------
    def show_control_dialog(self):
        existing = getattr(self, "_control_win", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return existing
        win = tk.Toplevel(self)
        self._control_win = win
        win.title("AI tools connection")
        win.configure(bg=DARK_PANEL)
        win.geometry("640x600")
        win.minsize(520, 480)
        win.transient(self)

        def label(text, **kw):
            return tk.Label(win, text=text, bg=DARK_PANEL, fg=kw.pop("fg", DARK_FG), anchor="w", justify=tk.LEFT,
                            font=kw.pop("font", ("Segoe UI", 9)), wraplength=590, **kw)

        def button(parent, text, command, **kw):
            return tk.Button(parent, text=text, command=command, bg=kw.pop("bg", DARK_BG), fg=kw.pop("fg", DARK_FG),
                             relief=tk.FLAT, cursor="hand2", activebackground=DARK_BORDER, activeforeground=DARK_FG,
                             font=("Segoe UI", 9), padx=10, pady=3)

        label("AI tools connection", font=("Segoe UI", 12, "bold")).pack(fill=tk.X, padx=16, pady=(14, 2))
        label("Lets an AI agent (Claude Code or another MCP client) work on the project open in Blockliner. "
              "It only listens on this computer, needs a secret token, and is switched off every time Blockliner starts.",
              fg="#888888").pack(fill=tk.X, padx=16)
        status = label("", font=("Segoe UI", 10, "bold"))
        status.pack(fill=tk.X, padx=16, pady=(12, 4))
        toggle = button(win, "", lambda: flip())
        toggle.pack(anchor="w", padx=16)

        label("What it may do", font=("Segoe UI", 9, "bold")).pack(fill=tk.X, padx=16, pady=(14, 2))
        access_var = tk.StringVar(value=self.control_access())
        for value, text in (("read", "Read only: it can look at the project"), ("edit", "Read and edit: it can also change it (every change is one undo step)")):
            tk.Radiobutton(win, text=text, value=value, variable=access_var, command=lambda: self.set_control_access(access_var.get()),
                           bg=DARK_PANEL, fg=DARK_FG, selectcolor=DARK_BG, activebackground=DARK_PANEL, activeforeground=DARK_FG,
                           anchor="w", font=("Segoe UI", 9)).pack(fill=tk.X, padx=28)
        confirm_var = tk.BooleanVar(value=bool(self.settings.get("control_confirm", True)))

        def save_confirm():
            self.settings["control_confirm"] = bool(confirm_var.get())
            self.save_app_settings()
        tk.Checkbutton(win, text="Ask me before each change (recommended)", variable=confirm_var, command=save_confirm,
                       bg=DARK_PANEL, fg=DARK_FG, selectcolor=DARK_BG, activebackground=DARK_PANEL, activeforeground=DARK_FG,
                       anchor="w", font=("Segoe UI", 9)).pack(fill=tk.X, padx=28, pady=(4, 0))

        bridge = os.path.join(get_bundle_path(), "blockliner_mcp.py")
        python = "python3" if getattr(sys, "frozen", False) else sys.executable
        link = self.control_file_path()
        command = f'claude mcp add blockliner -e BLOCKLINER_CONTROL="{link}" -- {python} "{bridge}"'
        config = json.dumps({"mcpServers": {"blockliner": {"command": python, "args": [bridge],
                                                           "env": {"BLOCKLINER_CONTROL": link}}}}, indent=2)
        label("Connect an agent", font=("Segoe UI", 9, "bold")).pack(fill=tk.X, padx=16, pady=(14, 2))
        label("Add the bridge to the agent's MCP settings once, switch this on, then tell the agent to use Blockliner.",
              fg="#888888").pack(fill=tk.X, padx=16)
        box = tk.Text(win, height=6, bg=DARK_BG, fg="#9cdcfe", relief=tk.FLAT, font=("Consolas", 8), wrap=tk.WORD, padx=8, pady=6)
        box.insert("1.0", "Claude Code:\n" + command + "\n\nOther MCP clients:\n" + config)
        box.configure(state=tk.DISABLED)
        box.pack(fill=tk.X, padx=16, pady=4)
        row = tk.Frame(win, bg=DARK_PANEL)
        row.pack(fill=tk.X, padx=16)

        def copy(text):
            self.clipboard_clear()
            self.clipboard_append(text)
        button(row, "Copy the Claude Code command", lambda: copy(command)).pack(side=tk.LEFT, padx=(0, 6))
        button(row, "Copy the JSON config", lambda: copy(config)).pack(side=tk.LEFT)

        label("Recent activity", font=("Segoe UI", 9, "bold")).pack(fill=tk.X, padx=16, pady=(14, 2))
        activity = tk.Listbox(win, bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT, highlightthickness=0, font=("Consolas", 8), height=6,
                              activestyle="none")
        activity.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 14))

        def refresh():
            if not win.winfo_exists():
                return
            on = self.control_running()
            status.configure(text=f"● On: listening on 127.0.0.1:{self._control.port}" if on else "○ Off",
                             fg="#4caf50" if on else "#888888")
            toggle.configure(text="Switch off" if on else "Switch on")
            activity.delete(0, tk.END)
            for stamp, method, outcome in reversed(list(self._control.log)[-30:] if on else []):
                activity.insert(tk.END, f"{time.strftime('%H:%M:%S', time.localtime(stamp))}  {method:<14} {outcome}")
            win.after(1000, refresh)

        def flip():
            if self.control_running():
                self.stop_control()
            else:
                if self.control_access() == "edit" and not self.settings.get("control_confirm", True) and not messagebox.askyesno(
                        "Switch on", "Editing is allowed and approvals are off: a connected agent can change the project without asking "
                                     "(you can still undo). Switch on?", parent=win):
                    return
                self.start_control()
            refresh_now()

        def refresh_now():
            on = self.control_running()
            status.configure(text=f"● On: listening on 127.0.0.1:{self._control.port}" if on else "○ Off",
                             fg="#4caf50" if on else "#888888")
            toggle.configure(text="Switch off" if on else "Switch on")
        refresh_now()
        refresh()
        win.bind("<Escape>", lambda _e: win.destroy())
        return win
