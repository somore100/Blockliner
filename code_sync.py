"""Pure logic for code-panel -> blocks sync (no Tk).

A node's blocks and the code typed in the panel are compared by GENERATED
CODE, never by block structure: blocks -> code -> blocks does not round-trip
exactly (a block that doesn't match its own pattern comes back as raw code),
so comparing structures would report changes nobody made."""
import difflib

SYNC_MODE_CHOICES = [
    ("line", "When I leave the edited line (default)"),
    ("char", "Every character"),
    ("manual", "Only when I press Sync"),
]


def normalize_sync_mode(value):
    return value if value in ("line", "char", "manual") else "line"


def norm_lines(code):
    """Code lines compared for 'did anything change': trailing spaces and blank
    lines don't count (blocks don't store them)."""
    return [ln.rstrip() for ln in code.splitlines() if ln.strip()]


def same_code(a, b):
    return norm_lines(a) == norm_lines(b)


def diff_blocks(old_sigs, new_sigs):
    """difflib opcodes [(tag, i1, i2, j1, j2)] between two lists of per-block
    generated code strings."""
    return difflib.SequenceMatcher(None, old_sigs, new_sigs, autojunk=False).get_opcodes()


def line_of_block(old_sigs, index):
    """1-based line (inside the node's code) where old block `index` starts."""
    return sum(max(1, len(s.splitlines())) for s in old_sigs[:index]) + 1


def merge_blocks(old_blocks, new_blocks, ops, keep_old=frozenset()):
    """Blocks after the sync. Equal runs keep the ORIGINAL block objects;
    inserts always take the new blocks; replace/delete take the new blocks
    unless that op's index is in `keep_old`."""
    out = []
    for n, (tag, i1, i2, j1, j2) in enumerate(ops):
        if tag == "equal":
            out.extend(old_blocks[i1:i2])
        elif tag == "insert":
            out.extend(new_blocks[j1:j2])
        elif n in keep_old:
            out.extend(old_blocks[i1:i2])
        else:
            out.extend(new_blocks[j1:j2])
    return out


def _short(sigs, limit=60):
    text = " / ".join(" ".join(s.split()) for s in sigs)
    return text if len(text) <= limit else text[:limit - 1] + "\u2026"


def describe_change(node_name, tag, line, old_sigs, new_sigs):
    if tag == "delete":
        return f"node '{node_name}' line {line}: \u201c{_short(old_sigs)}\u201d is removed"
    return (f"node '{node_name}' line {line}: \u201c{_short(old_sigs)}\u201d "
            f"is replaced by \u201c{_short(new_sigs)}\u201d")
