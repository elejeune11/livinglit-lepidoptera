"""Loading a record, value paths, context resolution and structural rules (02-audit)."""
from __future__ import annotations

from pathlib import Path

import yaml

from .models import Record, stated_text, Sides

BENCHMARK_STATE = "not stated in this source"  # a benchmark group's field it does not state (02-audit, Groups)


def load_yaml(path: Path):
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_record(path: Path) -> Record:
    return Record.model_validate(load_yaml(path))


def value_at(rec: Record, path: str):
    """'<item>.values.<name>' → the Value; '<item>.n' → the N."""
    parts = path.split(".")
    item = rec.evidence[parts[0]]
    if len(parts) == 2 and parts[1] == "n":
        return item.n
    if len(parts) != 3 or parts[1] != "values":
        raise KeyError(f"value path {path!r} is not <item>.values.<name>")
    return item.values[parts[2]]


def resolve_context(rec: Record, item_id: str, group: str | None = None) -> dict:
    """default → unit → group → item (02-audit, Context per unit). Never stored."""
    item = rec.evidence[item_id]
    unit = rec.units[item.unit]
    if group and group in unit.groups:
        ctx = group_context(rec, item.unit, group)
    else:
        ctx = dict(rec.default_context)
        ctx.update(unit.context)
    ctx.update(item.context)
    return ctx


def group_context(rec: Record, unit_id: str, group: str) -> dict:
    """default → unit → group; a native-tissue or other-study group resolves only its own context (02-audit, Groups)."""
    unit = rec.units[unit_id]
    g = unit.groups[group]
    if g.benchmark:
        return dict(g.context)
    ctx = dict(rec.default_context)
    ctx.update(unit.context)
    ctx.update(g.context)
    return ctx


def structure_problems(rec: Record) -> list[str]:
    """Rules on the record's structure that need no paper text."""
    out = []
    for f in rec.default_context:
        for uid, u in rec.units.items():
            if f in u.context:
                out.append(f"default_context.{f} is also set in unit {uid}: a field that differs between units is "
                           f"written in each unit, not the default (02-audit, Context per unit; decision 13)")
            for gid, g in u.groups.items():
                if f in g.context and not g.benchmark:
                    out.append(f"default_context.{f} is also set in group {uid}/{gid} (02-audit, Groups)")
    for uid, u in rec.units.items():
        for gid, g in u.groups.items():
            if g.benchmark:
                if g.citation and g.citation not in rec.citations:
                    out.append(f"group {uid}/{gid} cites {g.citation!r}, which is not in citations")
                continue
            for f in g.context:
                if f in u.context:
                    out.append(f"units.{uid}.context.{f} is also set in its group {gid}: a group's context holds "
                               f"what sets it apart; leave the field out of the unit (02-audit, Groups)")
            if g.citation and g.citation not in rec.citations:
                out.append(f"group {uid}/{gid} cites {g.citation!r}, which is not in citations")
    for iid, it in rec.evidence.items():
        if it.unit not in rec.units:
            out.append(f"evidence.{iid}.unit {it.unit!r} is not a unit")
            continue
        unit_groups = set(rec.units[it.unit].groups)
        named = it.group_ids()
        for g in named:
            if g not in unit_groups:
                out.append(f"evidence.{iid} names group {g!r}, not a group of unit {it.unit}")
        if isinstance(it.compares, Sides) and set(it.compares.condition) & set(it.compares.reference):
            out.append(f"evidence.{iid}: a group is on both sides of the main effect")
        for vn, v in it.values.items():
            for g in ([v.group] if v.group else []) + (v.between or []) + (v.over or []):
                if g not in unit_groups:
                    out.append(f"evidence.{iid}.values.{vn} names group {g!r}, not a group of unit {it.unit}")
                elif named and g not in named:
                    out.append(f"evidence.{iid}.values.{vn} names group {g!r}, which the item does not involve")
        if it.n != "not stated" and it.n.per_group:
            for g in it.n.per_group:
                if g not in unit_groups:
                    out.append(f"evidence.{iid}.n.per_group names {g!r}, not a group of unit {it.unit}")
        if it.n != "not stated" and it.n.origin == "from data" and it.n.data is None:
            out.append(f"evidence.{iid}.n has origin 'from data' without a data pointer")
        for vn, v in it.values.items():
            if v.origin == "from data" and v.data is None:
                out.append(f"evidence.{iid}.values.{vn} has origin 'from data' without a data pointer")
        if unit_groups and not named:
            pass
    for cid, c in rec.claims.items():
        for ref in c.rests_on + c.opposes:
            if ref not in rec.evidence:
                out.append(f"claims.{cid} rests on or opposes {ref!r}, not an evidence item")
        if c.restates and c.restates not in rec.claims:
            out.append(f"claims.{cid}.restates {c.restates!r} is not a claim")
        for ref in c.cites:
            if ref not in rec.citations:
                out.append(f"claims.{cid} cites {ref!r}, not a citation")
        if c.kind == "attributed" and c.judgement is not None:
            out.append(f"claims.{cid}: an attributed claim rests on nothing in this source and is not judged")
    return out


def all_context_values(rec: Record):
    """Every stated context value with its location: (at, field, value)."""
    for f, v in rec.default_context.items():
        yield f"default_context.{f}", f, v
    for uid, u in rec.units.items():
        for f, v in u.context.items():
            yield f"units.{uid}.context.{f}", f, v
        for gid, g in u.groups.items():
            for f, v in g.context.items():
                yield f"units.{uid}.groups.{gid}.context.{f}", f, v
    for iid, it in rec.evidence.items():
        for f, v in it.context.items():
            yield f"evidence.{iid}.context.{f}", f, v


__all__ = ["load_record", "value_at", "resolve_context", "structure_problems", "all_context_values", "stated_text",
           "BENCHMARK_STATE"]
