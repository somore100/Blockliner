"""Code panel (right side) -> blocks sync: when and how edits typed in the
panel become blocks. Pure diff logic lives in code_sync.py."""
import tkinter as tk
from tkinter import messagebox

import code_sync
import portable
from nodes_model import function_nodes_in_tree_order, make_node
from ui_common import DARK_BG, DARK_FG, DARK_PANEL, safe_grab_set

SYNC_BANNER_BG = "#5a4500"     # amber: "this needs your decision"
SYNC_BLUE = "#0e639c"


class CodeSyncMixin:
    # --- setup ----------------------------------------------------------

    def install_code_sync(self):
        self._sync_pending = None
        self._sync_after = None
        self._sync_running = False
        self._edit_line = None
        self._code_dirty = False
        self.sync_banner = None
        for seq in ("<KeyRelease>", "<ButtonRelease-1>", "<FocusOut>"):
            self.code_text.bind(seq, lambda _e: self.check_line_leave(), add="+")

    def sync_mode(self):
        return code_sync.normalize_sync_mode(self.settings.get("code_sync_mode"))

    # --- edit notifications (called from the code panel's edit guard) ----

    def confirm_first_code_edit(self):
        """One-time heads-up the first time the panel is edited. Always lets
        the edit through; remembered in settings."""
        if self.settings.get("code_edit_warned"):
            return True
        self.settings["code_edit_warned"] = True
        self.save_app_settings()
        messagebox.showwarning(
            "Editing raw code",
            "Modifying raw code can lead to mistakes, so be careful.\n\n"
            "What you type here is turned into blocks (you choose when, in Settings). "
            "This message is shown only once.")
        return True

    def on_code_panel_edited(self, args):
        self._code_dirty = True
        try:
            self._edit_line = int(str(self.code_text.index(args[1])).split(".")[0])
        except (tk.TclError, ValueError, IndexError):
            self._edit_line = None
        mode = self.sync_mode()
        if mode == "char":
            self.schedule_code_sync(150)
        elif mode == "line":
            self.after_idle(self.check_line_leave)

    def check_line_leave(self):
        if not self._code_dirty or self.sync_mode() != "line":
            return
        try:
            current = int(str(self.code_text.index("insert")).split(".")[0])
        except tk.TclError:
            return
        if current != self._edit_line:
            self.schedule_code_sync(0)

    def schedule_code_sync(self, delay_ms):
        if self._sync_after is not None:
            try:
                self.after_cancel(self._sync_after)
            except tk.TclError:
                pass
        self._sync_after = self.after(delay_ms, self.run_code_sync)

    # --- planning ----------------------------------------------------------

    def _wrapper_ignore(self, lang):
        wrapper = self.generate_code_for_tab({"language": lang, "nodes": []}, lang)
        return {ln.strip() for ln in wrapper.splitlines()}

    def _chunks_by_id(self, text, lang):
        marked, _meta, _diag = portable.parse_portable(text, ignore_lines=self._wrapper_ignore(lang))
        indent = self.WRAPPER_INDENT.get(lang, "")
        return {n["id"]: portable.dedent_code(n["code"], indent) for n in marked}

    def _code_for_blocks(self, lang, blocks):
        t = {"language": lang, "nodes": [make_node("x", node_id="x", blocks=blocks)], "active_node_id": "x"}
        chunks = self._chunks_by_id(self.generate_portable_for_tab(t, lang, embed_meta=False), lang)
        return chunks.get("x", "")

    def _block_sigs(self, lang, blocks):
        return [self._code_for_blocks(lang, [b]) for b in blocks]

    def compute_sync_plan(self):
        """Compare the panel text with the active tab. Returns a dict:
        status 'hidden' (markers off) / 'nomarkers' / 'ok'; for 'ok':
        nodes (changed existing nodes), adds (new marker ids), hunks
        (replace/remove changes that need a decision), missing (ids whose
        markers are gone - never deleted)."""
        tab = self.tabs[self.active_tab_index] if getattr(self, "tabs", None) else None
        if tab is None:
            return {"status": "nomarkers"}
        if not self.show_markers_setting():
            return {"status": "hidden"}
        text = self.code_text.get("1.0", "end-1c")
        if not portable.NODE_MARKER_RE.search(text):
            return {"status": "nomarkers"}
        lang = tab["language"]
        panel = self._chunks_by_id(text, lang)
        old_text = self.generate_portable_for_tab(tab, lang, embed_meta=False)
        old = self._chunks_by_id(old_text, lang)
        nodes = {n["id"]: n for n in function_nodes_in_tree_order(tab["nodes"])}
        plan = {"status": "ok", "tab": tab, "lang": lang, "nodes": [], "adds": [], "hunks": [],
                "missing": [i for i in nodes if i not in panel]}
        can_import = self.get_raw_code_block_id(lang) is not None
        with self._language_scope(lang):
            for node_id, code in panel.items():
                node = nodes.get(node_id)
                if node is None:
                    if can_import and code.strip():
                        plan["adds"].append((node_id, self.import_code_to_blocks(code)[0]))
                    continue
                if code_sync.same_code(old.get(node_id, ""), code):
                    continue
                new_blocks = self.import_code_to_blocks(code)[0] if can_import else None
                if new_blocks is None:
                    continue
                old_blocks = node.get("blocks", [])
                old_sigs = self._block_sigs(lang, old_blocks)
                new_sigs = self._block_sigs(lang, new_blocks)
                ops = code_sync.diff_blocks(old_sigs, new_sigs)
                entry = {"node": node, "old": old_blocks, "new": new_blocks, "ops": ops}
                plan["nodes"].append(entry)
                for n, (tag, i1, i2, j1, j2) in enumerate(ops):
                    if tag in ("replace", "delete"):
                        plan["hunks"].append({
                            "entry": entry, "op": n,
                            "message": code_sync.describe_change(
                                node.get("name") or node_id, tag,
                                code_sync.line_of_block(old_sigs, i1), old_sigs[i1:i2], new_sigs[j1:j2])})
        return plan

    # --- running ---------------------------------------------------------

    def run_code_sync(self, manual=False):
        self._sync_after = None
        if self._sync_running:
            return
        self._sync_running = True
        try:
            plan = self.compute_sync_plan()
            status = plan["status"]
            if status != "ok":
                self.hide_sync_banner()
                if manual:
                    messagebox.showinfo(
                        "Nothing to sync",
                        "Turn on \u201cShow markers\u201d to sync code edits to blocks."
                        if status == "hidden" else "The code panel has no node markers to sync.")
                return
            self._code_dirty = False
            if not plan["nodes"] and not plan["adds"]:
                self.hide_sync_banner()
                if manual:
                    self.maybe_notify("In sync", "Blocks and code already match.")
                return
            if plan["hunks"] and self.settings.get("code_sync_confirm", True):
                self.show_sync_banner(plan)
                return
            self.hide_sync_banner()
            self.apply_sync_plan(plan)
        finally:
            self._sync_running = False

    def sync_code_now(self):
        """The in-panel Sync button (works in every mode)."""
        self.run_code_sync(manual=True)

    def _plan_is_current(self, plan):
        tabs = getattr(self, "tabs", None)
        return bool(tabs) and plan["tab"] is tabs[self.active_tab_index]

    def apply_sync_plan(self, plan, keep=frozenset()):
        """keep = {(id(entry), op)} of replace/remove hunks to leave as blocks."""
        if not self._plan_is_current(plan):
            return
        tab = plan["tab"]
        caret = self.code_text.index("insert")   # refresh_workspace() rewrites the panel
        top = self.code_text.yview()[0]
        for entry in plan["nodes"]:
            keep_ops = {op for (eid, op) in keep if eid == id(entry)}
            merged = code_sync.merge_blocks(entry["old"], entry["new"], entry["ops"], keep_ops)
            self._replace_node_blocks(tab, entry["node"], merged)
        if plan["adds"]:
            orders = [n.get("order") for n in function_nodes_in_tree_order(tab["nodes"])
                      if isinstance(n.get("order"), int)]
            nxt = (max(orders) + 1) if orders else 1
            for node_id, blocks in plan["adds"]:
                tab["nodes"].append(make_node(node_id, node_id=node_id, blocks=blocks, order=nxt))
                nxt += 1
            tab["dirty"] = True
        self.hide_sync_banner()
        self.refresh_workspace()
        self.regenerate_panel_keep_caret(caret, top)

    def regenerate_panel_keep_caret(self, caret=None, top=None):
        caret = caret or self.code_text.index("insert")
        top = self.code_text.yview()[0] if top is None else top
        self.update_generated_code()
        try:
            self.code_text.mark_set("insert", caret)
            self.code_text.yview_moveto(top)
        except tk.TclError:
            pass

    # --- the amber decision banner -------------------------------------

    def hide_sync_banner(self):
        self._sync_pending = None
        if self.sync_banner is not None:
            self.sync_banner.destroy()
            self.sync_banner = None

    def show_sync_banner(self, plan):
        self.hide_sync_banner()
        self._sync_pending = plan
        hunks = plan["hunks"]
        text = hunks[0]["message"] if len(hunks) == 1 else (
            f"{len(hunks)} changes in your code replace or remove blocks. First: {hunks[0]['message']}")
        text += "\nContinue?"
        bar = tk.Frame(self.right_panel, bg=SYNC_BANNER_BG)
        bar.pack(fill=tk.X, padx=10, pady=(6, 0), before=self.code_text)
        tk.Label(bar, text=text, bg=SYNC_BANNER_BG, fg="#ffffff", justify=tk.LEFT,
                 anchor="w", wraplength=380, font=("Segoe UI", 9)).pack(fill=tk.X, padx=8, pady=(6, 4))
        row = tk.Frame(bar, bg=SYNC_BANNER_BG)
        row.pack(fill=tk.X, padx=8, pady=(0, 6))
        tk.Button(row, text="Replace all", bg=SYNC_BLUE, fg="#ffffff", relief=tk.FLAT, padx=8,
                  command=lambda: self.apply_sync_plan(plan)).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(row, text="Keep blocks", bg=DARK_PANEL, fg=DARK_FG, relief=tk.FLAT, padx=8,
                  command=self.keep_blocks_instead).pack(side=tk.LEFT, padx=4)
        tk.Button(row, text="See all\u2026", bg=DARK_PANEL, fg=DARK_FG, relief=tk.FLAT, padx=8,
                  command=lambda: self.open_sync_review(plan)).pack(side=tk.LEFT, padx=4)
        self.sync_banner = bar

    def keep_blocks_instead(self):
        """Throw the typed code away: blocks win, panel is regenerated."""
        self.hide_sync_banner()
        self._code_dirty = False
        self.regenerate_panel_keep_caret()

    def open_sync_review(self, plan):
        """One checkbox per change: ticked = my code wins, unticked = keep the blocks."""
        dialog = tk.Toplevel(self)
        self._sync_review_dialog = dialog
        dialog.title("Review code changes")
        dialog.configure(bg=DARK_PANEL)
        dialog.transient(self)
        tk.Label(dialog, text="Tick the changes where your code should win.\nUnticked ones keep their blocks.",
                 bg=DARK_PANEL, fg=DARK_FG, justify=tk.LEFT, font=("Segoe UI", 9)).pack(anchor="w", padx=12, pady=(10, 6))
        vars_ = []
        for hunk in plan["hunks"]:
            var = tk.BooleanVar(value=True)
            vars_.append((hunk, var))
            tk.Checkbutton(dialog, text=hunk["message"], variable=var, bg=DARK_PANEL, fg=DARK_FG,
                           selectcolor=DARK_BG, activebackground=DARK_PANEL, activeforeground=DARK_FG,
                           anchor="w", justify=tk.LEFT, wraplength=520, font=("Segoe UI", 9)
                           ).pack(fill=tk.X, padx=12, pady=2)

        def apply_selected():
            keep = {(id(h["entry"]), h["op"]) for h, v in vars_ if not v.get()}
            dialog.destroy()
            self.apply_sync_plan(plan, keep)

        row = tk.Frame(dialog, bg=DARK_PANEL)
        row.pack(fill=tk.X, padx=12, pady=10)
        tk.Button(row, text="Apply", bg=SYNC_BLUE, fg="#ffffff", relief=tk.FLAT, padx=12,
                  command=apply_selected).pack(side=tk.RIGHT, padx=4)
        tk.Button(row, text="Cancel", bg=DARK_PANEL, fg=DARK_FG, relief=tk.FLAT, padx=12,
                  command=dialog.destroy).pack(side=tk.RIGHT, padx=4)
        dialog.apply_selected = apply_selected
        dialog.review_vars = vars_
        safe_grab_set(dialog)
        return dialog
