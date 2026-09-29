import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog, colorchooser
import contextlib
import itertools
import os
import re
import shutil
import json
import threading
import uuid
import subprocess
import sys
from PIL import Image, ImageTk  # For logo support
from panels import PanelManager, PanelSpec


def make_node(name, node_id=None, blocks=None, category=None,
              kind="function", child_nodes=None, locked=False, node_type_id=None):
    """
    A UI-level node: a named container holding one block list, shaped
    EXACTLY like the block lists ui.py has always worked with - a list
    of (block_id, params_dict) tuples, with a container's children
    living in params["_children"] (never a separate .children
    attribute). This is deliberately NOT engine.model.Node's shape
    (BlockInstance objects with a separate .children list) - that
    class was tested in isolation against engine/renderer.py, which
    the live UI's BlockWidget/render_block_list never actually calls.
    Reconciling the two representations is a later (likely
    persistence-related) task, not this one.

    Phase B1: every tab gets exactly one node (name="main"), so this
    is purely an added layer - nothing about what's on screen changes
    yet. Phase B2 is what lets a file hold more than one.

    Phase B3 adds `kind`: "function" (default, has `blocks`) or
    "class" (has `child_nodes` instead - other nodes, not blocks).
    Phase D adds a third kind, "category": a pure visual folder with
    zero codegen effect (also has `child_nodes`, `blocks` always
    empty) - it's just a canvas organizational grouping, invisible to
    generated code. Class is the opposite of category - a real
    code-generation construct whose children render wrapped in
    `class Foo { ... }`. The two are deliberately kept separate:
    category changes editor organization, class changes generated
    code. For now class exists narrowly to make C#/Java's
    auto-created entry point compile (it can't sit outside a class),
    with room left for real OOP semantics later.

    `locked` marks a node as not user-deletable (auto-created entry
    points/wrapping classes) - there's no delete-node feature yet to
    actually enforce this against, but it's set now so that feature
    can honor it from day one instead of needing every entry-point
    node retrofitted later. `node_type_id` ties a node back to the
    node_types.json entry that caused it to be auto-created, if any
    (e.g. "start"), so ensure_entry_point-style logic can recognize
    one already exists instead of creating a duplicate.
    """
    return {
        "id": node_id or "main",
        "name": name,
        "category": category,
        "kind": kind,
        "blocks": blocks if blocks is not None else [],
        "child_nodes": child_nodes if child_nodes is not None else [],
        "locked": locked,
        "node_type_id": node_type_id,
        # Phase C1: which other nodes (by id) this node's func_call
        # blocks resolve to - always fully recomputed by
        # recompute_references(), never hand-authored or edited
        # directly. Wires are drawn from this, never the reverse.
        "references": [],
    }


def find_node_by_id(nodes, node_id):
    """Search a node list (and any class node's child_nodes, at any
    depth) for a node with the given id."""
    for node in nodes:
        if node["id"] == node_id:
            return node
        if node.get("child_nodes"):
            found = find_node_by_id(node["child_nodes"], node_id)
            if found:
                return found
    return None


def default_active_node_id(nodes):
    """The node a brand-new tab should open into: the first
    function-kind node, searching into class nodes' child_nodes since
    a class itself has no blocks to edit (e.g. for C#/Java, this finds
    the Main/main method nested inside the auto-created wrapping
    class, not the class itself)."""
    for node in nodes:
        if node.get("kind", "function") == "function":
            return node["id"]
        if node.get("child_nodes"):
            found = default_active_node_id(node["child_nodes"])
            if found:
                return found
    return nodes[0]["id"] if nodes else None


def make_raw_code_block_source(lang):
    """
    Source code for a starter Raw Code (escape hatch) block, written into
    every newly created language's blocks/ folder. This guarantees every
    language always has at least one block - a way to write code the
    block set doesn't cover yet - matching the per-block-file contract
    used by every other block (block_id, generate_code, etc.).
    """
    return (
        'block_id = "raw_code"\n'
        'display_name = "Custom Code"\n'
        'category = "Advanced"\n'
        '\n'
        'params = [\n'
        '    {"name": "code_line", "type": "code", "default": ""}\n'
        ']\n'
        '\n'
        'def default_params():\n'
        '    return {"code_line": ""}\n'
        '\n'
        f'def generate_code(params, children, lang="{lang}"):\n'
        f'    """Escape hatch: outputs the given line of {lang} code as-is."""\n'
        '    return params.get("code_line", "") + "\\n"\n'
        '\n'
        'block_ui_description = {\n'
        '    "label": "Custom Code",\n'
        '    "params": params,\n'
        '    "category": "Advanced",\n'
        f'    "description": "Write custom {lang} code directly (advanced users only)."\n'
        '}\n'
    )


def darken_hex(color, factor=0.75):
    """Darken a #RRGGBB color by a factor, used for block outline shades
    that match whatever category color a custom block is assigned to."""
    try:
        color = color.lstrip("#")
        r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
        r, g, b = int(r * factor), int(g * factor), int(b * factor)
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return "#000000"


def get_block_attr(block_module, name, default=None):
    """
    Read an attribute from a block. Built-in blocks (loaded from a
    language pack's per-block blocks/*.json files) and custom blocks (created via the
    visual builder) are both plain dicts, but a legacy module-style
    lookup is kept as a fallback for safety. Plain getattr() on a dict
    silently returns the default instead of the real value, and plain
    dict-style .get() on a module raises AttributeError - this
    normalizes both so call sites don't need an isinstance check every
    time (a bug that broke adding/deleting/rendering custom blocks
    entirely, since BlockWidget used module-only attribute access).
    """
    if isinstance(block_module, dict):
        return block_module.get(name, default)
    return getattr(block_module, name, default)


def safe_grab_set(window):
    """
    Grab input focus for a Toplevel dialog safely.

    grab_set() fails with 'window not viewable' if called before the
    window manager has actually mapped the window on screen. How long
    that takes varies by window manager (Cinnamon, MATE, Mutter/GNOME
    all behave slightly differently), so a fixed delay isn't reliable.

    wait_visibility() blocks (while still processing Tk events) until
    the window is confirmed visible, then grab_set() is safe to call.
    The try/except is a last-resort fallback so a window manager that
    never reports visibility can't crash the app - it just won't be
    modal in that edge case.
    """
    try:
        window.wait_visibility()
        window.grab_set()
    except tk.TclError:
        pass


def make_custom_block_generate_code(template, params_meta=None, quote_char='"'):
    """
    Build a generate_code(params, children, lang) function for a
    Scratch-style custom block.

    `template` uses {{name}} placeholders; label text around them is
    literal. Inputs declared as type 'text'/'string'/'input' are
    automatically wrapped in `quote_char` (with existing quote chars and
    backslashes escaped) so the user never has to type quote marks by
    hand - unlike Scratch, this is real code, so an unquoted string is a
    syntax error, and a 'variable' type input must stay unquoted to work
    as an identifier. Number and boolean inputs are also substituted raw.
    """
    params_meta = params_meta or []
    type_by_name = {p["name"]: p.get("type", "text") for p in params_meta}

    def gen_code(params, children=None, lang=None):
        code = template
        for name, raw_val in (params or {}).items():
            if name.startswith("_"):
                continue  # internal metadata (e.g. _nickname) - never part of generated code
            ptype = type_by_name.get(name, "text")
            val_str = "" if raw_val is None else str(raw_val)
            if ptype in ("text", "string", "input"):
                escaped = val_str.replace("\\", "\\\\").replace(quote_char, "\\" + quote_char)
                rendered = f"{quote_char}{escaped}{quote_char}"
            else:
                rendered = val_str
            code = code.replace("{{" + name + "}}", rendered)
        return code + "\n"

    return gen_code


def template_to_pieces(template, params_list):
    """
    Reverse of the builder's label/input -> {{name}} template flattening.
    Used to pre-populate the visual builder when editing an existing
    custom block, so editing always starts from the same piece-based
    representation as creating (never falls back to raw text editing).
    """
    param_by_name = {p["name"]: p for p in (params_list or [])}
    pieces = []
    pattern = re.compile(r"\{\{(\w+)\}\}")
    last_end = 0

    for m in pattern.finditer(template or ""):
        if m.start() > last_end:
            label_text = template[last_end:m.start()]
            if label_text:
                pieces.append({"kind": "label", "text": label_text})

        name = m.group(1)
        meta = param_by_name.get(name, {})
        pieces.append({
            "kind": "input",
            "name": name,
            "type": meta.get("type", "text"),
            "default": meta.get("default", "")
        })
        last_end = m.end()

    if last_end < len(template or ""):
        trailing = template[last_end:]
        if trailing:
            pieces.append({"kind": "label", "text": trailing})

    return pieces


_SENTINEL_RE = re.compile(r"@@(\w+)@@")

# Param types get a tighter capture pattern where the shape of a valid
# value is well known (numbers, identifiers) - this makes matches more
# precise and less likely to accidentally swallow a neighboring param's
# text. Free-form types fall back to a lazy .*? capture.
_PARAM_CAPTURE_PATTERNS = {
    "number": r"-?\d+(?:\.\d+)?",
    "variable": r"[A-Za-z_]\w*",
    # Conditions are free-form expressions ("x > 3", "a and not b"),
    # not just bare identifiers.
    "boolean": r".+?",
}


def get_choice_combos(params_meta):
    """
    All combinations of a block's 'choice'-type param values (e.g. the
    built-in print block's mode: text/variable). A block's rendered
    code shape can differ per choice, so each combination needs its own
    reverse-match pattern. Blocks with no choice params get one combo:
    the empty one (every other param becomes a sentinel placeholder).
    """
    choice_params = [p for p in (params_meta or []) if p.get("type") == "choice"]
    if not choice_params:
        return [{}]

    choice_lists = [p.get("choices") or [p.get("default", "")] for p in choice_params]
    combos = []
    for values in itertools.product(*choice_lists):
        combos.append({p["name"]: v for p, v in zip(choice_params, values)})
    return combos


def _net_braces(line):
    """Net { minus } on one line, ignoring braces inside string
    literals and after a // comment. Deliberately simple: good enough
    to find where a brace-style body ends without a real tokenizer."""
    net, quote, i = 0, None, 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in ("\"", "'", "`"):
            quote = ch
        elif ch == "/" and line[i + 1:i + 2] == "/":
            break
        elif ch == "{":
            net += 1
        elif ch == "}":
            net -= 1
        i += 1
    return net


def _pattern_from_rendered(rendered, param_type_by_name, combo):
    """Build a single regex pattern dict from an already-rendered
    (sentinel-substituted) code string. Shared by build_reverse_pattern
    for both the literal rendering and any quote-swapped variant."""
    rendered = rendered.rstrip("\n")
    if not rendered.strip():
        return None

    parts = _SENTINEL_RE.split(rendered)
    # re.split with a capturing group interleaves: [literal, sentinel_name, literal, sentinel_name, ...]
    pattern_parts = []
    seen_groups = []
    literal_score = 0

    for idx, part in enumerate(parts):
        is_sentinel = idx % 2 == 1
        if is_sentinel:
            name = part
            ptype = param_type_by_name.get(name, "text")
            if name in seen_groups:
                # Same param appears more than once in the output (e.g. a
                # variable name used twice) - backreference instead of a
                # second capture group, which Python's re doesn't allow.
                pattern_parts.append(f"(?P={name})")
            else:
                seen_groups.append(name)
                inner = _PARAM_CAPTURE_PATTERNS.get(ptype, r".*?")
                pattern_parts.append(f"(?P<{name}>{inner})")
        else:
            pattern_parts.append(re.escape(part))
            literal_score += len(part)

    pattern_str = "^" + "".join(pattern_parts) + "$"
    try:
        # No DOTALL: matching is bucketed by exact line count at match
        # time (see import_code_to_blocks), so a pattern only ever gets
        # tested against a candidate with the same number of lines its
        # own template has. Without that guarantee, a non-greedy .*?
        # capture can be forced by the trailing $ anchor to stretch
        # across extra joined lines just to find a matching literal
        # suffix further down - silently swallowing unrelated lines
        # into one block's param value.
        compiled = re.compile(pattern_str)
    except re.error:
        return None

    return {
        "regex": compiled,
        "groups": seen_groups,
        "combo": combo,
        "literal_score": literal_score,
        "line_count": rendered.count("\n") + 1,
    }


def build_reverse_pattern(gen_func, params_meta, lang, combo):
    """
    Derive regex pattern(s) that match code this block's generate_code()
    would itself produce.

    Trick: call generate_code with every non-choice param set to a
    unique sentinel token, then see where those tokens land in the
    rendered output. Escape everything else as literal text, and turn
    each sentinel into a named capture group - so the regex is built
    from the block's own real rendering logic instead of guessing at
    its structure.

    Returns a list (usually one pattern, sometimes two). Blocks that
    quote strings with Python's repr() - like the built-in print block -
    pick ' or " depending on the string's own content, but a single
    sentinel-derived template can only encode one quote character. A
    line typed with the other quote style would otherwise fail to match
    this pattern and fall through to a more permissive one that ends up
    swallowing the quote characters into the captured value instead of
    treating them as delimiters. So when the rendering uses exactly one
    quote style as an apparent delimiter, a second pattern with quotes
    swapped is generated too.
    """
    params_meta = params_meta or []
    param_type_by_name = {p["name"]: p.get("type", "text") for p in params_meta}

    full_params = {}
    for p in params_meta:
        name = p["name"]
        full_params[name] = combo[name] if name in combo else f"@@{name}@@"

    try:
        rendered = gen_func(full_params, [], lang=lang)
    except Exception:
        return []
    if not rendered:
        return []

    patterns = []
    base = _pattern_from_rendered(rendered, param_type_by_name, combo)
    if base:
        patterns.append(base)

    has_single = "'" in rendered
    has_double = '"' in rendered
    if has_single and not has_double:
        alt = _pattern_from_rendered(rendered.replace("'", '"'), param_type_by_name, combo)
        if alt:
            patterns.append(alt)
    elif has_double and not has_single:
        alt = _pattern_from_rendered(rendered.replace('"', "'"), param_type_by_name, combo)
        if alt:
            patterns.append(alt)

    return patterns


APP_VERSION = "1.0"
BUILD_NUMBER = 1  # bump this by hand each time you ship a meaningfully new build

# Languages available out of the box - each gets a folder with just the
# Raw Code escape-hatch block (see make_raw_code_block_source), not a
# full block set. python/cpp have their real block sets built on top of
# that same starting point; the rest are ready for you to build out.
PRESET_LANGUAGES = ["python", "cpp", "c", "csharp", "java", "javascript", "rust", "go", "html"]

# For Load Code File's language detection
LANGUAGE_EXTENSIONS = {
    ".py": "python", ".pyw": "python",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp",
    ".c": "c", ".h": "c",
    ".cs": "csharp",
    ".js": "javascript", ".mjs": "javascript",
    ".java": "java",
    ".rs": "rust",
    ".go": "go",
    ".html": "html", ".htm": "html",
}

