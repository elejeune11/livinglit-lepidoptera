"""Matching stated text to terms, and comparing term sets (03-vocabulary, How code matches; Comparing on terms)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .numbers import parse_number, try_unit, interval, numbers_in
from .text import normalize

SEPARATORS = {"+", ",", ";", "and", "with", "/", "&"}
TOKEN = re.compile(r"[,;+/&]|[^\s,;+/&]+")


@dataclass
class Match:
    terms: set[str] | None
    leftover: list[str] = field(default_factory=list)


def match_text(vocab, fld: str, text: str, max_words: int = 8) -> Match:
    """Every part must match a synonym or label; separators are skipped; ancestors dropped."""
    lex = vocab.lexicon(fld)
    toks = TOKEN.findall(text.lower())
    i, found, left = 0, set(), []
    while i < len(toks):
        hit = None
        for j in range(min(len(toks), i + max_words), i, -1):
            key = normalize(" ".join(toks[i:j]))
            if key and key in lex:
                hit = (j, lex[key])
                break
        if hit:
            found.add(hit[1])
            i = hit[0]
            continue
        if toks[i] in SEPARATORS or not normalize(toks[i]):
            i += 1
            continue
        left.append(toks[i])
        i += 1
    if left or not found:
        return Match(None, left)
    return Match(drop_ancestors(vocab, found))


def drop_ancestors(vocab, terms: set[str]) -> set[str]:
    return {t for t in terms if not any(t in vocab.ancestors(o) for o in terms if o != t)}


@dataclass
class Side:
    terms: set[str] = field(default_factory=set)
    state: str | None = None  # "not stated", "unmapped", "flagged", "by reference", "not applicable"
    flag: str | None = None
    qualifiers: dict = field(default_factory=dict)


def compare_terms(vocab, fld: str, a: Side, b: Side, level: int | None = None, under: str | None = None) -> str:
    for s in (a, b):
        if s.state == "flagged":
            return "flagged"
    for s in (a, b):
        if s.state == "unmapped":
            return "unmapped"
    for s in (a, b):
        if s.state == "by reference":
            return "by reference"
    for s in (a, b):
        if s.state in ("not stated", "not yet read", "not stated in this source"):
            return s.state
    A, B = set(a.terms), set(b.terms)
    st = lambda X: X and all(x.startswith("state:") for x in X)
    if A != B and (st(A) != st(B)) and A and B:
        return "not stated (a named state against a term)"  # open world: unknown, not a conflict
    if a.state == "not applicable" or b.state == "not applicable":
        return "same" if a.state == b.state else "differ"
    if A == B:
        return "same"
    if under:
        inside = lambda t: t == under or under in vocab.ancestors(t)
        if all(inside(t) for t in A) and all(inside(t) for t in B):
            return f"same under {under}"
    if level:
        if {vocab.at_level(t, level) for t in A} == {vocab.at_level(t, level) for t in B}:
            return f"same at level {level}"
    covers = lambda X, Y: all(any(x == y or y in vocab.ancestors(x) for y in Y) for x in X)
    if covers(A, B) or covers(B, A):
        return "narrower / broader"
    return "differ"


NUMBER_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
                "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12"}


def quantity_value(printed: str) -> tuple[float, float, float, str | None] | None:
    """(value, lo, hi, dimension) in base units for a printed quantity, or None."""
    import re as _re
    low = printed.strip().lower()
    if not (_re.search(r"(?<![a-z])[-+−]?(\d|\.\d)", low) or low.split(" ")[0] in NUMBER_WORDS):
        return None  # a name (a gene, a line), not a quantity
    first = printed.strip().split(" ", 1)
    if first and first[0].lower() in NUMBER_WORDS:
        printed = NUMBER_WORDS[first[0].lower()] + (" " + first[1] if len(first) > 1 else "")
    try:
        num, _ = parse_number(printed)
    except ValueError:
        return None
    unit_text = printed.split(num.lstrip("-").split("e")[0], 1)[-1] if num else ""
    unit_text = re.sub(r"^[\d.\s]*", "", unit_text).strip()
    u = try_unit(unit_text)
    lo, hi = interval(num)
    f = u.factor if u.name else 1.0
    return float(num) * f, lo * f, hi * f, u.dimension


def compare_quantity(a: str, b: str) -> str:
    qa, qb = quantity_value(a), quantity_value(b)
    if qa is None or qb is None:
        return "same" if normalize(a) == normalize(b) else "differ"
    if qa[3] != qb[3]:
        return "differ" if qa[3] and qb[3] else ("same" if abs(qa[0] - qb[0]) < 1e-12 else "differ")
    return "same" if qa[1] <= qb[2] and qb[1] <= qa[2] else "differ"


def compare_qualifiers(qa: dict, qb: dict) -> str:
    keys = set(qa) | set(qb)
    if not keys:
        return "same"
    if any(k not in qa or k not in qb for k in keys):
        return "not stated"
    return "same" if all(compare_quantity(qa[k], qb[k]) == "same" for k in keys) else "differ"
