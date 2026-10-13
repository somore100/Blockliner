"""Scan a project folder for the 'Open project' dialog. Pure (no Tk).
Never raises: unreadable things are listed as unsupported with a reason."""
import os

SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__", "venv", ".venv", "env",
             "dist", "build", "target", ".idea", ".vscode", ".mypy_cache", ".pytest_cache",
             ".gradle", "bin", "obj"}
MAX_FILES = 2000
MAX_BYTES = 1_000_000


def scan_folder(root, extensions, max_files=MAX_FILES, max_bytes=MAX_BYTES):
    """[{rel, path, size, language, ok, reason}] sorted by path, plus a bool
    'truncated'. `extensions` maps ".py" -> "python". ok=False rows are shown
    greyed out (other file types, too big, binary)."""
    out, truncated = [], False
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            if len(out) >= max_files:
                truncated = True
                break
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            lang = extensions.get(os.path.splitext(fn)[1].lower())
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            ok, reason = True, ""
            if lang is None:
                ok, reason = False, "no language pack for this file type"
            elif size > max_bytes:
                ok, reason = False, "file is too big"
            elif _looks_binary(path):
                ok, reason = False, "not a text file"
            out.append({"rel": rel, "path": path, "size": size, "language": lang,
                        "ok": ok, "reason": reason})
        if truncated:
            break
    out.sort(key=lambda e: e["rel"].lower())
    return out, truncated


def _looks_binary(path):
    try:
        with open(path, "rb") as f:
            return b"\0" in f.read(4096)
    except OSError:
        return True


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def node_title(rel):
    return os.path.basename(rel)
