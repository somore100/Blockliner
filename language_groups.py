"""How the language dropdown is ordered and grouped (pure, no Tk).

A language's manifest.json may say what kind it is:  "kind": "code" (default),
"text" (documents and data) or "workflow" (scripts and automation). Anything
else lands in "other". The dropdown lists the kinds as sections, but only when
more than one kind exists; with code languages alone it stays a plain list.
Order is fixed and predictable (no "recent first", which would move the items
under the mouse): the built-in languages in their usual order, then the user's
own alphabetically.
"""
KINDS = (("code", "Code languages"), ("text", "Text and data"), ("workflow", "Workflows and scripts"))
OTHER = ("other", "Other")
HEADER = "── "          # a dropdown row starting with this is a heading, not a language
HEADER_END = " ──"


def kind_of(manifest):
    """The language's kind from its manifest dict; unknown or missing -> 'code'
    when absent, 'other' when it names a kind that isn't known."""
    value = manifest.get("kind") if isinstance(manifest, dict) else None
    if value is None:
        return "code"
    known = {k for k, _label in KINDS}
    return value if isinstance(value, str) and value in known else "other"


def sort_key(lang, preset):
    return (0, preset.index(lang), lang) if lang in preset else (1, 0, lang)


def groups(kinds, preset=()):
    """[(kind, label, [language, ...])] for {language: kind}; empty groups left out."""
    out = []
    known = {k for k, _label in KINDS}
    kinds = {l: (k if k in known else OTHER[0]) for l, k in kinds.items()}      # never lose a language
    for kind, label in (*KINDS, OTHER):
        members = sorted((l for l, k in kinds.items() if k == kind), key=lambda l: sort_key(l, list(preset)))
        if members:
            out.append((kind, label, members))
    return out


def ordered(kinds, preset=()):
    """Every language, grouped order, no headings."""
    return [l for _k, _label, members in groups(kinds, preset) for l in members]


def dropdown_values(kinds, preset=()):
    """What the dropdown shows: languages, with a heading row before each
    section when there is more than one section."""
    grouped = groups(kinds, preset)
    if len(grouped) < 2:
        return ordered(kinds, preset)
    values = []
    for _kind, label, members in grouped:
        values.append(f"{HEADER}{label}{HEADER_END}")
        values.extend(members)
    return values


def is_heading(value):
    return isinstance(value, str) and value.startswith(HEADER)


def languages_only(values):
    return [v for v in values if not is_heading(v)]
