"""Checks within a source, status and depth (02-audit, Checks within a source; Status and depth).

Every statistical check applies an entry of the shared formula library and
names it. Values are judged at printed precision; P from read values is an
interval. Unstated test, spread or n are tried as labelled alternatives.
"""
from __future__ import annotations

import math
import re
import statistics as st
from dataclasses import dataclass, field
from itertools import combinations

from .formulas import evaluate
from .models import Item, Record, Sides
from .numbers import (judge_value, judge_p, parse_p, split_pm, numbers_in, test_kind, try_unit, interval,
                      same_quantity_units, parse_number, judge_p_range)

STATUS_ORDER = ["inconsistent", "close", "consistent within reading", "consistent"]


@dataclass
class Check:
    check: str
    verdict: str  # consistent | consistent within reading | close | inconsistent | cannot check
    target: str = ""
    entry: str | None = None
    alternatives: list[dict] = field(default_factory=list)
    basis: str = "printed"  # printed | data | readings
    note: str = ""

    def as_dict(self):
        d = {"check": self.check, "verdict": self.verdict, "target": self.target, "basis": self.basis}
        if self.entry:
            d["entry"] = self.entry
        if self.alternatives:
            d["alternatives"] = self.alternatives
        if self.note:
            d["note"] = self.note
        return d


def combine_alternatives(verdicts: list[str]) -> str:
    """consistent under every alternative; close under some; inconsistent under every one (02-audit, Status and depth)."""
    if not verdicts:
        return "cannot check"
    if all(v == "consistent" for v in verdicts):
        return "consistent"
    if all(v in ("consistent", "consistent within reading") for v in verdicts):
        return "consistent within reading"
    if all(v == "inconsistent" for v in verdicts):
        return "inconsistent"
    return "close"


def status(checks: list[Check]) -> str:
    ran = [c.verdict for c in checks if c.verdict != "cannot check"]
    if not ran:
        return "cannot check"
    for s in STATUS_ORDER:
        if s in ran:
            return s
    return "cannot check"


def depth(checks: list[Check]) -> str:
    ran = [c for c in checks if c.verdict != "cannot check"]
    if not ran:
        return "none"
    bases = {c.basis for c in ran}
    for b in ("data", "readings", "printed"):
        if b in bases:
            return {"printed": "printed only"}.get(b, b)
    return "none"


# ------------------------------------------------------------------ evidence per group
@dataclass
class GroupEvidence:
    mean: str | None = None          # printed
    spread: str | None = None        # printed
    spread_kind: str = "not stated"
    unit: str | None = None
    n: list[int] = field(default_factory=list)  # printed n alternatives
    data_points: list[float] = field(default_factory=list)
    data_summary: dict = field(default_factory=dict)  # kind -> (value text, unit)
    data_unit: str | None = None
    read_points: list[tuple[float, float, float]] = field(default_factory=list)  # value, lo, hi
    read_mean: tuple | None = None
    read_error: tuple | None = None
    read_unit: str | None = None
    read_counts_exact: bool = False
    n_min: int | None = None  # a printed lower bound on n ('n ≥ 6'); then n holds no exact value
    suspect: list[str] = field(default_factory=list)  # suspect cells or readings in this group


N_MIN = re.compile(r"(≥|>=|>|at least|(?:a )?minimum of|more than)\s*(\d+)|(\d+)\s*or more", re.I)


def parse_n_min(text: str) -> int | None:
    """A printed lower bound on n ('n ≥ 6', 'n > 5', 'at least 4', '3 or more'): the smallest n it allows, else None."""
    m = N_MIN.search(text)
    if not m:
        return None
    first = re.search(r"\d+", text)
    if first and first.start() < m.start(m.lastindex if m.group(3) is None else 3):  # an earlier number is the n
        return None
    if m.group(3):
        return int(m.group(3))
    k = int(m.group(2))
    return k + 1 if m.group(1).lower() in (">", "more than") else k


