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
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import portable
import project_scan
import source_follow
import source_writeback
from nodes_model import normalize_orders
from ui_common import LANGUAGE_EXTENSIONS

FOLLOW_MS = 1500
NOTICE_SECONDS = 20
WRITE_DELAY_MS = 600          # an edit is written this long after the last change (typing makes many)


class FollowMixin:
    _follow = None             # {"folder", "snap": {rel: info}, "job"} while a folder is followed

    def follow_folder(self, folder=None, write=None):
        """Pick a folder and start following it. `write` True lets edits made here be written back into the files
        (only the nodes that were edited); False keeps it read-only; None asks. Returns how many files were opened
        (0 = nothing started)."""
        if self._follow is not None:
            self.stop_following()
        if folder is None:
            folder = filedialog.askdirectory(title="Follow a folder - pick the project's root folder")
        if not folder:
            return 0
        snap = source_follow.snapshot(folder, LANGUAGE_EXTENSIONS)
        if not snap:
            messagebox.showinfo("Follow a folder", "There are no source files Blockliner can read in that folder.")
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
        self._follow = {"folder": os.path.abspath(folder), "snap": {}, "job": None, "write": bool(write)}
        opened = 0
        for rel in sorted(snap):
            if self._follow_open_file(rel, snap[rel]):
                opened += 1
        self._follow["snap"] = snap
        if opened:
            self.goto_layer("files")
        self._follow_schedule()
        self.remember_follow(self._follow["folder"], bool(write))
        mode = ("Edits you make to a block are written back into that file (only the nodes you change)."
                if write else "This is read-only: Blockliner never writes to these files, and what you change here is "
                              "replaced the next time the file changes on disk.")
        messagebox.showinfo(
            "Following a folder",
            f"Following {os.path.basename(self._follow['folder']) or folder}: {opened} file(s).\n\n"
            "The files on disk are the truth. When another program changes a file, Blockliner updates by itself.\n"
            f"{mode}\n\nNext time Blockliner starts it will offer to follow this folder again.")
        return opened

    def stop_following(self, forget=False):
        self.follow_flush()                              # an edit still waiting to be written is written first
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
        state = tab.get("follow_state")
        if f is not None and f.get("write") and state and state.get("writable"):
            self._follow_cancel_write(tab)
            tab["follow_job"] = self.after(WRITE_DELAY_MS, lambda t=tab: self._follow_write_job(t))
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
        """Write now every edit that is still waiting for its short delay."""
        for tab in list(getattr(self, "tabs", [])):
            if tab.get("follow_job") is not None:
                self._follow_cancel_write(tab)
                self._follow_write_job(tab)

    def _follow_arm(self, tab, rel, info):
        """Remember how a followed file looked when it was read (its chunks, what each node generates, its line ends),
        so a later edit can be written back as a splice. Sets tab["follow_state"]; "writable" False says why not."""
        lang = info["language"]
        state = {"writable": False, "why": "", "chunks": [], "baseline": {}, "eol": "\n", "bom": False}
        tab["follow_state"] = state
        src, why = source_writeback.read_source(info["path"])
        if src is None:
            state["why"] = why
            return state
        if portable.NODE_MARKER_RE.search(src.text):
            state["why"] = "it has Blockliner node markers"
            return state
        chunks = portable.split_top_level(src.text) or [
            (os.path.splitext(os.path.basename(rel))[0] or "main", src.text)]
        ids = portable.unique_ids(n for n, _c in chunks)
        nodes = tab.get("nodes") or []
        if any(n.get("child_nodes") for n in nodes) or sorted(n["id"] for n in nodes) != sorted(ids):
            state["why"] = "its nodes do not line up with the file's top-level parts"
            return state
        state.update(writable=True, chunks=[(i, c) for i, (_n, c) in zip(ids, chunks)], eol=src.eol, bom=src.bom,
                     baseline={n["id"]: self.generate_code_for_node(n, lang) for n in nodes})
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
        lang = info["language"]
        nodes = tab["nodes"]
        current = [(n["id"], self.generate_code_for_node(n, lang)) for n in nodes]
        new_chunks = source_writeback.plan(state["chunks"], state["baseline"], current, self._follow_order(tab))
        if new_chunks == state["chunks"]:
            return False                                 # nothing was edited: the file is not touched
        if source_writeback.hash_file(info["path"]) != info["hash"]:
            return self._follow_conflict(tab, rel, info, new_chunks, current)
        return self._follow_store(tab, rel, info, state, new_chunks, current)

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
        tab["follow_codes"] = {cid: t for cid, t in new_chunks}
        tab["dirty"] = False
        self.show_change_bar(f"Saved to {rel}", undo=False)
        return True

    # ---- the file changed on disk under an edit (phase 3) -----------------------
    def ask_follow_conflict(self, rel):
        """Ask what to do when a file changed on disk while an edit of it is waiting. Returns "mine" (overwrite the file
        with this version), "theirs" (take the file as it is now, drop the edit) or "copy" (save my version as a copy
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
        for label, v in (("Keep mine (overwrite the file)", "mine"), ("Take theirs (drop my edit)", "theirs"),
                         ("Save mine as a copy, take theirs", "copy")):
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

    # ---- remembering the folder ----------------------------------------------
    def remember_follow(self, folder, write=False):
        """Keep (or forget, with None) the followed folder in the settings so it can be offered at the next start."""
        if folder:
            self.settings["follow_folder"] = folder
            self.settings["follow_write"] = bool(write)
        else:
            self.settings.pop("follow_folder", None)
            self.settings.pop("follow_write", None)
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
                f"Last time you were following:\n\n  {folder}\n\nFollow it again? ({how})"):
            self.remember_follow(None)
            return False
        return bool(self.follow_folder(folder, write=write))

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
        except Exception as exc:                    # a watcher must never take the window down
            print(f"follow: {exc}")
        self._follow_schedule(time.time() - t0)

    def follow_check_now(self):
        """One look at the folder. Returns (added, changed, removed) relative paths."""
        f = self._follow
        if f is None:
            return [], [], []
        new = source_follow.snapshot(f["folder"], LANGUAGE_EXTENSIONS, previous=f["snap"])
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
        if tab.get("follow_job") is None or not f.get("write") or not state or not state.get("writable"):
            return False
        self._follow_cancel_write(tab)
        if self.tabs[self.active_tab_index] is tab:
            self.sync_active_tab_state()
        lang = info["language"]
        current = [(n["id"], self.generate_code_for_node(n, lang)) for n in tab["nodes"]]
        new_chunks = source_writeback.plan(state["chunks"], state["baseline"], current, self._follow_order(tab))
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
