"""Contrasts computed from groups (02-audit, Groups; What code computes; 08 decision 15).

The reader never writes what varies. Code compares the compared groups'
resolved contexts field by field, on signatures: mapped terms and qualifiers
when a mapping exists, otherwise the normalized stated text (labelled).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from .models import Record, Item, Sides, stated_text
from .record import group_context
from .text import normalize


def stated_signature(v) -> tuple:
    if isinstance(v, str):
        return ("stated", normalize(v), ())
    if v.by_reference is not None:
        return ("by_reference", v.by_reference.citation, ())
    return ("stated", normalize(v.value or ""), tuple(sorted((k, normalize(q)) for k, q in v.qualifiers.items())))


def stated_signatures(rec: Record, unit_id: str, signer=None) -> dict[str, dict[str, tuple]]:
    """group → field → signature, over the group's full resolved context."""
    signer = signer or (lambda at, f, v: stated_signature(v))
    out = {}
    unit = rec.units[unit_id]
    for gid in unit.groups:
        ctx = group_context(rec, unit_id, gid)
        out[gid] = {f: signer(_where(rec, unit_id, gid, f), f, v) for f, v in ctx.items()}
    return out


def _where(rec, unit_id, gid, f):
    if f in rec.units[unit_id].groups[gid].context:
        return f"units.{unit_id}.groups.{gid}.context.{f}"
    if f in rec.units[unit_id].context:
        return f"units.{unit_id}.context.{f}"
    return f"default_context.{f}"


def _diff_fields(sigs: dict, a: str, b: str) -> list[str]:
    fa, fb = sigs.get(a, {}), sigs.get(b, {})
    return sorted(f for f in set(fa) | set(fb) if fa.get(f, ("absent",)) != fb.get(f, ("absent",)))


@dataclass
class Contrast:
    kind: str
    fields: list[str] = field(default_factory=list)
    confound: bool = False
    balanced: bool | None = None
    pairwise: bool = True
    problems: list[str] = field(default_factory=list)
    condition: list[str] = field(default_factory=list)
    reference: list[str] = field(default_factory=list)
    aliased: bool = False
    benchmark: bool = False   # a native-tissue or other-study group is compared: value comparisons only
    linked: list[str] = field(default_factory=list)

    @property
    def field(self) -> str | None:
        return self.fields[0] if len(self.fields) == 1 and not self.confound else None


def engineered(rec: Record, unit_id: str) -> list[str]:
    return [g for g, x in rec.units[unit_id].groups.items() if not x.benchmark]


def _apply_links(fs: list[str], linked) -> tuple[list[str], list[str]]:
    """Fields declared linked (genotype ~ disease_model) count as one contrast on the first (02-audit, What code computes)."""
    for ln in linked or ():
        if len(fs) > 1 and set(fs) <= set(ln) and ln[0] in fs:
            return [ln[0]], [f for f in ln if f in fs]
    return fs, []


def item_contrast(rec: Record, item: Item, sigs: dict, linked=()) -> Contrast | None:
    kind = item.kind_of_test
    if kind is None:
        return None
    unit_groups = rec.units[item.unit].groups
    if any(unit_groups[g].benchmark for g in item.group_ids() if g in unit_groups):
        cond = [item.compares[0]] if kind == "pair" else (list(item.compares.condition) if kind == "main effect" else [])
        ref = [item.compares[1]] if kind == "pair" else (list(item.compares.reference) if kind == "main effect" else [])
        return Contrast(kind, [], benchmark=True, pairwise=kind == "pair", condition=cond, reference=ref)
    if kind == "pair":
        a, b = item.compares
        fs, links = _apply_links(_diff_fields(sigs, a, b), linked)
        c = Contrast("pair", fs, confound=len(fs) > 1, condition=[a], reference=[b], linked=links)
        if len(fs) > 1:
            c.aliased = any(set(fs) <= set(al) for al in aliased_sets(sigs, engineered(rec, item.unit)))
        if not fs:
            c.problems.append(f"groups {a} and {b} have identical context: no field differs")
        if len(fs) > 1:
            c.problems.append(f"confound: {a} and {b} differ in {', '.join(fs)}"
                              + (" (aliased: these fields vary together across every group of the unit)" if c.aliased else ""))
        return c
    if kind == "main effect":
        cond, ref = item.compares.condition, item.compares.reference
        c = Contrast("main effect", condition=list(cond), reference=list(ref))
        sigs = compound_signatures(sigs, engineered(rec, item.unit))
        all_fields = set().union(*(sigs.get(g, {}).keys() for g in cond + ref))
        factor = []
        for f in sorted(all_fields):
            cv = {sigs.get(g, {}).get(f) for g in cond}
            rv = {sigs.get(g, {}).get(f) for g in ref}
            if len(cv) == 1 and len(rv) == 1 and cv != rv:
                factor.append(f)
        c.fields = factor
        if len(factor) != 1:
            c.problems.append(f"main effect sides differ uniformly in {factor or 'no field'}, not exactly one")
            c.balanced = False
            return c
        f0 = factor[0]
        if "+" in f0:
            c.fields, c.confound, c.aliased = f0.split("+"), True, True
            c.problems.append(f"main effect of aliased fields {f0}: they vary together across every group of the unit")
        others = lambda gs: sorted(tuple(sorted((k, v) for k, v in sigs.get(g, {}).items() if k != f0)) for g in gs)
        c.balanced = others(cond) == others(ref)
        if not c.balanced:
            c.problems.append(f"main effect of {f0} is not balanced on the other fields")
        return c
    gs = list(item.compares)
    varying = sorted(set().union(*(set(_diff_fields(sigs, a, b)) for a, b in combinations(gs, 2))))
    c = Contrast(kind, varying, pairwise=False)
    if kind == "interaction":
        d = _design(gs, sigs)
        if not d.factorial:
            c.problems.append("an interaction needs groups crossed on two fields in all combinations")
        c.fields = d.factors or varying
    return c


