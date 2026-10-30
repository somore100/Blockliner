"""Rolled-up wires: pure module (no Tk).

A wire whose end sits INSIDE a box that is shown (a category or class) is
drawn to that box instead, so a category never hides how it is connected.
Edges are derived from the same data as the normal wires (node["references"],
node["ref_kinds"], node["data_uses"]) and merged: one line per
(from box, to box, kind) with a count. Direction as the normal wires:
call = caller -> callee, data = producer -> user.
"""


def _walk(node, shown_id, out):
    out.append((node, shown_id))
    for child in node.get("child_nodes") or []:
        _walk(child, shown_id, out)


def rolled_edges(shown):
    """[{"src", "dst", "kind", "count", "vars"}] for every connection with at
    least one end hidden inside a shown box and both ends inside DIFFERENT
    shown boxes. Connections to nodes outside `shown` are skipped."""
    members = []
    for top in shown:
        _walk(top, top["id"], members)
    rep = {n["id"]: r for n, r in members}
    merged = {}

    def add(src, dst, kind, names):
        edge = merged.setdefault((src, dst, kind),
                                 {"src": src, "dst": dst, "kind": kind, "count": 0, "vars": []})
        edge["count"] += 1
        for name in names:
            if name not in edge["vars"]:
                edge["vars"].append(name)

    for node, r in members:
        for target in node.get("references") or []:
            rt = rep.get(target)
            if rt is None or rt == r or (node["id"] == r and target == rt):
                continue
            add(r, rt, (node.get("ref_kinds") or {}).get(target, "call"), [])
        for use in node.get("data_uses") or []:
            rp = rep.get(use.get("id"))
            if rp is None or rp == r or (node["id"] == r and use.get("id") == rp):
                continue
            add(rp, r, "data", use.get("vars") or [])
    return list(merged.values())
