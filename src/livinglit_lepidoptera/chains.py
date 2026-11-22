"""Derivations evaluated along a chain (04-formulas, Checking a chain; Wrong derivations).

Inputs come from printed values, the means of data rows and readings, and other
derivations. The paper's formula is checked against its library entry
symbolically; numbers are rebuilt in SI and judged at printed precision. Values
rebuilt here are labelled derived by LivingLit. Every verdict names its formula.
"""
from __future__ import annotations

import math
import statistics as st
from dataclasses import dataclass, field

import sympy as sp

from .formulas import parse_rel, instantiate, follows, symtab, parse_expr
from .models import DerivedFile, Derivation, Record
from .numbers import parse_number, split_pm, judge_value, si_factor, parse_p, try_unit, interval
from .record import value_at


@dataclass
class ChainResult:
    key: str
    verdict: str  # consistent | close | inconsistent | cannot check
    library_verdict: str  # consistent | inconsistent | no formula | cannot check
    rebuilt: float | None = None
    rebuilt_unit: str | None = None
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    inputs_used: dict = field(default_factory=dict)
    interval: tuple | None = None
    interval_kind: str | None = None  # printed (last printed digits only) | read (reading uncertainty involved)

    def as_dict(self):
        d = {"derivation": self.key, "verdict": self.verdict, "library": self.library_verdict}
        if self.rebuilt is not None:
            d["rebuilt"] = {"value": float(f"{self.rebuilt:.6g}"), "unit": self.rebuilt_unit,
                            "origin": "derived by LivingLit"}
            if self.interval is not None:
                d["rebuilt"]["interval"] = [float(f"{self.interval[0]:.6g}"), float(f"{self.interval[1]:.6g}")]
        if self.flags:
            d["flags"] = self.flags
        if self.notes:
            d["notes"] = self.notes
        if self.inputs_used:
            d["inputs"] = self.inputs_used
        return d


def _mean_of_value(v, part):
    try:
        m, s = split_pm(v.printed)
    except ValueError:
        return None
    if part == "spread":
        return float(s) if s is not None else None
    return float(m)


INTERVALS: dict = {}
POINTS: dict = {}  # per-sample values of a data or reading input, for aggregation 'mean of per-sample'


def _same_x(a, b) -> bool:
    try:
        return abs(float(str(a).split()[0]) - float(str(b).split()[0])) < 1e-9
    except ValueError:
        return str(a).strip() == str(b).strip()


def _printed_part(printed: str, part):
    try:
        m, s = split_pm(printed)
    except ValueError:
        return None
    return s if part == "spread" else m


def _printed_interval(inp, text):
    """A stated input carries the interval of its last printed digit (04-formulas, Derivations)."""
    if text is None:
        return
    try:
        lo, hi = interval(text)
    except (ValueError, TypeError):
        return
    INTERVALS[id(inp)] = (lo, hi, "printed")