@dataclass
class Design:
    factorial: bool
    factors: list[str] = field(default_factory=list)
    levels: dict[str, int] = field(default_factory=dict)
    groups: list[str] = field(default_factory=list)


def _design(groups: list[str], sigs: dict) -> Design:
    """Factorial when the groups' varying fields (k >= 2) are crossed in all combinations."""
    if len(groups) < 4:
        return Design(False)
    varying = sorted(set().union(*(set(_diff_fields(sigs, a, b)) for a, b in combinations(groups, 2))))
    if len(varying) < 2 or not all(f in sigs.get(g, {}) for g in groups for f in varying):
        return Design(False)
    levels = {f: {sigs[g][f] for g in groups} for f in varying}
    if any(len(v) < 2 for v in levels.values()):
        return Design(False)
    combos = {tuple(sigs[g][f] for f in varying) for g in groups}
    prod = 1
    for v in levels.values():
        prod *= len(v)
    if len(combos) == prod:
        return Design(True, varying, {f: len(v) for f, v in levels.items()}, list(groups))
    return Design(False)


def aliased_sets(sigs: dict, groups: list[str]) -> list[list[str]]:
    """Varying fields that partition the groups identically (they always change together)."""
    if len(groups) < 2:
        return []
    varying = sorted(set().union(*(set(_diff_fields(sigs, a, b)) for a, b in combinations(groups, 2))))
    part = {}
    for f in varying:
        if not all(f in sigs.get(g, {}) for g in groups):
            continue
        vals = [sigs[g][f] for g in groups]
        canon, key = {}, []
        for v in vals:
            canon.setdefault(v, len(canon))
            key.append(canon[v])
        part.setdefault(tuple(key), []).append(f)
    return [fs for fs in part.values() if len(fs) > 1]


def compound_signatures(sigs: dict, groups: list[str]) -> dict:
    out = {g: dict(sigs.get(g, {})) for g in groups}
    for fs in aliased_sets(sigs, groups):
        name = "+".join(fs)
        for g in groups:
            out[g][name] = tuple(out[g].pop(f) for f in fs)
    return out


def expand_sets(sigs: dict, groups: list[str], set_fields=()) -> dict:
    """A set-valued field whose members differ between groups becomes one presence factor per member that varies
    (`treatment[insulin]`), when every group states the field as terms. Each group's stated set is its complete list
    (02-audit, What code computes)."""
    out = {g: dict(sigs.get(g, {})) for g in groups}
    for f in set_fields:
        vals = [out[g].get(f) for g in groups]
        if any(v is None or v[0] != "terms" for v in vals) or len({v for v in vals}) < 2:
            continue
        members = set().union(*(set(v[1]) for v in vals))
        varying = [m for m in sorted(members) if len({m in v[1] for v in vals}) > 1]
        if not varying:
            continue
        for g in groups:
            v = out[g].pop(f)
            for m in varying:
                out[g][f"{f}[{m}]"] = ("present",) if m in v[1] else ("absent",)
            rest = (tuple(x for x in v[1] if x not in varying), v[2])
            out[g][f"{f}[other]"] = rest
    return out


def unit_design(rec: Record, unit_id: str, sigs: dict, set_fields=()) -> Design:
    """Factorial if some of the unit's groups cross two fields (or compounds of aliased fields) in all combinations
    and differ in nothing else."""
    groups = engineered(rec, unit_id)
    sigs = compound_signatures(expand_sets(sigs, groups, set_fields), groups)
    d = _design(groups, sigs)
    if d.factorial:
        return d
    # try subsets: drop groups (e.g. native tissue) that differ in a third field
    varying = sorted(set().union(*(set(_diff_fields(sigs, a, b)) for a, b in combinations(groups, 2)))) if len(groups) > 1 else []
    best = Design(False)
    for f in varying:  # a subset of groups sharing one field's value (e.g. without native tissue) may be factorial
        buckets: dict = {}
        for g in groups:
            buckets.setdefault(sigs[g].get(f), []).append(g)
        for members in buckets.values():
            d = _design(members, sigs)
            if d.factorial and len(d.groups) > len(best.groups):
                best = d
    if best.factorial:
        return best
    # drop groups that lack a field the others state (another study's data, native tissue)
    for drop in combinations(groups, 1):
        rest = [g for g in groups if g not in drop]
        d = _design(rest, sigs)
        if d.factorial:
            return d
    return Design(False)
