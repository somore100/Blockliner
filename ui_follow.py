"""File > Follow a folder: source-first mode, phases 1 and 2 (docs/source-first-mode.md).

The files in the folder are the truth. Every source file becomes a file tab with nodes made from its structure; a timer
looks at the folder every couple of seconds, and when an outside tool (an editor, an AI agent) adds or changes a file the
layers update by themselves, keeping the nodes where they were.

Phase 2 (opt-in when following): an edit made to a block is written back into the file a moment later, as a splice -
only the nodes that were really edited are replaced (see source_writeback), the rest of the file stays byte for byte,
and a file another program changed in the meantime is never overwritten without asking (phase 3: keep mine, take
theirs, or save mine as a copy). Without it the mode is read-only: nothing is
written, and edits stay in Blockliner until the file changes on disk."""
import os
import re
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import portable
import project_scan
import source_follow
import source_merge
import source_rename
import source_writeback
from nodes_model import normalize_orders
from ui_common import LANGUAGE_EXTENSIONS

FOLLOW_MS = 1500
NOTICE_SECONDS = 20
WRITE_DELAY_MS = 600          # default: an edit is written this long after the last change (typing makes many)
MAX_DELAY_S = 300


class FollowMixin:
    _follow = None             # {"folder", "snap": {rel: info}, "job"} while a folder is followed

    def follow_file(self, path=None, write=None):
        """File > Follow a File...: the same as following a folder, but only that one file is read and written
        (its folder is still where .blockliner/presence lives, so teammates following the file see each other)."""
        if path is None:
            path = filedialog.askopenfilename(
                title="Follow a file",
                filetypes=[("Source files", " ".join("*" + e for e in sorted(LANGUAGE_EXTENSIONS))), ("All files", "*")])
        if not path:
            return 0
        path = os.path.abspath(path)
        return self.follow_folder(os.path.dirname(path), write=write, only=os.path.basename(path))

    def _follow_snapshot(self, folder, only=None, previous=None):
        snap = source_follow.snapshot(folder, LANGUAGE_EXTENSIONS, previous=previous)
        if only:
            snap = {rel: v for rel, v in snap.items() if rel == only}
        return snap

    def follow_folder(self, folder=None, write=None, only=None):
        """Pick a folder and start following it. `write` True lets edits made here be written back into the files
        (only the nodes that were edited); False keeps it read-only; None asks. Returns how many files were opened
        (0 = nothing started)."""
        if self._follow is not None:
            self.stop_following()
        if folder is None:
            folder = filedialog.askdirectory(title="Follow a folder - pick the project's root folder")
        if not folder:
            return 0
        snap = self._follow_snapshot(folder, only)
        if not snap:
            messagebox.showinfo("Follow a folder", "Blockliner can't read that file." if only else
                                "There are no source files Blockliner can read in that folder.")
            return 0
        if write is None:
            write = messagebox.askyesno(
                "Write edits back to the files?",
                "Following a folder: the files on disk are the truth and Blockliner shows them as blocks.\n\n"
                "Yes - when you edit a block here, only the node you changed is rewritten in its file. Everything else "
                "in the file stays exactly as it was. (A file changed by another program in the meantime is never "
                "overwritten: you get that version.)\n\n"
                "No - read-only. Nothing is written to the folder; what you change here is replaced the next time the "
                "file changes on disk.")
        self._follow = {"folder": os.path.abspath(folder), "snap": {}, "job": None, "write": bool(write), "only": only}
        opened = 0
        for rel in sorted(snap):
            if self._follow_open_file(rel, snap[rel]):
                opened += 1
        self._follow["snap"] = snap
        if opened:
            self.goto_layer("files")
        self._follow_schedule()
        self.presence_start()
        self.remember_follow(self._follow["folder"], bool(write), only)
        mode = ("Edits you make to a block are written back into that file (only the nodes you change)."
                if write else "This is read-only: Blockliner never writes to these files, and what you change here is "
                              "replaced the next time the file changes on disk.")
        messagebox.showinfo(
            "Following a folder",
            f"Following {only if only else (os.path.basename(self._follow['folder']) or folder)}: {opened} file(s).\n\n"
            "The files on disk are the truth. When another program changes a file, Blockliner updates by itself.\n"
            f"{mode}\n\nNext time Blockliner starts it will offer to follow this folder again.")
        return opened

    def stop_following(self, forget=False):
        self.follow_flush()                              # an edit still waiting to be written is written first
        self.presence_stop()
        f, self._follow = self._follow, None
        if forget:
            self.remember_follow(None)
        if f and f.get("job") is not None:
            try:
                self.after_cancel(f["job"])
            except tk.TclError:
                pass
        for tab in getattr(self, "tabs", []):
            tab.pop("followed", None)
            tab.pop("follow_state", None)

    def follow_edit_notice(self, tab):
        """Called when a followed tab is edited here. With write-back on (and the file writable) the edit is written
        into the file a moment later; otherwise the tab stays clean and the user is told once in a while that the
        change is only on screen. Returns True when a notice was shown."""
        tab["dirty"] = False
        f = self._follow
        self.presence_note_edit(tab)
        state = tab.get("follow_state")
        if f is not None and f.get("write") and state and state.get("writable"):
            self._follow_cancel_write(tab)
            if self.follow_sync_manual():
                tab["follow_pending"] = True             # written when the user chooses File > Update Source Files
                self._follow_manual_notice()
            else:
                tab["follow_job"] = self.after(self.follow_delay_ms(), lambda t=tab: self._follow_write_job(t))
            return False
        now = time.time()
        if now - tab.get("follow_notice_at", 0) < NOTICE_SECONDS:
            return False
        tab["follow_notice_at"] = now
        if f is not None and f.get("write") and state:
            why = state.get("why") or "it could not be written back exactly"
            self.show_change_bar(f"This file is read-only here ({why}). The change is only on screen and is replaced "
                                 "when the file changes.", undo=False)
        else:
            self.show_change_bar("Following this folder: the file on disk is the truth. This change is not saved to it "
                                 "and is replaced when the file changes.", undo=False)
        return True

    # ---- when edits are written: automatically after a pause, or only on request ------------
    def follow_sync_manual(self):
        return self.settings.get("follow_sync_mode") == "manual"

    def follow_delay_ms(self):
        """How long after the last edit it is written, from Settings (seconds; 0.6 by default)."""
        try:
            sec = float(self.settings.get("follow_sync_seconds", WRITE_DELAY_MS / 1000))
        except (TypeError, ValueError):
            sec = WRITE_DELAY_MS / 1000
        return int(max(0.1, min(MAX_DELAY_S, sec)) * 1000)

    def follow_waiting_tabs(self):
        """Followed tabs whose file differs from what Blockliner would write now (real edits, not just a tab switch)."""
        f = self._follow
        out = []
        if f is None or not f.get("write"):
            return out
        for tab in list(getattr(self, "tabs", [])):
            state, rel = tab.get("follow_state"), tab.get("followed")
            info = f["snap"].get(rel) if rel else None
            if not (state and state.get("writable") and info) or tab.get("title", "").endswith(" (missing)"):
                continue
            if self.tabs[self.active_tab_index] is tab:
                self.sync_active_tab_state()
            try:
                if self._follow_plan(tab, info)[0] != state["chunks"]:
                    out.append(tab)
            except Exception:
                pass
        return out

    def _follow_manual_notice(self):
        now = time.time()
        if now - getattr(self, "_follow_manual_at", 0) < NOTICE_SECONDS:
            return
        self._follow_manual_at = now
        self.show_change_bar("Edits to followed files are written when you choose File > Update Source Files "
                             "(or switch to automatic in Settings).", undo=False)

    def follow_update_now(self):
        """File > Update Source Files: write every waiting edit now. Returns the number of files written."""
        f = self._follow
        if f is None:
            self.show_change_bar("Not following a folder.", undo=False)
            return 0
        if not f.get("write"):
            self.show_change_bar("This folder is followed read-only (File > Follow a Folder... and answer Yes to write edits back).",
                                 undo=False)
            return 0
        wrote = 0
        for tab in self.follow_waiting_tabs():
            self._follow_cancel_write(tab)
            tab.pop("follow_pending", None)
            if self.follow_write_back(tab):
                wrote += 1
        self.show_change_bar(f"Updated {wrote} source file{'s' if wrote != 1 else ''}." if wrote else
                             "Nothing to update: the files already match.", undo=False)
        return wrote

    # ---- write-back (phase 2) ---------------------------------------------------
    def _follow_cancel_write(self, tab):
        job = tab.pop("follow_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass

    def _follow_write_job(self, tab):
        tab.pop("follow_job", None)
        try:
            self.follow_write_back(tab)
        except Exception as exc:                        # never take the window down over a file
            print(f"follow write-back: {exc}")

    def follow_flush(self):
        """Write now every edit that is still waiting for its short delay. With "only on request" nothing is written
        by itself: the user is asked once about the edits that are still waiting."""
        if self.follow_sync_manual():
            waiting = self.follow_waiting_tabs()
            if waiting and messagebox.askyesno(
                    "Update the source files?",
                    f"{len(waiting)} followed file{'s have' if len(waiting) != 1 else ' has'} edits that were not written yet.\n\n"
                    "Write them into the files now?"):
                for tab in waiting:
                    self.follow_write_back(tab)
            return
        for tab in list(getattr(self, "tabs", [])):
            if tab.get("follow_job") is not None:
                self._follow_cancel_write(tab)
                self._follow_write_job(tab)

    def _follow_arm(self, tab, rel, info):
        """Remember how a followed file looked when it was read (its chunks, what each node generates, its line ends),
        so a later edit can be written back as a splice. Sets tab["follow_state"]; "writable" False says why not."""
        lang = info["language"]
        state = {"writable": False, "why": "", "chunks": [], "baseline": {}, "names": {}, "eol": "\n", "bom": False}
        tab["follow_state"] = state
        src, why = source_writeback.read_source(info["path"])
        if src is None:
            state["why"] = why
            return state
        if portable.NODE_MARKER_RE.search(src.text):
            state["why"] = "it has Blockliner node markers"
            return state
        if source_merge.has_conflicts(src.text):
            state["why"] = "it has unresolved conflicts (File > Resolve Conflicts...)"
            return state
        chunks = portable.split_top_level(src.text) or [
            (os.path.splitext(os.path.basename(rel))[0] or "main", src.text)]
        ids = portable.unique_ids(n for n, _c in chunks)
        nodes = tab.get("nodes") or []
        if any(n.get("child_nodes") for n in nodes) or sorted(n["id"] for n in nodes) != sorted(ids):
            state["why"] = "its nodes do not line up with the file's top-level parts"
            return state
        with self._language_scope(lang):
            baseline = {n["id"]: self.generate_code_for_node(n, lang) for n in nodes}
        state.update(writable=True, chunks=[(i, c) for i, (_n, c) in zip(ids, chunks)], eol=src.eol, bom=src.bom,
                     baseline=baseline,
                     names={n["id"]: n["name"] for n in nodes})
        return state

    def follow_write_back(self, tab):
        """Write the edits made to this followed tab into its file. Returns True when the file was written.
        Only edited nodes are replaced; a file that changed on disk since it was read is never overwritten."""
        f = self._follow
        rel = tab.get("followed")
        state = tab.get("follow_state")
        if f is None or not f.get("write") or rel is None or not state or not state.get("writable"):
            return False
        info = f["snap"].get(rel)
        if info is None or tab.get("title", "").endswith(" (missing)"):
            return False
        if self.tabs[self.active_tab_index] is tab:
            self.sync_active_tab_state()                 # the blocks on screen into the node
        new_chunks, current = self._follow_plan(tab, info)
        if new_chunks == state["chunks"]:
            return False                                 # nothing was edited: the file is not touched
        if source_writeback.hash_file(info["path"]) != info["hash"]:
            return self._follow_conflict(tab, rel, info, new_chunks, current)
        return self._follow_store(tab, rel, info, state, new_chunks, current)

    def _follow_plan(self, tab, info):
        """(the file's new chunks, [(id, generated code)]) for the edits made to this tab: edited nodes regenerated, nodes
        in execution order and, in Python, a renamed function/class renamed everywhere in the file."""
        state = tab["follow_state"]
        lang = info["language"]
        with self._language_scope(lang):                 # the tab may not be the one on screen: use its own block pack
            current = [(n["id"], self.generate_code_for_node(n, lang)) for n in tab["nodes"]]
        chunks = source_writeback.plan(state["chunks"], state["baseline"], current, self._follow_order(tab))
        old_text = dict(state["chunks"])
        renames = {}
        for n in tab["nodes"]:
            was = state["names"].get(n["id"])
            if was and was != n["name"] and source_rename.declares(old_text.get(n["id"], ""), was, lang):
                renames[n["id"]] = (was, n["name"])
        tab["follow_renames"] = []
        if renames and lang in ("python",) + source_rename.CLIKE:
            chunks, skipped, applied = source_rename.apply_renames(chunks, renames, state["chunks"], lang)
            tab["follow_renames"] = applied
            if skipped:
                self.show_change_bar("Not renamed in the file: " + "; ".join(skipped) + ".", undo=False)
        return chunks, current

    def _follow_order(self, tab):
        """Node ids in execution order: the order the nodes have in the file once written (a node's execution order
        number is what Blockliner generates code by). None when the nodes are not all plain top-level functions."""
        nodes = tab.get("nodes") or []
        normalize_orders(nodes)
        keyed = sorted(enumerate(nodes), key=lambda it: (not isinstance(it[1].get("order"), int),
                                                         it[1].get("order") if isinstance(it[1].get("order"), int) else 0,
                                                         it[0]))
        return [n["id"] for _i, n in keyed]

    def _follow_store(self, tab, rel, info, state, new_chunks, current):
        text = source_writeback.join(new_chunks)
        src = source_writeback.Source(text, state["eol"], state["bom"])
        try:
            size, mtime, digest = source_writeback.write_source(info["path"], text, src)
        except OSError as exc:
            self.show_change_bar(f"{rel} could not be written ({exc.strerror or exc}). The change is only on screen.",
                                 undo=False)
            return False
        info.update(size=size, mtime=mtime, hash=digest)    # our own write: not an outside change
        state["chunks"] = new_chunks
        state["baseline"] = dict(current)
        state["names"] = {n["id"]: n["name"] for n in tab["nodes"]}
        tab["follow_codes"] = {cid: t for cid, t in new_chunks}
        tab["dirty"] = False
        self.show_change_bar(f"Saved to {rel}", undo=False)
        applied, tab["follow_renames"] = tab.get("follow_renames") or [], []
        if applied:
            self._follow_rename_elsewhere(rel, applied, info["language"])
        return True

    def _follow_rename_elsewhere(self, rel, applied, lang="python"):
        """A function/class was renamed in `rel`: fix the other files of the followed folder that use it from there (the
        import and the uses that follow from it, see source_rename.rename_elsewhere). The watcher then reads them again."""
        f = self._follow
        fixed, failed = [], []
        for other, oinfo in f["snap"].items():
            if other == rel or not source_rename.same_family(lang, oinfo["language"]):
                continue
            otab = self._follow_tab(other)
            if otab is not None and (otab.get("follow_job") is not None or otab.get("follow_pending")) \
                    and otab.get("follow_state", {}).get("writable"):
                if self._follow_plan(otab, oinfo)[0] != otab["follow_state"]["chunks"]:
                    failed.append(f"{other} (an edit of it is waiting)")
                    continue                            # a real edit of theirs is waiting: not under it
            src, _why = source_writeback.read_source(oinfo["path"])
            if src is None or portable.NODE_MARKER_RE.search(src.text):
                continue
            for old, new in applied:
                text, count = source_rename.rename_elsewhere(oinfo["language"], src.text, other, rel, old, new)
                if text is None:
                    failed.append(f"{other} ({count})")
                elif count:
                    src = source_writeback.Source(text, src.eol, src.bom)
                    fixed.append(other)
            if other in fixed:
                try:
                    source_writeback.write_source(oinfo["path"], src.text, src)
                except OSError:
                    failed.append(f"{other} (could not be written)")
        if fixed or failed:
            msg = f"Renamed also in {', '.join(sorted(set(fixed)))}." if fixed else ""
            if failed:
                msg += (" " if msg else "") + "Not changed: " + ", ".join(failed) + "."
            self.show_change_bar(msg, undo=False)
        if fixed:
            self.follow_check_now()

    # ---- the file changed on disk under an edit (phase 3) -----------------------
    def ask_follow_conflict(self, rel):
        """Ask what to do when a file changed on disk while an edit of it is waiting. Returns "merge" (node by node, see
        source_merge), "mine" (overwrite the file with this version), "theirs" (take the file as it is now, drop the edit) or "copy" (save my version as a copy
        somewhere, then take theirs). Closing the window means "theirs": the file on disk is the truth."""
        win = tk.Toplevel(self)
        win.title("File changed on disk")
        win.transient(self)
        result = {"v": "theirs"}
        tk.Label(win, text=f"{rel} was changed by another program while you were editing it.\n\n"
                           "Which version do you want?", justify="left", padx=16, pady=14).pack()
        row = tk.Frame(win, padx=12, pady=10)
        row.pack()

        def pick(v):
            result["v"] = v
            win.destroy()
        for label, v in (("Merge (keep both changes)", "merge"), ("Keep mine (overwrite the file)", "mine"),
                         ("Take theirs (drop my edit)", "theirs"), ("Save mine as a copy, take theirs", "copy")):
            tk.Button(row, text=label, command=lambda v=v: pick(v)).pack(side="left", padx=4)
        win.protocol("WM_DELETE_WINDOW", lambda: pick("theirs"))
        win.grab_set()
        self.wait_window(win)
        return result["v"]

    def _follow_conflict(self, tab, rel, info, new_chunks, current, recheck=True):
        """The file on disk is not what was read and there is an edit to write. Ask, then act. True when the file was
        written with this version."""
        state = tab["follow_state"]
        choice = self.ask_follow_conflict(rel)
        if choice == "merge":
            done = self._follow_merge(tab, rel, info, new_chunks)
            if done is not None:
                return done
            return False                                 # cancelled: the file and the edit stay as they are
        if choice == "mine":
            return self._follow_store(tab, rel, info, state, new_chunks, current)
        if choice == "copy":
            target = filedialog.asksaveasfilename(
                title="Save my version as", initialfile=os.path.basename(info["path"]) + ".mine",
                initialdir=os.path.dirname(info["path"]))
            if target:
                text = source_writeback.join(new_chunks)
                try:
                    source_writeback.write_source(target, text, source_writeback.Source(text, state["eol"], state["bom"]))
                except OSError as exc:
                    messagebox.showerror("Save a copy", f"Could not save the copy: {exc.strerror or exc}")
        self._follow_cancel_write(tab)
        if recheck:
            self.follow_check_now()                      # their version is shown
        self.show_change_bar(f"{rel} changed on disk first, so your edit was not written. Showing the file as it is now.",
                             undo=False)
        return False

    # ---- merging (phase A of docs/team-editing.md) -------------------------------
    def _follow_merge(self, tab, rel, info, new_chunks):
        """Merge my edit with the file as it is on disk, node by node. Conflicting nodes are asked about (or written as
        conflict markers). True when the merged file was written and read back; None when the user cancelled."""
        state = tab["follow_state"]
        src, why = source_writeback.read_source(info["path"])
        if src is None:
            self.show_change_bar(f"{rel} could not be merged ({why}).", undo=False)
            return None
        theirs = portable.split_top_level(src.text) or [(os.path.splitext(os.path.basename(rel))[0] or "main", src.text)]
        ids = portable.unique_ids(n for n, _c in theirs)
        chunks, conflicts = source_merge.merge(state["chunks"], new_chunks, [(i, c) for i, (_n, c) in zip(ids, theirs)])
        text = source_writeback.join(chunks)
        note = "Merged your edit with the change on disk."
        if conflicts:
            answer = self.ask_follow_resolve(rel, source_merge.conflict_regions(text), allow_markers=True)
            if answer is None:
                return None
            if answer != "markers":
                text = source_merge.resolve(text, answer)
                note = f"Merged {rel}; {len(conflicts)} conflict(s) resolved."
            else:
                note = (f"Merged {rel} with {len(conflicts)} conflict(s) written as markers: the file is read-only here "
                        "until they are resolved (File > Resolve Conflicts...).")
        try:
            size, mtime, digest = source_writeback.write_source(
                info["path"], text, source_writeback.Source(text, src.eol, src.bom))
        except OSError as exc:
            self.show_change_bar(f"{rel} could not be written ({exc.strerror or exc}).", undo=False)
            return None
        info.update(size=size, mtime=mtime, hash=digest)
        self._follow_cancel_write(tab)
        tab.pop("follow_pending", None)
        self._follow_reload(tab, rel, info)
        self.refresh_tab_bar()
        self.show_change_bar(note, undo=False)
        return True

    def ask_follow_resolve(self, rel, regions, allow_markers=False):
        """One window for the conflicts of a file: pick mine / theirs / both for each. Returns the list of choices (in file
        order), "markers" (only when allowed: write them as conflict markers instead) or None (cancelled)."""
        win = tk.Toplevel(self)
        win.title(f"Resolve conflicts - {rel}")
        win.transient(self)
        result = {"v": None}
        choices = ["both"] * len(regions)
        top = tk.Frame(win, padx=10, pady=8)
        top.pack(fill="both", expand=True)
        lb = tk.Listbox(top, height=min(8, max(3, len(regions))), exportselection=False)
        lb.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 8))
        panes = {}
        for col, key, title in ((1, "theirs", "Theirs (on disk)"), (2, "mine", "Mine (Blockliner)")):
            tk.Label(top, text=title).grid(row=0, column=col, sticky="w")
            t = tk.Text(top, width=44, height=12, wrap="none")
            t.grid(row=1, column=col, padx=4, sticky="nsew")
            panes[key] = t
        var = tk.StringVar(value="both")
        sel = {"i": 0}
        bar = tk.Frame(win, padx=10)
        bar.pack(fill="x")

        def refresh_list():
            lb.delete(0, "end")
            for i, c in enumerate(choices):
                first = (regions[i][1] or regions[i][0]).strip().split("\n")[0][:40]
                lb.insert("end", f"{i + 1}. {first}  [{c}]")
            lb.selection_set(sel["i"])

        def show(_e=None):
            cur = lb.curselection()
            if not cur:
                return
            sel["i"] = cur[0]
            for key, idx in (("mine", 0), ("theirs", 1)):
                panes[key].configure(state="normal")
                panes[key].delete("1.0", "end")
                panes[key].insert("1.0", regions[sel["i"]][idx])
                panes[key].configure(state="disabled")
            var.set(choices[sel["i"]])

        def choose():
            choices[sel["i"]] = var.get()
            refresh_list()

        lb.bind("<<ListboxSelect>>", show)
        for label, v in (("Theirs", "theirs"), ("Mine", "mine"), ("Both (theirs, then mine)", "both")):
            tk.Radiobutton(bar, text=label, value=v, variable=var, command=choose).pack(side="left", padx=4)
        end = tk.Frame(win, padx=10, pady=10)
        end.pack(fill="x")

        def done(v):
            result["v"] = v
            win.destroy()
        tk.Button(end, text="Apply choices", command=lambda: done(list(choices))).pack(side="left", padx=4)
        if allow_markers:
            tk.Button(end, text="Write conflict markers instead", command=lambda: done("markers")).pack(side="left", padx=4)
        tk.Button(end, text="Cancel", command=lambda: done(None)).pack(side="right", padx=4)
        win.protocol("WM_DELETE_WINDOW", lambda: done(None))
        refresh_list()
        show()
        win.grab_set()
        self.wait_window(win)
        return result["v"]

    def follow_resolve_conflicts(self):
        """File > Resolve Conflicts...: the followed files that contain conflict markers, one after the other."""
        f = self._follow
        if f is None:
            self.show_change_bar("Not following a folder.", undo=False)
            return 0
        fixed = 0
        for rel, info in sorted(f["snap"].items()):
            src, _why = source_writeback.read_source(info["path"])
            if src is None or not source_merge.has_conflicts(src.text):
                continue
            answer = self.ask_follow_resolve(rel, source_merge.conflict_regions(src.text))
            if not answer:
                continue
            text = source_merge.resolve(src.text, answer)
            try:
                size, mtime, digest = source_writeback.write_source(
                    info["path"], text, source_writeback.Source(text, src.eol, src.bom))
            except OSError as exc:
                self.show_change_bar(f"{rel} could not be written ({exc.strerror or exc}).", undo=False)
                continue
            info.update(size=size, mtime=mtime, hash=digest)
            tab = self._follow_tab(rel)
            if tab is not None:
                self._follow_reload(tab, rel, info)
            fixed += 1
        self.refresh_tab_bar()
        self.show_change_bar(f"Resolved the conflicts in {fixed} file{'s' if fixed != 1 else ''}." if fixed
                             else "No unresolved conflicts to resolve.", undo=False)
        return fixed

    # ---- remembering the folder ----------------------------------------------
    def remember_follow(self, folder, write=False, only=None):
        """Keep (or forget, with None) the followed folder in the settings so it can be offered at the next start."""
        if folder:
            self.settings["follow_folder"] = folder
            self.settings["follow_write"] = bool(write)
            if only:
                self.settings["follow_only"] = only
            else:
                self.settings.pop("follow_only", None)
        else:
            self.settings.pop("follow_folder", None)
            self.settings.pop("follow_write", None)
            self.settings.pop("follow_only", None)
        try:
            self.save_app_settings()
        except Exception:
            pass

    def offer_follow_again(self):
        """At startup: offer to follow the folder that was followed last time. Returns True when it was re-followed."""
        folder = self.settings.get("follow_folder")
        if not folder or self._follow is not None:
            return False
        if not os.path.isdir(folder):
            self.remember_follow(None)
            return False
        write = bool(self.settings.get("follow_write"))
        how = ("Edits you make will be written back into those files." if write
               else "Read-only: Blockliner never writes to those files.")
        if not messagebox.askyesno(
                "Follow the folder again?",
                f"Last time you were following:\n\n  {os.path.join(folder, self.settings['follow_only']) if self.settings.get('follow_only') else folder}\n\nFollow it again? ({how})"):
            self.remember_follow(None)
            return False
        return bool(self.follow_folder(folder, write=write, only=self.settings.get("follow_only")))

    # ---- the watcher ----------------------------------------------------
    def _follow_schedule(self, took=0.0):
        """Next look in FOLLOW_MS, or later when the last look was slow (a big folder): never more than ~10% busy."""
        if self._follow is not None:
            self._follow["job"] = self.after(max(FOLLOW_MS, int(took * 10000)), self._follow_tick)

    def _follow_tick(self):
        f = self._follow
        if f is None:
            return
        t0 = time.time()
        try:
            self.follow_check_now()
            self.presence_tick()
        except Exception as exc:                    # a watcher must never take the window down
            print(f"follow: {exc}")
        self._follow_schedule(time.time() - t0)

    def follow_check_now(self):
        """One look at the folder. Returns (added, changed, removed) relative paths."""
        f = self._follow
        if f is None:
            return [], [], []
        new = self._follow_snapshot(f["folder"], f.get("only"), previous=f["snap"])
        added, changed, removed = source_follow.diff(f["snap"], new)
        if not (added or changed or removed):
            f["snap"] = new
            return added, changed, removed
        back = self.active_tab_index
        keep = self.tabs[back] if 0 <= back < len(self.tabs) else None
        for rel in added:
            self._follow_open_file(rel, new[rel])
        for rel in changed:
            tab = self._follow_tab(rel)
            if tab is None:
                self._follow_open_file(rel, new[rel])
            elif self._follow_pending_edit(tab, rel, new[rel]):
                continue                                 # the user chose to keep their edit (and wrote it)
            else:
                self._follow_reload(tab, rel, new[rel])
        for rel in removed:
            tab = self._follow_tab(rel)
            if tab is not None and not tab.get("title", "").endswith(" (missing)"):
                tab["title"] += " (missing)"
        f["snap"] = new
        if keep in self.tabs and self.tabs.index(keep) != self.active_tab_index:
            self.switch_to_tab(self.tabs.index(keep))
        self.refresh_tab_bar()
        return added, changed, removed

    def _follow_pending_edit(self, tab, rel, info):
        """An outside change arrived while an edit of this tab waits for its write: ask. True when the edit was kept and
        written over the new file (the tab stays as it is); False when their version should be read in."""
        state = tab.get("follow_state")
        f = self._follow
        if (tab.get("follow_job") is None and not tab.get("follow_pending")) or not f.get("write") or not state \
                or not state.get("writable"):
            return False
        self._follow_cancel_write(tab)
        tab.pop("follow_pending", None)
        if self.tabs[self.active_tab_index] is tab:
            self.sync_active_tab_state()
        new_chunks, current = self._follow_plan(tab, info)
        if new_chunks == state["chunks"]:
            return False
        return self._follow_conflict(tab, rel, info, new_chunks, current, recheck=False)

    # ---- one file ---------------------------------------------------------
    def _follow_tab(self, rel):
        for tab in self.tabs:
            if tab.get("followed") == rel:
                return tab
        return None

    def _follow_entry(self, rel, info):
        return {"rel": rel, "path": info["path"], "language": info["language"], "ok": True}

    def _follow_open_file(self, rel, info):
        """Open one file of the folder as a new tab, marked as followed. True when it opened."""
        before = len(self.tabs)
        if self.import_project_file(self._follow_entry(rel, info), True) is None or len(self.tabs) == before:
            return False
        tab = self.tabs[-1]
        tab["followed"] = rel
        tab["dirty"] = False                         # it is on disk exactly like this
        try:
            tab["follow_codes"] = source_follow.chunk_codes(self._follow_chunks(rel, info))
        except OSError:
            tab["follow_codes"] = {}
        self._follow_arm(tab, rel, info)
        return True

    def _follow_chunks(self, rel, info):
        """[(name, code)] the file is cut into (the same cut for the first opening and every reload)."""
        text = project_scan.read_text(info["path"])
        chunks = portable.split_top_level(text)
        if not chunks:
            stem = os.path.splitext(os.path.basename(rel))[0]
            chunks = [(stem or "main", text)]
        return chunks

    def _follow_reload(self, tab, rel, info):
        """Read the file again into an existing tab, keeping the nodes where they were."""
        try:
            chunks = self._follow_chunks(rel, info)
        except OSError:
            return False
        lang = info["language"]
        token = self.get_comment_token(lang) or "#"
        marked = portable.wrap_with_markers(chunks, token)
        idx = self.tabs.index(tab)
        if idx != self.active_tab_index:
            self.switch_to_tab(idx)                  # the block matcher works on the current language
        nodes, active, _diag = self.nodes_from_portable_text(marked, lang)
        if not nodes:
            return False
        new_codes = source_follow.chunk_codes(chunks)
        source_follow.carry_layout(tab["nodes"], nodes, tab.get("follow_codes"), new_codes)
        tab["follow_codes"] = new_codes
        tab["nodes"], tab["active_node_id"], tab["dirty"] = nodes, active, False
        tab["title"] = project_scan.node_title(rel)
        self._follow_cancel_write(tab)                   # the file changed under it: what is on disk wins
        self._follow_arm(tab, rel, info)
        self.project_blocks = self.get_active_node(tab)["blocks"]
        self.refresh_workspace()
        return True