def input_value(rec: Record, df: DerivedFile, d: Derivation, name: str, inp, data_rows, readings, figures, done):
    """(value, unit, origin) of one input, or (None, None, reason)."""
    if inp.not_stated or inp.by_reference is not None:
        return None, None, "not stated" if inp.not_stated else "by reference"
    if inp.printed is not None:
        try:
            m = split_pm(inp.printed)[0]
        except ValueError:
            return None, None, f"cannot parse printed {inp.printed!r}"
        _printed_interval(inp, m)
        return float(m), inp.unit, "stated"
    if inp.value is not None:
        try:
            v = value_at(rec, inp.value)
        except KeyError:
            return None, None, f"no value {inp.value}"
        x = _mean_of_value(v, inp.part)
        _printed_interval(inp, _printed_part(v.printed, inp.part))
        return x, v.unit, "stated"
    if inp.item is not None:
        it = rec.evidence.get(inp.item)
        if it is None:
            return None, None, f"no item {inp.item}"
        vals = [v for v in it.values.values() if (d.group is None or v.group == d.group) and v.x is None]
        if len(vals) != 1:
            return None, None, f"item {inp.item} has {len(vals)} values for group {d.group}"
        _printed_interval(inp, _printed_part(vals[0].printed, inp.part))
        return _mean_of_value(vals[0], inp.part), vals[0].unit, "stated"
    if inp.data is not None:
        item, _, group = inp.data.partition("/")
        xm = lambda r: (r.x is None) if inp.x is None else (r.x is not None and _same_x(r.x, inp.x))
        pts = [float(r.value) for r in data_rows if r.item == item and r.group == group and r.kind == "point" and xm(r)]
        means = [r for r in data_rows if r.item == item and r.group == group and r.kind == "mean" and xm(r)]
        unit = next((r.unit for r in data_rows if r.item == item and r.group == group), None)
        if pts:
            POINTS[id(inp)] = pts
            return st.mean(pts), unit, "from data"
        if means:
            return float(means[0].value), unit, "from data"
        return None, None, f"no data rows {inp.data}"
    if inp.reading is not None:
        fig, _, label = inp.reading.partition("/")
        xm = lambda r: (r.x is None) if inp.x is None else (r.x is not None and _same_x(r.x, inp.x))
        pts = [r.value for r in readings if r.figure == fig and r.group == label and r.kind == "point" and xm(r)]
        bar = [r.value for r in readings if r.figure == fig and r.group == label and r.kind == "mean" and xm(r)]
        unit = None
        if figures is not None and fig in figures.figures and label in figures.figures[fig].groups:
            unit = figures.figures[fig].groups[label].unit_of_value
        rows = [r for r in readings if r.figure == fig and r.group == label and xm(r)]
        if pts:
            POINTS[id(inp)] = list(pts)
            p_rows = [r for r in rows if r.kind == "point"]
            half = st.mean([(r.hi - r.lo) / 2 for r in p_rows]) / math.sqrt(len(p_rows))
            INTERVALS[id(inp)] = (st.mean(pts) - half, st.mean(pts) + half, "read")
            return st.mean(pts), unit, "read"
        if bar:
            b = [r for r in rows if r.kind == "mean"][0]
            INTERVALS[id(inp)] = (b.lo, b.hi, "read")
            return bar[0], unit, "read"
        return None, None, f"no readings {inp.reading}"
    if inp.derived is not None:
        r = done.get(inp.derived)
        if r is None or r.rebuilt is None:
            return None, None, f"derivation {inp.derived} has no value"
        return r.rebuilt, r.rebuilt_unit, "derived by LivingLit"
    return None, None, "no source"


def judge_rebuilt(printed_mean: str, x: float, ivl, kind) -> str:
    """A printed value against a rebuilt one: at printed precision, or consistent when the rebuilt interval holds it
    (printed-precision intervals only) or consistent within reading (reading uncertainty involved)."""
    v = judge_value(printed_mean, x)
    if v != "consistent" and ivl is not None:
        plo, phi = interval(printed_mean.lstrip("~≈"))
        if plo <= ivl[1] and ivl[0] <= phi:
            return "consistent" if kind == "printed" else "consistent within reading"
    return v


def library_consistency(d: Derivation, lib) -> tuple[str, str | None]:
    """Is the paper's stated formula consistent with its library entry (symbolically, no numbers)?"""
    if d.library is None:
        return "no formula", None
    e = lib.get(d.library.formula)
    if e is None:
        return "cannot check", f"{d.library.formula} is not in the library"
    if d.library.formula in lib.suspect:
        return "cannot check", f"{d.library.formula} is held as suspect and not applied"
    if d.formula.strip() == "not stated" or "=" not in d.formula:
        return "cannot check", "formula not stated"
    try:
        prem = instantiate(e, d.library.vars, positive=True)
        names = set(d.inputs) | {d.formula.split("=")[0].strip()}
        syms = symtab(names | set(d.library.vars.values()), positive=True)
        lhs, op, rhs = parse_rel(d.formula, syms)
        ok = follows(prem, lhs - rhs)
    except Exception as ex:
        return "cannot check", f"cannot compare formulas ({ex})"
    return ("consistent", None) if ok else ("inconsistent", lib.flag_text(d.library.formula))


