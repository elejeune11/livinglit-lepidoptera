"""Vocabulary and formula measures computed every build (03-vocabulary, How the vocabulary grows; 04-formulas, The formula agent)."""
from __future__ import annotations

from collections import Counter, defaultdict

from .text import normalize


def new_terms_per_paper(log: list[dict]) -> list[dict]:
    rows = []
    for ver in log:
        evs = ver.get("events", [])
        rows.append({"version": ver["version"], "paper": ver.get("paper"),
                     "new_terms": sum(e["event"] in ("add_term", "adopt_own") or (e["event"] == "adopt") for e in evs),
                     "synonyms": sum(e["event"] == "add_synonym" for e in evs) +
                                 sum(len(e.get("synonyms", [])) for e in evs if e["event"] in ("add_term", "adopt", "adopt_own")),
                     "keys": sum(e["event"] == "standing_key" for e in evs)})
    return rows


def refinements(log: list[dict], vocab, mapped_by_paper: dict) -> list[dict]:
    """A new term lists earlier values mapped to its parent as possible refinements, by paper (03-vocabulary)."""
    order = {}
    for ver in log:
        order.setdefault(ver.get("paper"), ver["version"])
    rows = []
    for ver in log:
        for e in ver.get("events", []):
            if e["event"] != "add_term" or not e.get("parent"):
                continue
            for paper, mapped in mapped_by_paper.items():
                if order.get(paper, 10 ** 9) >= ver["version"]:
                    continue
                for at, m in mapped.items():
                    if e["parent"] in (m.terms or []):
                        rows.append({"new_term": e["id"], "added_by": ver.get("paper"), "paper": paper, "at": at,
                                     "stated": m.text, "mapped_to": e["parent"]})
    return rows


def near_duplicates(vocab) -> list[dict]:
    rows = []
    by_field = defaultdict(list)
    for t in vocab.terms.values():
        for f in t.fields:
            by_field[f].append(t)
    for f, ts in by_field.items():
        keys = [(normalize(t.label), t.id) for t in ts]
        for i, (a, ia) in enumerate(keys):
            for b, ib in keys[i + 1:]:
                if a and b and (a in b or b in a) and abs(len(a) - len(b)) <= 3:
                    rows.append({"field": f, "a": ia, "b": ib})
    return rows


def flags_per_field(mapped_by_paper: dict) -> dict:
    c = Counter()
    for mapped in mapped_by_paper.values():
        for at, m in mapped.items():
            if m.origin == "flagged":
                c["measure" if at.endswith(".measure") else at.rsplit(".", 1)[-1]] += 1
    return dict(c)
