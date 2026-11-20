"""GitHub workflow import: the small YAML reader, the job graph, and the generated Python (it must run). Pure, no Tk."""
import os, sys, subprocess, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import workflow_import as W
import portable

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

# --- the YAML reader
y = W.parse_yaml("""
# a comment
name: "CI # not a comment"
on:
  push:
    branches: [main, 'dev']
  pull_request:
env: {A: 1, B: x}
list:
  - one
  - two: 2
    three: true
  -
    - nested
text: |
  line one
    indented
  line three

after: 5
folded: >-
  a
  b
""")
check("scalars and quotes", y["name"] == "CI # not a comment" and y["after"] == 5)
check("flow lists and maps", y["on"]["push"]["branches"] == ["main", "dev"] and y["env"] == {"A": 1, "B": "x"} and y["on"]["pull_request"] is None)
check("lists of mappings and lists", y["list"] == ["one", {"two": 2, "three": True}, ["nested"]])
check("block scalars", y["text"] == "line one\n  indented\nline three\n" and y["folded"] == "a b")
for bad, label in (("a: &x 1", "anchors"), ("a: 1\n---\nb: 2", "second document"), ("a:\n\tb: 1", "tabs"), ("a: 1\na: 2", "duplicate keys")):
    try:
        W.parse_yaml(bad); check(f"{label} are refused", False)
    except W.YamlError:
        check(f"{label} are refused", True)

# --- a realistic workflow
WF = """
name: CI
on:
  push:
    branches: [main]
  pull_request:
env:
  CI: true
jobs:
  build:
    name: Build it
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Say hi
        run: echo "hi from build"
      - name: Two lines
        run: |
          echo one
          echo two
        env:
          WHO: me
  test:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - run: echo testing
        working-directory: .
  lint:
    needs: [build]
    if: github.event_name == 'push'
    steps:
      - run: echo lint
  deploy:
    needs: [test, lint]
    steps:
      - name: Ship
        run: echo shipping
"""
wf = W.parse_workflow(WF)
check("four jobs with their needs", [(j["id"], j["needs"]) for j in wf["jobs"]] == [("build", []), ("test", ["build"]), ("lint", ["build"]), ("deploy", ["test", "lint"])])
check("triggers are read", set(wf["on"]) == {"push", "pull_request"})
chunks, notes = W.workflow_to_chunks(WF)
names = [n for n, _c in chunks]
check("a node per job plus helpers and main", names == ["workflow", "job_build", "job_test", "job_lint", "job_deploy", "main"])
code = dict(chunks)
check("needs become calls (wires)", "job_build()" in code["job_test"] and "job_test()" in code["job_deploy"] and "job_lint()" in code["job_deploy"])
check("a uses step is kept as a comment", "# step: actions/checkout@v4" in code["job_build"] or "uses actions/checkout@v4" in code["job_build"])
check("notes name the skipped parts", any("actions/checkout" in n for n in notes) and any("condition" in n for n in notes))
check("main runs only the last job", code["main"].count("job_") == 1 and "job_deploy()" in code["main"])

# --- the text opens as nodes, and it runs in the right order, each job once
text, _n = W.workflow_to_marked_text(WF)
check("it has node markers", portable.NODE_MARKER_RE.search(text) is not None)
plain = portable.strip_portable(text)
with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "wf.py")
    open(path, "w").write(plain)
    out = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=30)
lines = out.stdout.split()
check(f"it runs ({out.stderr.strip()[:80]})", out.returncode == 0)
check("each job ran once, dependencies first", out.stdout.count("hi from build") == 1 and out.stdout.index("hi from build") < out.stdout.index("testing") < out.stdout.index("shipping"))
check("a multi-line step and its env work", "one" in lines and "two" in lines)

# --- problems are reported, not guessed
for bad, label in (("on: push\n", "no jobs"), ("jobs:\n  a:\n    needs: b\n    steps: []\n", "needs a missing job"),
                   ("jobs:\n  a:\n    needs: b\n  b:\n    needs: a\n", "a needs loop")):
    try:
        W.workflow_to_chunks(bad); check(f"{label} is refused", False)
    except W.YamlError:
        check(f"{label} is refused", True)

print("\nFAILED: " + ", ".join(FAILURES) if FAILURES else "\nALL PASS")
sys.exit(1 if FAILURES else 0)
