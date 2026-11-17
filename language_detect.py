"""Guess which language a piece of source code is written in (pure, no Tk).

Used when code is pasted or opened for Code -> Blocks, so Blockliner can offer to switch to the right language instead
of matching Rust against Python's blocks. It looks at telltale syntax (keywords, imports, punctuation habits), scores
every language, and only answers when one clearly wins; otherwise it says "don't know" and the caller leaves the
current language alone. A file extension, when there is one, counts as a strong hint but never beats the code itself
by a lot (a .h file may be C++, a .txt means nothing)."""
import re
from collections import namedtuple

Guess = namedtuple("Guess", "language confidence ranking")

MIN_SCORE = 4.0            # the winner needs at least this much evidence ...
MIN_MARGIN = 1.6           # ... and this ratio over the runner-up

# (regex, weight): matched per line unless the pattern starts with (?s) - then against the whole text.
SIGNS = {
    "python": [
        (r"^\s*def\s+\w+\s*\(.*\)\s*(->\s*[\w\[\], .]+)?:\s*$", 4), (r"^\s*class\s+\w+(\(.*\))?\s*:\s*$", 3),
        (r"^\s*(from\s+[\w.]+\s+)?import\s+[\w., *]+\s*$", 2), (r"^\s*elif\b.*:\s*$", 4), (r"^\s*(if|while|for)\b.*[^;{]:\s*$", 1.5),
        (r"\bself\.\w+", 2), (r"^\s*print\(", 1), (r"\b(None|True|False)\b", 1), (r"^\s*#(?!include|define|\!)", 0.5),
        (r"^\s*(try|except|finally|else)\b.*:\s*$", 1.5), (r"\bf\"[^\"]*\{", 2), (r"^\s*with\s+.+\s+as\s+\w+:\s*$", 3),
        (r"\blen\(|\brange\(", 1), (r"\bis not\b|\bnot in\b", 2), (r"^\s*if __name__ == .__main__.:", 6),
    ],
    "javascript": [
        (r"\bfunction\b\s*\w*\s*\(", 3), (r"\b(const|let|var)\s+\w+\s*=", 3), (r"=>", 2), (r"\bconsole\.(log|error|warn)\(", 4),
        (r"\brequire\(['\"]", 4), (r"={3}|!={2}", 2.5), (r"^\s*import\s+.*\bfrom\s+['\"]", 4), (r"\bdocument\.|\bwindow\.", 3),
        (r"\bmodule\.exports\b|\bexport\s+(default|const|function)\b", 4), (r"\bnew Promise\b|\basync\s+function\b|\bawait\b", 2), (r"\.then\(", 1.5),
    ],
    "java": [
        (r"\bpublic\s+(static\s+)?(final\s+)?class\s+\w+", 4), (r"System\.out\.print(ln)?\(", 5), (r"public\s+static\s+void\s+main\s*\(\s*String", 6),
        (r"^\s*import\s+java\.", 5), (r"^\s*package\s+[\w.]+;", 3), (r"\b(private|protected|public)\s+\w+(<[^>]*>)?\s+\w+\s*[(;=]", 1.5),
        (r"\bnew\s+\w+(<[^>]*>)?\s*\(", 1), (r"@Override\b", 3), (r"\bString\[\]|\bArrayList<|\bHashMap<", 2), (r"\bextends\s+\w+|\bimplements\s+\w+", 2),
    ],
    "csharp": [
        (r"^\s*using\s+System[\w.]*;", 6), (r"^\s*namespace\s+[\w.]+", 4), (r"Console\.(WriteLine|Write|ReadLine)\(", 6),
        (r"\bstatic\s+(void|int|async\s+Task)\s+Main\s*\(", 6), (r"\{\s*get;\s*(private\s+|protected\s+)?set;\s*\}", 6), (r"\bstring\s+\w+\s*[=;)]", 1.5),
        (r"\b(public|private|internal|protected)\s+(static\s+)?(readonly\s+)?\w+(<[^>]*>)?\s+\w+", 1), (r"\bvar\s+\w+\s*=\s*new\b", 2),
        (r"\b(List|Dictionary)<[^>]*>", 2), (r"\[[A-Z]\w+\]\s*$", 1.5), (r"\bforeach\s*\(", 2.5),
    ],
    "cpp": [
        (r"^\s*#\s*include\s*<(iostream|vector|string|map|set|algorithm|memory|cmath|fstream|sstream|unordered_map)>", 6),
        (r"\bstd::\w+", 4), (r"\bcout\s*<<|\bcin\s*>>", 5), (r"^\s*using\s+namespace\s+std\s*;", 6), (r"\btemplate\s*<", 4),
        (r"\bclass\s+\w+\s*(:\s*(public|private|protected)\s+\w+\s*)?\{", 3), (r"\b(nullptr|constexpr|auto)\b", 2), (r"::\w+\s*\(", 1.5),
        (r"\bnew\s+\w+(\s*[\[(])", 1), (r"\bendl\b", 3), (r"\b(public|private|protected)\s*:", 3), (r"\bvirtual\b|\boverride\b", 2),
    ],
    "c": [
        (r"^\s*#\s*include\s*<(stdio|stdlib|string|math|stdint|stdbool|ctype|time|unistd)\.h>", 6), (r"\bprintf\s*\(", 3), (r"\bscanf\s*\(", 3),
        (r"\bint\s+main\s*\(\s*(void|int\s+argc.*)?\)", 3), (r"\b(malloc|calloc|free|sizeof)\s*\(", 3), (r"\bstruct\s+\w+\s*\{", 2),
        (r"^\s*#\s*define\s+\w+", 2), (r"\bchar\s*\*\s*\w+", 2), (r"\bNULL\b", 1.5), (r"\btypedef\b", 2),
    ],
    "go": [
        (r"^\s*package\s+\w+\s*$", 6), (r"^\s*func\s+(\(\w+\s+\*?\w+\)\s*)?\w+\s*\(", 5), (r"\bfmt\.(Println|Printf|Sprintf|Print)\(", 6),
        (r":=", 3), (r"^\s*import\s*\(\s*$", 5), (r"^\s*import\s+\"[\w/.]+\"", 4), (r"\bgo\s+func\b|\bchan\s+\w+|\bdefer\b", 3),
        (r"\bvar\s+\w+\s+(int|string|bool|float64)\b", 3), (r"\bif\s+err\s*!=\s*nil\b", 5), (r"\bmake\(\s*(\[\]|map|chan)", 3),
    ],
    "rust": [
        (r"\bfn\s+\w+\s*(<[^>]*>)?\s*\(", 5), (r"\blet\s+mut\s+\w+", 5), (r"\bprintln!\s*\(|\bformat!\s*\(|\bvec!\s*\[", 6),
        (r"^\s*use\s+(std|crate|super|self)::", 6), (r"\bimpl(<[^>]*>)?\s+\w+", 4), (r"->\s*(Result|Option|Self|&|\w+)\s*[{<]", 2),
        (r"\bpub\s+(fn|struct|enum|mod)\b", 4), (r"\b(match)\s+\w+.*\{", 2), (r"\b&mut\s+\w+|\bOption<|\bResult<|\bSome\(|\bNone\b", 2), (r"::new\(", 1),
        (r"\blet\s+\w+\s*(:\s*[\w<>&\[\]]+\s*)?=", 1.5), (r"\bstruct\s+\w+\s*\{|\benum\s+\w+\s*\{", 2),
    ],
    "html": [
        (r"(?si)^\s*<!doctype\s+html", 10), (r"(?si)<html[\s>]", 6), (r"(?si)</(div|p|body|head|html|span|ul|li|table|h[1-6]|a|script|style)>", 3),
        (r"(?i)<(div|p|span|ul|ol|li|table|tr|td|h[1-6]|img|a|form|input|button|section|nav|header|footer)\b[^>]*>", 2),
        (r"(?i)<(meta|link|title|script|style)\b", 3), (r"<!--.*-->", 0.5),
    ],
}

