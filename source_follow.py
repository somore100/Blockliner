"""Source-first, phase 1 (see docs/source-first-mode.md): follow a folder of source files read-only. Pure (no Tk).

snapshot() remembers every readable source file (size, modification time, content hash); diff() says what an outside
tool added, changed or removed between two snapshots; carry_layout() gives the nodes of a re-read file the places the
old nodes had, so a reload does not shuffle the canvas. Nothing here writes to disk."""
import hashlib
import os

import project_scan


def _hash(path):
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                h.update(block)
    except OSError:
        return None
    return h.hexdigest()


def snapshot(root, extensions, previous=None, max_files=project_scan.MAX_FILES):
    """{rel: {"path", "language", "size", "mtime", "hash"}} for the files the Open-project scan accepts.
    A file whose size and time match `previous` keeps its old hash (no re-reading on every tick)."""
    entries, _truncated = project_scan.scan_folder(root, extensions, max_files=max_files)
    previous = previous or {}
    out = {}
    for e in entries:
        if not e["ok"]:
            continue
        try:
            mtime = os.stat(e["path"]).st_mtime_ns
        except OSError:
            continue
        old = previous.get(e["rel"])
        if old and old["size"] == e["size"] and old["mtime"] == mtime and old.get("hash"):
            digest = old["hash"]
        else:
            digest = _hash(e["path"])
        out[e["rel"]] = {"path": e["path"], "language": e["language"], "size": e["size"],
                         "mtime": mtime, "hash": digest}
    return out


def diff(old, new):
    """(added, changed, removed): sorted lists of relative paths. A touched file with the same content is not changed."""
    added = sorted(r for r in new if r not in old)
    removed = sorted(r for r in old if r not in new)
    changed = sorted(r for r in new if r in old and new[r]["hash"] != old[r]["hash"])
    return added, changed, removed


def carry_layout(old_nodes, new_nodes):
    """Give each node of a re-read file the position of the node it replaces: matched by id first, then by name.
    Nodes that match nothing keep the position they were given. Walks nested nodes too. Returns how many matched."""
    old_flat = []

    def collect(level):
        for n in level:
            old_flat.append(n)
            collect(n.get("child_nodes") or [])
    collect(old_nodes)
    by_id = {n["id"]: n for n in old_flat}
    by_name = {}
    for n in old_flat:
        by_name.setdefault(n.get("name"), []).append(n)
    used, matched = set(), 0

    def apply(level):
        nonlocal matched
        for n in level:
            src = by_id.get(n["id"])
            if src is None or id(src) in used:
                cands = [c for c in by_name.get(n.get("name"), []) if id(c) not in used]
                src = cands[0] if cands else None
            if src is not None:
                used.add(id(src))
                matched += 1
                for key in ("canvas_x", "canvas_y", "locked"):
                    if key in src:
                        n[key] = src[key]
                n.pop("_auto_pos", None)
            apply(n.get("child_nodes") or [])
    apply(new_nodes)
    return matched
