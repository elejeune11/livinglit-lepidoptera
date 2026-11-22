"""Across sources: directions, standing keys, comparisons, relaxation (05-across-sources).

Sources meet only where their mapped terms match. Code computes every
comparison and names the field when items cannot be compared. Direction is
computed from values and the printed P, never read from words; a reader's
stated_direction is used only when no values exist and is labelled 'stated'.
"""
from __future__ import annotations

import math
import statistics as st
from dataclasses import dataclass, field
from collections import Counter
from itertools import combinations

from .matching import Side, compare_terms, compare_qualifiers
from .models import Sides
from .numbers import parse_p, split_pm, convert, try_unit
from .text import normalize


@dataclass
class Direction:
    direction: str | None  # up | down | none | None (not available)
    origin: str | None     # computed | stated
    basis: str = ""


def group_mean(ev) -> tuple[float | None, str | None, str]:
    """Stated means first, then the mean of released or read points, then read bar means."""
    if ev.mean is not None:
        return float(ev.mean), ev.unit, "stated"
    if ev.data_points:
        return st.mean(ev.data_points), ev.data_unit, "data"
    if "mean" in ev.data_summary:
        return float(ev.data_summary["mean"]), ev.data_unit, "data"
    if ev.read_points:
        return st.mean(p[0] for p in ev.read_points), ev.read_unit, "readings"
    if ev.read_mean:
        return ev.read_mean[0], ev.read_unit, "readings"
    return None, None, ""


def rebuilt_side(mean, spread, unit, chain):
    """(mean, spread, unit, rebuilt?) for one group: a printed value from a wrong derivation (the paper's formula
    contradicts the library, or printed and rebuilt differ by a constant factor) is replaced by the value code rebuilt
    (derived by LivingLit), in the printed value's unit. The spread is scaled with it only when
    the two differ by a constant factor; otherwise no spread is known for the rebuilt value (04-formulas, Wrong
    derivations)."""
    if chain is None or chain.verdict != "inconsistent" or chain.rebuilt is None or mean is None:
        return mean, spread, unit, False
    constant = any(f.startswith("constant factor") for f in chain.flags)
    if not (constant or chain.library_verdict == "inconsistent"):
        return mean, spread, unit, False  # numbers off for another reason (e.g. how means were built): not a wrong derivation
    r = chain.rebuilt
    if chain.rebuilt_unit and unit and chain.rebuilt_unit != unit:
        try:
            r = convert(r, chain.rebuilt_unit, unit)
        except ValueError:
            return mean, spread, unit, False
    sp = abs(spread * r / mean) if (constant and spread is not None and mean) else None
    return r, sp, unit or chain.rebuilt_unit, True


def group_sd(ev, basis: str) -> float | None:
    """The group's SD on the same basis as its mean: a stated SD, a stated SEM times sqrt(n) when one n is printed, or
    the SD of released or read points (05-across-sources, Comparisons)."""
    def from_stated(spread, kind, n):
        try:
            s = float(spread)
        except (TypeError, ValueError):
            return None
        if kind == "SD":
            return s
        if kind == "SEM" and len(n) == 1:
            return s * math.sqrt(n[0])
        return None
    if basis == "stated":
        return from_stated(ev.spread, ev.spread_kind, ev.n)
    if basis == "data":
        if len(ev.data_points) >= 2:
            return st.stdev(ev.data_points)
        if "sd" in ev.data_summary:
            return from_stated(ev.data_summary["sd"], "SD", ev.n)
        if "sem" in ev.data_summary:
            return from_stated(ev.data_summary["sem"], "SEM", ev.n)
        return None
    if basis == "readings" and len(ev.read_points) >= 2:
        return st.stdev(p[0] for p in ev.read_points)
    return None


def _side_mean(evs, groups):
    vals, unit, basis = [], None, set()
    for g in groups:
        m, u, b = group_mean(evs[g])
        if m is None:
            return None, None, ""
        if unit and u and unit != u:
            try:
                m = convert(m, u, unit)
            except ValueError:
                return None, None, ""
        unit = unit or u
        vals.append(m)
        basis.add(b)
    return st.mean(vals), unit, "+".join(sorted(basis))


