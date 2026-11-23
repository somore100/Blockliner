"""Open a hand-written UI program (tkinter, customtkinter) in the UI designer. The reading is ui_import_reader (pure);
this part builds the file: ordinary nodes for the code around the window, and one UI node for the window itself."""
import tkinter as tk
from tkinter import messagebox

import portable
import ui_import_reader
import ui_node


class UIImportMixin:

    def read_ui_code(self, content):
        """(Result, pack): the first reading of `content` as a window with the UI library its imports point at."""
        packs = self.ui_packs_for("python")
        wanted = "python/kivy" if "kivy" in content else "python/customtkinter" if "customtkinter" in content else "python/tkinter"
        pack = next((p for p in packs if p.id == wanted), None)
        if pack is None:
            return ui_import_reader.Result(problems=[f"there is no UI library '{wanted}'"]), None
        return ui_import_reader.read(content, pack), pack

    def _offer_ui_import(self, content):
        """Python code that builds a window: offer to open it in the designer. True if it was opened."""
        if self.current_language != "python" or not ("tkinter" in content or "customtkinter" in content or "kivy" in content):
            return False
        res, pack = self.read_ui_code(content)
        if res.tree is None:
            return False
        if not messagebox.askyesno(
                "A window was found",
                f"This code builds a window with {res.widgets} widget(s).\n\nOpen the window in the UI designer? "
                "The rest of the code (functions, variables) stays as ordinary nodes, and anything the designer "
                "doesn't know stays as code, so nothing is lost.\n\nNo = open everything as plain nodes."):
            return False
        return self.open_text_as_ui(content)

    def open_text_as_ui(self, content, show_problems=True):
        """Open hand-written UI code in a NEW tab: functions and other code as nodes, the window as a UI node
        (in the place the window had in the code). True when done."""
        if self.current_language != "python":
            if show_problems:
                messagebox.showinfo("UI designer", "Importing a window works for Python (tkinter, customtkinter, Kivy) so far.")
            return False
        res, pack = self.read_ui_code(content)
        if res.tree is None:
            if show_problems:
                messagebox.showinfo("No window found", "\n".join("• " + p for p in res.problems))
            return False
        chunks = (portable.split_top_level(res.before) if res.before.strip() else []) \
            + [("app_window", "pass\n")] \
            + (portable.split_top_level(res.after) if res.after.strip() else [])
        ids = portable.unique_ids(n for n, _c in chunks)
        placeholder_id = ids[[n for n, _c in chunks].index("app_window")]
        token = self.get_comment_token("python") or "#"
        diagnostics = self.load_portable_text(portable.wrap_with_markers(chunks, token), language="python") or []
        tab = self.tabs[self.active_tab_index]
        nodes = tab["nodes"]
        index = next(i for i, n in enumerate(nodes) if n["id"] == placeholder_id)
        old = nodes[index]
        functions = {n["name"]: n["id"] for n in nodes if n.get("kind", "function") == "function" and n["id"] != placeholder_id}
        tree = res.tree
        for wname, key, handler in res.links:                 # command=name: a link to that function's node
            widget = next((w for w in tree.walk() if w["name"] == wname), None)
            if widget is None:
                continue
            if handler in functions:
                widget["events"][key] = functions[handler]
            else:
                widget.setdefault("extra", {})[key] = handler
        new = ui_node.make_ui_node("app_window", placeholder_id, tree, order=old.get("order"))
        for key in ("canvas_x", "canvas_y", "_auto_pos"):
            if key in old:
                new[key] = old[key]
        nodes[index] = new
        self.project_blocks = self.get_active_node(tab)["blocks"]
        self.mark_active_tab_dirty()
        self.refresh_workspace()
        self.update_generated_code()
        lines = [f"Opened the window with {res.widgets} widget(s) in the UI designer (node 'app_window'); the rest of the code is ordinary nodes."]
        lines += res.report[:8] + diagnostics[:4]
        messagebox.showinfo("Opened with notes", "\n".join("• " + n for n in lines))
        return True