def parse_n(text: str) -> list[int]:
    """The exact n a printed n allows; an upper bound ('up to 6') allows 2 to 6; a lower bound gives no exact n."""
    import re as _re
    if parse_n_min(text) is not None:
        return []
    low = text.lower()
    if _re.search(r"up to|≤|<=|at most|maximum of|max\.?\s", low):
        ks = [int(float(x)) for x in numbers_in(text) if float(x).is_integer() and float(x) > 1]
        if ks:
            return list(range(2, min(max(ks), 40) + 1))
    nums = []
    for x in numbers_in(text):
        try:
            v = float(x)
        except ValueError:
            continue
        if v.is_integer() and v > 0:
            nums.append(int(v))
    return sorted(set(nums))


def gather(rec: Record, iid: str, data_rows=(), readings=(), figures=None, drop_suspect=False) -> dict[str, GroupEvidence]:
    it = rec.evidence[iid]
    gids = it.group_ids() or ["_"]
    ev = {g: GroupEvidence() for g in gids}
    for vn, v in it.values.items():
        g = v.group or ("_" if not it.group_ids() and v.between is None else None)
        if g not in ev or v.x is not None:
            continue
        if v.kind in ("mean", "value", "median", "percent", "fraction"):
            try:
                m, s = split_pm(v.printed)
            except ValueError:
                continue
            if ev[g].mean is None:
                ev[g].mean, ev[g].spread, ev[g].spread_kind, ev[g].unit = m, s, v.spread, v.unit
        elif v.kind in ("sd", "sem"):
            ev[g].spread, ev[g].spread_kind = parse_number(v.printed)[0], v.kind.upper()
    if it.n != "not stated":
        per = it.n.per_group or {}
        for g in ev:
            if g in per:
                ev[g].n, ev[g].n_min = parse_n(per[g]), parse_n_min(per[g])
            elif not per:
                ev[g].n, ev[g].n_min = parse_n(it.n.printed), parse_n_min(it.n.printed)
    for r in data_rows:
        if r.item != iid or r.group not in ev or r.x is not None:
            continue
        e = ev[r.group]
        if r.suspect is not None:
            e.suspect.append(f"{r.file} {r.sheet or ''} {r.cell} = {r.value}: {r.suspect.why}")
            if drop_suspect:
                continue
        e.data_unit = r.unit
        if r.kind == "point":
            try:
                e.data_points.append(float(r.value))
            except ValueError:
                pass
        else:
            e.data_summary[r.kind] = r.value
    links = {}
    if figures is not None:
        for fid, f in figures.figures.items():
            for label, gl in f.groups.items():
                links[(fid, label)] = gl
    for rd in readings:
        gl = links.get((rd.figure, rd.group))
        if gl is None or gl.item != iid or gl.group not in ev or rd.x is not None:
            continue
        e = ev[gl.group]
        if rd.suspect is not None:
            e.suspect.append(f"{rd.figure}/{rd.group} {rd.kind} {rd.index}: {rd.suspect.why}")
            if drop_suspect:
                continue
        e.read_unit = gl.unit_of_value
        kind = figures.figures[rd.figure].kind if figures else "vector"
        e.read_counts_exact = kind == "vector"
        if rd.kind == "point":
            e.read_points.append((rd.value, rd.lo, rd.hi))
        elif rd.kind == "mean":
            e.read_mean = (rd.value, rd.lo, rd.hi)
        elif rd.kind == "error":
            e.read_error = (rd.value, rd.lo, rd.hi)
    return ev


# ------------------------------------------------------------------ statistics through the library
def t_and_p(lib, entry, m1, s1, n1, m2, s2, n2):
    g = {"m1": m1, "s1": s1, "n1": n1, "m2": m2, "s2": s2, "n2": n2}
    t = evaluate(lib.get(entry), g, "t")
    df = evaluate(lib.get(entry), g, "df")
    if t is None or df is None or not math.isfinite(t) or df <= 0:
        return None, None
    return t, evaluate(lib.get("t_distribution"), {"t": t, "df": df}, "p")


def anova_p(lib, groups):
    """groups: list of (mean, sd, n)."""
    N = sum(n for _, _, n in groups)
    k = len(groups)
    M = sum(m * n for m, _, n in groups) / N
    ssb = sum(n * (m - M) ** 2 for m, _, n in groups)
    ssw = sum((n - 1) * s ** 2 for _, s, n in groups)
    if ssw <= 0 or N - k <= 0:
        return None, None
    F = evaluate(lib.get("one_way_anova_f"), {"SSB": ssb, "SSW": ssw, "k": k, "N": N}, "F")
    return F, evaluate(lib.get("f_distribution"), {"F": F, "df1": k - 1, "df2": N - k}, "p")


