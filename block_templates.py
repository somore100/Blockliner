"""Pure helpers for custom-block templates and reverse (code -> block) patterns."""
import itertools
import re


def make_raw_code_block_source(lang):
    """
    Source code for a starter Raw Code (escape hatch) block, written into
    every newly created language's blocks/ folder. This guarantees every
    language always has at least one block - a way to write code the
    block set doesn't cover yet - matching the per-block-file contract
    used by every other block (block_id, generate_code, etc.).
    """
    return (
        'block_id = "raw_code"\n'
        'display_name = "Custom Code"\n'
        'category = "Advanced"\n'
        '\n'
        'params = [\n'
        '    {"name": "code_line", "type": "code", "default": ""}\n'
        ']\n'
        '\n'
        'def default_params():\n'
        '    return {"code_line": ""}\n'
        '\n'
        f'def generate_code(params, children, lang="{lang}"):\n'
        f'    """Escape hatch: outputs the given line of {lang} code as-is."""\n'
        '    return params.get("code_line", "") + "\\n"\n'
        '\n'
        'block_ui_description = {\n'
        '    "label": "Custom Code",\n'
        '    "params": params,\n'
        '    "category": "Advanced",\n'
        f'    "description": "Write custom {lang} code directly (advanced users only)."\n'
        '}\n'
    )


def make_custom_block_generate_code(template, params_meta=None, quote_char='"'):
    """
    Build a generate_code(params, children, lang) function for a
    Scratch-style custom block.

    `template` uses {{name}} placeholders; label text around them is
    literal. Inputs declared as type 'text'/'string'/'input' are
    automatically wrapped in `quote_char` (with existing quote chars and
    backslashes escaped) so the user never has to type quote marks by
    hand - unlike Scratch, this is real code, so an unquoted string is a
    syntax error, and a 'variable' type input must stay unquoted to work
    as an identifier. Number and boolean inputs are also substituted raw.
    """
    params_meta = params_meta or []
    type_by_name = {p["name"]: p.get("type", "text") for p in params_meta}

    def gen_code(params, children=None, lang=None):
        code = template
        for name, raw_val in (params or {}).items():
            if name.startswith("_"):
                continue  # internal metadata (e.g. _nickname) - never part of generated code
            ptype = type_by_name.get(name, "text")
            val_str = "" if raw_val is None else str(raw_val)
            if ptype in ("text", "string", "input"):
                escaped = val_str.replace("\\", "\\\\").replace(quote_char, "\\" + quote_char)
                rendered = f"{quote_char}{escaped}{quote_char}"
            else:
                rendered = val_str
            code = code.replace("{{" + name + "}}", rendered)
        return code + "\n"

    return gen_code


def template_to_pieces(template, params_list):
    """
    Reverse of the builder's label/input -> {{name}} template flattening.
    Used to pre-populate the visual builder when editing an existing
    custom block, so editing always starts from the same piece-based
    representation as creating (never falls back to raw text editing).
    """
    param_by_name = {p["name"]: p for p in (params_list or [])}
    pieces = []
    pattern = re.compile(r"\{\{(\w+)\}\}")
    last_end = 0

    for m in pattern.finditer(template or ""):
        if m.start() > last_end:
            label_text = template[last_end:m.start()]
            if label_text:
                pieces.append({"kind": "label", "text": label_text})

        name = m.group(1)
        meta = param_by_name.get(name, {})
        pieces.append({
            "kind": "input",
            "name": name,
            "type": meta.get("type", "text"),
            "default": meta.get("default", "")
        })
        last_end = m.end()

    if last_end < len(template or ""):
        trailing = template[last_end:]
        if trailing:
            pieces.append({"kind": "label", "text": trailing})

    return pieces


_SENTINEL_RE = re.compile(r"@@(\w+)@@")

# Param types get a tighter capture pattern where the shape of a valid
# value is well known (numbers, identifiers) - this makes matches more
# precise and less likely to accidentally swallow a neighboring param's
# text. Free-form types fall back to a lazy .*? capture.
_PARAM_CAPTURE_PATTERNS = {
    "number": r"-?\d+(?:\.\d+)?",
    "variable": r"[A-Za-z_]\w*",
    # Conditions are free-form expressions ("x > 3", "a and not b"),
    # not just bare identifiers.
    "boolean": r".+?",
}


def get_choice_combos(params_meta):
    """
    All combinations of a block's 'choice'-type param values (e.g. the
    built-in print block's mode: text/variable). A block's rendered
    code shape can differ per choice, so each combination needs its own
    reverse-match pattern. Blocks with no choice params get one combo:
    the empty one (every other param becomes a sentinel placeholder).
    """
    choice_params = [p for p in (params_meta or []) if p.get("type") == "choice"]
    if not choice_params:
        return [{}]

    choice_lists = [p.get("choices") or [p.get("default", "")] for p in choice_params]
    combos = []
    for values in itertools.product(*choice_lists):
        combos.append({p["name"]: v for p, v in zip(choice_params, values)})
    return combos


