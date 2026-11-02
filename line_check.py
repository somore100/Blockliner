"""Free-writing code check (pure, no Tk): how well does Blockliner understand a line?

    known       the line fits a block pattern, so it becomes a real block
    typo        a name in it is not known but is close to one that is
                ("pritn(" -> "print"), with a score and a suggested fix
    unverified  valid-looking code Blockliner has no block or name for
                (a library call, say); it stays a Raw Code block, quietly
    none        nothing to judge (blank line, comment, lone bracket)

Nothing here changes code: a Check only describes a line and offers fixes.
`confidence` is how sure Blockliner is of the verdict: 1.0 for known, the
name similarity (0..1) for a typo, 0.0 for unverified.
"""
import builtins
import keyword
import re

KNOWN, TYPO, UNVERIFIED, NONE = "known", "typo", "unverified", "none"
IMPORT = "import"            # uses a library that this file does not import yet

DEFAULT_THRESHOLD = 0.7      # lowest similarity that still counts as "probably a typo"
TIE_WINDOW = 0.04            # suggestions this close to the best are offered too
MIN_WORD = 3                 # shorter names are never called typos
MAX_SUGGESTIONS = 3

_IDENT = r"[A-Za-z_]\w*"
_CALL_RE = re.compile(rf"(?<![\w.])({_IDENT})\s*\(")
_HEAD_WORD_RE = re.compile(rf"^({_IDENT})(?=\s+[\w\"'(\[\-])")
_HEAD_COLON_RE = re.compile(rf"^({_IDENT})\s*:\s*$")
_JOINERS = {"is", "in", "and", "or", "not", "if", "else", "for", "as", "from", "import"}
_DEFS = (re.compile(rf"^\s*(?:async\s+)?def\s+({_IDENT})\s*\((.*?)\)"),
         re.compile(rf"^\s*class\s+({_IDENT})"),
         re.compile(rf"^\s*({_IDENT}(?:\s*,\s*{_IDENT})*)\s*(?:[-+*/%|&^]|//|\*\*)?=(?!=)"),
         re.compile(rf"^\s*for\s+({_IDENT}(?:\s*,\s*{_IDENT})*)\s+in\b"),
         re.compile(rf"\bas\s+({_IDENT})"))
_QUALIFIED_RE = re.compile(rf"(?<![\w.])({_IDENT})\.({_IDENT})")
_IMPORT_RE = re.compile(r"^\s*(?:from\s+[\w.]+\s+)?import\s+(.+)$")

OTHER_LANGUAGE_WORDS = {
    "javascript": "var let const function return if else for while switch case break continue new this class "
                  "console log true false null undefined typeof await async import export",
    "cpp": "int float double char bool void auto const static return if else for while switch case break continue "
           "class struct include using namespace std cout cin endl true false nullptr",
    "c": "int float double char void const static return if else for while switch case break continue struct "
         "include printf scanf main sizeof NULL",
    "java": "public private protected static final class void int double boolean String return if else for while "
            "new this import package System out println true false null",
    "csharp": "public private static class void int double bool string var return if else for while foreach new "
              "using namespace Console WriteLine true false null",
    "go": "package import func var const return if else for range switch case break continue struct interface "
          "fmt Println Printf true false nil",
    "rust": "fn let mut const return if else for while loop match impl struct enum use mod pub println true false",
    "html": "div span html head body title script style class href src input button form table",
}


class Check:
    """The verdict for one line."""

    def __init__(self, state, confidence=0.0, word="", start=0, end=0, message="", suggestions=(), action=None):
        self.state = state
        self.action = action                   # ("import", library name) for an IMPORT check
        self.confidence = confidence
        self.word = word                       # the doubtful name (typo only)
        self.start, self.end = start, end      # its position in the line
        self.message = message
        self.suggestions = list(suggestions)   # [(replacement word, similarity)], best first

    def __repr__(self):
        return f"Check({self.state}, {self.confidence:.2f}, {self.word!r}, {self.suggestions})"


# ---- vocabulary ------------------------------------------------------------
def language_words(lang):
    """Words every program in `lang` may use."""
    if lang == "python":
        return set(keyword.kwlist) | {n for n in dir(builtins) if not n.startswith("_")}
    return set(OTHER_LANGUAGE_WORDS.get(lang, "").split())


