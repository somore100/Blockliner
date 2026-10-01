"""Custom block builder and manager dialogs."""
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import re
import uuid
from block_templates import make_custom_block_generate_code, template_to_pieces
from ui_common import CATEGORY_COLORS, DARK_BG, DARK_BORDER, DARK_FG, DARK_PANEL, darken_hex, safe_grab_set


class CustomBlocksMixin:

    def manage_custom_blocks_dialog(self):
        """Dialog to view, edit, delete, and reorder custom blocks -
        scoped to the currently active language."""
        dialog = tk.Toplevel(self)
        dialog.title(f"Manage Custom Blocks - {self.current_language}")
        dialog.geometry("700x600")
        dialog.configure(bg=DARK_PANEL)
        dialog.transient(self)
        safe_grab_set(dialog)
        
        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Header
        header = tk.Frame(dialog, bg="#ff6b9d", height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text=f"\U0001F527 Custom Blocks for {self.current_language}",
            bg="#ff6b9d",
            fg="#000000",
            font=("Segoe UI", 13, "bold")
        ).pack(side=tk.LEFT, padx=20, pady=15)
        
        count_label = tk.Label(
            header,
            text="",
            bg="#ff6b9d",
            fg="#000000",
            font=("Segoe UI", 9)
        )
        count_label.pack(side=tk.RIGHT, padx=20)

        tk.Label(
            dialog,
            text="Only blocks made for this language are shown here. Switch language to manage the others.",
            bg=DARK_PANEL, fg="#888888", font=("Segoe UI", 8, "italic")
        ).pack(fill=tk.X, padx=20, pady=(8, 0))
        
        # Block list
        list_frame = tk.Frame(dialog, bg=DARK_PANEL)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        canvas = tk.Canvas(list_frame, bg=DARK_PANEL, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        blocks_container = tk.Frame(canvas, bg=DARK_PANEL)
        
        blocks_container.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=blocks_container, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def blocks_for_this_language():
            """(global_index, cblock) pairs for blocks visible in the
            current language, in their saved order."""
            return [
                (i, cblock) for i, cblock in enumerate(self.custom_blocks)
                if cblock.get("language", "all") in ("all", self.current_language)
            ]
        
        def refresh_list():
            for widget in blocks_container.winfo_children():
                widget.destroy()

            scoped = blocks_for_this_language()
            count_label.config(text=f"{len(scoped)} block{'s' if len(scoped) != 1 else ''}")
            
            if not scoped:
                tk.Label(
                    blocks_container,
                    text=f"No custom blocks yet for {self.current_language}\n\nClick 'Create New Block' to get started",
                    bg=DARK_PANEL,
                    fg="#888888",
                    font=("Segoe UI", 10),
                    justify=tk.CENTER
                ).pack(pady=50)
                return
            
            for display_pos, (i, cblock) in enumerate(scoped):
                block_frame = tk.Frame(blocks_container, bg=DARK_BG, relief=tk.RAISED, borderwidth=1)
                block_frame.pack(fill=tk.X, pady=5, padx=5)
                
                # Block info
                info_frame = tk.Frame(block_frame, bg=DARK_BG)
                info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=8)
                
                tk.Label(
                    info_frame,
                    text=cblock.get("display_name", "Unnamed"),
                    bg=DARK_BG,
                    fg=DARK_FG,
                    font=("Segoe UI", 10, "bold"),
                    anchor="w"
                ).pack(anchor="w")
                
                params_text = ", ".join([p["name"] for p in cblock.get("params", [])])
                if params_text:
                    tk.Label(
                        info_frame,
                        text=f"Parameters: {params_text}",
                        bg=DARK_BG,
                        fg="#888888",
                        font=("Segoe UI", 8),
                        anchor="w"
                    ).pack(anchor="w")
                
                # Buttons
                btn_frame = tk.Frame(block_frame, bg=DARK_BG)
                btn_frame.pack(side=tk.RIGHT, padx=10, pady=8)
                
                def make_edit(idx):
                    return lambda: self.edit_custom_block(idx, dialog, refresh_list)
                
                def make_delete(idx):
                    return lambda: self.delete_custom_block(idx, refresh_list)

                def make_move(idx, delta):
                    return lambda: self.move_custom_block(idx, delta, refresh_list)

                up_state = tk.NORMAL if display_pos > 0 else tk.DISABLED
                down_state = tk.NORMAL if display_pos < len(scoped) - 1 else tk.DISABLED

                tk.Button(
                    btn_frame, text="\u25B2", bg="#3a3a3a", fg="white",
                    font=("Segoe UI", 9), relief=tk.FLAT, cursor="hand2",
                    state=up_state, command=make_move(i, -1)
                ).pack(side=tk.LEFT, padx=2)

                tk.Button(
                    btn_frame, text="\u25BC", bg="#3a3a3a", fg="white",
                    font=("Segoe UI", 9), relief=tk.FLAT, cursor="hand2",
                    state=down_state, command=make_move(i, 1)
                ).pack(side=tk.LEFT, padx=2)
                
                tk.Button(
                    btn_frame,
                    text="✎ Edit",
                    bg="#4a9eff",
                    fg="white",
                    font=("Segoe UI", 9),
                    relief=tk.FLAT,
                    cursor="hand2",
                    command=make_edit(i)
                ).pack(side=tk.LEFT, padx=3)
                
                tk.Button(
                    btn_frame,
                    text="✕ Delete",
                    bg="#ff4757",
                    fg="white",
                    font=("Segoe UI", 9),
                    relief=tk.FLAT,
                    cursor="hand2",
                    command=make_delete(i)
                ).pack(side=tk.LEFT, padx=3)
        
        refresh_list()
        
        # Bottom buttons
        bottom_frame = tk.Frame(dialog, bg=DARK_PANEL)
        bottom_frame.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        ttk.Button(
            bottom_frame,
            text="➕ Create New Block",
            command=lambda: [dialog.destroy(), self.create_custom_block_dialog()],
            style="Toolbar.TButton"
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            bottom_frame,
            text="Close",
            command=dialog.destroy,
            style="Toolbar.TButton"
        ).pack(side=tk.RIGHT, padx=5)
    
    
    def create_custom_block_dialog(self):
        """Open the visual block builder to create a brand-new custom block."""
        self.open_block_builder_dialog()

    def edit_custom_block(self, index, parent_dialog, refresh_callback):
        """Open the visual block builder pre-filled with an existing custom block."""
        if index >= len(self.custom_blocks):
            return
        self.open_block_builder_dialog(
            existing_index=index, parent_window=parent_dialog, on_saved=refresh_callback
        )

    def open_block_builder_dialog(self, existing_index=None, parent_window=None, on_saved=None):
        """
        Scratch-style visual block builder ("Make a Block"): the block's
        shape is built up piece by piece (labels + typed inputs) with a
        live preview, instead of hand-typing a {{param}} code template.

        Shared by both create and edit so the two can never drift out of
        sync with each other - editing an existing block just pre-fills
        the same builder via template_to_pieces().
        """
        is_edit = existing_index is not None
        cblock = self.custom_blocks[existing_index] if is_edit else None

        dialog = tk.Toplevel(parent_window or self)
        dialog.title("Edit Block" if is_edit else "Make a Block")
        dialog.geometry("860x600")
        dialog.configure(bg=DARK_PANEL)
        dialog.transient(parent_window or self)
        safe_grab_set(dialog)

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        # ---- State ----
        # pieces: [{"kind": "label", "text": ...}]
        #      or [{"kind": "input", "name":, "type": "text|number|variable|boolean", "default":}]
        pieces = template_to_pieces(cblock.get("code_template", ""), cblock.get("params", [])) if is_edit else []
        selected = {"index": None}
        quote_var = tk.StringVar(value=(cblock.get("quote_char", '"') if is_edit else '"'))

        # ---- Header ----
        header_bg = "#4a9eff" if is_edit else "#ff6b9d"
        header_fg = "#ffffff" if is_edit else "#000000"
        block_lang = cblock.get("language", self.current_language) if is_edit else self.current_language
        header = tk.Frame(dialog, bg=header_bg, height=54)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header, text=("\u270E Edit Block" if is_edit else "\U0001F9E9 Make a Block"),
            bg=header_bg, fg=header_fg, font=("Segoe UI", 14, "bold")
        ).pack(side=tk.LEFT, padx=20, pady=10)
        tk.Label(
            header, text=f"for {block_lang}  -  Click a piece below to edit it, or use the buttons to build your block",
            bg=header_bg, fg=header_fg, font=("Segoe UI", 9)
        ).pack(side=tk.LEFT, padx=10)

        # ---- Live preview ----
        preview_frame = tk.Frame(dialog, bg=DARK_PANEL)
        preview_frame.pack(fill=tk.X, padx=20, pady=(15, 5))
        tk.Label(
            preview_frame, text="Preview:", bg=DARK_PANEL, fg="#888888",
            font=("Segoe UI", 9, "italic")
        ).pack(anchor="w")

        preview_canvas = tk.Canvas(
            preview_frame, height=100, bg=DARK_BG,
            highlightthickness=1, highlightbackground=DARK_BORDER
        )
        preview_canvas.pack(fill=tk.X, pady=(5, 0))

        def rounded_rect(canvas, x1, y1, x2, y2, r=10, **kwargs):
            points = [
                x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
                x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
                x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
            ]
            return canvas.create_polygon(points, smooth=True, **kwargs)

        def piece_display_text(piece):
            if piece["kind"] == "label":
                return piece["text"] or "(empty label)"
            return piece["name"] or "(unnamed)"

        def redraw_preview():
            preview_canvas.delete("all")
            font = ("Segoe UI", 12, "bold")
            y_mid = 50

            positions = []
            cx = 22
            for piece in pieces:
                text_w = max(34, len(piece_display_text(piece)) * 10 + 30)
                positions.append((cx, text_w))
                cx += text_w + 10
            total_width = max(cx + 20, 240)

            block_fill = CATEGORY_COLORS.get(category_var.get().strip(), "#ff6b9d")
            block_outline = darken_hex(block_fill)

            rounded_rect(
                preview_canvas, 10, 15, total_width, 85, r=16,
                fill=block_fill, outline=block_outline, width=2
            )
            preview_canvas.create_oval(0, 40, 20, 60, fill=block_fill, outline=block_outline, width=2)

            if not pieces:
                preview_canvas.create_text(
                    (total_width + 10) / 2, y_mid,
                    text="Add a label or input below to start building your block",
                    fill="#ffffff", font=("Segoe UI", 10, "italic")
                )
                refresh_code_preview()
                maybe_update_auto_name()
                return

            for i, (piece, (px, text_w)) in enumerate(zip(pieces, positions)):
                label_text = piece_display_text(piece)
                px1, py1, px2, py2 = px, 30, px + text_w, 70
                tag = f"piece-{i}"
                is_selected = (selected["index"] == i)

                # Invisible full-cell click-catcher, drawn first (underneath
                # the visible shape). Without this, boolean diamonds were
                # only clickable inside their inscribed polygon (much
                # smaller than the cell) and labels were only clickable on
                # the exact text glyphs - both made selecting a piece feel
                # unreliable, especially with several pieces close together.
                preview_canvas.create_rectangle(
                    px1 - 4, 15, px2 + 4, 85,
                    fill=DARK_BG, outline="", tags=(tag,)
                )

                if piece["kind"] == "label":
                    preview_canvas.create_text(
                        (px1 + px2) / 2, y_mid, text=label_text,
                        fill="#ffffff", font=font, tags=(tag,)
                    )
                    if is_selected:
                        preview_canvas.create_rectangle(
                            px1 - 4, py1, px2 + 4, py2, outline="#ffffff",
                            width=2, dash=(3, 2), tags=(tag,)
                        )
                elif piece["type"] == "boolean":
                    mx, my = (px1 + px2) / 2, y_mid
                    preview_canvas.create_polygon(
                        px1, my, mx, py1, px2, my, mx, py2,
                        fill="#5b8cff",
                        outline="#ffffff" if is_selected else "#3a5fd9",
                        width=3 if is_selected else 2,
                        tags=(tag,)
                    )
                    preview_canvas.create_text(
                        mx, my, text=label_text, fill="#ffffff",
                        font=("Segoe UI", 9, "bold"), tags=(tag,)
                    )
                elif piece["type"] == "input":
                    rounded_rect(
                        preview_canvas, px1, py1, px2, py2, r=14,
                        fill="#d4e4ff",
                        outline="#ffffff" if is_selected else "#7ea6e0",
                        width=3 if is_selected else 1,
                        tags=(tag,)
                    )
                    preview_canvas.create_text(
                        (px1 + px2) / 2, y_mid, text=label_text,
                        fill="#333333", font=("Segoe UI", 10, "bold"), tags=(tag,)
                    )
                else:
                    fill = "#fdf0d5" if piece["type"] == "variable" else "#ffffff"
                    rounded_rect(
                        preview_canvas, px1, py1, px2, py2, r=14,
                        fill=fill,
                        outline="#ffffff" if is_selected else "#c9c9c9",
                        width=3 if is_selected else 1,
                        tags=(tag,)
                    )
                    preview_canvas.create_text(
                        (px1 + px2) / 2, y_mid, text=label_text,
                        fill="#333333", font=("Segoe UI", 10, "bold"), tags=(tag,)
                    )

                preview_canvas.tag_bind(tag, "<Button-1>", lambda e, idx=i: select_piece(idx))

            refresh_code_preview()
            maybe_update_auto_name()

        def select_piece(idx):
            selected["index"] = idx
            redraw_preview()
            update_selection_label()

        def update_selection_label():
            idx = selected["index"]
            if idx is None:
                sel_label.config(text="No piece selected")
                return
            piece = pieces[idx]
            if piece["kind"] == "label":
                sel_label.config(text=f'Selected: label "{piece["text"]}"')
            else:
                sel_label.config(text=f'Selected: {piece["type"]} input "{piece["name"]}"')

        # ---- Add-piece controls ----
        add_frame = tk.Frame(dialog, bg=DARK_PANEL)
        add_frame.pack(fill=tk.X, padx=20, pady=(10, 5))

        tk.Label(
            add_frame, text="Add to block:", bg=DARK_PANEL, fg=DARK_FG,
            font=("Segoe UI", 9, "bold")
        ).pack(side=tk.LEFT, padx=(0, 10))

        def ask_input_details(title, initial_name="", initial_default=""):
            """
            One combined popup for parameter name + default value,
            instead of two separate sequential dialogs. Returns
            (name, default) - both None if the user cancelled.
            """
            result = {"name": None, "default": None}

            popup = tk.Toplevel(dialog)
            popup.title(title)
            popup.configure(bg=DARK_PANEL)
            popup.geometry("320x190")
            popup.transient(dialog)
            safe_grab_set(popup)
            popup.update_idletasks()
            popup.geometry(f"+{dialog.winfo_rootx() + 60}+{dialog.winfo_rooty() + 60}")

            tk.Label(
                popup, text="Parameter name (used in code, no spaces):",
                bg=DARK_PANEL, fg=DARK_FG, font=("Segoe UI", 9)
            ).pack(anchor="w", padx=15, pady=(15, 3))
            name_field = tk.Entry(
                popup, bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT,
                highlightthickness=1, highlightbackground=DARK_BORDER
            )
            name_field.pack(fill=tk.X, padx=15, ipady=4)
            name_field.insert(0, initial_name)

            tk.Label(
                popup, text="Default value (optional):",
                bg=DARK_PANEL, fg=DARK_FG, font=("Segoe UI", 9)
            ).pack(anchor="w", padx=15, pady=(12, 3))
            default_field = tk.Entry(
                popup, bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT,
                highlightthickness=1, highlightbackground=DARK_BORDER
            )
            default_field.pack(fill=tk.X, padx=15, ipady=4)
            default_field.insert(0, initial_default)

            def on_ok():
                result["name"] = name_field.get().strip()
                result["default"] = default_field.get()
                popup.destroy()

            def on_cancel():
                popup.destroy()

            btns = tk.Frame(popup, bg=DARK_PANEL)
            btns.pack(pady=15)
            tk.Button(
                btns, text="OK", bg="#4ec9b0", fg="#000000", relief=tk.FLAT,
                cursor="hand2", command=on_ok, padx=15
            ).pack(side=tk.LEFT, padx=5)
            tk.Button(
                btns, text="Cancel", bg="#888888", fg="white", relief=tk.FLAT,
                cursor="hand2", command=on_cancel, padx=15
            ).pack(side=tk.LEFT, padx=5)

            popup.bind("<Return>", lambda e: on_ok())
            popup.bind("<Escape>", lambda e: on_cancel())
            name_field.focus_set()
            name_field.select_range(0, tk.END)

            popup.wait_window(popup)
            return result["name"], result["default"]

        def prompt_label():
            text = simpledialog.askstring(
                "Add a Label", "Label text (shown as literal code/text):", parent=dialog
            )
            if text is None:
                return
            pieces.append({"kind": "label", "text": text})
            select_piece(len(pieces) - 1)

        def prompt_input(input_type):
            name, default = ask_input_details(f"Add {input_type.title()} Input")
            if not name:
                return
            name = name.strip().replace(" ", "_")
            pieces.append({"kind": "input", "name": name, "type": input_type, "default": default or ""})
            select_piece(len(pieces) - 1)

        def next_generic_input_name():
            existing = {p["name"] for p in pieces if p["kind"] == "input"}
            n = 1
            while f"input{n}" in existing:
                n += 1
            return f"input{n}"

        def prompt_generic_input():
            """
            Generic 'Input' piece: unlike Text/Number/Variable/Boolean,
            this skips the name+default popup entirely - it's just
            dropped straight into the block (auto-named, blank default),
            same as Scratch's plain input. Whoever USES the finished
            block later has to type something into it themselves; there's
            no default to fall back on. Rename it anytime via Edit.
            """
            pieces.append({
                "kind": "input", "name": next_generic_input_name(),
                "type": "input", "default": ""
            })
            select_piece(len(pieces) - 1)

        tk.Button(
            add_frame, text="+ Label", bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT,
            cursor="hand2", command=prompt_label
        ).pack(side=tk.LEFT, padx=3)
        tk.Button(
            add_frame, text="+ Input", bg="#3a3a3a", fg="#d4e4ff", relief=tk.FLAT,
            cursor="hand2", command=prompt_generic_input
        ).pack(side=tk.LEFT, padx=3)
        tk.Button(
            add_frame, text="+ Text Input", bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT,
            cursor="hand2", command=lambda: prompt_input("text")
        ).pack(side=tk.LEFT, padx=3)
        tk.Button(
            add_frame, text="+ Number Input", bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT,
            cursor="hand2", command=lambda: prompt_input("number")
        ).pack(side=tk.LEFT, padx=3)
        tk.Button(
            add_frame, text="+ Variable Input", bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT,
            cursor="hand2", command=lambda: prompt_input("variable")
        ).pack(side=tk.LEFT, padx=3)
        tk.Button(
            add_frame, text="+ Boolean Input", bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT,
            cursor="hand2", command=lambda: prompt_input("boolean")
        ).pack(side=tk.LEFT, padx=3)

        # ---- Selected-piece controls ----
        sel_frame = tk.Frame(dialog, bg=DARK_PANEL)
        sel_frame.pack(fill=tk.X, padx=20, pady=(5, 10))

        sel_label = tk.Label(
            sel_frame, text="No piece selected", bg=DARK_PANEL, fg="#888888",
            font=("Segoe UI", 9, "italic")
        )
        sel_label.pack(side=tk.LEFT, padx=(0, 15))

        def edit_selected():
            idx = selected["index"]
            if idx is None:
                messagebox.showinfo("Nothing selected", "Click a piece in the preview first.")
                return
            piece = pieces[idx]
            if piece["kind"] == "label":
                new_text = simpledialog.askstring(
                    "Edit Label", "Label text:", initialvalue=piece["text"], parent=dialog
                )
                if new_text is not None:
                    piece["text"] = new_text
            else:
                new_name, new_default = ask_input_details(
                    "Edit Input", initial_name=piece["name"], initial_default=piece.get("default", "")
                )
                if new_name:
                    piece["name"] = new_name.strip().replace(" ", "_")
                if new_default is not None:
                    piece["default"] = new_default
            redraw_preview()
            update_selection_label()

        def delete_selected():
            idx = selected["index"]
            if idx is None:
                return
            pieces.pop(idx)
            selected["index"] = None
            redraw_preview()
            update_selection_label()

        def move_selected(delta):
            idx = selected["index"]
            if idx is None:
                return
            new_idx = idx + delta
            if 0 <= new_idx < len(pieces):
                pieces[idx], pieces[new_idx] = pieces[new_idx], pieces[idx]
                selected["index"] = new_idx
                redraw_preview()

        tk.Button(
            sel_frame, text="\u270E Edit", bg="#569cd6", fg="#000000", relief=tk.FLAT,
            cursor="hand2", command=edit_selected
        ).pack(side=tk.LEFT, padx=3)
        tk.Button(
            sel_frame, text="\u25C0 Move Left", bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT,
            cursor="hand2", command=lambda: move_selected(-1)
        ).pack(side=tk.LEFT, padx=3)
        tk.Button(
            sel_frame, text="\u25B6 Move Right", bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT,
            cursor="hand2", command=lambda: move_selected(1)
        ).pack(side=tk.LEFT, padx=3)
        tk.Button(
            sel_frame, text="\U0001F5D1 Delete", bg="#c0392b", fg="#ffffff", relief=tk.FLAT,
            cursor="hand2", command=delete_selected
        ).pack(side=tk.LEFT, padx=3)

        # ---- Block name + quote style ----
        meta_frame = tk.Frame(dialog, bg=DARK_PANEL)
        meta_frame.pack(fill=tk.X, padx=20, pady=(5, 5))

        tk.Label(
            meta_frame, text="Block Name:", bg=DARK_PANEL, fg=DARK_FG,
            font=("Segoe UI", 9, "bold")
        ).pack(side=tk.LEFT)
        name_entry = tk.Entry(
            meta_frame, bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=DARK_BORDER, width=28
        )
        name_entry.pack(side=tk.LEFT, padx=(8, 8), ipady=3)
        name_entry.insert(0, cblock.get("display_name", "") if is_edit else "")

        tk.Label(
            meta_frame, text="(auto-filled from your first label - edit anytime)",
            bg=DARK_PANEL, fg="#888888", font=("Segoe UI", 8, "italic")
        ).pack(side=tk.LEFT, padx=(0, 17))

        # Auto-naming: suggest a name from the first label piece (e.g. a
        # "print(" label suggests "print"), but only while the user
        # hasn't typed their own name over it, and never in edit mode
        # (an existing block already has a real name, don't touch it).
        last_auto_name = {"value": None if is_edit else ""}

        def suggest_block_name():
            if not pieces or pieces[0]["kind"] != "label":
                return ""
            text = pieces[0]["text"]
            m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)", text)
            if m:
                return m.group(1)
            return re.sub(r"[^A-Za-z0-9_ ]", "", text).strip()

        def maybe_update_auto_name():
            if last_auto_name["value"] is None:
                return
            if name_entry.get() != last_auto_name["value"]:
                return  # user has typed their own name - don't overwrite it
            suggestion = suggest_block_name()
            name_entry.delete(0, tk.END)
            name_entry.insert(0, suggestion)
            last_auto_name["value"] = suggestion

        tk.Label(
            meta_frame, text="String quotes:", bg=DARK_PANEL, fg=DARK_FG,
            font=("Segoe UI", 9, "bold")
        ).pack(side=tk.LEFT)
        tk.Radiobutton(
            meta_frame, text='"double"', variable=quote_var, value='"',
            bg=DARK_PANEL, fg=DARK_FG, selectcolor=DARK_BG,
            activebackground=DARK_PANEL, activeforeground=DARK_FG
        ).pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(
            meta_frame, text="'single'", variable=quote_var, value="'",
            bg=DARK_PANEL, fg=DARK_FG, selectcolor=DARK_BG,
            activebackground=DARK_PANEL, activeforeground=DARK_FG
        ).pack(side=tk.LEFT, padx=5)
        tk.Label(
            meta_frame, text="(applied automatically to Text inputs - no need to type quotes yourself)",
            bg=DARK_PANEL, fg="#888888", font=("Segoe UI", 8, "italic")
        ).pack(side=tk.LEFT, padx=10)

        # ---- Category (which palette section this block lives in) ----
        category_frame = tk.Frame(dialog, bg=DARK_PANEL)
        category_frame.pack(fill=tk.X, padx=20, pady=(0, 5))

        tk.Label(
            category_frame, text="Category:", bg=DARK_PANEL, fg=DARK_FG,
            font=("Segoe UI", 9, "bold")
        ).pack(side=tk.LEFT)

        category_var = tk.StringVar(
            value=cblock.get("category", "Custom Blocks") if is_edit else "Custom Blocks"
        )
        category_combo = ttk.Combobox(
            category_frame, textvariable=category_var,
            values=sorted(CATEGORY_COLORS.keys()), width=22
        )
        category_combo.pack(side=tk.LEFT, padx=(8, 10))

        tk.Label(
            category_frame,
            text="Pick an existing category (block joins it and takes its color), or type a new one.",
            bg=DARK_PANEL, fg="#888888", font=("Segoe UI", 8, "italic")
        ).pack(side=tk.LEFT)

        def on_category_change(*_args):
            redraw_preview()

        category_var.trace_add("write", on_category_change)

        # ---- Generated code preview (read-only) ----
        code_preview_frame = tk.LabelFrame(
            dialog, text="Generated code (using your default values)", bg=DARK_PANEL,
            fg="#569cd6", font=("Segoe UI", 9, "bold"), labelanchor="n"
        )
        code_preview_frame.pack(fill=tk.X, padx=20, pady=(5, 10))
        code_preview_label = tk.Label(
            code_preview_frame, text="", bg=DARK_BG, fg="#4ec9b0",
            font=("Consolas", 10), justify=tk.LEFT, anchor="w", padx=10, pady=8
        )
        code_preview_label.pack(fill=tk.X, padx=8, pady=8)

        def build_template_and_params():
            template_parts = []
            params_list = []
            for piece in pieces:
                if piece["kind"] == "label":
                    template_parts.append(piece["text"])
                else:
                    template_parts.append("{{" + piece["name"] + "}}")
                    params_list.append({
                        "name": piece["name"],
                        "type": piece["type"],
                        "default": piece.get("default", "")
                    })
            return "".join(template_parts), params_list

        def refresh_code_preview():
            template, params_list = build_template_and_params()
            if not template:
                code_preview_label.config(text="(add pieces above to see generated code)")
                return
            sample_params = {p["name"]: (p["default"] or f"<{p['name']}>") for p in params_list}
            gen = make_custom_block_generate_code(template, params_list, quote_var.get())
            try:
                code_preview_label.config(text=gen(sample_params).rstrip("\n"))
            except Exception as e:
                code_preview_label.config(text=f"(preview error: {e})")

        quote_var.trace_add("write", lambda *a: refresh_code_preview())

        # ---- Save / Cancel ----
        btn_frame = tk.Frame(dialog, bg=DARK_PANEL)
        btn_frame.pack(fill=tk.X, padx=20, pady=(0, 20))

        def on_save():
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror("Oops!", "Please give your block a name!")
                return
            if not pieces:
                messagebox.showerror("Oops!", "Add at least one label or input to your block!")
                return

            template, params_list = build_template_and_params()
            chosen_category = category_var.get().strip() or "Custom Blocks"

            if chosen_category not in CATEGORY_COLORS:
                CATEGORY_COLORS[chosen_category] = "#ff6b9d"
                self.settings.setdefault("category_colors", {})[chosen_category] = "#ff6b9d"
                self.save_app_settings()
            if chosen_category not in self.category_order:
                self.category_order.append(chosen_category)
                self.settings["category_order"] = self.category_order
                self.save_app_settings()

            block_data = {
                "block_id": cblock["block_id"] if is_edit else "custom_" + str(uuid.uuid4())[:8],
                "display_name": name,
                "category": chosen_category,
                "params": params_list,
                "code_template": template,
                "quote_char": quote_var.get(),
                "language": cblock.get("language", self.current_language) if is_edit else self.current_language
            }

            if is_edit:
                self.custom_blocks[existing_index] = block_data
            else:
                self.custom_blocks.append(block_data)

            self.save_custom_blocks_data(self.custom_blocks)

            # Full reload keeps self.blocks / self.blocks_by_category free
            # of stale duplicate entries - matters especially on edit.
            self.load_blocks_for_language(self.current_language)
            self.load_and_merge_custom_blocks()
            self.refresh_palette()

            if on_saved:
                on_saved()

            verb = "updated" if is_edit else "created"
            extra = "" if is_edit else "\n\nFind it in the 'Custom Blocks' category."
            self.maybe_notify("Success!", f"Custom block '{name}' {verb}!{extra}")
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        tk.Button(
            btn_frame,
            text=("\u2713 Save Changes" if is_edit else "\u2713 Create My Block!"),
            bg="#4ec9b0", fg="#000000", font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT, cursor="hand2", command=on_save, padx=20, pady=8
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_frame, text="\u2715 Cancel", bg="#888888", fg="white",
            font=("Segoe UI", 10), relief=tk.FLAT, cursor="hand2",
            command=on_cancel, padx=15, pady=8
        ).pack(side=tk.LEFT, padx=5)

        dialog.bind("<Escape>", lambda e: on_cancel())
        redraw_preview()

    def delete_custom_block(self, index, refresh_callback):
        """Delete a custom block"""
        if index >= len(self.custom_blocks):
            return
        
        cblock = self.custom_blocks[index]
        block_name = cblock.get("display_name", "Unnamed")
        block_id = cblock.get("block_id")

        used_count = sum(1 for bid, _ in self.project_blocks if bid == block_id)

        warning = f"Delete custom block '{block_name}'?\n\nThis cannot be undone."
        if used_count:
            warning += (
                f"\n\nIt's currently used {used_count} time"
                f"{'s' if used_count != 1 else ''} in your workspace - "
                f"deleting it will also remove those instance{'s' if used_count != 1 else ''}, "
                f"since the code pad can't generate code for a block that no longer exists."
            )

        proceed = True
        if self.settings.get("confirm_delete", True) or used_count:
            proceed = messagebox.askyesno("Delete Block", warning)

        if proceed:
            self.custom_blocks.pop(index)
            self.save_custom_blocks_data(self.custom_blocks)

            # Remove any now-dangling instances from the workspace too -
            # otherwise the code pad shows "Block '...' not found" for
            # every instance still referencing the deleted definition.
            if used_count:
                self.set_project_blocks([
                    (bid, params) for bid, params in self.project_blocks if bid != block_id
                ])
                self.refresh_workspace()
            
            # Reload blocks
            self.load_blocks_for_language(self.current_language)
            self.load_and_merge_custom_blocks()
            self.refresh_palette()
            
            refresh_callback()
            self.maybe_notify("Deleted", f"Block '{block_name}' deleted.")

    def move_custom_block(self, index, delta, refresh_callback):
        """
        Move a custom block up/down relative to other blocks of the
        SAME language, skipping over any other-language blocks that
        happen to sit between them in the underlying saved list.
        """
        if not (0 <= index < len(self.custom_blocks)):
            return

        lang = self.custom_blocks[index].get("language", "all")
        step = 1 if delta > 0 else -1
        j = index + step

        while 0 <= j < len(self.custom_blocks):
            neighbor_lang = self.custom_blocks[j].get("language", "all")
            if neighbor_lang in ("all", lang) or lang == "all":
                self.custom_blocks[index], self.custom_blocks[j] = \
                    self.custom_blocks[j], self.custom_blocks[index]
                self.save_custom_blocks_data(self.custom_blocks)
                refresh_callback()
                return
            j += step
