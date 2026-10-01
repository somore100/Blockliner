"""Reusable widgets: palette item, block widget, expression slot."""
import tkinter as tk
from tkinter import ttk
from ui_common import BLOCK_BG, BLOCK_HOVER, CATEGORY_COLORS, DARK_BG, DARK_BORDER, DARK_FG, DARK_HOVER, DARK_PANEL, get_block_attr, safe_grab_set


class PaletteBlockItem(tk.Frame):
    """Block item in palette - click to add"""
    def __init__(self, parent, block_module, on_add, can_drop=None):
        super().__init__(parent, bg=DARK_PANEL, cursor="hand2", relief=tk.FLAT)
        self.block_module = block_module
        self.on_add = on_add
        # can_drop(x_root, y_root) -> bool says whether a drag released
        # there should add the block; without it, dragging never adds.
        self.can_drop = can_drop
        
        # Handle both dict (custom blocks) and module objects
        category = get_block_attr(block_module, "category", "Basic")
        display_name = get_block_attr(block_module, "display_name", "Unknown")
        description = get_block_attr(block_module, "block_ui_description", {}).get("description", "")
        
        self.color = CATEGORY_COLORS.get(category, "#ffffff")
        
        # Color indicator
        indicator = tk.Frame(self, bg=self.color, width=4)
        indicator.pack(side=tk.LEFT, fill=tk.Y)
        
        # Block info
        info_frame = tk.Frame(self, bg=DARK_PANEL)
        info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=6)
        
        self.name_label = tk.Label(
            info_frame,
            text=display_name,
            bg=DARK_PANEL,
            fg=DARK_FG,
            font=("Segoe UI", 9, "bold"),
            anchor="w"
        )
        self.name_label.pack(anchor="w")
        
        if description:
            self.desc_label = tk.Label(
                info_frame,
                text=description[:50] + "..." if len(description) > 50 else description,
                bg=DARK_PANEL,
                fg="#888888",
                font=("Segoe UI", 8),
                anchor="w",
                wraplength=180
            )
            self.desc_label.pack(anchor="w")
        
        # Add button
        add_btn = tk.Label(
            self,
            text="＋",
            bg=DARK_PANEL,
            fg=self.color,
            font=("Segoe UI", 14, "bold"),
            cursor="hand2"
        )
        add_btn.pack(side=tk.RIGHT, padx=8)
        
        # Bind events: a plain click still adds the block; pressing and
        # dragging past a small threshold drags it onto the workspace
        # instead (see _drag_motion/_drag_release).
        self._drag = None
        self._ghost = None
        self._press_xy = None
        widgets = [self, add_btn, self.name_label]
        if description:
            widgets.append(self.desc_label)
        for w in widgets:
            w.bind("<ButtonPress-1>", self._drag_press)
            w.bind("<B1-Motion>", self._drag_motion)
            w.bind("<ButtonRelease-1>", self._drag_release)
        
        self.bind("<Enter>", self.on_hover)
        self.bind("<Leave>", self.on_leave)
    
    def _drag_press(self, e):
        self._press_xy = (e.x_root, e.y_root)
        self._drag = False

    def _drag_motion(self, e):
        if self._press_xy is None:
            return
        if not self._drag:
            if (abs(e.x_root - self._press_xy[0]) <= 5
                    and abs(e.y_root - self._press_xy[1]) <= 5):
                return
            self._drag = True
            self._make_ghost()
        ok = bool(self.can_drop and self.can_drop(e.x_root, e.y_root))
        if self._ghost is not None:
            name = get_block_attr(self.block_module, "display_name", "Block")
            self._ghost_label.config(
                text=name if ok else "\u2715  " + name,
                bg=self.color if ok else "#555555",
                fg="#000000" if ok else "#dddddd")
            self._ghost.geometry(f"+{e.x_root + 14}+{e.y_root + 10}")

    def _drag_release(self, e):
        was_drag = self._drag
        self._drag = False
        self._press_xy = None
        self._destroy_ghost()
        if not was_drag:
            self.on_add(self.block_module)
            return
        if self.can_drop and self.can_drop(e.x_root, e.y_root):
            self.on_add(self.block_module)

    def _make_ghost(self):
        try:
            ghost = tk.Toplevel(self)
            ghost.overrideredirect(True)
            ghost.attributes("-topmost", True)
            try:
                ghost.attributes("-alpha", 0.85)
            except tk.TclError:
                pass
            self._ghost_label = tk.Label(
                ghost, text=get_block_attr(self.block_module, "display_name", "Block"),
                bg=self.color, fg="#000000", font=("Segoe UI", 10, "bold"),
                padx=14, pady=6)
            self._ghost_label.pack()
            self._ghost = ghost
        except tk.TclError:
            self._ghost = None

    def _destroy_ghost(self):
        if self._ghost is not None:
            try:
                self._ghost.destroy()
            except tk.TclError:
                pass
        self._ghost = None

    def on_hover(self, event):
        self.configure(bg=DARK_HOVER, relief=tk.RAISED)
        for child in self.winfo_children():
            if isinstance(child, (tk.Frame, tk.Label)) and child.winfo_width() > 4:
                child.configure(bg=DARK_HOVER)
    
    def on_leave(self, event):
        self.configure(bg=DARK_PANEL, relief=tk.FLAT)
        for child in self.winfo_children():
            if isinstance(child, (tk.Frame, tk.Label)) and child.winfo_width() > 4:
                child.configure(bg=DARK_PANEL)

