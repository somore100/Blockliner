"""Shared constants, theme colours, paths, default settings and small UI helpers."""
import tkinter as tk
import os
import sys


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
    # Layer switching shortcuts, as Tk key sequences (no angle brackets).
    "keybinds": {
        "layer_files": "Control-Key-1",
        "layer_nodes": "Control-Key-2",
        "layer_blocks": "Control-Key-3",
        "layer_code": "Control-Key-4",
    },
}

LAYER_ACTIONS = [
    ("layer_files", "Files layer"),
    ("layer_nodes", "Nodes layer"),
    ("layer_blocks", "Blocks layer"),
    ("layer_code", "Code (toggle)"),
]

_MODIFIER_KEYSYMS = {
    "Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R",
    "Meta_L", "Meta_R", "Super_L", "Super_R", "ISO_Level3_Shift",
    "Caps_Lock", "Num_Lock", "Scroll_Lock",
}


def keybind_from_event(event):
    """Turn a KeyPress event into a Tk sequence like 'Control-Key-1', or
    None if it's only a modifier or has no Ctrl/Alt (a bare key would
    steal normal typing, so shortcuts must include one of them)."""
    if event.keysym in _MODIFIER_KEYSYMS:
        return None
    ctrl = bool(event.state & 0x4)
    alt = bool(event.state & 0x8) or bool(event.state & 0x20000)
    if not (ctrl or alt):
        return None
    parts = []
    if ctrl:
        parts.append("Control")
    if alt:
        parts.append("Alt")
    if event.state & 0x1:
        parts.append("Shift")
    parts.append("Key-" + event.keysym)
    return "-".join(parts)


def keybind_label(seq):
    """'Control-Key-1' -> 'Ctrl+1' for display."""
    if not seq:
        return "(none)"
    out = []
    for part in seq.split("-"):
        if part == "Key":
            continue
        out.append({"Control": "Ctrl"}.get(part, part))
    return "+".join(out)
