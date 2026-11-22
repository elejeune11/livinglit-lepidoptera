"""The record job's gate and the figures-and-data job's gate (07-building, Jobs; 02-audit).

Record: schema, anchors found, ids, units and groups, context resolution (every
field filled or 'not stated'), quotes at most 30 words.
Figures and data: every script and every cell reproduces what is stored.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from . import PAPERS_DIR, RECORDS_DIR
from .data import check_rows, read_cell
from .figures.run import run_figure, compare_readings
from .models import Record, FiguresFile, ReadingsFile, DataFile, Anchor, ByReference, ContextObj
from .record import structure_problems, resolve_context, load_yaml, BENCHMARK_STATE
from .text import find_quote, source_files, SourceUnavailable, normalize

MAX_WORDS = 30


def _anchors(rec: Record):
    for iid, it in rec.evidence.items():
        yield f"evidence.{iid}.anchor", it.anchor
        if isinstance(it.definition, ByReference):
            yield f"evidence.{iid}.definition", it.definition.anchor
        if it.stated_direction:
            yield f"evidence.{iid}.stated_direction", it.stated_direction.anchor
        if it.scaling:
            yield f"evidence.{iid}.scaling", it.scaling.anchor
    for uid, u in rec.units.items():
        if u.anchor:
            yield f"units.{uid}.anchor", u.anchor
        for gid, g in u.groups.items():
            if g.anchor:
                yield f"units.{uid}.groups.{gid}.anchor", g.anchor
    for cid, c in rec.claims.items():
        yield f"claims.{cid}.quote", Anchor(quote=c.quote, where=c.where)
    for cid, c in rec.citations.items():
        yield f"citations.{cid}.anchor", c.anchor
    for i, x in enumerate(rec.cross_references):
        yield f"cross_references[{i}].anchor", x.anchor
    for i, ca in enumerate(rec.context_anchors):
        yield f"context_anchors[{i}] ({ca.field}: {ca.value})", ca.anchor
    for uid, u in rec.units.items():
        for i, oc in enumerate(u.other_conditions):
            yield f"units.{uid}.other_conditions[{i}]", oc.anchor
        for gid, g in u.groups.items():
            for i, oc in enumerate(g.other_conditions):
                yield f"units.{uid}.groups.{gid}.other_conditions[{i}]", oc.anchor
    from .record import all_context_values
    for at, f, v in all_context_values(rec):
        if isinstance(v, ContextObj):
            if v.anchor:
                yield f"{at}.anchor", v.anchor
            if v.by_reference:
                yield f"{at}.by_reference", v.by_reference.anchor


def check_anchor(a: Anchor, paper_dir: Path, rec: Record) -> str | None:
    if len(a.quote.split()) > MAX_WORDS:
        return f"quote has {len(a.quote.split())} words; at most {MAX_WORDS}"
    if a.kind == "unit":
        return None  # values inside an image, anchored to their unit
    if a.kind == "dataset cell":
        try:
            file, sheet, cell = a.quote.split("!")
            return None if read_cell(paper_dir, file, sheet or None, cell) != "" else f"dataset cell {a.quote} is empty"
        except Exception as e:
            return f"dataset cell anchor {a.quote!r}: {e} (write it as file!sheet!B7)"
    files = [a.file] if a.file else None
    try:
        if find_quote(a.quote, paper_dir, files) is None:
            return f"quote not found{' in ' + a.file if a.file else ''}: {a.quote!r}"
    except SourceUnavailable as e:
        return str(e)
    return None


ANCHORS_FROM_FIELD_SET = 3  # context anchors are required from field set 3 (02-audit, Context is anchored too)
_WORD = re.compile(r"[^\W_]+(?:[.,][0-9]+)*", re.UNICODE)


def holds(quote: str, value: str) -> bool:
    """Every word and number of the value appears in the quote (normalized)."""
    q = normalize(quote)
    return all(normalize(w) in q for w in _WORD.findall(value) if normalize(w))


def stated_context_values(rec: Record, field_cfg: dict) -> dict[tuple[str, str], str]:
    """Distinct (field, wording) pairs that need an anchor, with one place each is used."""
    from .record import all_context_values
    named = set(field_cfg.get("named_states", [])) | {"not stated", "not applicable", "none", BENCHMARK_STATE}
    out = {}
    for at, f, v in all_context_values(rec):
        states = named | set((field_cfg["fields"].get(f) or {}).get("states", []))
        if isinstance(v, ContextObj):
            if v.by_reference is not None:
                continue
            for q, qv in v.qualifiers.items():
                if qv not in states:
                    out.setdefault((f"{f}.{q}", qv), at)
            if v.anchor is not None or v.value in states:
                continue
            out.setdefault((f, v.value), at)
        elif v not in states:
            out.setdefault((f, v), at)
    return out


def context_anchor_problems(rec: Record, field_cfg: dict) -> list[str]:
    probs = []
    have = {(ca.field, ca.value): ca for ca in rec.context_anchors}
    if rec.field_set >= ANCHORS_FROM_FIELD_SET:
        for (f, val), at in stated_context_values(rec, field_cfg).items():
            if (f, val) not in have:
                probs.append(f"{at}: {f} {val!r} has no anchor in context_anchors (02-audit, Context is anchored too)")
    for (f, val), ca in have.items():
        if not holds(ca.anchor.quote, val):
            probs.append(f"context_anchors ({f}: {val!r}): the quote does not hold the value's words")
    for uid, u in rec.units.items():
        ocs = [(f"units.{uid}.other_conditions", u.other_conditions)] + \
              [(f"units.{uid}.groups.{gid}.other_conditions", g.other_conditions) for gid, g in u.groups.items()]
        for at, lst in ocs:
            for i, oc in enumerate(lst):
                if not holds(oc.anchor.quote, oc.text):
                    probs.append(f"{at}[{i}] ({oc.text!r}): the quote does not hold the condition's words")
    return probs


DATA_TABLE_SUFFIXES = (".xlsx", ".xlsm", ".xls", ".xlsb", ".csv", ".tsv", ".docx")


def files_used(rec: Record, data_rows=()) -> set[str]:
    """Files some value or anchor of the record comes from."""
    used = {r.file for r in data_rows}
    for _, a in _anchors(rec):
        if a.file:
            used.add(a.file)
        if a.kind == "dataset cell":
            used.add(a.quote.split("!")[0])
    for it in rec.evidence.values():
        for v in it.values.values():
            if v.data:
                used.add(v.data.file)
        if it.n != "not stated" and it.n.data:
            used.add(it.n.data.file)
    return used


def unread_files(rec: Record, paper_dir: Path) -> list[str]:
    """Files in the paper's folder that are neither in source.files nor in source.not_used (folders skipped)."""
    known = set(rec.source.files) | {n.file for n in rec.source.not_used}
    if not paper_dir.is_dir():
        return []
    return sorted(f.name for f in paper_dir.iterdir() if f.is_file() and not f.name.startswith(".") and f.name not in known)


