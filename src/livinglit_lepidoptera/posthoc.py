"""Post-hoc pairs and two-way ANOVA effects, checked from points only (02-audit, Checks within a source; 04-formulas,
Statistical formulas; decision 23).

A printed post-hoc pair or two-way ANOVA effect is never rechecked with a two-group test. It is checked with its own
library entry, from released or read points, and only when the unit's groups determine the family: every
group of the unit has points for the measure (from the item or a sibling item of the same unit, measure and test).
Otherwise the check says cannot check and names what is missing.
"""
from __future__ import annotations

import math
import re
import statistics as st
from itertools import combinations, product

import numpy as np

from .formulas import evaluate
from .numbers import judge_p, parse_p, test_kind
from .text import normalize

CHECKED = {"tukey", "bonferroni", "sidak", "holm", "holm-sidak"}
WITHIN = re.compile(r"\bwithin (each|every)\b|\bfor each\b|\beach (loading|condition|level|group|time)", re.I)
NOT_IN_LIBRARY = re.compile(r"repeated|mixed|nested|ancova|three[\s-]?way|3[\s-]?way", re.I)


def _check(*a, **k):
    from .checks import Check
    return Check(*a, **k)


def _family_points(rec, iid, data_rows, readings, figures, drop_suspect):
    """group -> (points, basis) for the item's unit, from the item and its siblings (same unit, measure and test)."""
    from .checks import gather
    it = rec.evidence[iid]
    key = (it.unit, normalize(it.measure), normalize(it.stats.test))
    sibs = [k for k, x in rec.evidence.items()
            if (x.unit, normalize(x.measure), normalize(x.stats.test)) == key]
    sibs.sort(key=lambda k: k != iid)  # the item's own points first
    out = {}
    for k in sibs:
        for g, e in gather(rec, k, data_rows, readings, figures, drop_suspect=drop_suspect).items():
            if g in out or g == "_":
                continue
            if len(e.data_points) >= 2:
                out[g] = (list(e.data_points), "data", [])
            elif len(e.read_points) >= 2 and e.read_counts_exact:
                out[g] = ([p[0] for p in e.read_points], "readings", [(p[2] - p[1]) / 2 for p in e.read_points])
    return out, sibs


def _unit_groups(rec, unit):
    """The family is every group of the unit, benchmarks included: a post-hoc test runs over all groups in the ANOVA."""
    return list(rec.units[unit].groups)


def _msw(groups):
    N = sum(len(v) for v in groups.values())
    k = len(groups)
    ssw = sum(sum((x - st.mean(v)) ** 2 for x in v) for v in groups.values())
    return ssw / (N - k), N, k


def _judge(printed, p, basis, p_range=None):
    from .checks import p_from_interval
    if basis == "readings" and p_range is not None:
        return p_from_interval(printed, min(p_range + [p]), max(p_range + [p]))
    return judge_p(printed, p)


def _shifted(pts, a, b, half):
    """Points with groups a and b moved apart and together by their mean reading half-widths."""
    out = []
    ha = st.mean(half.get(a) or [0]) / math.sqrt(max(len(pts[a]), 1))
    hb = st.mean(half.get(b) or [0]) / math.sqrt(max(len(pts[b]), 1))
    s = 1 if st.mean(pts[a]) >= st.mean(pts[b]) else -1
    for d in (-1, 1):
        q = dict(pts)
        q[a] = [x + d * s * ha for x in pts[a]]
        q[b] = [x - d * s * hb for x in pts[b]]
        out.append(q)
    return out


def tukey_p(lib, pts, a, b, k_family=None):
    """MSW and its df from every group in `pts` (the full model); k is the family size."""
    msw, N, k_all = _msw(pts)
    k = k_family or k_all
    g = {"m1": st.mean(pts[a]), "m2": st.mean(pts[b]), "MSW": msw, "n1": len(pts[a]), "n2": len(pts[b]), "N": N, "k": k_all}
    q = evaluate(lib.get("tukey_kramer_q"), g, "q")
    return evaluate(lib.get("studentized_range_distribution"), {"q": q, "k": k, "df": N - k_all}, "p")


