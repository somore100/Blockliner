"""Read a GitHub Actions workflow (.github/workflows/*.yml) and turn it into Python nodes (pure, no Tk).

Each job becomes a function node. Its `needs:` become calls to the jobs it waits for, so the node wires show the job
graph; each `run:` step becomes a `run(...)` call (a shell command), and steps that use a ready-made action
(`uses:`) can't run here and are kept as comments. A "workflow" node holds the helpers and the triggers, and a
"main" node runs the jobs nothing else waits for.

`parse_yaml` is a small reader for the YAML a workflow file uses (block mappings and lists, quoted text, block
scalars `|` and `>`, one-line `[a, b]` / `{a: b}`). It is not full YAML: anchors, tags and multi-document files raise
YamlError instead of being guessed at.
"""
import re

import portable


class YamlError(ValueError):
    pass


# --- a small YAML reader -----------------------------------------------------------------------------------------

def _strip_comment(text):
    """The text without a trailing ` # comment` (a # inside quotes stays)."""
    quote = None
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"" and (i == 0 or text[i - 1] in " \t[{,:-"):
            quote = ch
        elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i].rstrip()
    return text.rstrip()


def _scalar(text):
    text = text.strip()
    if text == "":
        return None
    if text[0] in "&*!":
        raise YamlError(f"anchors, aliases and tags aren't supported: {text}")
    if text[0] == '"':
        if len(text) < 2 or text[-1] != '"':
            raise YamlError(f"unclosed quote: {text}")
        body = text[1:-1]
        return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "/": "/"}.get(m.group(1), "\\" + m.group(1)), body)
    if text[0] == "'":
        if len(text) < 2 or text[-1] != "'":
            raise YamlError(f"unclosed quote: {text}")
        return text[1:-1].replace("''", "'")
    if text[0] == "[" or text[0] == "{":
        return _flow(text)
    low = text.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "~"):
        return None
    if re.fullmatch(r"[-+]?\d+", text):
        return int(text)
    if re.fullmatch(r"[-+]?\d*\.\d+", text):
        return float(text)
    return text


def _split_flow(body):
    parts, depth, quote, cur = [], 0, None, ""
    for ch in body:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            cur += ch
        elif ch in "[{":
            depth += 1
            cur += ch
        elif ch in "]}":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts


def _flow(text):
    if text[0] == "[" and text[-1] == "]":
        return [_scalar(p) for p in _split_flow(text[1:-1])]
    if text[0] == "{" and text[-1] == "}":
        out = {}
        for p in _split_flow(text[1:-1]):
            key, sep, value = p.partition(":")
            if not sep:
                raise YamlError(f"expected 'key: value' in {text}")
            out[str(_scalar(key))] = _scalar(value)
        return out
    raise YamlError(f"unclosed flow collection: {text}")


_KEY = re.compile(r"""((?:"[^"]*"|'[^']*'|[^\s:#'"\[\]{}-][^:#]*?|-[^\s:][^:#]*?))\s*:(?:\s+(.*))?\Z""")