def sd_of(points):
    return st.stdev(points) if len(points) > 1 else None


def to_sd(spread: float, kind: str, n: int, lib) -> float:
    if kind == "SEM":
        return spread * math.sqrt(n)
    if kind == "CI95":
        h1 = evaluate(lib.get("ci95_halfwidth"), {"sd": 1.0, "n": n}, "h")
        return spread / h1
    return spread


SPREAD_ALTS = {"SD": ["SD"], "SEM": ["SEM"], "CI95": ["CI95"], "not stated": ["SD", "SEM"], "none": []}


def convert_factor(frm: str | None, to: str | None) -> float | None:
    """Multiply a value in `frm` by this to get `to`; None when they are different quantities (02-audit, Units)."""
    if not frm or not to:
        return 1.0
    a, b = try_unit(frm), try_unit(to)
    if a.name and b.name:
        return a.factor / b.factor if a.dimension == b.dimension else None
    return 1.0 if same_quantity_units(frm, to) else None


# ------------------------------------------------------------------ the checks
def check_item(rec: Record, iid: str, lib, data_rows=(), readings=(), figures=None) -> list[Check]:
    """Every check; with a suspect cell or reading, each check that uses it runs again without it, and the two runs are
    labelled alternatives of one check (02-audit, Checks within a source)."""
    ev = gather(rec, iid, data_rows, readings, figures)
    out = _checks(rec, iid, lib, ev, (data_rows, readings, figures, False))
    sus = [s for e in ev.values() for s in e.suspect] + _family_suspects(rec, iid, data_rows, readings, figures)
    if not sus:
        return out
    without = {(c.check, c.target, c.basis, c.entry): c
               for c in _checks(rec, iid, lib, gather(rec, iid, data_rows, readings, figures, drop_suspect=True),
                                (data_rows, readings, figures, True))}
    merged = []
    for c in out:
        w = without.pop((c.check, c.target, c.basis, c.entry), None)
        if c.check in ("n against data", "n against readings"):
            w = None  # a suspect cell is still a replicate: counts are judged with it
        if w is None or (w.verdict == c.verdict and c.basis == "printed"):
            merged.append(c)
            continue
        alts = [{"label": "with suspect cells", "verdict": c.verdict}, {"label": "without suspect cells", "verdict": w.verdict}]
        merged.append(Check(c.check, combine_alternatives([v for v in (c.verdict, w.verdict) if v != "cannot check"]),
                            c.target, c.entry, alts + c.alternatives, c.basis,
                            (c.note + " " if c.note else "") + "(run with and without suspect: " + "; ".join(sus) + ")"))
    return merged


def _family_suspects(rec: Record, iid: str, data_rows, readings, figures) -> list[str]:
    """Suspect cells or readings in other items of the same unit, measure and test: they enter pooled post-hoc checks."""
    from .text import normalize
    it = rec.evidence[iid]
    key = (it.unit, normalize(it.measure), normalize(it.stats.test))
    sibs = {k for k, x in rec.evidence.items() if k != iid and (x.unit, normalize(x.measure), normalize(x.stats.test)) == key}
    if not sibs:
        return []
    out = [f"{r.file} {r.cell} = {r.value} ({r.item}): {r.suspect.why}" for r in data_rows if r.item in sibs and r.suspect]
    if figures is not None:
        links = {(fid, l): gl for fid, f in figures.figures.items() for l, gl in f.groups.items()}
        out += [f"{rd.figure}/{rd.group} {rd.index}: {rd.suspect.why}" for rd in readings
                if rd.suspect and (links.get((rd.figure, rd.group)) or None) and links[(rd.figure, rd.group)].item in sibs]
    return out