def item_direction(item, evs) -> Direction:
    kind = item.kind_of_test
    if kind not in ("pair", "main effect"):
        return Direction(None, None)
    if kind == "pair":
        cond, ref = [item.compares[0]], [item.compares[1]]
    else:
        cond, ref = item.compares.condition, item.compares.reference
    mc, uc, bc = _side_mean(evs, cond)
    mr, ur, br = _side_mean(evs, ref)
    pp = parse_p(item.stats.p)
    if mc is not None and mr is not None and pp is not None:
        if not pp.significant:
            return Direction("none", "computed", f"P {item.stats.p}")
        if mc == mr:
            return Direction(None, None, "equal means with a significant P")
        return Direction("up" if mc > mr else "down", "computed", f"{bc} means, P {item.stats.p}")
    if item.stated_direction is not None:
        sd = item.stated_direction.direction
        if mc is not None and mr is not None and sd in ("up", "down"):
            if (sd == "up" and mc <= mr) or (sd == "down" and mc >= mr):
                return Direction(None, None, f"stated {sd} disagrees with group means ({mc:g} vs {mr:g})")
            return Direction(sd, "stated", "stated, agreeing with group means (no P)")
        return Direction(sd, "stated", "stated, not computed")
    return Direction(None, None, "no values or no printed P")


def direction_with_suspects(item, rec, iid, data_rows=(), readings=(), figures=None) -> Direction:
    """A direction that changes when suspect cells or readings are left out is not available (02-audit, Checks within a
    source)."""
    from .checks import gather
    ev = gather(rec, iid, data_rows, readings, figures)
    d = item_direction(item, ev)
    sus = [s for e in ev.values() for s in e.suspect]
    if not sus:
        return d
    d2 = item_direction(item, gather(rec, iid, data_rows, readings, figures, drop_suspect=True))
    if d2.direction != d.direction:
        return Direction(None, None, f"not available (suspect cell): {d.direction} with, {d2.direction} without; "
                                     + "; ".join(sus))
    d.basis += " (unchanged without suspect cells)"
    return d


# ------------------------------------------------------------------ comparing contexts under a key
@dataclass
class Unit:
    """One side of a comparison: an item (and group, for values) with its mapped context."""
    paper: str
    unit: str
    item: str
    group: str | None
    measure_terms: tuple
    measure_qualifiers: dict
    context: dict          # field -> Side
    method: str | None = None
    derivation: str | None = None
    contrast: object = None
    cond_ctx: dict | None = None
    ref_ctx: dict | None = None
    mean: float | None = None
    spread: float | None = None
    value_unit: str | None = None
    direction: Direction | None = None
    lab: str | None = None
    rebuilt: bool = False  # mean (and spread) rebuilt by LivingLit from a derivation the printed value failed


