"""What changing a file's language does to the file (pure, no Tk).

A file (tab) has one language. Its blocks are that language's blocks, and a UI
node's design belongs to one language and one UI library, so neither can be
converted by flipping the dropdown. assess() says what would be lost, so the
window can refuse or ask first instead of leaving a half-converted file.
"""
import ui_node


def _walk(nodes):
    for node in nodes or []:
        yield node
        yield from _walk(node.get("child_nodes"))


def assess(tab, new_language):
    """{"same": bool, "ui_nodes": [names], "with_blocks": [names]} for switching
    `tab` to `new_language`. Nothing is changed."""
    nodes = list(_walk(tab.get("nodes")))
    return {
        "same": new_language == tab.get("language"),
        "ui_nodes": [n["name"] for n in nodes if ui_node.is_ui_node(n)],
        "with_blocks": [n["name"] for n in nodes if n.get("blocks") and not ui_node.is_ui_node(n)],
    }


def verdict(info):
    """"nothing" (just switch), "ask" (content would be cleared) or "refuse"
    (a UI design would be left behind)."""
    if info["same"]:
        return "nothing"
    if info["ui_nodes"]:
        return "refuse"
    if info["with_blocks"]:
        return "ask"
    return "nothing"


def clear_blocks(tab):
    """Empty the blocks of every node in the tab (their code belongs to the old
    language). The lists are cleared in place: the active node's list is also
    the window's working list."""
    for node in _walk(tab.get("nodes")):
        if isinstance(node.get("blocks"), list):
            node["blocks"].clear()


def extension_for(language, extensions):
    """The file ending ('.py') of a language from LANGUAGE_EXTENSIONS, or ''."""
    for ext, lang in extensions.items():
        if lang == language:
            return ext
    return ""