# Dark mode color scheme
DARK_BG = "#1e1e1e"
DARK_FG = "#d4d4d4"
DARK_PANEL = "#252526"
DARK_ACCENT = "#007acc"
DARK_HOVER = "#2d2d30"
DARK_BORDER = "#3e3e42"
BLOCK_BG = "#2d2d30"
BLOCK_HOVER = "#3e3e42"
BLOCK_SELECTED = "#094771"

# Block category colors
CATEGORY_COLORS = {
    "Basic": "#4ec9b0",
    "Math": "#ce9178",
    "Control": "#c586c0",
    "Functions": "#dcdcaa",
    "Data Structures": "#569cd6",
    "String Operations": "#9cdcfe",
    "Modules": "#4fc1ff",
    "GUI": "#b5cea8",
    "Advanced": "#f48771",
    "Custom Blocks": "#ff6b9d"
}

def get_persistent_data_path():
    """
    Where user data actually lives - user_data/, blockliner_saves/, etc.
    Always next to the real executable/script, NEVER just 'whatever the
    current working directory happens to be'. Running from source that
    distinction doesn't matter (CWD is normally the script's own
    folder anyway), but a built .exe/AppImage can be launched from
    anywhere (double-clicked from Downloads, a desktop shortcut,
    wherever) - and worse, PyInstaller's actual working files live in
    a temporary extraction folder that's deleted when the app closes,
    so relying on CWD there would risk data vanishing on exit with no
    warning.

    AppImage needs special handling: it mounts itself as a read-only
    virtual filesystem before running, so sys.executable points INSIDE
    that temporary mount, not the real .AppImage file - writing there
    fails with a read-only-filesystem error. The AppImage runtime sets
    the APPIMAGE env var to the actual file's real path before
    launching, so that's checked first. Mirrors the same logic in
    main.py.
    """
    appimage_path = os.environ.get("APPIMAGE")
    if appimage_path:
        return os.path.dirname(os.path.abspath(appimage_path))
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


_PERSISTENT_DATA_PATH = get_persistent_data_path()
CUSTOM_BLOCKS_PATH = os.path.join(_PERSISTENT_DATA_PATH, "user_data", "custom_blocks.json")
BLOCKLINER_SAVES_PATH = os.path.join(_PERSISTENT_DATA_PATH, "blockliner_saves")
APP_SETTINGS_PATH = os.path.join(_PERSISTENT_DATA_PATH, "user_data", "app_settings.json")

DEFAULT_SETTINGS = {
    "default_language": "python",
    "confirm_delete": True,
    "show_notifications": True,
    "animate_blocks": False,
    "python_command": "python3",
    "cpp_compiler": "g++",
    "terminal_command": "gnome-terminal --",
    "category_colors": {},
    "category_order": [],
}

class PaletteBlockItem(tk.Frame):
    """Block item in palette - click to add"""
    def __init__(self, parent, block_module, on_add):
        super().__init__(parent, bg=DARK_PANEL, cursor="hand2", relief=tk.FLAT)
        self.block_module = block_module
        self.on_add = on_add
        
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
        
        # Bind events
        self.bind("<Button-1>", lambda e: self.on_add(self.block_module))
        add_btn.bind("<Button-1>", lambda e: self.on_add(self.block_module))
        self.name_label.bind("<Button-1>", lambda e: self.on_add(self.block_module))
        
        self.bind("<Enter>", self.on_hover)
        self.bind("<Leave>", self.on_leave)
    
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