class _Reader:
    def __init__(self, text):
        self.lines = []                       # (indent, text, number) of lines that carry content
        self.raw = text.split("\n")
        for n, line in enumerate(self.raw, 1):
            if "\t" in line[: len(line) - len(line.lstrip())]:
                raise YamlError(f"line {n}: tabs can't indent YAML")
            stripped = _strip_comment(line)
            if stripped.strip() in ("", "---", "..."):
                if stripped.strip() == "---" and self.lines:
                    raise YamlError(f"line {n}: more than one document in a file isn't supported")
                self.lines.append(None)
            else:
                self.lines.append((len(line) - len(line.lstrip()), stripped.strip(), n))
        self.i = 0

    def peek(self):
        while self.i < len(self.lines) and self.lines[self.i] is None:
            self.i += 1
        return self.lines[self.i] if self.i < len(self.lines) else None

    def block(self, indent):
        cur = self.peek()
        if cur is None or cur[0] < indent:
            return None
        indent = cur[0]
        if cur[1].startswith("- ") or cur[1] == "-":
            return self.sequence(indent)
        if _KEY.match(cur[1]):
            return self.mapping(indent)
        self.i += 1
        return _scalar(cur[1])

    def sequence(self, indent):
        out = []
        while True:
            cur = self.peek()
            if cur is None or cur[0] != indent or not (cur[1].startswith("- ") or cur[1] == "-"):
                if cur is not None and cur[0] > indent:
                    raise YamlError(f"line {cur[2]}: unexpected indentation")
                return out
            rest = cur[1][1:].strip()
            if rest == "":
                self.i += 1
                out.append(self.block(indent + 1))
            elif _KEY.match(rest) and rest[0] not in "'\"[{":
                inner = indent + (len(cur[1]) - len(cur[1][1:].lstrip()))
                self.lines[self.i] = (inner, rest, cur[2])         # "- key: v" is a mapping starting at the key
                out.append(self.mapping(inner))
            else:
                self.i += 1
                out.append(self.value(rest, indent))

    def value(self, text, indent):
        """The value written after `key:` or `- `: a scalar, or a block scalar (| or >)."""
        if re.fullmatch(r"[|>][+-]?\d*", text):
            return self.block_scalar(text, indent)
        return _scalar(text)

    def block_scalar(self, head, indent):
        folded = head[0] == ">"
        keep, strip = "+" in head, "-" in head
        lines, base = [], None
        j = self.i
        while j < len(self.raw):
            raw = self.raw[j]
            if raw.strip() == "":
                lines.append("")
                j += 1
                continue
            ind = len(raw) - len(raw.lstrip())
            if ind <= indent:
                break
            if base is None:
                base = ind
            lines.append(raw[base:] if ind >= base else raw.lstrip())
            j += 1
        # the reader's own list mirrors the raw lines one to one, so the scalar's lines are skipped by position
        self.i = j
        while lines and lines[-1] == "" and not keep:
            lines.pop()
        text = "\n".join(lines)
        if folded:                                   # > joins lines with a space; a blank line is a line break
            text = re.sub(r"(?<!\n)\n(?!\n)", " ", text).replace("\n\n", "\n")
        return text if strip else (text + "\n" if text else "")

    def mapping(self, indent):
        out = {}
        while True:
            cur = self.peek()
            if cur is None or cur[0] != indent:
                if cur is not None and cur[0] > indent:
                    raise YamlError(f"line {cur[2]}: unexpected indentation")
                return out
            m = _KEY.match(cur[1])
            if not m or cur[1].startswith("- "):
                return out
            key, rest = str(_scalar(m.group(1))), m.group(2)
            if key in out:
                raise YamlError(f"line {cur[2]}: '{key}' is listed twice")
            self.i += 1
            if rest is None or rest.strip() == "":
                nxt = self.peek()
                if nxt is not None and (nxt[0] > indent or (nxt[0] == indent and nxt[1].startswith("-"))):
                    out[key] = self.block(indent if nxt[0] == indent else indent + 1)
                else:
                    out[key] = None
            else:
                out[key] = self.value(rest.strip(), indent)


def parse_yaml(text):
    """The YAML text as dicts, lists and plain values. Raises YamlError."""
    reader = _Reader(text.replace("\r\n", "\n").replace("\r", "\n"))
    value = reader.block(0)
    rest = reader.peek()
    if rest is not None:
        raise YamlError(f"line {rest[2]}: can't read this line")
    return value


# --- the workflow ------------------------------------------------------------------------------------------------

