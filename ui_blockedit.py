"""Blocks-layer editing: add/edit/move/delete blocks and block list rendering."""
import tkinter as tk
from tkinter import messagebox, ttk
from ui_common import CATEGORY_COLORS, DARK_ACCENT, DARK_BG, DARK_BORDER, DARK_FG, DARK_PANEL, get_block_attr, safe_grab_set
from ui_widgets import ExpressionSlot


class BlockEditMixin:
        # No same-language neighbor in that direction - already at the edge, no-op.

    def add_block_to_workspace(self, block_module, container_list=None):
        """Add a block to the workspace, or into a container block's
        body if container_list is given."""
        # Check for special action blocks (like custom block creator)
        special_action = get_block_attr(block_module, "block_ui_description", {}).get("special_action")

        # Handle special blocks
        if special_action == "create_custom_block":
            self.create_custom_block_dialog()
            return
        elif special_action == "manage_custom_blocks":
            self.manage_custom_blocks_dialog()
            return

        # Normal block adding
        default_params_func = get_block_attr(block_module, "default_params", None)
        if isinstance(block_module, dict) and default_params_func is None:
            default_params_func = lambda: {p["name"]: p.get("default", "") for p in block_module.get("params", [])}

        params = default_params_func() if callable(default_params_func) else {}
        self.edit_block_params(block_module, params, add_mode=True, container_list=container_list)
    
    def edit_block_params(self, block_module, current_params, add_mode=True, index=None, container_list=None):
        """Show dialog to edit block parameters"""
        block_id = get_block_attr(block_module, "block_id", "unknown")
        display_name = get_block_attr(block_module, "display_name", "Unknown")
        category = get_block_attr(block_module, "category", "Basic")
        description = get_block_attr(block_module, "block_ui_description", {}).get("description", "")
        block_params = get_block_attr(block_module, "params", [])
        
        dialog = tk.Toplevel(self)
        dialog.title(f"{'Add' if add_mode else 'Edit'} {display_name}")
        dialog.geometry("520x480")
        dialog.minsize(420, 320)
        dialog.configure(bg=DARK_PANEL)
        dialog.transient(self)
        safe_grab_set(dialog)
        
        # Header
        header_color = CATEGORY_COLORS.get(category, DARK_ACCENT)
        
        header = tk.Frame(dialog, bg=header_color, height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text=f"⚙ {display_name}",
            bg=header_color,
            fg="#000000",
            font=("Segoe UI", 13, "bold")
        ).pack(side=tk.LEFT, padx=20, pady=15)
        
        tk.Label(
            header,
            text=category,
            bg=header_color,
            fg="#000000",
            font=("Segoe UI", 9)
        ).pack(side=tk.RIGHT, padx=20)
        
        # Description
        if description:
            desc_frame = tk.Frame(dialog, bg=DARK_BG)
            desc_frame.pack(fill=tk.X, padx=20, pady=10)
            
            tk.Label(
                desc_frame,
                text=description,
                bg=DARK_BG,
                fg="#aaaaaa",
                font=("Segoe UI", 9),
                wraplength=450,
                justify=tk.LEFT
            ).pack(anchor="w")
        
        # Nickname (optional, purely for your own organization - never
        # affects generated code). Most useful once a workspace has
        # several similar-looking blocks, especially in languages with
        # more verbose/repetitive syntax than Python.
        nickname_frame = tk.Frame(dialog, bg=DARK_PANEL)
        nickname_frame.pack(fill=tk.X, padx=20, pady=(10, 0))
        tk.Label(
            nickname_frame, text="Nickname (optional):", bg=DARK_PANEL, fg=DARK_FG,
            font=("Segoe UI", 9, "bold")
        ).pack(side=tk.LEFT)
        nickname_entry = tk.Entry(
            nickname_frame, bg=DARK_BG, fg=DARK_FG, insertbackground=DARK_FG,
            font=("Segoe UI", 9), relief=tk.FLAT,
            highlightthickness=1, highlightbackground=DARK_BORDER
        )
        nickname_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0), ipady=3)
        nickname_entry.insert(0, current_params.get("_nickname", ""))

        # Buttons - deliberately created and packed (side=BOTTOM) BEFORE
        # the scrollable params area below. Packing order matters here:
        # a widget packed first with side=BOTTOM permanently reserves its
        # own requested height at the bottom of the dialog, so it can
        # never be squeezed by an expand=True sibling packed after it -
        # which is exactly what was happening before (params_container's
        # expand=True canvas was packed first and claimed height greedily,
        # leaving the button row a few leftover pixels once a fixed-size
        # dialog's content ran long - the actual cause of the "can't tell
        # which button is which" bug, not just a color/label problem).
        # param_widgets/required_param_names are declared now (still
        # empty) and populated later in the params loop below; on_save
        # only reads them when the button is actually clicked, by which
        # point they're fully populated, so this ordering is safe.
        param_widgets = {}
        required_param_names = {p["name"] for p in block_params if p.get("type") == "input"}

        btn_frame = tk.Frame(dialog, bg=DARK_PANEL)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=20)

        def on_save():
            new_params = {name: w.get() for name, w in param_widgets.items()}
            missing = [name for name in required_param_names if not new_params.get(name, "").strip()]
            if missing:
                messagebox.showerror(
                    "Missing Required Value",
                    "Please fill in: " + ", ".join(missing)
                )
                return
            nickname = nickname_entry.get().strip()
            if nickname:
                new_params["_nickname"] = nickname
            # Preserve reserved/internal keys that aren't part of the
            # block's own declared params (nested children, collapsed
            # state) - otherwise editing a container's condition would
            # silently wipe out everything inside its body.
            for reserved_key in ("_children", "_collapsed"):
                if reserved_key in current_params:
                    new_params[reserved_key] = current_params[reserved_key]
            target = container_list if container_list is not None else self.project_blocks
            if add_mode:
                target.append((block_id, new_params))
            else:
                target[index] = (block_id, new_params)
            self.mark_active_tab_dirty()
            self.refresh_workspace()
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        ttk.Button(btn_frame, text="Save & Add" if add_mode else "Save Changes",
                  command=on_save, style="DialogPrimary.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="Cancel", command=on_cancel,
                  style="DialogSecondary.TButton").pack(side=tk.LEFT)

        dialog.bind("<Return>", lambda e: on_save())
        dialog.bind("<Escape>", lambda e: on_cancel())

        # Parameters
        params_container = tk.Frame(dialog, bg=DARK_PANEL)
        params_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        params_canvas = tk.Canvas(params_container, bg=DARK_PANEL, highlightthickness=0)
        params_scroll = ttk.Scrollbar(params_container, orient="vertical", command=params_canvas.yview)
        params_frame = tk.Frame(params_canvas, bg=DARK_PANEL)
        
        params_frame.bind(
            "<Configure>",
            lambda e: params_canvas.configure(scrollregion=params_canvas.bbox("all"))
        )
        
        params_canvas.create_window((0, 0), window=params_frame, anchor="nw")
        params_canvas.configure(yscrollcommand=params_scroll.set)
        
        params_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        params_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        for i, param in enumerate(block_params):
            name = param["name"]
            param_type = param.get("type", "string")
            is_required = name in required_param_names
            
            row_frame = tk.Frame(params_frame, bg=DARK_PANEL)
            row_frame.pack(fill=tk.X, pady=6)
            
            label_frame = tk.Frame(row_frame, bg=DARK_PANEL)
            label_frame.pack(fill=tk.X)
            
            tk.Label(
                label_frame,
                text=f"{name}:",
                bg=DARK_PANEL,
                fg=DARK_FG,
                font=("Segoe UI", 9, "bold")
            ).pack(side=tk.LEFT)
            
            tk.Label(
                label_frame,
                text="(required - no default)" if is_required else f"({param_type})",
                bg=DARK_PANEL,
                fg="#ff9955" if is_required else "#888888",
                font=("Segoe UI", 8, "bold" if is_required else "normal")
            ).pack(side=tk.LEFT, padx=5)
            
            initial_value = current_params.get(name, param.get("default", ""))
            entry_kwargs = dict(
                bg=DARK_BG,
                fg=DARK_FG,
                insertbackground=DARK_FG,
                font=("Consolas", 10),
                relief=tk.FLAT,
                highlightthickness=1,
                highlightbackground=DARK_BORDER,
                highlightcolor=header_color
            )

            # Phase F: expression slots get the chip-capable widget,
            # Python only - every other type/language keeps the plain
            # Entry exactly as before. Both expose the same .get()
            # contract, so on_save below needs no changes either way.
            if param_type == "expression" and self.current_language == "python":
                entry = ExpressionSlot(row_frame, initial_value, header_color, **entry_kwargs)
                entry.pack(fill=tk.X)
            else:
                entry = tk.Entry(row_frame, **entry_kwargs)
                entry.pack(fill=tk.X, pady=(3, 0), ipady=4)
                entry.insert(0, initial_value)
            param_widgets[name] = entry

        if param_widgets:
            list(param_widgets.values())[0].focus_set()
    
    def delete_block(self, index, container_list=None):
        """Delete a block from the workspace, or from a container
        block's body if container_list is given."""
        target = container_list if container_list is not None else self.project_blocks
        if 0 <= index < len(target):
            block_id, _ = target[index]
            module = self.blocks.get(block_id)
            block_name = get_block_attr(module, "display_name", "Block") if module else "Block"
            proceed = True
            if self.settings.get("confirm_delete", True):
                proceed = messagebox.askyesno("Delete Block", f"Remove '{block_name}' from workspace?")
            if proceed:
                target.pop(index)
                self.mark_active_tab_dirty()
                self.refresh_workspace()
    
    def edit_block(self, index, container_list=None):
        """Edit an existing block, in the workspace or inside a container's body."""
        target = container_list if container_list is not None else self.project_blocks
        if 0 <= index < len(target):
            block_id, params = target[index]
            block_module = self.blocks.get(block_id)
            if block_module:
                self.edit_block_params(block_module, params, add_mode=False, index=index, container_list=target)
    
    def move_block_up(self, index, container_list=None):
        """Move block up in sequence, within its own list (workspace or container body)."""
        target = container_list if container_list is not None else self.project_blocks
        if index > 0:
            target[index], target[index-1] = target[index-1], target[index]
            self.mark_active_tab_dirty()
            self.refresh_workspace()
    
    def move_block_down(self, index, container_list=None):
        """Move block down in sequence, within its own list (workspace or container body)."""
        target = container_list if container_list is not None else self.project_blocks
        if index < len(target) - 1:
            target[index], target[index+1] = target[index+1], target[index]
            self.mark_active_tab_dirty()
            self.refresh_workspace()
    
    def show_empty_state(self):
        """Show empty workspace message"""
        self.empty_label = tk.Label(
            self.workspace_frame,
            text="👈 Click or drag blocks from the palette to add them here",
            bg=DARK_BG,
            fg="#555555",
            font=("Segoe UI", 12, "italic")
        )
        self.empty_label.pack(expand=True, pady=150)
    
    def iter_all_blocks_recursive(self, block_list):
        """Yield every (block_id, params) at any nesting depth - used
        for whole-project checks like 'is there an #include already'
        that shouldn't miss blocks tucked inside an if-block's body,
        or (Phase F) tucked inside another block's own param slot as a
        recognized chip - e.g. a func_call typed directly into an
        expression slot instead of dragged in from the palette (see
        engine/slot_match.py). Those must surface here too, or
        recompute_references would silently never wire them into the
        C1/C2/C3 canvas graph, violating the "wires are always
        derived, never missed" invariant."""
        for block_id, params in block_list:
            yield block_id, params
            module = self.blocks.get(block_id)
            if module and get_block_attr(module, "is_container", False):
                yield from self.iter_all_blocks_recursive(params.get("_children", []))
            for value in (params or {}).values():
                if isinstance(value, dict) and "_nested_block" in value:
                    yield from self.iter_all_blocks_recursive(
                        [(value["_nested_block"], value.get("_nested_params", {}))]
                    )

    def render_block_list(self, block_list, lang):
        """
        Render a (possibly nested) list of (block_id, params) into a
        list of code strings, one per block. Container blocks (like
        If) have their _children rendered first, and the resulting
        code strings are passed through as the `children` argument to
        the container's own generate_code - exactly matching the
        generate_code(params, children, lang) contract every block file
        already declares, just actually using `children` for the first
        time instead of it always being an empty list.
        """
        rendered = []
        prev_id = None
        for block_id, params in block_list:
            module = self.blocks.get(block_id)
            if not module:
                rendered.append(f"// ERROR: Block '{block_id}' not found\n")
                prev_id = block_id
                continue

            gen_func = get_block_attr(module, "generate_code")
            if not callable(gen_func):
                rendered.append(f"// ERROR: block '{block_id}' has no generate_code\n")
                continue

            try:
                if get_block_attr(module, "is_container", False):
                    child_list = params.get("_children", [])
                    child_rendered = self.render_block_list(child_list, lang)
                    code = gen_func(params, child_rendered, lang=lang)
                else:
                    code = gen_func(params, [], lang=lang)
            except Exception as e:
                code = f"// ERROR generating block '{block_id}': {e}\n"

            # else/else-if directly after an if/else-if in a K&R brace
            # language: join onto the previous block's closing brace
            # ("} else {") instead of starting a new line. Required in
            # Go (a newline after '}' is a syntax error) and the
            # conventional style everywhere K&R is used. Allman (C#)
            # and indentation languages don't end their else header
            # with '{' / never end a block with '}', so they're left
            # exactly as generated.
            if (block_id in ("else_statement", "elif_statement")
                    and prev_id in ("if_statement", "elif_statement")
                    and rendered and rendered[-1].endswith("}\n")
                    and code.split("\n", 1)[0].rstrip().endswith("{")):
                rendered[-1] = rendered[-1][:-1] + " " + code
            else:
                rendered.append(code)
            prev_id = block_id
        return rendered
