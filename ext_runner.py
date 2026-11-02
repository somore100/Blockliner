"""Running outside extensions (pure, no Tk): start a program, speak JSON lines
with it, keep it from ever blocking or crashing Blockliner. See
docs/design-extensions.md (sections 4 and 5).

    Blockliner -> extension   {"event": "hello" | "command" | "shutdown" | ..., "params": {...}}
    extension -> Blockliner   {"event": "ready", "params": {"api": ["1.0"]}}       (first message)
                              {"id": 7, "method": "panel.set", "params": {...}}    (a request)
    Blockliner -> extension   {"id": 7, "result": {...}}  or  {"id": 7, "error": {"code", "message"}}

Everything that touches the extension happens on background threads. Requests are
checked against the permissions the user granted before any handler runs.
"""
import collections
import json
import subprocess
import threading
import time

PERMISSION_FOR = {                     # method -> permission it needs (None: always allowed)
    "panel.set": "ui.panel", "notify": "ui.notify",
    "project.read": "project.read", "project.edit": "project.write",
    "files.read": "files.read", "files.write": "files.write",
    "settings.get": None, "settings.set": None, "secrets.get": None, "secrets.set": None,
}
LOG_LINES = 200
MAX_RESTARTS = 3


class ExtensionError(Exception):
    """Raised by a handler to answer a request with an error."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def api_text(api):
    return f"{api[0]}.{api[1]}"


class ExtensionProcess:
    """One running extension."""

    def __init__(self, ext_id, folder, command, permissions, handler, api=(1, 0),
                 ready_timeout=5.0, stop_timeout=2.0, popen=subprocess.Popen):
        self.ext_id, self.folder, self.command = ext_id, folder, list(command)
        self.permissions = set(permissions)
        self.handler = handler                 # handler(ext_id, method, params, is_event) -> result
        self.api, self.ready_timeout, self.stop_timeout = api, ready_timeout, stop_timeout
        self._popen = popen
        self.proc = None
        self.state = "stopped"                 # stopped | starting | running | failed
        self.note = ""
        self.log = collections.deque(maxlen=LOG_LINES)
        self.supported_api = []
        self._ready = threading.Event()
        self._write_lock = threading.Lock()

    # ---- start / stop -------------------------------------------------------
    def start(self):
        """True when the extension started and answered hello in time."""
        self.state, self.note = "starting", ""
        self._ready.clear()
        try:
            self.proc = self._popen(self.command, cwd=self.folder, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, bufsize=1, encoding="utf-8", errors="replace")
        except (OSError, ValueError) as e:
            return self._fail(f"could not start ({e})")
        threading.Thread(target=self._read_out, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()
        self.send_event("hello", {"api": api_text(self.api), "id": self.ext_id, "permissions": sorted(self.permissions)})
        if not self._ready.wait(self.ready_timeout):
            self.stop(quick=True)
            return self._fail("did not answer hello in time")
        if api_text(self.api) not in self.supported_api:
            self.stop()
            return self._fail(f"does not support API {api_text(self.api)} (it supports {', '.join(self.supported_api) or 'none'})")
        self.state = "running"
        return True

    def _fail(self, note):
        self.state, self.note = "failed", note
        return False

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self, quick=False):
        """Ask politely (shutdown event), then terminate, then kill."""
        if self.proc is None:
            return
        if not quick and self.alive():
            self.send_event("shutdown", {})
            deadline = time.time() + self.stop_timeout
            while self.alive() and time.time() < deadline:
                time.sleep(0.02)
        for action in (self.proc.terminate, self.proc.kill):
            if not self.alive():
                break
            try:
                action()
            except OSError:
                pass
            for _ in range(50):
                if not self.alive():
                    break
                time.sleep(0.02)
        for pipe in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                pipe and pipe.close()
            except (OSError, ValueError):
                pass
        if self.state != "failed":
            self.state = "stopped"

    # ---- talking ------------------------------------------------------------
    def _send(self, obj):
        if not self.alive():
            return False
        try:
            with self._write_lock:
                self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
                self.proc.stdin.flush()
            return True
        except (OSError, ValueError):
            return False

    def send_event(self, event, params=None):
        return self._send({"event": event, "params": params or {}})

    def _read_out(self):
        try:
            for line in self.proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except ValueError:
                    self.log.append(f"[not JSON] {line[:200]}")
                    continue
                if isinstance(msg, dict):
                    self._handle(msg)
        except (OSError, ValueError):
            pass

    def _read_err(self):
        try:
            for line in self.proc.stderr:
                self.log.append(line.rstrip("\n")[:400])
        except (OSError, ValueError):
            pass

    def _handle(self, msg):
        if msg.get("event") == "ready":
            params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
            self.supported_api = [str(v) for v in params.get("api") or [] if isinstance(v, (str, int, float))]
            self._ready.set()
        elif "method" in msg and "id" in msg:
            self._answer(msg)
        elif isinstance(msg.get("event"), str):
            try:
                self.handler(self.ext_id, msg["event"], msg.get("params") or {}, True)
            except Exception as e:                       # a handler bug must not stop the reader
                self.log.append(f"[handler error] {e}")

    def _answer(self, msg):
        method, params, rid = msg.get("method"), msg.get("params") or {}, msg["id"]
        if method not in PERMISSION_FOR:
            return self._send({"id": rid, "error": {"code": "unknown_method", "message": f"unknown method {method!r}"}})
        need = PERMISSION_FOR[method]
        if need is not None and need not in self.permissions:
            self.log.append(f"[denied] {method} needs {need}")
            return self._send({"id": rid, "error": {"code": "denied", "message": f"{method} needs the {need} permission"}})
        try:
            result = self.handler(self.ext_id, method, params, False)
            self._send({"id": rid, "result": result if result is not None else {}})
        except ExtensionError as e:
            self._send({"id": rid, "error": {"code": e.code, "message": e.message}})
        except Exception as e:
            self.log.append(f"[handler error] {e}")
            self._send({"id": rid, "error": {"code": "failed", "message": "Blockliner could not do that"}})


class Host:
    """All running extensions. `check()` is called now and then (from the UI
    timer): a program that exited is restarted up to MAX_RESTARTS times."""

    def __init__(self, handler, max_restarts=MAX_RESTARTS, **process_options):
        self.handler, self.max_restarts, self.options = handler, max_restarts, process_options
        self.procs, self.restarts, self._specs = {}, {}, {}

    def start(self, ext_id, folder, command, permissions):
        proc = ExtensionProcess(ext_id, folder, command, permissions, self.handler, **self.options)
        self.procs[ext_id] = proc
        self._specs[ext_id] = (folder, command, permissions)
        self.restarts.setdefault(ext_id, 0)
        return proc.start()

    def stop(self, ext_id):
        proc = self.procs.pop(ext_id, None)
        self._specs.pop(ext_id, None)
        self.restarts.pop(ext_id, None)
        if proc:
            proc.stop()

    def stop_all(self):
        for ext_id in list(self.procs):
            self.stop(ext_id)

    def send_event(self, ext_id, event, params=None):
        proc = self.procs.get(ext_id)
        return bool(proc and proc.state == "running" and proc.send_event(event, params))

    def check(self):
        """Restart what died. Returns [(ext_id, note)] for things worth telling the user."""
        news = []
        for ext_id, proc in list(self.procs.items()):
            if proc.state != "running" or proc.alive():
                continue
            if self.restarts[ext_id] >= self.max_restarts:
                proc.state, proc.note = "failed", f"stopped {self.max_restarts + 1} times; turned off until you enable it again"
                news.append((ext_id, proc.note))
                continue
            self.restarts[ext_id] += 1
            folder, command, permissions = self._specs[ext_id]
            proc.stop(quick=True)
            fresh = ExtensionProcess(ext_id, folder, command, permissions, self.handler, **self.options)
            self.procs[ext_id] = fresh
            ok = fresh.start()
            news.append((ext_id, "restarted" if ok else f"could not restart: {fresh.note}"))
        return news

    def status(self, ext_id):
        proc = self.procs.get(ext_id)
        if proc is None:
            return {"state": "stopped", "note": "", "restarts": 0, "log": []}
        return {"state": proc.state, "note": proc.note, "restarts": self.restarts.get(ext_id, 0), "log": list(proc.log)}