class BlockWidget(tk.Frame):
    """Visual representation of a block in the workspace. Also renders
    container blocks (like If) with a nested, indented body of child
    BlockWidgets and a way to add more blocks into that body."""
    def __init__(self, parent, block_id, block_module, params, index, container_list, app):
        super().__init__(parent, bg=BLOCK_BG, highlightthickness=2, highlightbackground=DARK_BORDER, relief=tk.RAISED)
        self.block_id = block_id
        self.block_module = block_module
        self.params = params if isinstance(params, dict) else {}
        self.index = index
        self.container_list = container_list
        self.app = app

        self.is_container = get_block_attr(block_module, "is_container", False)
        self.is_collapsed = bool(self.params.get("_collapsed", False))
        
        # Get category color
        category = get_block_attr(block_module, "category", "Basic")
        self.category_color = CATEGORY_COLORS.get(category, "#ffffff")
        
        self.create_widgets()
        self.bind("<Enter>", self.on_hover)
        self.bind("<Leave>", self.on_leave)

    def toggle_collapsed(self):
        self.params["_collapsed"] = not self.is_collapsed
        self.app.refresh_workspace()
        
    def create_widgets(self):
        # Header with block name and buttons
        header = tk.Frame(self, bg=self.category_color, height=32)
        header.pack(fill=tk.X, padx=2, pady=2)
        header.pack_propagate(False)
        
        # Block index number
        tk.Label(
            header,
            text=f"{self.index + 1}",
            bg=self.category_color,
            fg="#000000",
            font=("Segoe UI", 9, "bold"),
            width=3
        ).pack(side=tk.LEFT, padx=(8, 4))

        # Collapse/expand toggle - lets a big block (especially a
        # container with a long body, or eventually a function
        # definition) shrink down to just its header row.
        collapse_btn = tk.Button(
            header, text=("\u25B6" if self.is_collapsed else "\u25BC"),
            font=("Segoe UI", 8), bg=self.category_color, fg="#000000",
            relief=tk.FLAT, width=2, cursor="hand2",
            command=self.toggle_collapsed
        )
        collapse_btn.pack(side=tk.LEFT, padx=(0, 2))
        
        # Block name (with optional nickname). When a nickname is set,
        # it's shown as the PRIMARY label, not the type name - a
        # nickname exists specifically to explain what an otherwise
        # opaque block actually does (e.g. a raw C block containing
        # "sizeof(numbers) / sizeof(numbers[0])" nicknamed "calculates
        # how many elements the array contains"), so it needs to be
        # what a user's eye lands on first, not buried after the type.
        base_name = get_block_attr(self.block_module, "display_name", "Unknown")
        nickname = self.params.get("_nickname", "").strip()
        prefix = "\U0001F9E9 " if self.is_container else ""

        name_label = tk.Label(
            header,
            bg=self.category_color,
            fg="#000000",
            anchor="w"
        )
        name_label.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)

        if nickname:
            name_label.config(text=f'{prefix}{nickname}', font=("Segoe UI", 10, "bold"))
            # Small secondary tag showing the underlying block type, so
            # the type is still visible on a glance/hover - just not
            # competing with the nickname for attention.
            tk.Label(
                header, text=f"({base_name})", bg=self.category_color,
                fg="#3a3a3a", font=("Segoe UI", 8)
            ).pack(side=tk.LEFT, padx=(0, 4))
        else:
            name_label.config(text=f'{prefix}{base_name}', font=("Segoe UI", 10, "bold"))
        
        # Control buttons
        btn_config = {
            "bg": self.category_color,
            "fg": "#000000",
            "relief": tk.FLAT,
            "width": 2,
            "cursor": "hand2"
        }
        
        tk.Button(header, text="▲", font=("Segoe UI", 8), command=self._move_up, **btn_config).pack(side=tk.RIGHT, padx=1)
        tk.Button(header, text="▼", font=("Segoe UI", 8), command=self._move_down, **btn_config).pack(side=tk.RIGHT, padx=1)
        tk.Button(header, text="✎", font=("Segoe UI", 10), command=self._edit, **btn_config).pack(side=tk.RIGHT, padx=2)
        tk.Button(header, text="✕", font=("Segoe UI", 10, "bold"), command=self._delete, **btn_config).pack(side=tk.RIGHT, padx=2)

        if self.is_collapsed:
            return

        # Parameters display
        visible_params = {k: v for k, v in self.params.items() if not k.startswith("_")}
        if visible_params:
            params_frame = tk.Frame(self, bg=BLOCK_BG)
            params_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
            
            for name, value in visible_params.items():
                param_row = tk.Frame(params_frame, bg=BLOCK_BG)
                param_row.pack(fill=tk.X, pady=2)
                
                tk.Label(
                    param_row,
                    text=f"{name}:",
                    bg=BLOCK_BG,
                    fg="#888888",
                    font=("Consolas", 9),
                    anchor="w",
                    width=15
                ).pack(side=tk.LEFT)
                
                # Truncate long values
                display_value = str(value)
                if len(display_value) > 40:
                    display_value = display_value[:37] + "..."
                
                tk.Label(
                    param_row,
                    text=display_value,
                    bg=BLOCK_BG,
                    fg=DARK_FG,
                    font=("Consolas", 9, "bold"),
                    anchor="w"
                ).pack(side=tk.LEFT, padx=4)

        if self.is_container:
            self._build_body()

    def _build_body(self):
        """Render this container's nested child blocks, indented, plus
        a button to add more - recursion happens naturally since each
        child is itself a full BlockWidget, which builds its own body
        the same way if it's also a container."""
        children_list = self.params.setdefault("_children", [])

        body_outer = tk.Frame(self, bg=BLOCK_BG)
        body_outer.pack(fill=tk.X, padx=(28, 8), pady=(0, 8))

        tk.Label(
            body_outer, text="Body:", bg=BLOCK_BG, fg="#888888",
            font=("Segoe UI", 8, "bold")
        ).pack(anchor="w")

        body_frame = tk.Frame(body_outer, bg=DARK_BG, highlightthickness=1, highlightbackground=DARK_BORDER)
        body_frame.pack(fill=tk.X, pady=(2, 4))

        if children_list:
            for i, (child_id, child_params) in enumerate(children_list):
                child_module = self.app.blocks.get(child_id)
                if not child_module:
                    tk.Label(
                        body_frame, text=f"\u26A0 Block '{child_id}' not found",
                        bg=DARK_BG, fg="#ff5555", font=("Consolas", 9)
                    ).pack(anchor="w", padx=6, pady=3)
                    continue
                child_widget = BlockWidget(
                    body_frame, child_id, child_module,
                    child_params if isinstance(child_params, dict) else dict(child_params),
                    i, children_list, self.app
                )
                child_widget.pack(fill=tk.X, padx=6, pady=4)
        else:
            tk.Label(
                body_frame, text="(empty - click below to add a block)",
                bg=DARK_BG, fg="#555555", font=("Segoe UI", 9, "italic")
            ).pack(anchor="w", padx=6, pady=8)

        tk.Button(
            body_outer, text="+ Add Block", bg="#3a3a3a", fg=DARK_FG,
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
            command=lambda: self.app.open_block_chooser_dialog(children_list)
        ).pack(anchor="w", pady=(2, 0))

    def _delete(self):
        self.app.delete_block(self.index, self.container_list)

    def _edit(self):
        self.app.edit_block(self.index, self.container_list)

    def _move_up(self):
        self.app.move_block_up(self.index, self.container_list)

    def _move_down(self):
        self.app.move_block_down(self.index, self.container_list)
    
    def on_hover(self, event):
        self.configure(bg=BLOCK_HOVER, highlightbackground=self.category_color, highlightthickness=3)
    
    def on_leave(self, event):
        self.configure(bg=BLOCK_BG, highlightbackground=DARK_BORDER, highlightthickness=2)

