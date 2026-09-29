"""
Template renderer: pure string substitution, no eval()/exec() ever.

Placeholder syntax is locked at [[slotname]] (Phase 1 point 3) - two
opening brackets, a slot name, two closing brackets. A block's slot
values are dropped straight into the template text; nothing here ever
interprets or executes what the user typed into a block's fields, so
a template can't do anything a plain string can't do.
"""

import re

PLACEHOLDER_RE = re.compile(r"\[\[([a-zA-Z_][a-zA-Z0-9_]*)\]\]")


def render_template(template, slot_values):
    """
    Replace every [[slotname]] in `template` with str(slot_values[slotname]).
    A missing slot is substituted with "" rather than raising, so one
    incomplete block doesn't blow up rendering the whole project.
    """
    def _replace(match):
        return str(slot_values.get(match.group(1), ""))

    return PLACEHOLDER_RE.sub(_replace, template)


def indent_block(code, spaces=4):
    """Indent every non-blank line of `code` by `spaces` spaces."""
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else "" for line in code.split("\n"))


def _is_nested_block_value(value):
    """True for a Phase F chip value: {"_nested_block": id, "_nested_params": {...}}."""
    return isinstance(value, dict) and "_nested_block" in value


def _resolve_nested_slots(params, block_registry):
    """
    Replace any Phase F chip value in `params` with the plain string
    its nested block renders to, recursing as needed (a chip's own
    params could themselves hold a chip, though the UI only ever
    builds one level deep for now). Non-chip values pass through
    untouched. block_registry is required to resolve a chip's block_id
    to its definition - if it's missing (an older call site that
    hasn't been updated), chip values are left as-is rather than
    crashing, which will render as Python's dict repr - visibly wrong,
    matching the project's "honest incompleteness over fake
    completeness" rule rather than silently guessing at a string.
    """
    if not block_registry:
        return params
    resolved = dict(params or {})
    for key, value in resolved.items():
        if _is_nested_block_value(value):
            nested_def = block_registry.get(value["_nested_block"])
            if nested_def is None:
                continue
            rendered = render_block(
                nested_def, value.get("_nested_params", {}), block_registry=block_registry
            )
            resolved[key] = rendered.rstrip("\n")
    return resolved


def render_block(block_def, params, children=None, block_registry=None):
    """
    Render one block into source code.

    block_def      : dict loaded from a language pack's per-block JSON
                      file (languages/<lang>/blocks/<block_id>.json),
                      e.g. {"template": "print([[value]])\\n", ...}
    params         : dict of this block's own slot values. A value can
                      be a Phase F chip ({"_nested_block": ...,
                      "_nested_params": {...}}) instead of a plain
                      string - see engine/slot_match.py - and gets
                      rendered recursively before substitution.
    children       : list of already-rendered code strings for nested
                      blocks (only used when block_def["is_container"]
                      is True - mirrors the old
                      generate_code(params, children, lang) contract
                      so container blocks like `if` keep working the
                      same way, just driven by a template instead of
                      an indentation loop written in Python).
    block_registry : dict of block_id -> block_def, needed only to
                      resolve chip values in params. Both real call
                      sites (with_generate_code's closure, and
                      _render_recursive below) always pass it.
    """
    children = children or []
    slot_values = _resolve_nested_slots(params, block_registry)

    if block_def.get("is_container"):
        child_lines = [c.rstrip("\n") for c in children]
        body = "\n".join(child_lines)
        if not body.strip():
            body = block_def.get("empty_body", "pass")
        slot_values["body"] = indent_block(body)

    code = render_template(block_def.get("template", ""), slot_values)
    if not code.endswith("\n"):
        code += "\n"
    return code