def evaluate_derivation(rec, df, key, d: Derivation, lib, data_rows, readings, figures, done) -> ChainResult:
    lv, flag = library_consistency(d, lib)
    res = ChainResult(key, "cannot check", lv)
    if flag:
        res.flags.append(flag) if lv == "inconsistent" else res.notes.append(flag)
    if d.formula.strip() == "not stated" or "=" not in d.formula:
        res.notes.append("formula not stated: nothing to rebuild")
        return res
    out_name, expr_text = [x.strip() for x in d.formula.split("=", 1)]
    vals, units, ivals, ikinds = {}, {}, {}, set()
    per_sample = {}
    for name, inp in d.inputs.items():
        INTERVALS.pop(id(inp), None)
        POINTS.pop(id(inp), None)
        v, u, origin = input_value(rec, df, d, name, inp, data_rows, readings, figures, done)
        if id(inp) in POINTS:
            per_sample[name] = (POINTS.pop(id(inp)), si_factor(u) or 1.0)
        if id(inp) in INTERVALS:
            lo, hi, kind = INTERVALS.pop(id(inp))
            ivals[name] = (lo, hi)
            ikinds.add(kind)
        elif inp.derived and done.get(inp.derived) is not None and done[inp.derived].interval is not None:
            ivals[name] = done[inp.derived].interval
            ikinds.add(done[inp.derived].interval_kind or "read")
        if v is None:
            res.notes.append(f"input {name}: {origin}")
            continue
        f = si_factor(u)
        if f is None and u not in (None, "", "dimensionless", "a.u.", "count", "fold"):
            res.notes.append(f"input {name}: unit {u!r} not known; used as printed")
        vals[name] = v * (f or 1.0)
        if name in ivals:
            ivals[name] = (ivals[name][0] * (f or 1.0), ivals[name][1] * (f or 1.0))
        units[name] = u
        res.inputs_used[name] = {"value": float(f"{v:.6g}"), "unit": u, "origin": origin}
    try:
        expr = parse_expr(expr_text, list(d.inputs))
    except Exception as ex:
        res.notes.append(f"cannot parse formula ({ex})")
        return res
    missing = {str(s) for s in expr.free_symbols} - set(vals)
    if missing:
        res.notes.append(f"cannot rebuild: {', '.join(sorted(missing))} not available")
        return res
    try:
        x = float(expr.xreplace({sp.Symbol(k, real=True): v for k, v in vals.items()}).evalf())
    except Exception as ex:
        res.notes.append(f"cannot evaluate ({ex})")
        return res
    out_unit = d.output_unit
    if d.output:
        try:
            ov = value_at(rec, d.output)
            out_unit = out_unit or ov.unit
        except KeyError:
            res.notes.append(f"output {d.output} not found")
            ov = None
    else:
        ov = None
    fo = si_factor(out_unit) or 1.0
    res.rebuilt, res.rebuilt_unit = x / fo, out_unit
    if ivals:  # carry reading uncertainty: evaluate at the corners of the input intervals
        from itertools import product
        names = list(ivals)[:8]
        outs = []
        for corner in product(*[ivals[n] for n in names]):
            sub = dict(vals)
            sub.update(dict(zip(names, corner)))
            try:
                outs.append(float(expr.xreplace({sp.Symbol(k, real=True): v for k, v in sub.items()}).evalf()) / fo)
            except Exception:
                pass
        if outs:
            res.interval = (min(outs + [res.rebuilt]), max(outs + [res.rebuilt]))
            res.interval_kind = "read" if "read" in ikinds else "printed"
    mps = None
    if d.aggregation in ("mean of per-sample", "not stated"):
        lens = {len(v[0]) for v in per_sample.values()}
        if per_sample and len(lens) == 1 and min(lens) >= 2:
            n = lens.pop()
            outs = []
            for i in range(n):
                sub = dict(vals)
                sub.update({k: pts[i] * f for k, (pts, f) in per_sample.items()})
                try:
                    outs.append(float(expr.xreplace({sp.Symbol(k, real=True): v for k, v in sub.items()}).evalf()) / fo)
                except Exception:
                    pass
            if len(outs) == n:
                mps = st.mean(outs)
        if mps is None:
            res.notes.append("mean of per-sample: per-sample inputs with equal counts are not available")
    if d.aggregation == "mean of per-sample":
        if mps is None:
            res.rebuilt = None
            return res
        res.rebuilt, res.interval = mps, None
        res.notes.append("aggregation: mean of per-sample")
    if ov is not None:
        try:
            m, _ = split_pm(ov.printed)
            if parse_number(ov.printed)[1]:
                m = "~" + m  # approximate as printed (02-audit, Values)
            of_means = res.rebuilt
            res.verdict = judge_rebuilt(m, res.rebuilt, res.interval, res.interval_kind)
            if d.aggregation == "not stated" and mps is not None:
                from .checks import combine_alternatives
                shifted = None if res.interval is None else (res.interval[0] + mps - of_means, res.interval[1] + mps - of_means)
                v2 = judge_rebuilt(m, mps, shifted, res.interval_kind)
                res.notes.append(f"aggregation not stated: of means {res.rebuilt:.4g} ({res.verdict}); "
                                 f"mean of per-sample {mps:.4g} ({v2})")
                res.verdict = combine_alternatives([res.verdict, v2])
        except ValueError:
            res.notes.append(f"output {ov.printed!r} has no single value")
        if res.verdict == "inconsistent" and float(m.lstrip("~")) != 0:
            ratio = res.rebuilt / float(m.lstrip("~"))
            for k in (2, 0.5, 1000, 0.001, 1e6, 1e-6, 100, 0.01):
                if abs(ratio - k) / k < 0.02:
                    res.flags.append(f"constant factor {k:g} between printed and rebuilt value: conclusion unaffected "
                                     f"(constant_scaling_t), absolute values off")
                    break
    return res


