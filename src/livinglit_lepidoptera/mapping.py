"""Stated values and their mappings: matched, assigned, flagged (03-vocabulary, Mapping, and flags).

Matches are recomputed on every build and never stored. Identical stated text of
a field within a paper is mapped once and reused wherever it appears.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dfield

from .matching import match_text, quantity_value
from .models import Record, TermsFile, ContextObj
from .record import all_context_values
from .text import normalize

NAMED_STATES = {"notstated": "not stated", "notapplicable": "not applicable", "na": "not applicable",
                "none": "none"}


@dataclass
class Occurrence:
    at: str
    field: str
    text: str | None
    qualifiers: dict = dfield(default_factory=dict)
    by_reference: str | None = None


@dataclass
class Mapped:
    origin: str  # matched | assigned | flagged | quantity | not stated | not applicable | none | by reference | unmapped
    terms: list[str] = dfield(default_factory=list)
    qualifiers: dict = dfield(default_factory=dict)
    flag: str | None = None
    note: str | None = None
    text: str | None = None

    def signature(self) -> tuple:
        q = tuple(sorted(self.qualifiers.items()))
        if self.origin in ("matched", "assigned"):
            return ("terms", tuple(sorted(self.terms)), _qsig(self.qualifiers))
        if self.origin == "quantity":
            qv = quantity_value(self.text or "")
            return ("quantity", (round(qv[0], 9), qv[3]) if qv else normalize(self.text or ""), _qsig(self.qualifiers))
        if self.origin in ("not stated", "not applicable", "none"):
            return ("state", self.origin, _qsig(self.qualifiers))
        if self.origin == "state":
            return ("state", normalize(self.text or ""), _qsig(self.qualifiers))
        return (self.origin, normalize(self.text or ""), q)


def _qsig(q: dict) -> tuple:
    out = []
    for k, v in sorted(q.items()):
        qv = quantity_value(v)
        out.append((k, (round(qv[0], 9), qv[3]) if qv else normalize(v)))
    return tuple(out)


def occurrences(rec: Record) -> list[Occurrence]:
    out = []
    for at, f, v in all_context_values(rec):
        if isinstance(v, ContextObj):
            out.append(Occurrence(at, f, v.value, dict(v.qualifiers), v.by_reference.citation if v.by_reference else None))
        else:
            out.append(Occurrence(at, f, v))
    for iid, it in rec.evidence.items():
        out.append(Occurrence(f"evidence.{iid}.measure", "measure", it.measure))
    return out


def named_state(text: str | None) -> str | None:
    return NAMED_STATES.get(normalize(text or "")) if text is not None else "not stated"


def map_occurrence(vocab, occ: Occurrence, assigned: dict) -> Mapped:
    if occ.by_reference:
        return Mapped("by reference", qualifiers=occ.qualifiers, text=occ.by_reference)
    st = named_state(occ.text)
    if st:
        return Mapped(st, qualifiers=occ.qualifiers, text=occ.text)
    decl = vocab.fields.get(occ.field)
    key = (occ.field, normalize(occ.text))
    if key in assigned:
        m = assigned[key]
        if m.flag:
            return Mapped("flagged", flag=m.flag.kind, note=m.flag.note, text=occ.text)
        return Mapped("assigned", list(m.terms), {**m.qualifiers, **occ.qualifiers}, text=occ.text)
    if decl is not None and normalize(occ.text) in {normalize(x) for x in getattr(decl, "states", [])}:
        return Mapped("state", qualifiers=occ.qualifiers, text=occ.text)
    if decl is not None and decl.kind == "quantity":
        if quantity_value(occ.text) is not None:
            return Mapped("quantity", qualifiers=occ.qualifiers, text=occ.text)
        return Mapped("unmapped", qualifiers=occ.qualifiers, text=occ.text)
    m = match_text(vocab, occ.field, occ.text)
    if m.terms:
        return Mapped("matched", sorted(m.terms), dict(occ.qualifiers), text=occ.text)
    return Mapped("unmapped", qualifiers=occ.qualifiers, text=occ.text)


def assigned_index(tf: TermsFile | None) -> dict:
    if tf is None:
        return {}
    return {(m.field, normalize(m.stated)): m for m in tf.mappings}


def map_record(vocab, rec: Record, tf: TermsFile | None) -> dict[str, Mapped]:
    a = assigned_index(tf)
    return {o.at: map_occurrence(vocab, o, a) for o in occurrences(rec)}


def signer(vocab, rec: Record, tf: TermsFile | None):
    """A signature function for groups.stated_signatures, using mappings where they exist."""
    a = assigned_index(tf)

    def sign(at, f, v):
        if isinstance(v, ContextObj):
            occ = Occurrence(at, f, v.value, dict(v.qualifiers), v.by_reference.citation if v.by_reference else None)
        else:
            occ = Occurrence(at, f, v)
        return map_occurrence(vocab, occ, a).signature()
    return sign


def wording_copies(vocab, rec: Record, mapped: dict[str, Mapped]) -> list[dict]:
    """Distinct stated texts of one field that map to the same terms and qualifiers: copies that differ
    only in wording, reported back to the reader (03-vocabulary, How code matches)."""
    seen: dict = {}
    for at, m in mapped.items():
        if m.origin not in ("matched", "assigned") or at.endswith(".measure"):
            continue
        f = at.rsplit(".", 1)[-1]
        seen.setdefault((f, m.signature()), set()).add(m.text)
    return [{"field": f, "texts": sorted(t)} for (f, _), t in seen.items() if len({normalize(x) for x in t}) > 1]