def with_generate_code(blocks):
    """
    UI compatibility bridge: ui.py's existing block interface (see its
    get_block_attr() helper) expects every block to expose a callable
    generate_code(params, children, lang) - true for both old .py
    modules and dict-based custom blocks from the visual builder.
    This attaches an equivalent callable (backed by render_block, not
    exec'd code) to each JSON-loaded block dict, plus the couple of
    other keys ui.py reads (block_ui_description), so ui.py keeps
    working against JSON blocks with zero changes to its 4000+ lines.
    """
    result = {}
    for block_id, block_def in blocks.items():
        bd = dict(block_def)
        bd.setdefault("block_id", block_id)
        bd.setdefault("display_name", bd.get("display_name", block_id))
        bd.setdefault("block_ui_description", {
            "description": bd.get("description", ""),
            "params": bd.get("params", []),
            "category": bd.get("category", "Basic"),
        })

        def _generate_code(params, children, lang="python", _bd=bd, _registry=blocks):
            return render_block(_bd, params, children, block_registry=_registry)

        bd["generate_code"] = _generate_code
        result[block_id] = bd
    return result


def render_project(project, block_registry):
    """
    Render an entire Project (engine.model.Project) into source code,
    recursing into container blocks' children. block_registry maps
    block_id -> block definition dict, e.g. the "blocks" half of one
    entry from engine.loader.load_all_language_packs().
    """
    return "".join(_render_recursive(block, block_registry) for block in project.blocks)


def _render_recursive(block, block_registry):
    block_def = block_registry.get(block.block_id)
    if not block_def:
        return f"# \u26a0 Unknown block: {block.block_id}\n"

    children_code = [_render_recursive(child, block_registry) for child in block.children]
    return render_block(block_def, block.params, children_code, block_registry=block_registry)


# --- Phase A3: marker-comment round-trip -----------------------------------
#
# The marker tag itself (the "$$$blockliner:node:N$$$ start/end" part) is
# deliberately comment-syntax-agnostic - engine.markers.parse_marked_file()
# only ever searches for that literal tag text, never the surrounding
# comment characters, so parsing works even if a pack's comment_token is
# missing/invalid (see validate_comment_token) or a file gets hand-edited
# with mismatched comment style. Only *rendering* needs comment_token, to
# make the marker look like a real comment to the file's own language.
#
# The delimiter is plain ASCII ($$$) on purpose, not an exotic Unicode
# character - it needs to be something any human or AI coding assistant
# can type reliably on any keyboard, and that survives copy-paste through
# any terminal/editor without mangling.

MARKER_TAG = "$$$blockliner:node:{node_id}$$$"


def _comment_line(comment_token, text):
    """
    Wrap `text` as one comment line using a manifest's comment_token,
    which is either a single line-comment token ("//", "#") or a
    [open, close] pair for block-comment-only languages like HTML.
    Falls back to "#" if comment_token is missing entirely (e.g. an
    older pack from before A2, or one where a bad comment_token was
    stripped by validate_comment_token) rather than raising.
    """
    if isinstance(comment_token, (list, tuple)) and len(comment_token) == 2:
        return f"{comment_token[0]} {text} {comment_token[1]}"
    token = comment_token if isinstance(comment_token, str) else "#"
    return f"{token} {text}"


def render_node_with_marker(node, block_registry, comment_token):
    """
    Render one Node's contents wrapped in a marker-comment pair carrying
    its node_id, e.g.:
        # $$$blockliner:node:800$$$ start
        def health():
            ...
        # $$$blockliner:node:800$$$ end

    A raw node (node.raw_span is not None) is emitted verbatim - no
    template rendering happens for it, matching raw_code's "honest
    escape hatch" philosophy carried up to node granularity. Otherwise
    node.blocks is rendered via render_project() (works via the same
    duck-typing render_project already relies on for Project).
    """
    body = node.raw_span if node.raw_span is not None else render_project(node, block_registry)
    if body and not body.endswith("\n"):
        body += "\n"

    tag = MARKER_TAG.format(node_id=node.node_id)
    start_line = _comment_line(comment_token, f"{tag} start")
    end_line = _comment_line(comment_token, f"{tag} end")
    return f"{start_line}\n{body}{end_line}\n"


def render_file(blockliner_file, block_registry, comment_token):
    """
    Render an entire BlocklinerFile (engine.model.BlocklinerFile) as
    marker-wrapped source text - every node in file order, each in its
    own marker pair. This is the text Phase A3's round-trip checks
    against on reopen (see engine.markers.reconcile_file).
    """
    return "".join(
        render_node_with_marker(node, block_registry, comment_token)
        for node in blockliner_file.nodes
    )
