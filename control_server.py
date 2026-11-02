"""Local control channel for outside AI tools (pure, no Tk). See
docs/design-extensions.md section 14.

A tiny server on the loopback address only. Every request carries a random token
that exists only while the channel is on. Requests are JSON lines:

    -> {"id": 1, "token": "...", "method": "read_project", "params": {}}
    <- {"id": 1, "result": {...}}        or     {"id": 1, "error": {"code": "...", "message": "..."}}

Which methods may run depends on the access level the user chose ("read" or
"edit"). The server only checks the token and the level; what a method does is up
to the handler the app supplies (it runs on a server thread and may block while the
app, on its own thread, answers).
"""
import collections
import hmac
import json
import os
import secrets
import socketserver
import threading
import time

READ_METHODS = {"read_project", "list_blocks"}
EDIT_METHODS = {"edit_project", "undo"}
MAX_LINE = 1_000_000
MAX_CONNECTIONS = 8
IDLE_SECONDS = 300
LOG_SIZE = 100


class ControlError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class ControlServer:

    def __init__(self, handler, access="read"):
        self.handler, self.access = handler, access if access in ("read", "edit") else "read"
        self.token = ""
        self.port = 0
        self.log = collections.deque(maxlen=LOG_SIZE)     # (time, method, "ok" | error text)
        self._server = None
        self._connections = 0
        self._lock = threading.Lock()

    @property
    def running(self):
        return self._server is not None

    def start(self):
        """Listen on 127.0.0.1 on a free port; returns (port, token)."""
        if self._server is not None:
            return self.port, self.token
        self.token = secrets.token_urlsafe(24)
        outer = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                outer._serve(self)

        self._server = _Server(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self.port, self.token

    def stop(self):
        server, self._server = self._server, None
        self.token = ""
        if server is not None:
            server.shutdown()
            server.server_close()

    # ---- one connection ---------------------------------------------------------
    def _serve(self, conn):
        with self._lock:
            if self._connections >= MAX_CONNECTIONS:
                return
            self._connections += 1
        try:
            conn.request.settimeout(IDLE_SECONDS)
            while self._server is not None:
                try:
                    line = conn.rfile.readline(MAX_LINE + 1)
                except OSError:
                    return
                if not line:
                    return
                if len(line) > MAX_LINE:
                    self._reply(conn, None, error=("too_big", "the request is too large"))
                    return
                self._request(conn, line)
        finally:
            with self._lock:
                self._connections -= 1

    def _reply(self, conn, rid, result=None, error=None):
        msg = {"id": rid, "error": {"code": error[0], "message": error[1]}} if error else {"id": rid, "result": result}
        try:
            conn.wfile.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
            conn.wfile.flush()
        except OSError:
            pass

    def _request(self, conn, line):
        try:
            msg = json.loads(line)
            if not isinstance(msg, dict):
                raise ValueError
        except ValueError:
            return self._reply(conn, None, error=("bad_request", "not a JSON object"))
        rid, method = msg.get("id"), msg.get("method")
        token = msg.get("token")
        if not (isinstance(token, str) and self.token and hmac.compare_digest(token, self.token)):
            self.log.append((time.time(), str(method), "unauthorized"))
            return self._reply(conn, rid, error=("unauthorized", "wrong or missing token"))
        if method in EDIT_METHODS and self.access != "edit":
            self.log.append((time.time(), method, "denied"))
            return self._reply(conn, rid, error=("denied", "this connection is read-only; the user can allow editing in Blockliner"))
        if method not in READ_METHODS and method not in EDIT_METHODS:
            return self._reply(conn, rid, error=("unknown_method", f"unknown method {method!r}"))
        try:
            result = self.handler(method, msg.get("params") if isinstance(msg.get("params"), dict) else {})
        except ControlError as e:
            self.log.append((time.time(), method, e.code))
            return self._reply(conn, rid, error=(e.code, e.message))
        except Exception as e:                       # a handler bug must not drop the connection
            self.log.append((time.time(), method, "failed"))
            return self._reply(conn, rid, error=("failed", f"Blockliner could not do that ({e})"))
        self.log.append((time.time(), method, "ok"))
        self._reply(conn, rid, result=result)


# ---- the file the bridge reads to find the running app -----------------------------------
def write_control_file(path, port, token, access):
    """Owner-only file {"host", "port", "token", "access", "pid"} (written whole, then moved into place)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"host": "127.0.0.1", "port": port, "token": token, "access": access, "pid": os.getpid()}, f)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def remove_control_file(path):
    try:
        os.remove(path)
    except OSError:
        pass


def read_control_file(path):
    """The saved connection details, or None when the channel is off / the file is unusable."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    ok = (isinstance(data, dict) and data.get("host") == "127.0.0.1" and isinstance(data.get("port"), int)
          and isinstance(data.get("token"), str) and data["token"])
    return data if ok else None