def unused_data_files(rec: Record, data_rows=()) -> list[str]:
    """Data and table files the record lists that feed no value and are not explained in source.not_used."""
    used = files_used(rec, data_rows)
    explained = {n.file for n in rec.source.not_used}
    return sorted(f for f in rec.source.files if Path(f).suffix.lower() in DATA_TABLE_SUFFIXES
                  and f not in used and f not in explained)


def context_fields(field_cfg: dict) -> list[str]:
    return [k for k, v in field_cfg["fields"].items() if v["kind"] != "measure"]


def check_record(raw: dict, paper_dir: Path, field_cfg: dict, check_text: bool = True) -> tuple[Record | None, list[str]]:
    try:
        rec = Record.model_validate(raw)
    except ValidationError as e:
        return None, [f"schema: {err['loc']}: {err['msg']}" for err in e.errors()]
    probs = structure_problems(rec)
    declared = set(field_cfg["fields"])
    from .record import all_context_values
    for at, f, v in all_context_values(rec):
        if f not in declared:
            probs.append(f"{at}: {f!r} is not a field of the vocabulary (fields/<field>/field.yaml)")
    needed = [f for f in context_fields(field_cfg) if f in declared
              and int(field_cfg["fields"][f].get("since", 1)) <= rec.field_set]  # later fields: not yet read
    for iid, it in rec.evidence.items():
        if it.unit not in rec.units:
            continue
        for g in it.group_ids() or [None]:
            if g and g in rec.units[it.unit].groups and rec.units[it.unit].groups[g].benchmark:
                continue  # code supplies 'not stated in this source' (02-audit, Groups)
            ctx = resolve_context(rec, iid, g)
            missing = [f for f in needed if f not in ctx]
            if missing:
                probs.append(f"evidence.{iid}{'/' + g if g else ''}: context fields neither filled nor 'not stated': "
                             f"{', '.join(missing)}")
                break
    probs += context_anchor_problems(rec, field_cfg)
    for cid, c in rec.citations.items():
        if not c.purpose:
            probs.append(f"citations.{cid}: needs a purpose")
    if check_text:
        if not source_files(paper_dir):
            probs.append(f"no source text files in {paper_dir}")
        else:
            for f in rec.source.files:
                if not (paper_dir / f).is_file():
                    probs.append(f"source.files: {f} is not in the paper's folder")
            for f in unread_files(rec, paper_dir):
                probs.append(f"{f}: in the paper's folder but not read (list it in source.files, or in source.not_used "
                             f"with what it holds)")
            for where, a in _anchors(rec):
                p = check_anchor(a, paper_dir, rec)
                if p:
                    probs.append(f"{where}: {p}")
    # Validate manifest.yaml (OA policy & schema) when present
    mpath = RECORDS_DIR / rec.id / "manifest.yaml"
    if mpath.is_file():
        from .models import Manifest
        try:
            mf = Manifest.model_validate(load_yaml(mpath))
            if (field_cfg.get("policy") or {}).get("oa_only") and mf.oa_status != "open_access":
                probs.append(f"manifest.yaml: oa_status={mf.oa_status!r} rejected under policy.oa_only=true")
        except ValidationError as e:
            probs.extend(f"manifest.yaml: {err['loc']}: {err['msg']}" for err in e.errors())
    return rec, probs


