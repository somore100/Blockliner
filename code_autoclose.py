"""Auto-closing brackets/quotes for the code Text widgets (editor style).

( [ { " '  insert the pair and put the caret between; typing the closer
right before the same closer steps over it; Backspace between an empty
pair deletes both; typing an opener over a selection wraps it.
Pure Tk-text logic, no app state: pass enabled=False to do nothing.
"""

PAIRS = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}
CLOSERS = set(PAIRS.values())
_CONTROL, _ALT = 0x4, 0x8


def _char(w, index):
    return w.get(index, index + "+1c")


def _prev(w):
    return w.get("insert-1c", "insert") if w.compare("insert", ">", "1.0") else ""


def on_keypress(w, event, enabled=True):
    """Return "break" if the key was handled here, else None."""
    ch = event.char
    if not enabled or not ch or len(ch) != 1 or event.state & (_CONTROL | _ALT):
        return None
    sel = w.tag_ranges("sel")
    if ch in PAIRS and sel:
        a, b = str(sel[0]), str(sel[1])
        text = w.get(a, b)
        w.delete(a, b)
        w.insert(a, ch + text + PAIRS[ch])
        w.mark_set("insert", f"{a}+{len(text) + 2}c")
        return "break"
    if sel:
        return None
    nxt = _char(w, "insert")
    if ch in CLOSERS and nxt == ch:           # step over an existing closer
        w.mark_set("insert", "insert+1c")
        return "break"
    if ch in PAIRS:
        prev = _prev(w)
        if ch in "\"'" and (prev.isalnum() or prev == ch or prev == "\\"):
            return None                        # don't, it's, '''  ->  plain char
        if ch in "([{" and nxt and not nxt.isspace() and nxt not in CLOSERS:
            return None                        # typing before a word: plain
        at = w.index("insert")
        w.insert("insert", ch + PAIRS[ch])
        if w.get(at, at + "+2c") != ch + PAIRS[ch]:   # edit was refused (guard)
            return "break"
        w.mark_set("insert", at + "+1c")
        return "break"
    return None


def on_backspace(w, event, enabled=True):
    if not enabled or w.tag_ranges("sel"):
        return None
    prev, nxt = _prev(w), _char(w, "insert")
    if prev in PAIRS and PAIRS[prev] == nxt and nxt:
        w.delete("insert-1c", "insert+1c")
        return "break"
    return None


def install(w, is_enabled):
    """Bind the handlers on a Text widget; is_enabled() is checked per key."""
    w.bind("<KeyPress>", lambda e: on_keypress(w, e, is_enabled()), add="+")
    w.bind("<BackSpace>", lambda e: on_backspace(w, e, is_enabled()), add="+")
