# Importing code: how much stays Raw Code

Measured on 24 real Python files (a sample of the standard library plus some of this project's own modules), counting blocks
the importer matched against blocks it kept as Custom Code, and whether the regenerated code equals the original:

| | Raw Code share | Same after regenerate |
|---|---|---|
| before | 39 % | not measured (known: a raw line in a body gained an extra indent) |
| after | 19 % | 426 of 439 chunks (the rest: `'` became `"` in a matched block, and under-indented docstring lines) |

What changed (all in `ui_import.py`, `statements.py`, `languages/python/blocks/raw_block.json`):

- **A statement over several lines is one block.** `statements.statement_end` follows open brackets, triple-quoted strings
  and a trailing backslash. A docstring or a call spread over lines used to become a raw block per line, and an
  under-indented docstring line also ended its function's body early. A compound header over several lines
  (`if (a and\n b):`) is still handled line by line.
- **An unmatched header keeps its body.** `with a, b:`, `match`, `async for` and any other header no block covers becomes a
  *Custom Block* (`raw_block`: the header as written, with a body), so the body is still nested, not flat raw lines.
- **No extra indent.** A raw line inside a body was stored with its indent and indented again when the code was regenerated.
- The block face shows `first line ⏎ +N lines` for a multi-line value, and the editor uses a small text box for it.

Still raw (the next candidates): docstrings and comments (kept lossless but as Custom Code), assignments the Set Variable
pattern doesn't accept (tuple unpacking, annotations, `+=` on attributes), bare `return` / `yield` / `del` / `raise X`, and
`# comment` lines with a trailing comment on a header. Measure with a script like `tests/` ... over a folder to see the list.
Only Python gets the grouping (brace languages keep their own rule).

## Splitting a file into nodes

`portable.split_top_level` (any language) cuts a file with no node markers. Besides one node per top-level class / function,
top-level code **separated by blank lines is one node per group** (a group of only imports is named `imports`, the rest
`top_level`, `top_level_2` ...). Blank lines inside a function, bracket or triple-quoted string never split. The nodes join back
into exactly the original text. Class methods and long functions are still one node each.

## Class methods as nodes (Python)

File > Import Code > "split into nodes" now also opens a Python class that has methods as a **class node**:

- `<Name>_header`: the `class` line, its docstring and class attributes.
- one node per method (decorators and comment lines right above a method stay with it).

A method node holds its code without the class indent, so it imports into real blocks. The node keeps `indent`
(the class indent width, saved in projects and in the portable metadata); the indent is added back when code is
generated, so the generated file has the original text. Per-node code views show the method without the indent.
Method nodes stay in file order under their class and are not moved first by the "definitions first" rule.

Not split: a class with no methods, tab-indented classes, files opened as a followed file or a project folder
(those still use one node per top-level part). As for any import, blank lines between statements are not kept.