def parse_workflow(text):
    """{name, on, env, jobs: [{id, name, needs, env, steps: [{name, run, uses, with, env, cwd, if}]}]}.
    Raises YamlError when the text isn't a workflow."""
    data = parse_yaml(text)
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), dict) or not data["jobs"]:
        raise YamlError("this doesn't look like a GitHub workflow: it has no 'jobs'")
    jobs = []
    for jid, job in data["jobs"].items():
        if not isinstance(job, dict):
            raise YamlError(f"job '{jid}' is not a mapping")
        needs = job.get("needs") or []
        needs = [needs] if isinstance(needs, str) else [str(n) for n in needs]
        defaults = ((job.get("defaults") or {}).get("run") or {}) if isinstance(job.get("defaults"), dict) else {}
        steps = []
        for s in job.get("steps") or []:
            if not isinstance(s, dict):
                continue
            steps.append({"name": str(s["name"]) if s.get("name") is not None else None,
                          "run": s["run"] if isinstance(s.get("run"), str) else None,
                          "uses": str(s["uses"]) if s.get("uses") is not None else None,
                          "with": s["with"] if isinstance(s.get("with"), dict) else {},
                          "env": _env(s.get("env")),
                          "cwd": s.get("working-directory") or defaults.get("working-directory"),
                          "if": str(s["if"]) if s.get("if") is not None else None})
        jobs.append({"id": str(jid), "name": str(job["name"]) if job.get("name") else str(jid),
                     "needs": needs, "env": _env(job.get("env")), "steps": steps,
                     "uses": str(job["uses"]) if job.get("uses") else None,
                     "runs_on": job.get("runs-on"), "matrix": bool(isinstance(job.get("strategy"), dict) and job["strategy"].get("matrix")),
                     "if": str(job["if"]) if job.get("if") is not None else None})
    ids = {j["id"] for j in jobs}
    for j in jobs:
        missing = [n for n in j["needs"] if n not in ids]
        if missing:
            raise YamlError(f"job '{j['id']}' needs '{missing[0]}', which isn't a job in this file")
    return {"name": str(data["name"]) if data.get("name") else None,
            "on": data.get("on", data.get(True)),          # YAML 1.1 readers turn a bare `on` key into True
            "env": _env(data.get("env")), "jobs": jobs}


def _env(raw):
    return {str(k): ("" if v is None else str(v).lower() if isinstance(v, bool) else str(v)) for k, v in raw.items()} if isinstance(raw, dict) else {}


def _cycle(jobs):
    """Name of a job in a `needs` cycle, or None."""
    by_id = {j["id"]: j for j in jobs}
    state = {}

    def visit(jid):
        if state.get(jid) == 1:
            return jid
        if state.get(jid) == 2:
            return None
        state[jid] = 1
        for n in by_id[jid]["needs"]:
            hit = visit(n)
            if hit:
                return hit
        state[jid] = 2
        return None
    for j in jobs:
        hit = visit(j["id"])
        if hit:
            return hit
    return None


# --- the nodes ---------------------------------------------------------------------------------------------------

_HELPERS = '''import os
import subprocess
import textwrap

_ran = set()


def run(command, env=None, cwd=None):
    """Run one shell command; stop the workflow if it fails (like a workflow step)."""
    subprocess.run(textwrap.dedent(command), shell=True, check=True, cwd=cwd, env={**os.environ, **(env or {})})


def job(fn):
    """A job runs once, however many other jobs wait for it."""
    def once():
        if fn.__name__ not in _ran:
            _ran.add(fn.__name__)
            fn()
    once.__name__ = fn.__name__
    return once
'''


def _ident(text):
    out = re.sub(r"\W+", "_", text).strip("_").lower() or "job"
    return "job_" + out if not out.startswith("job_") else out


def _string(text):
    """Python source for a string: triple-quoted when it has several lines and nothing that needs escaping."""
    if "\n" in text.rstrip("\n") and '"""' not in text and "\\" not in text and not text.rstrip("\n").endswith('"'):
        return '"""\n' + text.strip("\n") + '\n"""'
    return repr(text.rstrip("\n"))


def _comment(text):
    return "# " + " ".join(str(text).split())