def check_figures_and_data(rec: Record, record_dir: Path, paper_dir: Path, rerun: bool = True) -> list[str]:
    probs = []
    figs = FiguresFile()
    stored = ReadingsFile()
    data = DataFile()
    try:
        if (record_dir / "figures.yaml").exists():
            figs = FiguresFile.model_validate(load_yaml(record_dir / "figures.yaml"))
        if (record_dir / "readings.yaml").exists():
            stored = ReadingsFile.model_validate(load_yaml(record_dir / "readings.yaml"))
        if (record_dir / "data.yaml").exists():
            data = DataFile.model_validate(load_yaml(record_dir / "data.yaml"))
    except ValidationError as e:
        return [f"schema: {err['loc']}: {err['msg']}" for err in e.errors()]
    for fid, f in figs.figures.items():
        if f.unit not in rec.units:
            probs.append(f"figures.{fid}: unit {f.unit!r} is not a unit")
        for label, gl in f.groups.items():
            it = rec.evidence.get(gl.item)
            if it is None:
                probs.append(f"figures.{fid}.{label}: item {gl.item!r} is not an evidence item")
                continue
            if gl.group not in rec.units[it.unit].groups and gl.group != "_":
                probs.append(f"figures.{fid}.{label}: group {gl.group!r} is not a group of unit {it.unit}")
            if it.unit != f.unit:
                probs.append(f"figures.{fid}.{label}: item {gl.item} is in unit {it.unit}, the figure in {f.unit}")
        if not f.script.startswith("figures/") or not f.script.endswith(".py"):
            probs.append(f"figures.{fid}: script must be figures/<name>.py")
    for uid, why in figs.no_points.items():
        if uid not in rec.units:
            probs.append(f"no_points.{uid}: not a unit")
        elif not why.strip():
            probs.append(f"no_points.{uid}: say what the figure shows instead of points")
    fresh = []
    if rerun:
        for fid, f in figs.figures.items():
            rows, errs = run_figure(fid, f, record_dir, paper_dir)
            fresh += rows
            probs += errs
        probs += compare_readings(stored.readings, fresh)
    for r in stored.readings:
        if r.figure not in figs.figures:
            probs.append(f"readings: figure {r.figure!r} is not in figures.yaml")
    for i, r in enumerate(data.data):
        it = rec.evidence.get(r.item)
        if it is None:
            probs.append(f"data[{i}]: item {r.item!r} is not an evidence item")
        elif r.group not in rec.units[it.unit].groups and r.group != "_":
            probs.append(f"data[{i}]: group {r.group!r} is not a group of unit {it.unit}")
    probs += check_rows(data.data, paper_dir)
    for f in unused_data_files(rec, data.data):
        probs.append(f"{f}: a data or table file that feeds no value; take the values from it (data.yaml rows or "
                     f"anchors), or list it in source.not_used with what it holds")
    return probs


def load_record_files(paper: str, records_dir: Path = RECORDS_DIR):
    d = records_dir / paper
    rec = Record.model_validate(load_yaml(d / "record.yaml"))
    figs = FiguresFile.model_validate(load_yaml(d / "figures.yaml")) if (d / "figures.yaml").exists() else FiguresFile()
    rd = ReadingsFile.model_validate(load_yaml(d / "readings.yaml")) if (d / "readings.yaml").exists() else ReadingsFile()
    data = DataFile.model_validate(load_yaml(d / "data.yaml")) if (d / "data.yaml").exists() else DataFile()
    return rec, figs, rd, data
