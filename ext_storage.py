"""Settings and secrets of extensions (pure, no Tk).

Each extension gets its own folder under user_data/extension_data/<id>/ (never
inside the extension's own folder, and never inside a project):

    settings.json   its settings
    secrets.json    its API keys and the like, written with owner-only permissions

Nothing here is part of a project save, an export or a feedback report. The
manager can say that a secret exists, never what it is.
"""
import json
import os
import re
import shutil
import threading

MAX_KEY = 80
MAX_SETTINGS_BYTES = 64 * 1024
MAX_SECRET = 4096
MAX_SECRETS = 20
_KEY = re.compile(r"^[A-Za-z0-9_.-]{1,%d}$" % MAX_KEY)


class StorageError(Exception):
    pass


def folder_name(ext_id):
    """'author/name' -> 'author__name' (ids are already limited to a-z 0-9 - _)."""
    return ext_id.replace("/", "__")


class ExtStorage:

    def __init__(self, root):
        self.root = root
        self._lock = threading.Lock()

    def _dir(self, ext_id):
        return os.path.join(self.root, folder_name(ext_id))

    def _read(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, ext_id, name, data, private):
        os.makedirs(self._dir(ext_id), exist_ok=True)
        path = os.path.join(self._dir(ext_id), name)
        tmp = path + ".tmp"
        text = json.dumps(data, ensure_ascii=False, indent=2)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600 if private else 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)                          # whole file or nothing
        if private:
            os.chmod(path, 0o600)

    # ---- settings -------------------------------------------------------------
    def get_settings(self, ext_id, key=None):
        with self._lock:
            data = self._read(os.path.join(self._dir(ext_id), "settings.json"))
        return data if key is None else data.get(key)

    def set_setting(self, ext_id, key, value):
        if not isinstance(key, str) or not _KEY.match(key):
            raise StorageError(f"a setting name is letters, digits, _ . - (most {MAX_KEY})")
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            raise StorageError("the value must be JSON (text, number, list, object)")
        with self._lock:
            data = self._read(os.path.join(self._dir(ext_id), "settings.json"))
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
            if len(json.dumps(data)) > MAX_SETTINGS_BYTES:
                raise StorageError("the settings are too big")
            self._write(ext_id, "settings.json", data, private=False)

    # ---- secrets ----------------------------------------------------------------
    def get_secret(self, ext_id, name):
        with self._lock:
            value = self._read(os.path.join(self._dir(ext_id), "secrets.json")).get(name)
        return value if isinstance(value, str) else None

    def set_secret(self, ext_id, name, value):
        """value None deletes it."""
        if not isinstance(name, str) or not _KEY.match(name):
            raise StorageError(f"a secret name is letters, digits, _ . - (most {MAX_KEY})")
        if value is not None and (not isinstance(value, str) or len(value) > MAX_SECRET):
            raise StorageError(f"a secret is text of at most {MAX_SECRET} characters")
        with self._lock:
            path = os.path.join(self._dir(ext_id), "secrets.json")
            data = self._read(path)
            if value is None:
                data.pop(name, None)
            else:
                data[name] = value
            if len(data) > MAX_SECRETS:
                raise StorageError(f"at most {MAX_SECRETS} secrets")
            self._write(ext_id, "secrets.json", data, private=True)

    def secret_names(self, ext_id):
        """Names only: what the manager may show."""
        with self._lock:
            return sorted(self._read(os.path.join(self._dir(ext_id), "secrets.json")))

    # ---- removal ----------------------------------------------------------------
    def delete_all(self, ext_id):
        """Remove the extension's saved settings and secrets."""
        folder = self._dir(ext_id)
        if os.path.isdir(folder) and os.path.realpath(folder).startswith(os.path.realpath(self.root) + os.sep):
            shutil.rmtree(folder, ignore_errors=True)