def workflow_to_chunks(text):
    """([(node name, code)], notes). Raises YamlError. Every job is a node named after its id."""
    wf = parse_workflow(text)
    cycle = _cycle(wf["jobs"])
    if cycle:
        raise YamlError(f"job '{cycle}' is part of a 'needs' loop")
    notes = []
    names = {}
    for j in wf["jobs"]:
        base = _ident(j["id"])
        n, k = base, 2
        while n in names.values():
            n, k = f"{base}_{k}", k + 1
        names[j["id"]] = n

    head = [f"# Workflow: {wf['name']}" if wf["name"] else "# Workflow"]
    triggers = wf["on"]
    if isinstance(triggers, str):
        triggers = [triggers]
    if isinstance(triggers, dict):
        triggers = list(triggers)
    if triggers:
        head.append(_comment("runs on: " + ", ".join(str(t) for t in triggers)))
    if wf["env"]:
        head.append("WORKFLOW_ENV = " + repr(wf["env"]))
    chunks = [("workflow", "\n".join(head) + "\n\n" + _HELPERS)]

    for j in wf["jobs"]:
        fname = names[j["id"]]
        body = []
        if j["name"] != j["id"]:
            body.append(_comment(j["name"]))
        if j["runs_on"]:
            body.append(_comment(f"runs-on: {j['runs_on'] if not isinstance(j['runs_on'], (list, dict)) else '(several)'}"))
        if j["if"]:
            body.append(_comment(f"only when: {j['if']}"))
            notes.append(f"job '{j['id']}' has a condition (if:); it runs always here")
        if j["matrix"]:
            body.append(_comment("matrix: this job runs once here, not once per combination"))
            notes.append(f"job '{j['id']}' uses a matrix; it runs once, not per combination")
        for n in j["needs"]:
            body.append(f"{names[n]}()")
        if j["uses"]:
            body.append(_comment(f"uses (reusable workflow, not run here): {j['uses']}"))
            notes.append(f"job '{j['id']}' calls a reusable workflow ({j['uses']}); kept as a comment")
        for k, s in enumerate(j["steps"], 1):
            label = s["name"] or (s["run"].strip().splitlines()[0][:40] if s["run"] and s["run"].strip() else f"step {k}")
            if s["run"] is not None:
                body.append(_comment(f"step: {label}"))
                if s["if"]:
                    body.append(_comment(f"only when: {s['if']}"))
                    notes.append(f"step '{label}' in '{j['id']}' has a condition (if:); it runs always here")
                env = {**wf["env"], **j["env"], **s["env"]}
                args = [_string(s["run"])]
                if env:
                    args.append("env=" + repr(env))
                if s["cwd"]:
                    args.append("cwd=" + repr(str(s["cwd"])))
                body.append(f"run({', '.join(args)})")
            elif s["uses"]:
                body.append(_comment(f"step: {label} - uses {s['uses']} (an action; not run here)"))
                for key, value in s["with"].items():
                    body.append(_comment(f"  with {key}: {value}"))
                notes.append(f"step '{label}' in '{j['id']}' uses {s['uses']}; kept as a comment")
        if not any(not ln.startswith("#") for ln in body):
            body.append("pass")
        chunks.append((fname, "@job\ndef " + fname + "():\n" + "\n".join("    " + ln if ln else ln for ln in
                                                                           "\n".join(body).split("\n")) + "\n"))

    needed = {n for j in wf["jobs"] for n in j["needs"]}
    last = [names[j["id"]] for j in wf["jobs"] if j["id"] not in needed]
    chunks.append(("main", 'if __name__ == "__main__":\n' + "".join(f"    {n}()\n" for n in last)))
    return chunks, notes


def workflow_to_marked_text(text, token="#"):
    """(portable text with node markers, notes) - ready for the app's portable loader. Raises YamlError."""
    chunks, notes = workflow_to_chunks(text)
    return portable.wrap_with_markers(chunks, token), notes
