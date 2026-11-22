"""The formula job's gate (04-formulas, The formula agent; 07-building, Jobs).

Derivations anchored, inputs resolvable, library formulas exist, assumption
reports name the model's assumptions, proposals checked. A failing proposal is
reported; the step it was for is marked no formula applies.
"""
from __future__ import annotations

from .formulas import check_entry, Library, parse_rel, symtab
from .models import DerivedFile, Record, FormulaEntry
from .record import value_at


def check_derived(rec: Record, df: DerivedFile, lib: Library, *, found, vocab=None, data_rows=(), readings=(),
                  figures=None) -> tuple[list[str], list[str]]:
    """(problems, rejected proposals)."""
    probs, rejected = [], []
    if df.record != rec.id:
        probs.append(f"derived.yaml names record {df.record!r}, not {rec.id!r}")
    work = Library(dict(lib.entries), lib.version, lib.suspect)
    for p in df.proposals:
        if p.formula in lib.entries and lib.entries[p.formula].equations == p.equations:
            continue  # already applied from this file: a re-run checks derivations, not the edits again (07-building)
        errs = check_entry(p, work, vocab)
        if errs:
            rejected += errs
        else:
            work.entries[p.formula] = p
    data_keys = {f"{r.item}/{r.group}" for r in data_rows}
    read_keys = {f"{r.figure}/{r.group}" for r in readings}
    read_x = {}
    for r in readings:
        read_x.setdefault(f"{r.figure}/{r.group}", set()).add(r.x)
    for key, d in df.derived.items():
        if d.item not in rec.evidence:
            probs.append(f"derived.{key}: item {d.item!r} is not an evidence item")
            continue
        if d.group is not None and d.group not in rec.units[rec.evidence[d.item].unit].groups:
            probs.append(f"derived.{key}: group {d.group!r} is not a group of unit {rec.evidence[d.item].unit}")
        if d.anchor != "not stated":
            if len(d.anchor.quote.split()) > 30:
                probs.append(f"derived.{key}: anchor longer than 30 words")
            elif not found(d.anchor.quote):
                probs.append(f"derived.{key}: anchor not found: {d.anchor.quote!r}")
        if d.library:
            e = work.get(d.library.formula)
            if e is None:
                probs.append(f"derived.{key}: library formula {d.library.formula!r} is not in the library"
                             + (" (its proposal was rejected: use no_formula)" if any(x.formula == d.library.formula for x in df.proposals) else ""))
            else:
                bad = set(d.library.vars) - set(e.variables)
                if bad:
                    probs.append(f"derived.{key}: {sorted(bad)} are not variables of {e.formula}")
        if d.formula.strip() != "not stated":
            if "=" not in d.formula:
                probs.append(f"derived.{key}: write the formula as an equation 'output = expression'")
            else:
                try:
                    names = set(d.inputs) | {d.formula.split("=")[0].strip()}
                    lhs, op, rhs = parse_rel(d.formula, symtab(names))
                    extra = {str(s) for s in (lhs - rhs).free_symbols} - names
                    if extra:
                        probs.append(f"derived.{key}: formula names {sorted(extra)} that are not inputs")
                except Exception as ex:
                    probs.append(f"derived.{key}: cannot parse formula ({ex})")
        for n, i in d.inputs.items():
            where = f"derived.{key}.inputs.{n}"
            if i.value:
                try:
                    value_at(rec, i.value)
                except KeyError:
                    probs.append(f"{where}: value path {i.value!r} does not resolve")
            if i.item and i.item not in rec.evidence:
                probs.append(f"{where}: item {i.item!r} is not an evidence item")
            if i.data and i.data not in data_keys:
                probs.append(f"{where}: no data rows {i.data!r}")
            if i.reading and i.reading not in read_keys:
                probs.append(f"{where}: no readings {i.reading!r}")
            elif i.reading and i.x is None and None not in read_x.get(i.reading, {None}):
                probs.append(f"{where}: readings {i.reading!r} are a curve (every point has x): give the input's x")
            if i.derived and i.derived not in df.derived:
                probs.append(f"{where}: no derivation {i.derived!r}")
            if i.printed is not None and i.anchor is not None and not found(i.anchor.quote):
                probs.append(f"{where}: anchor not found: {i.anchor.quote!r}")
            if i.by_reference is not None and i.by_reference.citation not in rec.citations:
                probs.append(f"{where}: citation {i.by_reference.citation!r} is not in the record")
        if d.output:
            try:
                value_at(rec, d.output)
            except KeyError:
                probs.append(f"derived.{key}: output {d.output!r} does not resolve")
    for key, rep in df.assumptions.items():
        e = work.get(rep.model)
        if e is None:
            probs.append(f"assumptions.{key}: model {rep.model!r} is not in the library")
            continue
        known = set(work.holds_under(rep.model)) | set(e.assumes)
        for a, r in rep.assumptions.items():
            if a not in known:
                probs.append(f"assumptions.{key}: {a!r} is not an assumption of {rep.model} ({sorted(known)})")
            if not isinstance(r, dict) or "reported" not in r:
                probs.append(f"assumptions.{key}.{a}: needs reported: <values or 'not stated'>")
            elif r["reported"] != "not stated" and isinstance(r["reported"], dict):
                for vn, path in r["reported"].items():
                    try:
                        value_at(rec, path)
                    except (KeyError, TypeError):
                        if not (isinstance(path, str) and found(path)):
                            probs.append(f"assumptions.{key}.{a}: {vn} {path!r} is neither a value path nor a quote found in the paper")
    for b in df.bounds:
        e = work.get(b.formula)
        if e is None or e.kind != "bound":
            probs.append(f"bounds: {b.formula!r} is not a bound entry")
        try:
            value_at(rec, b.value)
        except KeyError:
            probs.append(f"bounds: value {b.value!r} does not resolve")
    if not df.derived and not df.bounds and not df.reason_if_empty:
        probs.append("an empty derived.yaml gives reason_if_empty")
    return probs, rejected