def replication_checks(iid: str, it: Item, ev: dict[str, GroupEvidence], lib) -> list[Check]:
    """Verify that reported SEM/SD matches the stated inferential unit_of_analysis rather than nested substructures."""
    if it.n == "not stated" or not it.n.levels or not it.n.test_unit:
        return []
    levels = it.n.levels
    tu = it.n.test_unit
    n_test_default = levels.get(tu)
    if not n_test_default or n_test_default < 2:
        return []
    out: list[Check] = []
    for g, e in ev.items():
        if not e.spread or e.spread_kind not in ("SEM", "not stated"):
            continue
        pts = e.data_points if len(e.data_points) >= 2 else [p[0] for p in e.read_points] if len(e.read_points) >= 2 else []
        basis = "data" if len(e.data_points) >= 2 else ("readings" if len(e.read_points) >= 2 else "")
        sd = st.stdev(pts) if len(pts) >= 2 else (e.read_error[0] if e.read_error else None)
        if not basis and e.read_error:
            basis = "readings"
        if sd is None or sd <= 0:
            continue
        fb = convert_factor(e.data_unit if basis == "data" else e.read_unit, e.unit)
        if fb is None:
            continue
        sd_u = sd * fb
        n_test = e.n[0] if e.n else n_test_default
        sem_test = evaluate(lib.get("sem_def"), {"sd": sd_u, "n": n_test}, "sem")
        sp_val = float(e.spread)
        if sp_val <= 0:
            continue
        n_eff = round((sd_u / sp_val) ** 2)
        v_test = judge_value(e.spread, sem_test)
        if v_test in ("consistent", "consistent within reading") or abs(sp_val - sem_test) / max(sem_test, 1e-12) < 0.35:
            out.append(Check("replication hierarchy", "consistent" if basis == "data" else "consistent within reading",
                             f"{iid}/{g}", "sem_def", basis=basis,
                             note=f"printed spread {e.spread} matches {tu}-level SEM ({sem_test:.4g}, N={n_test})"))
        elif n_eff >= 3 * n_test:
            finer = [f"{k}={v}" for k, v in levels.items() if k != tu and v > n_test]
            out.append(Check("replication hierarchy", "inconsistent", f"{iid}/{g}", "sem_def", basis=basis,
                             note=f"substructure pseudo-replication: printed SEM {e.spread} implies n_eff≈{n_eff} "
                                  f"({', '.join(finer) or 'substructures'}) while test unit is {tu} (N={n_test}, true SEM≈{sem_test:.4g})"))
    return out


def _checks(rec: Record, iid: str, lib, ev, src=((), (), None, False)) -> list[Check]:
    it = rec.evidence[iid]
    out: list[Check] = []
    out += against_data_and_readings(iid, ev)
    out += n_checks(iid, ev)
    out += spread_checks(iid, ev, lib)
    out += replication_checks(iid, it, ev, lib)
    out += same_data(iid, ev)
    out += reported_twice(iid, it)
    out += granularity(iid, it, ev)
    out += p_checks(iid, it, ev, lib)
    from .posthoc import pair_checks, two_way_checks
    data_rows, readings, figures, drop = src
    if it.kind_of_test == "pair":
        out += pair_checks(rec, iid, lib, data_rows, readings, figures, drop)
    elif it.kind_of_test in ("main effect", "interaction"):
        out += two_way_checks(rec, iid, lib, data_rows, readings, figures, drop)
    for extra in it.stats.p_values:
        alt = it.model_copy(update={"stats": it.stats.model_copy(update={"p": extra.p, "p_values": []})})
        for c in p_checks(iid, alt, ev, lib):
            c.note = (c.note + " " if c.note else "") + f"(P also printed: {extra.p!r}, {extra.anchor.where})"
            out.append(c)
    out += p_reported_twice(iid, it)
    return out


def p_reported_twice(iid, it: Item) -> list[Check]:
    """Several printed P for one item: significance must agree, and two exact P agree at the coarser precision (02-audit, Values)."""
    out = []
    first = parse_p(it.stats.p)
    for extra in it.stats.p_values:
        other = parse_p(extra.p)
        note = f"P {it.stats.p!r} vs {extra.p!r} ({extra.anchor.where})"
        if first is None or other is None:
            out.append(Check("reported twice", "cannot check", iid, note=note))
            continue
        if first.significant != other.significant:
            out.append(Check("reported twice", "inconsistent", iid, note=note))
            continue
        if first.op == "=" and other.op in ("=", "<", ">", ">="):
            out.append(Check("reported twice", judge_p(extra.p, first.value), iid, note=note))
        elif other.op == "=" and first.op in ("<", ">", ">="):
            out.append(Check("reported twice", judge_p(it.stats.p, other.value), iid, note=note))
        else:
            out.append(Check("reported twice", "consistent", iid, note=note))
    return out


