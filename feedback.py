"""Leave Feedback: the report itself and how it is sent. Pure module (no Tk).

Reusable: copy feedback.py (and feedback_window.py for the Tk window) into
another app and give it that app's name, version and addresses through
`FeedbackConfig`. Standard library only.

No password or key is ever stored here. A report goes out one of two ways:
  1. to a small RELAY you own (an https URL, see docs/feedback-relay/), which
     holds the mail credentials and forwards the report to the support address;
  2. when no relay is set or it fails, the user's own email app is opened with
     the same report filled in (a mailto: link) and the user presses Send.
System information is only collected when the user ticks the box, and the
exact text is shown to them before anything is sent.
"""
import json
import os
import platform
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

REPORT_TYPES = [
    ("bug", "Bug Report", "BUG"),
    ("suggestion", "Feature Suggestion", "SUGGESTION"),
    ("feedback", "General Feedback", "FEEDBACK"),
    ("question", "Question", "QUESTION"),
    ("other", "Other", "OTHER"),
]
MAX_TITLE = 120
MAX_DESCRIPTION = 5000
MAX_NAME = 80
MIN_DESCRIPTION = 10
MAILTO_LIMIT = 1800          # many mail clients and browsers cut longer links


class FeedbackConfig:
    """Everything that differs between apps."""

    def __init__(self, app_name, app_version, to_address, relay_url=""):
        self.app_name = app_name
        self.app_version = app_version
        self.to_address = to_address
        self.relay_url = relay_url or ""


def type_label(type_key):
    return next((label for k, label, _tag in REPORT_TYPES if k == type_key), "Other")


def type_tag(type_key):
    return next((tag for k, _label, tag in REPORT_TYPES if k == type_key), "OTHER")


def clean_line(text, limit):
    """One line of text: control characters and newlines turned into spaces."""
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", str(text or ""))).strip()[:limit]


def validate(form):
    """[problem text] for a form dict {type, name, title, description}; [] = fine."""
    problems = []
    if form.get("type") not in {k for k, _l, _t in REPORT_TYPES}:
        problems.append("Choose a report type.")
    if not clean_line(form.get("title"), MAX_TITLE):
        problems.append("Add a short title.")
    description = str(form.get("description") or "").strip()
    if len(description) < MIN_DESCRIPTION:
        problems.append(f"Describe it in at least {MIN_DESCRIPTION} characters.")
    if len(description) > MAX_DESCRIPTION:
        problems.append(f"The description is too long (most {MAX_DESCRIPTION} characters).")
    return problems


def build_subject(config, form):
    """[Blockliner] [BUG] UI is not working"""
    return f"[{config.app_name}] [{type_tag(form.get('type'))}] {clean_line(form.get('title'), MAX_TITLE)}"


def build_body(config, form, system=None):
    """The structured plain-text body; `system` is the text from system_text()
    when the user chose to include it."""
    lines = [
        f"Application: {config.app_name}",
        f"Version: {config.app_version}",
        f"Report type: {type_label(form.get('type'))}",
        f"Name: {clean_line(form.get('name'), MAX_NAME) or '(not given)'}",
        f"Title: {clean_line(form.get('title'), MAX_TITLE)}",
        "",
        "Description:",
        str(form.get("description") or "").strip()[:MAX_DESCRIPTION],
        "",
    ]
    if system:
        lines += ["System information (included by the user):", system.strip()]
    else:
        lines += ["System information: not included"]
    return "\n".join(lines) + "\n"


def build_payload(config, form, system=None):
    """What the relay receives (JSON): the mail parts plus the raw fields."""
    return {
        "app": config.app_name,
        "version": config.app_version,
        "to": config.to_address,
        "type": form.get("type"),
        "subject": build_subject(config, form),
        "body": build_body(config, form, system),
        "system_included": bool(system),
    }


# ---- system information (only on request, nothing identifying) ----------
def _run(cmd, timeout=4):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError, ValueError):
        return ""


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _cpu():
    if sys.platform.startswith("linux"):
        m = re.search(r"model name\s*:\s*(.+)", _read("/proc/cpuinfo"))
        if m:
            return m.group(1).strip()
    elif sys.platform == "darwin":
        return _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    elif sys.platform == "win32":
        out = _run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"])
        if out:
            return out.splitlines()[0].strip()
    return platform.processor() or "unknown"