def games_howell_p(lib, pts, a, b, k):
    g = {"m1": st.mean(pts[a]), "m2": st.mean(pts[b]), "s1": st.stdev(pts[a]), "s2": st.stdev(pts[b]),
         "n1": len(pts[a]), "n2": len(pts[b])}
    q = evaluate(lib.get("games_howell_q"), g, "qgh")
    df = evaluate(lib.get("games_howell_q"), g, "df")
    return evaluate(lib.get("studentized_range_distribution"), {"q": q, "k": k, "df": df}, "p")


def welch_p(lib, pts, a, b):
    g = {"m1": st.mean(pts[a]), "m2": st.mean(pts[b]), "s1": st.stdev(pts[a]), "s2": st.stdev(pts[b]),
         "n1": len(pts[a]), "n2": len(pts[b])}
    t = evaluate(lib.get("t_two_sample_welch"), g, "t")
    df = evaluate(lib.get("t_two_sample_welch"), g, "df")
    return evaluate(lib.get("t_distribution"), {"t": abs(t), "df": df}, "p")


def pooled_t_p(lib, pts, a, b):
    msw, N, k = _msw(pts)
    t = (st.mean(pts[a]) - st.mean(pts[b])) / math.sqrt(msw * (1 / len(pts[a]) + 1 / len(pts[b])))
    return evaluate(lib.get("t_distribution"), {"t": abs(t), "df": N - k}, "p")


def adjusted_p(lib, method, pts, pair, family_pairs, unequal=False):
    """The adjusted P of `pair` among `family_pairs` (Bonferroni, Šidák single step; Holm, Holm–Šidák step-down);
    raw P from the t pooled over the unit, or from Welch's t when variances are not assumed equal."""
    m = len(family_pairs)
    raw = {pr: (welch_p if unequal else pooled_t_p)(lib, pts, *pr) for pr in family_pairs}
    if method == "bonferroni":
        return evaluate(lib.get("bonferroni_adjust"), {"p": raw[pair], "m": m}, "pb")
    if method == "sidak":
        return evaluate(lib.get("sidak_adjust"), {"p": raw[pair], "m": m}, "ps")
    entry, out = ("holm_step", "ph") if method == "holm" else ("holm_sidak_step", "phs")
    order = sorted(family_pairs, key=lambda pr: raw[pr])
    adj, run = {}, 0.0
    for i, pr in enumerate(order, 1):
        run = max(run, evaluate(lib.get(entry), {"p": raw[pr], "m": m, "i": i}, out))  # kept monotone by code
        adj[pr] = min(1.0, run)
    return adj[pair]


ENTRY = {"tukey": "tukey_kramer_q / games_howell_q + studentized_range_distribution",
         "bonferroni": "t pooled or Welch + t_distribution + bonferroni_adjust",
         "sidak": "t pooled or Welch + t_distribution + sidak_adjust",
         "holm": "t pooled or Welch + t_distribution + holm_step",
         "holm-sidak": "t pooled or Welch + t_distribution + holm_sidak_step"}