def field_result(vocab, entry: str, a: Unit, b: Unit, part: str) -> tuple[bool, str]:
    """(matches, reason) for one must_match entry."""
    name, _, level = entry.partition("@")
    if name == "contrast":
        ca, cb = a.contrast, b.contrast
        if getattr(ca, "kind", None) == "scaling" or getattr(cb, "kind", None) == "scaling":
            if getattr(ca, "kind", None) == "scaling" and getattr(cb, "kind", None) == "scaling":
                return ca.field == cb.field, f"scaling {ca.field} vs {cb.field}"
            return False, "scaling law vs group contrast"
        if ca is None or cb is None or ca.field is None or cb.field is None:
            why = []
            for side, c in (("a", ca), ("b", cb)):
                if c is not None and c.field is None:
                    kind = ("against benchmark" if getattr(c, "benchmark", False) else "aliased confound"
                            if getattr(c, "aliased", False) else ("confound" if c.confound else "no differing field"))
                    why.append(f"{side}: {kind} on {'+'.join(c.fields) or '—'}")
            return False, "contrast: no single computed contrast (" + "; ".join(why) + ")"
        if ca.field != cb.field:
            return False, f"contrast varies {ca.field} vs {cb.field}"
        f = ca.field
        for sa, sb, what in ((a.cond_ctx, b.cond_ctx, "condition"), (a.ref_ctx, b.ref_ctx, "reference")):
            r = compare_terms(vocab, f, sa.get(f, Side(state="not stated")), sb.get(f, Side(state="not stated")))
            if r not in ("same",) and not r.startswith("same"):
                q = compare_qualifiers(sa.get(f, Side()).qualifiers, sb.get(f, Side()).qualifiers)
                return False, f"contrast {what} {f}: {r}"
        return True, ""
    if name == "method":
        if not a.method or not b.method:
            return (part == "direction"), "method not stated"
        return normalize(a.method) == normalize(b.method), "method differs"
    if name == "derivation":
        if a.derivation is None and b.derivation is None:
            return True, ""
        return a.derivation == b.derivation, f"derivation {a.derivation} vs {b.derivation}"
    if name.startswith("measure."):
        q = name.split(".", 1)[1]
        va, vb = a.measure_qualifiers.get(q), b.measure_qualifiers.get(q)
        if q == "normalised_to" and va is None and vb is None and \
                a.measure_qualifiers.get("expressed_as") == b.measure_qualifiers.get("expressed_as") == "absolute":
            return True, ""  # absolute values are normalised to nothing
        if va is None or vb is None:
            return False, f"{name} not stated"
        return normalize(va) == normalize(vb) or compare_qualifiers({q: va}, {q: vb}) == "same", f"{name} differs"
    sa = a.context.get(name, Side(state="not stated"))
    sb = b.context.get(name, Side(state="not stated"))
    decl = vocab.fields.get(name)
    if decl is not None and decl.kind == "quantity":
        if sa.state or sb.state:
            st_ = sa.state or sb.state
            if sa.state == sb.state and st_ in ("not applicable", "none"):
                return True, ""
            return False, f"{name}: {st_}"
        r = compare_qualifiers({"v": sa.qualifiers.get("_text", "")}, {"v": sb.qualifiers.get("_text", "")})
        return r == "same", f"{name}: differ"
    under = level[6:] if level.startswith("under:") else None
    k = int(level) if level.isdigit() else None
    r = compare_terms(vocab, name, sa, sb, level=k, under=under)
    ok = r == "same" or r.startswith("same at") or r.startswith("same under")
    if ok:
        q = compare_qualifiers(sa.qualifiers, sb.qualifiers) if k is None and under is None else "same"
        if q == "differ":
            return False, f"{name}: qualifiers differ"
    reason = f"{name}: {r}" + (f" ({sa.flag or sb.flag})" if r == "flagged" else "")
    return ok, reason


UNKNOWN = ("not stated", "not yet read", "by reference")


def is_unknown(reason: str) -> bool:
    """Open world: a field unstated on a side (not stated, not yet read, stated only by reference) is unknown, not a
    conflict. Unmapped and flagged values are not unknown: they wait on a reader or agent (05-across-sources)."""
    r = reason.lower()
    return any(u in r for u in UNKNOWN) and "differ" not in r and "flagged" not in r


def key_check(vocab, entries, a, b, part):
    reasons = []
    for e in entries:
        ok, why = field_result(vocab, e, a, b, part)
        if not ok:
            reasons.append((e, why))
    return reasons


def relax(vocab, entries, a, b, part) -> str | None:
    """Coarsen each blocking field one level, then drop it, and report where the verdict changes."""
    blocking = key_check(vocab, entries, a, b, part)
    if not blocking:
        return None
    current = list(entries)
    changes = []
    for e, _ in blocking:
        name, _, level = e.partition("@")
        tried = []
        if vocab.fields.get(name) is not None and vocab.fields[name].kind in ("terms", "measure"):
            lv = int(level) if level.isdigit() else None
            if lv is None:
                tried.append(f"{name}@1")
            elif lv > 1:
                tried.append(f"{name}@{lv - 1}")
        done = False
        for t in tried:
            trial = [t if x == e else x for x in current]
            if not any(x == t for x, _ in key_check(vocab, [t], a, b, part)):
                current = trial
                changes.append(t)
                done = True
                break
        if not done:
            current = [x for x in current if x != e]
            changes.append(f"drop {name}")
    return "comparable if " + ", ".join(changes)


def compare_values(a: Unit, b: Unit) -> str:
    if a.mean is None or b.mean is None:
        return "not available"
    mb = b.mean
    if a.value_unit and b.value_unit and a.value_unit != b.value_unit:
        try:
            mb = convert(b.mean, b.value_unit, a.value_unit)
        except ValueError:
            return "not comparable (units)"
    if a.spread is None or b.spread is None:
        return "not available (no spread)"
    sb = b.spread
    if a.value_unit and b.value_unit and a.value_unit != b.value_unit:
        sb = convert(b.spread, b.value_unit, a.value_unit)
    tol = math.sqrt(a.spread ** 2 + sb ** 2)  # within the spread of the difference (SDs)
    return "agree" if abs(a.mean - mb) <= tol else "differ"


