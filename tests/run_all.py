"""Runs every test script, each in its own process with its own empty data folder.

    python tests/run_all.py                 all tests (window tests need a display: on Linux use xvfb-run)
    python tests/run_all.py --pure          only tests that need no window
    python tests/run_all.py --window        only tests that open the app
    python tests/run_all.py NAME ...        only tests whose file name contains NAME
    python tests/run_all.py --strict        (CI) a test skipped for a missing module counts as a failure
    python tests/run_all.py --timeout 90    seconds per test (default 120)
    python tests/run_all.py --python "CMD"   run the tests with another Python / wrapper

Exit status 0 when nothing unexpected failed. Known failures live in tests/expected_failures.txt.
Why each test runs apart: the app is one big window object, a test that dies or hangs must not take the
others with it, and a test must never read or write the real user data folder."""
import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MISSING = re.compile(r"ModuleNotFoundError: No module named '([\w.]+)'")


def needs_window(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    return "tkinter" in text or "BlocklinerUI" in text


def expected_failures():
    out = {}
    path = os.path.join(HERE, "expected_failures.txt")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    name, _, why = line.partition("#")
                    out[name.strip()] = why.strip()
    return out


def run_test(path, timeout, python):
    """-> (status, seconds, output). status: PASS, FAIL, TIMEOUT or SKIP:<module>."""
    data = tempfile.mkdtemp(prefix="blockliner_test_data_")
    env = dict(os.environ, BLOCKLINER_DATA_DIR=data, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    start = time.time()
    try:
        done = subprocess.run(python + [os.path.join(HERE, "run_one.py"), path], cwd=ROOT, env=env,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        out = (done.stdout or "") + (done.stderr or "")
        status = "PASS" if done.returncode == 0 else "FAIL"
        if status == "FAIL":
            m = MISSING.search(out)
            if m and "[FAIL]" not in out:
                status = f"SKIP:{m.group(1)}"
    except subprocess.TimeoutExpired as e:
        raw = e.stdout or b""
        out = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        status = "TIMEOUT"
    finally:
        shutil.rmtree(data, ignore_errors=True)
    return status, time.time() - start, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*")
    ap.add_argument("--pure", action="store_true")
    ap.add_argument("--window", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--python", default=None, help="the Python that runs each test (default: the one running this script)")
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(HERE) if f.startswith("test_") and f.endswith(".py"))
    if args.names:
        files = [f for f in files if any(n in f for n in args.names)]
    python = shlex.split(args.python) if args.python else [sys.executable]
    xfail = expected_failures()
    has_display = bool(os.environ.get("DISPLAY")) or sys.platform in ("win32", "darwin")
    counts = {"PASS": 0, "FAIL": 0, "XFAIL": 0, "XPASS": 0, "SKIP": 0}
    bad = []
    for name in files:
        path = os.path.join(HERE, name)
        window = needs_window(path)
        if (args.pure and window) or (args.window and not window):
            continue
        if window and not has_display:
            print(f"SKIP   {name}  (no display: on Linux run under xvfb-run)")
            counts["SKIP"] += 1
            if args.strict:
                bad.append(name)
            continue
        status, secs, out = run_test(path, args.timeout, python)
        if status == "PASS" and name in xfail:
            label = "XPASS"
        elif status != "PASS" and name in xfail:
            label = "XFAIL"
        elif status.startswith("SKIP") and not args.strict:
            label = "SKIP"
        elif status == "PASS":
            label = "PASS"
        else:
            label = "FAIL"
        key = "FAIL" if label in ("FAIL",) else label
        counts[key] += 1
        shown = status if status in ("TIMEOUT",) or status.startswith("SKIP") else ""
        print(f"{label:6} {name}  ({secs:.1f}s){'  ' + shown if shown and shown != label else ''}")
        if label == "FAIL":
            bad.append(name)
            print("   " + "\n   ".join(out.strip().splitlines()[-25:]))
    print()
    print("  ".join(f"{k}: {v}" for k, v in counts.items() if v) or "no tests found")
    if bad:
        print("Failed: " + ", ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
