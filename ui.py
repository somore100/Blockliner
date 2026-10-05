"""Blockliner main window. The heavy lifting lives in the ui_* mixin modules;
this file keeps window construction (__init__, create_widgets, theme) and start_ui()."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog, colorchooser  # noqa: F401 (re-exported: tests patch ui.messagebox etc.)
import os
import time
from PIL import Image
from PIL import ImageTk
from panels import PanelManager
from scroll_modes import SNAP_THROTTLE_S, next_snap, normalize_mode, snap_points
from panels import PanelSpec
from block_templates import make_raw_code_block_source
from nodes_model import default_active_node_id, find_node_by_id
from ui_common import APP_VERSION, BLOCK_SELECTED, BUILD_NUMBER, CATEGORY_COLORS, DARK_ACCENT, DARK_BG, DARK_BORDER, DARK_FG, DARK_HOVER, DARK_PANEL, PRESET_LANGUAGES
from ui_tabs import TabsMixin
from ui_import import ImportMixin
from ui_palette import PaletteMixin
from ui_custom_blocks import CustomBlocksMixin
from ui_blockedit import BlockEditMixin
from ui_layers import LayersMixin
from ui_nodeops import NodeOpsMixin
from ui_menus import MenusMixin
from ui_canvas import CanvasMixin
from ui_codegen import CodegenMixin
from ui_codesync import CodeSyncMixin
# Re-exported so `ui.<name>` keeps working for tests and old imports.
from nodes_model import *  # noqa: F401,F403
from block_templates import *  # noqa: F401,F403
from ui_common import *  # noqa: F401,F403
from ui_widgets import *  # noqa: F401,F403


class BlocklinerUI(TabsMixin, ImportMixin, PaletteMixin, CustomBlocksMixin, BlockEditMixin, LayersMixin, NodeOpsMixin, MenusMixin, CanvasMixin, CodegenMixin, CodeSyncMixin, tk.Tk):
    def __init__(self, initial_lang="python", languages_path="languages"):
        super().__init__()
        self.title("Blockliner - Visual Code Builder")
        self.geometry("1400x800")
        self.configure(bg=DARK_BG)
        
        self.languages_path = languages_path
        self.settings = self.load_app_settings()
        self._scroll_clock = time.monotonic   # tests swap this to step time
        self._rigid_last = {}

        # A settings.default_language only overrides the caller's choice
        # if the caller left it at the plain default ("python") - an
        # explicit initial_lang argument (e.g. a resumed session) still wins.
        available_langs_at_start = self.get_available_languages()
        if initial_lang == "python" and self.settings.get("default_language") in available_langs_at_start:
            initial_lang = self.settings["default_language"]

        self.current_language = initial_lang
        self.blocks = {}
        self.project_blocks = []
        self.blocks_by_category = {}
        self.custom_blocks = []
        self.view_mode = "node"  # "files", "file", or "node" - see refresh_workspace
        # Files-layer "View Code" toggle - swaps the files-as-boxes
        # canvas for a stacked, read-only concatenation of every open
        # tab's code (one Text widget per file). Reset to False on
        # entering the Files layer so it never persists confusingly
        # across an unrelated navigation.
        self.files_view_code_mode = False
        # Nodes-layer "View Code" toggle (same idea, one level down) -
        # swaps the current file's node/wire canvas for a single
        # read-only Text widget of that file's generated code. Also
        # reset to False on entering the Nodes layer.
        self.file_view_code_mode = False
        # Phase C2: freeform file-view canvas state. Populated fresh by
        # render_file_view() every time it runs - node_id -> (canvas
        # window item id, box Frame widget) - and consulted by
        # draw_wires()/dragging while that view is on screen.
        self._fileview_boxes = {}
        self._fileview_selected_wire = None
        # Files-layer: same shape as _fileview_boxes but keyed by tab
        # index - int, not id, since tabs have no stable id today (only
        # a position in self.tabs). Populated fresh by
        # render_files_view() every time it runs.
        self._filesview_boxes = {}
        # Phase C3: manual wire-drag state. None when no drag is in
        # progress; while dragging, holds the source node id so
        # _port_motion/_port_release know what's being wired.
        self._wire_drag_source = None
        self._wire_drag_temp_id = None
        self._wire_drag_hover_id = None

        # Multi-tab support: each tab holds its own language and its own
        # node list, fully independent and all kept in memory at once -
        # switching tabs just repoints self.project_blocks/current_language
        # at a different tab's active node and refreshes the view.
        # Phase B1: every tab has exactly one node ("main") for now for
        # languages with no required entry point. Phase B3 auto-creates
        # a locked entry-point node (and, for C#/Java, a wrapping class
        # node) instead, where the language requires one.
        initial_nodes = self.build_initial_nodes_for_language(self.current_language)
        self.project_blocks = find_node_by_id(initial_nodes, default_active_node_id(initial_nodes))["blocks"]
        self.tabs = [{
            "title": "Untitled 1",
            "language": self.current_language,
            "nodes": initial_nodes,
            "active_node_id": default_active_node_id(initial_nodes),
            "filepath": None,
            "dirty": False,
        }]
        self.active_tab_index = 0
        self._next_untitled_number = 2

        # Category colors/order are mutated in place so every widget that
        # already reads CATEGORY_COLORS picks up changes automatically.
        CATEGORY_COLORS.update(self.settings.get("category_colors", {}))
        self.category_order = list(self.settings.get("category_order", [])) or list(CATEGORY_COLORS.keys())
        
        # Create languages folder structure if it doesn't exist. Only
        # touches languages that don't exist yet, so it never overwrites
        # anything you've already built out (including python/cpp's real
        # block sets).
        for lang in PRESET_LANGUAGES:
            lang_blocks_path = os.path.join(languages_path, lang, "blocks")
            if not os.path.isdir(lang_blocks_path):
                os.makedirs(lang_blocks_path, exist_ok=True)
                raw_code_path = os.path.join(lang_blocks_path, "raw_code.py")
                if not os.path.exists(raw_code_path):
                    with open(raw_code_path, "w") as f:
                        f.write(make_raw_code_block_source(lang))
        
        self.load_blocks_for_language(self.current_language)
        self.load_and_merge_custom_blocks()
        self.create_widgets()
        self.refresh_tab_bar()
        self.update_generated_code()
    
    def _on_mousewheel(self, event, canvas):
        """
        Handle mousewheel scrolling across Windows, macOS, and Linux.

        Windows/macOS send a <MouseWheel> event with event.delta (Windows:
        multiples of 120, macOS: small values like +-1). Linux (X11) sends
        no <MouseWheel> event at all - it sends <Button-4> (scroll up) and
        <Button-5> (scroll down) instead, so without handling event.num
        the scroll wheel silently does nothing on Linux, which is what
        was happening here.
        """
        if event.num == 4:
            step = -1
        elif event.num == 5:
            step = 1
        elif event.delta:
            step = -1 if event.delta > 0 else 1
        else:
            return
        if normalize_mode(self.settings.get("scroll_mode", "smooth")) == "rigid":
            self._rigid_scroll(canvas, step)
        else:
            canvas.yview_scroll(step, "units")

    def _snap_targets(self, canvas):
        """Top y (canvas coordinates) of every item rigid mode can snap to:
        palette headers/blocks, the blocks of the open node, or the node/file
        boxes on the canvas layers."""
        if canvas is self.palette_canvas:
            return [w.winfo_y() for w in self.palette_frame.winfo_children() if w.winfo_ismapped()]
        if getattr(self, "view_mode", None) == "node":
            return [w.winfo_y() for w in self.workspace_frame.winfo_children() if w.winfo_ismapped()]
        tops = []
        for item in canvas.find_all():
            if canvas.type(item) == "window" and item != getattr(self, "workspace_frame_window_id", None):
                box = canvas.bbox(item)
                if box:
                    tops.append(box[1])
        return tops

    def _rigid_scroll(self, canvas, step):
        """Snap `canvas` one item up/down (step < 0 / > 0). Throttled."""
        now = self._scroll_clock()
        last = self._rigid_last.get(str(canvas), -1e9)
        if now - last < SNAP_THROTTLE_S:
            return
        self._rigid_last[str(canvas)] = now
        box = canvas.bbox("all")
        region = str(canvas.cget("scrollregion")).split()
        top, bottom = (float(region[1]), float(region[3])) if len(region) == 4 else (box[1], box[3]) if box else (0.0, 0.0)
        if bottom - top <= 0:
            return
        current = top + canvas.yview()[0] * (bottom - top)   # (canvasy(0) is off by the border inset)
        target = next_snap(snap_points(self._snap_targets(canvas), top), current, step)
        if target is None:
            return
        canvas.yview_moveto((target - top) / (bottom - top))
    
    def create_widgets(self):
        # Top toolbar
        toolbar = tk.Frame(self, bg=DARK_PANEL, height=50)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        toolbar.pack_propagate(False)
        
        # Logo and branding
        logo_frame = tk.Frame(toolbar, bg=DARK_PANEL)
        logo_frame.pack(side=tk.LEFT, padx=15)
        
        # Try to load logo
        try:
            logo_path = "logo.png"  # Assumes logo.png is in the same folder as main.py
            if os.path.exists(logo_path):
                logo_img = Image.open(logo_path)
                logo_img = logo_img.resize((32, 32), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(logo_img)
                tk.Label(
                    logo_frame,
                    image=self.logo_photo,
                    bg=DARK_PANEL
                ).pack(side=tk.LEFT, padx=(0, 8))
        except Exception as e:
            print(f"Could not load logo: {e}")
        
        tk.Label(
            logo_frame,
            text="⬢ Blockliner",
            bg=DARK_PANEL,
            fg=DARK_ACCENT,
            font=("Segoe UI", 16, "bold")
        ).pack(side=tk.LEFT)
        
        tk.Label(
            logo_frame,
            text="by domore100",
            bg=DARK_PANEL,
            fg="#888888",
            font=("Segoe UI", 8, "italic")
        ).pack(side=tk.LEFT, padx=(5, 0))
        
        # Toolbar buttons
        btn_style = {"style": "Toolbar.TButton"}
        
        ttk.Button(toolbar, text="💾 Save", command=self.save_project, **btn_style).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="📂 Load", command=self.load_project, **btn_style).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="\U0001F4C4 Open Code File", command=lambda: self.open_code_to_blocks_dialog(prefill_from_file=True), **btn_style).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="📤 Export", command=self.export_code, **btn_style).pack(side=tk.LEFT, padx=3)
        
        tk.Frame(toolbar, bg=DARK_BORDER, width=2).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=8)
        
        ttk.Button(toolbar, text="🔧 Manage Custom Blocks", command=self.manage_custom_blocks_dialog, **btn_style).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="\u2699 Settings", command=self.settings_dialog, **btn_style).pack(side=tk.LEFT, padx=3)
        
        tk.Frame(toolbar, bg=DARK_BORDER, width=2).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=8)
        
        # Run button with dropdown
        run_frame = tk.Frame(toolbar, bg=DARK_PANEL)
        run_frame.pack(side=tk.LEFT, padx=3)
        
        run_btn = ttk.Button(run_frame, text="▶ Run", command=self.run_code, **btn_style)
        run_btn.pack(side=tk.LEFT)
        
        # Dropdown for run options
        run_menu_btn = tk.Label(
            run_frame,
            text="▼",
            bg=DARK_PANEL,
            fg=DARK_FG,
            font=("Segoe UI", 8),
            cursor="hand2"
        )
        run_menu_btn.pack(side=tk.LEFT, padx=(2, 0))
        
        def show_run_menu(event):
            menu = tk.Menu(self, tearoff=0, bg=DARK_PANEL, fg=DARK_FG, activebackground=DARK_HOVER)
            menu.add_command(label="▶ Run in Blockliner", command=self.run_code)
            menu.add_command(label="🖥️ Run in Terminal", command=self.run_in_terminal)
            menu.add_command(label="📝 Open in VS Code", command=self.open_in_vscode)
            menu.add_separator()
            menu.add_command(label="💾 Export & Run...", command=self.export_and_run)
            menu.post(event.x_root, event.y_root)
        
        run_menu_btn.bind("<Button-1>", show_run_menu)
        
        ttk.Button(toolbar, text="🗑 Clear", command=self.clear_all, **btn_style).pack(side=tk.LEFT, padx=3)
        
        # Tab bar (VS Code style) - each tab is a fully independent
        # project, kept in memory, switchable instantly.
        self.tab_bar_frame = tk.Frame(self, bg=DARK_PANEL, height=34)
        self.tab_bar_frame.pack(side=tk.TOP, fill=tk.X)
        self.tab_bar_frame.pack_propagate(False)

        # Always-visible layer selector (Files | Nodes | Blocks | Code).
        # Lives in the tab bar row but is never destroyed by
        # refresh_tab_bar, so it can be restyled cheaply on every
        # workspace refresh (see refresh_layer_bar).
        self.layer_bar = tk.Frame(self.tab_bar_frame, bg=DARK_PANEL)
        self.layer_bar.pack(side=tk.RIGHT, padx=(0, 6), pady=3)
        self._layer_buttons = {}
        for key, text in (("files", "\U0001F4C1 Files"), ("nodes", "\U0001F5C2 Nodes"),
                          ("blocks", "\U0001F9E9 Blocks"), ("code", "\U0001F4C4 Code")):
            b = tk.Button(
                self.layer_bar, text=text, relief=tk.FLAT, cursor="hand2",
                font=("Segoe UI", 9), padx=10, bd=0,
                command=lambda k=key: self.goto_layer(k))
            b.pack(side=tk.LEFT, padx=(0 if key == "files" else 1, 0), fill=tk.Y)
            self._layer_buttons[key] = b
        self._layer_key_seqs = []
        self.apply_keybinds()

        # Main container - hosts the PanelManager (panels.py), which owns
        # where the palette / workspace / generated-code panels live.
        # Each area below registers itself and builds into its frame.
        main_container = tk.Frame(self, bg=DARK_BG)
        main_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
        # Edge strip for the left palette: lives OUTSIDE the paned window
        # so it stays put while the palette itself is hidden. Its glyph
        # follows the palette's state via the manager's listener hook.
        self.palette_strip = tk.Frame(main_container, bg=DARK_PANEL, width=16,
                                      cursor="hand2")
        self.palette_strip.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 3))
        self.palette_strip.pack_propagate(False)
        self.palette_strip_glyph = tk.Label(
            self.palette_strip, text="\u25c2", bg=DARK_PANEL, fg="#888888",
            font=("Segoe UI", 10), cursor="hand2")
        self.palette_strip_glyph.pack(pady=(10, 0))
        for w in (self.palette_strip, self.palette_strip_glyph):
            w.bind("<Button-1>", lambda e: self.toggle_palette())
            w.bind("<Enter>", lambda e: self._palette_strip_hover(True))
            w.bind("<Leave>", lambda e: self._palette_strip_hover(False))

        # Right edge strip: mirrors the left one for the Generated Code
        # panel (Blocks layer only - see update_right_panel_visibility).
        # Deliberately a general "edge bar": when panels are hidden it is
        # where their icons live, and where future extensions can add theirs.
        self.code_strip = tk.Frame(main_container, bg=DARK_PANEL, width=16,
                                   cursor="hand2")
        self.code_strip.pack_propagate(False)
        self.code_strip_glyph = tk.Label(
            self.code_strip, text="\u25b8", bg=DARK_PANEL, fg="#888888",
            font=("Segoe UI", 10), cursor="hand2")
        self.code_strip_glyph.pack(pady=(10, 0))
        for w in (self.code_strip, self.code_strip_glyph):
            w.bind("<Button-1>", lambda e: self.toggle_code_panel())
            w.bind("<Enter>", lambda e: self._code_strip_hover(True))
            w.bind("<Leave>", lambda e: self._code_strip_hover(False))
        self._code_strip_shown = False

        self.panels = PanelManager(main_container, bg=DARK_BG)
        self.panels.paned.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.panels.add_listener(self._on_panel_visibility_changed)
        
        # Left panel: Block Palette
        left_panel = self.panels.create_panel(
            PanelSpec("palette", "Blocks", dock="left", width=280, min_width=180),
            bg=DARK_PANEL)
        
        palette_header = tk.Frame(left_panel, bg=DARK_PANEL, height=50)
        palette_header.pack(fill=tk.X)
        palette_header.pack_propagate(False)
        
        tk.Label(
            palette_header,
            text="📦 Block Palette",
            bg=DARK_PANEL,
            fg=DARK_FG,
            font=("Segoe UI", 11, "bold")
        ).pack(pady=5)
        
        tk.Label(
            palette_header,
            text="Click or drag to add \u2192",
            bg=DARK_PANEL,
            fg="#888888",
            font=("Segoe UI", 8, "italic")
        ).pack()
        
        # Search box
        search_frame = tk.Frame(left_panel, bg=DARK_PANEL)
        search_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', self.filter_palette)
        
        search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            bg=DARK_BG,
            fg=DARK_FG,
            font=("Segoe UI", 9),
            insertbackground=DARK_FG
        )
        search_entry.pack(fill=tk.X, ipady=3)
        
        tk.Label(
            search_frame,
            text="🔍 Search blocks...",
            bg=DARK_PANEL,
            fg="#555555",
            font=("Segoe UI", 8)
        ).pack(anchor="w", pady=(2, 0))
        
        # Scrollable palette - FIXED
        self.palette_canvas = tk.Canvas(left_panel, bg=DARK_PANEL, highlightthickness=0)
        palette_scrollbar = ttk.Scrollbar(left_panel, orient="vertical", command=self.palette_canvas.yview)
        self.palette_frame = tk.Frame(self.palette_canvas, bg=DARK_PANEL)
        
        self.palette_frame.bind(
            "<Configure>",
            lambda e: self.palette_canvas.configure(scrollregion=self.palette_canvas.bbox("all"))
        )
        
        self.palette_canvas.create_window((0, 0), window=self.palette_frame, anchor="nw", width=260)
        self.palette_canvas.configure(yscrollcommand=palette_scrollbar.set)
        
        # Bind mousewheel ONLY to palette canvas
        def _bind_palette_scroll(e):
            self.palette_canvas.bind_all("<MouseWheel>", lambda ev: self._on_mousewheel(ev, self.palette_canvas))
            self.palette_canvas.bind_all("<Button-4>", lambda ev: self._on_mousewheel(ev, self.palette_canvas))
            self.palette_canvas.bind_all("<Button-5>", lambda ev: self._on_mousewheel(ev, self.palette_canvas))

        def _unbind_palette_scroll(e):
            self.palette_canvas.unbind_all("<MouseWheel>")
            self.palette_canvas.unbind_all("<Button-4>")
            self.palette_canvas.unbind_all("<Button-5>")

        self.palette_canvas.bind("<Enter>", _bind_palette_scroll)
        self.palette_canvas.bind("<Leave>", _unbind_palette_scroll)
        
        self.palette_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        palette_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Build palette
        self.build_palette()
        
        # Middle panel: Workspace
        middle_panel = self.panels.create_panel(
            PanelSpec("workspace", "Workspace", dock="center", width=400,
                      min_width=200, stretch=True),
            bg=DARK_BG)
        
        workspace_header = tk.Frame(middle_panel, bg=DARK_BG, height=50)
        workspace_header.pack(fill=tk.X)
        workspace_header.pack_propagate(False)
        
        tk.Label(
            workspace_header,
            text="🎨 Workspace",
            bg=DARK_BG,
            fg=DARK_FG,
            font=("Segoe UI", 11, "bold")
        ).pack(side=tk.LEFT, padx=10, pady=5)
        
        self.block_count_label = tk.Label(
            workspace_header,
            text="0 blocks",
            bg=DARK_BG,
            fg="#888888",
            font=("Segoe UI", 9)
        )
        self.block_count_label.pack(side=tk.LEFT, padx=5)

        # Phase B2: node navigation controls (breadcrumb + Nodes/New Node
        # buttons), rebuilt each refresh the same way refresh_tab_bar()
        # rebuilds the tab strip - see refresh_node_nav().
        self.node_nav_frame = tk.Frame(workspace_header, bg=DARK_BG)
        self.node_nav_frame.pack(side=tk.RIGHT, padx=10)
        
        # Workspace canvas - FIXED
        self.workspace_canvas = tk.Canvas(middle_panel, bg=DARK_BG, highlightthickness=1, highlightbackground=DARK_BORDER)
        workspace_scrollbar = ttk.Scrollbar(middle_panel, orient="vertical", command=self.workspace_canvas.yview)
        self.workspace_scrollbar = workspace_scrollbar
        self.workspace_frame = tk.Frame(self.workspace_canvas, bg=DARK_BG)
        
        self.workspace_frame.bind(
            "<Configure>",
            lambda e: self.workspace_canvas.configure(scrollregion=self.workspace_canvas.bbox("all"))
        )
        
        self.workspace_frame_window_id = self.workspace_canvas.create_window(
            (0, 0), window=self.workspace_frame, anchor="nw", width=600
        )
        self.workspace_canvas.configure(yscrollcommand=self._on_workspace_yscroll)
        
        # Bind mousewheel ONLY to workspace canvas
        def _bind_workspace_scroll(e):
            self.workspace_canvas.bind_all("<MouseWheel>", lambda ev: self._on_mousewheel(ev, self.workspace_canvas))
            self.workspace_canvas.bind_all("<Button-4>", lambda ev: self._on_mousewheel(ev, self.workspace_canvas))
            self.workspace_canvas.bind_all("<Button-5>", lambda ev: self._on_mousewheel(ev, self.workspace_canvas))

        def _unbind_workspace_scroll(e):
            self.workspace_canvas.unbind_all("<MouseWheel>")
            self.workspace_canvas.unbind_all("<Button-4>")
            self.workspace_canvas.unbind_all("<Button-5>")

        self.workspace_canvas.bind("<Enter>", _bind_workspace_scroll)
        self.workspace_canvas.bind("<Leave>", _unbind_workspace_scroll)
        
        self.workspace_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        workspace_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._bind_workspace_context_menu()
        
        # Empty state
        self.show_empty_state()
        
        # Right panel: Code Preview
        self.right_panel = right_panel = self.panels.create_panel(
            PanelSpec("code", "Generated Code", dock="right", width=400, min_width=250),
            bg=DARK_PANEL)
        self._sync_code_strip()
        
        code_header = tk.Frame(right_panel, bg=DARK_PANEL, height=50)
        code_header.pack(fill=tk.X)
        code_header.pack_propagate(False)
        
        tk.Label(
            code_header,
            text="📝 Generated Code",
            bg=DARK_PANEL,
            fg=DARK_FG,
            font=("Segoe UI", 11, "bold")
        ).pack(pady=5)
        
        # Language selector with Add Language button
        lang_frame = tk.Frame(right_panel, bg=DARK_PANEL)
        lang_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(
            lang_frame,
            text="Language:",
            bg=DARK_PANEL,
            fg=DARK_FG,
            font=("Segoe UI", 9)
        ).pack(side=tk.LEFT, padx=5)
        
        # Get available languages
        available_langs = self.get_available_languages()
        
        self.lang_var = tk.StringVar(value=self.current_language)
        self.lang_combo = ttk.Combobox(
            lang_frame,
            textvariable=self.lang_var,
            values=available_langs,
            state="readonly",
            width=10
        )
        self.lang_combo.pack(side=tk.LEFT, padx=5)
        self.lang_combo.bind("<<ComboboxSelected>>", self.on_language_change)
        
        # Add Language button
        ttk.Button(
            lang_frame,
            text="+ Lang",
            command=self.add_language_dialog,
            style="Toolbar.TButton"
        ).pack(side=tk.LEFT, padx=2)

        # Delete Language button
        ttk.Button(
            lang_frame,
            text="\U0001F5D1 Lang",
            command=self.delete_language_dialog,
            style="Toolbar.TButton"
        ).pack(side=tk.LEFT, padx=2)

        # Refresh Languages button - re-scans languages/ from disk, so a
        # folder added or removed by hand (outside the app) is picked up
        # without needing a restart.
        ttk.Button(
            lang_frame,
            text="\U0001F504",
            command=self.refresh_language_list,
            style="Toolbar.TButton",
            width=3
        ).pack(side=tk.LEFT, padx=2)
        
        self.line_count_label = tk.Label(
            lang_frame,
            text="0 lines",
            bg=DARK_PANEL,
            fg="#888888",
            font=("Segoe UI", 8)
        )
        self.line_count_label.pack(side=tk.RIGHT, padx=5)
        
        # Code display
        self.code_text = tk.Text(
            right_panel,
            bg="#1e1e1e",
            fg=DARK_FG,
            font=("Consolas", 9),
            insertbackground=DARK_FG,
            selectbackground=BLOCK_SELECTED,
            relief=tk.FLAT,
            padx=12,
            pady=12,
            wrap=tk.NONE
        )
        self.code_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.install_code_guard()
        self.build_code_options_row(code_header_row=lang_frame)
        self.install_code_sync()
        
        # Apply dark theme
        self.apply_theme()
        
        # Footer with credits
        footer = tk.Frame(self, bg=DARK_PANEL, height=25)
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        footer.pack_propagate(False)
        
        tk.Label(
            footer,
            text="Made with ❤️ by domore100  |  Blockliner Visual Code Builder",
            bg=DARK_PANEL,
            fg="#666666",
            font=("Segoe UI", 8)
        ).pack(side=tk.LEFT, padx=15, pady=5)
        
        version_label = tk.Label(
            footer,
            text=f"v{APP_VERSION}  \u00b7  #build {BUILD_NUMBER}",
            bg=DARK_PANEL,
            fg="#444444",
            font=("Segoe UI", 7)
        )
        version_label.pack(side=tk.RIGHT, padx=15, pady=5)
    
    def apply_theme(self):
        """Apply dark theme to ttk widgets"""
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure("Toolbar.TButton",
                       background=DARK_PANEL,
                       foreground=DARK_FG,
                       borderwidth=1,
                       focuscolor=DARK_ACCENT,
                       padding=8)
        style.map("Toolbar.TButton",
                 background=[('active', DARK_HOVER), ('pressed', DARK_ACCENT)])

        # Dialog confirm/cancel buttons: deliberately distinct from
        # Toolbar.TButton (and from each other) and deliberately NOT
        # relying on unicode glyphs (checkmark/cross) for meaning -
        # those glyphs silently failed to render as visible marks on
        # some system fonts, leaving two identical-looking blank
        # buttons with no way to tell save from cancel. Plain text +
        # a strong color difference + explicit font/padding fixes both
        # the "too small" and "which one is yes" complaints at once.
        style.configure("DialogPrimary.TButton",
                       background=DARK_ACCENT,
                       foreground="#ffffff",
                       borderwidth=0,
                       focuscolor=DARK_ACCENT,
                       font=("Segoe UI", 10, "bold"),
                       padding=(18, 10))
        style.map("DialogPrimary.TButton",
                 background=[('active', "#1a8cd8"), ('pressed', "#005a9e")])

        style.configure("DialogSecondary.TButton",
                       background=DARK_PANEL,
                       foreground=DARK_FG,
                       borderwidth=1,
                       relief="solid",
                       focuscolor=DARK_BORDER,
                       font=("Segoe UI", 10),
                       padding=(18, 10))
        style.map("DialogSecondary.TButton",
                 background=[('active', DARK_HOVER), ('pressed', DARK_HOVER)],
                 bordercolor=[('!disabled', DARK_BORDER)])
        
        style.configure("TCombobox",
                       fieldbackground=DARK_BG,
                       background=DARK_PANEL,
                       foreground=DARK_FG,
                       arrowcolor=DARK_FG)
        style.map("TCombobox",
                 fieldbackground=[('readonly', DARK_BG)],
                 selectbackground=[('readonly', DARK_BG)])



def start_ui(blocks=None, initial_lang="python", languages_path="languages"):
    """Start the Blockliner UI"""
    app = BlocklinerUI(initial_lang=initial_lang, languages_path=languages_path)
    app.mainloop()
