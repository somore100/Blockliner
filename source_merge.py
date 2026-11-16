"""Three-way merge of a source file by node (pure: no Tk, no files). See docs/team-editing.md.

A node is one top-level part of the file (portable.split_top_level). The three versions are lists of (id, text):
  base    what Blockliner read
  mine    what Blockliner would write now (the edit, already spliced into base)
  theirs  the file on disk now, cut the same way
merge() decides per node. Nodes that only one side changed are taken from that side; nodes both sides changed
differently become git-style conflict markers (only for those nodes), so git and every editor understand them."""
import difflib
import re

MINE_LABEL = "mine (Blockliner)"
THEIRS_LABEL = "theirs (on disk)"
_REGION = re.compile(r"^<<<<<<< [^\n]*\n(.*?)^=======\n(.*?)^>>>>>>> [^\n]*(?:\n|\Z)", re.M | re.S)
_SIMILAR = 0.6


def has_conflicts(text):
    return bool(_REGION.search(text))


def count_conflicts(text):
    return len(_REGION.findall(text))


def _same(a, b):
    return (a or "").rstrip() == (b or "").rstrip()


def _alike(a, b):
    a = "\n".join(l.strip() for l in a.splitlines() if l.strip())
    b = "\n".join(l.strip() for l in b.splitlines() if l.strip())
    return bool(a and b) and difflib.SequenceMatcher(None, a, b).ratio() >= _SIMILAR


def match_ids(base, other):
    """`other` [(id, text)] with its ids renamed to the ids of `base` where they are the same node: the same id, or
    (for ids that only one list has) texts alike enough to be one node edited or renamed. Returns [(id, text)]."""
    bids = {i for i, _t in base}
    known = [(i, t) for i, t in other if i in bids]
    taken = {i for i, _t in known}
    loose = [(i, t) for i, t in other if i not in bids]
    free = [(i, t) for i, t in base if i not in {x for x, _ in other}]
    out = {}
    pairs = sorted(((difflib.SequenceMatcher(None, bt, ot).ratio() if _alike(bt, ot) else 0, bi, oi)
                    for bi, bt in free for oi, ot in loose), reverse=True)
    used_b, used_o = set(), set()
    for score, bi, oi in pairs:
        if score and bi not in used_b and oi not in used_o and bi not in taken:
            out[oi] = bi
            used_b.add(bi)
            used_o.add(oi)
    return [(out.get(i, i), t) for i, t in other]


def _marked(mine, theirs):
    def part(t):
        return "" if not t else (t if t.endswith("\n") else t + "\n")
    return f"<<<<<<< {MINE_LABEL}\n{part(mine)}=======\n{part(theirs)}>>>>>>> {THEIRS_LABEL}\n"


def _order(base_ids, mine_ids, theirs_ids, keep):
    """The order of the surviving ids: theirs, unless only mine moved nodes. Ids only one side has are placed after
    their predecessor in that side's list."""
    def only(ids):
        return [i for i in ids if i in keep]
    b, m, t = only(base_ids), only(mine_ids), only(theirs_ids)
    common_b = [i for i in b if i in m and i in t]
    common_m = [i for i in m if i in common_b]
    common_t = [i for i in t if i in common_b]
    lead = m if (common_t == common_b and common_m != common_b) else t
    other = t if lead is m else m
    out = list(lead)
    for i, x in enumerate(other):
        if x in out:
            continue
        j = i - 1
        while j >= 0 and other[j] not in out:
            j -= 1
        out.insert(out.index(other[j]) + 1 if j >= 0 else 0, x)
    return out


def merge(base, mine, theirs):
    """(chunks [(id, text)], conflicts [id]). Conflicting nodes carry conflict markers in their text."""
    theirs = match_ids(base, theirs)
    mine = match_ids(base, mine)
    b, m, t = dict(base), dict(mine), dict(theirs)
    result, conflicts = {}, []
    for nid in list(dict.fromkeys([i for i, _ in base] + [i for i, _ in mine] + [i for i, _ in theirs])):
        inb, inm, int_ = nid in b, nid in m, nid in t
        if inb:
            if not inm and not int_:
                continue
            if not inm:
                if _same(t[nid], b[nid]):
                    continue
                result[nid] = _marked("", t[nid]); conflicts.append(nid)
            elif not int_:
                if _same(m[nid], b[nid]):
                    continue
                result[nid] = _marked(m[nid], ""); conflicts.append(nid)
            elif _same(m[nid], b[nid]):
                result[nid] = t[nid]
            elif _same(t[nid], b[nid]) or _same(m[nid], t[nid]):
                result[nid] = m[nid] if not _same(m[nid], t[nid]) else t[nid]
            else:
                result[nid] = _marked(m[nid], t[nid]); conflicts.append(nid)
        elif inm and int_:
            if _same(m[nid], t[nid]):
                result[nid] = t[nid]
            else:
                result[nid] = _marked(m[nid], t[nid]); conflicts.append(nid)
        else:
            result[nid] = m[nid] if inm else t[nid]
    ids = _order([i for i, _ in base], [i for i, _ in mine], [i for i, _ in theirs], set(result))
    chunks = [(i, result[i]) for i in ids]
    # a chunk that was last (no blank line after it) and now has something after it gets a line break and a blank line
    fixed = []
    for k, (i, tx) in enumerate(chunks):
        if tx and k < len(chunks) - 1 and not tx.endswith("\n\n"):
            tx = tx.rstrip("\n") + "\n\n"
        fixed.append((i, tx))
    chunks = fixed
    return chunks, conflicts


def conflict_regions(text):
    """[(mine, theirs)] for every conflict-marker region in `text`, in file order."""
    return [(m.group(1), m.group(2)) for m in _REGION.finditer(text)]


def resolve(text, choices):
    """`text` with each marker region replaced by the chosen side: choices is a list, one of "mine" / "theirs" /
    "both" (theirs, a blank line, mine) per region in file order."""
    it = iter(choices)

    def pick(m):
        c = next(it, "theirs")
        mine, theirs = m.group(1), m.group(2)
        if c == "mine":
            return mine
        if c == "both":
            return theirs + ("\n" if theirs and not theirs.endswith("\n\n") else "") + mine
        return theirs
    return _REGION.sub(pick, text)