def words_from_pattern(pattern_text):
    """The literal words a block's reverse-pattern regex spells out (so 'print',
    'while', 'append'), without parameter names or regex syntax."""
    text = re.sub(r"\(\?P[<=]\w+[>)]", " ", pattern_text)
    text = re.sub(r"\[[^\]]*\]", " ", text)
    return set(re.findall(rf"(?<![\\\w])[A-Za-z_]\w{{{MIN_WORD - 1},}}", text))


def defined_names(lines):
    """Names the text itself defines (functions, classes, variables, parameters,
    loop variables, imports): calling them is fine."""
    names = set()
    for line in lines:
        code = _blank_strings(line)
        for rx in _DEFS:
            m = rx.search(code)
            if not m:
                continue
            names.update(n.strip() for n in re.split(r"\s*,\s*", m.group(1)) if n.strip())
            if rx is _DEFS[0]:
                names.update(re.findall(_IDENT, re.sub(r"=[^,]*", "", m.group(2))))
        m = _IMPORT_RE.match(code)
        if m:
            for part in m.group(1).split(","):
                bits = part.replace("(", " ").replace(")", " ").split()
                if bits:
                    names.add(bits[-1].split(".")[0])
    return names


# ---- text handling ---------------------------------------------------------
def _blank_strings(line):
    """`line` with string contents and trailing comments replaced by spaces
    (same length, so positions still line up)."""
    out, quote, i = [], None, 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\" and i + 1 < len(line):
                out.append("  ")
                i += 2
                continue
            if ch == quote:
                quote = None
                out.append(ch)
            else:
                out.append(" ")
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#" or line.startswith("//", i):
            out.append(" " * (len(line) - i))
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def similarity(a, b):
    """1.0 for equal words, falling with the number of edits (a swap of two
    neighbouring letters counts as one edit); case is ignored."""
    a, b = a.lower(), b.lower()
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return 1.0 - d[la][lb] / max(la, lb)


def suggest(word, vocab, threshold=DEFAULT_THRESHOLD):
    """[(name, similarity)] of known names close to `word`, best first; the
    runners-up are only kept when almost as close as the best."""
    if len(word) < MIN_WORD:
        return []
    scored = sorted(((similarity(word, v), v) for v in vocab if len(v) >= MIN_WORD and v != word),
                    key=lambda t: (-t[0], t[1]))
    scored = [(v, round(s, 2)) for s, v in scored if s >= threshold]
    if not scored:
        return []
    best = scored[0][1]
    return [t for t in scored if best - t[1] <= TIE_WINDOW][:MAX_SUGGESTIONS]


def _candidates(code):
    """[(word, start, end)] of the names worth checking: statement keywords at
    the start of the line and called names (not attributes like obj.method)."""
    found = {}
    stripped = code.strip()
    offset = len(code) - len(code.lstrip())
    for rx in (_HEAD_WORD_RE, _HEAD_COLON_RE):
        m = rx.match(stripped)
        if m and m.group(1) not in _JOINERS:
            found[offset + m.start(1)] = (m.group(1), offset + m.start(1), offset + m.end(1))
    for m in _CALL_RE.finditer(code):
        found[m.start(1)] = (m.group(1), m.start(1), m.end(1))
    return [found[k] for k in sorted(found)]


# ---- the verdict -----------------------------------------------------------
def _library_check(code, libs, threshold, ignored):
    """A typo in `namespace.method`, or a library that is used without being
    imported. `libs` = {"index": libraries.qualified_index(..), "imported": {names}}."""
    index, imported = libs["index"], libs["imported"]
    best, missing = None, None
    for m in _QUALIFIED_RE.finditer(code):
        ns, method = m.group(1), m.group(2)
        if ns in index:
            entry = index[ns]
            if entry["methods"] and method not in entry["methods"] and method not in ignored:
                options = suggest(method, entry["methods"], threshold)
                if options and (best is None or options[0][1] > best.confidence):
                    best = Check(TYPO, options[0][1], method, m.start(2), m.end(2),
                                 f'"{ns}" has no "{method}".', options)
            if entry["lib"] not in imported and missing is None:
                missing = Check(IMPORT, 0.9, ns, m.start(1), m.end(1), f'"{ns}" is used but not imported in this file.',
                                action=("import", entry["lib"]))
        elif ns not in ignored:
            options = suggest(ns, index.keys(), threshold)
            tail = code[m.end():].lstrip()[:1]
            if options and tail in ("(", "."):
                if best is None or options[0][1] > best.confidence:
                    best = Check(TYPO, options[0][1], ns, m.start(1), m.end(1), f'"{ns}" is not a known name.', options)
    return best or missing