def scaling_checks(rec: Record, df: DerivedFile, lib) -> list[dict]:
    """P for a derived measure and its input must match when the scaling parameter is one constant
    (constant_scaling_t). A disagreement rules out a constant parameter (04-formulas, Statistical formulas)."""
    out = []
    for key, d in df.derived.items():
        items = [i.item for i in d.inputs.values() if i.item]
        consts = [n for n, i in d.inputs.items() if not i.item and i.kind in ("constant", "not stated")]
        if len(items) != 1 or not consts:
            continue
        a, b = rec.evidence.get(d.item), rec.evidence.get(items[0])
        if a is None or b is None:
            continue
        pa, pb = parse_p(a.stats.p), parse_p(b.stats.p)
        if pa is None or pb is None or a.kind_of_test != "pair" or b.kind_of_test != "pair":
            continue
        same = pa.significant == pb.significant
        kinds = {n: d.inputs[n].kind for n in consts}
        verdict = "consistent" if same else ("inconsistent" if all(k == "constant" for k in kinds.values()) else "close")
        note = (f"P {a.stats.p!r} ({d.item}) vs {b.stats.p!r} ({items[0]}); parameters {kinds}" +
                ("" if same else ": differ in significance, so the parameter cannot be one constant"))
        out.append({"check": "P along a constant scaling", "derivation": key, "verdict": verdict,
                    "entry": "constant_scaling_t", "note": note})
    return out


def _group_n(item, group) -> list[int]:
    """The exact n a printed n allows for one group of an item ([] when not stated or not exact)."""
    from .checks import parse_n
    if item is None or item.n == "not stated":
        return []
    per = item.n.per_group or {}
    if per:
        return parse_n(per[group]) if group in per else []
    return parse_n(item.n.printed)


