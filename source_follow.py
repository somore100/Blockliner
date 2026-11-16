"""Source-first, phase 1 (see docs/source-first-mode.md): follow a folder of source files read-only. Pure (no Tk).

snapshot() remembers every readable source file (size, modification time, content hash); diff() says what an outside
tool added, changed or removed between two snapshots; carry_layout() gives the nodes of a re-read file the places the
old nodes had, so a reload does not shuffle the canvas. Nothing here writes to disk."""
import difflib
import hashlib
import os

import portable
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


def chunk_codes(chunks):
    """{node id: code} for the [(name, code)] chunks, with the same ids portable.wrap_with_markers gives them."""
    return {nid: code for nid, code in zip(portable.unique_ids(n for n, _c in chunks), (c for _n, c in chunks))}


def _similar(a, b):
    """0..1: how alike two pieces of code are (blank lines and edge spaces ignored)."""
    a = "\n".join(l.strip() for l in a.splitlines() if l.strip())
    b = "\n".join(l.strip() for l in b.splitlines() if l.strip())
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


RENAME_MIN = 0.6          # a new node this alike an unmatched old one is the same function under a new name


def carry_layout(old_nodes, new_nodes, old_codes=None, new_codes=None):
    """Give each node of a re-read file the position of the node it replaces: matched by id first, then by name, then
    (when old_codes / new_codes {id: code} are given) by how alike the code is - so a renamed function keeps its place.
    Nodes that match nothing keep the position they were given. Walks nested nodes too. Returns how many matched."""
    def flat(level, out):
        for n in level:
            out.append(n)
            flat(n.get("child_nodes") or [], out)
        return out
    old_flat, new_flat = flat(old_nodes, []), flat(new_nodes, [])
    by_id = {n["id"]: n for n in old_flat}
    by_name = {}
    for n in old_flat:
        by_name.setdefault(n.get("name"), []).append(n)
    pairs, used = {}, set()                          # id(new node) -> old node
    for n in new_flat:                               # 1. same id
        src = by_id.get(n["id"])
        if src is not None and id(src) not in used:
            pairs[id(n)] = src
            used.add(id(src))
    for n in new_flat:                               # 2. same name
        if id(n) in pairs:
            continue
        cands = [c for c in by_name.get(n.get("name"), []) if id(c) not in used]
        if cands:
            pairs[id(n)] = cands[0]
            used.add(id(cands[0]))
    if old_codes and new_codes:                      # 3. the same code under another name (best matches first)
        scored = []
        for n in new_flat:
            if id(n) in pairs or not new_codes.get(n["id"]):
                continue
            for o in old_flat:
                if id(o) in used or not old_codes.get(o["id"]):
                    continue
                score = _similar(old_codes[o["id"]], new_codes[n["id"]])
                if score >= RENAME_MIN:
                    scored.append((score, n, o))
        scored.sort(key=lambda t: -t[0])
        for _score, n, o in scored:
            if id(n) not in pairs and id(o) not in used:
                pairs[id(n)] = o
                used.add(id(o))
    for n in new_flat:
        src = pairs.get(id(n))
        if src is None:
            continue
        for key in ("canvas_x", "canvas_y", "locked"):
            if key in src:
                n[key] = src[key]
        n.pop("_auto_pos", None)
    return len(pairs)
