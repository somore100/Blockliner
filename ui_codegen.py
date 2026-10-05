"""Code generation, project save/load, export and run."""
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import json
import threading
import subprocess
import sys
from nodes_model import make_node, sorted_function_nodes
import portable
from ui_common import BLOCKLINER_SAVES_PATH, DARK_ACCENT, DARK_BG, DARK_BORDER, DARK_FG, DARK_PANEL, get_block_attr, safe_grab_set


class CodegenMixin:

    def collect_tab_blocks(self, tab):
        """All blocks across every node in the given tab, concatenated
        in node order - including blocks nested inside a class node's
        child_nodes, since a class node's own `blocks` is always empty
        by construction (see make_node/build_initial_nodes_for_language).
        Pulled out of all_tab_blocks_concatenated() so the Files-layer
        code view can generate code for a tab other than the active
        one."""
        nodes = tab.get("nodes")
        if not nodes:
            return None

        # Execution order: blocks are concatenated in each function
        # node's order number (see sorted_function_nodes), not raw
        # tree position. Class/category nodes have empty blocks by
        # construction, so only function nodes contribute anyway.
        combined = []
        for node in sorted_function_nodes(nodes):
            combined.extend(node["blocks"])
        return combined

    def all_tab_blocks_concatenated(self):
        """All blocks across every node in the active tab, concatenated
        in node order - including blocks nested inside a class node's
        child_nodes, since a class node's own `blocks` is always empty
        by construction (see make_node/build_initial_nodes_for_language).
        This is what gets exported/rendered - a node is purely an
        organizational grouping (Phase B), so splitting the same
        blocks across nodes must produce identical total output to
        today's single flat list. Falls back to self.project_blocks if
        (for whatever reason) the active tab has no nodes yet."""
        if not getattr(self, "tabs", None):
            return self.project_blocks
        tab = self.tabs[self.active_tab_index]
        blocks = self.collect_tab_blocks(tab)
        return blocks if blocks is not None else self.project_blocks

    def get_wrapping_class_name(self, tab, lang):
        """The name of the active tab's top-level class node, if it has
        one (e.g. the auto-created C#/Java entry-point wrapper) - falls
        back to a sensible default if not found, so renaming or a
        missing class node never breaks codegen."""
        for node in tab.get("nodes", []):
            if node.get("kind") == "class":
                return node["name"]
        return "Program" if lang == "csharp" else "Main"

    def generate_code_for_node(self, node, lang):
        """Pure: generate code for just this one node's own blocks - no
        concatenation with sibling nodes, and deliberately none of
        generate_code_for_tab's C++/C#/Java wrapper boilerplate
        (#include, class Program {, int main() {, closing braces),
        since that wrapping is a tab-level concern with no block of
        its own behind it. A node's own generated code is exactly its
        blocks rendered flat - per the standing B1/C1 decision that a
        top-level node IS the function, so nothing here wraps it in a
        def/function header either. Used by the Nodes-layer per-node
        'View Code' toggle so each node's view is genuinely just that
        node's blocks, round-trippable through the reverse-matcher
        without it ever seeing wrapper text it was never meant to
        parse. Class/category nodes always have empty `blocks` by
        construction (see make_node) so this naturally returns ''
        for them - callers should skip rendering an editable widget
        for those kinds rather than show a pointless empty box."""
        code = ""
        for block_code in self.render_block_list(node.get("blocks", []), lang):
            code += block_code
        return code

    def generate_code_for_tab(self, tab, lang=None):
        """Pure: generate the full code string for a given tab,
        independent of which tab is currently active. update_generated_code()
        is a thin wrapper around this for the active tab (writing the
        result into self.code_text); the Files-layer 'View Code' toggle
        calls this directly per tab. `lang` defaults to the tab's own
        stored language rather than self.lang_var, since a non-active
        tab's language may differ from whatever the dropdown currently
        shows."""
        if lang is None:
            lang = tab["language"]
        code = ""
        all_blocks = self.collect_tab_blocks(tab)
        if all_blocks is None:
            all_blocks = self.project_blocks if getattr(self, "tabs", None) and tab is self.tabs[self.active_tab_index] else []

        if lang == "cpp":
            has_iostream = any(
                get_block_attr(self.blocks.get(bid), "block_id") == "include_cpp"
                for bid, _ in self.iter_all_blocks_recursive(all_blocks)
            )
            if not has_iostream:
                code += "#include <iostream>\n"
                code += "using namespace std;\n\n"
            code += "int main() {\n"
        elif lang == "csharp":
            class_name = self.get_wrapping_class_name(tab, lang)
            code += f"class {class_name}\n{{\n    static void Main(string[] args)\n    {{\n"
        elif lang == "java":
            class_name = self.get_wrapping_class_name(tab, lang)
            code += f"public class {class_name} {{\n    public static void main(String[] args) {{\n"

        for block_code in self.render_block_list(all_blocks, lang):
            if lang == "cpp":
                block_code = "    " + block_code.replace("\n", "\n    ").rstrip() + "\n"
            elif lang in ("csharp", "java"):
                block_code = "        " + block_code.replace("\n", "\n        ").rstrip() + "\n"
            code += block_code

        if lang == "cpp":
            code += "    return 0;\n}\n"
        elif lang in ("csharp", "java"):
            code += "    }\n}\n"

        return code

    WRAPPER_INDENT = {"cpp": "    ", "csharp": "        ", "java": "        "}
    WRAPPER_TAIL = {"cpp": "    return 0;\n}\n", "csharp": "    }\n}\n", "java": "    }\n}\n"}

    def get_comment_token(self, lang):
        """The language pack's comment_token (cached; None -> '#')."""
        cache = self.__dict__.setdefault("_comment_tokens", {})
        if lang not in cache:
            from engine.loader import load_language_pack
            try:
                manifest, _ = load_language_pack(os.path.join(self.languages_path, lang), verbose=False)
            except Exception:
                manifest = None
            cache[lang] = (manifest or {}).get("comment_token")
        return cache[lang]

    def generate_portable_for_tab(self, tab, lang=None, embed_meta=True):
        """The portable form of a tab's code: exactly generate_code_for_tab's
        output plus node marker lines around each function node (in
        execution order) and the optional metadata block at the end.
        portable.strip_portable() of it is the plain code again."""
        if lang is None:
            lang = tab["language"]
        nodes = tab.get("nodes")
        if not nodes:
            return self.generate_code_for_tab(tab, lang)
        clean = self.generate_code_for_tab(tab, lang)
        indent = self.WRAPPER_INDENT.get(lang, "")
        token = self.get_comment_token(lang)

        chunks = []
        for node in sorted_function_nodes(nodes):
            code = ""
            for block_code in self.render_block_list(node.get("blocks", []), lang):
                if indent:
                    block_code = indent + block_code.replace("\n", "\n" + indent).rstrip() + "\n"
                code += block_code
            start, end = portable.node_marker_lines(node["id"], token)
            chunks.append((start, code, end, indent))

        # head/tail = the wrapper text generate_code_for_tab puts around the
        # bodies; verified, so a mismatch can only ever mean "stay plain".
        body = "".join(c[1] for c in chunks)
        tail = self.WRAPPER_TAIL.get(lang, "")
        if not (clean.endswith(body + tail) and len(clean) >= len(body) + len(tail)):
            return clean
        head = clean[:len(clean) - len(body) - len(tail)]
        meta_block = ""
        if embed_meta:
            meta = portable.build_metadata(nodes, lang, tab.get("active_node_id"))
            meta_block = portable.render_meta_block(meta, token)
        return portable.assemble(head, chunks, tail, meta_block)

    # --- code panel options: safe mode + show markers ---------------------

    def build_code_options_row(self, code_header_row):
        """Two checkboxes on the right side of the code panel's header row."""
        self.safe_mode_var = tk.BooleanVar(value=bool(self.settings.get("safe_mode", True)))
        self.show_markers_var = tk.BooleanVar(value=bool(self.settings.get("show_markers", True)))
        tk.Button(
            code_header_row, text="\U0001F504 Sync code \u2192 blocks", command=self.sync_code_now,
            bg=DARK_PANEL, fg=DARK_FG, relief=tk.FLAT, font=("Segoe UI", 8)
        ).pack(side=tk.RIGHT, padx=4)
        for text, var, cmd in (("Show markers", self.show_markers_var, self.on_show_markers_toggle),
                               ("Safe mode", self.safe_mode_var, self.on_safe_mode_toggle)):
            tk.Checkbutton(
                code_header_row, text=text, variable=var, command=cmd,
                bg=DARK_PANEL, fg=DARK_FG, selectcolor=DARK_BG,
                activebackground=DARK_PANEL, activeforeground=DARK_FG,
                font=("Segoe UI", 8)
            ).pack(side=tk.RIGHT, padx=2)

    def on_safe_mode_toggle(self):
        self.settings["safe_mode"] = bool(self.safe_mode_var.get())
        self.save_app_settings()

    def on_show_markers_toggle(self):
        self.settings["show_markers"] = bool(self.show_markers_var.get())
        self.save_app_settings()
        self.update_generated_code()

    def show_markers_setting(self):
        return bool(self.settings.get("show_markers", True))

    def safe_mode_setting(self):
        return bool(self.settings.get("safe_mode", True))

    def install_code_guard(self):
        """Route every edit of the code panel through a check: with safe mode
        on, anything that would change a node marker line (or the embedded
        metadata block) is refused. Blockliner's own regeneration bypasses it."""
        widget = self.code_text
        name = str(widget)
        orig = name + "_orig"
        widget.tk.call("rename", name, orig)
        self._code_internal = False

        def proxy(*args):
            editing = bool(args) and args[0] in ("insert", "delete", "replace") and not self._code_internal
            if editing and self.safe_mode_setting() and self.code_edit_blocked(orig, args):
                widget.bell()
                return ""
            if editing:
                self.confirm_first_code_edit()
            result = widget.tk.call((orig,) + args)
            if editing:
                self.on_code_panel_edited(args)
            return result

        widget.tk.createcommand(name, proxy)

    def code_edit_blocked(self, orig, args):
        call = self.code_text.tk.call
        def idx(i):
            return call(orig, "index", i)
        # pasting/typing marker or metadata tags would duplicate structure
        new_text = args[2] if args[0] == "insert" and len(args) > 2 else (
            args[3] if args[0] == "replace" and len(args) > 3 else "")
        if isinstance(new_text, str) and (portable.NODE_MARKER_RE.search(new_text)
                                          or portable.META_START_TAG in new_text
                                          or portable.META_END_TAG in new_text):
            return True
        text = call(orig, "get", "1.0", "end-1c")
        lines = text.split("\n")
        protected = portable.protected_line_numbers(lines)
        if not protected:
            return False
        def line_col(i):
            ln, col = str(idx(i)).split(".")
            return int(ln), int(col)
        if args[0] == "insert":
            ln, col = line_col(args[1])
            if ln in protected:
                return col > 0   # col 0 only pushes the marker down a line
            return False
        a = line_col(args[1])
        b = line_col(args[2]) if len(args) > 2 and args[2] not in ("",) else (a[0], a[1] + 1)
        if b < a:
            a, b = b, a
        if a == b:
            return False
        for ln in range(a[0], b[0] + 1):
            if ln not in protected:
                continue
            start = (ln, 0)
            end = (ln + 1, 0)   # the line plus its newline
            if a < end and b > start:
                return True
        # deleting just the newline in front of a marker line would glue it to code
        if b[1] == 0 and b[0] in protected and a[0] == b[0] - 1 and a[1] == len(lines[a[0] - 1]):
            return True
        return False

    def embed_meta_setting(self):
        """True when node data goes inside the code file (setting 'save_format')."""
        from ui_common import normalize_save_format
        return normalize_save_format(self.settings.get("save_format")) == "embedded"

    def load_portable_text(self, text, title="Imported", sidecar_text=None):
        """Open a portable file's text as a NEW tab: nodes, nesting, order
        and layout from its metadata when present, otherwise a flat
        skeleton from the markers (see portable.rebuild_nodes). Each
        function node's code goes through the normal Code -> Blocks matcher
        (unmatched lines stay as Raw Code, so nothing is lost). Returns the
        diagnostics list, or None if the text has no node markers."""
        if not portable.NODE_MARKER_RE.search(text):
            return None
        _n, meta, _d = portable.parse_portable(text)
        sidecar_meta, sidecar_notes = None, []
        if sidecar_text is not None:
            sidecar_meta, sidecar_notes = portable.parse_sidecar(sidecar_text)
        if meta is None:
            meta = sidecar_meta
        lang = (meta or {}).get("language")
        if not (isinstance(lang, str) and os.path.isdir(os.path.join(self.languages_path, lang))):
            lang = self.current_language

        self.sync_active_tab_state()
        placeholder = make_node("main", node_id="main", blocks=[])
        self.tabs.append({
            "title": title, "language": lang, "nodes": [placeholder],
            "active_node_id": "main", "filepath": None, "dirty": False,
        })
        self.switch_to_tab(len(self.tabs) - 1)  # loads the language + palette

        wrapper = self.generate_code_for_tab({"language": lang, "nodes": []}, lang)
        nodes, active, diagnostics = portable.rebuild_nodes(
            text, lang, self.WRAPPER_INDENT.get(lang, ""), wrapper, meta_override=sidecar_meta)
        diagnostics = sidecar_notes + diagnostics

        can_import = self.get_raw_code_block_id(lang) is not None
        if not can_import:
            diagnostics.append(f"no Raw Code block for '{lang}' - node code could not be turned into blocks")

        def fill(level):
            for node in level:
                code = node.pop("code", "")
                if can_import and code.strip():
                    node["blocks"] = self.import_code_to_blocks(code)[0]
                fill(node["child_nodes"])
        fill(nodes)

        if not nodes:
            nodes = [make_node("main", node_id="main", blocks=[])]
            active = "main"
        tab = self.tabs[self.active_tab_index]
        tab["nodes"], tab["active_node_id"], tab["dirty"] = nodes, active, True
        self.project_blocks = self.get_active_node(tab)["blocks"]
        self.view_mode = "file"
        self.refresh_workspace()
        self.refresh_tab_bar()
        return diagnostics

    def get_clean_code(self):
        """Code-panel text with markers/metadata removed - what Run, the
        terminal and VS Code use, identical to the pre-marker output."""
        return portable.strip_portable(self.code_text.get(1.0, tk.END)).strip()

    def update_generated_code(self):
        """Generate code from every node's blocks in the active tab,
        concatenated in node order (see all_tab_blocks_concatenated),
        and write it into the right-hand code panel. Delegates the
        actual generation to generate_code_for_tab() (Files-layer code
        view reuses that same logic for other tabs)."""
        lang = self.lang_var.get()
        tab = self.tabs[self.active_tab_index] if getattr(self, "tabs", None) else None
        code = self.generate_code_for_tab(tab, lang) if tab is not None else self.generate_code_for_tab({"language": lang, "nodes": []}, lang)
        if tab is not None and code.strip() and self.show_markers_setting():
            code_shown = self.generate_portable_for_tab(tab, lang, embed_meta=self.embed_meta_setting())
        else:
            code_shown = code

        if getattr(self, "sync_banner", None) is not None:
            self.hide_sync_banner()   # the panel is being rewritten from blocks
        self._code_internal = True
        try:
            self.code_text.delete(1.0, tk.END)
            if code:
                self.code_text.insert(tk.END, code_shown)
            else:
                self.code_text.insert(tk.END, "# No code generated yet\n# Add blocks from the palette!")
        finally:
            self._code_internal = False

        line_count = len([l for l in code.split('\n') if l.strip()])
        self.line_count_label.config(text=f"{line_count} lines")
    
    def save_project(self):
        """Save project - shows a small dialog to name the file and
        choose where it goes: Blockliner's own saves folder, or any
        custom location via the normal file browser."""
        if not self.project_blocks:
            messagebox.showinfo("Nothing to Save", "Add some blocks first!")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Save Project")
        dialog.geometry("440x230")
        dialog.configure(bg=DARK_PANEL)
        dialog.transient(self)
        safe_grab_set(dialog)

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        tk.Label(
            dialog, text="\U0001F4BE Save Project", bg=DARK_PANEL, fg=DARK_FG,
            font=("Segoe UI", 12, "bold")
        ).pack(pady=(15, 10))

        name_frame = tk.Frame(dialog, bg=DARK_PANEL)
        name_frame.pack(fill=tk.X, padx=20)
        tk.Label(
            name_frame, text="File name:", bg=DARK_PANEL, fg=DARK_FG, font=("Segoe UI", 9)
        ).pack(side=tk.LEFT)
        name_entry = tk.Entry(
            name_frame, bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=DARK_BORDER
        )
        name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0), ipady=4)
        name_entry.insert(0, f"project_{self.current_language}")
        name_entry.focus_set()
        name_entry.select_range(0, tk.END)

        tk.Label(
            dialog, text=f"App folder is: {BLOCKLINER_SAVES_PATH}",
            bg=DARK_PANEL, fg="#888888", font=("Segoe UI", 8, "italic")
        ).pack(pady=(12, 2))

        def do_save_to_app_folder():
            name = name_entry.get().strip()
            if not name:
                messagebox.showwarning("Name Required", "Please enter a file name.")
                return
            if not name.lower().endswith(".json"):
                name += ".json"
            os.makedirs(BLOCKLINER_SAVES_PATH, exist_ok=True)
            filepath = os.path.join(BLOCKLINER_SAVES_PATH, name)
            if self._write_project_file(filepath):
                dialog.destroy()

        def do_save_custom_location():
            name = name_entry.get().strip() or f"project_{self.current_language}"
            if not name.lower().endswith(".json"):
                name += ".json"
            filepath = filedialog.asksaveasfilename(
                initialfile=name,
                defaultextension=".json",
                filetypes=[("Blockliner Project", "*.json"), ("All Files", "*.*")],
                title="Save Blockliner Project"
            )
            if filepath and self._write_project_file(filepath):
                dialog.destroy()

        btn_frame = tk.Frame(dialog, bg=DARK_PANEL)
        btn_frame.pack(pady=12)
        tk.Button(
            btn_frame, text="\U0001F4C1 Save to App Folder", bg="#4ec9b0", fg="#000000",
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9, "bold"),
            command=do_save_to_app_folder, padx=12, pady=7
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_frame, text="\U0001F5C2 Choose Custom Location...", bg="#3a3a3a", fg=DARK_FG,
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
            command=do_save_custom_location, padx=12, pady=7
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            dialog, text="Cancel", bg="#888888", fg="white", relief=tk.FLAT,
            cursor="hand2", command=dialog.destroy
        ).pack(pady=(2, 10))

        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.bind("<Return>", lambda e: do_save_to_app_folder())

    def _write_project_file(self, filepath):
        """Actually write the project JSON to disk. Returns True on success."""
        try:
            project_data = {
                "language": self.current_language,
                "blocks": self.project_blocks
            }
            with open(filepath, 'w') as f:
                json.dump(project_data, f, indent=2)

            tab = self.tabs[self.active_tab_index]
            tab["filepath"] = filepath
            tab["title"] = os.path.splitext(os.path.basename(filepath))[0]
            tab["dirty"] = False
            self.refresh_tab_bar()

            self.maybe_notify("Saved", f"Project saved to:\n{filepath}")
            return True
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save: {e}")
            return False
    
    def load_project(self):
        """Load project from JSON - opens into a new tab, unless the
        current tab is both empty and unmodified, in which case it's
        reused rather than leaving a pointless blank tab behind."""
        initial_dir = BLOCKLINER_SAVES_PATH if os.path.isdir(BLOCKLINER_SAVES_PATH) else "."
        filename = filedialog.askopenfilename(
            filetypes=[("Blockliner Project", "*.json"), ("All Files", "*.*")],
            title="Load Blockliner Project",
            initialdir=initial_dir
        )
        if filename:
            try:
                with open(filename, 'r') as f:
                    project_data = json.load(f)

                if isinstance(project_data, list):
                    loaded_lang = self.current_language
                    loaded_blocks = project_data
                else:
                    loaded_lang = project_data.get("language", "python")
                    loaded_blocks = project_data.get("blocks", [])

                current_tab = self.tabs[self.active_tab_index]
                reuse_current = (not self.project_blocks) and (not current_tab["dirty"])

                if not reuse_current:
                    self.sync_active_tab_state()
                    new_node = make_node("main", node_id="main", blocks=[])
                    self.tabs.append({
                        "title": "Untitled",
                        "language": loaded_lang,
                        "nodes": [new_node],
                        "active_node_id": new_node["id"],
                        "filepath": None,
                        "dirty": False,
                    })
                    self.active_tab_index = len(self.tabs) - 1

                if loaded_lang != self.current_language:
                    self.current_language = loaded_lang
                    self.lang_var.set(loaded_lang)
                    self.load_blocks_for_language(loaded_lang)
                    self.load_and_merge_custom_blocks()
                    self.refresh_palette()

                self.set_project_blocks(loaded_blocks)

                tab = self.tabs[self.active_tab_index]
                tab["filepath"] = filename
                tab["title"] = os.path.splitext(os.path.basename(filename))[0]
                tab["dirty"] = False

                self.refresh_workspace()
                self.refresh_tab_bar()
                self.maybe_notify("Loaded", f"Project loaded from:\n{filename}")
            except Exception as e:
                messagebox.showerror("Load Error", f"Failed to load: {e}")
    
    def export_code(self):
        """Export generated code to file"""
        code = self.code_text.get(1.0, tk.END).strip()
        if not code or code.startswith("# No code"):
            messagebox.showinfo("Nothing to Export", "Generate some code first!")
            return
        
        lang = self.lang_var.get()
        ext_map = {"python": ".py", "cpp": ".cpp", "javascript": ".js", "rust": ".rs"}
        ext = ext_map.get(lang, ".txt")
        
        filename = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=[("Source Code", f"*{ext}"), ("All Files", "*.*")],
            title=f"Export {lang.title()} Code"
        )
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(code)
                note = ""
                if not self.show_markers_setting():
                    note = "\n(markers hidden - exported plain code, no node data)"
                elif not self.embed_meta_setting():
                    note = self.write_sidecar_for_active_tab(filename, lang)
                self.maybe_notify("Exported", f"Code exported to:\n{filename}{note}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export: {e}")
    
    def write_sidecar_for_active_tab(self, code_path, lang):
        """Write <code_path>.blockliner.json for the active tab's nodes (or
        remove a stale one when there are no nodes). Returns a note for the
        export popup."""
        tab = self.tabs[self.active_tab_index] if getattr(self, "tabs", None) else None
        side = portable.sidecar_path(code_path)
        if tab is None or not tab.get("nodes"):
            return ""
        meta = portable.build_metadata(tab["nodes"], lang, tab.get("active_node_id"))
        with open(side, "w", encoding="utf-8") as f:
            f.write(portable.render_sidecar(meta))
        return f"\n{side}"

    def run_in_terminal(self):
        """Run code in external terminal"""
        code = self.get_clean_code()
        if not code or code.startswith("# No code"):
            messagebox.showwarning("No Code", "Generate some code first!")
            return
        
        lang = self.lang_var.get()
        
        try:
            if lang == "python":
                # Create temp Python file
                temp_file = os.path.join(os.getcwd(), "temp_blockliner_script.py")
                with open(temp_file, 'w') as f:
                    f.write(code)
                
                # Run in terminal based on OS
                if os.name == 'nt':  # Windows
                    subprocess.Popen(['cmd', '/K', self.settings.get("python_command", "python"), temp_file])
                else:  # macOS/Linux
                    term_cmd = self.settings.get("terminal_command", "gnome-terminal --").split()
                    py_cmd = self.settings.get("python_command", "python3")
                    subprocess.Popen(term_cmd + [py_cmd, temp_file])
                
                messagebox.showinfo("Running", "Python script is running in terminal!")
            
            elif lang == "cpp":
                # Create temp C++ file
                temp_cpp = os.path.join(os.getcwd(), "temp_blockliner_script.cpp")
                temp_exe = os.path.join(os.getcwd(), "temp_blockliner_script.exe")
                
                with open(temp_cpp, 'w') as f:
                    f.write(code)
                
                # Compile C++ code
                messagebox.showinfo("Compiling", "Compiling C++ code...\nThis may take a moment.")
                
                if os.name == 'nt':  # Windows
                    # Try configured compiler (default g++/MinGW)
                    compile_result = subprocess.run(
                        [self.settings.get("cpp_compiler", "g++"), temp_cpp, '-o', temp_exe],
                        capture_output=True,
                        text=True
                    )
                    
                    if compile_result.returncode != 0:
                        messagebox.showerror(
                            "Compilation Error",
                            f"Failed to compile C++ code:\n\n{compile_result.stderr}\n\n" +
                            "Make sure MinGW (g++) is installed and in your PATH."
                        )
                        return
                    
                    # Run compiled program
                    subprocess.Popen(['cmd', '/K', temp_exe])
                    messagebox.showinfo("Running", "C++ program is running in terminal!")
                
                else:  # macOS/Linux
                    compile_result = subprocess.run(
                        [self.settings.get("cpp_compiler", "g++"), temp_cpp, '-o', 'temp_blockliner_script'],
                        capture_output=True,
                        text=True
                    )
                    
                    if compile_result.returncode != 0:
                        messagebox.showerror(
                            "Compilation Error",
                            f"Failed to compile C++ code:\n\n{compile_result.stderr}"
                        )
                        return
                    
                    term_cmd = self.settings.get("terminal_command", "gnome-terminal --").split()
                    subprocess.Popen(term_cmd + ['./temp_blockliner_script'])
                    messagebox.showinfo("Running", "C++ program is running in terminal!")
            
            else:
                messagebox.showinfo("Not Supported", f"Terminal execution for {lang} is not yet supported.")
        
        except FileNotFoundError as e:
            if lang == "cpp":
                messagebox.showerror(
                    "Compiler Not Found",
                    "C++ compiler (g++) not found!\n\n" +
                    "Please install:\n" +
                    "• Windows: MinGW (https://www.mingw-w64.org/)\n" +
                    "• macOS: Xcode Command Line Tools\n" +
                    "• Linux: sudo apt-get install g++\n\n" +
                    "Then add to your system PATH."
                )
            else:
                messagebox.showerror("Error", f"Could not open terminal:\n{e}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not run code:\n{e}")
    
    def open_in_vscode(self):
        """Open generated code in VS Code"""
        code = self.get_clean_code()
        if not code or code.startswith("# No code"):
            messagebox.showwarning("No Code", "Generate some code first!")
            return
        
        try:
            lang = self.lang_var.get()
            ext_map = {"python": ".py", "cpp": ".cpp", "javascript": ".js", "rust": ".rs"}
            ext = ext_map.get(lang, ".txt")
            
            # Create a temp file
            temp_file = os.path.join(os.getcwd(), f"blockliner_script{ext}")
            with open(temp_file, 'w') as f:
                # Add header comment
                f.write(f"# Generated by Blockliner - by domore100\n")
                f.write(f"# Language: {lang}\n")
                f.write(f"# Project blocks: {len(self.project_blocks)}\n\n")
                f.write(code)
            
            # Try to open in VS Code
            try:
                subprocess.Popen(['code', temp_file])
                messagebox.showinfo("VS Code", f"Opening in VS Code!\n\nFile: {temp_file}")
            except FileNotFoundError:
                # VS Code not in PATH, try full path
                if os.name == 'nt':  # Windows
                    vscode_path = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe")
                    if os.path.exists(vscode_path):
                        subprocess.Popen([vscode_path, temp_file])
                        messagebox.showinfo("VS Code", f"Opening in VS Code!\n\nFile: {temp_file}")
                    else:
                        raise FileNotFoundError("VS Code not found")
                else:
                    raise FileNotFoundError("VS Code not found")
        except FileNotFoundError:
            messagebox.showerror(
                "VS Code Not Found",
                "Could not find VS Code.\n\nPlease install VS Code or add it to your PATH.\n\nAlternatively, use 'Export Code' to save the file manually."
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not open VS Code:\n{e}")
    
    def export_and_run(self):
        """Export code and provide run instructions"""
        code = self.get_clean_code()
        if not code or code.startswith("# No code"):
            messagebox.showwarning("No Code", "Generate some code first!")
            return
        
        lang = self.lang_var.get()
        ext_map = {"python": ".py", "cpp": ".cpp", "javascript": ".js", "rust": ".rs"}
        ext = ext_map.get(lang, ".txt")
        
        filename = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=[("Source Code", f"*{ext}"), ("All Files", "*.*")],
            title=f"Export {lang.title()} Code"
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(f"# Generated by Blockliner - by domore100\n")
                    f.write(f"# Language: {lang}\n\n")
                    f.write(code)
                
                # Provide run instructions
                run_instructions = {
                    "python": f"python {os.path.basename(filename)}",
                    "cpp": f"g++ {os.path.basename(filename)} -o output && ./output",
                    "javascript": f"node {os.path.basename(filename)}",
                    "rust": f"rustc {os.path.basename(filename)} && ./output"
                }
                
                instruction = run_instructions.get(lang, f"Run with appropriate compiler/interpreter")
                
                messagebox.showinfo(
                    "Exported!",
                    f"Code exported to:\n{filename}\n\nTo run:\n{instruction}"
                )
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export: {e}")
        """Execute generated Python code in a thread to prevent freezing"""
        code = self.get_clean_code()
        if not code or code.startswith("# No code"):
            messagebox.showwarning("No Code", "Generate some code first!")
            return
        
        if self.lang_var.get() != "python":
            messagebox.showinfo("Python Only", "Only Python code can be run directly.\nExport and compile/run externally.")
            return
        
        # Create output window
        output_window = tk.Toplevel(self)
        output_window.title("Program Output")
        output_window.geometry("700x500")
        output_window.configure(bg=DARK_BG)
        
        # Header
        header = tk.Frame(output_window, bg=DARK_ACCENT, height=40)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="▶ Program Output",
            bg=DARK_ACCENT,
            fg="white",
            font=("Segoe UI", 12, "bold")
        ).pack(side=tk.LEFT, padx=15, pady=10)
        
        # Output text
        output_text = tk.Text(
            output_window,
            bg="#1e1e1e",
            fg="#00ff00",
            font=("Consolas", 10),
            padx=15,
            pady=15,
            wrap=tk.WORD
        )
        output_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Run in thread to prevent UI freezing
        def execute_code():
            import sys
            from io import StringIO
            
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            old_stdin = sys.stdin
            
            sys.stdout = StringIO()
            sys.stderr = StringIO()
            
            # Create a custom input handler
            input_buffer = []
            
            def custom_input(prompt=""):
                # Schedule input dialog on main thread
                result = []
                def show_input():
                    user_input = tk.simpledialog.askstring("Input", prompt, parent=output_window)
                    result.append(user_input if user_input is not None else "")
                
                output_window.after(0, show_input)
                # Wait for result
                while not result:
                    import time
                    time.sleep(0.1)
                return result[0]
            
            # Replace built-in input
            import builtins
            old_input = builtins.input
            builtins.input = custom_input
            
            try:
                exec(code, {"__builtins__": builtins})
                stdout_output = sys.stdout.getvalue()
                stderr_output = sys.stderr.getvalue()
                
                def update_output():
                    if stdout_output:
                        output_text.insert(tk.END, stdout_output)
                    if stderr_output:
                        output_text.insert(tk.END, f"\n--- Errors ---\n{stderr_output}", "error")
                        output_text.tag_config("error", foreground="#ff5555")
                    if not stdout_output and not stderr_output:
                        output_text.insert(tk.END, "✓ Program executed successfully (no output)")
                
                output_window.after(0, update_output)
                
            except Exception as e:
                # Capture the message now - 'e' is deleted the moment this
                # except block exits (Python does this automatically), but
                # show_error runs later via .after(), by which point 'e'
                # would already be gone, causing a NameError/free-variable
                # crash every single time a runtime error occurred.
                error_message = str(e)

                def show_error():
                    output_text.insert(tk.END, f"❌ Runtime Error:\n{error_message}", "error")
                    output_text.tag_config("error", foreground="#ff5555")
                
                output_window.after(0, show_error)
                
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                sys.stdin = old_stdin
                builtins.input = old_input
        
        # Start execution in thread
        thread = threading.Thread(target=execute_code, daemon=True)
        thread.start()
    
    def run_code(self):
        """Execute generated Python code in a thread to prevent freezing - runs in Blockliner"""
        code = self.get_clean_code()
        if not code or code.startswith("# No code"):
            messagebox.showwarning("No Code", "Generate some code first!")
            return
        
        if self.lang_var.get() != "python":
            messagebox.showinfo("Python Only", "Blockliner can only run Python code directly.\n\nFor other languages:\n• Use '🖥️ Run in Terminal'\n• Or '📝 Open in VS Code'")
            return
        
        # Create output window
        output_window = tk.Toplevel(self)
        output_window.title("Program Output")
        output_window.geometry("700x500")
        output_window.configure(bg=DARK_BG)
        
        # Header
        header = tk.Frame(output_window, bg=DARK_ACCENT, height=40)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="▶ Program Output",
            bg=DARK_ACCENT,
            fg="white",
            font=("Segoe UI", 12, "bold")
        ).pack(side=tk.LEFT, padx=15, pady=10)
        
        # Output text
        output_text = tk.Text(
            output_window,
            bg="#1e1e1e",
            fg="#00ff00",
            font=("Consolas", 10),
            padx=15,
            pady=15,
            wrap=tk.WORD
        )
        output_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Run in thread to prevent UI freezing
        def execute_code():
            import sys
            from io import StringIO
            
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            old_stdin = sys.stdin
            
            sys.stdout = StringIO()
            sys.stderr = StringIO()
            
            # Create a custom input handler
            input_buffer = []
            
            def custom_input(prompt=""):
                # Schedule input dialog on main thread
                result = []
                def show_input():
                    user_input = tk.simpledialog.askstring("Input", prompt, parent=output_window)
                    result.append(user_input if user_input is not None else "")
                
                output_window.after(0, show_input)
                # Wait for result
                while not result:
                    import time
                    time.sleep(0.1)
                return result[0]
            
            # Replace built-in input
            import builtins
            old_input = builtins.input
            builtins.input = custom_input
            
            try:
                exec(code, {"__builtins__": builtins})
                stdout_output = sys.stdout.getvalue()
                stderr_output = sys.stderr.getvalue()
                
                def update_output():
                    if stdout_output:
                        output_text.insert(tk.END, stdout_output)
                    if stderr_output:
                        output_text.insert(tk.END, f"\n--- Errors ---\n{stderr_output}", "error")
                        output_text.tag_config("error", foreground="#ff5555")
                    if not stdout_output and not stderr_output:
                        output_text.insert(tk.END, "✓ Program executed successfully (no output)")
                
                output_window.after(0, update_output)
                
            except Exception as e:
                # Capture the message now - 'e' is deleted the moment this
                # except block exits (Python does this automatically), but
                # show_error runs later via .after(), by which point 'e'
                # would already be gone, causing a NameError/free-variable
                # crash every single time a runtime error occurred.
                error_message = str(e)

                def show_error():
                    output_text.insert(tk.END, f"❌ Runtime Error:\n{error_message}", "error")
                    output_text.tag_config("error", foreground="#ff5555")
                
                output_window.after(0, show_error)
                
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                sys.stdin = old_stdin
                builtins.input = old_input
        
        # Start execution in thread
        thread = threading.Thread(target=execute_code, daemon=True)
        thread.start()
