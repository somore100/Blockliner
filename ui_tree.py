"""UI builder widget tree (pure, no Tk).

The single source of truth for a designed UI: a tree of widget nodes, each
plain JSON-able data. The designer view and the generated code are both views
of it. See docs/ui-builder-design.md.

    node = {"id": "w1", "type": "button", "name": "btn_save",
            "props": {"text": "Save"},        values, typed by the pack's schema
            "layout": {"manager": "grid", ...},
            "events": {"command": "<function node id>"},
            "design": {"x": 0, "y": 0, "w": 100, "h": 32},   editor-only
            "children": [node, ...]}

Anything this module doesn't know about (extra keys on a node or on the
document, unknown widget types, newer versions) is kept untouched, so a file
round-trips through an older build. A tree from a NEWER format version is
loaded read-only: every edit raises ReadOnlyError.

The tree knows nothing about widget kinds. Pass `is_container(type)` (from the
pack) to stop children being added to leaf widgets; the default allows any.
"""
import copy
import json
import keyword
import uuid

FORMAT = "blockliner-ui"
VERSION = 1
MAX_UNDO = 100


class ReadOnlyError(Exception):
    """The tree came from a newer format version and may not be edited."""


def is_valid_name(name):
    return isinstance(name, str) and name.isidentifier() and not keyword.iskeyword(name)


def _default_id():
    return uuid.uuid4().hex[:8]


def make_widget(wtype, name, widget_id, props=None, layout=None, design=None):
    return {"id": widget_id, "type": wtype, "name": name,
            "props": dict(props or {}), "layout": dict(layout or {}),
            "events": {}, "design": dict(design or {}), "children": []}