def compare_directions(a: Unit, b: Unit) -> str:
    da, db = a.direction, b.direction
    if da is None or db is None or da.direction is None or db.direction is None:
        return "not available"
    tag = " (stated)" if "stated" in (da.origin, db.origin) else ""
    if "none" in (da.direction, db.direction) and da.direction != db.direction:
        return "differ in significance" + tag
    return ("same direction" if da.direction == db.direction else "differ in direction") + tag


_CONFOUNDER_FIELDS = ("view_orientation", "hydration_and_prep", "imaging_modality", "perturbation_modality")


def _side_label(vocab, s: Side) -> str:
    if s.terms:
        return ", ".join(sorted(vocab.terms[t].label if t in vocab.terms else t for t in s.terms))
    if s.qualifiers:
        return ", ".join(f"{k}={v}" for k, v in sorted(s.qualifiers.items()))
    if s.state:
        return s.state
    return "not stated"


def compute_context_diff(vocab, a: Unit, b: Unit) -> dict:
    """Compute transparent matched fields, differing fields, and physical confounder warnings for pair (a, b)."""
    matched: list[str] = []
    differing: dict[str, list[str]] = {}
    confounders: list[str] = []
    for fname, fdecl in vocab.fields.items():
        if fname == "measure":
            continue
        sa = a.context.get(fname, Side(state="not stated"))
        sb = b.context.get(fname, Side(state="not stated"))
        la, lb = _side_label(vocab, sa), _side_label(vocab, sb)
        if la == "not stated" and lb == "not stated":
            continue
        if fdecl.kind == "terms":
            if sa.terms and sb.terms:
                same = bool(sa.terms == sb.terms)
            elif sa.state and sb.state:
                same = sa.state == sb.state
            else:
                same = False
        else:
            same = (la == lb)
        if same:
            matched.append(fname)
        else:
            differing[fname] = [la, lb]
            if fname in _CONFOUNDER_FIELDS:
                confounders.append(f"{fname}: {la} vs {lb}")
    return {"matched": matched, "differing": differing, "confounders": confounders}


def comparisons(vocab, units: list[Unit], key_for) -> list[dict]:
    """Every pair across papers sharing a measure term; one row per pair and part (value, direction)."""
    rows = []
    by_measure: dict = {}
    for u in units:
        if u.measure_terms:
            by_measure.setdefault(u.measure_terms, []).append(u)
    for mt, us in by_measure.items():
        key = key_for(mt)
        for a, b in combinations(us, 2):
            if a.paper == b.paper:
                continue
            part = "direction" if a.contrast is not None and b.contrast is not None else (
                "value" if a.group is not None and b.group is not None else None)
            if part is None:
                continue
            entries = key[part]["must_match"]
            blocking = key_check(vocab, entries, a, b, part)
            unknown = [(e, why) for e, why in blocking if is_unknown(why)]
            known = [(e, why) for e, why in blocking if not is_unknown(why)]
            if known:
                verdict = "not comparable"
            else:  # computed, conditional on the fields unknown on a side
                verdict = compare_directions(a, b) if part == "direction" else compare_values(a, b)
            cdiff = compute_context_diff(vocab, a, b)
            rows.append({
                "measure": "+".join(mt), "part": part,
                "a": f"{a.paper}/{a.item}" + (f"/{a.group}" if a.group else ""), "a_unit": f"{a.paper}/{a.unit}",
                "b": f"{b.paper}/{b.item}" + (f"/{b.group}" if b.group else ""), "b_unit": f"{b.paper}/{b.unit}",
                "verdict": verdict,
                "assumes": [] if known else [e for e, _ in unknown],
                "blocking": [f"{e}: {why}" for e, why in known] + ([] if not known else [f"{e}: {why}" for e, why in unknown]),
                "relaxation": relax(vocab, entries, a, b, part) if blocking else None,
                "rebuilt": [_label(x) for x in (a, b) if x.rebuilt] if part == "value" else [],
                "direction_origin": (",".join(sorted({x.direction.origin for x in (a, b) if x.direction and x.direction.origin}))
                                     if part == "direction" else None),
                "context_diff": cdiff,
            })
    return rows


def _label(u: Unit) -> str:
    return f"{u.paper}/{u.item}" + (f"/{u.group}" if u.group else "")