# a signature that says "this is NOT that language" (e.g. a '{' after every line is not Python)
VETOS = {
    "python": [(r"^\s*(public|private|protected)\s+", 4), (r"^\s*#\s*include\b", 6), (r";\s*$", 1.5), (r"^\s*(const|let|var)\s+\w+\s*=", 3), (r"^\s*fn\s+", 4), (r"^\s*package\s+", 4)],
    "c": [(r"\bstd::|\bcout\b|\bclass\b\s+\w+", 6)],
}

# when two languages share syntax, the more specific one's evidence is also (a bit) evidence against the general one
BEATS = {"cpp": ("c", 0.5), "javascript": (), "csharp": ("java", 0.4)}


def _count(pattern, text, lines):
    if pattern.startswith("(?s") or "(?si)" in pattern[:6] or pattern.startswith("(?i)"):
        return len(re.findall(pattern, text, re.MULTILINE))
    rx = re.compile(pattern)
    return sum(1 for ln in lines if rx.search(ln))


def scores(text):
    """{language: score} for the text (higher = more evidence)."""
    text = text or ""
    lines = text.splitlines()[:600]
    flat = "\n".join(lines)
    out = {}
    for lang, signs in SIGNS.items():
        total = 0.0
        for pattern, weight in signs:
            n = _count(pattern, flat, lines)
            if n:
                total += weight * min(n, 3) ** 0.7        # a repeated habit counts more, with diminishing returns
        for pattern, weight in VETOS.get(lang, ()):
            if _count(pattern, flat, lines):
                total -= weight
        out[lang] = max(0.0, total)
    for lang, (general, share) in ((k, v) for k, v in BEATS.items() if v):
        if out.get(lang, 0) >= MIN_SCORE:
            out[general] = max(0.0, out[general] - out[lang] * share)
    return out


def detect(text, extension=None, ext_map=None):
    """Guess(language, confidence 0..1, ranking [(lang, score)]); language is None when it can't tell.
    `extension` (".py") with `ext_map` ({".py": "python"}) adds a hint."""
    text = text or ""
    if len(text.strip()) < 8:
        return Guess(None, 0.0, [])
    sc = scores(text)
    hinted = (ext_map or {}).get((extension or "").lower())
    if hinted in sc:
        sc[hinted] += 3.0
    ranking = sorted(sc.items(), key=lambda kv: -kv[1])
    (best, top), (_second, runner) = ranking[0], ranking[1]
    if top < MIN_SCORE or (runner > 0 and top < runner * MIN_MARGIN):
        return Guess(None, 0.0, ranking)
    conf = min(1.0, top / (top + runner + 4.0))
    return Guess(best, round(conf, 2), ranking)
