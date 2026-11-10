"""Runs a generated Python program in its OWN process (no Tk, pure).

Why: running it inside Blockliner meant a loop could never be stopped, two runs
mixed their output, sys.exit() or os._exit() hit the app itself, and nothing showed
until the program ended. Here the program is a separate Python: output arrives as it
is printed, input() reads a line we send, Stop ends it (and anything it started),
and whatever it does cannot touch the app.

ProgramRun.events is a queue of ("out", text), ("err", text) and finally ("end", code).
"""
import atexit
import codecs
import os
import queue
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading

PROGRAM_NAME = "your program"            # shown in tracebacks instead of the temp file's long path
GRACE_SECONDS = 1.5                      # between "please stop" and "stop now"
_ACTIVE = set()


class RunnerError(Exception):
    """The program could not be started; the message says what to do."""


def python_candidates(command):
    """Programs to try, best first: what Settings says, the usual other names, and (running
    from source) the Python that runs Blockliner. A packaged app is never a candidate."""
    command = (command or "").strip() or "python3"
    try:
        parts = shlex.split(command, posix=(os.name != "nt"))
    except ValueError:
        parts = [command]
    out = [parts or [command]]
    if command in ("python3", "python", "py"):
        for other in ("python3", "python", "py"):
            if [other] not in out:
                out.append([other])
    if not getattr(sys, "frozen", False) and [sys.executable] not in out:
        out.append([sys.executable])
    return out


def find_python(command):
    """The first candidate that exists, as an argument list, or None."""
    for parts in python_candidates(command):
        if shutil.which(parts[0]) or os.path.isfile(parts[0]):
            return parts
    return None


class ProgramRun:
    def __init__(self, source, python_command="python3", cwd=None, queue_size=2000):
        self.source = source
        self.python_command = python_command
        self.cwd = cwd if cwd and os.path.isdir(cwd) else None
        self.events = queue.Queue(maxsize=queue_size)     # bounded: a program that floods us waits instead of eating memory
        self.proc = None
        self.returncode = None
        self.stopped = False
        self.folder = None
        self.path = None
        self._closed = False
        self._readers = []

    # ---- starting ------------------------------------------------------------------
    def start(self):
        exe = find_python(self.python_command)
        if exe is None:
            raise RunnerError(f"Blockliner could not find Python ('{self.python_command}').\n"
                              "Set the Python command in Settings (for example python3, python or the full path).")
        self.folder = tempfile.mkdtemp(prefix="blockliner_run_")
        self.path = os.path.join(self.folder, "blockliner_program.py")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(self.source)
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            kwargs["start_new_session"] = True            # its own process group, so Stop reaches what it started too
        try:
            self.proc = subprocess.Popen(exe + ["-u", self.path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, cwd=self.cwd or self.folder, env=env, bufsize=0, **kwargs)
        except OSError as e:
            self.cleanup()
            raise RunnerError(f"Could not start Python: {e}")
        _ACTIVE.add(self)
        self._readers = [threading.Thread(target=self._pump, args=(self.proc.stdout, "out"), daemon=True),
                         threading.Thread(target=self._pump, args=(self.proc.stderr, "err"), daemon=True)]
        for t in self._readers:
            t.start()
        threading.Thread(target=self._wait, daemon=True).start()
        return self

    # ---- reading -------------------------------------------------------------------
    def _put(self, item):
        while not self._closed:
            try:
                self.events.put(item, timeout=0.2)
                return True
            except queue.Full:
                continue
        return False

    def _pump(self, stream, kind):
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            while True:
                data = stream.read(4096)
                if not data:
                    break
                text = decoder.decode(data)
                if text and self.path:
                    text = text.replace(self.path, PROGRAM_NAME)
                if text and not self._put((kind, text)):
                    break
        except (OSError, ValueError):
            pass

    def _wait(self):
        code = self.proc.wait()
        for t in self._readers:
            t.join(timeout=1.0)                 # a child that kept the pipe open must not hold us up
        self.returncode = code
        _ACTIVE.discard(self)
        self._put(("end", code))

    # ---- talking to it ---------------------------------------------------------------
    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def send_line(self, text):
        """Answer an input() call. False when the program is no longer listening."""
        if not self.running:
            return False
        try:
            self.proc.stdin.write((text + "\n").encode("utf-8"))
            self.proc.stdin.flush()
            return True
        except (OSError, ValueError):
            return False

    def stop(self, force=False):
        """End the program and anything it started: politely first, then for sure."""
        if not self.running:
            return
        self.stopped = True
        pid = self.proc.pid
        if force:
            self._kill(pid)
            return
        self._signal(pid, False)
        timer = threading.Timer(GRACE_SECONDS, lambda: self._kill(pid) if self.running else None)
        timer.daemon = True
        timer.start()

    def _signal(self, pid, hard):
        try:
            if os.name == "nt":
                self.proc.kill() if hard else self.proc.terminate()
            else:
                os.killpg(pid, signal.SIGKILL if hard else signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass

    def _kill(self, pid):
        self._signal(pid, True)

    def cleanup(self):
        """Drop the temp script and stop caring about output (call when the run is over)."""
        self._closed = True
        _ACTIVE.discard(self)
        if self.folder:
            shutil.rmtree(self.folder, ignore_errors=True)
            self.folder = None


def _stop_all():
    for run in list(_ACTIVE):
        try:
            run.stop(force=True)
            run.cleanup()
        except Exception:
            pass


atexit.register(_stop_all)
