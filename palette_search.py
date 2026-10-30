"""Forgiving block search (pure, no Tk).

Every word you type must be found somewhere in the block's text (name,
description, category, keywords), but a word counts as found when it is the
same after light stemming ("reads" ~ "read"), starts a longer word
("cont" ~ "container") or is a close misspelling ("contanier"). Filler words
(a, the, to, ...) are ignored, so "reads text" finds "Reads a line of text".
"""
import difflib
import re

STOP = {"a", "an", "the", "to", "of", "into", "from", "in", "on", "and", "or", "is", "it", "for", "with", "that", "this", "as", "at", "by"}
_WORD = re.compile(r"[a-z0-9]+")
_SUFFIXES = ("ing", "ed", "es", "s")
CLOSE = 0.8                 # difflib ratio for "close enough" (words of 4+ letters)
WEIGHTS = {"name": 4.0, "keywords": 3.0, "id": 2.0, "category": 1.5, "description": 1.0}


def stem(word):
    for suf in _SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            return word[: -len(suf)]
    return word


def tokens(text):
    """Stemmed words of `text` without filler words."""
    return [stem(w) for w in _WORD.findall((text or "").lower()) if w not in STOP]


def _word_score(q, words):
    """How well query word `q` is found among `words` (0 = not at all)."""
    best = 0.0
    for w in words:
        if w == q:
            return 3.0
        if len(q) >= 2 and w.startswith(q):
            best = max(best, 2.0)
        elif len(q) >= 4 and len(w) >= 4 and difflib.SequenceMatcher(None, q, w).ratio() >= CLOSE:
            best = max(best, 1.0)
    return best


def score(query, fields):
    """Match score of `query` against {field: text}; 0 means no match.
    All query words must be found (in any field); fields weigh differently."""
    qs = tokens(query)
    if not qs:
        return 1.0                    # nothing to filter on: everything matches
    per_field = {f: tokens(t) for f, t in fields.items()}
    total = 0.0
    for q in qs:
        best = 0.0
        for f, words in per_field.items():
            s = _word_score(q, words) * WEIGHTS.get(f, 1.0)
            best = max(best, s)
        if best == 0.0:
            return 0.0
        total += best
    return total