def against_data_and_readings(iid, ev) -> list[Check]:
    out = []
    for g, e in ev.items():
        if e.mean is None:
            continue
        tgt = f"{iid}/{g} mean"
        if e.data_points or "mean" in e.data_summary:
            f = convert_factor(e.data_unit, e.unit)
            if f is None:
                out.append(Check("against data", "cannot check", tgt, basis="data",
                                 note=f"printed in {e.unit}, data in {e.data_unit}: different quantities"))
            else:
                dm = (st.mean(e.data_points) if e.data_points else float(e.data_summary["mean"])) * f
                out.append(Check("against data", judge_value(e.mean, dm), tgt, "mean_def", basis="data",
                                 note=f"data mean {dm:.6g}"))
        if e.read_points or e.read_mean:
            f = convert_factor(e.read_unit, e.unit)
            if f is None:
                out.append(Check("against readings", "cannot check", tgt, basis="readings",
                                 note=f"printed in {e.unit}, figure axis in {e.read_unit}: different quantities"))
                continue
            if e.read_points:
                vals = [p[0] * f for p in e.read_points]
                half = st.mean([(p[2] - p[1]) / 2 for p in e.read_points]) * f / math.sqrt(len(vals))
                rm = st.mean(vals)
            else:
                rm, half = e.read_mean[0] * f, (e.read_mean[2] - e.read_mean[1]) / 2 * f
            lo, hi = interval(e.mean)
            if lo <= rm <= hi:
                v = "consistent"
            elif lo - half <= rm <= hi + half:
                v = "consistent within reading"
            elif lo - half - (hi - lo) <= rm <= hi + half + (hi - lo):
                v = "close"
            else:
                v = "inconsistent"
            out.append(Check("against readings", v, tgt, "mean_def", basis="readings", note=f"read mean {rm:.6g} ± {half:.2g}"))
    return out


def n_checks(iid, ev) -> list[Check]:
    out = []
    for g, e in ev.items():
        if not e.n and e.n_min is None:
            continue
        tgt = f"{iid}/{g} n"
        allows = (lambda k: k >= e.n_min) if e.n_min is not None else (lambda k: k in e.n)
        printed = f"≥ {e.n_min}" if e.n_min is not None else str(e.n)
        if e.data_points:
            k = len(e.data_points)
            out.append(Check("n against data", "consistent" if allows(k) else "inconsistent", tgt, basis="data",
                             note=f"{k} data points, printed n {printed}"))
        elif "n" in e.data_summary:
            k = int(float(e.data_summary["n"]))
            out.append(Check("n against data", "consistent" if allows(k) else "inconsistent", tgt, basis="data",
                             note=f"data n {k}, printed n {printed}"))
        if e.read_points and e.read_counts_exact:
            k = len(e.read_points)
            out.append(Check("n against readings", "consistent within reading" if allows(k) else "inconsistent", tgt,
                             basis="readings", note=f"{k} points read (vector, exact count), printed n {printed}"))
    return out


def n_from_bar_verdict(implied: float, ns: list[int]) -> str:
    """Within a quarter (at least 1) of a printed n: consistent within reading; within half (at least 2): close; an
    SD-sized bar (implied n about 1) is a spread question; otherwise inconsistent."""
    if abs(implied - 1) <= 0.5:
        return "cannot check"
    if any(abs(implied - k) <= max(1.0, 0.25 * k) for k in ns):
        return "consistent within reading"
    if any(abs(implied - k) <= max(2.0, 0.5 * k) for k in ns):
        return "close"
    return "inconsistent"


