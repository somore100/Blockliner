"""Import changes suggested by an AI chat (pure, no Tk).

Chatbots that can't touch files tend to say "change line 30 to ...", and line numbers drift. This reads a small
text template instead, where every change names a NODE (a function) and says what to replace by quoting code:

    === edit: parse_args
    <<<<<<< SEARCH
    parser.add_argument("-v")
    =======
    parser.add_argument("-v", action="store_true")
    >>>>>>> REPLACE

    === replace: main          (the whole node is replaced by the code that follows)
    def main():
        ...

    === new: helper            (a new node)
    def helper():
        ...

`Class.method` names a method node; a plain name works when only one node has it (the node id works too).
`plan` checks every change against the current code and says what would happen; nothing is applied here.
"""
import re
import textwrap
from dataclasses import dataclass, field

INSTRUCTIONS = """When you suggest changes to my code, do not use line numbers. Use exactly this format, one section per change,
and name the function (node) each change is for:

=== edit: <function name>
<<<<<<< SEARCH
<a few lines copied exactly from the current code>
=======
<what they should become>
>>>>>>> REPLACE

=== replace: <function name>
<the complete new code of that function>

=== new: <new function name>
<the code of the new function>

Rules: the SEARCH text must appear exactly once in that function (add a neighbouring line if needed). For a method
write <Class>.<method>. Use "edit" for small changes and "replace" when most of the function changes. Do not
include anything else inside the sections; explanations go before the first ===."""

_HEAD_RE = re.compile(r"^\s*={3,}\s*(edit|replace|new)\b\s*(?:node|function)?\s*[:\-]?\s*(.*?)\s*=*\s*$", re.I)
_OPEN_RE = re.compile(r"^\s*<{5,}\s*(?:SEARCH|FIND)?\s*$", re.I)
_MID_RE = re.compile(r"^\s*={5,}\s*$")
_CLOSE_RE = re.compile(r"^\s*>{5,}\s*(?:REPLACE|WITH)?\s*$", re.I)
_FENCE_RE = re.compile(r"^\s*```\w*\s*$")


@dataclass
class Op:
    kind: str                  # "edit" | "replace" | "new"
    node: str                  # the name the change gave
    edits: list = field(default_factory=list)      # edit: [(search, replacement)]
    code: str = ""             # replace / new
    line: int = 0              # where it starts in the pasted text (1-based)


@dataclass
class Change:
    op: Op
    node: object = None        # the node dict (None for a new node)
    old: str = ""
    new: str = ""
    error: str = ""            # why it can't be applied (empty = ok)

    @property
    def ok(self):
        return not self.error


def _strip_fences(lines):
    while lines and not lines[0].strip():
        lines = lines[1:]
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    if lines and _FENCE_RE.match(lines[0]):
        lines = lines[1:]
    if lines and _FENCE_RE.match(lines[-1]):
        lines = lines[:-1]
    return lines


def parse(text):
    """-> (ops, problems). A malformed section is reported, the others still count."""
    lines = text.replace("\r\n", "\n").split("\n")
    sections, cur = [], None
    for i, ln in enumerate(lines, 1):
        m = _HEAD_RE.match(ln)
        if m:
            cur = [m.group(1).lower(), m.group(2).strip().strip("`'\""), i, []]
            sections.append(cur)
        elif cur is not None:
            cur[3].append(ln)
    ops, problems = [], []
    if not sections:
        return [], ["No changes found. Each change starts with a line like  === edit: function_name  (see 'Copy instructions for AI')."]
    for kind, name, line, body in sections:
        where = f"line {line} ({kind}: {name or '?'})"
        if not name:
            problems.append(f"{where}: no node name")
            continue
        body = _strip_fences(body)
        if kind == "edit":
            edits, bad = _parse_edits(body)
            if bad:
                problems.append(f"{where}: {bad}")
            elif not edits:
                problems.append(f"{where}: no <<<<<<< SEARCH ... ======= ... >>>>>>> REPLACE block")
            else:
                ops.append(Op("edit", name, edits=edits, line=line))
        else:
            code = textwrap.dedent("\n".join(body)).strip("\n")
            if not code.strip():
                problems.append(f"{where}: no code")
            else:
                ops.append(Op(kind, name, code=code + "\n", line=line))
    return ops, problems


def _parse_edits(body):
    edits, state, search, repl = [], 0, [], []
    for ln in body:
        if state == 0:
            if _OPEN_RE.match(ln):
                state, search, repl = 1, [], []
            elif ln.strip() and not _FENCE_RE.match(ln):
                return [], "text outside a SEARCH block"
        elif state == 1:
            if _MID_RE.match(ln):
                state = 2
            else:
                search.append(ln)
        else:
            if _CLOSE_RE.match(ln):
                if not "".join(search).strip():
                    return [], "an empty SEARCH block"
                edits.append(("\n".join(search), "\n".join(repl)))
                state = 0
            else:
                repl.append(ln)
    if state:
        return [], "a SEARCH block is not closed (missing =======  or >>>>>>> REPLACE)"
    return edits, ""


