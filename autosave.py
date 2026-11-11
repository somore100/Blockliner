"""Recovery copies of unsaved projects (pure, no Tk).

Every minute or so the app writes the projects with unsaved changes into a recovery folder, NEVER over the
user's own file. A normal save, closing the project or quitting on purpose deletes its copy; what is left after a
crash is offered back at the next start."""
import json
import os
import re
import time

from safe_write import write_text_atomic

VERSION = 1
MAX_AGE_DAYS = 30
DEFAULT_SECONDS = 60
MIN_SECONDS = 10
MAX_SECONDS = 3600
_ID = re.compile(r"[A-Za-z0-9_\-]{1,64}")


def seconds(settings):
    """Seconds between recovery copies; 0 means off. Anything odd falls back to the default."""
    value = (settings if isinstance(settings, dict) else {}).get("autosave_seconds", DEFAULT_SECONDS)
    try:
        value = int(float(value))
    except (TypeError, ValueError):
        return DEFAULT_SECONDS
    if value <= 0:
        return 0
    return max(MIN_SECONDS, min(MAX_SECONDS, value))


def _path(folder, rid):
    if not _ID.fullmatch(str(rid)):
        raise ValueError("bad recovery id")
    return os.path.join(folder, f"{rid}.recovery.json")


def write_snapshot(folder, rid, project_text, title, filepath, now=None):
    """Store one project's current text. project_text is the project file text (project_file.dumps_workspace)."""
    data = {"blockliner_recovery": VERSION, "id": rid, "title": title or "Untitled", "filepath": filepath or None,
            "saved_at": time.time() if now is None else now, "project": json.loads(project_text)}
    write_text_atomic(_path(folder, rid), json.dumps(data))


def remove(folder, rid):
    try:
        os.unlink(_path(folder, rid))
    except (OSError, ValueError):
        pass


def clear_all(folder):
    for name in _names(folder):
        try:
            os.unlink(os.path.join(folder, name))
        except OSError:
            pass


def _names(folder):
    try:
        return [n for n in os.listdir(folder) if n.endswith(".recovery.json")]
    except OSError:
        return []


def list_snapshots(folder, now=None):
    """Recovery copies that can be offered, newest first: {"id", "title", "filepath", "saved_at", "project"}.
    Damaged files are skipped and copies older than MAX_AGE_DAYS are deleted."""
    now = time.time() if now is None else now
    out = []
    for name in _names(folder):
        path = os.path.join(folder, name)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or data.get("blockliner_recovery") != VERSION or not isinstance(data.get("project"), dict):
                continue
            rid = data.get("id")
            if not isinstance(rid, str) or not _ID.fullmatch(rid) or name != f"{rid}.recovery.json":
                continue
            saved = data.get("saved_at")
            saved = float(saved) if isinstance(saved, (int, float)) and not isinstance(saved, bool) else 0.0
        except (OSError, ValueError):
            continue
        if now - saved > MAX_AGE_DAYS * 86400:
            try:
                os.unlink(path)
            except OSError:
                pass
            continue
        title = data.get("title") if isinstance(data.get("title"), str) and data.get("title") else "Untitled"
        fp = data.get("filepath") if isinstance(data.get("filepath"), str) else None
        out.append({"id": rid, "title": title, "filepath": fp, "saved_at": saved, "project": data["project"]})
    out.sort(key=lambda s: s["saved_at"], reverse=True)
    return out