class ExpressionSlot(tk.Frame):
    """
    Phase F: the widget used for an "expression"-typed param field,
    Python only (see edit_block_params, which decides whether to use
    this or a plain tk.Entry per param). Exposes .get()/.focus_set()
    matching tk.Entry's own contract, so on_save's blanket
    `{name: w.get() for name, w in param_widgets.items()}` in
    edit_block_params needs no changes at all to handle this widget
    alongside plain Entries - the same "duck typing over duplication"
    approach the project already uses for Node.blocks vs
    Project.blocks (see engine/model.py).

    On <FocusOut>, the typed text is run through
    engine.slot_match.try_match_expression(); a clean match swaps the
    Entry for a small "chip" showing the recognized func_call instead
    of raw text, with Edit/Revert-to-text actions. An unrecognized or
    still-incomplete parse (a normal state while someone is mid-typing)
    just leaves the field as an ordinary Entry - never an error.
    """

    def __init__(self, parent, initial_value, header_color, **entry_kwargs):
        super().__init__(parent, bg=DARK_PANEL)
        self._header_color = header_color
        self._entry_kwargs = entry_kwargs
        self._chip_value = None
        self._entry = None

        if isinstance(initial_value, dict) and "_nested_block" in initial_value:
            self._show_chip(initial_value)
        else:
            self._show_entry("" if initial_value is None else str(initial_value))

    def get(self):
        if self._chip_value is not None:
            return self._chip_value
        return self._entry.get()

    def focus_set(self):
        if self._entry is not None:
            self._entry.focus_set()
        else:
            super().focus_set()

    def _clear(self):
        for child in self.winfo_children():
            child.destroy()

    def _show_entry(self, text):
        self._clear()
        self._chip_value = None
        self._entry = tk.Entry(self, **self._entry_kwargs)
        self._entry.pack(fill=tk.X, pady=(3, 0), ipady=4)
        self._entry.insert(0, text)
        self._entry.bind("<FocusOut>", self._on_focus_out)

    def _on_focus_out(self, event=None):
        from engine.slot_match import try_match_expression
        match = try_match_expression(self._entry.get(), lang="python")
        if match:
            self._show_chip(match)

    @staticmethod
    def _preview_text(chip_value):
        p = chip_value.get("_nested_params", {})
        return f"{p.get('name', '')}({p.get('args', '')})"

    def _show_chip(self, chip_value):
        self._clear()
        self._entry = None
        self._chip_value = chip_value

        chip = tk.Frame(self, bg=DARK_BG, highlightthickness=1,
                         highlightbackground=self._header_color)
        chip.pack(fill=tk.X, pady=(3, 0))

        tk.Label(chip, text="\u25c9 Call Function", bg=DARK_BG, fg=self._header_color,
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(8, 4), pady=6)
        tk.Label(chip, text=self._preview_text(chip_value), bg=DARK_BG, fg=DARK_FG,
                 font=("Consolas", 9)).pack(side=tk.LEFT, padx=4, pady=6)

        ttk.Button(chip, text="Edit", width=5, command=self._edit_chip).pack(side=tk.RIGHT, padx=(0, 4), pady=4)
        ttk.Button(chip, text="\u21a9 Text", width=6, command=self._revert_to_text).pack(side=tk.RIGHT, padx=4, pady=4)

    def _edit_chip(self):
        """A small two-field dialog for the nested call's name/args -
        deliberately not a recursive call into edit_block_params
        itself: func_call only has two fields, so a second dialog with
        the parent's full header/description/nickname chrome would be
        far more UI than the content warrants."""
        p = dict(self._chip_value.get("_nested_params", {}))
        win = tk.Toplevel(self)
        win.title("Edit Function Call")
        win.configure(bg=DARK_PANEL)
        win.transient(self.winfo_toplevel())
        safe_grab_set(win)

        tk.Label(win, text="Function name:", bg=DARK_PANEL, fg=DARK_FG).pack(anchor="w", padx=12, pady=(12, 0))
        name_entry = tk.Entry(win, bg=DARK_BG, fg=DARK_FG, insertbackground=DARK_FG)
        name_entry.pack(fill=tk.X, padx=12)
        name_entry.insert(0, p.get("name", ""))

        tk.Label(win, text="Arguments:", bg=DARK_PANEL, fg=DARK_FG).pack(anchor="w", padx=12, pady=(8, 0))
        args_entry = tk.Entry(win, bg=DARK_BG, fg=DARK_FG, insertbackground=DARK_FG)
        args_entry.pack(fill=tk.X, padx=12)
        args_entry.insert(0, p.get("args", ""))

        def save():
            self._show_chip({
                "_nested_block": "func_call",
                "_nested_params": {"name": name_entry.get(), "args": args_entry.get()},
            })
            win.destroy()

        btns = tk.Frame(win, bg=DARK_PANEL)
        btns.pack(fill=tk.X, padx=12, pady=12)
        ttk.Button(btns, text="Save", command=save).pack(side=tk.LEFT)
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side=tk.LEFT, padx=(6, 0))
        name_entry.focus_set()

    def _revert_to_text(self):
        self._show_entry(self._preview_text(self._chip_value))