def pair_checks(rec, iid, lib, data_rows=(), readings=(), figures=None, drop_suspect=False) -> list:
    it = rec.evidence[iid]
    tk = test_kind(it.stats.test)
    pp = parse_p(it.stats.p)
    if pp is None or pp.op == "sig" or tk.posthoc is None:
        return []
    if NOT_IN_LIBRARY.search(it.stats.test):
        return [_check("points to P", "cannot check", iid, note=f"{it.stats.test}: repeated-measures and mixed models are "
                                                                f"not in the library")]
    if tk.posthoc not in CHECKED:
        return [_check("points to P", "cannot check", iid, note=f"{tk.posthoc} post-hoc test is not in the library")]
    a, b = it.compares
    pts, sibs = _family_points(rec, iid, data_rows, readings, figures, drop_suspect)
    fam = _unit_groups(rec, it.unit)
    missing = [g for g in fam if g not in pts]
    if missing or len(fam) < 3 or a not in pts or b not in pts:
        return [_check("points to P", "cannot check", iid, ENTRY[tk.posthoc],
                       note="family not determined: groups without points: " + (", ".join(missing) or "none")
                       + ("" if len(fam) >= 3 else "; fewer than three groups"))]
    P = {g: pts[g][0] for g in fam}
    half = {g: pts[g][2] for g in fam}
    basis = "readings" if any(pts[g][1] == "readings" for g in fam) else "data"
    alts, verdicts = [], []
    # in a factorial unit, a pair differing in one factor is also compared within the other factors' level
    within, within_label = None, None
    d, sigs = _design(rec, it.unit)
    if d is not None and a in d.groups and b in d.groups:
        fs = [f for f in d.factors if sigs[a][f] != sigs[b][f]]
        if len(fs) == 1:
            within = [g for g in d.groups if all(sigs[g][f] == sigs[a][f] for f in d.factors if f != fs[0])]
            within_label = "within " + ", ".join(f for f in d.factors if f != fs[0]) + " of the pair"
    only_within = within is not None and bool(WITHIN.search(it.stats.test))
    if tk.posthoc == "tukey":
        for label, k in ((None if only_within else "all groups of the unit", len(fam)), (within_label, len(within or []))):
            if label is None or k < 2:
                continue
            p = tukey_p(lib, P, a, b, k)
            rng = [tukey_p(lib, q, a, b, k) for q in _shifted(P, a, b, half)] if basis == "readings" else None
            v = _judge(it.stats.p, p, basis, rng)
            alts.append({"family": label, "k": k, "variance": "equal (Tukey–Kramer)", "p": round(p, 6), "verdict": v,
                         "added": within is not None})
            verdicts.append(v)
            if all(len(P[g]) >= 2 for g in (a, b)):
                p2 = games_howell_p(lib, P, a, b, k)
                rng2 = [games_howell_p(lib, q, a, b, k) for q in _shifted(P, a, b, half)] if basis == "readings" else None
                v2 = _judge(it.stats.p, p2, basis, rng2)
                alts.append({"family": label, "k": k, "variance": "unequal (Games–Howell)", "p": round(p2, 6),
                             "verdict": v2, "added": True})
                verdicts.append(v2)
    else:
        all_pairs = list(combinations(fam, 2))
        printed = []
        for k in sibs:
            c = rec.evidence[k].compares
            if isinstance(c, list) and len(c) == 2 and parse_p(rec.evidence[k].stats.p) is not None:
                pr = next((x for x in all_pairs if set(x) == set(c)), None)
                if pr and pr not in printed:
                    printed.append(pr)
        pair = next(x for x in all_pairs if set(x) == {a, b})
        fams = [] if only_within else [("all pairs of the unit", all_pairs), ("printed pairs", printed)]
        if within:
            fams.append((within_label, [x for x in combinations(within, 2)]))
        for label, family in fams:
            family = [next((y for y in all_pairs if set(y) == set(x)), x) for x in family]
            if pair not in family or (label == "printed pairs" and len(family) == len(all_pairs)):
                continue
            for unequal, vlabel in ((False, "equal (pooled t)"), (True, "unequal (Welch)")):
                p = adjusted_p(lib, tk.posthoc, P, pair, family, unequal)
                rng = [adjusted_p(lib, tk.posthoc, q, pair, family, unequal) for q in _shifted(P, a, b, half)] \
                    if basis == "readings" else None
                v = _judge(it.stats.p, p, basis, rng)
                alts.append({"family": label, "m": len(family), "variance": vlabel, "p": round(p, 6), "verdict": v,
                             "added": True})
                verdicts.append(v)
    from .checks import combine_alternatives
    return [_check("points to P", combine_alternatives(verdicts), iid, ENTRY[tk.posthoc], alts, basis,
                   note=f"{tk.posthoc} over {len(fam)} groups of unit {it.unit}")]


# ------------------------------------------------------------------ two-way ANOVA
def _design(rec, unit):
    from .groups import stated_signatures, unit_design, compound_signatures
    sigs = stated_signatures(rec, unit)
    d = unit_design(rec, unit, sigs)
    if not d.factorial:
        return None, None
    return d, compound_signatures(sigs, d.groups)