def analyse_line(line, matchers, vocab, ignored=(), threshold=DEFAULT_THRESHOLD, libs=None):
    """Judge one line. `matchers` are compiled block patterns (anything with
    .match), `vocab` the set of known names, `ignored` words the user chose to
    keep as they are, `libs` the library info for namespace checks (optional)."""
    code = _blank_strings(line)
    text = code.strip()
    if not text or re.fullmatch(r"[\s{}()\[\],;:]*", text):
        return Check(NONE)
    best = None
    for word, start, end in _candidates(code):
        if word in vocab or word in ignored:
            continue
        options = suggest(word, vocab, threshold)
        if options and (best is None or options[0][1] > best.confidence):
            best = Check(TYPO, options[0][1], word, start, end,
                         f'"{word}" is not a known name.', options)
    if best is not None:
        return best
    if libs:
        found = _library_check(code, libs, threshold, ignored)
        if found is not None:
            return found
    if any(m.match(text) for m in matchers) or any(m.match(line.strip()) for m in matchers):
        return Check(KNOWN, 1.0)
    semi = _stray_semicolon(code, text, matchers)
    if semi is not None:
        return Check(TYPO, 0.95, ";", semi, semi + 1,
                     'The trailing ";" is not needed here, and it stops this line from becoming a block.',
                     [("", 0.95)])
    heads = [w for w, _s, _e in _candidates(code) if w in vocab and w not in _JOINERS]
    if heads and not heads[0] in keyword.kwlist:
        return Check(UNVERIFIED, 0.0, message=f'It starts with "{heads[0]}", but the rest does not fit a block for it, '
                                              "so it stays raw code.")
    return Check(UNVERIFIED, 0.0, message="Blockliner has no block for this line, so it stays raw code.")


def _stray_semicolon(code, text, matchers):
    """Position of a trailing ';' when the line fits a block without it (Python
    and friends where the block does not write one), else None."""
    bare = text.rstrip()
    if not bare.endswith(";"):
        return None
    without = bare[:-1].rstrip()
    if any(m.match(without) for m in matchers):
        return len(code.rstrip()) - 1
    return None


def analyse_text(lines, matchers, vocab, ignored=(), threshold=DEFAULT_THRESHOLD, libs=None):
    """One Check per line; names the text defines itself count as known."""
    allowed = set(vocab) | defined_names(lines)
    return [analyse_line(ln, matchers, allowed, ignored, threshold, libs) for ln in lines]


def apply_fix(line, check, replacement):
    """`line` with the doubtful word replaced (a typo Check only)."""
    if check.state != TYPO or not (0 <= check.start < check.end <= len(line)):
        return line
    return line[:check.start] + replacement + line[check.end:]


def describe(check):
    """Text for the bulb: what is wrong and what to do."""
    if check.state == TYPO and check.suggestions and check.suggestions[0][0] == "":
        return f'{check.message}\nRemove it? ({round(check.suggestions[0][1] * 100)}% sure)'
    if check.state == TYPO and check.suggestions:
        name, score = check.suggestions[0]
        text = f'{check.message}\nDid you mean "{name}"? ({round(score * 100)}% sure)'
        if len(check.suggestions) > 1:
            text += "\nOr: " + ", ".join(f'"{n}"' for n, _s in check.suggestions[1:])
        return text
    if check.state == IMPORT:
        return f"{check.message}\nAdd the import line for it?"
    if check.state == UNVERIFIED:
        return check.message
    return ""
