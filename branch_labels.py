"""Branch labels for call wires. Pure module (no Tk).

A call that sits inside an if / elif / else body only runs when that branch is
taken, so its wire is labelled with the branch ("if ok", "else"). Derived from
the blocks every time, never stored in the file.

  - a condition's own calls run every time, so they get no label;
  - nested branches join with " > " ("if a > else");
  - a name called in several branches gets all of them, joined with " / ";
  - a name that is also called somewhere outside every branch gets no label,
    because it runs whatever the condition says.
"""
import wire_kinds

MAX_COND = 18
BRANCH_BLOCKS = ("if_statement", "elif_statement", "else_statement")


def _condition_text(value):
    """Short readable text of a condition param (a string or a call chip)."""
    if isinstance(value, dict):
        params = value.get("_nested_params")
        name = str((params or {}).get("name") or "").strip() if isinstance(params, dict) else ""
        text = f"{name}(...)" if name else "..."
    else:
        text = " ".join(str(value or "").split())
    if len(text) > MAX_COND:
        text = text[:MAX_COND - 1] + "…"
    return text


def branch_name(block_id, params):
    """"if x" / "elif x" / "else" for a branch block, else None."""
    if block_id == "if_statement":
        return ("if " + _condition_text((params or {}).get("condition"))).strip()
    if block_id == "elif_statement":
        return ("elif " + _condition_text((params or {}).get("condition"))).strip()
    if block_id == "else_statement":
        return "else"
    return None


def call_branches(blocks):
    """{called name: label} for every call that only runs inside branches."""
    inside = {}                     # name -> labels in order of appearance
    outside = set()

    def note(name, label):
        if label is None:
            outside.add(name)
        else:
            labels = inside.setdefault(name, [])
            if label not in labels:
                labels.append(label)

    def walk(entries, label):
        for entry in entries or []:
            try:
                bid, params = entry
            except (TypeError, ValueError):
                continue
            if not isinstance(params, dict):
                continue
            if bid == "func_call":
                name = str(params.get("name") or "").strip()
                if name:
                    note(name, label)
            chips = set()
            for k, v in params.items():
                if k != "_children":
                    wire_kinds._chip_names(v, chips)
            for name in chips:
                note(name, label)
            mine = branch_name(bid, params)
            child_label = label
            if mine:
                child_label = f"{label} > {mine}" if label else mine
            children = params.get("_children")
            if isinstance(children, list):
                walk(children, child_label)

    walk(blocks, None)
    return {name: " / ".join(labels) for name, labels in inside.items() if name not in outside}
