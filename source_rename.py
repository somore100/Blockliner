"""Renaming a function/class inside source text, token by token (so strings and comments are never touched).

Python uses the real tokenizer; the C-like languages (JavaScript, Go, Rust, Java, C#, C, C++) use a small scanner that
knows comments and string literals. Both skip `obj.name` / `Type::name` member uses, which are some other thing than
the definition. Pure: no UI, no files."""
import io
import keyword
import re
import tokenize

CLIKE = ("javascript", "typescript", "go", "rust", "java", "csharp", "c", "cpp")
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")
_KEYWORDS = set("""abstract as async await break case catch char class const continue default defer do double else
enum export extends false fn final finally float for func function go if implements import in instanceof int interface
let long match mod mut namespace new nil null override package private protected public pub return self short static
struct super switch this throw throws true try type typeof union unsafe use using var void volatile where while yield
""".split())


def valid_name(name, lang):
    if lang == "python":
        return name.isidentifier() and not keyword.iskeyword(name)
    return bool(re.fullmatch(r"[A-Za-z_$][\w$]*", name)) and name not in _KEYWORDS


def _python_names(text):
    """[(line, col, name, prev, nxt, depth, prev2)] for every NAME token (1-based line, 0-based col), or None when the
    text does not tokenize."""
    skip = (tokenize.NL, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE)
    try:
        toks = [t for t in tokenize.generate_tokens(io.StringIO(text).readline) if t.type not in skip]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None
    out, depth = [], 0
    for i, t in enumerate(toks):
        if t.type == tokenize.OP and t.string in "([{":
            depth += 1
        elif t.type == tokenize.OP and t.string in ")]}":
            depth -= 1
        if t.type == tokenize.NAME and not keyword.iskeyword(t.string):
            prev = toks[i - 1].string if i else ""
            prev2 = toks[i - 2].string if i > 1 else ""
            nxt = toks[i + 1].string if i + 1 < len(toks) else ""
            out.append((t.start[0], t.start[1], t.string, prev, nxt, depth, prev2))
    return out


def _clike_names(text, lang):
    """The same tuples for C-like source: identifiers outside comments and strings. `prev` is the previous
    significant character(s) ("." for a member use, "::" and "->" too), `nxt` the next significant one."""
    out = []
    n, i, line, line_start = len(text), 0, 1, 0
    toks = []                                          # (kind, value, line, col)
    while i < n:
        c = text[i]
        if c == "\n":
            line, i = line + 1, i + 1
            line_start = i
        elif c in " \t\r":
            i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            line += text.count("\n", i, j)
            if "\n" in text[i:j]:
                line_start = text.rfind("\n", i, j) + 1
            i = j
        elif c in "\"`" or (c == "'" and not _is_lifetime(text, i, lang)):
            j = i + 1
            while j < n and text[j] != c:
                if text[j] == "\\" and c != "`":
                    j += 1
                if j < n and text[j] == "\n" and c != "`":
                    break
                j += 1
            seg = text[i:j + 1]
            line += seg.count("\n")
            if "\n" in seg:
                line_start = i + seg.rfind("\n") + 1
            i = j + 1
            toks.append(("str", "", line, 0))
        else:
            m = _IDENT.match(text, i)
            if m:
                toks.append(("id", m.group(), line, i - line_start))
                i = m.end()
            elif text.startswith("::", i) or text.startswith("->", i):
                toks.append(("op", text[i:i + 2], line, i - line_start))
                i += 2
            else:
                toks.append(("op", c, line, i - line_start))
                i += 1
    depth = 0
    for k, (kind, val, ln, col) in enumerate(toks):
        if kind == "op" and val in "([{":
            depth += 1
        elif kind == "op" and val in ")]}":
            depth -= 1
        if kind == "id" and val not in _KEYWORDS:
            prev = toks[k - 1][1] if k else ""
            nxt = toks[k + 1][1] if k + 1 < len(toks) else ""
            out.append((ln, col, val, prev, nxt, depth, toks[k - 2][1] if k > 1 else ""))
    return out


def _is_lifetime(text, i, lang):
    """Rust: 'a is a lifetime, 'a' a character."""
    if lang != "rust":
        return False
    m = re.match(r"'([A-Za-z_]\w*)", text[i:i + 80])
    return bool(m) and text[i + m.end():i + m.end() + 1] != "'"


def names(text, lang):
    return _python_names(text) if lang == "python" else _clike_names(text, lang)


def _is_member(prev):
    return prev in (".", "::", "->")


def _is_key_or_kwarg(lang, prev, nxt, depth):
    if lang == "python":
        return depth > 0 and nxt == "="                  # f(old=1)
    return prev in ("{", ",") and nxt == ":" and lang in ("javascript", "typescript", "go")    # {old: 1}