class BlocklinerUI(tk.Tk):
    def __init__(self, initial_lang="python", languages_path="languages"):
        super().__init__()
        self.title("Blockliner - Visual Code Builder")
        self.geometry("1400x800")
        self.configure(bg=DARK_BG)
        
        self.languages_path = languages_path
        self.settings = self.load_app_settings()

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
    
    def get_active_node(self, tab=None):
        """Return the currently-active node dict for `tab` (defaulting
        to the active tab), searching into class nodes' child_nodes at
        any depth since B3's auto-created entry point can be nested
        inside an auto-created wrapping class. Falls back to the first
        function-kind node found anywhere (never a class node itself -
        it has no blocks to edit), and - purely as a defensive last
        resort for a tab that somehow has no nodes at all - creates a
        fresh "main" node rather than raising, since losing the
        workspace entirely on a lookup miss would be a far worse
        failure than silently recovering an empty one."""
        tab = tab if tab is not None else self.tabs[self.active_tab_index]
        if not tab.get("nodes"):
            tab["nodes"] = [make_node("main", node_id="main")]
            tab["active_node_id"] = tab["nodes"][0]["id"]

        found = find_node_by_id(tab["nodes"], tab.get("active_node_id"))
        if found is not None and found.get("kind", "function") == "function":
            return found

        fallback_id = default_active_node_id(tab["nodes"])
        fallback = find_node_by_id(tab["nodes"], fallback_id) if fallback_id else None
        return fallback or tab["nodes"][0]

    def set_project_blocks(self, new_list):
        """
        Reassign self.project_blocks to an entirely new list (as opposed
        to mutating the existing one in place, e.g. .append()/.pop()).
        Always goes through here so the active tab's active node's own
        stored reference gets updated too - otherwise the node would
        silently keep pointing at the old (now stale) list after a full
        reload like Code -> Blocks or Load Project.
        """
        self.project_blocks = new_list
        if getattr(self, "tabs", None):
            self.get_active_node()["blocks"] = new_list

    def sync_active_tab_state(self):
        """Write the currently-active tab's live language/project_blocks
        back into its stored slot. project_blocks is normally already
        the same list object (mutations like .append()/.pop() keep it
        in sync automatically), but this also covers current_language,
        and is cheap insurance before switching away from a tab."""
        if not getattr(self, "tabs", None):
            return
        tab = self.tabs[self.active_tab_index]
        tab["language"] = self.current_language
        self.get_active_node(tab)["blocks"] = self.project_blocks

    def mark_active_tab_dirty(self):
        if getattr(self, "tabs", None):
            self.tabs[self.active_tab_index]["dirty"] = True
            self.refresh_tab_bar()

    def switch_to_tab(self, index):
        if not (0 <= index < len(self.tabs)) or index == self.active_tab_index:
            return
        self.sync_active_tab_state()

        self.active_tab_index = index
        tab = self.tabs[index]
        self.current_language = tab["language"]
        self.project_blocks = self.get_active_node(tab)["blocks"]
        self.view_mode = "node"

        self.lang_var.set(self.current_language)
        self.load_blocks_for_language(self.current_language)
        self.load_and_merge_custom_blocks()
        self.refresh_palette()
        self.refresh_workspace()
        self.refresh_tab_bar()

    def _append_new_tab(self):
        """Add a fresh Untitled tab WITHOUT switching to it; returns it."""
        self.sync_active_tab_state()
        title = f"Untitled {self._next_untitled_number}"
        self._next_untitled_number += 1
        new_nodes = self.build_initial_nodes_for_language(self.current_language)
        tab = {
            "title": title,
            "language": self.current_language,
            "nodes": new_nodes,
            "active_node_id": default_active_node_id(new_nodes),
            "filepath": None,
            "dirty": False,
        }
        self.tabs.append(tab)
        return tab

    def new_tab(self):
        self._append_new_tab()
        self.switch_to_tab(len(self.tabs) - 1)

    def create_file_at(self, pos):
        """Files-layer right-click 'New file': add a tab as a box at the
        cursor and stay on the Files layer (new_tab() would switch away)."""
        tab = self._append_new_tab()
        tab["canvas_x"], tab["canvas_y"] = pos
        self.refresh_tab_bar()
        self.refresh_workspace()

    def close_tab(self, index):
        if not (0 <= index < len(self.tabs)):
            return
        tab = self.tabs[index]

        if tab["dirty"]:
            proceed = messagebox.askyesno(
                "Unsaved Changes",
                f"'{tab['title']}' has unsaved changes. Close it anyway?"
            )
            if not proceed:
                return

        self.tabs.pop(index)

        if not self.tabs:
            # Always keep at least one tab open.
            fallback_nodes = self.build_initial_nodes_for_language(self.current_language)
            self.tabs.append({
                "title": f"Untitled {self._next_untitled_number}",
                "language": self.current_language,
                "nodes": fallback_nodes,
                "active_node_id": default_active_node_id(fallback_nodes),
                "filepath": None,
                "dirty": False,
            })
            self._next_untitled_number += 1

        if index < self.active_tab_index:
            self.active_tab_index -= 1
        elif index == self.active_tab_index:
            self.active_tab_index = min(self.active_tab_index, len(self.tabs) - 1)
            tab = self.tabs[self.active_tab_index]
            self.current_language = tab["language"]
            self.project_blocks = self.get_active_node(tab)["blocks"]
            self.view_mode = "node"
            self.lang_var.set(self.current_language)
            self.load_blocks_for_language(self.current_language)
            self.load_and_merge_custom_blocks()
            self.refresh_palette()
            self.refresh_workspace()

        self.refresh_tab_bar()

    def refresh_tab_bar(self):
        """Redraw the tab strip at the top of the window."""
        for widget in self.tab_bar_frame.winfo_children():
            widget.destroy()

        for i, tab in enumerate(self.tabs):
            is_active = (i == self.active_tab_index)
            tab_frame = tk.Frame(
                self.tab_bar_frame,
                bg=(DARK_ACCENT if is_active else DARK_PANEL),
                highlightthickness=1,
                highlightbackground=DARK_BORDER
            )
            tab_frame.pack(side=tk.LEFT, padx=(0, 2), pady=2)

            label_text = tab["title"] + (" \u25CF" if tab["dirty"] else "")
            label = tk.Label(
                tab_frame, text=label_text,
                bg=(DARK_ACCENT if is_active else DARK_PANEL),
                fg=("#ffffff" if is_active else DARK_FG),
                font=("Segoe UI", 9, "bold" if is_active else "normal"),
                cursor="hand2", padx=10, pady=6
            )
            label.pack(side=tk.LEFT)
            label.bind("<Button-1>", lambda e, idx=i: self.switch_to_tab(idx))

            close_btn = tk.Label(
                tab_frame, text="\u2715",
                bg=(DARK_ACCENT if is_active else DARK_PANEL),
                fg=("#ffffff" if is_active else "#888888"),
                font=("Segoe UI", 8), cursor="hand2", padx=8
            )
            close_btn.pack(side=tk.LEFT)
            close_btn.bind("<Button-1>", lambda e, idx=i: self.close_tab(idx))

        tk.Button(
            self.tab_bar_frame, text="+", bg=DARK_PANEL, fg=DARK_FG,
            relief=tk.FLAT, font=("Segoe UI", 11, "bold"), cursor="hand2",
            width=2, command=self.new_tab
        ).pack(side=tk.LEFT, padx=(6, 0), pady=2)

        # Files-layer entry point: always visible regardless of which
        # tab/view is currently active, since it's a level above any
        # one tab rather than scoped to one.
        is_files_view = (self.view_mode == "files")
        tk.Button(
            self.tab_bar_frame, text="\U0001F4C1 Files",
            bg=(DARK_ACCENT if is_files_view else DARK_PANEL),
            fg=("#ffffff" if is_files_view else DARK_FG),
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
            command=self.switch_to_files_view
        ).pack(side=tk.RIGHT, padx=(0, 6), pady=2)

    def load_blocks_for_language(self, lang, verbose=True):
        """
        Load blocks for a language from its JSON language pack
        (languages/<lang>/manifest.json + languages/<lang>/blocks/*.json,
        one file per block), via the V2 engine.
        """
        from engine.loader import load_language_pack
        from engine.renderer import with_generate_code

        manifest, blocks = load_language_pack(os.path.join(self.languages_path, lang), verbose=verbose)
        self.blocks = with_generate_code(blocks) if blocks else {}
        self.node_types = manifest.get("node_types", []) if manifest else []

        # Group blocks by category
        self.blocks_by_category = {}
        for block_id, block_def in self.blocks.items():
            category = get_block_attr(block_def, "category", "Basic")
            self.blocks_by_category.setdefault(category, []).append(block_def)

    def get_node_types_for_language(self, lang):
        """Fetch node_types.json for `lang` directly from disk, rather
        than relying on self.node_types (which reflects whichever
        language is CURRENTLY active) - this needs to work for the
        language a brand-new tab is ABOUT to use, including at
        __init__ time before any language pack has been loaded yet."""
        from engine.loader import load_language_pack
        try:
            manifest, _ = load_language_pack(os.path.join(self.languages_path, lang))
        except Exception:
            return []
        return manifest.get("node_types", []) if manifest else []

    def build_initial_nodes_for_language(self, lang):
        """
        Phase B3: the node(s) a brand-new file starts with for `lang`.

        Most languages just get today's single empty, unlocked "main"
        node - unchanged from before B3. A language whose
        node_types.json marks some node type both required and
        is_entry_point gets that entry point auto-created and locked
        instead, since such a file can't run/compile without one.

        For C#/Java specifically, the entry point can't sit outside a
        class, so it's wrapped in an auto-created, locked class node
        (see the class-node decision: class is a real code-generation
        construct, scoped narrowly here to this compile requirement,
        kept deliberately separate from Phase D's purely-visual
        category folders).
        """
        node_types = self.get_node_types_for_language(lang)
        entry_type = next(
            (nt for nt in node_types if nt.get("required") and nt.get("is_entry_point")),
            None
        )
        if not entry_type:
            return [make_node("main", node_id="main", blocks=[])]

        entry_node = make_node(
            "Main" if lang == "csharp" else "main",
            node_id=str(uuid.uuid4())[:8],
            blocks=[],
            locked=True,
            node_type_id=entry_type["id"],
        )

        if lang in ("csharp", "java"):
            class_name = "Program" if lang == "csharp" else "Main"
            class_node = make_node(
                class_name, node_id=str(uuid.uuid4())[:8], kind="class",
                child_nodes=[entry_node], locked=True,
            )
            return [class_node]

        return [entry_node]
    
    def load_app_settings(self):
        """Load app settings from JSON file, filling in any missing keys with defaults."""
        user_data_dir = os.path.dirname(APP_SETTINGS_PATH)
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)
        settings = dict(DEFAULT_SETTINGS)
        if os.path.exists(APP_SETTINGS_PATH):
            try:
                with open(APP_SETTINGS_PATH, "r") as f:
                    saved = json.load(f)
                settings.update(saved)
            except Exception as e:
                print(f"Failed to load app settings: {e}")
        return settings

    def save_app_settings(self):
        """Save current app settings to JSON file"""
        user_data_dir = os.path.dirname(APP_SETTINGS_PATH)
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)
        try:
            with open(APP_SETTINGS_PATH, "w") as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Failed to save app settings: {e}")

    def maybe_notify(self, title, message):
        """Show a 'this succeeded' confirmation popup, unless the user
        has turned those off in Settings. Errors/warnings never go
        through this - only pure success confirmations do."""
        if self.settings.get("show_notifications", True):
            messagebox.showinfo(title, message)

    def load_custom_blocks_data(self):
        """Load custom blocks from JSON file"""
        user_data_dir = os.path.dirname(APP_SETTINGS_PATH)
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)
        if os.path.exists(CUSTOM_BLOCKS_PATH):
            try:
                with open(CUSTOM_BLOCKS_PATH, "r") as f:
                    return json.load(f)
            except Exception as e:
                # Don't just discard a corrupt file - back it up so the
                # user's blocks aren't silently lost, then start fresh.
                print(f"Failed to load custom blocks: {e}")
                try:
                    backup_path = CUSTOM_BLOCKS_PATH + ".corrupt-backup"
                    shutil.copy2(CUSTOM_BLOCKS_PATH, backup_path)
                    print(f"Backed up the unreadable file to: {backup_path}")
                except Exception as backup_error:
                    print(f"Could not back up corrupt file either: {backup_error}")
                return []
        return []
    
    def save_custom_blocks_data(self, custom_blocks):
        """
        Save custom blocks to JSON file. Writes to a temp file first and
        atomically swaps it into place - if serialization fails partway
        through (e.g. a non-JSON-safe value slipped into one of the
        dicts), the real file on disk is never touched, so it can't be
        left half-written/corrupted the way a direct write can.
        """
        user_data_dir = os.path.dirname(APP_SETTINGS_PATH)
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)

        # Defensive: strip anything that isn't JSON-safe (e.g. a
        # generate_code function accidentally attached to a block dict)
        # rather than letting the whole save fail because of one bad key.
        def clean(block):
            return {k: v for k, v in block.items() if not callable(v)}

        safe_blocks = [clean(b) if isinstance(b, dict) else b for b in custom_blocks]

        tmp_path = CUSTOM_BLOCKS_PATH + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                json.dump(safe_blocks, f, indent=2)
            os.replace(tmp_path, CUSTOM_BLOCKS_PATH)
        except Exception as e:
            print(f"Failed to save custom blocks: {e}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
    
    def _is_raw_code_block(self, block_id, module):
        """Identify the escape-hatch block so it's excluded from
        reverse-matching (its own pattern would trivially match every
        line) and so the importer knows what to fall back to."""
        if block_id.startswith("raw_code"):
            return True
        params = get_block_attr(module, "params", [])
        return any(p.get("name") == "code_line" for p in params)

    def get_raw_code_block_id(self, lang):
        """Find whichever block is this language's Raw Code escape
        hatch. Every language is guaranteed one (auto-created when the
        language itself is created), but the exact block_id has varied
        historically (raw_code vs raw_code_cpp), so search rather than
        assume a fixed name."""
        for block_id, module in self.blocks.items():
            if self._is_raw_code_block(block_id, module):
                return block_id
        return None

    def get_raw_code_param_name(self, block_id):
        """
        Which param name this specific raw code block actually expects
        to hold the literal line of code. Historically assumed to
        always be 'code_line', but a block file predating that
        convention (or a hand-written one) can use something else - and
        constructing params with the wrong key produces a KeyError
        inside that block's own generate_code the moment it runs,
        surfacing as '// ERROR generating block ...: 'whatever_name''.
        """
        module = self.blocks.get(block_id)
        params = get_block_attr(module, "params", [])
        if params:
            return params[0].get("name", "code_line")
        return "code_line"

    def build_reverse_patterns(self, lang):
        """
        Build reverse-match patterns for every block available in the
        current language (built-in and custom alike - both work the
        same way here since both expose generate_code + params).
        Sorted most-specific-first so a precise match always wins over
        a vaguer one that happens to also fit.
        """
        patterns = []
        for block_id, module in self.blocks.items():
            if self._is_raw_code_block(block_id, module):
                continue

            params_meta = get_block_attr(module, "params", [])
            gen_func = get_block_attr(module, "generate_code")
            if not callable(gen_func):
                continue

            for combo in get_choice_combos(params_meta):
                for pat in build_reverse_pattern(gen_func, params_meta, lang, combo):
                    pat["block_id"] = block_id
                    patterns.append(pat)

        patterns.sort(key=lambda p: -p["literal_score"])
        return patterns

    def build_container_header_patterns(self, lang):
        """Header-line patterns for container blocks (if/for/while/def)
        in indentation-style languages. Each container is rendered once
        with a sentinel child; only blocks that come out as exactly
        "header line + one indented body line" qualify (Python-style).
        Brace-style containers ({ ... } with a closing line) don't fit
        that shape and are skipped, so those languages keep the plain
        raw-code fallback for their bodies. The header alone becomes the
        regex - the body is parsed separately, by indentation."""
        patterns = []
        for block_id, module in self.blocks.items():
            if self._is_raw_code_block(block_id, module):
                continue
            if not get_block_attr(module, "is_container", False):
                continue
            params_meta = get_block_attr(module, "params", [])
            gen_func = get_block_attr(module, "generate_code")
            if not callable(gen_func):
                continue
            type_by_name = {p["name"]: p.get("type", "text") for p in params_meta}
            for combo in get_choice_combos(params_meta):
                full = {
                    p["name"]: (combo[p["name"]] if p["name"] in combo else f"@@{p['name']}@@")
                    for p in params_meta
                }
                try:
                    rendered = gen_func(full, ["@@BODY@@\n"], lang=lang)
                except Exception:
                    continue
                lines = [l for l in (rendered or "").split("\n") if l.strip()]
                style = None
                indented_body = lambda l: l.strip() == "@@BODY@@" and l[:1] in (" ", "\t")
                if len(lines) == 2 and indented_body(lines[1]):
                    style = "indent"        # Python: header + indented body
                elif (len(lines) == 3 and lines[0].rstrip().endswith("{")
                        and indented_body(lines[1]) and lines[2].strip() == "}"):
                    style = "knr"           # header { / body / }
                elif (len(lines) == 4 and lines[1].strip() == "{"
                        and indented_body(lines[2]) and lines[3].strip() == "}"):
                    style = "allman"        # header / { / body / }
                if style is None:
                    continue
                pat = _pattern_from_rendered(lines[0], type_by_name, combo)
                if pat:
                    pat["block_id"] = block_id
                    pat["style"] = style
                    patterns.append(pat)
        patterns.sort(key=lambda p: -p["literal_score"])
        return patterns

    def strip_cpp_boilerplate(self, lines):
        """
        Remove the #include/using/main()/return-0/closing-brace
        scaffolding that update_generated_code() auto-adds around C++
        output, and de-indent the body - none of that is a block
        itself, it's regenerated automatically every time.
        """
        lines = list(lines)

        if (len(lines) >= 2 and lines[0].strip() == "#include <iostream>"
                and lines[1].strip() == "using namespace std;"):
            lines = lines[2:]
            if lines and lines[0].strip() == "":
                lines = lines[1:]

        if lines and lines[0].strip() == "int main() {":
            lines = lines[1:]

        if lines and lines[-1].strip() == "}":
            lines = lines[:-1]
        if lines and lines[-1].strip() == "return 0;":
            lines = lines[:-1]

        return [line[4:] if line.startswith("    ") else line for line in lines]

    def import_code_to_blocks(self, code_text):
        """
        Convert typed/pasted code into workspace blocks: each line (or
        small window of lines, for blocks whose generate_code legitimately
        spans a few lines) is matched against every available block's
        reverse pattern. Unmatched lines become Raw Code blocks instead
        of being lost, so nothing in the original code disappears.

        Returns (new_project_blocks, matched_count, raw_count).
        """
        lang = self.current_language
        patterns = self.build_reverse_patterns(lang)
        raw_block_id = self.get_raw_code_block_id(lang)
        raw_param_name = self.get_raw_code_param_name(raw_block_id) if raw_block_id else "code_line"

        # Group patterns by how many physical lines their own template
        # spans, so a candidate window is only ever tested against
        # patterns expecting exactly that many lines.
        patterns_by_line_count = {}
        for pat in patterns:
            patterns_by_line_count.setdefault(pat["line_count"], []).append(pat)
        window_sizes = sorted(patterns_by_line_count.keys(), reverse=True)
        container_patterns = self.build_container_header_patterns(lang)
        # In a language whose containers are brace-delimited, indentation
        # is cosmetic: structure comes from braces, and matching looks at
        # each line stripped. (Python-style languages keep the
        # indentation-driven behaviour.)
        brace_mode = any(p["style"] != "indent" for p in container_patterns)

        from engine.formatter import normalize_line
        all_lines = [normalize_line(l) for l in code_text.split("\n")]
        if lang == "cpp":
            all_lines = self.strip_cpp_boilerplate(all_lines)
        if brace_mode:
            # "} else {" / "} else if (c) {" is really a closer followed
            # by the next container's header. Splitting it lets the
            # else/else-if blocks parse like any other container; the
            # renderer joins them back onto one line.
            split_lines = []
            for l in all_lines:
                m = re.match(r"^(\s*)\}\s*(else\b.*)$", l)
                if m:
                    split_lines.append(m.group(1) + "}")
                    split_lines.append(m.group(1) + m.group(2))
                else:
                    split_lines.append(l)
            all_lines = split_lines
        counts = {"matched": 0, "raw": 0}

        def indent_of(text):
            return len(text) - len(text.lstrip(" "))

        def emit_raw(line, out):
            if raw_block_id:
                out.append((raw_block_id, {raw_param_name: line}))
                counts["raw"] += 1

        def find_brace_body(lines, start):
            """Given the index of the first body line, return the index
            of the closing '}' line that ends this container, or None
            if the braces don't form a clean container. A closer that
            shares its line with other code ('} else {') or an
            unbalanced/unclosed body is NOT clean: the caller falls back
            to raw lines, which is always lossless."""
            depth = 1
            for j in range(start, len(lines)):
                text = lines[j].strip()
                if depth == 1 and text.startswith("}"):
                    return j if text == "}" else None
                depth += _net_braces(text)
                if depth <= 0:
                    return None
            return None

        def parse(lines, i, base):
            """Parse lines from i at indentation `base`. Indent-style
            containers end on a dedent; brace-style ones end on their
            matching '}'. Returns (blocks, next_i). Anything no block
            claims stays verbatim raw code (lossless)."""
            n = len(lines)
            out = []
            while i < n:
                line = lines[i]
                if not line.strip():
                    i += 1
                    continue
                ind = indent_of(line)
                if not brace_mode:
                    if ind < base:
                        break
                    if ind > base:
                        emit_raw(line, out)
                        i += 1
                        continue
                text = line.strip() if brace_mode else line[base:]

                handled = False
                for pat in container_patterns:
                    m = pat["regex"].match(text)
                    if not m:
                        continue
                    style = pat["style"]
                    children, next_i = None, None
                    if style == "indent":
                        if brace_mode:
                            continue
                        j = i + 1
                        while j < n and not lines[j].strip():
                            j += 1
                        if j >= n or indent_of(lines[j]) <= base:
                            break  # header with no body yet (mid-typing)
                        children, next_i = parse(lines, j, indent_of(lines[j]))
                        if (len(children) == 1 and raw_block_id
                                and children[0][0] == raw_block_id
                                and children[0][1].get(raw_param_name, "").strip() == "pass"):
                            children = []  # the container's own empty-body filler
                            counts["raw"] -= 1
                    else:
                        if not brace_mode:
                            continue
                        body_start = i + 1
                        if style == "allman":
                            k = i + 1
                            while k < n and not lines[k].strip():
                                k += 1
                            if k >= n or lines[k].strip() != "{":
                                continue
                            body_start = k + 1
                        close = find_brace_body(lines, body_start)
                        if close is None:
                            continue
                        body = [l.strip() for l in lines[body_start:close]]
                        children, _ = parse(body, 0, 0)
                        next_i = close + 1
                    params = {name: m.group(name) for name in pat["groups"]}
                    params.update(pat["combo"])
                    params["_children"] = children
                    out.append((pat["block_id"], params))
                    counts["matched"] += 1
                    i = next_i
                    handled = True
                    break
                if handled:
                    continue

                matched = False
                for window in window_sizes:
                    if i + window > n:
                        continue
                    chunk = lines[i:i + window]
                    if not brace_mode and any(l.strip() and indent_of(l) < base for l in chunk):
                        continue
                    candidate = "\n".join(
                        (l.strip() if brace_mode else l[base:]) for l in chunk
                    )
                    for fpat in patterns_by_line_count[window]:
                        m = fpat["regex"].match(candidate)
                        if not m:
                            continue
                        params = {name: m.group(name) for name in fpat["groups"]}
                        params.update(fpat["combo"])
                        out.append((fpat["block_id"], params))
                        counts["matched"] += 1
                        i += window
                        matched = True
                        break
                    if matched:
                        break

                if not matched:
                    emit_raw(line, out)
                    i += 1
            return out, i

        new_project_blocks, _ = parse(all_lines, 0, 0)
        return new_project_blocks, counts["matched"], counts["raw"]

    def _convert_code_string_to_blocks(self, code, dialog=None):
        """Shared by the Code->Blocks dialog: match `code` (a plain
        string, not read from any particular widget) against the
        current language's reverse patterns and replace the workspace
        blocks with the result. Closes `dialog` on success, if given,
        so the paste/convert window doesn't linger after it's done its
        job."""
        placeholder = "# No code generated yet\n# Add blocks from the palette!"
        remaining = code.strip()
        if remaining.startswith(placeholder):
            remaining = remaining[len(placeholder):].strip()
        if not remaining:
            messagebox.showwarning("No Code", "Type or paste some code into the box first!")
            return

        if self.project_blocks:
            proceed = messagebox.askyesno(
                "Replace Workspace Blocks?",
                "This replaces every block currently in your workspace with blocks "
                "matched from the code above. This can't be undone.\n\nContinue?"
            )
            if not proceed:
                return

        raw_block_id = self.get_raw_code_block_id(self.current_language)
        if raw_block_id is None:
            messagebox.showerror(
                "Can't Import",
                f"No Raw Code block found for '{self.current_language}' - "
                "can't safely fall back for unmatched lines."
            )
            return

        new_blocks, matched_count, raw_count = self.import_code_to_blocks(remaining)
        self.set_project_blocks(new_blocks)
        self.mark_active_tab_dirty()
        self.refresh_workspace()

        if dialog is not None:
            dialog.destroy()

        self.maybe_notify(
            "Code Converted",
            f"Converted {len(new_blocks)} line(s) into blocks:\n"
            f"  \u2713 {matched_count} matched to real blocks\n"
            f"  \u26A0 {raw_count} kept as Raw Code (no matching block found)"
        )

    def _pick_code_file_content(self):
        """File-picker + language-detection half of the old
        load_code_file(): reads a source file from disk and, if its
        extension implies a different language than the current one,
        offers to switch so 'Code -> Blocks' matches against the right
        block set. Returns the file's text, or None if the user
        cancelled or the read failed - doesn't touch any widget, so
        it's reusable from the Code->Blocks dialog regardless of
        whether that dialog is showing on the Files, Nodes, or Blocks
        layer."""
        filetypes_pattern = " ".join(f"*{ext}" for ext in LANGUAGE_EXTENSIONS)
        filename = filedialog.askopenfilename(
            title="Open Code File",
            filetypes=[("Code files", filetypes_pattern), ("All files", "*.*")]
        )
        if not filename:
            return None

        try:
            with open(filename, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            messagebox.showerror("Open Failed", f"Could not read file:\n{e}")
            return None

        ext = os.path.splitext(filename)[1].lower()
        detected_lang = LANGUAGE_EXTENSIONS.get(ext)

        if detected_lang and detected_lang != self.current_language:
            available = self.get_available_languages()
            if detected_lang in available:
                switch = messagebox.askyesno(
                    "Switch Language?",
                    f"This looks like {detected_lang} code (.{ext.lstrip('.')} extension).\n\n"
                    f"Switch Blockliner to '{detected_lang}' before converting it, so "
                    f"'Code \u2192 Blocks' matches against the right block set?"
                )
                if switch:
                    self.lang_var.set(detected_lang)
                    self.on_language_change()
            else:
                messagebox.showinfo(
                    "Language Not Set Up",
                    f"This looks like {detected_lang} code, but that language isn't set up "
                    f"in Blockliner yet. Loading the text in anyway - use '+ Lang' first if "
                    f"you want proper block matching for it."
                )

        return content

    def open_code_to_blocks_dialog(self, prefill_from_file=False):
        """Standalone Code->Blocks paste/convert dialog - reachable from
        the toolbar regardless of which layer (Files/Nodes/Blocks) is
        currently on screen, and independent of self.code_text/the
        right-hand panel's visibility. Splitting this out of that panel
        is what let the panel itself become Blocks-layer-only (see
        update_right_panel_visibility) without losing the 'Open Code
        File' / 'Code -> Blocks' workflow at the other two layers."""
        dialog = tk.Toplevel(self)
        dialog.title("Code \u2192 Blocks")
        dialog.geometry("640x480")
        dialog.configure(bg=DARK_BG)
        dialog.transient(self)

        header = tk.Frame(dialog, bg=DARK_BG)
        header.pack(fill=tk.X, padx=10, pady=(10, 4))
        tk.Label(
            header, text="Paste or open code below, then Convert.",
            bg=DARK_BG, fg="#888888", font=("Segoe UI", 9)
        ).pack(side=tk.LEFT)

        text_widget = tk.Text(
            dialog, bg=BLOCK_BG, fg=DARK_FG, insertbackground=DARK_FG,
            relief=tk.FLAT, wrap=tk.NONE, font=("Consolas", 10)
        )
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        def _open_file():
            content = self._pick_code_file_content()
            if content is None:
                return
            text_widget.delete(1.0, tk.END)
            text_widget.insert(1.0, content)

        def _convert():
            self._convert_code_string_to_blocks(text_widget.get(1.0, tk.END), dialog=dialog)

        btn_row = tk.Frame(dialog, bg=DARK_BG)
        btn_row.pack(fill=tk.X, padx=10, pady=(4, 10))
        tk.Button(
            btn_row, text="\U0001F4C4 Open File", bg="#3a3a3a", fg=DARK_FG,
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9), command=_open_file
        ).pack(side=tk.LEFT)
        tk.Button(
            btn_row, text="Cancel", bg="#3a3a3a", fg=DARK_FG,
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9), command=dialog.destroy
        ).pack(side=tk.RIGHT)
        tk.Button(
            btn_row, text="\U0001F504 Convert", bg=DARK_ACCENT, fg="#ffffff",
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9, "bold"), command=_convert
        ).pack(side=tk.RIGHT, padx=(0, 8))

        if prefill_from_file:
            content = self._pick_code_file_content()
            if content is None:
                dialog.destroy()
                return
            text_widget.insert(1.0, content)

        return dialog

    def load_and_merge_custom_blocks(self):
        """
        Load custom blocks and merge into the blocks dictionary, scoped
        to the currently active language - a block made while editing
        Python shouldn't also show up (and be offered as runnable code)
        in C++. Blocks saved before this field existed have no
        'language' key at all; those are treated as 'all' so nothing a
        user already built silently disappears.
        """
        self.custom_blocks = self.load_custom_blocks_data()

        for cblock in self.custom_blocks:
            # Ensure block has all required attributes
            if "block_id" not in cblock:
                cblock["block_id"] = "custom_" + str(uuid.uuid4())[:8]

            cblock["category"] = cblock.get("category", "Custom Blocks")
            cblock["display_name"] = cblock.get("display_name", "Unnamed Custom Block")
            cblock["params"] = cblock.get("params", [])

            block_lang = cblock.get("language", "all")
            if block_lang not in ("all", self.current_language):
                continue  # belongs to a different language - not part of this palette

            quote_char = cblock.get("quote_char", '"')

            # IMPORTANT: attach generate_code to a COPY, not to cblock
            # itself. self.custom_blocks must always stay pure JSON-safe
            # data - it gets saved to disk directly elsewhere. Attaching
            # a live function straight onto these dicts (as before) meant
            # every save after the first load tried to json.dump a
            # function object, which fails - and because the write
            # wasn't atomic, it corrupted custom_blocks.json on disk.
            runtime_block = dict(cblock)
            runtime_block["generate_code"] = make_custom_block_generate_code(
                cblock["code_template"], cblock["params"], quote_char
            )

            # Add to blocks dict and category
            self.blocks[runtime_block["block_id"]] = runtime_block
            self.blocks_by_category.setdefault(runtime_block["category"], []).append(runtime_block)
    
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
            canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            canvas.yview_scroll(1, "units")
        elif event.delta:
            step = -1 if event.delta > 0 else 1
            canvas.yview_scroll(step, "units")
    
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
        ttk.Button(toolbar, text="\U0001F504 Code \u2192 Blocks", command=lambda: self.open_code_to_blocks_dialog(prefill_from_file=False), **btn_style).pack(side=tk.LEFT, padx=3)
        
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
            text="Click to add block →",
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
        self.workspace_frame = tk.Frame(self.workspace_canvas, bg=DARK_BG)
        
        self.workspace_frame.bind(
            "<Configure>",
            lambda e: self.workspace_canvas.configure(scrollregion=self.workspace_canvas.bbox("all"))
        )
        
        self.workspace_frame_window_id = self.workspace_canvas.create_window(
            (0, 0), window=self.workspace_frame, anchor="nw", width=600
        )
        self.workspace_canvas.configure(yscrollcommand=workspace_scrollbar.set)
        
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
    
    def get_available_languages(self):
        """Get list of available languages"""
        if not os.path.exists(self.languages_path):
            return ["python"]
        return sorted([d for d in os.listdir(self.languages_path) 
                      if os.path.isdir(os.path.join(self.languages_path, d))])

    def refresh_language_list(self):
        """
        Re-scan languages/ from disk and update the dropdown. The main
        language list is normally only set once at startup (and patched
        by + Lang / delete Lang), so a folder added or removed by hand
        outside the app - e.g. in a file manager or terminal - won't
        show up or disappear on its own until this runs (or the app
        restarts, which does the same scan).
        """
        available = self.get_available_languages()
        self.lang_combo['values'] = available

        if self.current_language not in available:
            fallback = available[0] if available else "python"
            messagebox.showwarning(
                "Language Missing",
                f"'{self.current_language}' no longer has a folder on disk.\n\n"
                f"Switching to '{fallback}'."
            )
            self.lang_var.set(fallback)
            self.on_language_change()

        self.maybe_notify(
            "Languages Refreshed",
            f"Found {len(available)} language(s):\n{', '.join(available)}"
        )
    
    def open_block_chooser_dialog(self, container_list):
        """
        Small popup palette for adding a block into a container block's
        body (e.g. inside an If block). Reuses the same categorized
        block list as the main palette, but clicking an entry adds it
        into container_list instead of the top-level workspace.
        """
        dialog = tk.Toplevel(self)
        dialog.title("Add Block to Body")
        dialog.geometry("360x520")
        dialog.configure(bg=DARK_PANEL)
        dialog.transient(self)
        safe_grab_set(dialog)

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        header = tk.Frame(dialog, bg="#4a9eff", height=44)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header, text="Add Block to Body", bg="#4a9eff", fg="white",
            font=("Segoe UI", 12, "bold")
        ).pack(side=tk.LEFT, padx=15, pady=10)

        canvas = tk.Canvas(dialog, bg=DARK_PANEL, highlightthickness=0)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        list_frame = tk.Frame(canvas, bg=DARK_PANEL)
        list_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def choose(block_module):
            dialog.destroy()
            self.add_block_to_workspace(block_module, container_list=container_list)

        for category in self.get_ordered_categories():
            blocks_in_category = self.blocks_by_category.get(category, [])
            if not blocks_in_category:
                continue
            color = CATEGORY_COLORS.get(category, "#ffffff")
            tk.Label(
                list_frame, text=category.upper(), bg=DARK_PANEL, fg=color,
                font=("Segoe UI", 9, "bold")
            ).pack(anchor="w", padx=10, pady=(10, 2))
            for block_module in sorted(blocks_in_category, key=lambda x: get_block_attr(x, "display_name", "")):
                name = get_block_attr(block_module, "display_name", "Unknown")
                tk.Button(
                    list_frame, text=f"+ {name}", bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT,
                    anchor="w", cursor="hand2",
                    command=lambda bm=block_module: choose(bm)
                ).pack(fill=tk.X, padx=10, pady=1)

        dialog.bind("<Escape>", lambda e: dialog.destroy())

    def get_ordered_categories(self):
        """
        All currently-populated categories in their persisted display
        order. Any category that exists in the palette but isn't in the
        saved order yet (a brand-new one, or the very first run) gets
        appended alphabetically and the order is persisted, so nothing
        is ever silently missing from the palette.
        """
        present = set(self.blocks_by_category.keys())
        ordered = [c for c in self.category_order if c in present]
        missing = sorted(present - set(ordered))
        if missing:
            ordered.extend(missing)
            self.category_order = ordered
            self.settings["category_order"] = self.category_order
            self.save_app_settings()
        return ordered

    def category_options_menu(self, category, event):
        """Small popup menu from a category's gear icon: recolor or reorder it."""
        menu = tk.Menu(self, tearoff=0, bg=DARK_PANEL, fg=DARK_FG,
                        activebackground=DARK_HOVER, activeforeground=DARK_FG)
        menu.add_command(label=f"\U0001F3A8 Change '{category}' Color",
                          command=lambda: self.change_category_color(category))
        menu.add_separator()
        menu.add_command(label="\u25B2 Move Up", command=lambda: self.reorder_category(category, -1))
        menu.add_command(label="\u25BC Move Down", command=lambda: self.reorder_category(category, 1))
        menu.tk_popup(event.x_root, event.y_root)

    def change_category_color(self, category):
        """Open a native color picker and persist the chosen color for this category."""
        current = CATEGORY_COLORS.get(category, "#ffffff")
        chosen = colorchooser.askcolor(color=current, title=f"Color for '{category}'")
        if chosen and chosen[1]:
            CATEGORY_COLORS[category] = chosen[1]
            self.settings.setdefault("category_colors", {})[category] = chosen[1]
            self.save_app_settings()
            self.refresh_palette()

    def reorder_category(self, category, delta):
        """Move a category up/down in the palette's display order."""
        ordered = self.get_ordered_categories()
        if category not in ordered:
            return
        idx = ordered.index(category)
        new_idx = idx + delta
        if 0 <= new_idx < len(ordered):
            ordered[idx], ordered[new_idx] = ordered[new_idx], ordered[idx]
            self.category_order = ordered
            self.settings["category_order"] = ordered
            self.save_app_settings()
            self.refresh_palette()

    def build_palette(self):
        """Build the block palette"""
        for widget in self.palette_frame.winfo_children():
            widget.destroy()
        
        search_term = self.search_var.get().lower()
        
        if not self.blocks_by_category:
            tk.Label(
                self.palette_frame,
                text=f"No blocks for '{self.current_language}'\n\nAdd blocks to:\nlanguages/{self.current_language}/blocks/",
                bg=DARK_PANEL,
                fg="#888888",
                font=("Segoe UI", 9),
                justify=tk.CENTER
            ).pack(pady=50)
            return

        # "Switch Animation" setting: each header/item still gets built
        # fully immediately (all the actual widget construction below is
        # unchanged) - only the .pack() call that makes each one visible
        # gets deferred a little further than the last, so they cascade
        # in instead of all appearing in the same frame. Off by default
        # so browsing/searching stays instant; this is purely a look.
        animate = self.settings.get("animate_blocks", False)
        stagger_ms = 35
        self._palette_delay_index = 0

        def place(widget, **pack_kwargs):
            if not animate:
                widget.pack(**pack_kwargs)
                return
            delay = self._palette_delay_index * stagger_ms
            self._palette_delay_index += 1

            def do_pack():
                try:
                    if widget.winfo_exists():
                        widget.pack(**pack_kwargs)
                except tk.TclError:
                    pass  # palette was torn down before this fired - fine to ignore

            self.after(delay, do_pack)
        
        for category in self.get_ordered_categories():
            if category not in self.blocks_by_category:
                continue
            blocks_in_category = [
                b for b in self.blocks_by_category[category]
                if not search_term or search_term in get_block_attr(b, "display_name", "").lower() or
                   search_term in get_block_attr(b, "block_ui_description", {}).get("description", "").lower()
            ]
            
            if not blocks_in_category:
                continue
            
            # Category header
            category_header = tk.Frame(self.palette_frame, bg=DARK_PANEL)
            
            color = CATEGORY_COLORS.get(category, "#ffffff")
            
            tk.Label(
                category_header,
                text="▼",
                bg=DARK_PANEL,
                fg=color,
                font=("Segoe UI", 8)
            ).pack(side=tk.LEFT, padx=5)
            
            tk.Label(
                category_header,
                text=category.upper(),
                bg=DARK_PANEL,
                fg=color,
                font=("Segoe UI", 9, "bold")
            ).pack(side=tk.LEFT)
            
            tk.Label(
                category_header,
                text=f"({len(blocks_in_category)})",
                bg=DARK_PANEL,
                fg="#666666",
                font=("Segoe UI", 8)
            ).pack(side=tk.LEFT, padx=3)

            gear_label = tk.Label(
                category_header,
                text="\u2699",
                bg=DARK_PANEL,
                fg="#888888",
                font=("Segoe UI", 9),
                cursor="hand2"
            )
            gear_label.pack(side=tk.LEFT, padx=6)
            gear_label.bind(
                "<Button-1>",
                lambda e, cat=category: self.category_options_menu(cat, e)
            )

            place(category_header, fill=tk.X, pady=(10, 2))
            
            # Category blocks
            for block_module in sorted(blocks_in_category, key=lambda x: get_block_attr(x, "display_name", "")):
                item = PaletteBlockItem(self.palette_frame, block_module, self.add_block_to_workspace)
                place(item, fill=tk.X, pady=1)
    
    def refresh_palette(self):
        """Refresh the palette when language or search changes"""
        self.build_palette()
    
    def filter_palette(self, *args):
        """Filter palette based on search"""
        self.refresh_palette()
    
    def on_language_change(self, event=None):
        """Handle language change"""
        self.current_language = self.lang_var.get()
        if getattr(self, "tabs", None):
            self.tabs[self.active_tab_index]["language"] = self.current_language
        self.load_blocks_for_language(self.current_language)
        self.load_and_merge_custom_blocks()  # Re-merge custom blocks
        self.refresh_palette()
        self.project_blocks.clear()
        self.mark_active_tab_dirty()
        self.refresh_workspace()
        self.update_generated_code()
    
    def add_language_dialog(self):
        """Prompt user to add a new language folder"""
        def create_language():
            new_lang = entry.get().strip().lower()
            if not new_lang:
                messagebox.showwarning("Invalid", "Language name cannot be empty.")
                return
            new_path = os.path.join(self.languages_path, new_lang)
            if os.path.exists(new_path):
                messagebox.showwarning("Exists", f"Language '{new_lang}' already exists.")
                return
            blocks_path = os.path.join(new_path, "blocks")
            os.makedirs(blocks_path)

            # Every language gets a Raw Code escape-hatch block by default,
            # so there's always a way to write code the block set doesn't
            # cover yet, even before any other blocks exist for it.
            raw_code_path = os.path.join(blocks_path, "raw_code.py")
            with open(raw_code_path, "w") as f:
                f.write(make_raw_code_block_source(new_lang))

            self.maybe_notify("Created", f"Language '{new_lang}' created with a starter Custom Code block.")
            dialog.destroy()
            
            # Refresh language list and select new language
            langs = list(self.lang_combo['values'])
            langs.append(new_lang)
            langs.sort()
            self.lang_combo['values'] = langs
            self.lang_var.set(new_lang)
            self.on_language_change()
        
        dialog = tk.Toplevel(self)
        dialog.title("Add New Language")
        dialog.geometry("300x120")
        dialog.configure(bg=DARK_PANEL)
        dialog.transient(self)
        safe_grab_set(dialog)
        
        tk.Label(
            dialog,
            text="Enter language name:",
            bg=DARK_PANEL,
            fg=DARK_FG,
            font=("Segoe UI", 10)
        ).pack(pady=10)
        
        entry = tk.Entry(dialog, bg=DARK_BG, fg=DARK_FG, font=("Segoe UI", 10))
        entry.pack(pady=5, padx=10)
        entry.focus()
        
        btn_frame = tk.Frame(dialog, bg=DARK_PANEL)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Create", command=create_language).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        dialog.bind("<Return>", lambda e: create_language())
        dialog.bind("<Escape>", lambda e: dialog.destroy())

    def delete_language_dialog(self):
        """Delete the currently selected language's entire folder, after confirming."""
        lang = self.lang_var.get()
        langs = list(self.lang_combo['values'])

        if len(langs) <= 1:
            messagebox.showwarning("Can't Delete", "You need at least one language to remain.")
            return

        lang_path = os.path.join(self.languages_path, lang)
        confirm = messagebox.askyesno(
            "Delete Language",
            f"Delete language '{lang}'?\n\n"
            f"This permanently removes the folder:\n{lang_path}\n\n"
            f"All blocks (including custom ones) defined only for '{lang}' will be lost.\n"
            f"This cannot be undone."
        )
        if not confirm:
            return

        try:
            shutil.rmtree(lang_path)
        except Exception as e:
            messagebox.showerror("Delete Failed", f"Could not delete '{lang}':\n{e}")
            return

        # Also drop any saved custom blocks tagged for this language, so
        # they don't linger in custom_blocks.json pointing at a language
        # that no longer exists.
        self.custom_blocks = [
            cb for cb in self.load_custom_blocks_data()
            if cb.get("language", "all") != lang
        ]
        self.save_custom_blocks_data(self.custom_blocks)

        langs.remove(lang)
        self.lang_combo['values'] = langs
        self.lang_var.set(langs[0])
        self.on_language_change()
        self.maybe_notify("Deleted", f"Language '{lang}' deleted.")

    def settings_dialog(self):
        """App settings: default language, run/compile commands, and
        delete-confirmation preference. Nothing here applies until you
        hit Save & Close - Cancel discards changes."""
        dialog = tk.Toplevel(self)
        dialog.title("Settings")
        dialog.geometry("520x420")
        dialog.configure(bg=DARK_PANEL)
        dialog.transient(self)
        safe_grab_set(dialog)

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        header = tk.Frame(dialog, bg="#569cd6", height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header, text="\u2699 Settings", bg="#569cd6", fg="#000000",
            font=("Segoe UI", 13, "bold")
        ).pack(side=tk.LEFT, padx=20, pady=15)

        body = tk.Frame(dialog, bg=DARK_PANEL)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)

        def add_row(label_text, help_text=None):
            row = tk.Frame(body, bg=DARK_PANEL)
            row.pack(fill=tk.X, pady=(0, 4))
            tk.Label(
                row, text=label_text, bg=DARK_PANEL, fg=DARK_FG,
                font=("Segoe UI", 9, "bold"), width=20, anchor="w"
            ).pack(side=tk.LEFT)
            return row

        def add_help(text):
            tk.Label(
                body, text=text, bg=DARK_PANEL, fg="#888888",
                font=("Segoe UI", 8, "italic"), anchor="w", justify=tk.LEFT, wraplength=460
            ).pack(fill=tk.X, pady=(0, 12))

        # --- Default language ---
        row = add_row("Default language:")
        lang_var = tk.StringVar(value=self.settings.get("default_language", "python"))
        lang_combo = ttk.Combobox(
            row, textvariable=lang_var, values=self.get_available_languages(),
            state="readonly", width=20
        )
        lang_combo.pack(side=tk.LEFT)
        add_help("Which language loads automatically the next time Blockliner starts.")

        # --- Python command ---
        row = add_row("Python command:")
        python_cmd_var = tk.StringVar(value=self.settings.get("python_command", "python3"))
        tk.Entry(
            row, textvariable=python_cmd_var, bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=DARK_BORDER, width=22
        ).pack(side=tk.LEFT, ipady=3)
        add_help("Command used to run generated Python code (e.g. 'python3' or 'python').")

        # --- C++ compiler ---
        row = add_row("C++ compiler:")
        cpp_var = tk.StringVar(value=self.settings.get("cpp_compiler", "g++"))
        tk.Entry(
            row, textvariable=cpp_var, bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=DARK_BORDER, width=22
        ).pack(side=tk.LEFT, ipady=3)
        add_help("Command used to compile generated C++ code.")

        # --- Terminal command ---
        row = add_row("Terminal command:")
        terminal_var = tk.StringVar(value=self.settings.get("terminal_command", "gnome-terminal --"))
        tk.Entry(
            row, textvariable=terminal_var, bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=DARK_BORDER, width=22
        ).pack(side=tk.LEFT, ipady=3)
        add_help(
            "How 'Run in Terminal' opens a terminal window. Linux desktops vary - try "
            "'gnome-terminal --', 'xterm -e', or 'mate-terminal --' depending on what's installed."
        )

        # --- Confirm before delete ---
        confirm_var = tk.BooleanVar(value=self.settings.get("confirm_delete", True))
        tk.Checkbutton(
            body, text="Ask for confirmation before deleting blocks",
            variable=confirm_var, bg=DARK_PANEL, fg=DARK_FG, selectcolor=DARK_BG,
            activebackground=DARK_PANEL, activeforeground=DARK_FG,
            font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(5, 0))

        # --- Success notification popups ---
        notify_var = tk.BooleanVar(value=self.settings.get("show_notifications", True))
        tk.Checkbutton(
            body, text="Show confirmation popups (e.g. \"Block deleted successfully\")",
            variable=notify_var, bg=DARK_PANEL, fg=DARK_FG, selectcolor=DARK_BG,
            activebackground=DARK_PANEL, activeforeground=DARK_FG,
            font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(5, 0))

        # --- Switch animation ---
        animate_var = tk.BooleanVar(value=self.settings.get("animate_blocks", False))
        tk.Checkbutton(
            body, text="Animate the block palette loading in (cascades in instead of appearing instantly)",
            variable=animate_var, bg=DARK_PANEL, fg=DARK_FG, selectcolor=DARK_BG,
            activebackground=DARK_PANEL, activeforeground=DARK_FG,
            font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(5, 0))

        # --- Save / Cancel ---
        btn_frame = tk.Frame(dialog, bg=DARK_PANEL)
        btn_frame.pack(fill=tk.X, padx=20, pady=(0, 20))

        def on_save_close():
            self.settings["default_language"] = lang_var.get()
            self.settings["python_command"] = python_cmd_var.get().strip() or "python3"
            self.settings["cpp_compiler"] = cpp_var.get().strip() or "g++"
            self.settings["terminal_command"] = terminal_var.get().strip() or "gnome-terminal --"
            self.settings["confirm_delete"] = confirm_var.get()
            self.settings["show_notifications"] = notify_var.get()
            self.settings["animate_blocks"] = animate_var.get()
            self.save_app_settings()
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        tk.Button(
            btn_frame, text="\U0001F4BE Save & Close", bg="#4ec9b0", fg="#000000",
            font=("Segoe UI", 10, "bold"), relief=tk.FLAT, cursor="hand2",
            command=on_save_close, padx=15, pady=6
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_frame, text="Cancel", bg="#888888", fg="white",
            font=("Segoe UI", 10), relief=tk.FLAT, cursor="hand2",
            command=on_cancel, padx=15, pady=6
        ).pack(side=tk.LEFT, padx=5)

        dialog.bind("<Escape>", lambda e: on_cancel())

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
            text="👈 Click blocks in palette to add them here",
            bg=DARK_BG,
            fg="#555555",
            font=("Segoe UI", 12, "italic")
        )
        self.empty_label.pack(expand=True, pady=150)
    
    def refresh_node_nav(self):
        """Rebuild the node navigation controls in the workspace header -
        same rebuild-from-scratch pattern as refresh_tab_bar()."""
        for widget in self.node_nav_frame.winfo_children():
            widget.destroy()

        if not getattr(self, "tabs", None):
            return
        if self.view_mode == "files":
            tk.Label(
                self.node_nav_frame, text="\U0001F4C1 All Files \u2014 choose a file",
                bg=DARK_BG, fg="#888888", font=("Segoe UI", 9)
            ).pack(side=tk.LEFT, padx=(0, 10))
            tk.Button(
                self.node_nav_frame, text="+ New File", bg="#3a3a3a", fg=DARK_FG,
                relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                command=self.new_tab
            ).pack(side=tk.LEFT, padx=(0, 10))
            code_toggle_active = self.files_view_code_mode
            tk.Button(
                self.node_nav_frame,
                text=("\U0001F5BC View Canvas" if code_toggle_active else "\U0001F4C4 View Code"),
                bg=(DARK_ACCENT if code_toggle_active else "#3a3a3a"),
                fg=("#ffffff" if code_toggle_active else DARK_FG),
                relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                command=self.toggle_files_view_code_mode
            ).pack(side=tk.LEFT)
            return

        tab = self.tabs[self.active_tab_index]
        nodes = tab.get("nodes", [])

        if self.view_mode == "file":
            path = tab.get("file_view_path", [])
            crumb_parts = [tab["title"]]
            for node_id in path:
                node = find_node_by_id(tab["nodes"], node_id)
                if node:
                    crumb_parts.append(node["name"])
            crumb = "  \u203A  ".join(["\U0001F4C4 " + crumb_parts[0]] + crumb_parts[1:])
            if path:
                tk.Button(
                    self.node_nav_frame, text="\u2190 Back", bg="#3a3a3a", fg=DARK_FG,
                    relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                    command=self.file_view_go_back
                ).pack(side=tk.LEFT, padx=(0, 10))
            else:
                tk.Button(
                    self.node_nav_frame, text="\u2190 Files", bg="#3a3a3a", fg=DARK_FG,
                    relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                    command=self.switch_to_files_view
                ).pack(side=tk.LEFT, padx=(0, 10))
            tk.Label(
                self.node_nav_frame, text=f"{crumb} \u2014 choose a node",
                bg=DARK_BG, fg="#888888", font=("Segoe UI", 9)
            ).pack(side=tk.LEFT, padx=(0, 10))
            tk.Button(
                self.node_nav_frame, text="+ New Node", bg="#3a3a3a", fg=DARK_FG,
                relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                command=self.create_node
            ).pack(side=tk.LEFT, padx=(0, 4))
            tk.Button(
                self.node_nav_frame, text="+ New Category", bg="#3a3a3a", fg=DARK_FG,
                relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                command=self.create_category
            ).pack(side=tk.LEFT, padx=(0, 10))
            code_toggle_active = self.file_view_code_mode
            tk.Button(
                self.node_nav_frame,
                text=("\U0001F5BC View Canvas" if code_toggle_active else "\U0001F4C4 View Code"),
                bg=(DARK_ACCENT if code_toggle_active else "#3a3a3a"),
                fg=("#ffffff" if code_toggle_active else DARK_FG),
                relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                command=self.toggle_file_view_code_mode
            ).pack(side=tk.LEFT)
        else:
            active_node = self.get_active_node(tab)
            crumb = f"\U0001F4C4 {tab['title']}  \u203A  \U0001F9E9 {active_node['name']}"
            tk.Label(
                self.node_nav_frame, text=crumb, bg=DARK_BG, fg="#888888",
                font=("Segoe UI", 9)
            ).pack(side=tk.LEFT, padx=(0, 10))
            # Only worth surfacing "view all nodes" once a file actually
            # has more than one top-level node, or that one node is a
            # class/category with something inside it - otherwise it's
            # a button to a screen that only ever shows the one thing
            # you're already in.
            if len(nodes) > 1 or (len(nodes) == 1 and nodes[0].get("kind") in ("class", "category")):
                tk.Button(
                    self.node_nav_frame, text="\U0001F5C2 Nodes",
                    bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT, cursor="hand2",
                    font=("Segoe UI", 9), command=self.switch_to_file_view
                ).pack(side=tk.LEFT, padx=(0, 4))
            tk.Button(
                self.node_nav_frame, text="+ New Node", bg="#3a3a3a", fg=DARK_FG,
                relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                command=self.create_node
            ).pack(side=tk.LEFT)

    def switch_to_file_view(self):
        """Always resets to the top level of the file view - a user
        clicking "Nodes" from inside a nested method wants their
        reference frame reset to the whole file, not to resume
        mid-navigation from wherever they last left it."""
        tab = self.tabs[self.active_tab_index]
        tab["file_view_path"] = []
        self.view_mode = "file"
        self.file_view_code_mode = False
        self.refresh_workspace()

    def switch_to_files_view(self):
        """Files layer (top of the three-layer nav model): shows every
        open tab as a box on workspace_canvas, wired by import_module-
        derived file_references. Doesn't touch which tab is "active" -
        active_tab_index still matters for language/palette state - it
        just changes what's drawn. Always resets to the canvas (not the
        code view), mirroring switch_to_file_view()'s reset-to-top
        behavior."""
        self.view_mode = "files"
        self.files_view_code_mode = False
        self.refresh_workspace()
        self.refresh_tab_bar()

    def toggle_files_view_code_mode(self):
        """The Files layer's 'View Code' toggle - swaps the file-boxes
        canvas and the stacked code view, never shows both at once
        ("separate, not split - both would be too messy")."""
        self.files_view_code_mode = not self.files_view_code_mode
        self.refresh_workspace()

    def toggle_file_view_code_mode(self):
        """The Nodes layer's 'View Code' toggle - same idea one level
        down, swaps that file's node/wire canvas for its generated
        code. This is what replaces the old always-visible right-hand
        Generated Code panel at this layer (see
        update_right_panel_visibility) - the panel itself stays
        completely unchanged at the Blocks layer per the settled
        design, and Export/Run/Code->Blocks keep working regardless of
        which of the two is on screen, since they read generated code
        straight from generate_code_for_tab()/self.code_text rather
        than from whatever's currently drawn."""
        self.file_view_code_mode = not self.file_view_code_mode
        self.refresh_workspace()

    def open_file_from_files_view(self, index):
        """Enter a specific file from the Files layer, landing on its
        Nodes layer (the per-tab node/wire canvas) - matches how
        open_node() from the Nodes layer lands you in the Blocks layer.
        Unlike switch_to_tab(), this must work even when index is
        already the active tab (clicking "Open" on the current file
        from the Files layer is a normal thing to do)."""
        if not (0 <= index < len(self.tabs)):
            return
        self.sync_active_tab_state()
        self.active_tab_index = index
        tab = self.tabs[index]
        self.current_language = tab["language"]
        self.project_blocks = self.get_active_node(tab)["blocks"]
        tab["file_view_path"] = []
        self.view_mode = "file"
        self.lang_var.set(self.current_language)
        self.load_blocks_for_language(self.current_language)
        self.load_and_merge_custom_blocks()
        self.refresh_palette()
        self.refresh_workspace()
        self.refresh_tab_bar()

    def file_view_go_back(self):
        tab = self.tabs[self.active_tab_index]
        if tab.get("file_view_path"):
            tab["file_view_path"].pop()
        self.refresh_workspace()

    def get_current_node_list(self, tab):
        """The list of nodes currently shown in file view - either the
        tab's top-level nodes, or a class node's child_nodes if the
        file view has navigated inside one (see file_view_path)."""
        nodes = tab["nodes"]
        for node_id in tab.get("file_view_path", []):
            parent = find_node_by_id(tab["nodes"], node_id)
            nodes = parent["child_nodes"] if parent else []
        return nodes

    def open_node(self, node_id):
        """Enter a node. A function-kind node opens the B1 block editor
        scoped to it. A class-kind or category-kind node has no blocks
        of its own to edit - it holds other nodes - so "opening" it
        instead navigates the file view one level deeper into its
        child_nodes. Category (Phase D) is a pure visual folder with
        zero codegen effect; class actually wraps its children in
        generated code - the two behave identically here since both
        are just organizational containers from the navigation's point
        of view."""
        tab = self.tabs[self.active_tab_index]
        node = find_node_by_id(tab["nodes"], node_id)
        if node is None:
            return
        if node.get("kind") in ("class", "category"):
            tab.setdefault("file_view_path", []).append(node_id)
            self.view_mode = "file"
            self.refresh_workspace()
            return
        tab["active_node_id"] = node_id
        self.project_blocks = node["blocks"]
        self.view_mode = "node"
        self.refresh_workspace()

    def create_node(self, pos=None):
        """Add a new, empty function-kind node at the current file-view
        depth (top-level, or inside whichever class/category is
        currently open) and open it directly - naming/organizing
        several nodes is easiest done from inside the one you just
        made, not by round-tripping through the file view."""
        tab = self.tabs[self.active_tab_index]
        target_list = self.get_current_node_list(tab) if self.view_mode == "file" else tab["nodes"]
        name = simpledialog.askstring(
            "New Node", "Node name:", initialvalue=f"Node {len(target_list) + 1}"
        )
        if name is None:
            return
        name = name.strip() or f"Node {len(target_list) + 1}"
        new_node = make_node(name, node_id=str(uuid.uuid4())[:8], blocks=[])
        target_list.append(new_node)
        self.mark_active_tab_dirty()
        if pos is not None:
            # Right-click creation: drop it under the cursor and stay on
            # the canvas so the placement is actually visible.
            new_node["canvas_x"], new_node["canvas_y"] = pos
            self.refresh_workspace()
            return
        self.open_node(new_node["id"])

    def create_category(self, pos=None):
        """Phase D: add a new, empty category node (a pure visual
        folder - zero codegen effect, see make_node's docstring) at the
        current file-view depth, and navigate straight into it via
        open_node so nodes can be added to it immediately. Only
        available from file view - a category is an organizational
        concept on the canvas, not something reachable from inside a
        function's block editor."""
        tab = self.tabs[self.active_tab_index]
        target_list = self.get_current_node_list(tab)
        name = simpledialog.askstring(
            "New Category", "Category name:", initialvalue=f"Category {len(target_list) + 1}"
        )
        if name is None:
            return
        name = name.strip() or f"Category {len(target_list) + 1}"
        new_category = make_node(
            name, node_id=str(uuid.uuid4())[:8], kind="category", child_nodes=[]
        )
        target_list.append(new_category)
        self.mark_active_tab_dirty()
        if pos is not None:
            new_category["canvas_x"], new_category["canvas_y"] = pos
            self.refresh_workspace()
            return
        self.open_node(new_category["id"])

    def render_files_view(self):
        """Files layer: every open tab as a draggable box on
        workspace_canvas, reusing C2's box/wire canvas mechanics one
        level up - files as boxes instead of nodes, wires resolved
        from import_module blocks (recompute_file_references) the same
        way func_call resolves node-to-node in the Nodes layer. Shares
        the "fileview" canvas tag with the Nodes layer's own boxes/
        wires purely so _update_fileview_scrollregion's bbox lookup
        works unchanged for either layer."""
        self._filesview_boxes = {}
        self.workspace_canvas.delete("wire_drag_temp")

        if not self.tabs:
            self.show_empty_state()
            return

        self.assign_default_tab_canvas_positions()

        for index, tab in enumerate(self.tabs):
            self.create_filesview_file_box(index, tab)

        self.workspace_frame.update_idletasks()
        self.draw_file_wires()
        self._update_fileview_scrollregion()

    def create_filesview_file_box(self, index, tab):
        """Build one tab's draggable box and place it on
        workspace_canvas at its stored (canvas_x, canvas_y). Visually
        distinct from a Nodes-layer node box (blue accent, file icon)
        so the two layers are never mistaken for each other in a
        screenshot. No wire-drag port here - unlike func_call wires
        (C3), an import wire is created by typing into an
        import_module block's module field, not by dragging."""
        box_color = "#2a5a8a"
        box = tk.Frame(
            self.workspace_canvas, bg=BLOCK_BG, highlightthickness=2,
            highlightbackground=DARK_BORDER
        )

        def _open(_e=None, idx=index):
            self.open_file_from_files_view(idx)

        header = tk.Frame(box, bg=box_color, height=36, cursor="fleur")
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        label_text = tab["title"] + (" \u25CF" if tab.get("dirty") else "")
        name_label = tk.Label(
            header, text=f"\U0001F4C4 {label_text}",
            bg=box_color, fg="#ffffff",
            font=("Segoe UI", 10, "bold"), anchor="w", cursor="fleur"
        )
        name_label.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)

        body = tk.Frame(box, bg=BLOCK_BG)
        body.pack(fill=tk.X, padx=10, pady=8)
        node_count = len(tab.get("nodes", []))
        tk.Label(
            body, text=f"{node_count} node{'s' if node_count != 1 else ''} \u2022 {tab['language']}",
            bg=BLOCK_BG, fg="#888888", font=("Segoe UI", 9)
        ).pack(side=tk.LEFT)
        tk.Button(
            body, text="Open \u2192", bg="#3a3a3a", fg=DARK_FG,
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
            command=_open
        ).pack(side=tk.RIGHT)

        win_id = self.workspace_canvas.create_window(
            tab["canvas_x"], tab["canvas_y"], anchor="nw", window=box,
            tags=("fileview", "file_box")
        )
        self._filesview_boxes[index] = (win_id, box)
        self._bind_context_recursive(
            box, lambda e, idx=index: self._on_file_box_right_click(e, idx))

        # Same press/motion/release-with-threshold drag pattern as
        # create_fileview_node_box(), operating on the tab's canvas_x/
        # canvas_y instead of a node's.
        drag_state = {"dragging": False, "start_x": 0, "start_y": 0,
                      "tab_x0": 0, "tab_y0": 0}

        def _press(e, idx=index):
            drag_state["dragging"] = False
            drag_state["start_x"] = e.x_root
            drag_state["start_y"] = e.y_root
            if not (0 <= idx < len(self.tabs)):
                return
            t = self.tabs[idx]
            drag_state["tab_x0"] = t["canvas_x"]
            drag_state["tab_y0"] = t["canvas_y"]

        def _motion(e, idx=index):
            dx = e.x_root - drag_state["start_x"]
            dy = e.y_root - drag_state["start_y"]
            if not drag_state["dragging"] and (abs(dx) > 4 or abs(dy) > 4):
                drag_state["dragging"] = True
            if not drag_state["dragging"]:
                return
            if not (0 <= idx < len(self.tabs)):
                return
            t = self.tabs[idx]
            new_x = drag_state["tab_x0"] + dx
            new_y = drag_state["tab_y0"] + dy
            t["canvas_x"], t["canvas_y"] = new_x, new_y
            wid, _ = self._filesview_boxes.get(idx, (None, None))
            if wid is not None:
                self.workspace_canvas.coords(wid, new_x, new_y)
            self.draw_file_wires()

        def _release(e, idx=index):
            drag_state["dragging"] = False
            self._update_fileview_scrollregion()

        for w in (header, name_label):
            w.bind("<ButtonPress-1>", _press)
            w.bind("<B1-Motion>", _motion)
            w.bind("<ButtonRelease-1>", _release)
            w.bind("<Double-Button-1>", _open)

    def draw_file_wires(self):
        """Files-layer equivalent of draw_wires(): redraw every derived
        import edge (tab['file_references']) as a curved connector
        between two file boxes. Pure rendering, never mutates."""
        self.workspace_canvas.delete("wire")
        for index, tab in enumerate(self.tabs):
            if index not in self._filesview_boxes:
                continue
            for target_index in tab.get("file_references", []):
                if target_index not in self._filesview_boxes:
                    continue
                self._draw_one_file_wire(index, target_index)

    def _draw_one_file_wire(self, source_index, target_index):
        _, src_widget = self._filesview_boxes[source_index]
        _, dst_widget = self._filesview_boxes[target_index]
        sw = src_widget.winfo_width() or 220
        sh = src_widget.winfo_height() or 70
        dh = dst_widget.winfo_height() or 70
        src_tab = self.tabs[source_index]
        dst_tab = self.tabs[target_index]

        x0 = src_tab["canvas_x"] + sw
        y0 = src_tab["canvas_y"] + sh / 2
        x1 = dst_tab["canvas_x"]
        y1 = dst_tab["canvas_y"] + dh / 2

        pull = max(abs(x1 - x0) * 0.5, 40)
        p0 = (x0, y0)
        p1 = (x0 + pull, y0)
        p2 = (x1 - pull, y1)
        p3 = (x1, y1)

        tag = f"file_wire_{source_index}_{target_index}"
        self.workspace_canvas.create_line(
            *self._bezier_points(p0, p1, p2, p3), smooth=True,
            fill="#4a90d9", width=2, tags=("fileview", "wire", tag)
        )
        self.workspace_canvas.create_oval(
            x1 - 4, y1 - 4, x1 + 4, y1 + 4, fill="#4a90d9", outline="",
            tags=("fileview", "wire", tag)
        )

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

    def toggle_palette(self):
        """Collapse / expand the left block palette (edge-strip click)."""
        self.panels.toggle("palette")

    def _on_panel_visibility_changed(self, panel_id, visible):
        if panel_id == "palette":
            self.palette_strip_glyph.config(text="\u25c2" if visible else "\u25b8")

    def _palette_strip_hover(self, on):
        bg = DARK_BORDER if on else DARK_PANEL
        self.palette_strip.config(bg=bg)
        self.palette_strip_glyph.config(bg=bg, fg="#ffffff" if on else "#888888")

    # ------------------------------------------------------------------
    # Workspace right-click menu (ComfyUI-style): top entry adds
    # something appropriate to the current layer, below it a Panels
    # submenu shows/hides parts of the window.
    # ------------------------------------------------------------------

    def _bind_workspace_context_menu(self):
        """Right-click on EMPTY workspace area (canvas or the block-editor
        frame). Node/file boxes and blocks are child widgets, so a click on
        them never reaches these bindings."""
        if sys.platform == "darwin":
            seqs = ("<Button-2>", "<Control-Button-1>")
        else:
            seqs = ("<Button-3>",)
        for w in (self.workspace_canvas, self.workspace_frame):
            for seq in seqs:
                w.bind(seq, self._on_workspace_right_click)

    def _on_workspace_right_click(self, event):
        x, y = self._canvas_coords_from_event(event)
        menu = self.build_workspace_menu((max(0, x), max(0, y)))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _new_menu(self, parent):
        return tk.Menu(parent, tearoff=0, bg=DARK_PANEL, fg=DARK_FG,
                       activebackground=DARK_HOVER, activeforeground=DARK_FG)

    def build_workspace_menu(self, canvas_pos):
        """Build (don't show) the right-click menu for the current layer.
        canvas_pos is where the click landed, in canvas coordinates, used
        to place new nodes/categories/files under the cursor."""
        menu = self._new_menu(self)
        menu._vars = []  # keep BooleanVars alive for the checkbuttons

        in_code_view = (
            (self.view_mode == "file" and self.file_view_code_mode)
            or (self.view_mode == "files" and self.files_view_code_mode)
        )
        added = False
        if not in_code_view:
            if self.view_mode == "node":
                self._add_block_cascade(menu)
                added = True
            elif self.view_mode == "file":
                menu.add_command(label="\u2795 Add node",
                                 command=lambda: self.create_node(pos=canvas_pos))
                menu.add_command(label="\U0001F4C1 Add category",
                                 command=lambda: self.create_category(pos=canvas_pos))
                added = True
            elif self.view_mode == "files":
                menu.add_command(label="\u2795 New file",
                                 command=lambda: self.create_file_at(canvas_pos))
                added = True
        if added:
            menu.add_separator()

        panels = self._new_menu(menu)
        v = tk.BooleanVar(value=self.panels.is_visible("palette"))
        menu._vars.append(v)
        panels.add_checkbutton(label="Block Palette", variable=v,
                               command=self.toggle_palette)
        if self.view_mode == "node":  # the code panel only exists at Blocks layer
            v2 = tk.BooleanVar(value=self.panels.is_visible("code"))
            menu._vars.append(v2)
            panels.add_checkbutton(label="Generated Code", variable=v2,
                                   command=self.toggle_code_panel)
        menu.add_cascade(label="\u25a4 Panels", menu=panels)
        return menu

    def _add_block_cascade(self, menu):
        """'Add block' > category > block, same source/order as the palette."""
        sub = self._new_menu(menu)
        any_block = False
        for category in self.get_ordered_categories():
            blocks = self.blocks_by_category.get(category) or []
            if not blocks:
                continue
            any_block = True
            cat_menu = self._new_menu(sub)
            for b in blocks:
                cat_menu.add_command(
                    label=get_block_attr(b, "display_name", "Unknown"),
                    command=lambda b=b: self.add_block_to_workspace(b))
            sub.add_cascade(label=category, menu=cat_menu,
                            foreground=CATEGORY_COLORS.get(category, DARK_FG))
        menu.add_cascade(label="\u2795 Add block", menu=sub,
                         state=tk.NORMAL if any_block else tk.DISABLED)

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

    # --- box menus ---

    def _context_seqs(self):
        return ("<Button-2>", "<Control-Button-1>") if sys.platform == "darwin" else ("<Button-3>",)

    def _bind_context_recursive(self, widget, handler):
        for seq in self._context_seqs():
            widget.bind(seq, handler)
        for child in widget.winfo_children():
            self._bind_context_recursive(child, handler)

    def _popup(self, menu, event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def build_node_menu(self, node_id):
        tab = self.tabs[self.active_tab_index]
        node = find_node_by_id(tab["nodes"], node_id)
        menu = self._new_menu(self)
        if node is None:
            return menu
        locked = bool(node.get("locked"))
        off = tk.DISABLED if locked else tk.NORMAL
        menu.add_command(label="Open", command=lambda: self.open_node(node_id))
        menu.add_command(label="Rename\u2026", state=off,
                         command=lambda: self.rename_node_dialog(node_id))
        dests = self.move_destinations(tab, node)
        move = self._new_menu(menu)
        for label, lst in dests:
            move.add_command(label=label,
                             command=lambda lst=lst: self.move_node(tab, node, lst))
        menu.add_cascade(label="Move to", menu=move,
                         state=tk.NORMAL if dests else tk.DISABLED)
        menu.add_separator()
        menu.add_command(label="Delete\u2026", state=off,
                         command=lambda: self.delete_node_dialog(node_id))
        return menu

    def build_file_menu(self, index):
        menu = self._new_menu(self)
        menu.add_command(label="Open", command=lambda: self.open_file_from_files_view(index))
        menu.add_command(label="Rename\u2026", command=lambda: self.rename_file_dialog(index))
        menu.add_separator()
        menu.add_command(label="Close file", command=lambda: self.close_file_from_files_view(index))
        return menu

    def _on_node_box_right_click(self, event, node_id):
        return self._popup(self.build_node_menu(node_id), event)

    def _on_file_box_right_click(self, event, index):
        return self._popup(self.build_file_menu(index), event)

    def toggle_code_panel(self):
        """User show/hide of the Generated Code panel (Blocks layer). Kept
        as a flag because update_right_panel_visibility() runs on every
        refresh and would otherwise force the panel back on."""
        self._code_panel_user_hidden = not getattr(self, "_code_panel_user_hidden", False)
        self.update_right_panel_visibility()

    def update_right_panel_visibility(self):
        """The always-visible right-hand Generated Code panel is now
        exclusively a Blocks-layer (view_mode == "node") feature, per
        the settled design - the Files and Nodes layers each got their
        own in-canvas 'View Code' toggle instead (render_files_code_view/
        render_file_code_view), so showing this panel at the same time
        would be exactly the redundant split the toggle design was
        chosen to avoid. Hiding it never affects Export/Run/Code->Blocks
        - self.code_text is kept current regardless (update_generated_code()
        now runs unconditionally in refresh_workspace), a Tk widget's
        .get() works whether or not it's currently on screen."""
        self.panels.set_visible(
            "code",
            self.view_mode == "node" and not getattr(self, "_code_panel_user_hidden", False))

    def render_file_view(self):
        """Phase C2: freeform ComfyUI-style canvas. Node boxes sit at
        explicit, draggable (canvas_x, canvas_y) positions and are
        drawn directly on workspace_canvas (via create_window) rather
        than pack()-stacked into workspace_frame, so they can be placed
        anywhere. Curved wires are drawn between them from the derived
        `references` graph (see recompute_references/draw_wires) -
        double-clicking a wire removes the func_call block that
        produced it. Shows whichever level of the hierarchy
        file_view_path points at (top-level nodes, or a class's
        child_nodes). Double-click a box (or its Open button) enters
        that node via open_node()."""
        tab = self.tabs[self.active_tab_index]
        nodes = self.get_current_node_list(tab)

        self._fileview_boxes = {}
        # Defensive: a refresh mid wire-drag (e.g. triggered by something
        # else while dragging) would otherwise leave a dangling temp line
        # and stale hover state pointing at boxes that are about to be
        # destroyed and recreated.
        self.workspace_canvas.delete("wire_drag_temp")
        self._wire_drag_source = None
        self._wire_drag_temp_id = None
        self._wire_drag_hover_id = None

        if not nodes:
            self.show_empty_state()
            return

        self.assign_default_canvas_positions(nodes)

        for node in nodes:
            self.create_fileview_node_box(node)

        self.workspace_frame.update_idletasks()
        self.draw_wires()
        self._update_fileview_scrollregion()

    def assign_default_canvas_positions(self, nodes):
        """Give any node without a stored canvas position a sensible
        default grid slot (3 per row) so a freshly created node - or a
        file that predates C2 entirely - always has somewhere valid to
        render. Positions aren't a real persistence format yet (see
        carry-forward item 4 in the handoff) - they just live on the
        in-memory node dict like everything else in Phase B/C. Never
        overwrites a position the user has already dragged a node to."""
        col_width, row_height = 260, 150
        start_x, start_y = 30, 20
        per_row = 3
        idx = 0
        for node in nodes:
            if "canvas_x" not in node or "canvas_y" not in node:
                row, col = divmod(idx, per_row)
                node["canvas_x"] = start_x + col * col_width
                node["canvas_y"] = start_y + row * row_height
            idx += 1

    def create_fileview_node_box(self, node):
        """Build one node's draggable box and place it on
        workspace_canvas at its stored position. Visually identical to
        the pre-C2 B2/B3 box (same icon/lock/color scheme) - only how
        it's placed and how it responds to the mouse has changed.

        Phase D: a third kind, "category", joins "function"/"class" -
        a pure visual folder (zero codegen effect, unlike class) that
        can hold anything, styled distinctly (folder icon, gold) so
        it's never mistaken for a class node at a glance."""
        kind = node.get("kind", "function")
        is_class = kind == "class"
        is_category = kind == "category"
        is_container = is_class or is_category
        if is_category:
            box_color = "#8a6a2a"
        elif is_class:
            box_color = "#5a4a8a"
        else:
            box_color = CATEGORY_COLORS.get("Basic", "#4a4a4a")
        text_fg = "#ffffff" if is_container else "#000000"
        box = tk.Frame(
            self.workspace_canvas, bg=BLOCK_BG, highlightthickness=2,
            highlightbackground=DARK_BORDER
        )

        def _open(_e=None, nid=node["id"]):
            self.open_node(nid)

        if is_category:
            icon = "\U0001F4C1"  # folder
        elif is_class:
            icon = "\U0001F3DB"  # classical building
        else:
            icon = "\U0001F9E9"  # puzzle piece
        header = tk.Frame(box, bg=box_color, height=36, cursor="fleur")
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        name_label = tk.Label(
            header, text=f"{icon} {node['name']}",
            bg=box_color, fg=text_fg,
            font=("Segoe UI", 10, "bold"), anchor="w", cursor="fleur"
        )
        name_label.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)

        # Phase C3: an output "port" handle, only on function-kind nodes
        # in a language that actually has a func_call block (HTML has
        # none, so wiring makes no sense there). Neither class nor
        # category nodes wire directly - they hold other nodes, not
        # blocks. Dragging from this handle to another node's box calls
        # that node - see _port_press/_port_motion/_port_release below.
        can_wire = (not is_container) and "func_call" in self.blocks
        port = None
        if can_wire:
            port = tk.Label(
                header, text="\u25cf", bg=box_color, fg=text_fg,
                font=("Segoe UI", 12, "bold"), cursor="crosshair"
            )
            port.pack(side=tk.RIGHT, padx=(4, 8))

        if node.get("locked"):
            tk.Label(
                header, text="\U0001F512", bg=box_color, fg=text_fg,
            ).pack(side=tk.RIGHT, padx=8)

        body = tk.Frame(box, bg=BLOCK_BG)
        body.pack(fill=tk.X, padx=10, pady=8)
        if is_container:
            count = len(node.get("child_nodes", []))
            label_text = f"{count} node{'s' if count != 1 else ''} inside"
        else:
            count = len(node["blocks"])
            label_text = f"{count} block{'s' if count != 1 else ''}"
        tk.Label(
            body, text=label_text,
            bg=BLOCK_BG, fg="#888888", font=("Segoe UI", 9)
        ).pack(side=tk.LEFT)
        tk.Button(
            body, text="Open \u2192", bg="#3a3a3a", fg=DARK_FG,
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
            command=_open
        ).pack(side=tk.RIGHT)

        win_id = self.workspace_canvas.create_window(
            node["canvas_x"], node["canvas_y"], anchor="nw", window=box,
            tags=("fileview", "node_box")
        )
        self._fileview_boxes[node["id"]] = (win_id, box)
        self._bind_context_recursive(
            box, lambda e, nid=node["id"]: self._on_node_box_right_click(e, nid))

        # Dragging is grabbed from the header only, so the Open button
        # and double-click-to-open both keep working undisturbed. A
        # small movement threshold distinguishes an actual drag from a
        # click/double-click, since a plain click never moves the
        # mouse far enough to cross it.
        drag_state = {"dragging": False, "start_x": 0, "start_y": 0,
                      "node_x0": 0, "node_y0": 0}

        def _press(e, nid=node["id"]):
            drag_state["dragging"] = False
            drag_state["start_x"] = e.x_root
            drag_state["start_y"] = e.y_root
            n = find_node_by_id(self.tabs[self.active_tab_index]["nodes"], nid)
            if n is None:
                return
            drag_state["node_x0"] = n["canvas_x"]
            drag_state["node_y0"] = n["canvas_y"]

        def _motion(e, nid=node["id"]):
            dx = e.x_root - drag_state["start_x"]
            dy = e.y_root - drag_state["start_y"]
            if not drag_state["dragging"] and (abs(dx) > 4 or abs(dy) > 4):
                drag_state["dragging"] = True
            if not drag_state["dragging"]:
                return
            n = find_node_by_id(self.tabs[self.active_tab_index]["nodes"], nid)
            if n is None:
                return
            new_x = drag_state["node_x0"] + dx
            new_y = drag_state["node_y0"] + dy
            n["canvas_x"], n["canvas_y"] = new_x, new_y
            wid, _ = self._fileview_boxes.get(nid, (None, None))
            if wid is not None:
                self.workspace_canvas.coords(wid, new_x, new_y)
            self.draw_wires()

        def _release(e, nid=node["id"]):
            if drag_state["dragging"]:
                self.mark_active_tab_dirty()
                self._update_fileview_scrollregion()
            drag_state["dragging"] = False

        for w in (header, name_label):
            w.bind("<ButtonPress-1>", _press)
            w.bind("<B1-Motion>", _motion)
            w.bind("<ButtonRelease-1>", _release)
            w.bind("<Double-Button-1>", _open)

        if port is not None:
            port.bind("<ButtonPress-1>", lambda e, nid=node["id"]: self._port_press(e, nid))
            port.bind("<B1-Motion>", self._port_motion)
            port.bind("<ButtonRelease-1>", self._port_release)

    def _canvas_coords_from_event(self, e):
        """Convert a mouse event fired on some widget nested inside
        workspace_canvas (a port label several frames deep) into actual
        canvas coordinates, accounting for scroll offset. canvasx/canvasy
        expect a position relative to the canvas widget itself, not the
        screen, so root coordinates are translated through the canvas's
        own screen origin first."""
        rel_x = e.x_root - self.workspace_canvas.winfo_rootx()
        rel_y = e.y_root - self.workspace_canvas.winfo_rooty()
        return self.workspace_canvas.canvasx(rel_x), self.workspace_canvas.canvasy(rel_y)

    def _port_press(self, e, source_id):
        """Phase C3: start dragging a wire from source_id's output port.
        Draws a temporary dashed line that follows the mouse until
        release; the real wire only gets created (as a func_call block
        inserted into the source node) if release lands on a valid
        target box - see _port_release."""
        tab = self.tabs[self.active_tab_index]
        src_node = find_node_by_id(tab["nodes"], source_id)
        wid_pair = self._fileview_boxes.get(source_id)
        if src_node is None or wid_pair is None:
            return
        _, src_widget = wid_pair
        sw = src_widget.winfo_width() or 220
        sh = src_widget.winfo_height() or 70
        x0 = src_node["canvas_x"] + sw
        y0 = src_node["canvas_y"] + sh / 2

        self._wire_drag_source = source_id
        self._wire_drag_start = (x0, y0)
        self._wire_drag_temp_id = self.workspace_canvas.create_line(
            x0, y0, x0, y0, fill="#e8a33d", width=2, dash=(5, 3),
            tags=("wire_drag_temp",)
        )

    def _port_motion(self, e):
        """Redraw the in-progress wire-drag line to follow the mouse,
        and highlight whichever node box (if any) the cursor is
        currently over, so it's clear where releasing would connect
        to. Purely visual - no data changes until _port_release."""
        if self._wire_drag_source is None or self._wire_drag_temp_id is None:
            return
        cx, cy = self._canvas_coords_from_event(e)
        x0, y0 = self._wire_drag_start
        self.workspace_canvas.coords(self._wire_drag_temp_id, x0, y0, cx, cy)

        target_id = self._node_box_at(cx, cy, exclude_id=self._wire_drag_source)
        if target_id != self._wire_drag_hover_id:
            if self._wire_drag_hover_id is not None:
                prev = self._fileview_boxes.get(self._wire_drag_hover_id)
                if prev is not None:
                    prev[1].configure(highlightbackground=DARK_BORDER)
            if target_id is not None:
                cur = self._fileview_boxes.get(target_id)
                if cur is not None:
                    cur[1].configure(highlightbackground="#e8a33d")
            self._wire_drag_hover_id = target_id

    def _port_release(self, e):
        """Finish a wire-drag: if the mouse was released on top of a
        valid, different function-kind node's box, insert a func_call
        block (targeting that node's name) into the source node's
        top-level blocks - the same underlying data change a user
        adding that block by hand through the palette would produce.
        Always cleans up the temp line/hover highlight regardless of
        whether a connection was actually made."""
        source_id = self._wire_drag_source
        cx, cy = self._canvas_coords_from_event(e) if source_id is not None else (0, 0)

        if self._wire_drag_temp_id is not None:
            self.workspace_canvas.delete(self._wire_drag_temp_id)
            self._wire_drag_temp_id = None
        if self._wire_drag_hover_id is not None:
            hovered = self._fileview_boxes.get(self._wire_drag_hover_id)
            if hovered is not None:
                hovered[1].configure(highlightbackground=DARK_BORDER)
            self._wire_drag_hover_id = None

        target_id = self._node_box_at(cx, cy, exclude_id=source_id) if source_id is not None else None
        self._wire_drag_source = None
        if target_id is not None:
            self.add_wire_by_drag(source_id, target_id)

    def _node_box_at(self, cx, cy, exclude_id=None):
        """Return the id of whichever currently-drawn function-kind node
        box contains canvas point (cx, cy), or None. Used both to
        highlight a hover target mid-drag and to resolve the actual
        drop target on release, so the two always agree on hit-testing."""
        tab = self.tabs[self.active_tab_index]
        for node in self.get_current_node_list(tab):
            if node["id"] == exclude_id:
                continue
            if node.get("kind", "function") != "function":
                continue
            wid_pair = self._fileview_boxes.get(node["id"])
            if wid_pair is None:
                continue
            _, widget = wid_pair
            nx, ny = node["canvas_x"], node["canvas_y"]
            nw = widget.winfo_width() or 220
            nh = widget.winfo_height() or 70
            if nx <= cx <= nx + nw and ny <= cy <= ny + nh:
                return node["id"]
        return None

    def add_wire_by_drag(self, source_id, target_id):
        """Insert a func_call block (targeting target_id's node name)
        into source_id's top-level blocks. This is the one place a
        wire gets created by drawing rather than by hand-adding a
        func_call block through the palette - everything downstream
        (references, the drawn wire itself) is still fully derived,
        same as ever, so nothing else needs to know a drag caused it."""
        tab = self.tabs[self.active_tab_index]
        source = find_node_by_id(tab["nodes"], source_id)
        target = find_node_by_id(tab["nodes"], target_id)
        if source is None or target is None:
            return
        source["blocks"].append(("func_call", {"name": target["name"], "args": ""}))
        self.mark_active_tab_dirty()
        self.refresh_workspace()

    def draw_wires(self):
        """Redraw every wire (a derived call-graph edge between two
        function nodes) as a curved connector on workspace_canvas.
        Pure rendering of node['references'] - never mutates it, and
        only draws an edge when both endpoints are boxes actually shown
        at the current file-view depth (a class's internal nodes don't
        draw wires out to their siblings' external callers, etc.).
        Called after every file-view refresh and on every drag motion,
        so wires always track the boxes they connect live."""
        self.workspace_canvas.delete("wire")
        tab = self.tabs[self.active_tab_index]
        nodes_shown = self.get_current_node_list(tab)
        shown_ids = {n["id"] for n in nodes_shown}

        for node in nodes_shown:
            if node.get("kind", "function") != "function":
                continue
            if node["id"] not in self._fileview_boxes:
                continue
            for target_id in node.get("references", []):
                if target_id not in shown_ids or target_id not in self._fileview_boxes:
                    continue
                self._draw_one_wire(node["id"], target_id)

    def _draw_one_wire(self, source_id, target_id):
        _, src_widget = self._fileview_boxes[source_id]
        _, dst_widget = self._fileview_boxes[target_id]
        sw = src_widget.winfo_width() or 220
        sh = src_widget.winfo_height() or 70
        dh = dst_widget.winfo_height() or 70
        tab = self.tabs[self.active_tab_index]
        src_node = find_node_by_id(tab["nodes"], source_id)
        dst_node = find_node_by_id(tab["nodes"], target_id)
        if not src_node or not dst_node:
            return
        x0 = src_node["canvas_x"] + sw
        y0 = src_node["canvas_y"] + sh / 2
        x1 = dst_node["canvas_x"]
        y1 = dst_node["canvas_y"] + dh / 2

        # ComfyUI-style cubic bezier: control points pulled
        # horizontally outward from each endpoint, so the curve leaves
        # and arrives roughly perpendicular to the box edge no matter
        # the relative position of the two boxes (including one
        # stacked directly above/below the other).
        pull = max(abs(x1 - x0) * 0.5, 40)
        p0 = (x0, y0)
        p1 = (x0 + pull, y0)
        p2 = (x1 - pull, y1)
        p3 = (x1, y1)

        tag = f"wire_{source_id}_{target_id}"
        selected = self._fileview_selected_wire == (source_id, target_id)
        color = "#e8a33d" if selected else "#6a9955"
        width = 3 if selected else 2
        self.workspace_canvas.create_line(
            *self._bezier_points(p0, p1, p2, p3), smooth=True,
            fill=color, width=width, tags=("fileview", "wire", tag)
        )
        self.workspace_canvas.create_oval(
            x1 - 4, y1 - 4, x1 + 4, y1 + 4, fill=color, outline="",
            tags=("fileview", "wire", tag)
        )
        self.workspace_canvas.tag_bind(
            tag, "<Button-1>",
            lambda e, s=source_id, t=target_id: self.select_wire(s, t)
        )
        self.workspace_canvas.tag_bind(
            tag, "<Double-Button-1>",
            lambda e, s=source_id, t=target_id: self.delete_wire(s, t)
        )

    def _bezier_points(self, p0, p1, p2, p3, segments=24):
        """Flatten a cubic bezier into a polyline for Canvas's own
        smooth=True line drawing (Tkinter has no native bezier item)."""
        pts = []
        for i in range(segments + 1):
            t = i / segments
            mt = 1 - t
            x = (mt ** 3) * p0[0] + 3 * (mt ** 2) * t * p1[0] + 3 * mt * (t ** 2) * p2[0] + (t ** 3) * p3[0]
            y = (mt ** 3) * p0[1] + 3 * (mt ** 2) * t * p1[1] + 3 * mt * (t ** 2) * p2[1] + (t ** 3) * p3[1]
            pts.extend([x, y])
        return pts

    def select_wire(self, source_id, target_id):
        """Single-click a wire to highlight it (orange, thicker) -
        purely visual feedback that a specific call edge is what a
        follow-up double-click would delete."""
        self._fileview_selected_wire = (source_id, target_id)
        self.draw_wires()

    def delete_wire(self, source_id, target_id):
        """Double-clicking a drawn wire removes the underlying
        func_call block from the source node - never the reverse (the
        wire itself is never hand-editable, only what produces it is).
        If the source calls the target more than once, this removes
        just the first matching func_call found; the wire stays drawn
        until every call to that target is gone, matching one
        double-click removing one edge's worth of calls at a time."""
        tab = self.tabs[self.active_tab_index]
        source = find_node_by_id(tab["nodes"], source_id)
        target = find_node_by_id(tab["nodes"], target_id)
        if not source or not target:
            return
        removed = self.remove_first_func_call_targeting(source["blocks"], target["name"])
        if removed:
            self._fileview_selected_wire = None
            self.mark_active_tab_dirty()
            self.refresh_workspace()

    def remove_first_func_call_targeting(self, block_list, target_name):
        """Recursively find and remove the first func_call block (at
        any nesting depth, including inside a container block's
        _children) whose name matches target_name. Returns True if
        something was removed. Mirrors iter_all_blocks_recursive's
        traversal order so "first" is well-defined and matches what a
        user would read top-to-bottom in the block editor."""
        for i, (block_id, params) in enumerate(block_list):
            if block_id == "func_call" and (params.get("name") or "").strip() == target_name:
                del block_list[i]
                return True
        for block_id, params in block_list:
            module = self.blocks.get(block_id)
            if module and get_block_attr(module, "is_container", False):
                if self.remove_first_func_call_targeting(params.get("_children", []), target_name):
                    return True
        return False

    def _update_fileview_scrollregion(self):
        """Size workspace_canvas's scrollregion to whatever the
        freeform boxes/wires currently occupy, so dragging a node far
        out lets the existing scrollbar reach it instead of clipping
        it. Pan/zoom proper is deferred (see handoff carry-forward
        item 1) - this first pass reuses the plain vertical/horizontal
        scrollbar machinery already in place for the block editor."""
        bbox = self.workspace_canvas.bbox("fileview")
        if bbox:
            x0, y0, x1, y1 = bbox
            self.workspace_canvas.configure(scrollregion=(0, 0, x1 + 60, y1 + 60))
        else:
            self.workspace_canvas.configure(scrollregion=self.workspace_canvas.bbox("all"))

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

    def assign_default_tab_canvas_positions(self):
        """Files-layer equivalent of assign_default_canvas_positions():
        give any tab without a stored canvas position a sensible
        default grid slot (3 per row), never overwriting a position
        the user has already dragged a file box to."""
        col_width, row_height = 260, 150
        start_x, start_y = 30, 20
        per_row = 3
        for idx, tab in enumerate(self.tabs):
            if "canvas_x" not in tab or "canvas_y" not in tab:
                row, col = divmod(idx, per_row)
                tab["canvas_x"] = start_x + col * col_width
                tab["canvas_y"] = start_y + row * row_height

    def refresh_workspace(self):
        """Refresh the visual workspace - either the file-level node
        boxes (view_mode == "file") or the block editor for whichever
        node is currently active (view_mode == "node", the default and
        today's exact original behavior when a tab has only one node)."""
        self.recompute_references()
        self.recompute_file_references()
        # Kept unconditional (not just for view_mode == "file"/"node")
        # so self.code_text - the data Export/Run/Code->Blocks actually
        # read - stays current for the active tab no matter which layer
        # or toggle state is on screen; see update_right_panel_visibility.
        self.update_generated_code()
        self.update_right_panel_visibility()

        for widget in self.workspace_frame.winfo_children():
            widget.destroy()
        # Phase C2's node boxes/wires live directly on workspace_canvas
        # (not inside workspace_frame, so they can be freely positioned
        # instead of pack()-stacked) - clear them here unconditionally
        # so switching to the block editor view never leaves stale
        # boxes/wires behind.
        self.workspace_canvas.delete("fileview")

        # Tk canvas window items (like the one embedding workspace_frame)
        # always paint on top of drawn items (lines/ovals) regardless of
        # creation order or raise/lower - and an empty Frame doesn't
        # reliably shrink its own requested height back down once
        # something bigger (e.g. the "empty state" message) has been
        # packed into it. Left alone, that stale height silently
        # occludes every wire drawn on the canvas beneath it. Pinning
        # it to 1px whenever nothing is meant to be inside
        # workspace_frame (file view - the "Back" button lives in the
        # header nav instead, see refresh_node_nav) sidesteps the
        # problem entirely; reverting to "" lets it size normally again
        # for the block editor or either layer's code view.
        if self.view_mode == "files" and self.files_view_code_mode:
            self.workspace_canvas.itemconfigure(self.workspace_frame_window_id, height=0)
        elif self.view_mode == "file" and self.file_view_code_mode:
            self.workspace_canvas.itemconfigure(self.workspace_frame_window_id, height=0)
        elif self.view_mode in ("file", "files"):
            self.workspace_canvas.itemconfigure(self.workspace_frame_window_id, height=1)
        else:
            self.workspace_canvas.itemconfigure(self.workspace_frame_window_id, height=0)

        self.refresh_node_nav()

        if self.view_mode == "files":
            if self.files_view_code_mode:
                self.render_files_code_view()
            else:
                self.render_files_view()
            self.block_count_label.config(text="")
            return

        if self.view_mode == "file":
            if self.file_view_code_mode:
                self.render_file_code_view()
            else:
                self.render_file_view()
            self.block_count_label.config(text="")
            return

        if not self.project_blocks:
            self.show_empty_state()
        else:
            for i, (block_id, params) in enumerate(self.project_blocks):
                block_module = self.blocks.get(block_id)
                if block_module:
                    block_widget = BlockWidget(
                        self.workspace_frame,
                        block_id,
                        block_module,
                        params if isinstance(params, dict) else dict(params),
                        i,
                        self.project_blocks,
                        self
                    )
                    block_widget.pack(fill=tk.X, pady=4, padx=10)
        
        count = len(self.project_blocks)
        self.block_count_label.config(text=f"{count} block{'s' if count != 1 else ''}")
        self.update_generated_code()
    
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

        def collect(node_list):
            combined = []
            for node in node_list:
                combined.extend(node["blocks"])
                if node.get("child_nodes"):
                    combined.extend(collect(node["child_nodes"]))
            return combined

        return collect(nodes)

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

    def update_generated_code(self):
        """Generate code from every node's blocks in the active tab,
        concatenated in node order (see all_tab_blocks_concatenated),
        and write it into the right-hand code panel. Delegates the
        actual generation to generate_code_for_tab() (Files-layer code
        view reuses that same logic for other tabs)."""
        lang = self.lang_var.get()
        tab = self.tabs[self.active_tab_index] if getattr(self, "tabs", None) else None
        code = self.generate_code_for_tab(tab, lang) if tab is not None else self.generate_code_for_tab({"language": lang, "nodes": []}, lang)

        self.code_text.delete(1.0, tk.END)
        if code:
            self.code_text.insert(tk.END, code)
        else:
            self.code_text.insert(tk.END, "# No code generated yet\n# Add blocks from the palette!")

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
                self.maybe_notify("Exported", f"Code exported to:\n{filename}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export: {e}")
    
    def run_in_terminal(self):
        """Run code in external terminal"""
        code = self.code_text.get(1.0, tk.END).strip()
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
        code = self.code_text.get(1.0, tk.END).strip()
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
        code = self.code_text.get(1.0, tk.END).strip()
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
        code = self.code_text.get(1.0, tk.END).strip()
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
        code = self.code_text.get(1.0, tk.END).strip()
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
    
    def clear_all(self):
        """Clear all blocks"""
        if not self.project_blocks:
            return
        if messagebox.askyesno("Clear Workspace", f"Remove all {len(self.project_blocks)} blocks?"):
            self.project_blocks.clear()
            self.mark_active_tab_dirty()
            self.refresh_workspace()

def start_ui(blocks=None, initial_lang="python", languages_path="languages"):
    """Start the Blockliner UI"""
    app = BlocklinerUI(initial_lang=initial_lang, languages_path=languages_path)
    app.mainloop()