class UITree:
    def __init__(self, pack_id, root=None, is_container=None, id_factory=None,
                 extra=None, read_only=False):
        self.pack_id = pack_id
        self.root = root
        self.extra = dict(extra or {})          # unknown top-level keys, kept verbatim
        self.read_only = read_only
        self._is_container = is_container or (lambda _t: True)
        self._new_id = id_factory or _default_id
        self._undo, self._redo = [], []
        self._last_key = None                   # coalescing key of the last edit

    # ---- construction / persistence -------------------------------------
    @classmethod
    def new(cls, pack_id, root_type="window", root_name="root", props=None, **kw):
        tree = cls(pack_id, **kw)
        tree.root = make_widget(root_type, root_name, tree._new_id(), props)
        return tree

    def to_dict(self):
        doc = dict(self.extra)
        doc.update({"format": FORMAT, "version": VERSION if not self.read_only
                    else self.extra.get("version", VERSION),
                    "pack": self.pack_id, "root": copy.deepcopy(self.root)})
        return doc

    @classmethod
    def from_dict(cls, doc, **kw):
        """Raises ValueError (with a readable message) on a broken document."""
        if not isinstance(doc, dict) or doc.get("format") != FORMAT:
            raise ValueError("not a Blockliner UI document")
        version = doc.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("bad UI document version")
        root = doc.get("root")
        if not isinstance(root, dict):
            raise ValueError("UI document has no root widget")
        seen = set()
        cls._check_node(root, seen, set())
        known = {"format", "pack", "root"}
        extra = {k: v for k, v in doc.items() if k not in known}
        return cls(doc.get("pack", ""), root=copy.deepcopy(root), extra=extra,
                   read_only=version > VERSION, **kw)

    @classmethod
    def _check_node(cls, node, seen, path):
        if not isinstance(node, dict):
            raise ValueError("a widget is not an object")
        wid = node.get("id")
        if not isinstance(wid, str) or not wid:
            raise ValueError("a widget has no id")
        if wid in seen:
            raise ValueError(f"duplicate widget id '{wid}'")
        seen.add(wid)
        if not isinstance(node.get("type"), str):
            raise ValueError(f"widget '{wid}' has no type")
        for key, kind in (("props", dict), ("layout", dict), ("events", dict),
                          ("design", dict), ("children", list)):
            node.setdefault(key, kind())
            if not isinstance(node[key], kind):
                raise ValueError(f"widget '{wid}': '{key}' has the wrong shape")
        node.setdefault("name", node["type"])
        for child in node["children"]:
            cls._check_node(child, seen, path)

    # ---- queries ----------------------------------------------------------
    def walk(self, node=None):
        node = node or self.root
        yield node
        for c in node["children"]:
            yield from self.walk(c)

    def find(self, widget_id):
        return next((n for n in self.walk() if n["id"] == widget_id), None)

    def parent_of(self, widget_id):
        for n in self.walk():
            if any(c["id"] == widget_id for c in n["children"]):
                return n
        return None

    def names(self):
        return {n["name"] for n in self.walk()}

    def unique_name(self, base, exclude_id=None):
        """base, or base_2, base_3... whichever is free (and a valid identifier)."""
        base = base if is_valid_name(base) else "widget"
        taken = {n["name"] for n in self.walk() if n["id"] != exclude_id}
        if base not in taken:
            return base
        i = 2
        while f"{base}_{i}" in taken:
            i += 1
        return f"{base}_{i}"

    # ---- undo / redo ------------------------------------------------------
    def _snapshot(self):
        return json.dumps(self.root, sort_keys=True)

    def _checkpoint(self, key=None):
        """Call BEFORE a mutation. Repeated edits with the same non-None key
        (typing in one property field) share one undo step."""
        if self.read_only:
            raise ReadOnlyError("this UI was made by a newer Blockliner and can't be edited")
        if key is not None and key == self._last_key:
            return
        self._undo.append(self._snapshot())
        del self._undo[:-MAX_UNDO]
        self._redo.clear()
        self._last_key = key

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    def undo(self):
        if self.read_only or not self._undo:
            return False
        self._redo.append(self._snapshot())
        self.root = json.loads(self._undo.pop())
        self._last_key = None
        return True

    def redo(self):
        if self.read_only or not self._redo:
            return False
        self._undo.append(self._snapshot())
        self.root = json.loads(self._redo.pop())
        self._last_key = None
        return True

    # ---- edits (each is one undo step) -----------------------------------
    def _get(self, widget_id):
        node = self.find(widget_id)
        if node is None:
            raise KeyError(f"no widget '{widget_id}'")
        return node

    def _check_parent(self, parent):
        if not self._is_container(parent["type"]):
            raise ValueError(f"a {parent['type']} can't contain other widgets")

    def add(self, parent_id, wtype, index=None, name=None, props=None, layout=None, design=None):
        """Add a widget under parent_id (at index, default last). Returns its id."""
        parent = self._get(parent_id)
        self._check_parent(parent)
        self._checkpoint()
        node = make_widget(wtype, self.unique_name(name or wtype), self._new_id(),
                           props, layout, design)
        kids = parent["children"]
        kids.insert(len(kids) if index is None else max(0, min(index, len(kids))), node)
        return node["id"]

    def remove(self, widget_id):
        if widget_id == self.root["id"]:
            raise ValueError("the root widget can't be removed")
        parent = self.parent_of(widget_id)
        if parent is None:
            raise KeyError(f"no widget '{widget_id}'")
        self._checkpoint()
        parent["children"] = [c for c in parent["children"] if c["id"] != widget_id]

    def move(self, widget_id, new_parent_id, index=None):
        if widget_id == self.root["id"]:
            raise ValueError("the root widget can't be moved")
        node, new_parent = self._get(widget_id), self._get(new_parent_id)
        if any(n["id"] == new_parent_id for n in self.walk(node)):
            raise ValueError("a widget can't be moved into itself")
        self._check_parent(new_parent)
        self._checkpoint()
        self.parent_of(widget_id)["children"].remove(node)
        kids = new_parent["children"]
        kids.insert(len(kids) if index is None else max(0, min(index, len(kids))), node)

    def set_prop(self, widget_id, key, value):
        node = self._get(widget_id)
        self._checkpoint(("prop", widget_id, key))
        node["props"][key] = value

    def clear_prop(self, widget_id, key):
        node = self._get(widget_id)
        self._checkpoint()
        node["props"].pop(key, None)

    def set_layout(self, widget_id, **values):
        node = self._get(widget_id)
        self._checkpoint(("layout", widget_id, tuple(sorted(values))))
        node["layout"].update(values)

    def edit_many(self, changes):
        """{widget id: {"layout": {...}, "props": {...}, "parent": id}} as ONE
        undo step (a drag on the paper can move two widgets: a grid swap, or
        move a widget into another container). "layout" replaces the whole
        layout when "parent" changes, else it is merged."""
        nodes = {wid: self._get(wid) for wid in changes}
        for wid, change in changes.items():               # check everything before changing anything
            if "parent" in change:
                if wid == self.root["id"]:
                    raise ValueError("the root widget can't be moved")
                target = self._get(change["parent"])
                self._check_parent(target)
                if any(n["id"] == target["id"] for n in self.walk(nodes[wid])):
                    raise ValueError("a widget can't be moved into itself")
        self._checkpoint()
        for wid, change in changes.items():
            node = nodes[wid]
            if "parent" in change and self.parent_of(wid)["id"] != change["parent"]:
                self.parent_of(wid)["children"].remove(node)
                self._get(change["parent"])["children"].append(node)
                node["layout"] = dict(change.get("layout") or {})
            else:
                node["layout"].update(change.get("layout") or {})
            node["props"].update(change.get("props") or {})

    def set_design(self, widget_id, **values):
        """Editor-only geometry (x, y, w, h). Dragging coalesces into one step."""
        node = self._get(widget_id)
        self._checkpoint(("design", widget_id, tuple(sorted(values))))
        node["design"].update(values)

    def set_event(self, widget_id, event, target):
        """Point an event at a function node id; target None unlinks it."""
        node = self._get(widget_id)
        self._checkpoint()
        if target is None:
            node["events"].pop(event, None)
        else:
            node["events"][event] = target

    def rename(self, widget_id, new_name):
        """Returns the name actually used (uniquified). Invalid names raise."""
        if not is_valid_name(new_name):
            raise ValueError(f"'{new_name}' isn't a valid variable name")
        node = self._get(widget_id)
        if node["name"] == new_name:
            return new_name
        self._checkpoint()
        node["name"] = self.unique_name(new_name, exclude_id=widget_id)
        return node["name"]

    def duplicate(self, widget_id):
        """Deep copy next to the original, with fresh ids and unique names.
        Event links are kept (both widgets call the same handler)."""
        if widget_id == self.root["id"]:
            raise ValueError("the root widget can't be duplicated")
        src, parent = self._get(widget_id), self.parent_of(widget_id)
        self._checkpoint()
        clone = copy.deepcopy(src)
        for n in self.walk(clone):
            n["id"] = self._new_id()
        # Names must be unique across the whole tree, so give them out one at
        # a time with the clone already attached.
        parent["children"].insert(parent["children"].index(src) + 1, clone)
        for n in self.walk(clone):
            n["name"] = self.unique_name(n["name"], exclude_id=n["id"])
        return clone["id"]