def _net_braces(line):
    """Net { minus } on one line, ignoring braces inside string
    literals and after a // comment. Deliberately simple: good enough
    to find where a brace-style body ends without a real tokenizer."""
    net, quote, i = 0, None, 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in ("\"", "'", "`"):
            quote = ch
        elif ch == "/" and line[i + 1:i + 2] == "/":
            break
        elif ch == "{":
            net += 1
        elif ch == "}":
            net -= 1
        i += 1
    return net


def _pattern_from_rendered(rendered, param_type_by_name, combo):
    """Build a single regex pattern dict from an already-rendered
    (sentinel-substituted) code string. Shared by build_reverse_pattern
    for both the literal rendering and any quote-swapped variant."""
    rendered = rendered.rstrip("\n")
    if not rendered.strip():
        return None

    parts = _SENTINEL_RE.split(rendered)
    # re.split with a capturing group interleaves: [literal, sentinel_name, literal, sentinel_name, ...]
    pattern_parts = []
    seen_groups = []
    literal_score = 0

    for idx, part in enumerate(parts):
        is_sentinel = idx % 2 == 1
        if is_sentinel:
            name = part
            ptype = param_type_by_name.get(name, "text")
            if name in seen_groups:
                # Same param appears more than once in the output (e.g. a
                # variable name used twice) - backreference instead of a
                # second capture group, which Python's re doesn't allow.
                pattern_parts.append(f"(?P={name})")
            else:
                seen_groups.append(name)
                inner = _PARAM_CAPTURE_PATTERNS.get(ptype, r".*?")
                pattern_parts.append(f"(?P<{name}>{inner})")
        else:
            pattern_parts.append(re.escape(part))
            literal_score += len(part)

    pattern_str = "^" + "".join(pattern_parts) + "$"
    try:
        # No DOTALL: matching is bucketed by exact line count at match
        # time (see import_code_to_blocks), so a pattern only ever gets
        # tested against a candidate with the same number of lines its
        # own template has. Without that guarantee, a non-greedy .*?
        # capture can be forced by the trailing $ anchor to stretch
        # across extra joined lines just to find a matching literal
        # suffix further down - silently swallowing unrelated lines
        # into one block's param value.
        compiled = re.compile(pattern_str)
    except re.error:
        return None

    return {
        "regex": compiled,
        "groups": seen_groups,
        "combo": combo,
        "literal_score": literal_score,
        "line_count": rendered.count("\n") + 1,
    }


def build_reverse_pattern(gen_func, params_meta, lang, combo):
    """
    Derive regex pattern(s) that match code this block's generate_code()
    would itself produce.

    Trick: call generate_code with every non-choice param set to a
    unique sentinel token, then see where those tokens land in the
    rendered output. Escape everything else as literal text, and turn
    each sentinel into a named capture group - so the regex is built
    from the block's own real rendering logic instead of guessing at
    its structure.

    Returns a list (usually one pattern, sometimes two). Blocks that
    quote strings with Python's repr() - like the built-in print block -
    pick ' or " depending on the string's own content, but a single
    sentinel-derived template can only encode one quote character. A
    line typed with the other quote style would otherwise fail to match
    this pattern and fall through to a more permissive one that ends up
    swallowing the quote characters into the captured value instead of
    treating them as delimiters. So when the rendering uses exactly one
    quote style as an apparent delimiter, a second pattern with quotes
    swapped is generated too.
    """
    params_meta = params_meta or []
    param_type_by_name = {p["name"]: p.get("type", "text") for p in params_meta}

    full_params = {}
    for p in params_meta:
        name = p["name"]
        full_params[name] = combo[name] if name in combo else f"@@{name}@@"

    try:
        rendered = gen_func(full_params, [], lang=lang)
    except Exception:
        return []
    if not rendered:
        return []

    patterns = []
    base = _pattern_from_rendered(rendered, param_type_by_name, combo)
    if base:
        patterns.append(base)

    has_single = "'" in rendered
    has_double = '"' in rendered
    if has_single and not has_double:
        alt = _pattern_from_rendered(rendered.replace("'", '"'), param_type_by_name, combo)
        if alt:
            patterns.append(alt)
    elif has_double and not has_single:
        alt = _pattern_from_rendered(rendered.replace('"', "'"), param_type_by_name, combo)
        if alt:
            patterns.append(alt)

    return patterns
