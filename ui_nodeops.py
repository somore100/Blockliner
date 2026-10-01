"""Node and file operations: rename, move, delete, order, reference tracking, code editing."""
import tkinter as tk
from tkinter import messagebox, simpledialog
import contextlib
from nodes_model import default_active_node_id, find_node_by_id, function_nodes_in_tree_order, normalize_orders
from ui_common import BLOCK_BG, DARK_BG, DARK_BORDER, DARK_FG


class NodeOpsMixin:

    def render_files_code_view(self):
        """Files layer 'View Code' toggle: every open tab, each as a
        section of per-NODE editable Text widgets (all nodes, including
        those nested in class/category nodes, labelled 'Parent > name').
        Same node-granular design as the Nodes layer's toggle and for
        the same reason: a tab's whole-file code concatenates every node
        plus synthetic C++/C#/Java wrapper lines that no block backs, so
        an edit there can't be attributed back to a node. Each tab is
        rendered and matched under its OWN language pack
        (_language_scope), so tabs in different languages are shown
        correctly and edits never match against the wrong pack.
        Class/category nodes hold no blocks of their own, so they get a
        plain label instead of an empty box."""
        for index, tab in enumerate(self.tabs):
            if index > 0:
                tk.Frame(self.workspace_frame, bg=DARK_BORDER, height=2).pack(fill=tk.X, pady=(10, 10))

            header = tk.Frame(self.workspace_frame, bg=DARK_BG)
            header.pack(fill=tk.X, padx=4, pady=(4, 4))
            tk.Label(
                header, text=f"\U0001F4C4 {tab['title']}", bg=DARK_BG, fg=DARK_FG,
                font=("Segoe UI", 10, "bold"), anchor="w"
            ).pack(side=tk.LEFT)
            tk.Label(
                header, text=tab["language"], bg=DARK_BG, fg="#888888",
                font=("Segoe UI", 9)
            ).pack(side=tk.RIGHT)

            with self._language_scope(tab["language"]):
                for node, path in self.iter_tab_nodes(tab):
                    kind = node.get("kind", "function")
                    label = " \u203a ".join(path + [node["name"]])
                    if kind in ("class", "category"):
                        icon = "\U0001F4C1" if kind == "category" else "\U0001F3DB"
                        tk.Label(
                            self.workspace_frame, text=f"{icon} {label}", bg=DARK_BG,
                            fg="#888888", font=("Segoe UI", 9), anchor="w"
                        ).pack(fill=tk.X, padx=12, pady=(4, 0))
                        continue

                    tk.Label(
                        self.workspace_frame, text=f"\U0001F9E9 {label}", bg=DARK_BG,
                        fg=DARK_FG, font=("Segoe UI", 9, "bold"), anchor="w"
                    ).pack(fill=tk.X, padx=12, pady=(6, 2))
                    code = self.generate_code_for_node(node, tab["language"])
                    text_widget = tk.Text(
                        self.workspace_frame, bg=BLOCK_BG, fg=DARK_FG,
                        insertbackground=DARK_FG, relief=tk.FLAT, wrap=tk.NONE,
                        font=("Consolas", 10), height=max(3, min(30, code.count("\n") + 2))
                    )
                    text_widget.pack(fill=tk.X, padx=12, pady=(0, 4))
                    if code:
                        text_widget.insert("1.0", code)
                    text_widget.bind(
                        "<FocusOut>",
                        lambda _e, t=tab, n=node, w=text_widget:
                            self._on_files_node_code_focus_out(t, n, w)
                    )

    def render_file_code_view(self):
        """Nodes layer 'View Code' toggle: one editable Text widget PER
        NODE at the current file_view_path depth (the same set of boxes
        render_file_view() would otherwise draw), replacing the
        node/wire canvas entirely. This is deliberately node-granular,
        not a single whole-tab blob - see generate_code_for_node's
        docstring for why: the old whole-tab version (still used
        read-only by the Files layer) concatenates every node plus
        synthetic C++/C#/Java wrapper boilerplate that no block backs,
        so there is no clean way to attribute an edit back to the node
        it came from. Per-node keeps editing and attribution the same
        thing: each widget's FocusOut re-matches only its own text and
        replaces only that node's blocks (_on_node_code_focus_out),
        exactly mirroring how the toolbar's Code->Blocks dialog already
        treats self.project_blocks as the active node's blocks alone.
        Class/category nodes have no blocks of their own by
        construction, so they get a plain non-editable note instead of
        an empty, meaningless Text widget - open them (Nodes-layer
        canvas mode) to drill into their children instead."""
        tab = self.tabs[self.active_tab_index]
        nodes = self.get_current_node_list(tab)

        if not nodes:
            self.show_empty_state()
            return

        for index, node in enumerate(nodes):
            if index > 0:
                tk.Frame(self.workspace_frame, bg=DARK_BORDER, height=2).pack(fill=tk.X, pady=(10, 10))

            kind = node.get("kind", "function")
            icon = "\U0001F4C1" if kind == "category" else "\U0001F3DB" if kind == "class" else "\U0001F9E9"

            header = tk.Frame(self.workspace_frame, bg=DARK_BG)
            header.pack(fill=tk.X, padx=4, pady=(4, 4))
            tk.Label(
                header, text=f"{icon} {node['name']}", bg=DARK_BG, fg=DARK_FG,
                font=("Segoe UI", 10, "bold"), anchor="w"
            ).pack(side=tk.LEFT)
            if node.get("locked"):
                tk.Label(
                    header, text="\U0001F512", bg=DARK_BG, fg="#888888"
                ).pack(side=tk.RIGHT)

            if kind in ("class", "category"):
                tk.Label(
                    self.workspace_frame,
                    text="Holds other nodes, not code of its own - open it to view/edit them.",
                    bg=DARK_BG, fg="#888888", font=("Segoe UI", 9), anchor="w"
                ).pack(fill=tk.X, padx=4, pady=(0, 4))
                continue

            code = self.generate_code_for_node(node, tab["language"])
            text_widget = tk.Text(
                self.workspace_frame, bg=BLOCK_BG, fg=DARK_FG,
                insertbackground=DARK_FG, relief=tk.FLAT, wrap=tk.NONE,
                font=("Consolas", 10), height=max(3, min(30, code.count("\n") + 2))
            )
            text_widget.pack(fill=tk.X, padx=4, pady=(0, 4))
            if code:
                text_widget.insert("1.0", code)
            text_widget.bind(
                "<FocusOut>",
                lambda _e, n=node, w=text_widget: self._on_node_code_focus_out(n, w)
            )

    @contextlib.contextmanager
    def _language_scope(self, lang):
        """Temporarily make `lang`'s block pack (and matching custom
        blocks) the loaded one, then restore exactly what was there.
        self.blocks only ever holds the ACTIVE tab's language, but the
        Files layer shows and edits tabs in other languages too:
        matching or rendering another tab's code against the wrong pack
        would mis-match lines and could clobber its blocks. A no-op when
        `lang` is already loaded."""
        if lang == self.current_language:
            yield
            return
        saved = (self.blocks, self.node_types, self.blocks_by_category,
                 self.current_language, getattr(self, "custom_blocks", None))
        try:
            self.current_language = lang
            self.load_blocks_for_language(lang, verbose=False)
            self.load_and_merge_custom_blocks()
            yield
        finally:
            (self.blocks, self.node_types, self.blocks_by_category,
             self.current_language, self.custom_blocks) = saved

    def iter_tab_nodes(self, tab):
        """Depth-first (node, path_names) over every node in a tab,
        including those inside class/category child_nodes. path_names
        is the chain of ancestor names, for 'Category > method' labels."""
        def walk(nodes, path):
            for node in nodes:
                yield node, path
                yield from walk(node.get("child_nodes", []), path + [node["name"]])
        return walk(tab.get("nodes", []), [])

    def _replace_node_blocks(self, tab, node, new_blocks):
        """The one way code-view edits replace a node's blocks. Besides
        storing them on the node, if that node is the ACTIVE tab's
        ACTIVE node, self.project_blocks must be re-pointed too:
        sync_active_tab_state() (run on every tab switch and save)
        writes project_blocks back into the active node, so a stale
        pointer would silently revert the edit."""
        node["blocks"] = new_blocks
        if (getattr(self, "tabs", None) and tab is self.tabs[self.active_tab_index]
                and self.get_active_node(tab) is node):
            self.project_blocks = new_blocks
        tab["dirty"] = True
        self.refresh_tab_bar()

    def _node_code_commit_guard_ok(self, tab, node, layer):
        """Shared staleness guard for _commit_node_code, checked both
        before matching and again right before the deferred rebuild
        actually runs (state can change in between - see below)."""
        if not getattr(self, "tabs", None) or not any(t is tab for t in self.tabs):
            return False
        if layer == "file":
            if (self.view_mode != "file" or not self.file_view_code_mode
                    or tab is not self.tabs[self.active_tab_index]):
                return False
        elif layer == "files":
            if self.view_mode != "files" or not self.files_view_code_mode:
                return False
        else:
            return False
        return find_node_by_id(tab["nodes"], node["id"]) is not None

    def _commit_node_code(self, tab, node, text_widget, layer):
        """Shared code-view commit (Nodes layer 'file', Files layer
        'files'): re-match this ONE node's text against ITS tab's
        language pack and replace only that node's blocks, then
        refresh_workspace() rebuilds every widget from the freshly
        matched blocks - the same 'rebuild UI from canonical data on
        commit' pattern Phase F's ExpressionSlot and Phase A3 use. The
        guards make it a safe no-op when the widget is stale: a layer or
        tab switch that blurred focus mid-teardown, a closed tab, a
        deleted node, or a re-entrant commit.

        The mutate-and-rebuild part is deferred to the next idle tick
        (real-desktop caveat from Handoff #4): this handler fires as a
        FocusOut, most commonly because the user clicked straight into
        ANOTHER code box in the same view. Tk finishes placing that
        click's cursor as part of the SAME synchronous dispatch that
        delivers this FocusOut, and refresh_workspace() destroys every
        widget in the view, including the box just clicked into - doing
        that destruction before Tk is done with the click could swallow
        it or drop the caret. Returning immediately and doing the
        destructive part via after_idle lets the click land first."""
        if getattr(self, "_node_code_committing", False):
            return
        if not self._node_code_commit_guard_ok(tab, node, layer):
            return

        code = text_widget.get("1.0", tk.END)
        with self._language_scope(tab["language"]):
            new_blocks, _matched, _raw = self.import_code_to_blocks(code)
        if new_blocks == node.get("blocks", []):
            return

        def _apply():
            if getattr(self, "_node_code_committing", False):
                return
            if not self._node_code_commit_guard_ok(tab, node, layer):
                return
            self._node_code_committing = True
            try:
                self._replace_node_blocks(tab, node, new_blocks)
                self.refresh_workspace()
            finally:
                self._node_code_committing = False

        self.after_idle(_apply)

    def _on_node_code_focus_out(self, node, text_widget):
        """Nodes-layer per-node commit (active tab)."""
        tab = self.tabs[self.active_tab_index] if getattr(self, "tabs", None) else None
        if tab is not None:
            self._commit_node_code(tab, node, text_widget, "file")

    def _on_files_node_code_focus_out(self, tab, node, text_widget):
        """Files-layer per-node commit (any tab, any language)."""
        self._commit_node_code(tab, node, text_widget, "files")

    # ------------------------------------------------------------------
    # Node / file operations behind the box right-click menus. Each
    # operation is a plain method returning (ok, message, count) so it
    # can be tested without dialogs; the *_dialog wrappers add prompts.
    # ------------------------------------------------------------------

    def _find_node_container(self, nodes, node_id):
        """(list_holding_node, node) searching nested child_nodes, or None."""
        for n in nodes:
            if n["id"] == node_id:
                return nodes, n
            if n.get("child_nodes"):
                found = self._find_node_container(n["child_nodes"], node_id)
                if found:
                    return found
        return None

    def _subtree(self, node):
        """The node plus every node nested under it."""
        out = [node]
        for child in node.get("child_nodes") or []:
            out.extend(self._subtree(child))
        return out

    def _pop_by_identity(self, lst, node):
        for i, n in enumerate(lst):
            if n is node:
                return lst.pop(i)
        return None

    def rename_node(self, tab, node, new_name):
        """Rename a node AND rewrite every func_call in the tab that
        called it by the old name, so wires survive. Refuses empty names,
        locked nodes, and names another node already has (references
        resolve by exact name, so a duplicate would silently rewire)."""
        new_name = (new_name or "").strip()
        old = node["name"]
        if node.get("locked"):
            return False, "This node is locked and can't be renamed.", 0
        if not new_name:
            return False, "The name can't be empty.", 0
        if new_name == old:
            return True, "", 0
        if any(n is not node and n["name"] == new_name for n, _p in self.iter_tab_nodes(tab)):
            return False, f"Another node in this file is already called '{new_name}'.", 0
        updated = 0
        if node.get("kind", "function") == "function":
            with self._language_scope(tab["language"]):
                for other in self.all_function_nodes(tab):
                    for bid, params in self.iter_all_blocks_recursive(other["blocks"]):
                        if bid == "func_call" and (params.get("name") or "").strip() == old:
                            params["name"] = new_name
                            updated += 1
        node["name"] = new_name
        self.mark_active_tab_dirty()
        self.refresh_workspace()
        return True, "", updated

    def count_calls_to(self, tab, node):
        """func_call blocks OUTSIDE node's own subtree that call it (or
        anything nested in it) by name - what deleting would orphan."""
        inside = {id(n) for n in self._subtree(node)}
        names = {n["name"] for n in self._subtree(node) if n.get("kind", "function") == "function"}
        count = 0
        with self._language_scope(tab["language"]):
            for other in self.all_function_nodes(tab):
                if id(other) in inside:
                    continue
                for bid, params in self.iter_all_blocks_recursive(other["blocks"]):
                    if bid == "func_call" and (params.get("name") or "").strip() in names:
                        count += 1
        return count

    def delete_node(self, tab, node):
        """Remove a node (and anything nested in it). Calls that pointed
        at it stay in the code and simply become unresolved."""
        subtree = self._subtree(node)
        if any(n.get("locked") for n in subtree):
            return False, "This node is locked and can't be deleted.", 0
        gone = {id(n) for n in subtree}
        if not any(id(n) not in gone for n in self.all_function_nodes(tab)):
            return False, "A file needs at least one node - this is the last one.", 0
        found = self._find_node_container(tab["nodes"], node["id"])
        if not found:
            return False, "That node no longer exists.", 0
        self._pop_by_identity(found[0], node)
        if tab.get("active_node_id") in {n["id"] for n in subtree}:
            tab["active_node_id"] = default_active_node_id(tab["nodes"])
            if tab is self.tabs[self.active_tab_index]:
                self.project_blocks = self.get_active_node(tab)["blocks"]
        self.mark_active_tab_dirty()
        self.refresh_workspace()
        return True, "", len(subtree)

    def move_destinations(self, tab, node):
        """[(label, target_list)] where this node may be moved: the top
        level and every category, minus where it already is, minus its own
        subtree (no moving a category into itself). Locked nodes: none."""
        if node.get("locked"):
            return []
        found = self._find_node_container(tab["nodes"], node["id"])
        if not found:
            return []
        cur_list = found[0]
        banned = {id(n) for n in self._subtree(node)}
        dests = []
        if cur_list is not tab["nodes"]:
            dests.append(("Top level", tab["nodes"]))

        def walk(nodes, path):
            for n in nodes:
                if id(n) in banned or n.get("kind") != "category":
                    continue
                kids = n.setdefault("child_nodes", [])
                if kids is not cur_list:
                    dests.append((" > ".join(path + [n["name"]]), kids))
                walk(kids, path + [n["name"]])

        walk(tab["nodes"], [])
        return dests

    def move_node(self, tab, node, dest_list):
        """Move a node into dest_list (must be one of move_destinations).
        Its canvas position is dropped so it gets a free default slot in
        its new home. Wires are unaffected (they resolve by name)."""
        if not any(lst is dest_list for _lbl, lst in self.move_destinations(tab, node)):
            return False, "That isn't a valid place to move this node.", 0
        found = self._find_node_container(tab["nodes"], node["id"])
        self._pop_by_identity(found[0], node)
        dest_list.append(node)
        node.pop("canvas_x", None)
        node.pop("canvas_y", None)
        self.mark_active_tab_dirty()
        self.refresh_workspace()
        return True, "", 1

    def rename_file(self, index, new_title):
        """Rename an open file (tab) AND rewrite every import_module in
        other files that resolved to it (same case-insensitive title match
        the Files layer uses), so import wires survive. Renames the
        in-app title only - never the file on disk."""
        if not (0 <= index < len(self.tabs)):
            return False, "That file no longer exists.", 0
        tab = self.tabs[index]
        old = tab["title"]
        new_title = (new_title or "").strip()
        if not new_title:
            return False, "The name can't be empty.", 0
        if new_title == old:
            return True, "", 0
        if any(i != index and t["title"].strip().lower() == new_title.lower()
               for i, t in enumerate(self.tabs)):
            return False, f"Another open file is already called '{new_title}'.", 0
        updated = 0
        for i, t in enumerate(self.tabs):
            if i == index:
                continue
            changed = False
            with self._language_scope(t["language"]):
                for fn in self.all_function_nodes(t):
                    for bid, params in self.iter_all_blocks_recursive(fn["blocks"]):
                        if (bid == "import_module"
                                and (params.get("module") or "").strip().lower() == old.strip().lower()):
                            params["module"] = new_title
                            updated += 1
                            changed = True
            if changed:
                t["dirty"] = True
        tab["title"] = new_title
        tab["dirty"] = True
        self.refresh_tab_bar()
        self.refresh_workspace()
        return True, "", updated

    # --- dialog wrappers ---

    def set_node_order(self, tab, node, value, on_conflict=None):
        """Give a function node an explicit execution-order number.
        Returns (ok, message, holder). A locked node's order is fixed
        (the entry point is always 1) and a locked node's number can't
        be taken. If another node already has `value`: with
        on_conflict=None nothing changes and (False, msg, holder) comes
        back so the caller can ask; "swap" gives the other node this
        node's old number; "take" leaves the other node UNASSIGNED
        (outlined red, generated last) until the user numbers it."""
        if node.get("kind", "function") != "function":
            return False, "Only function nodes have an execution order.", None
        if node.get("locked"):
            return False, "This node is locked - its order can't change.", None
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            return False, "The order must be a whole number, 1 or higher.", None
        normalize_orders(tab["nodes"])
        old = node.get("order")
        if old == value:
            return True, "", None
        holder = next((n for n in function_nodes_in_tree_order(tab["nodes"])
                       if n is not node and n.get("order") == value), None)
        if holder is not None:
            if holder.get("locked"):
                return False, f"{value} belongs to the locked node '{holder['name']}'.", None
            if on_conflict is None:
                return False, f"{value} is already used by '{holder['name']}'.", holder
            holder["order"] = old if on_conflict == "swap" else None
        node["order"] = value
        self.mark_active_tab_dirty()
        self.refresh_workspace()
        return True, "", holder

    def set_node_order_dialog(self, node_id):
        tab = self.tabs[self.active_tab_index]
        node = find_node_by_id(tab["nodes"], node_id)
        if node is None or node.get("kind", "function") != "function":
            return
        if node.get("locked"):
            messagebox.showinfo("Execution order", "This node is locked - its order is fixed.")
            return
        normalize_orders(tab["nodes"])
        cur = node.get("order")
        raw = simpledialog.askstring(
            "Execution order", f"Order number for '{node['name']}':",
            initialvalue="" if cur is None else str(cur))
        if raw is None:
            return
        try:
            value = int(raw.strip())
        except ValueError:
            messagebox.showwarning("Execution order", "Enter a whole number (1 or higher).")
            return
        ok, msg, holder = self.set_node_order(tab, node, value)
        if ok:
            return
        if holder is None:
            messagebox.showwarning("Execution order", msg)
            return
        answer = messagebox.askyesnocancel(
            "Order already used",
            f"{value} is already used by '{holder['name']}'.\n\n"
            f"Yes = swap (it takes your old number)\n"
            f"No = take {value} (it becomes unassigned, shown red)\n"
            f"Cancel = keep things as they are")
        if answer is None:
            return
        self.set_node_order(tab, node, value, on_conflict="swap" if answer else "take")

    def rename_node_dialog(self, node_id):
        tab = self.tabs[self.active_tab_index]
        node = find_node_by_id(tab["nodes"], node_id)
        if node is None:
            return
        name = simpledialog.askstring("Rename", "New name:", initialvalue=node["name"])
        if name is None:
            return
        ok, msg, _n = self.rename_node(tab, node, name)
        if not ok:
            messagebox.showwarning("Can't rename", msg)

    def delete_node_dialog(self, node_id):
        tab = self.tabs[self.active_tab_index]
        node = find_node_by_id(tab["nodes"], node_id)
        if node is None:
            return
        if node.get("locked"):
            messagebox.showwarning("Can't delete", "This node is locked and can't be deleted.")
            return
        text = f"Delete '{node['name']}'?"
        inner = len(self._subtree(node)) - 1
        if inner:
            text += f"\n\nThis also deletes the {inner} node{'s' if inner != 1 else ''} inside it."
        calls = self.count_calls_to(tab, node)
        if calls:
            text += (f"\n\n{calls} call{'s' if calls != 1 else ''} in other nodes point at it. "
                     "They stay in the code but become unresolved.")
        if not messagebox.askyesno("Delete", text):
            return
        ok, msg, _n = self.delete_node(tab, node)
        if not ok:
            messagebox.showwarning("Can't delete", msg)

    def rename_file_dialog(self, index):
        if not (0 <= index < len(self.tabs)):
            return
        name = simpledialog.askstring("Rename file", "New name:",
                                      initialvalue=self.tabs[index]["title"])
        if name is None:
            return
        ok, msg, _n = self.rename_file(index, name)
        if not ok:
            messagebox.showwarning("Can't rename", msg)

    def close_file_from_files_view(self, index):
        """Close a file from its Files-layer box and stay on the Files
        layer (close_tab alone would drop you into the Blocks layer)."""
        if not (0 <= index < len(self.tabs)):
            return
        tab = self.tabs[index]
        self.close_tab(index)
        if not any(t is tab for t in self.tabs):  # not cancelled at the unsaved-changes prompt
            self.view_mode = "files"
            self.refresh_workspace()

    def all_function_nodes(self, tab=None):
        """Every function-kind node in the tab, at any depth (top-level
        or nested inside a class) - class nodes themselves excluded,
        since they hold other nodes rather than blocks/references."""
        tab = tab if tab is not None else self.tabs[self.active_tab_index]

        def collect(nodes):
            result = []
            for node in nodes:
                if node.get("kind", "function") == "function":
                    result.append(node)
                if node.get("child_nodes"):
                    result.extend(collect(node["child_nodes"]))
            return result

        return collect(tab.get("nodes", []))

    def recompute_references(self):
        """Phase C1: after any edit, rescan every node's blocks for
        func_call instances and resolve the called name against other
        nodes' names in this file, recomputing node['references'].
        Pure derivation - never hand-authored, and always fully
        recomputed from scratch (not incrementally patched) so it can
        never drift from the blocks that actually produced it. Hooked
        into refresh_workspace() rather than every individual mutation
        site, since refresh_workspace() already runs after every one
        of them. import_module isn't wired here - it references
        external modules/files, not in-file nodes, so it's relevant
        once cross-file wiring exists, not yet."""
        if not getattr(self, "tabs", None):
            return
        tab = self.tabs[self.active_tab_index]
        nodes = self.all_function_nodes(tab)
        name_to_id = {n["name"]: n["id"] for n in nodes}

        for node in nodes:
            refs = []
            for block_id, params in self.iter_all_blocks_recursive(node["blocks"]):
                if block_id == "func_call":
                    called_name = (params.get("name") or "").strip()
                    target_id = name_to_id.get(called_name)
                    if target_id and target_id not in refs:
                        refs.append(target_id)
            node["references"] = refs

    def recompute_file_references(self):
        """Files-layer: after any edit, rescan every tab's blocks for
        import_module instances and resolve the imported module name
        against other tabs, recomputing tab['file_references']. Same
        pure-derivation contract as recompute_references() (C1) - never
        hand-authored, always fully recomputed from scratch.

        Resolution is a hybrid match against each candidate tab's
        title: a saved tab's title is already its filename stem (set
        in save_tab_as()/open the same way), so matching title alone
        covers both "saved filename stem" and "unsaved tab title" -
        there's no separate saved/unsaved code path needed, just a
        single case-insensitive title match. Self-imports never
        resolve (a file can't import itself)."""
        if not getattr(self, "tabs", None):
            return
        title_to_index = {}
        for i, t in enumerate(self.tabs):
            title_to_index.setdefault(t["title"].strip().lower(), i)

        for i, tab in enumerate(self.tabs):
            refs = []
            for node in self.all_function_nodes(tab):
                for block_id, params in self.iter_all_blocks_recursive(node["blocks"]):
                    if block_id == "import_module":
                        module_name = (params.get("module") or "").strip().lower()
                        target_index = title_to_index.get(module_name)
                        if target_index is not None and target_index != i and target_index not in refs:
                            refs.append(target_index)
            tab["file_references"] = refs
