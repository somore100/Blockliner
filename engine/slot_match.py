"""
Phase F (v1): recognizing raw-typed code in an expression slot.

Scope, deliberately narrow - see the project backlog for why: Python
only, and only ever produces a func_call block. `print(x)` and
`mylist.append(y)` also parse as tree-sitter "call" nodes, but nothing
here tries to recognize them AS the print/list_append blocks
specifically - the match schema has no field yet to disambiguate
three blocks that all share match.node_kind "call" (func_call, print,
list_append), and neither of those two is something you'd sensibly
type as the *value* of an expression slot anyway (both return None).
Typing `print(x)` into a slot here still converts - just into a
generic func_call named "print", which renders identically
("print(x)") to the dedicated print block would have. Real
disambiguation between the three is Phase E's problem (cold-import of
whole statements, where it actually matters), not this one's.

This module never executes or evaluates anything - it only inspects
tree-sitter's parse tree and slices substrings out of the original
text, matching the project's existing "templates are pure string
substitution, never eval()" rule (see engine/renderer.py).
"""

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

_PY_LANGUAGE = Language(tspython.language())
_parser = Parser(_PY_LANGUAGE)

# func_call's own match.slot_map (languages/python/blocks/func_call.json)
# - kept in sync by hand for v1 rather than read from the pack at
# runtime, since this module only ever targets that one block.
_NAME_FIELD = "function"
_ARGS_FIELD = "arguments"


def try_match_expression(text, lang="python"):
    """
    Try to recognize `text` (whatever's currently typed into an
    expression-type param slot) as a single function call.

    Returns {"_nested_block": "func_call", "_nested_params": {"name":
    ..., "args": ...}} on a clean, unambiguous match. Returns None if
    it should stay flat text - including while the user is still
    mid-typing an incomplete call. A parse error is treated exactly
    like "not recognized yet", never surfaced as a mistake - matches
    the project's warn-and-strip-never-fatal contract elsewhere in the
    engine (see engine/loader.py, engine/schema.py).
    """
    if lang != "python":
        return None
    if not text or not text.strip():
        return None

    source = text.encode("utf-8")
    tree = _parser.parse(source)
    root = tree.root_node

    if root.has_error:
        return None

    # Must be exactly one bare expression statement wrapping a call -
    # not part of a larger statement (an assignment, a for-loop, two
    # statements typed with a semicolon, etc.). Anything else means
    # the slot doesn't hold just a single call expression.
    if len(root.children) != 1:
        return None
    stmt = root.children[0]
    if stmt.type != "expression_statement" or len(stmt.children) != 1:
        return None
    call_node = stmt.children[0]
    if call_node.type != "call":
        return None

    name_node = call_node.child_by_field_name(_NAME_FIELD)
    args_node = call_node.child_by_field_name(_ARGS_FIELD)
    if name_node is None or args_node is None:
        return None

    name_text = source[name_node.start_byte:name_node.end_byte].decode("utf-8")
    args_text = source[args_node.start_byte:args_node.end_byte].decode("utf-8")

    # "arguments" is the whole parenthesized argument_list (e.g.
    # "(5, x)") - func_call's own template already supplies the
    # parens ("[[name]]([[args]])"), so strip them here so the args
    # slot holds just the inner contents, matching what someone would
    # have typed into func_call's own args field by hand.
    if args_text.startswith("(") and args_text.endswith(")"):
        args_text = args_text[1:-1]

    return {
        "_nested_block": "func_call",
        "_nested_params": {"name": name_text, "args": args_text},
    }
