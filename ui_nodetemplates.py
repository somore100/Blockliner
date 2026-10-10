"""Node templates in the UI: save a node as a template, add one from the
wire-drop menu / Nodes-layer right-click menu, fill in its variables."""
import tkinter as tk
from tkinter import messagebox
import uuid

import node_templates
from nodes_model import function_nodes_in_tree_order, find_node_by_id, normalize_orders
from ui_common import (DARK_BG, DARK_BORDER, DARK_FG, DARK_PANEL, NODES_BUNDLED_PATH,
                       NODES_USER_PATH, safe_grab_set)

FOLDER_LABELS = (("custom", "Custom nodes"), ("prebuilt", "Prebuilt nodes"))


class NodeTemplatesMixin:
    # ---- where templates live (overridable, e.g. by tests) ----
    def node_template_roots(self):
        return [NODES_BUNDLED_PATH, NODES_USER_PATH]

    def node_template_save_root(self):
        return NODES_USER_PATH

    def available_node_templates(self):
        entries, _notes = node_templates.load_all(self.node_template_roots(), self.current_language)
        return entries

    # ---- menus ----
    def add_template_cascades(self, menu, on_pick, separator=False):
        """Add 'Custom nodes' / 'Prebuilt nodes' cascades (only the ones
        that have entries). Returns True if anything was added."""
        entries = self.available_node_templates()
        groups = [(label, [e for e in entries if e["folder_kind"] == kind])
                  for kind, label in FOLDER_LABELS]
        groups = [(label, g) for label, g in groups if g]
        if not groups:
            return False
        if separator:
            menu.add_separator()
        for label, group in groups:
            sub = self._new_menu(menu)
            for e in group:
                text = e["template"]["name"] + ("  (all languages)" if e["scope"] == node_templates.GENERAL else "")
                sub.add_command(label=text, command=lambda e=e: on_pick(e))
            menu.add_cascade(label=label, menu=sub)
        return True

    # ---- adding a template as a node ----
    def insert_node_template(self, entry, pos, wire_from=None):
        """Create the node(s) from a template at pos (canvas coords).
        Asks for the template's variables first. Function-type results are
        wired from `wire_from` when given. Returns the new node or None."""
        t = entry["template"]
        values = {}
        if t.get("variables"):
            values = self.ask_template_variables(t)
            if values is None:
                return None
        tab = self.tabs[self.active_tab_index]
        target_list = self.get_current_node_list(tab) if self.view_mode == "file" else tab["nodes"]
        raw_id = self.get_raw_code_block_id(self.current_language)
        raw_param = self.get_raw_code_param_name(raw_id) if raw_id else None
        node, notes = node_templates.instantiate(
            t, values, set(self.blocks.keys()), raw_id, raw_param,
            lambda: str(uuid.uuid4())[:8])
        self._make_node_names_unique(tab, node)
        node["canvas_x"], node["canvas_y"] = pos
        target_list.append(node)
        normalize_orders(tab["nodes"])
        self.mark_active_tab_dirty()
        if wire_from is not None and node.get("kind", "function") == "function":
            self.add_wire_by_drag(wire_from, node["id"])      # also refreshes
        else:
            self.refresh_workspace()
        if notes:
            messagebox.showinfo("Node added",
                                "Added, but some parts were skipped:\n- " + "\n- ".join(sorted(set(notes))))
        return node

    def _make_node_names_unique(self, tab, new_node):
        """Wires resolve by function name, so a new function node must not
        reuse a name already in this file."""
        used = {n["name"] for n in function_nodes_in_tree_order(tab["nodes"])}
        for n in function_nodes_in_tree_order([new_node]):
            base, i, name = n["name"], 2, n["name"]
            while name in used:
                name = f"{base} {i}"
                i += 1
            n["name"] = name
            used.add(name)

    def ask_template_variables(self, template):
        """Small dialog: one box per variable (pre-filled with its default).
        Returns {name: text} or None when cancelled."""
        dialog = tk.Toplevel(self)
        dialog.title(template["name"])
        dialog.configure(bg=DARK_PANEL)
        dialog.transient(self)
        safe_grab_set(dialog)
        result = {"values": None}
        tk.Label(dialog, text=f"Fill in the variables for \u201c{template['name']}\u201d", bg=DARK_PANEL,
                 fg=DARK_FG, font=("Segoe UI", 10, "bold")).pack(padx=16, pady=(14, 4), anchor="w")
        if template.get("description"):
            tk.Label(dialog, text=template["description"], bg=DARK_PANEL, fg="#888888",
                     font=("Segoe UI", 8), wraplength=360, justify="left").pack(padx=16, anchor="w")
        entries = {}
        for v in template["variables"]:
            row = tk.Frame(dialog, bg=DARK_PANEL)
            row.pack(fill=tk.X, padx=16, pady=3)
            tk.Label(row, text=v["label"], bg=DARK_PANEL, fg=DARK_FG, width=22, anchor="w").pack(side=tk.LEFT)
            e = tk.Entry(row, bg=DARK_BG, fg=DARK_FG, insertbackground=DARK_FG, relief=tk.FLAT,
                         highlightthickness=1, highlightbackground=DARK_BORDER)
            e.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
            e.insert(0, v["default"])
            entries[v["name"]] = e

        def ok(_e=None):
            result["values"] = {n: e.get() for n, e in entries.items()}
            dialog.destroy()
        btns = tk.Frame(dialog, bg=DARK_PANEL)
        btns.pack(pady=12)
        tk.Button(btns, text="Add node", command=ok, bg="#4ec9b0", fg="#000000",
                  relief=tk.FLAT, padx=14, pady=4).pack(side=tk.LEFT, padx=4)
        tk.Button(btns, text="Cancel", command=dialog.destroy, bg="#888888", fg="white",
                  relief=tk.FLAT, padx=14, pady=4).pack(side=tk.LEFT, padx=4)
        dialog.bind("<Return>", ok)
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        first = next(iter(entries.values()), None)
        if first is not None:
            first.focus_set()
        self.wait_window(dialog)
        return result["values"]

    # ---- saving a node as a template ----
    def save_node_as_template(self, node_id, name=None, description="", scope=None, defaults=None):
        """Backing operation: write the node (function or class) into the
        user's nodes folder. scope = a language id or 'general' (default:
        the current language). Returns the file path."""
        tab = self.tabs[self.active_tab_index]
        node = find_node_by_id(tab["nodes"], node_id)
        if node is None:
            raise ValueError("That node no longer exists.")
        template = node_templates.build_template(node, name=name, description=description, defaults=defaults)
        return node_templates.save_custom(self.node_template_save_root(),
                                          scope or self.current_language, template)

    def save_node_as_template_dialog(self, node_id):
        tab = self.tabs[self.active_tab_index]
        node = find_node_by_id(tab["nodes"], node_id)
        if node is None or node.get("kind", "function") not in node_templates.KINDS:
            return
        found = node_templates.build_template(node)["variables"]
        dialog = tk.Toplevel(self)
        dialog.title("Save as node template")
        dialog.configure(bg=DARK_PANEL)
        dialog.transient(self)
        safe_grab_set(dialog)

        def label(text, **kw):
            tk.Label(dialog, text=text, bg=DARK_PANEL, fg=kw.pop("fg", DARK_FG), anchor="w",
                     **kw).pack(fill=tk.X, padx=16, pady=(8, 0))

        def entry(initial=""):
            e = tk.Entry(dialog, bg=DARK_BG, fg=DARK_FG, insertbackground=DARK_FG, relief=tk.FLAT,
                         highlightthickness=1, highlightbackground=DARK_BORDER)
            e.pack(fill=tk.X, padx=16, ipady=3)
            e.insert(0, initial)
            return e
        label("Template name", font=("Segoe UI", 9, "bold"))
        name_e = entry(node["name"])
        label("Description (optional)")
        desc_e = entry()
        label("Available in")
        scope_var = tk.StringVar(value=self.current_language)
        for value, text in ((self.current_language, f"This language only ({self.current_language})"),
                            (node_templates.GENERAL, "All languages (blocks missing in a language are skipped there)")):
            tk.Radiobutton(dialog, text=text, variable=scope_var, value=value, bg=DARK_PANEL, fg=DARK_FG,
                           selectcolor=DARK_BG, activebackground=DARK_PANEL, activeforeground=DARK_FG,
                           anchor="w").pack(fill=tk.X, padx=12)
        label("Variables: type {{name}} anywhere in the node's text to make a blank you fill in "
              "when you add the node.", fg="#888888", font=("Segoe UI", 8), wraplength=380, justify="left")
        default_entries = {}
        for v in found:
            row = tk.Frame(dialog, bg=DARK_PANEL)
            row.pack(fill=tk.X, padx=16, pady=2)
            tk.Label(row, text=f"{{{{{v['name']}}}}} default", bg=DARK_PANEL, fg=DARK_FG,
                     width=22, anchor="w").pack(side=tk.LEFT)
            e = tk.Entry(row, bg=DARK_BG, fg=DARK_FG, insertbackground=DARK_FG, relief=tk.FLAT,
                         highlightthickness=1, highlightbackground=DARK_BORDER)
            e.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
            default_entries[v["name"]] = e
        if not found:
            label("(no variables found in this node)", fg="#888888", font=("Segoe UI", 8))

        def save(_e=None):
            nm = name_e.get().strip()
            if not nm:
                messagebox.showwarning("Name Required", "Please enter a template name.")
                return
            try:
                path = self.save_node_as_template(
                    node_id, name=nm, description=desc_e.get(), scope=scope_var.get(),
                    defaults={k: e.get() for k, e in default_entries.items()})
            except (OSError, ValueError) as ex:
                messagebox.showerror("Save Error", f"Could not save the template: {ex}")
                return
            dialog.destroy()
            self.maybe_notify("Saved", f"Node template saved to:\n{path}")
        btns = tk.Frame(dialog, bg=DARK_PANEL)
        btns.pack(pady=12)
        tk.Button(btns, text="Save template", command=save, bg="#4ec9b0", fg="#000000",
                  relief=tk.FLAT, padx=14, pady=4).pack(side=tk.LEFT, padx=4)
        tk.Button(btns, text="Cancel", command=dialog.destroy, bg="#888888", fg="white",
                  relief=tk.FLAT, padx=14, pady=4).pack(side=tk.LEFT, padx=4)
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        name_e.focus_set()
        name_e.select_range(0, tk.END)