def spread_checks(iid, ev, lib) -> list[Check]:
    """Which spread; n implied by an error bar (02-audit, Checks within a source)."""
    out = []
    for g, e in ev.items():
        pts, basis = (e.data_points, "data") if len(e.data_points) > 2 else ([p[0] for p in e.read_points], "readings")
        if len(pts) < 3:
            continue
        sd = st.stdev(pts)
        n = len(pts)
        sem = sd / math.sqrt(n)
        if e.spread is not None and e.unit is not None:
            f = convert_factor(e.data_unit if basis == "data" else e.read_unit, e.unit)
            if f is None:
                continue
            fits = [k for k, v in (("SD", sd * f), ("SEM", sem * f)) if judge_value(e.spread, v) != "inconsistent"]
            stated = e.spread_kind
            if stated in ("SD", "SEM"):
                verdict = "consistent" if stated in fits else ("inconsistent" if fits else "inconsistent")
                if basis == "readings" and verdict == "consistent":
                    verdict = "consistent within reading"
                out.append(Check("which spread", verdict, f"{iid}/{g} spread", "sem_def", basis=basis,
                                 note=f"printed {e.spread} labelled {stated}; fits {fits or 'neither'} (SD {sd*f:.4g}, SEM {sem*f:.4g})"))
            else:
                out.append(Check("which spread", "cannot check", f"{iid}/{g} spread", "sem_def", basis=basis,
                                 note=f"spread not labelled; fits {fits or 'neither'}"))
        if e.read_error and e.read_mean and basis == "readings":
            bar = abs(e.read_error[0] - e.read_mean[0])
            if bar > 0:
                implied = (sd / bar) ** 2
                out.append(Check("n implied by error bar", n_from_bar_verdict(implied, e.n or [n]), f"{iid}/{g} n",
                                 "sem_def", basis="readings",
                                 note=f"(SD of points / bar)² = {implied:.1f}; points {n}, printed n "
                                      + (f"≥ {e.n_min}" if e.n_min is not None else str(e.n))))
    return out


def same_data(iid, ev) -> list[Check]:
    out = []
    for a, b in combinations(ev, 2):
        pa, pb = ev[a].data_points, ev[b].data_points
        if len(pa) >= 3 and pa == pb:
            out.append(Check("same data", "inconsistent", f"{iid}/{a},{b}", basis="data",
                             note="identical runs of values in separate groups"))
    return out


SOURCE_SUFFIXES = ("_text", "_legend", "_table", "_fig", "_figure", "_abstract", "_results", "_methods", "_si",
                   "_supplement", "_discussion")


def _base_name(vn: str) -> str:
    for suf in SOURCE_SUFFIXES:
        if vn.endswith(suf):
            return vn[: -len(suf)]
    return vn


def reported_twice(iid, it: Item) -> list[Check]:
    """One quantity printed in two places: value names that differ only by a source suffix (_text, _legend, ...)."""
    out = []
    seen = {}
    for vn, v in it.values.items():
        if v.group is None or v.kind not in ("mean", "value", "percent"):
            continue
        key = (_base_name(vn), v.group, v.x, v.kind)
        if key in seen:
            other = seen[key]
            try:
                a, _ = split_pm(v.printed)
                b, _ = split_pm(other.printed)
            except ValueError:
                continue
            f = convert_factor(other.unit, v.unit)
            if f is None:
                out.append(Check("reported twice", "cannot check", f"{iid}/{v.group}", note="different units"))
                continue
            dec = lambda x: len(x.split("e")[0].split(".")[1]) if "." in x.split("e")[0] else 0
            # judge at the coarser printed precision
            verdict = judge_value(b, float(a) / f) if dec(a) >= dec(b) else judge_value(a, float(b) * f)
            out.append(Check("reported twice", verdict, f"{iid}/{v.group}", note=f"{other.printed} vs {v.printed}"))
        else:
            seen[key] = v
    return out


def granularity(iid, it: Item, ev) -> list[Check]:
    """Is a mean possible for its n, when the values are counts (GRIM) (02-audit, Checks within a source)."""
    out = []
    for g, e in ev.items():
        if e.mean is None or not e.n or try_unit(e.unit or "").dimension != "count":
            continue
        dec = len(e.mean.split(".")[1]) if "." in e.mean else 0
        ok = any(abs(round(float(e.mean) * n) / n - float(e.mean)) <= 0.5 * 10 ** -dec + 1e-12 for n in e.n)
        out.append(Check("granularity", "consistent" if ok else "inconsistent", f"{iid}/{g} mean", "mean_def",
                         note=f"mean {e.mean} of counts with n {e.n}"))
    return out