def same_n_checks(rec: Record, df: DerivedFile) -> list[dict]:
    """A derived value carries the n of the measured (per-sample) input it is computed from, for the same group: equal
    is consistent, a larger derived n is inconsistent, a smaller one (a subset) cannot be checked. Constant inputs
    carry no n (04-formulas, Checking a chain)."""
    out = []
    for key, d in df.derived.items():
        n_out = _group_n(rec.evidence.get(d.item), d.group)
        if len(n_out) != 1:
            continue
        for name, i in d.inputs.items():
            src = i.item or (i.value.split(".")[0] if i.value else None) or (i.data.split("/")[0] if i.data else None)
            if src is None or src == d.item or i.kind == "constant":
                continue
            n_in = _group_n(rec.evidence.get(src), d.group)
            if len(n_in) != 1:
                continue
            note = f"n {n_out[0]} for {d.item}/{d.group} vs n {n_in[0]} for input {name} ({src})"
            if n_out == n_in:
                verdict = "consistent"
            elif n_out[0] > n_in[0]:
                verdict = "inconsistent"  # more derived samples than measured ones
            else:
                verdict, note = "cannot check", note + ": derived on a subset of the input's samples"
            out.append({"check": "same n along the chain", "derivation": key, "verdict": verdict, "note": note})
    return out


def run_chains(rec, df: DerivedFile | None, lib, data_rows=(), readings=(), figures=None) -> dict[str, ChainResult]:
    done: dict[str, ChainResult] = {}
    if df is None:
        return done
    pending = dict(df.derived)
    for _ in range(len(pending) + 1):
        progressed = False
        for key, d in list(pending.items()):
            deps = [i.derived for i in d.inputs.values() if i.derived]
            if all(x in done or x not in df.derived for x in deps):
                done[key] = evaluate_derivation(rec, df, key, d, lib, data_rows, readings, figures, done)
                pending.pop(key)
                progressed = True
        if not progressed:
            break
    for key in pending:
        done[key] = ChainResult(key, "cannot check", "cannot check", notes=["circular derivations"])
    return done


def bound_checks(rec, df: DerivedFile | None, lib) -> list[dict]:
    out = []
    if df is None:
        return out
    for b in df.bounds:
        e = lib.get(b.formula)
        try:
            v = value_at(rec, b.value)
            m, _ = split_pm(v.printed)
        except (KeyError, ValueError):
            out.append({"check": "bound", "target": b.value, "verdict": "cannot check", "entry": b.formula})
            continue
        x = float(m) * (0.01 if "%" in (v.unit or "") or "%" in v.printed else 1.0)
        var = next(iter(e.variables)) if e else None
        ok = True
        if e:
            syms = symtab(e.variables)
            for s in e.equations:
                lhs, op, rhs = parse_rel(s, syms)
                expr_l, expr_r = (sp.sympify(lhs).xreplace({syms[var]: sp.Float(x)}),
                                  sp.sympify(rhs).xreplace({syms[var]: sp.Float(x)}))
                if expr_l.free_symbols or expr_r.free_symbols:
                    continue
                l, r = float(expr_l), float(expr_r)
                ok &= {"<": l < r, ">": l > r, "<=": l <= r, ">=": l >= r, "=": abs(l - r) < 1e-12}.get(op, True)
        out.append({"check": "bound", "target": b.value, "verdict": "consistent" if ok else "inconsistent",
                    "entry": b.formula, "note": "" if ok else lib.flag_text(b.formula)})
    return out


def assumption_verdicts(df: DerivedFile | None, lib, rec) -> list[dict]:
    """Code decides from what the agent reports: held, failed, or not stated (04-formulas, The formula agent)."""
    out = []
    if df is None:
        return out
    for key, rep in df.assumptions.items():
        for name, r in rep.assumptions.items():
            reported = r.get("reported")
            if reported in (None, "not stated"):
                out.append({"derivation": key, "model": rep.model, "assumption": name, "verdict": "not stated"})
                continue
            verdict = "reported"
            limit = r.get("limit")  # {"ratio": [num, den], "max": 0.1}
            if isinstance(limit, dict) and "ratio" in limit and "max" in limit:
                try:
                    num = float(split_pm(value_at(rec, limit["ratio"][0]).printed)[0])
                    den = float(split_pm(value_at(rec, limit["ratio"][1]).printed)[0])
                    verdict = "holds" if num / den <= float(limit["max"]) else "fails"
                except (KeyError, ValueError, ZeroDivisionError):
                    verdict = "reported"
            out.append({"derivation": key, "model": rep.model, "assumption": name, "verdict": verdict})
    return out