def rename_in_text(text, old, new, lang="python"):
    """`text` with the identifier `old` replaced by `new`. Returns (text, count), or (None, 0) when the text does not
    tokenize."""
    found = names(text, lang)
    if found is None:
        return None, 0
    lines = text.split("\n")
    hits = [(ln, col) for ln, col, name, prev, nxt, depth, _p2 in found
            if name == old and not _is_member(prev) and not _is_key_or_kwarg(lang, prev, nxt, depth)]
    for ln, col in sorted(hits, reverse=True):
        row = lines[ln - 1]
        lines[ln - 1] = row[:col] + new + row[col + len(old):]
    return "\n".join(lines), len(hits)


def declares(text, name, lang):
    """True when `name` is declared in the first line of `text` that has code (def/class/func/fn/function/type...)."""
    first = next((l for l in text.split("\n") if l.strip() and not l.strip().startswith(("//", "#", "/*", "*", "@"))), "")
    if lang == "python":
        return bool(re.match(r"\s*(async\s+def|def|class)\s+" + re.escape(name) + r"\b", first))
    found = names(first, lang) or []
    # a declaration has a type/keyword (or a * & > ] of a return type) right before the name; a use has an operator
    return any(n == name and (re.fullmatch(r"[\w$]+", p or "") or p in ("*", "&", ">", "]"))
               and p not in ("return", "new", "await", "throw", "else", "case")
               for _l, _c, n, p, *_r in found)


def apply_renames(chunks, renames, original=None, lang="python"):
    """renames {id: (old name, new name)}: rewrite the definition and every use of the old name in all chunks. A rename
    is skipped (and reported) when the new name is not a plain identifier, is already used in the file as it was before
    (`original` chunks; Blockliner's own edit may already use the new name), or the text does not tokenize.
    Returns (chunks, [skipped descriptions], [(old, new) applied])."""
    skipped, applied = [], []
    for _cid, (old, new) in renames.items():
        if not valid_name(new, lang):
            skipped.append(f"{new!r} is not a valid name")
            continue
        used = names("".join(t for _c, t in (original or chunks)), lang)
        if used is None:
            skipped.append(f"{old}: the file does not tokenize")
            continue
        if any(n == new for _l, _c, n, *_r in used):
            skipped.append(f"{new!r} is already used in the file")
            continue
        out = []
        for c, t in chunks:
            t2, _n = rename_in_text(t, old, new, lang)
            out.append((c, t if t2 is None else t2))
        chunks = out
        applied.append((old, new))
    return chunks, skipped, applied


# ---- Python: files that import the renamed module ---------------------------------------------------
def module_name(rel):
    """"pkg/utils.py" -> "pkg.utils"; "pkg/__init__.py" -> "pkg"."""
    parts = rel.replace("\\", "/").rsplit(".", 1)[0].split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _from_module(importer_rel, level, module):
    parts = importer_rel.replace("\\", "/").split("/")[:-1]
    if level:
        if level - 1 > len(parts):
            return None
        parts = parts[:len(parts) - (level - 1)]
    else:
        parts = []
    return ".".join(parts + (module.split(".") if module else []))


def rename_imports(text, importer_rel, module, old, new):
    """For a Python file `text` (at `importer_rel`) that imports `module`, whose function/class `old` was renamed `new`:
    the import name, the bare uses after `from module import old`, and `alias.old` uses after `import module as alias`.
    Returns (new text, count); (text, 0) when it does not import the module; (None, reason) when it cannot be done."""
    import ast
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None, "it does not parse"
    at_import, direct, aliases = set(), False, set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            full = _from_module(importer_rel, node.level, node.module)
            if full is None:
                continue
            for a in node.names:
                if full == module and a.name == old:
                    at_import.add((a.lineno, a.col_offset))
                    direct = direct or a.asname is None
                elif full == module and a.name == "*":
                    direct = True
                elif (full + "." + a.name if full else a.name) == module:
                    aliases.add(a.asname or a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name == module and (a.asname or "." not in a.name):
                    aliases.add(a.asname or a.name)
    if not (at_import or direct or aliases):
        return text, 0
    found = _python_names(text)
    if found is None:
        return None, "it does not tokenize"
    if any(n == new for _l, _c, n, *_r in found):
        return None, f"{new!r} is already used there"
    hits = set(at_import)
    for ln, col, name, prev, nxt, depth, prev2 in found:
        if name != old:
            continue
        if direct and prev != "." and not (depth > 0 and nxt == "="):
            hits.add((ln, col))
        elif prev == "." and prev2 in aliases:
            hits.add((ln, col))
    lines = text.split("\n")
    count = 0
    for ln, col in sorted(hits, reverse=True):
        row = lines[ln - 1]
        if row[col:col + len(old)] == old:
            lines[ln - 1] = row[:col] + new + row[col + len(old):]
            count += 1
    return "\n".join(lines), count