def p_checks(iid, it: Item, ev, lib) -> list[Check]:
    out = []
    kind = it.kind_of_test
    pp = parse_p(it.stats.p)
    tk = test_kind(it.stats.test)
    if kind is None:
        return out
    if pp is not None and pp.op == "sig":
        return [Check("summary to P", "cannot check", iid,
                      note="significant, threshold not stated: a direction, but no P check (02-audit, Values)")]
    if kind in ("main effect", "interaction"):
        if pp:
            out.append(Check("summary to P", "cannot check", iid, note=f"{kind} of a {tk.family.replace('_', ' ')}: checked "
                                                                        f"from points only, never from summaries"))
        return out
    if kind == "omnibus":
        if not pp:
            return out
        if tk.family != "one_way_anova":
            out.append(Check("summary to P", "cannot check", iid, note=f"omnibus P rechecked only for a one-way ANOVA; printed test: {it.stats.test}"))
            return out
        groups = [ev[g] for g in it.compares]
        out += _anova(iid, groups, pp, lib)
        return out
    a, b = it.compares
    ea, eb = ev[a], ev[b]
    # statistic to P
    if it.stats.statistic not in ("not stated", "") and pp:
        out += statistic_to_p(iid, it, pp, lib)
    if not pp:
        return out
    if tk.posthoc or tk.family in ("two_way_anova", "anova_unspecified", "one_way_anova", "kruskal_wallis", "friedman"):
        out.append(Check("summary to P", "cannot check", iid,
                         note=f"pairwise P from {it.stats.test}: post-hoc or ANOVA tests are not rechecked with a "
                              f"two-group test; post-hoc pairs are checked from points only"))
        return out
    if tk.family in ("mann_whitney", "wilcoxon_signed_rank", "paired_t", "correlation", "contingency", "other"):
        out.append(Check("summary to P", "cannot check", iid, note=f"{it.stats.test}: not in the library for this check"))
        return out
    entries = tk.alternatives
    # summary to P
    if ea.mean and eb.mean and ea.spread and eb.spread and ea.n and eb.n:
        if convert_factor(eb.unit, ea.unit) is None:
            out.append(Check("summary to P", "cannot check", iid, note=f"groups printed in {ea.unit} and {eb.unit}"))
        else:
            fb = convert_factor(eb.unit, ea.unit)
            alts, verdicts = [], []
            for entry in entries:
                for sk in SPREAD_ALTS.get(ea.spread_kind, ["SD", "SEM"]):
                    for n1 in ea.n:
                        for n2 in eb.n:
                            if n1 < 2 or n2 < 2:
                                continue
                            s1 = to_sd(float(ea.spread), sk, n1, lib)
                            s2 = to_sd(float(eb.spread) * fb, sk if eb.spread_kind in ("not stated", ea.spread_kind) else eb.spread_kind, n2, lib)
                            t, p = t_and_p(lib, entry, float(ea.mean), s1, n1, float(eb.mean) * fb, s2, n2)
                            if p is None:
                                continue
                            v = judge_p(it.stats.p, p)
                            verdicts.append(v)
                            alts.append({"entry": entry, "spread": sk, "n": [n1, n2], "p": round(p, 6), "verdict": v,
                                         "added": sk != ea.spread_kind or entry not in TK_STATED.get(tk.family, ())})
            if verdicts:
                out.append(Check("summary to P", combine_alternatives(verdicts), iid, " / ".join(entries) + " + t_distribution",
                                 alts, "printed"))
    # points to P
    for basis in ("data", "readings"):
        pa = ea.data_points if basis == "data" else [p[0] for p in ea.read_points]
        pb = eb.data_points if basis == "data" else [p[0] for p in eb.read_points]
        if len(pa) < 2 or len(pb) < 2:
            continue
        verdicts, alts = [], []
        for entry in entries:
            t, p = t_and_p(lib, entry, st.mean(pa), st.stdev(pa), len(pa), st.mean(pb), st.stdev(pb), len(pb))
            if p is None:
                continue
            if basis == "readings":
                ha = st.mean([(x[2] - x[1]) / 2 for x in ea.read_points])
                hb = st.mean([(x[2] - x[1]) / 2 for x in eb.read_points])
                sgn = 1 if st.mean(pa) >= st.mean(pb) else -1
                ps = []
                for d in (-1, 1):
                    _, pq = t_and_p(lib, entry, st.mean(pa) + d * sgn * ha, st.stdev(pa), len(pa),
                                    st.mean(pb) - d * sgn * hb, st.stdev(pb), len(pb))
                    if pq is not None:
                        ps.append(pq)
                lo, hi = min(ps + [p]), max(ps + [p])
                v = p_from_interval(it.stats.p, lo, hi)
                alts.append({"entry": entry, "p": [round(lo, 6), round(hi, 6)], "verdict": v})
            else:
                v = judge_p(it.stats.p, p)
                alts.append({"entry": entry, "p": round(p, 6), "verdict": v})
            verdicts.append(v)
        if verdicts:
            out.append(Check("points to P", combine_alternatives(verdicts), iid, " / ".join(entries) + " + t_distribution",
                             alts, basis))
    return out


