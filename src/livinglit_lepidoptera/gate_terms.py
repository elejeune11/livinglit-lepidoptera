"""The vocabulary job's gate (03-vocabulary, How the vocabulary grows; 07-building, Jobs).

Mapping complete, flags respected, edits anchored and checked. The orchestrator's
re-run after apply checks the mappings against the current vocabulary, not the
edits again (07-building, What the first build taught about the code).
"""
from __future__ import annotations

from .mapping import occurrences, map_occurrence, named_state
from .models import Record, TermsFile
from .text import normalize
from .vocab import check_edits, apply_version, edit_kind
import copy


def pending_edits(edits: list[dict], log: list[dict], paper: str) -> list[dict]:
    """Edits of this paper's terms.yaml that are not yet in the log under this paper: a re-map adds to what was applied
    before (03-vocabulary, Earlier papers)."""
    import json
    from .vocab import edit_kind
    done = {json.dumps({"event": ev["event"], **{k: v for k, v in ev.items() if k != "event"}}, sort_keys=True, default=str)
            for ver in log if ver.get("paper") == paper for ev in ver.get("events", [])}
    out = []
    for e in edits:
        k, b = edit_kind(e)
        if json.dumps({"event": k, **b}, sort_keys=True, default=str) not in done:
            out.append(e)
    return out


def check_terms(vocab, rec: Record, tf: TermsFile, *, found, ontology, check_edits_too: bool = True,
                anchor_of=None) -> list[str]:
    probs = []
    if tf.record != rec.id:
        probs.append(f"terms.yaml names record {tf.record!r}, not {rec.id!r}")
    v = vocab
    edits = tf.edits
    if anchor_of is not None:  # anchors given as record paths ("evidence.E08.anchor") become their quotes
        edits = resolve_anchor_paths(edits, anchor_of)
    if check_edits_too and edits:
        probs += check_edits(vocab, edits, found=found, ontology=ontology, paper=rec.id)
        v = copy.deepcopy(vocab)
        try:
            apply_version(v, {"version": vocab.version + 1, "paper": rec.id,
                              "events": [{"event": edit_kind(e)[0], **edit_kind(e)[1]} for e in edits]})
        except Exception as exc:  # malformed edits already reported
            probs.append(f"edits could not be applied: {exc}")
            return probs
    occs = occurrences(rec)
    stated = {(o.field, normalize(o.text)) for o in occs if o.text}
    seen = set()
    for m in tf.mappings:
        key = (m.field, normalize(m.stated))
        if key in seen:
            probs.append(f"{m.field} {m.stated!r} is mapped twice; identical stated text is mapped once")
        seen.add(key)
        if key not in stated:
            probs.append(f"{m.field} {m.stated!r} is not a stated value of this record")
            continue
        if m.field not in v.fields:
            probs.append(f"{m.stated!r}: field {m.field!r} is not declared")
            continue
        for t in m.terms:
            if t not in v.terms or m.field not in v.terms[t].fields:
                probs.append(f"{m.field} {m.stated!r}: term {t!r} is not a term of field {m.field}")
        if not m.flag and not m.terms:
            probs.append(f"{m.field} {m.stated!r}: neither terms nor a flag")
        for qn in m.qualifiers:
            declared = set()
            for t in m.terms:
                for a in [t, *v.ancestors(t)]:
                    if a in v.terms:
                        declared |= set(v.terms[a].qualifiers)
            if m.field == "measure" and qn in v.measure_qualifiers:
                allowed = v.measure_qualifiers[qn]
                if allowed and m.qualifiers[qn] not in allowed:
                    probs.append(f"measure {m.stated!r}: {qn} {m.qualifiers[qn]!r} is not one of {allowed} "
                                 f"(03-vocabulary, Relative measures)")
                continue
            if qn not in declared:
                probs.append(f"{m.field} {m.stated!r}: qualifier {qn!r} is not declared on its terms "
                             f"(add it with add_qualifier)")
        for s in m.split:
            if s.field not in v.fields:
                probs.append(f"{m.stated!r}: split request names field {s.field!r}, not declared")
        if normalize(m.stated) in {normalize(x) for x in getattr(v.fields[m.field], "states", [])}:
            probs.append(f"{m.field} {m.stated!r}: a declared state of the field; code matches it, so it is neither "
                         f"mapped nor flagged")
        # a value code matches is never stored
        if not m.flag and v.fields[m.field].kind != "quantity":
            from .matching import match_text
            mm = match_text(v, m.field, m.stated)
            if mm.terms and set(mm.terms) == set(m.terms) and not m.qualifiers:
                probs.append(f"{m.field} {m.stated!r}: code matches this value; remove the stored mapping "
                             f"(matches are never stored)")
    assigned = {(m.field, normalize(m.stated)): m for m in tf.mappings}
    for o in occs:
        if o.field not in v.fields:
            probs.append(f"{o.at}: field {o.field!r} is not declared in the field's vocabulary")
            continue
        res = map_occurrence(v, o, assigned)
        if res.origin == "unmapped":
            probs.append(f"{o.at}: {o.field} {o.text!r} is neither matched by code nor mapped or flagged")
    return probs


def resolve_anchor_paths(edits: list[dict], anchor_of) -> list[dict]:
    out = []
    for e in edits:
        e = copy.deepcopy(e)
        k, b = edit_kind(e)
        syns = b.get("synonyms", []) if k in ("add_term", "adopt", "adopt_own") else ([b] if k == "add_synonym" else [])
        for s in syns:
            if isinstance(s, dict) and isinstance(s.get("anchor"), str) and s["anchor"].count(".") >= 1 \
                    and s["anchor"].split(".")[0] in ("evidence", "units", "default_context", "claims", "citations"):
                q = anchor_of(s["anchor"])
                if q:
                    s["anchor"] = q
        out.append(e)
    return out


def flag_counts(tf: TermsFile) -> dict:
    out: dict = {}
    for m in tf.mappings:
        if m.flag:
            out[m.flag.kind] = out.get(m.flag.kind, 0) + 1
    out["split requests"] = sum(len(m.split) for m in tf.mappings)
    return out