def _ram_bytes():
    if sys.platform.startswith("linux"):
        m = re.search(r"MemTotal:\s*(\d+)\s*kB", _read("/proc/meminfo"))
        return int(m.group(1)) * 1024 if m else 0
    if sys.platform == "darwin":
        out = _run(["sysctl", "-n", "hw.memsize"])
        return int(out) if out.isdigit() else 0
    if sys.platform == "win32":
        out = _run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"])
        return int(out) if out.isdigit() else 0
    return 0


def _gpus():
    names = []
    if sys.platform.startswith("linux"):
        for line in _run(["lspci"]).splitlines():
            if re.search(r"VGA|3D controller|Display controller", line):
                names.append(line.split(": ", 1)[-1].strip())
    elif sys.platform == "darwin":
        for line in _run(["system_profiler", "SPDisplaysDataType"], timeout=8).splitlines():
            if "Chipset Model" in line:
                names.append(line.split(":", 1)[-1].strip())
    elif sys.platform == "win32":
        out = _run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name"])
        names = [n.strip() for n in out.splitlines() if n.strip()]
    return names


def collect_system():
    """{"os", "cpu", "gpu", "ram", "arch", "python"}: values as short text.
    Never the user name, computer name, serial numbers, IP or paths."""
    ram = _ram_bytes()
    return {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})".strip(),
        "cpu": _cpu(),
        "gpu": ", ".join(_gpus()) or "unknown",
        "ram": f"{ram / 1024 ** 3:.1f} GB" if ram else "unknown",
        "arch": platform.machine() or "unknown",
        "python": platform.python_version(),
    }


def system_text(info, config=None):
    """The block of text shown to the user and put in the report."""
    lines = [
        f"Operating system: {info.get('os', 'unknown')}",
        f"CPU: {info.get('cpu', 'unknown')}",
        f"GPU: {info.get('gpu', 'unknown')}",
        f"RAM: {info.get('ram', 'unknown')}",
        f"Architecture: {info.get('arch', 'unknown')}",
        f"Python: {info.get('python', 'unknown')}",
    ]
    if config is not None:
        lines.append(f"Application version: {config.app_version}")
    return "\n".join(lines)


# ---- sending ---------------------------------------------------------------
def mailto_url(to_address, subject, body):
    """A mailto: link; the body is cut (with a note) to stay under MAILTO_LIMIT."""
    base = f"mailto:{to_address}?subject={urllib.parse.quote(subject)}&body="
    note = "\n[... cut: copy the full report from the Blockliner feedback window]"
    room = max(0, MAILTO_LIMIT - len(base))
    encoded = urllib.parse.quote(body)
    if len(encoded) > room:
        keep = body
        while keep and len(urllib.parse.quote(keep + note)) > room:
            keep = keep[: int(len(keep) * 0.9)]
        encoded = urllib.parse.quote(keep + note)
    return base + encoded


def relay_ok(url):
    """Only a real https address is used as a relay."""
    parts = urllib.parse.urlparse(str(url or ""))
    return parts.scheme == "https" and bool(parts.netloc)


def send_via_relay(url, payload, timeout=15, opener=None):
    """(True, message) when the relay accepted it, else (False, why).
    The relay answers JSON {"ok": true} or {"ok": false, "error": "..."}."""
    if not relay_ok(url):
        return False, "No feedback relay is set up."
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "text/plain;charset=utf-8"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as resp:
            text = resp.read(65536).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return False, f"The server answered {e.code}."
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, f"Could not reach the server ({getattr(e, 'reason', e)})."
    try:
        answer = json.loads(text)
    except ValueError:
        return False, "The server's answer was not understood."
    if not isinstance(answer, dict):
        return False, "The server refused the report."
    if answer.get("ok"):
        return True, "Thank you! Your report was sent."
    return False, str(answer.get("error") or "The server refused the report.")


def load_relay_url(settings=None, base_dir=None):
    """The relay address: the user's setting first, then feedback_config.json
    next to the program ({"relay_url": "https://..."}), else ""."""
    url = (settings or {}).get("feedback_relay_url") if isinstance(settings, dict) else ""
    if url:
        return url
    try:
        with open(os.path.join(base_dir or ".", "feedback_config.json"), encoding="utf-8") as f:
            return str(json.load(f).get("relay_url") or "")
    except (OSError, ValueError, AttributeError):
        return ""