def p_from_interval(printed: str, lo: float, hi: float) -> str:
    """Judge a P interval from read values: within reading if any value in it agrees and the rest are close or agree."""
    if judge_p(printed, lo) == judge_p(printed, hi) == "consistent":
        return "consistent within reading"
    r = judge_p_range(printed, lo, hi)
    pp = parse_p(printed)
    if r == "consistent":
        return "consistent within reading" if pp.op == "=" else "close"
    return r


TK_STATED = {"welch_t": ("t_two_sample_welch",), "student_t": ("t_two_sample_pooled",)}


def statistic_to_p(iid, it, pp, lib) -> list[Check]:
    s = it.stats.statistic
    nums = numbers_in(s)
    low = s.lower()
    try:
        if low.strip().startswith("t") and it.stats.df:
            t = float(nums[-1]) if "=" in s else float(nums[0])
            df = float(numbers_in(it.stats.df)[0])
            lo, hi = interval(str(nums[-1] if "=" in s else nums[0]))
            ps = [evaluate(lib.get("t_distribution"), {"t": abs(x), "df": df}, "p") for x in (lo, hi)]
            vs = [judge_p_range(it.stats.p, min(ps), max(ps))]
            return [Check("statistic to P", combine_alternatives(vs), iid, "t_distribution",
                          [{"t": [lo, hi], "df": df, "p": [round(p, 6) for p in ps]}])]
        if low.strip().startswith("f") and it.stats.df:
            dfs = [float(x) for x in numbers_in(it.stats.df)[:2]]
            F = float(nums[-1])
            lo, hi = interval(nums[-1])
            ps = [evaluate(lib.get("f_distribution"), {"F": x, "df1": dfs[0], "df2": dfs[1]}, "p") for x in (lo, hi)]
            vs = [judge_p_range(it.stats.p, min(ps), max(ps))]
            return [Check("statistic to P", combine_alternatives(vs), iid, "f_distribution",
                          [{"F": [lo, hi], "df": dfs, "p": [round(p, 6) for p in ps]}])]
    except (ValueError, IndexError, TypeError):
        pass
    return [Check("statistic to P", "cannot check", iid, note=f"statistic {s!r} without degrees of freedom")]


def _anova(iid, groups, pp, lib) -> list[Check]:
    out = []
    if all(g.mean and g.spread and g.n for g in groups):
        verdicts, alts = [], []
        for sk in SPREAD_ALTS.get(groups[0].spread_kind, ["SD", "SEM"]):
            gs = [(float(g.mean), to_sd(float(g.spread), sk, g.n[0], lib), g.n[0]) for g in groups]
            F, p = anova_p(lib, gs)
            if p is not None:
                v = judge_p(pp.text, p)
                verdicts.append(v)
                alts.append({"spread": sk, "p": round(p, 6), "verdict": v})
        if verdicts:
            out.append(Check("summary to P", combine_alternatives(verdicts), iid, "one_way_anova_f + f_distribution", alts))
    pts = [g.data_points for g in groups]
    if all(len(p) >= 2 for p in pts):
        F, p = anova_p(lib, [(st.mean(x), st.stdev(x), len(x)) for x in pts])
        if p is not None:
            out.append(Check("points to P", judge_p(pp.text, p), iid, "one_way_anova_f + f_distribution",
                             [{"p": round(p, 6)}], "data"))
    return out