# --- matching ---------------------------------------------------------------

def _lines_key(text):
    return [ln.strip() for ln in text.split("\n") if ln.strip()]


def apply_edit(code, search, replacement):
    """code with `search` replaced; raises ValueError (with a reason) when it can't be done safely.
    Exact text first; then a match that ignores indentation and blank lines (the code shown to a chatbot is
    not always character for character what is stored). It must be unique."""
    if code.count(search) == 1 and not search[:1].isspace():
        return code.replace(search, replacement)
    if code.count(search) > 1 and not search[:1].isspace():
        raise ValueError(f"the SEARCH text appears {code.count(search)} times - add a neighbouring line to make it unique")
    want = _lines_key(search)
    lines = code.split("\n")
    idx = [i for i, ln in enumerate(lines) if ln.strip()]       # the non-blank lines
    keys = [lines[i].strip() for i in idx]
    hits = [k for k in range(len(keys) - len(want) + 1) if keys[k:k + len(want)] == want]
    if not hits:
        raise ValueError(f"the SEARCH text was not found (first line: {want[0][:60]!r})")
    if len(hits) > 1:
        raise ValueError(f"the SEARCH text appears {len(hits)} times (ignoring indentation) - make it unique")
    a, b = idx[hits[0]], idx[hits[0] + len(want) - 1]
    base = lines[a][:len(lines[a]) - len(lines[a].lstrip())]
    first = next((ln for ln in search.split("\n") if ln.strip()), "")
    given = first[:len(first) - len(first.lstrip())]
    new_lines = []
    for ln in replacement.split("\n"):
        if ln.strip() and ln.startswith(given):
            ln = base + ln[len(given):]
        new_lines.append(ln)
    return "\n".join(lines[:a] + new_lines + lines[b + 1:])


# --- planning -----------------------------------------------------------------

def _walk(nodes, path=()):
    for n in nodes:
        yield n, path
        yield from _walk(n.get("child_nodes") or [], path + (n["name"],))


def resolve(nodes, ref):
    """The function node a change means: 'Class.method', a unique name, or an id. (node, error)."""
    ref = ref.strip()
    found = [(n, p) for n, p in _walk(nodes) if n.get("kind", "function") == "function"]
    if "." in ref:
        cls, _dot, name = ref.rpartition(".")
        hits = [n for n, p in found if n["name"] == name and p and p[-1] == cls.rpartition(".")[2]]
    else:
        hits = [n for n, _p in found if n["name"] == ref] or [n for n, _p in found if n["id"] == ref]
    if len(hits) == 1:
        return hits[0], ""
    if len(hits) > 1:
        return None, f"more than one node is called {ref!r} - write Class.method"
    names = [n["name"] for n, _p in found]
    close = [x for x in names if ref.lower() in x.lower() or x.lower() in ref.lower()][:3]
    return None, f"there is no node {ref!r}" + (f" (did you mean {', '.join(close)}?)" if close else "")


def plan(nodes, ops, node_code, is_locked=lambda node: ""):
    """[Change] for the ops. `node_code(node)` is the node's current code as text; `is_locked(node)` returns a
    reason (text) when the node can't be changed by code (a window layout node, say), else ''."""
    out, created, latest = [], set(), {}      # latest: a node changed twice builds on its first change
    for op in ops:
        node, err = resolve(nodes, op.node)
        if op.kind == "new":
            leaf = op.node.rpartition(".")[2]
            if node is not None or leaf in created:
                out.append(Change(op, error=f"a node called {op.node!r} already exists - use replace"))
            else:
                created.add(leaf)
                out.append(Change(op, new=op.code))
            continue
        if node is None:
            out.append(Change(op, error=err))
            continue
        reason = is_locked(node)
        old = latest.get(id(node)) if id(node) in latest else node_code(node)
        if reason:
            out.append(Change(op, node, old, error=reason))
            continue
        if op.kind == "replace":
            latest[id(node)] = op.code
            out.append(Change(op, node, old, op.code))
            continue
        new, problem = old, ""
        for n, (search, repl) in enumerate(op.edits, 1):
            try:
                new = apply_edit(new, search, repl)
            except ValueError as e:
                problem = f"edit {n}: {e}"
                break
        if not problem:
            latest[id(node)] = new
        out.append(Change(op, node, old, new, error=problem))
    return out