def _ss_terms(cells: dict, levels_a: list, levels_b: list):
    """Sums of squares for A, B and A×B from cell points by least squares with sum-to-zero coding.
    Returns {"II": {...}, "III": {...}}, SSE and its df."""
    y, Xa, Xb = [], [], []
    for (la, lb), pts in cells.items():
        for v in pts:
            y.append(v)
            Xa.append([1.0 if la == l else (-1.0 if la == levels_a[-1] else 0.0) for l in levels_a[:-1]])
            Xb.append([1.0 if lb == l else (-1.0 if lb == levels_b[-1] else 0.0) for l in levels_b[:-1]])
    y = np.array(y)
    A, B = np.array(Xa), np.array(Xb)
    AB = np.array([[a * b for a in ra for b in rb] for ra, rb in zip(Xa, Xb)])
    one = np.ones((len(y), 1))

    def sse(*blocks):
        X = np.hstack([one, *blocks])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        r = y - X @ beta
        return float(r @ r)
    full = sse(A, B, AB)
    add = sse(A, B)
    ss = {"III": {"a": sse(B, AB) - full, "b": sse(A, AB) - full, "ab": add - full},
          "II": {"a": sse(B) - add, "b": sse(A) - add, "ab": add - full}}
    return ss, full, len(y) - len(cells)


def two_way_checks(rec, iid, lib, data_rows=(), readings=(), figures=None, drop_suspect=False) -> list:
    it = rec.evidence[iid]
    kind = it.kind_of_test
    tk = test_kind(it.stats.test)
    pp = parse_p(it.stats.p)
    if kind not in ("main effect", "interaction") or pp is None or pp.op == "sig":
        return []
    if tk.family != "two_way_anova" or NOT_IN_LIBRARY.search(it.stats.test):
        return [_check("points to P", "cannot check", iid,
                       note=f"{kind} of {it.stats.test}: only an ordinary two-way ANOVA is in the library")]
    d, sigs = _design(rec, it.unit)
    if d is None or len(d.factors) != 2:
        return [_check("points to P", "cannot check", iid, "two_way_anova_f",
                       note="the unit's groups are not a two-factor factorial design")]
    pts, _ = _family_points(rec, iid, data_rows, readings, figures, drop_suspect)
    missing = [g for g in d.groups if g not in pts]
    if missing:
        return [_check("points to P", "cannot check", iid, "two_way_anova_f",
                       note="cells without points: " + ", ".join(missing))]
    fa, fb = d.factors
    la = sorted({sigs[g][fa] for g in d.groups}, key=str)
    lb = sorted({sigs[g][fb] for g in d.groups}, key=str)
    cells = {(sigs[g][fa], sigs[g][fb]): pts[g][0] for g in d.groups}
    if kind == "interaction":
        term = "ab"
    else:
        cond, ref = it.compares.condition, it.compares.reference
        term = None
        for t, f in (("a", fa), ("b", fb)):
            cv, rv = {sigs[g][f] for g in cond if g in sigs}, {sigs[g][f] for g in ref if g in sigs}
            if len(cv) == 1 and len(rv) == 1 and cv != rv:
                term = t
        if term is None:
            return [_check("points to P", "cannot check", iid, "two_way_anova_f",
                           note="the main effect's sides do not split one factor of the design")]
    ss, sse, dfe = _ss_terms(cells, la, lb)
    df_term = {"a": len(la) - 1, "b": len(lb) - 1, "ab": (len(la) - 1) * (len(lb) - 1)}[term]
    basis = "readings" if any(pts[g][1] == "readings" for g in d.groups) else "data"
    alts, verdicts = [], []
    types = ["III"] if abs(ss["III"][term] - ss["II"][term]) < 1e-9 * max(1.0, abs(ss["III"][term])) else ["II", "III"]
    for ty in types:
        F = evaluate(lib.get("two_way_anova_f"), {"SS": ss[ty][term], "df": df_term, "SSE": sse, "dfE": dfe}, "F")
        p = evaluate(lib.get("f_distribution"), {"F": F, "df1": df_term, "df2": dfe}, "p")
        v = judge_p(it.stats.p, p)
        if basis == "readings" and v != "consistent":
            v = "close" if v == "close" else v
        elif basis == "readings":
            v = "consistent within reading"
        alts.append({"sums of squares": f"type {ty}", "F": round(F, 4), "df": [df_term, dfe], "p": round(p, 6),
                     "verdict": v, "added": len(types) > 1})
        verdicts.append(v)
    from .checks import combine_alternatives
    name = {"a": fa, "b": fb, "ab": f"{fa} × {fb}"}[term]
    return [_check("points to P", combine_alternatives(verdicts), iid, "two_way_anova_f + f_distribution", alts, basis,
                   note=f"{'interaction' if term == 'ab' else 'main effect of ' + name} from {len(d.groups)} cells")]
