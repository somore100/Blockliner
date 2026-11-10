"""Content of the "How is a project built?" window (pure, no Tk).

A project is made of FILES; a file is made of NODES (a batch of code that does one job);
a node is made of BLOCKS (one line of code, or a line with lines inside it)."""

LEVELS = [
    {"key": "file", "layer": "files", "icon": "\U0001F4C1", "name": "File", "color": "#4ec9b0",
     "what": "One program in one language (entry.py). A project holds one or more files.",
     "where": "Files layer"},
    {"key": "node", "layer": "nodes", "icon": "\U0001F5C2", "name": "Node", "color": "#ffb454",
     "what": "A batch of code that does one job, like asking the age or checking it. Nodes run in order; wires show how they connect.",
     "where": "Nodes layer"},
    {"key": "block", "layer": "blocks", "icon": "\U0001F9E9", "name": "Block", "color": "#569cd6",
     "what": "One line of code. A block like if can hold more blocks inside it.",
     "where": "Blocks layer"},
]

FILE_NAME = "entry.py"

# (node name, [(line of code, depth)]) - a block with depth 1 sits inside the block above it
EXAMPLE = [
    ("ask_age", [("age = int(input('Age? '))", 0)]),
    ("check_age", [("if age > 18:", 0), ('print("allow entry")', 1), ("else:", 0), ('print("too young")', 1)]),
    ("goodbye", [('print("bye")', 0)]),
]


def example_code():
    """The program the example makes, as plain Python."""
    lines = []
    for _name, blocks in EXAMPLE:
        for text, depth in blocks:
            lines.append("    " * depth + text)
    return "\n".join(lines) + "\n"


def code_rows():
    """[(node name, text of the line)] in file order, with node marker lines as the Code
    layer shows them; the marker rows belong to their node."""
    rows = []
    for name, blocks in EXAMPLE:
        rows.append((name, f"# $$$blockliner:node:{name}$$$ start"))
        for text, depth in blocks:
            rows.append((name, "    " * depth + text))
        rows.append((name, f"# $$$blockliner:node:{name}$$$ end"))
    return rows
