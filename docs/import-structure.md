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
