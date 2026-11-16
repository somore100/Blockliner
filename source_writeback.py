"""Source-first, phase 2 (see docs/source-first-mode.md): put an edit made in Blockliner back into the source file,
touching only the nodes that were edited. Pure (no Tk); the only thing here that writes is write_source().

A followed file is cut into chunks (portable.split_top_level; "".join(chunks) is the file). Every chunk is a node.
After an edit, plan() builds the new file text from the old chunks: a node whose generated code is the same as when the
file was read keeps its ORIGINAL text byte for byte (so reading a file and writing it back changes nothing, however it
was formatted); only a node the user really changed is replaced by its newly generated code; a node that is gone is
dropped; a new node is appended at the end."""
import hashlib
import os

import safe_write


class Source:
    """A source file as text: `text` has "\\n" line ends whatever the file used; eol and bom say how to write it back."""
    def __init__(self, text, eol, bom):
        self.text, self.eol, self.bom = text, eol, bom


def decode(raw):
    """Source for the bytes of a file, or (None, reason) when writing it back could not be exact: not valid UTF-8,
    or line ends that are a mix (or a lone carriage return)."""
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw[3:].decode("utf-8") if bom else raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, "the file is not valid UTF-8"
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    bare_cr = text.count("\r") - crlf
    if bare_cr:
        return None, "the file has old-style (lone carriage return) line ends"
    if crlf and lf:
        return None, "the file mixes Windows and Unix line ends"
    eol = "\r\n" if crlf else "\n"
    return Source(text.replace("\r\n", "\n"), eol, bom), ""


def read_source(path):
    """(Source, "") or (None, reason)."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        return None, f"the file cannot be read ({exc.strerror or exc})"
    return decode(raw)


def encode(text, eol="\n", bom=False):
    """The text to write for a file that was read with this eol and bom."""
    if eol != "\n":
        text = text.replace("\n", eol)
    return ("﻿" if bom else "") + text


def hash_file(path):
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                h.update(block)
    except OSError:
        return None
    return h.hexdigest()


def _split_tail(text):
    """(body, tail): the blank lines at the end of a chunk stay with it when the body is replaced."""
    body = text.rstrip(" \t\r\n")
    tail = text[len(body):]
    lines = tail.split("\n")
    # keep the line break that ends the body out of the tail; keep the blank lines after it
    keep = "\n".join(lines[1:]) if len(lines) > 1 else ""
    return body, keep


def indent_unit(text):
    """How the original code indents one level: "\t", or that many spaces as a string; None when it has no indented line."""
    unit = None
    for line in text.split("\n"):
        if not line.strip() or not line[0].isspace():
            continue
        if line[0] == "\t":
            return "\t"
        n = len(line) - len(line.lstrip(" "))
        unit = n if unit is None else min(unit, n)
    return " " * unit if unit else None


def restyle(code, original):
    """Generated code uses 4 spaces per level; give it the file's own indentation (tabs, or 2/8 spaces) so an edited
    node does not look foreign in its file."""
    unit = indent_unit(original)
    if unit is None or unit == "    ":
        return code
    out = []
    for line in code.split("\n"):
        n = len(line) - len(line.lstrip(" "))
        out.append(unit * (n // 4) + " " * (n % 4) + line[n:] if n else line)
    return "\n".join(out)


def plan(chunks, baseline, current):
    """The file's new chunks.

    chunks   [(id, original text)] in file order
    baseline {id: code generated when the file was read}
    current  [(id, code generated now)] in node order
    Returns [(id, text)]. Equal to `chunks` when nothing was edited."""
    now = dict(current)
    out = []
    for cid, text in chunks:
        if cid not in now:
            continue                                   # the node was deleted
        gen = now[cid]
        if gen == baseline.get(cid):
            out.append((cid, text))                    # untouched: the original bytes
            continue
        body, keep = _split_tail(text)
        new_body = restyle(gen, body).rstrip("\n")
        out.append((cid, (new_body + "\n" + keep) if new_body else keep))
    known = {cid for cid, _t in chunks}
    added = [(cid, gen.rstrip("\n") + "\n") for cid, gen in current if cid not in known and gen.strip()]
    if out and added and not out[-1][1].endswith("\n\n"):
        added[0] = (added[0][0], "\n" + added[0][1])      # a new node is set apart from the old end by a blank line
    out += added
    # joining must never glue lines together: a chunk that lost its final newline gets one when something follows
    return [(cid, text + "\n" if text and not text.endswith("\n") and i < len(out) - 1 else text)
            for i, (cid, text) in enumerate(out)]


def join(chunks):
    return "".join(text for _cid, text in chunks)


def write_source(path, text, source):
    """Write `text` (with "\\n" line ends) back with the eol/bom the file had, atomically.
    Returns (size, mtime_ns, hash) of what is on disk now."""
    data = encode(text, source.eol, source.bom)
    safe_write.write_text_atomic(path, data)
    st = os.stat(path)
    return st.st_size, st.st_mtime_ns, hash_file(path)
