"""The "Run in Blockliner" window: the program runs in its own process (program_runner.py),
its output streams in as it is printed, a line box answers input(), and Stop ends it."""
import os
import tkinter as tk
from tkinter import messagebox

import program_runner
from ui_common import DARK_ACCENT, DARK_BG, DARK_FG, DARK_PANEL

TICK_MS = 40
CHARS_PER_TICK = 20000                  # a flood of output is drawn in slices so the window stays usable
KEEP_CHARS = 400000                     # the oldest output is dropped beyond this


class RunView:
    """One output window and the run behind it."""

    def __init__(self, app, get_code, python_command, cwd=None):
        self.app = app
        self.get_code = get_code
        self.python_command = python_command
        self.cwd = cwd
        self.run = None
        self.status_text = ""
        self.job = None
        self.win = tk.Toplevel(app)
        self.win.title("Program Output")
        self.win.geometry("760x540")
        self.win.configure(bg=DARK_BG)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda _e: self.stop())

        header = tk.Frame(self.win, bg=DARK_ACCENT, height=40)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="▶ Program Output", bg=DARK_ACCENT, fg="white", font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT, padx=15)
        self.status = tk.Label(header, text="", bg=DARK_ACCENT, fg="white", font=("Segoe UI", 10))
        self.status.pack(side=tk.LEFT, padx=8)
        self.again_btn = self._button(header, "↻ Run again", self.again)
        self.again_btn.pack(side=tk.RIGHT, padx=(0, 10), pady=6)
        self.stop_btn = self._button(header, "■ Stop", self.stop, bg="#c0392b")
        self.stop_btn.pack(side=tk.RIGHT, padx=6, pady=6)

        bottom = tk.Frame(self.win, bg=DARK_PANEL)
        bottom.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Label(bottom, text="Answer for input():", bg=DARK_PANEL, fg="#888888", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(10, 6), pady=6)
        self.entry = tk.Entry(bottom, bg=DARK_BG, fg=DARK_FG, insertbackground=DARK_FG, relief=tk.FLAT, font=("Consolas", 10))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=6)
        self.entry.bind("<Return>", lambda _e: self.send())
        self.send_btn = self._button(bottom, "Send", self.send)
        self.send_btn.pack(side=tk.LEFT, padx=10, pady=6)

        body = tk.Frame(self.win, bg=DARK_BG)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        bar = tk.Scrollbar(body)
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text = tk.Text(body, bg="#1e1e1e", fg="#00ff00", font=("Consolas", 10), padx=12, pady=12, wrap=tk.WORD,
                            yscrollcommand=bar.set, state=tk.DISABLED)
        self.text.pack(fill=tk.BOTH, expand=True)
        bar.config(command=self.text.yview)
        self.text.tag_config("err", foreground="#ff5555")
        self.text.tag_config("typed", foreground="#9cdcfe")
        self.text.tag_config("note", foreground="#888888")
        self.begin()

    def _button(self, parent, label, command, bg=DARK_BG):
        return tk.Button(parent, text=label, command=command, bg=bg, fg="white", relief=tk.FLAT, cursor="hand2",
                         activebackground="#555555", activeforeground="white", font=("Segoe UI", 9), padx=10, pady=2)

    # ---- the run -----------------------------------------------------------------------
    def begin(self):
        code = self.get_code()
        self._clear()
        self.got_output = False
        if not code:
            self._add("Nothing to run: generate some code first.\n", "note")
            self._state(False, "")
            return
        self.run = program_runner.ProgramRun(code, self.python_command, cwd=self.cwd)
        try:
            self.run.start()
        except program_runner.RunnerError as e:
            self.run = None
            self._add(f"❌ {e}\n", "err")
            self._state(False, "Could not start")
            return
        self._state(True, "Running…")
        self.entry.focus_set()
        self.job = self.win.after(TICK_MS, self.tick)

    def again(self):
        if self.run is None or not self.run.running:
            self.begin()

    def stop(self):
        if self.run is not None and self.run.running:
            self.run.stop()
            self.status.config(text="Stopping…")

    def send(self):
        if self.run is None or not self.run.running:
            return
        line = self.entry.get()
        if self.run.send_line(line):
            self._add(line + "\n", "typed")
            self.entry.delete(0, tk.END)

    def close(self):
        if self.job is not None:
            try:
                self.win.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        if self.run is not None:
            self.run.stop(force=True)
            self.run.cleanup()
            self.run = None
        self.win.destroy()

    # ---- drawing -----------------------------------------------------------------------
    def tick(self):
        self.job = None
        if self.run is None or not self.win.winfo_exists():
            return
        budget, ended = CHARS_PER_TICK, None
        while budget > 0:
            try:
                kind, payload = self.run.events.get_nowait()
            except Exception:
                break
            if kind == "end":
                ended = payload
                break
            self._add(payload, "err" if kind == "err" else "")
            self.got_output = True
            budget -= len(payload)
        if ended is not None:
            self.finish(ended)
            return
        self.job = self.win.after(TICK_MS, self.tick)

    def finish(self, code):
        run = self.run
        if run.stopped:
            self._add("\n■ Stopped.\n", "note")
            label = "Stopped"
        elif code == 0:
            self._add(("\n" if self.got_output else "") + ("✓ Finished.\n" if self.got_output else "✓ Program ran (no output).\n"), "note")
            label = "Finished"
        else:
            self._add(f"\n❌ The program stopped with an error (exit code {code}).\n", "err")
            label = f"Exit code {code}"
        run.cleanup()
        self.run = None
        self._state(False, label)

    def _state(self, running, label):
        self.status_text = label
        self.status.config(text=label)
        self.stop_btn.config(state=tk.NORMAL if running else tk.DISABLED)
        self.again_btn.config(state=tk.DISABLED if running else tk.NORMAL)
        self.send_btn.config(state=tk.NORMAL if running else tk.DISABLED)
        self.entry.config(state=tk.NORMAL if running else tk.DISABLED)

    def _clear(self):
        self.text.config(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.config(state=tk.DISABLED)

    def _add(self, chunk, tag=""):
        at_end = self.text.yview()[1] >= 0.999
        self.text.config(state=tk.NORMAL)
        self.text.insert(tk.END, chunk, tag or ())
        extra = int(self.text.count("1.0", tk.END, "chars")[0]) - KEEP_CHARS
        if extra > 0:
            self.text.delete("1.0", f"1.0 + {extra} chars")
        self.text.config(state=tk.DISABLED)
        if at_end:
            self.text.see(tk.END)

    def contents(self):
        return self.text.get("1.0", tk.END)


class RunWindowMixin:

    def run_code(self):
        """Run the generated Python in its own process, in a window with Stop."""
        code = self.get_clean_code()
        if not code or code.startswith("# No code"):
            messagebox.showwarning("No Code", "Generate some code first!")
            return None
        if self.lang_var.get() != "python":
            messagebox.showinfo("Python Only", "Blockliner can only run Python code directly.\n\nFor other languages:\n"
                                "• Use '\U0001f5a5️ Run in Terminal'\n• Or '\U0001f4dd Open in VS Code'")
            return None

        def fresh():
            code_now = self.get_clean_code()
            return code_now if code_now and not code_now.startswith("# No code") else ""

        folder = None
        try:
            path = self.workspaces[self.active_ws_index].get("filepath")
            folder = os.path.dirname(path) if path else None
        except (AttributeError, IndexError, KeyError, TypeError):
            folder = None
        view = RunView(self, fresh, self.settings.get("python_command", "python3"), cwd=folder)
        self.__dict__.setdefault("_run_views", []).append(view)
        return view
