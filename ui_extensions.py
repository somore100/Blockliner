"""Extensions in the app: the icon strip and "..." menu, side panels, and the
manager window (Tools > Extensions...). The rules are pure (extensions.py,
extensions_builtin.py); this file only shows them. See docs/design-extensions.md.

First slice: the two extensions that ship with Blockliner. Outside extensions are
read and listed, with their compatibility, but not started yet (the process
runner comes next), so the manager marks them "not started yet".
"""
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox

import extensions as X
import extensions_api
import project_undo
import ext_runner
import ext_storage
import extensions_builtin as B
from panels import PanelSpec
from ui_common import get_block_attr
from ui_common import APP_SETTINGS_PATH, DARK_ACCENT, DARK_BG, DARK_BORDER, DARK_FG, DARK_HOVER, DARK_PANEL, get_bundle_path

OK_COLOR, WARN_COLOR, BAD_COLOR = "#4caf50", "#e5a50a", "#d9534f"
PUMP_MS = 200                   # how often messages from extension programs are taken in
REFRESH_EVERY = 8               # pump ticks between panel refreshes / restart checks


class ExtensionsMixin:

    def extension_roots(self):
        return [(os.path.join(get_bundle_path(), "extensions", "builtin"), "built-in"),
                (os.path.join(os.path.dirname(APP_SETTINGS_PATH), "extensions"), "user")]

    def install_extensions(self):
        self._ext_all = X.find_extensions(self.extension_roots())
        self._ext_panels = {}           # panel id -> {"ext", "body", "shown": json text}
        self._ext_storage = ext_storage.ExtStorage(os.path.join(os.path.dirname(APP_SETTINGS_PATH), "extension_data"))
        self._ext_values = {}           # extension id -> {input id: text typed so far}
        self._ext_remote = {}           # extension id -> the panel description it last sent
        self._ext_inbox = queue.Queue()  # messages from extension threads, handled on the Tk thread
        self._ext_starting = set()
        self._ext_ticks = 0
        self._ext_host = ext_runner.Host(self._ext_handler)
        self.protocol("WM_DELETE_WINDOW", self._ext_close)
        self.refresh_extensions()
        self.after(PUMP_MS, self._ext_pump)

    def _ext_close(self):
        unsaved = self.unsaved_workspace_titles()
        if unsaved and not messagebox.askyesno(
                "Unsaved changes",
                "These projects have changes that are not saved:\n\n  " + "\n  ".join(unsaved[:8])
                + ("\n  \u2026" if len(unsaved) > 8 else "") + "\n\nClose Blockliner anyway?"):
            return
        try:
            if hasattr(self, "stop_control"):
                self.stop_control()
            self._ext_host.stop_all()
        finally:
            self.destroy()

    def _ext_runnable(self, ext):
        """Shipped extensions run in-process; outside ones run as their own program."""
        m = ext["manifest"]
        return m is not None and (bool(m["builtin"]) or bool(m["run"]))

    def _ext_by_id(self, ext_id):
        return next((e for e in self._ext_all if e["manifest"] and e["manifest"]["id"] == ext_id), None)

    def _ext_handler(self, ext_id, method, params, is_event):
        """Called on an extension's reader thread: only queue, never touch Tk here."""
        if is_event:
            return None
        if method in ("panel.set", "notify"):
            self._ext_inbox.put((ext_id, method, params, None))
            return {"ok": True}
        if method in ("project.read", "project.edit"):
            reply = queue.Queue()
            reply.cancelled = False
            self._ext_inbox.put((ext_id, method, params, reply))        # answered on the Tk thread
            try:
                answer = reply.get(timeout=5)
            except queue.Empty:
                reply.cancelled = True
                raise ext_runner.ExtensionError("busy", "Blockliner did not answer in time; try again")
            if isinstance(answer, Exception):
                raise answer
            return answer
        if method in ("settings.get", "settings.set", "secrets.get", "secrets.set"):
            return self._ext_storage_call(ext_id, method, params)
        raise ext_runner.ExtensionError("not_available", f"{method} is not available yet")

    def _ext_storage_call(self, ext_id, method, params):
        """Settings and secrets of one extension (file work only: fine off the Tk thread)."""
        store = self._ext_storage
        try:
            if method == "settings.get":
                return {"value": store.get_settings(ext_id, params.get("key"))}
            if method == "settings.set":
                store.set_setting(ext_id, params.get("key"), params.get("value"))
            elif method == "secrets.get":
                return {"value": store.get_secret(ext_id, params.get("name"))}
            else:
                store.set_secret(ext_id, params.get("name"), params.get("value"))
            return {"ok": True}
        except ext_storage.StorageError as e:
            raise ext_runner.ExtensionError("invalid", str(e))

    def refresh_extensions(self):
        active = [e for e in X.active(self._ext_all, self.settings) if self._ext_runnable(e)]
        self._ext_layout = X.layout(active)
        live = {f"ext:{e['manifest']['id']}" for e in active}
        for pid in list(self._ext_panels):
            if pid not in live and pid in self.panels.ids():
                self.panels.hide(pid)
        wanted = {e["manifest"]["id"]: e for e in active if e["manifest"]["run"]}
        for ext_id in list(self._ext_host.procs):
            if ext_id not in wanted:
                threading.Thread(target=self._ext_host.stop, args=(ext_id,), daemon=True).start()
        for ext_id, ext in wanted.items():
            if ext_id not in self._ext_host.procs and ext_id not in self._ext_starting:
                self._ext_starting.add(ext_id)
                m = ext["manifest"]
                threading.Thread(target=self._ext_start, args=(ext_id, ext["folder"], m["run"], m["permissions"]),
                                 daemon=True).start()
        self.draw_extension_bar()

    def _ext_start(self, ext_id, folder, command, permissions):
        try:
            self._ext_host.start(ext_id, folder, command, permissions)
        finally:
            self._ext_starting.discard(ext_id)

    # ---- icon strip and "..." menu ---------------------------------------------
    def draw_extension_bar(self):
        bar = self.plugin_bar
        for w in bar.winfo_children():
            w.destroy()
        lay = self._ext_layout

        def flat(text, font):
            return tk.Button(bar, text=text, bg=DARK_PANEL, fg=DARK_FG, activebackground=DARK_HOVER,
                             activeforeground=DARK_FG, relief=tk.FLAT, bd=0, padx=8, pady=4, font=font,
                             cursor="hand2", highlightthickness=0)
        for ext in lay["pinned"]:
            m = ext["manifest"]
            shown = f"ext:{m['id']}" in self.panels.ids() and self.panels.is_visible(f"ext:{m['id']}")
            b = flat(f"{m['icon']} {m['panel']['title']}", ("Segoe UI", 9))
            if shown:
                b.configure(bg=DARK_ACCENT)
            b.configure(command=lambda e=ext: self.toggle_extension_panel(e))
            b.pack(side=tk.LEFT)
        more = tk.Menubutton(bar, text="⋯", bg=DARK_PANEL, fg=DARK_FG, activebackground=DARK_HOVER,
                             activeforeground=DARK_FG, relief=tk.FLAT, bd=0, padx=8, pady=4,
                             font=("Segoe UI", 12, "bold"), cursor="hand2", highlightthickness=0)
        menu = self._new_menu(more)
        for ext in lay["overflow_panels"]:
            m = ext["manifest"]
            menu.add_command(label=f"{m['icon']}  {m['panel']['title']}", command=lambda e=ext: self.toggle_extension_panel(e))
        for ext, command in lay["commands"]:
            menu.add_command(label=command["label"], command=lambda e=ext, c=command["command"]: self.extension_command(e, c))
        if menu.index("end") is not None:
            menu.add_separator()
        menu.add_command(label="Manage extensions...", command=self.show_extension_manager)
        more.configure(menu=menu)
        more.pack(side=tk.LEFT)
        self.sync_extension_commands()

    # ---- panels -----------------------------------------------------------------
    def toggle_extension_panel(self, ext):
        m = ext["manifest"]
        pid = f"ext:{m['id']}"
        if pid in self.panels.ids():
            if self.panels.is_visible(pid):
                self.panels.hide(pid)
            else:
                self.panels.show(pid)
                self.render_extension_panel(pid)
        else:
            frame = self.panels.create_panel(
                PanelSpec(pid, m["panel"]["title"], dock=m["panel"]["dock"], width=m["panel"]["width"], min_width=160),
                bg=DARK_PANEL)
            head = tk.Frame(frame, bg=DARK_PANEL)
            head.pack(fill=tk.X, padx=10, pady=(10, 4))
            tk.Label(head, text=f"{m['icon']}  {m['panel']['title']}", bg=DARK_PANEL, fg=DARK_FG,
                     font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
            tk.Button(head, text="✕", command=lambda: (self.panels.hide(pid), self.draw_extension_bar()),
                      bg=DARK_PANEL, fg=DARK_FG, relief=tk.FLAT, bd=0, cursor="hand2",
                      activebackground=DARK_HOVER, activeforeground=DARK_FG).pack(side=tk.RIGHT)
            body = tk.Frame(frame, bg=DARK_PANEL)
            body.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
            self._ext_panels[pid] = {"ext": ext, "body": body, "shown": ""}
            self.render_extension_panel(pid)
        self.draw_extension_bar()

    def _panel_description(self, ext):
        build = B.PANELS.get(ext["manifest"]["builtin"])
        if build:
            return build(self.tabs)
        waiting = {"type": "label", "text": "Waiting for the extension...", "style": "muted"}
        return self._ext_remote.get(ext["manifest"]["id"], waiting)

    def render_extension_panel(self, pid):
        info = self._ext_panels.get(pid)
        if info is None:
            return
        desc = self._panel_description(info["ext"])
        text = json.dumps(desc, sort_keys=True)
        if text == info["shown"]:
            return                                   # nothing changed: no flicker
        info["shown"] = text
        for w in info["body"].winfo_children():
            w.destroy()
        if desc:
            self._draw_description(info["body"], desc, info["ext"])

    def _ext_handle_message(self, ext_id, method, params, reply):
        ext = self._ext_by_id(ext_id)
        if ext is None:
            if reply is not None:
                reply.put(ext_runner.ExtensionError("gone", "extension not found"))
            return
        if method == "project.read":
            reply.put(self._project_snapshot())
        elif method == "project.edit":
            reply.put(self._ext_apply_edits(ext, params))
        elif method == "notify" and isinstance(params.get("text"), str):
            self.maybe_notify(ext["manifest"]["name"], params["text"][:500])
        elif method == "panel.set" and isinstance(params.get("description"), dict):
            self._ext_remote[ext_id] = params["description"]
            pid = f"ext:{ext_id}"
            if pid in self._ext_panels:
                self.render_extension_panel(pid)

    def _ext_pump(self):
        """Every PUMP_MS: take in what extension programs sent; now and then
        redraw panels and restart what died. Nothing here may raise: this loop
        must keep running."""
        try:
            while True:
                item = self._ext_inbox.get_nowait()
                if item[3] is not None and getattr(item[3], "cancelled", False):
                    continue                                # the extension was told "busy"; do not do it behind its back
                self._edit_reply = item[3]
                try:
                    self._ext_handle_message(*item)
                except Exception as e:                      # a bug here must not stop the loop or leave a caller waiting
                    if item[3] is not None:
                        item[3].put(ext_runner.ExtensionError("failed", f"Blockliner could not do that ({e})"))
                finally:
                    self._edit_reply = None
        except queue.Empty:
            pass
        self._ext_ticks += 1
        if self._ext_ticks % REFRESH_EVERY == 0:
            try:
                for pid in list(self._ext_panels):
                    if pid in self.panels.ids() and self.panels.is_visible(pid):
                        self.render_extension_panel(pid)
                for ext_id, note in self._ext_host.check():
                    self._ext_remote.pop(ext_id, None)
                self._announce_project_changes()
            except Exception as e:                          # keep the loop alive; show nothing noisy
                print(f"extensions: {e}")
        self.after(PUMP_MS, self._ext_pump)

    def _draw_description(self, parent, node, ext):
        """Draw a widget description (see extensions_builtin.py). Unknown types are skipped."""
        kind = node.get("type") if isinstance(node, dict) else None
        if kind in ("column", "row"):
            frame = tk.Frame(parent, bg=DARK_PANEL)
            frame.pack(fill=tk.X, pady=2)
            for i, child in enumerate(node.get("children") or []):
                if kind == "row":
                    holder = tk.Frame(frame, bg=DARK_PANEL)
                    holder.pack(side=tk.LEFT if i == 0 else tk.RIGHT)
                    self._draw_description(holder, child, ext)
                else:
                    self._draw_description(frame, child, ext)
        elif kind == "label":
            style = node.get("style")
            tk.Label(parent, text=str(node.get("text", "")), bg=DARK_PANEL, anchor="w", justify=tk.LEFT,
                     fg="#888888" if style == "muted" else DARK_FG,
                     font=("Segoe UI", 10, "bold") if style == "title" else ("Segoe UI", 9)).pack(fill=tk.X)
        elif kind == "text":
            box = tk.Text(parent, height=int(node.get("height", 12)) if str(node.get("height", 12)).isdigit() else 12,
                          bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT, wrap=tk.WORD, font=("Segoe UI", 9), padx=6, pady=6)
            box.insert("1.0", str(node.get("text", "")))
            if node.get("follow"):
                box.see(tk.END)
            box.configure(state=tk.DISABLED)
            box.pack(fill=tk.X, pady=2)
        elif kind == "input":
            self._draw_input(parent, node, ext)
        elif kind == "button":
            tk.Button(parent, text=str(node.get("text", "")), command=lambda c=node.get("command"): self.extension_command(ext, c),
                      bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT, cursor="hand2", activebackground=DARK_BORDER,
                      activeforeground=DARK_FG, font=("Segoe UI", 9), padx=8).pack(anchor="w", pady=4)

    def _available_blocks(self):
        """{language: {block id: {"name", "params"}}} for the language that is open."""
        return {self.current_language: {
            bid: {"name": str(get_block_attr(mod, "display_name", bid)),
                  "params": {p["name"]: p.get("default", "") for p in get_block_attr(mod, "params", [])}}
            for bid, mod in self.blocks.items()}}

    def _project_snapshot(self):
        self.sync_active_tab_state()
        return extensions_api.snapshot(self.tabs, self.active_tab_index, self._available_blocks())

    def _ext_apply_edits(self, ext, params):
        """project.edit from an extension: all or nothing, one undoable step."""
        return self._apply_project_edits(ext["manifest"]["name"], params.get("edits"))

    def _apply_project_edits(self, source, edits, confirm=False):
        """Check the edits on a copy, (optionally ask), then swap them in as one undoable
        step. Returns {"ok", "summary"} or an ExtensionError to hand back. Shared by
        extensions and by outside AI tools. Runs on the Tk thread."""
        self.sync_active_tab_state()
        ws = self.workspaces[self.active_ws_index]
        known = {lang: {bid: info["params"] for bid, info in blocks.items()}
                 for lang, blocks in self._available_blocks().items()}

        def code_to_blocks(language, text):
            with self._language_scope(language):
                return self.import_code_to_blocks(text)[0]
        try:
            new_files, summary = extensions_api.apply_edits(ws["files"], edits, known, code_to_blocks)
        except extensions_api.EditError as e:
            return ext_runner.ExtensionError("invalid", str(e))
        def gone():
            reply = self.__dict__.get("_edit_reply")
            return reply is not None and getattr(reply, "cancelled", False)
        if confirm:
            shown = "\n".join(f"  \u2022 {line}" for line in summary[:10]) + (f"\n  ... and {len(summary) - 10} more" if len(summary) > 10 else "")
            if not messagebox.askyesno("Allow this change?", f"{source} wants to change your project:\n\n{shown}\n\n"
                                       "You can undo it afterwards (File > Undo)."):
                return ext_runner.ExtensionError("declined", "the user declined the change")
        if gone():
            return ext_runner.ExtensionError("busy", "the request timed out before it was approved, so nothing was changed")
        self.record_project_undo(f"{source}: {summary[0]}" + (f" (+{len(summary) - 1} more)" if len(summary) > 1 else ""))
        ws["active_index"] = project_undo.restore_files(ws["files"], {"files": new_files, "active_index": ws["active_index"]})
        self._show_active_file(self.view_mode)
        self.mark_active_tab_dirty()
        self.refresh_workspace()
        self.update_generated_code()
        self.show_change_bar(f"{source} changed the project: " + "; ".join(summary[:2]) + ("..." if len(summary) > 2 else ""))
        return {"ok": True, "summary": summary}

    def _announce_project_changes(self):
        """Tell extensions that may read the project when it changed (checked
        every few ticks, so it is at most a couple of events per second)."""
        readers = [i for i, pr in self._ext_host.procs.items() if pr.state == "running" and "project.read" in pr.permissions]
        if not readers:
            self._ext_last_print = None
            return
        print_now = extensions_api.fingerprint(self._project_snapshot())
        if print_now != getattr(self, "_ext_last_print", None):
            first = getattr(self, "_ext_last_print", None) is None
            self._ext_last_print = print_now
            if not first:
                for ext_id in readers:
                    self._ext_host.send_event(ext_id, "project.changed", {})

    def _draw_input(self, parent, node, ext):
        """A one-line input with a button; what is typed survives a redraw of the panel."""
        key = str(node.get("id", "input"))
        values = self._ext_values.setdefault(ext["manifest"]["id"], {})
        row = tk.Frame(parent, bg=DARK_PANEL)
        row.pack(fill=tk.X, pady=2)
        if node.get("label"):
            tk.Label(row, text=str(node["label"]), bg=DARK_PANEL, fg="#888888", font=("Segoe UI", 8), anchor="w").pack(fill=tk.X)
        line = tk.Frame(row, bg=DARK_PANEL)
        line.pack(fill=tk.X)
        entry = tk.Entry(line, bg=DARK_BG, fg=DARK_FG, insertbackground=DARK_FG, relief=tk.FLAT,
                         show="\u2022" if node.get("secret") else "", highlightthickness=1,
                         highlightbackground=DARK_BORDER, highlightcolor=DARK_ACCENT)
        entry.insert(0, values.get(key, str(node.get("value", ""))))
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
        entry.bind("<KeyRelease>", lambda _e: values.__setitem__(key, entry.get()))

        def submit(_e=None):
            text = entry.get()
            if not node.get("keep"):
                entry.delete(0, tk.END)
                values[key] = ""
            self.extension_command(ext, node.get("command"), {"value": text, "id": key})
        entry.bind("<Return>", submit)
        tk.Button(line, text=str(node.get("button", "Send")), command=submit, bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT,
                  cursor="hand2", activebackground=DARK_BORDER, activeforeground=DARK_FG, font=("Segoe UI", 9),
                  padx=8).pack(side=tk.LEFT, padx=(4, 0))

    # ---- commands -----------------------------------------------------------------
    def extension_command(self, ext, command, extra=None):
        """A button, input or menu entry of an extension was used."""
        if command == "refresh":
            for pid, info in self._ext_panels.items():
                if info["ext"] is ext:
                    info["shown"] = ""
                    self.render_extension_panel(pid)
            return
        if not ext["manifest"]["builtin"]:
            self._ext_host.send_event(ext["manifest"]["id"], "command", {"command": command, **(extra or {})})
            return
        tab = self.tabs[self.active_tab_index]
        result = B.run_command(ext["manifest"]["builtin"], command, {"code": self.generate_code_for_tab(tab)})
        if result.get("clipboard") is not None:
            self.clipboard_clear()
            self.clipboard_append(result["clipboard"])
        if result.get("notify"):
            self.maybe_notify(ext["manifest"]["name"], result["notify"])

    # ---- manager window --------------------------------------------------------------
    def show_extension_manager(self):
        existing = getattr(self, "_ext_win", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return existing
        win = tk.Toplevel(self)
        self._ext_win = win
        win.title("Extensions")
        win.configure(bg=DARK_PANEL)
        win.geometry("760x520")
        win.minsize(600, 400)
        win.transient(self)

        def label(parent, text, **kw):
            return tk.Label(parent, text=text, bg=DARK_PANEL, fg=kw.pop("fg", DARK_FG), anchor="w",
                            font=kw.pop("font", ("Segoe UI", 9)), **kw)

        label(win, "Extensions", font=("Segoe UI", 12, "bold")).pack(fill=tk.X, padx=14, pady=(12, 0))
        safe = X.safe_start(self.settings)
        label(win, "Safe start is on: every extension is off until you turn it off in Settings or unset BLOCKLINER_SAFE."
              if safe else "Only install extensions you trust: they run as programs on your computer.",
              fg=WARN_COLOR if safe else "#888888", wraplength=700, justify=tk.LEFT).pack(fill=tk.X, padx=14, pady=(0, 8))
        tk.Button(win, text="Depot...", command=self.show_depot, bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT, cursor="hand2",
                  activebackground=DARK_BORDER, activeforeground=DARK_FG, font=("Segoe UI", 9), padx=8).place(relx=1.0, x=-14, y=12, anchor="ne")
        body = tk.Frame(win, bg=DARK_PANEL)
        body.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 12))
        left = tk.Frame(body, bg=DARK_BG, width=260)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)
        right = tk.Frame(body, bg=DARK_PANEL)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        user_root = self.extension_roots()[1][0]

        def add_remove(ext):
            """A Remove button for extensions the user installed (shipped ones can only be turned off)."""
            if X.can_remove(ext, user_root):
                tk.Button(right, text="Remove extension...", command=lambda e=ext: remove(e), bg=DARK_BG, fg=BAD_COLOR,
                          relief=tk.FLAT, cursor="hand2", activebackground=DARK_BORDER, activeforeground=BAD_COLOR,
                          font=("Segoe UI", 9), padx=8).pack(anchor="w", pady=(10, 0))
            else:
                label(right, "Shipped with Blockliner: it can be turned off but not removed.", fg="#666666").pack(fill=tk.X, pady=(10, 0))

        def remove(ext):
            m = ext["manifest"]
            name = m["name"] if m else os.path.basename(ext["folder"])
            if not messagebox.askyesno("Remove extension", f"Delete \"{name}\" and its files?\n\n{ext['folder']}\n\nThis cannot be undone.", parent=win):
                return
            also = bool(m) and bool(self._ext_storage.get_settings(m["id"]) or self._ext_storage.secret_names(m["id"])) and messagebox.askyesno(
                "Remove extension", "Also delete its saved settings and API keys?", parent=win)
            if m:
                self._ext_host.stop(m["id"])
            if not X.remove_extension(ext, user_root):
                messagebox.showwarning("Remove extension", "The folder could not be deleted.", parent=win)
                return
            if m:
                X.forget_settings(self.settings, m["id"])
                self.save_app_settings()
                self._ext_remote.pop(m["id"], None)
                if also:
                    self._ext_storage.delete_all(m["id"])
            self._ext_all = X.find_extensions(self.extension_roots())
            self.refresh_extensions()
            win.destroy()
            self.show_extension_manager()

        def show_detail(ext):
            for w in right.winfo_children():
                w.destroy()
            m = ext["manifest"]
            if m is None:
                label(right, "This extension can't be used", font=("Segoe UI", 10, "bold"), fg=BAD_COLOR).pack(fill=tk.X)
                label(right, os.path.basename(ext["folder"]), fg="#888888").pack(fill=tk.X)
                for note in ext["notes"]:
                    label(right, note, fg=BAD_COLOR, wraplength=420, justify=tk.LEFT).pack(fill=tk.X, pady=2)
                add_remove(ext)
                return
            status, reason = X.compatibility(m)
            label(right, f"{m['icon']}  {m['name']}", font=("Segoe UI", 11, "bold")).pack(fill=tk.X)
            label(right, f"{m['id']}   version {m['extension_version']}   by {m['author'] or 'unknown'}", fg="#888888").pack(fill=tk.X)
            label(right, m["description"], wraplength=440, justify=tk.LEFT).pack(fill=tk.X, pady=(6, 6))
            label(right, X.STATUS_TEXT[status] + (f": {reason}" if reason else ""),
                  fg=OK_COLOR if status == "ok" else BAD_COLOR, wraplength=440, justify=tk.LEFT).pack(fill=tk.X)
            if m["run"]:
                st = self._ext_host.status(m["id"])
                text = {"running": "Running", "failed": "Failed", "starting": "Starting...", "stopped": "Not running"}[st["state"]]
                label(right, text + (f": {st['note']}" if st["note"] else ""),
                      fg=OK_COLOR if st["state"] == "running" else (BAD_COLOR if st["state"] == "failed" else "#888888"),
                      wraplength=440, justify=tk.LEFT).pack(fill=tk.X, pady=(4, 0))
                if st["log"]:
                    tk.Button(right, text="Show log", command=lambda l=st["log"]: messagebox.showinfo(m["name"], "\n".join(l[-30:]), parent=win),
                              bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 8)).pack(anchor="w", pady=2)
            label(right, "Permissions", font=("Segoe UI", 9, "bold")).pack(fill=tk.X, pady=(10, 2))
            for p in m["permissions"] or []:
                label(right, f"• {X.PERMISSIONS[p]}", fg="#bbbbbb", wraplength=440, justify=tk.LEFT).pack(fill=tk.X)
            if not m["permissions"]:
                label(right, "None", fg="#888888").pack(fill=tk.X)
            if m["panel"]:
                label(right, f"Panel: {m['panel']['title']} ({m['panel']['dock']}, {'pinned icon' if m['pin'] else 'in the ⋯ menu'})",
                      fg="#bbbbbb").pack(fill=tk.X, pady=(8, 0))
            for c in m["commands"]:
                label(right, f"Command: {c['label']} ({c['menu']})", fg="#bbbbbb").pack(fill=tk.X)
            for note in ext["notes"]:
                label(right, note, fg=WARN_COLOR, wraplength=440, justify=tk.LEFT).pack(fill=tk.X, pady=(6, 0))
            names = self._ext_storage.secret_names(m["id"])
            if names:
                label(right, "Saved secrets: " + ", ".join(names) + " (values are never shown)", fg="#bbbbbb",
                      wraplength=440, justify=tk.LEFT).pack(fill=tk.X, pady=(8, 0))
            label(right, f"{ext['scope']}  •  {ext['folder']}", fg="#666666", wraplength=440, justify=tk.LEFT).pack(fill=tk.X, pady=(10, 0))
            add_remove(ext)

        def toggle(ext, var):
            m = ext["manifest"]
            if var.get() and m["run"] and not messagebox.askyesno(
                    "Turn on extension",
                    f"\"{m['name']}\" runs as a program on your computer and asks for:\n\n" +
                    ("\n".join(f"  \u2022 {X.PERMISSIONS[p]}" for p in m["permissions"]) or "  (nothing)") +
                    "\n\nOnly turn it on if you trust where it came from.", parent=win):
                var.set(False)
                return
            X.set_enabled(self.settings, ext["manifest"]["id"], var.get())
            self.save_app_settings()
            self.refresh_extensions()

        if not self._ext_all:
            label(left, "No extensions found.", fg="#888888").pack(padx=8, pady=8)
        for ext in self._ext_all:
            row = tk.Frame(left, bg=DARK_BG)
            row.pack(fill=tk.X)
            m = ext["manifest"]
            if m is not None and X.compatibility(m)[0] == "ok":
                var = tk.BooleanVar(value=X.is_enabled(m, self.settings))
                tk.Checkbutton(row, variable=var, command=lambda e=ext, v=var: toggle(e, v), bg=DARK_BG,
                               activebackground=DARK_BG, selectcolor=DARK_PANEL).pack(side=tk.LEFT)
            else:
                tk.Label(row, text=" ⚠ ", bg=DARK_BG, fg=BAD_COLOR).pack(side=tk.LEFT)
            name = tk.Label(row, text=m["name"] if m else os.path.basename(ext["folder"]), bg=DARK_BG,
                            fg=DARK_FG if m and X.compatibility(m)[0] == "ok" else "#777777", anchor="w",
                            cursor="hand2", font=("Segoe UI", 9))
            name.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=4)
            name.bind("<Button-1>", lambda _e, x=ext: show_detail(x))
        if self._ext_all:
            show_detail(self._ext_all[0])
        win.bind("<Escape>", lambda _e: win.destroy())
        return win
