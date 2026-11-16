"""Who else is in the followed folder, and where (pure: no Tk). See docs/team-editing.md, phase B.

Every running Blockliner that follows a folder writes one small JSON file, `<folder>/.blockliner/presence/<id>.json`,
saying which nodes it has open and which it is editing (with the line they start at). The others already look at that
folder, so a shared or synced folder is all it takes: no server. A file nobody refreshed for STALE_SECONDS is ignored
(and cleaned up); a clean exit removes its own file. Presence is advice only - the merge is the safety net."""
import hashlib
import json
import os
import re
import time

from safe_write import write_text_atomic

VERSION = 1
STALE_SECONDS = 30
HEARTBEAT_SECONDS = 5          # rewritten at least this often while running
EDIT_SECONDS = 20              # "editing" lasts this long after the last change
SUBDIR = os.path.join(".blockliner", "presence")
_SAFE = re.compile(r"[^A-Za-z0-9_\-]")
PALETTE = ["#e5484d", "#f5a524", "#3ecf8e", "#4aa8ff", "#a78bfa", "#f472b6", "#2dd4bf", "#fb923c"]


def clean_name(name):
    name = _SAFE.sub("", (name or "").replace(" ", "_"))[:24]
    return name or "user"


def color_for(name):
    return PALETTE[int(hashlib.sha1((name or "").encode("utf-8")).hexdigest(), 16) % len(PALETTE)]


def folder_of(root):
    return os.path.join(root, SUBDIR)


def path_of(root, pid):
    return os.path.join(folder_of(root), f"{clean_name(pid)}.json")


def build(pid, user, color, files, now=None):
    """The document for one running app. files = {rel: {"open": [node ids], "editing": {node id: {"line": n}}}}."""
    return {"v": VERSION, "id": pid, "user": user, "color": color, "updated": now if now is not None else time.time(),
            "files": files}


def write(root, doc):
    write_text_atomic(path_of(root, doc["id"]), json.dumps(doc, indent=1))


def remove(root, pid):
    try:
        os.remove(path_of(root, pid))
    except OSError:
        pass


def read_others(root, own_id, now=None, stale=STALE_SECONDS):
    """[doc] of the other apps that refreshed within `stale` seconds; stale files of others are deleted."""
    now = now if now is not None else time.time()
    out = []
    folder = folder_of(root)
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for name in sorted(names):
        if not name.endswith(".json"):
            continue
        path = os.path.join(folder, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict) or doc.get("id") == own_id or not isinstance(doc.get("files"), dict):
            continue
        try:
            age = now - float(doc.get("updated", 0))
        except (TypeError, ValueError):
            continue
        if age > stale:
            if age > stale * 4:                         # long dead (a crash): tidy up
                try:
                    os.remove(path)
                except OSError:
                    pass
            continue
        out.append(doc)
    return out


def by_node(docs, now=None):
    """{(rel, node id): [{"user", "color", "editing": bool, "line": int|None}]} for the nodes others have open."""
    now = now if now is not None else time.time()
    out = {}
    for doc in docs:
        for rel, info in (doc.get("files") or {}).items():
            if not isinstance(info, dict):
                continue
            editing = info.get("editing") if isinstance(info.get("editing"), dict) else {}
            for nid in list(info.get("open") or []) + [n for n in editing if n not in (info.get("open") or [])]:
                e = editing.get(nid)
                line = e.get("line") if isinstance(e, dict) and isinstance(e.get("line"), int) else None
                out.setdefault((rel, nid), []).append(
                    {"user": str(doc.get("user", "?"))[:24], "color": str(doc.get("color", "#888888")),
                     "editing": e is not None, "line": line})
    return out


def tag(people):
    """The short text for a node box: '✎ Anna · line 42' for someone editing, '● Ben' for someone with it open."""
    parts = []
    for p in sorted(people, key=lambda q: (not q["editing"], q["user"])):
        text = ("✎ " if p["editing"] else "● ") + p["user"]
        if p["editing"] and p.get("line"):
            text += f" · line {p['line']}"
        parts.append(text)
    return "   ".join(parts)


def ensure_git_excluded(root):
    """Add `.blockliner/` to .git/info/exclude (once) so presence files never get committed. True when added."""
    exclude = os.path.join(root, ".git", "info", "exclude")
    if not os.path.isdir(os.path.join(root, ".git")):
        return False
    try:
        os.makedirs(os.path.dirname(exclude), exist_ok=True)
        text = ""
        if os.path.exists(exclude):
            with open(exclude, "r", encoding="utf-8") as f:
                text = f.read()
        if any(line.strip() in (".blockliner", ".blockliner/") for line in text.splitlines()):
            return False
        with open(exclude, "a", encoding="utf-8") as f:
            f.write(("" if not text or text.endswith("\n") else "\n") + ".blockliner/\n")
        return True
    except OSError:
        return False