def _signature(vocab, entries, u: Unit) -> str:
    out = []
    for e in entries:
        name, _, level = e.partition("@")
        if name == "contrast":
            c = u.contrast
            out.append(f"contrast={getattr(c, 'field', None) or '—'}")
        elif name in ("method", "derivation"):
            out.append(f"{name}={getattr(u, name) or 'not stated'}")
        elif name.startswith("measure."):
            out.append(f"{name}={u.measure_qualifiers.get(name.split('.', 1)[1], 'not stated')}")
        else:
            s = u.context.get(name, Side(state="not stated"))
            projected = {vocab.at_level(t, int(level)) if level.isdigit() else t for t in s.terms}
            val = s.state or ", ".join(sorted(vocab.terms[t].label if t in vocab.terms else t for t in projected)) \
                or s.qualifiers.get("_text", "")
            out.append(f"{e}={val}")
    return "; ".join(out)


def strata(vocab, units: list[Unit], key_for) -> list[dict]:
    """Comparable sets per measure (05-across-sources, Strata, not pairs).

    Items whose must-match fields all match with nothing assumed are one stratum (union of confirmed matches).
    Each item lists the key fields unknown on its side. Strata whose items match except for fields unknown on a
    side are linked, the link naming what it assumes. Verdicts are computed only between items of different
    papers: confirmed inside a stratum, conditional along a link."""
    buckets: dict = {}
    for u in units:
        if not u.measure_terms:
            continue
        part = "direction" if u.contrast is not None else ("value" if u.group is not None else None)
        if part:
            buckets.setdefault((u.measure_terms, part), []).append(u)
    rows = []
    for (mt, part), us in buckets.items():
        entries = key_for(mt)[part]["must_match"]
        parent = list(range(len(us)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        pairs = {}
        for i, j in combinations(range(len(us)), 2):
            blocking = key_check(vocab, entries, us[i], us[j], part)
            pairs[(i, j)] = blocking
            if not blocking:
                parent[find(i)] = find(j)
        groups: dict = {}
        for i in range(len(us)):
            groups.setdefault(find(i), []).append(i)
        sid = {}
        for root, members in groups.items():
            sid[root] = f"S{len(rows) + len(sid) + 1}"
        verdicts = {r: Counter() for r in groups}
        links = {r: {} for r in groups}
        for (i, j), blocking in pairs.items():
            a, b = us[i], us[j]
            ri, rj = find(i), find(j)
            if blocking and any(not is_unknown(w) for _, w in blocking):
                continue
            assumed = sorted({e for e, _ in blocking})
            if a.paper != b.paper:
                v = compare_directions(a, b) if part == "direction" else compare_values(a, b)
            else:
                v = None
            if ri == rj:
                if v and not assumed:
                    verdicts[ri][v] += 1
                continue
            for x, y in ((ri, rj), (rj, ri)):
                l = links[x].setdefault(y, {"assumes": set(), "verdicts": Counter()})
                l["assumes"] |= set(assumed)
                if v:
                    l["verdicts"][v] += 1
        for root, members in groups.items():
            ms = [us[k] for k in members]
            unknown = {}
            for u in ms:
                f = [e for e in entries if e.partition("@")[0] not in ("contrast", "method", "derivation")
                     and not e.startswith("measure.")
                     and (u.context.get(e.partition("@")[0], Side(state="not stated")).state or "") in UNKNOWN]
                if f:
                    unknown[_label(u)] = f
            rows.append({
                "stratum": sid[root], "measure": "+".join(mt), "part": part,
                "key": _signature(vocab, entries, ms[0]),
                "items": [_label(u) for u in ms], "papers": len({u.paper for u in ms}),
                "values": [f"{_label(u)}: {u.mean:g}" + (f" ± {u.spread:g} SD" if u.spread is not None else "")
                           + (f" {u.value_unit}" if u.value_unit else "") for u in ms if u.mean is not None]
                if part == "value" else [f"{_label(u)}: {u.direction.direction if u.direction else 'not available'}"
                                         for u in ms],
                "verdicts": dict(verdicts[root]),
                "unknowns": unknown,
                "links": [{"stratum": sid[y], "assumes": sorted(l["assumes"]), "verdicts": dict(l["verdicts"])}
                          for y, l in sorted(links[root].items(), key=lambda kv: sid[kv[0]])],
            })
    return rows
