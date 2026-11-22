"""The controlled vocabulary: format, edit checks, append-only log and rebuild (03-vocabulary).

fields/<field>/field.yaml declares the fields; fields/<field>/changes.yaml is the
append-only log of accepted edits; vocab.yaml is rebuilt from both by code.
Edits only add: a term, an adopted id (or a second field for it), an own term in
an adopted field, a synonym, a scope note, a field, a standing key.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dfield
from pathlib import Path

import yaml

from . import FIELDS_DIR, DEFAULT_FIELD
from .text import normalize

OWN_ID = re.compile(r"^([a-z][a-z0-9_]*):([a-z0-9_]+)$")
CANARIES = ("sythemax", "xay939")
ONTOLOGY_PREFIX = {"chebi": "CHEBI:", "cl": "CL:", "mondo": "MONDO:", "cellosaurus": "CVCL_", "uo": "UO:"}
KEY_SPECIALS = {"contrast", "derivation", "method", "software"}


@dataclass
class FieldDecl:
    name: str
    kind: str  # terms | adopted | quantity | measure | identifier
    ontology: str | None = None
    set: bool = True
    scope: str = ""
    states: list = dfield(default_factory=list)


@dataclass
class Term:
    id: str
    fields: list[str]
    label: str
    parent: str | None = None
    definition: str = ""
    scope: str | None = None
    synonyms: list[dict] = dfield(default_factory=list)
    qualifiers: dict = dfield(default_factory=dict)
    dimension: str | None = None
    xref: list[str] = dfield(default_factory=list)
    source: str = "LivingLit"  # or the ontology name for adopted ids
    lookup: str | None = None
    added: dict = dfield(default_factory=dict)

    @property
    def field(self) -> str:
        return self.fields[0]

    @property
    def adopted(self) -> bool:
        return self.source != "LivingLit"


@dataclass
class KeyPart:
    must_match: list[str]
    may_vary: list[str] = dfield(default_factory=list)


@dataclass
class StandingKey:
    measure: str
    value: KeyPart
    direction: KeyPart
    added: dict = dfield(default_factory=dict)


class Vocabulary:
    def __init__(self, fields: dict[str, FieldDecl], name: str = DEFAULT_FIELD):
        self.name = name
        self.fields = dict(fields)
        self.terms: dict[str, Term] = {}
        self.keys: dict[str, StandingKey] = {}
        self.version = 0
        self.ontology = None  # set by the build for adopted-id ancestry
        self.measure_qualifiers: dict = {}  # field-wide measure qualifiers; a list fixes their values (decision 24)

    # ---------------------------------------------------------------- tree
    def field_terms(self, f: str) -> dict[str, Term]:
        return {t.id: t for t in self.terms.values() if f in t.fields}

    def lineage(self, tid: str) -> list[str]:
        """Root first, the term last (own trees)."""
        out, t = [], tid
        while t and t in self.terms and t not in out:
            out.append(t)
            t = self.terms[t].parent
        return list(reversed(out))

    def depth(self, tid: str) -> int:
        return len(self.lineage(tid))

    def at_level(self, tid: str, k: int) -> str:
        a = self.lineage(tid)
        return a[min(k, len(a)) - 1] if a else tid

    def ancestors(self, tid: str) -> set[str]:
        """Strict ancestors: own parent chain, plus ontology ancestors for adopted ids."""
        out = set(self.lineage(tid)[:-1])
        t = self.terms.get(tid)
        if t is not None and t.adopted and self.ontology is not None:
            out |= set(self.ontology.ancestors(tid))
        return out

    def lexicon(self, f: str) -> dict[str, str]:
        out = {}
        for t in self.field_terms(f).values():
            for w in [t.label] + [s["text"] for s in t.synonyms if s.get("field") in (None, f)]:
                out[normalize(w)] = t.id
        return out

    # ---------------------------------------------------------------- export
    def to_yaml(self) -> dict:
        return {"name": self.name, "version": self.version,
                "fields": {k: {kk: vv for kk, vv in v.__dict__.items() if kk != "name" and vv not in (None, "")}
                           for k, v in self.fields.items()},
                "terms": [{k: v for k, v in t.__dict__.items() if v not in (None, [], {}, "")} for t in self.terms.values()],
                "standing_keys": {m: {"value": k.value.__dict__, "direction": k.direction.__dict__, "added": k.added}
                                  for m, k in self.keys.items()}}


# -------------------------------------------------------------------- loading
def load_fields(field: str = DEFAULT_FIELD, root: Path = FIELDS_DIR) -> dict[str, FieldDecl]:
    d = yaml.safe_load((root / field / "field.yaml").read_text())
    return {k: FieldDecl(k, v["kind"], v.get("ontology"), v.get("set", True), v.get("scope", ""), list(v.get("states", [])))
            for k, v in d["fields"].items()}


def field_config(field: str = DEFAULT_FIELD, root: Path = FIELDS_DIR) -> dict:
    return yaml.safe_load((root / field / "field.yaml").read_text())


def load_log(field: str = DEFAULT_FIELD, root: Path = FIELDS_DIR) -> list[dict]:
    p = root / field / "changes.yaml"
    return (yaml.safe_load(p.read_text()) or []) if p.exists() else []


def load_vocab(field: str = DEFAULT_FIELD, root: Path = FIELDS_DIR, ontology=None) -> Vocabulary:
    v = rebuild(load_fields(field, root), load_log(field, root), name=field)
    v.ontology = ontology
    v.measure_qualifiers = dict(field_config(field, root).get("measure_qualifiers") or {})
    return v


def rebuild(fields: dict[str, FieldDecl], log: list[dict], name: str = DEFAULT_FIELD) -> Vocabulary:
    v = Vocabulary(fields, name)
    for version in log:
        apply_version(v, version)
    return v


def _syn(s, field=None) -> dict:
    if isinstance(s, str):
        return {"text": s}
    d = {"text": s["text"]}
    if s.get("anchor"):
        d["anchor"] = s["anchor"]
    if field:
        d["field"] = field
    return d


def apply_version(v: Vocabulary, version: dict) -> None:
    added = {"paper": version.get("paper"), "version": version.get("version"), "agent": version.get("agent")}
    for ev in version.get("events", []):
        kind = ev["event"]
        body = {k: x for k, x in ev.items() if k != "event"}
        if kind == "add_term":
            v.terms[body["id"]] = Term(body["id"], [body["field"]], body["label"], body.get("parent"),
                                       body.get("definition", ""), body.get("scope"),
                                       [_syn(s) for s in body.get("synonyms", [])], body.get("qualifiers") or {},
                                       body.get("dimension"), body.get("xref") or [], "LivingLit", None, added)
        elif kind == "adopt":
            fdecl = v.fields[body["field"]]
            if body["id"] in v.terms:
                t = v.terms[body["id"]]
                if body["field"] not in t.fields:
                    t.fields.append(body["field"])
                t.synonyms += [_syn(s) for s in body.get("synonyms", [])]
            else:
                v.terms[body["id"]] = Term(body["id"], [body["field"]], body["label"], None,
                                           body.get("definition", ""), body.get("scope"),
                                           [_syn(s) for s in body.get("synonyms", [])], body.get("qualifiers") or {},
                                           None, [], fdecl.ontology or "ontology", body.get("lookup"), added)
        elif kind == "adopt_own":
            v.terms[body["id"]] = Term(body["id"], [body["field"]], body["label"], body.get("parent"),
                                       body.get("definition", ""), body.get("scope"),
                                       [_syn(s) for s in body.get("synonyms", [])], body.get("qualifiers") or {},
                                       None, body.get("xref") or [], "LivingLit", body.get("lookup"), added)
        elif kind == "add_synonym":
            v.terms[body["id"]].synonyms.append(_syn(body))
        elif kind == "set_scope":
            v.terms[body["id"]].scope = body["scope"]
        elif kind == "set_parent":
            v.terms[body["id"]].parent = body["parent"]
        elif kind == "add_xref":
            xs = body.get("xref") or ([body["value"]] if body.get("value") else [])
            for x in xs:
                if x not in v.terms[body["id"]].xref:
                    v.terms[body["id"]].xref.append(x)
        elif kind == "add_qualifier":
            v.terms[body["id"]].qualifiers[body["name"]] = {"dimension": body["dimension"]}
        elif kind == "add_field":
            v.fields[body["name"]] = FieldDecl(body["name"], body["kind"], body.get("ontology"), True, body.get("scope", ""))
        elif kind == "rename_field":  # a person's decision, logged (08, decision 25)
            old, new = body["old"], body["new"]
            if old in v.fields:
                d = v.fields.pop(old)
                v.fields.setdefault(new, FieldDecl(new, d.kind, d.ontology, d.set, d.scope, d.states))
            ren = lambda e: new + e[len(old):] if e == old or e.startswith(old + "@") else e
            for k in v.keys.values():
                for part in (k.value, k.direction):
                    part.must_match = [ren(e) for e in part.must_match]
                    part.may_vary = [ren(e) for e in part.may_vary]
            for term in v.terms.values():
                term.fields = [new if f == old else f for f in term.fields]
                for s in term.synonyms:
                    if s.get("field") == old:
                        s["field"] = new
        elif kind == "standing_key":
            v.keys[body["measure"]] = StandingKey(body["measure"], KeyPart(**body["value"]), KeyPart(**body["direction"]), added)
        else:
            raise ValueError(f"unknown event {kind!r}")
    if version.get("events"):
        v.version = max(v.version, int(version.get("version", v.version + 1)))


# -------------------------------------------------------------------- edit checks
def edit_kind(e: dict) -> tuple[str, dict]:
    if len(e) != 1:
        raise ValueError(f"an edit has exactly one kind, got {list(e)}")
    k = next(iter(e))
    return k, e[k]


def check_edits(vocab: Vocabulary, edits: list[dict], *, found, ontology, paper: str) -> list[str]:
    """Problems with a job's edits; [] means they may be appended to the log (03-vocabulary, How the vocabulary grows).

    `found(quote) -> bool` says whether a quote is in this paper's text; `ontology.check(id)` gives
    {label, obsolete} or None from the pinned releases.
    """
    import copy
    probs: list[str] = []
    v = copy.deepcopy(vocab)
    touched_parents: set = set()
    ever_ids = set(v.terms)

    def check_syn(tid, s, fld):
        text = s["text"] if isinstance(s, dict) else s
        anchor = s.get("anchor") if isinstance(s, dict) else None
        if any(c in normalize(text) for c in CANARIES):
            probs.append(f"{tid}: synonym {text!r} is a validation-study canary")
        if not anchor:
            probs.append(f"{tid}: synonym {text!r} has no anchor")
        elif normalize(text) not in normalize(anchor):
            probs.append(f"{tid}: synonym {text!r} is not inside its anchor {anchor!r}")
        elif not found(anchor):
            probs.append(f"{tid}: synonym {text!r} not found in {paper}'s text at its anchor")
        owner = v.lexicon(fld).get(normalize(text))
        if owner is not None:
            probs.append(f"{tid}: synonym {text!r} collides with {owner} in field {fld} (already a label or synonym)")

    for e in edits:
        try:
            kind, b = edit_kind(e)
        except ValueError as exc:
            probs.append(str(exc))
            continue
        fld = b.get("field")
        for x in b.get("xref") or []:  # xrefs into a pinned ontology must exist there (08 decision 34)
            info = ontology.check(x) if ontology is not None else None
            pre = x.split(":")[0]
            from .ontology import PREFIX as _PINNED
            if pre in _PINNED and ontology is not None:
                if info is None:
                    probs.append(f"{b.get('id')}: xref {x} is not in the pinned {_PINNED[pre]} release")
                elif info.get("obsolete"):
                    probs.append(f"{b.get('id')}: xref {x} is obsolete in the pinned {_PINNED[pre]} release")
        if kind in ("add_term", "adopt", "adopt_own"):
            if fld not in v.fields:
                probs.append(f"{b.get('id')}: field {fld!r} is not declared")
                continue
            decl = v.fields[fld]
            tid = b.get("id", "")
            label = b.get("label", "")
            if any(c in normalize(label) for c in CANARIES):
                probs.append(f"{tid}: label {label!r} is a validation-study canary")
            if kind == "adopt":
                if decl.kind != "adopted":
                    probs.append(f"{tid}: field {fld} is not an adopted field")
                    continue
                prefix = ONTOLOGY_PREFIX.get(decl.ontology or "", "")
                if not tid.startswith(prefix):
                    probs.append(f"{tid}: field {fld} adopts {decl.ontology} ids ({prefix}…)")
                    continue
                info = ontology.check(tid) if ontology is not None else None
                if info is None:
                    probs.append(f"{tid}: not in the pinned {decl.ontology} release")
                    continue
                if info.get("obsolete"):
                    probs.append(f"{tid}: obsolete in the pinned {decl.ontology} release")
                    continue
                if normalize(info["label"]) != normalize(label):
                    probs.append(f"{tid}: label {label!r} is not the ontology's label {info['label']!r}")
                if not b.get("lookup"):
                    probs.append(f"{tid}: adopt needs a lookup note")
                if tid in v.terms:
                    if fld in v.terms[tid].fields:
                        probs.append(f"{tid}: already adopted in {fld}")
                    for s in b.get("synonyms", []):
                        check_syn(tid, s, fld)
                    apply_version(v, {"version": v.version, "events": [{"event": "adopt", **b}]})
                    continue
                for s in b.get("synonyms", []):
                    check_syn(tid, s, fld)
                if normalize(label) in v.lexicon(fld):
                    probs.append(f"{tid}: label {label!r} collides with {v.lexicon(fld)[normalize(label)]}")
                apply_version(v, {"version": v.version, "events": [{"event": "adopt", **b}]})
                continue
            # own ids
            m = OWN_ID.match(tid)
            if not m or m.group(1) != fld:
                probs.append(f"{tid}: an own id is '{fld}:<slug>' with a lower-case slug [a-z0-9_]")
                continue
            if tid in ever_ids or tid in v.terms:
                probs.append(f"{tid}: id already used; ids are never reused")
                continue
            if kind == "add_term" and decl.kind == "adopted":
                probs.append(f"{tid}: field {fld} is adopted ({decl.ontology}); own terms go through adopt_own")
                continue
            if kind == "adopt_own" and decl.kind != "adopted":
                probs.append(f"{tid}: adopt_own is for adopted fields; use add_term")
                continue
            if kind == "adopt_own" and not (b.get("lookup") or "").strip():
                probs.append(f"{tid}: adopt_own needs a lookup note saying what was searched")
            if decl.kind == "quantity":
                probs.append(f"{tid}: field {fld} is a quantity and takes no terms")
                continue
            if not (b.get("definition") or "").strip():
                probs.append(f"{tid}: a term needs a definition")
            if normalize(label) in v.lexicon(fld):
                probs.append(f"{tid}: label {label!r} collides with {v.lexicon(fld)[normalize(label)]}")
            parent = b.get("parent")
            if parent is not None:
                pt = v.terms.get(parent)
                if pt is None or fld not in pt.fields:
                    probs.append(f"{tid}: parent {parent!r} does not exist in field {fld}")
                    continue
            if decl.kind == "measure" and not b.get("dimension"):
                probs.append(f"{tid}: a measure needs a dimension")
            for s in b.get("synonyms", []):
                check_syn(tid, s, fld)
            for qn, q in (b.get("qualifiers") or {}).items():
                if not isinstance(q, dict) or "dimension" not in q:
                    probs.append(f"{tid}: qualifier {qn} needs a dimension")
            apply_version(v, {"version": v.version, "events": [{"event": kind, **b}]})
            touched_parents.add((fld, parent))
        elif kind == "add_synonym":
            t = v.terms.get(b.get("id"))
            if t is None:
                probs.append(f"add_synonym: {b.get('id')!r} is not a term")
                continue
            fld = b.get("field") or t.field
            check_syn(t.id, b, fld)
            apply_version(v, {"version": v.version, "events": [{"event": "add_synonym", **b}]})
        elif kind == "set_scope":
            if b.get("id") not in v.terms or not (b.get("scope") or "").strip():
                probs.append(f"set_scope: {b.get('id')!r} is not a term or the scope is empty")
                continue
            apply_version(v, {"version": v.version, "events": [{"event": "set_scope", **b}]})
        elif kind == "add_qualifier":
            if b.get("id") not in v.terms or not b.get("dimension") or not b.get("name"):
                probs.append(f"add_qualifier: needs an existing id, a name and a dimension")
                continue
            apply_version(v, {"version": v.version, "events": [{"event": "add_qualifier", **b}]})
        elif kind == "add_field":
            if b.get("name") in v.fields or b.get("kind") not in ("terms", "adopted", "quantity"):
                probs.append(f"add_field: {b.get('name')!r} exists or kind is not terms/adopted/quantity")
                continue
            if not (b.get("scope") or "").strip():
                probs.append(f"add_field: {b.get('name')!r} needs a scope note saying what belongs there")
            apply_version(v, {"version": v.version, "events": [{"event": "add_field", **b}]})
        elif kind == "standing_key":
            probs += check_key(v, b)
            if not any(p.startswith("standing key") for p in probs):
                apply_version(v, {"version": v.version, "events": [{"event": "standing_key", **b}]})
        else:
            probs.append(f"unknown edit kind {kind!r}")

    # scope when a term has siblings, for every family this job touched
    for fld, parent in touched_parents:
        sibs = [t for t in v.field_terms(fld).values() if t.parent == parent and not t.adopted]
        if len(sibs) > 1:
            for t in sibs:
                if not (t.scope or "").strip():
                    probs.append(f"{t.id}: needs a scope note against its siblings "
                                 f"({', '.join(s.id for s in sibs if s.id != t.id)})")
    return probs


def check_key(v: Vocabulary, b: dict) -> list[str]:
    out = []
    m = b.get("measure")
    if m not in v.terms or "measure" not in v.terms[m].fields:
        out.append(f"standing key: {m!r} is not a measure term")
        return out
    for part in ("value", "direction"):
        p = b.get(part) or {}
        if "must_match" not in p:
            out.append(f"standing key {m}: {part} needs must_match")
            continue
        for entry in list(p.get("must_match", [])) + list(p.get("may_vary", [])):
            name, _, level = entry.partition("@")
            if name.startswith("measure."):
                q = name.split(".", 1)[1]
                declared = set()
                for a in [m, *v.ancestors(m)]:
                    if a in v.terms:
                        declared |= set(v.terms[a].qualifiers)
                if q not in declared and q not in ("method", "software", "definition") and q not in v.measure_qualifiers:
                    out.append(f"standing key {m}: measure qualifier {q!r} is not declared on the measure")
                continue
            if name in KEY_SPECIALS:
                continue
            if name not in v.fields:
                out.append(f"standing key {m}: field {name!r} does not exist")
                continue
            if level:
                if level.startswith("under:"):
                    anc = level[6:]
                    if anc not in v.terms and not (v.ontology and v.ontology.check(anc)):
                        out.append(f"standing key {m}: ancestor class {anc!r} not found")
                elif not level.isdigit() or int(level) < 1:
                    out.append(f"standing key {m}: level {level!r} is not a positive integer")
                elif v.fields[name].kind == "adopted":
                    out.append(f"standing key {m}: adopted field {name} uses @under:<class>, not a level")
    return out


def save_vocab(v: Vocabulary, field: str = DEFAULT_FIELD, root: Path = FIELDS_DIR) -> None:
    (root / field / "vocab.yaml").write_text(
        "# Rebuilt by code from field.yaml and changes.yaml; never edited (03-vocabulary).\n"
        + yaml.safe_dump(v.to_yaml(), sort_keys=False, allow_unicode=True, width=120))


def append_version(edits: list[dict], paper: str, agent: dict | None, field: str = DEFAULT_FIELD,
                   root: Path = FIELDS_DIR) -> int | None:
    """Append accepted edits as one version; an apply with nothing new adds no version (07-building)."""
    log = load_log(field, root)
    if not edits:
        return None
    version = (log[-1]["version"] if log else 0) + 1
    events = []
    for e in edits:
        k, b = edit_kind(e)
        events.append({"event": k, **b})
    log.append({"version": version, "paper": paper, "agent": agent, "events": events})
    (root / field / "changes.yaml").write_text(
        "# Append-only log of accepted vocabulary edits (03-vocabulary). vocab.yaml is rebuilt from it.\n"
        + yaml.safe_dump(log, sort_keys=False, allow_unicode=True, width=120))
    return version


EXTERNAL_XREF_PATTERNS = {
    "FlyBase": re.compile(r"^FlyBase:FBgn\d{7}$"),
    "NCBI_Gene": re.compile(r"^NCBI_Gene:(?:LOC)?\d+$"),
    "OrthoDB": re.compile(r"^OrthoDB:[A-Za-z0-9_.-]+$"),
    "GO": re.compile(r"^GO:\d{7}$"),
    "UniProt": re.compile(r"^UniProt:[A-Z0-9_-]+$"),
}


def recheck_ontology(vocab, ontology) -> list[str]:
    """Every adopted id and every own term's xref against the pinned ontology releases (or validated external gene
    database CURIE formats): missing, malformed, or obsolete ones are listed. Run on every release."""
    probs = []
    for tid, t in sorted(vocab.terms.items()):
        if t.adopted:
            info = ontology.check(tid)
            if info is None:
                probs.append(f"{tid} (adopted id) is not in the pinned release")
            elif info.get("obsolete"):
                probs.append(f"{tid} (adopted id) is obsolete in the pinned {info.get('release')} release")
        for oid in t.xref:
            what = f"xref of {tid}"
            pre = oid.split(":", 1)[0] if ":" in oid else ""
            if pre in EXTERNAL_XREF_PATTERNS:
                if not EXTERNAL_XREF_PATTERNS[pre].match(oid):
                    probs.append(f"{oid} ({what}) has invalid {pre} identifier format")
                continue
            info = ontology.check(oid)
            if info is None:
                probs.append(f"{oid} ({what}) is not in the pinned release")
            elif info.get("obsolete"):
                probs.append(f"{oid} ({what}) is obsolete in the pinned {info.get('release')} release")
    return probs

