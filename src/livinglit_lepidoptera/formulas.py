"""The formula library (04-formulas, The formula library; New formulas; Statistical formulas).

Four kinds: definition, model and bound are given with a citation; derived
entries are proved by code from accepted entries (Groebner reduction for
polynomial systems; substitution confirmed numerically otherwise). Dimensions are
checked structurally in every equation; a variable of dimension D, D2… means "the
same dimension as the other D variables". Distribution functions are named
functions evaluated numerically. holds_under is collected by code from premises.
The library is an append-only log; one file per entry is written by code.
"""
from __future__ import annotations

import random
import re
from pathlib import Path

import sympy as sp
import yaml
from scipy import stats as sst

from . import FIELDS_DIR, DEFAULT_FIELD
from .models import FormulaEntry

M, L, T, I, N, TH = sp.symbols("M L T I N Theta", positive=True)
DIMS = {
    "dimensionless": sp.Integer(1), "count": sp.Integer(1), "1": sp.Integer(1), "angle": sp.Integer(1),
    "mass": M, "length": L, "time": T, "current": I, "amount": N, "temperature": TH,
    "area": L**2, "volume": L**3, "frequency": 1 / T, "rate": 1 / T, "velocity": L / T,
    "force": M * L / T**2, "pressure": M / (L * T**2), "stress": M / (L * T**2), "modulus": M / (L * T**2),
    "energy": M * L**2 / T**2, "power": M * L**2 / T**3, "voltage": M * L**2 / (T**3 * I),
    "concentration": N / L**3, "stiffness": M / T**2, "charge": I * T, "second_moment": L**4,
    "capacitance": I**2 * T**4 / (M * L**2), "current_density": I / L**2, "fluorescence": sp.Integer(1),
}
DIMVAR = re.compile(r"\bD\d*\b")
REL = re.compile(r"(<=|>=|==|=|<|>)")


# named distribution functions: P from a statistic and degrees of freedom (models, under normality and independence)
class tdist_p2(sp.Function):
    """Two-sided P of Student's t with df degrees of freedom."""
    @classmethod
    def eval(cls, t, df):
        if t.is_Number and df.is_Number:
            return sp.Float(2 * sst.t.sf(abs(float(t)), float(df)))


class fdist_p(sp.Function):
    @classmethod
    def eval(cls, f, d1, d2):
        if f.is_Number and d1.is_Number and d2.is_Number:
            return sp.Float(sst.f.sf(float(f), float(d1), float(d2)))


class chi2_p(sp.Function):
    @classmethod
    def eval(cls, x, df):
        if x.is_Number and df.is_Number:
            return sp.Float(sst.chi2.sf(float(x), float(df)))


class norm_p2(sp.Function):
    @classmethod
    def eval(cls, z):
        if z.is_Number:
            return sp.Float(2 * sst.norm.sf(abs(float(z))))


class tq975(sp.Function):
    """The 97.5 % quantile of Student's t (for a CI95 half-width)."""
    @classmethod
    def eval(cls, df):
        if df.is_Number:
            return sp.Float(sst.t.ppf(0.975, float(df)))


class qrange_p(sp.Function):
    """Upper-tail P of the studentized range q for k means and df degrees of freedom (Tukey HSD)."""
    @classmethod
    def eval(cls, q, k, df):
        if q.is_Number and k.is_Number and df.is_Number:
            return sp.Float(sst.studentized_range.sf(float(q), float(k), float(df)))


FUNCS = {"qrange_p": qrange_p, "Min": sp.Min, "tdist_p2": tdist_p2, "fdist_p": fdist_p, "chi2_p": chi2_p, "norm_p2": norm_p2, "tq975": tq975,
         "sqrt": sp.sqrt, "exp": sp.exp, "log": sp.log, "pi": sp.pi, "Abs": sp.Abs}


class DimMismatch(Exception):
    pass


def dim_of(s: str) -> sp.Expr:
    s = str(s).replace("^", "**")
    names = {k: sp.Symbol(k) for k in DIMS}
    for d in set(DIMVAR.findall(s)):
        names[d] = sp.Symbol(f"dimvar_{d}", positive=True)
    expr = sp.sympify(s, locals=names)
    return sp.simplify(expr.subs({sp.Symbol(k): v for k, v in DIMS.items()}))


def dimension(expr, dmap):
    if expr.is_Number or expr.is_NumberSymbol:
        return sp.Integer(1)
    if expr.is_Symbol:
        return dmap.get(expr, sp.Integer(1))
    if expr.is_Add:
        ds = {sp.simplify(dimension(a, dmap)) for a in expr.args}
        if len(ds) > 1:
            raise DimMismatch(sorted(map(str, ds)))
        return ds.pop()
    if expr.is_Mul:
        out = sp.Integer(1)
        for a in expr.args:
            out *= dimension(a, dmap)
        return sp.simplify(out)
    if expr.is_Pow:
        base = dimension(expr.base, dmap)
        if expr.base.is_number:
            if sp.simplify(dimension(expr.exp, dmap)) != 1:
                raise DimMismatch([f"exponent {expr.exp} is not dimensionless"])
            return sp.Integer(1)
        if base != 1 and not expr.exp.is_number:
            raise DimMismatch([f"exponent of a dimensional base: {expr}"])
        return sp.simplify(base ** expr.exp)
    if isinstance(expr, sp.Abs):
        return dimension(expr.args[0], dmap)
    if expr.is_Function:
        for a in expr.args:
            if sp.simplify(dimension(a, dmap)) != 1:
                raise DimMismatch([f"argument of {expr.func} is not dimensionless"])
        return sp.Integer(1)
    return sp.Integer(1)


def symtab(names, positive=False) -> dict:
    return {v: sp.Symbol(v, positive=True) if positive else sp.Symbol(v, real=True) for v in names}


def parse_rel(s: str, syms: dict):
    parts = REL.split(s, maxsplit=1)
    if len(parts) != 3:
        raise ValueError(f"not an equation or inequality: {s!r}")
    loc = {**FUNCS, **syms}
    lhs = sp.sympify(parts[0].replace("^", "**"), locals=loc)
    rhs = sp.sympify(parts[2].replace("^", "**"), locals=loc)
    return lhs, parts[1], rhs


def parse_expr(s: str, names) -> sp.Expr:
    """A stated formula: pi, exp, log, sqrt are constants and functions; every other name is a variable (04-formulas)."""
    toks = set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", s)) - set(FUNCS)
    syms = {t: sp.Symbol(t, real=True) for t in toks | set(names)}
    return sp.sympify(s.replace("^", "**"), locals={**FUNCS, **syms})


def instantiate(entry: FormulaEntry, subs: dict, positive=True) -> list:
    vs = symtab(entry.variables, positive)
    ren = {vs[k]: sp.Symbol(str(v), positive=True) if positive else sp.Symbol(str(v), real=True)
           for k, v in (subs or {}).items() if k in vs}
    out = []
    for s in entry.equations:
        lhs, op, rhs = parse_rel(s, vs)
        if op in ("=", "=="):
            out.append((lhs - rhs).xreplace(ren))
    return out


def _is_poly(exprs) -> bool:
    try:
        return all(sp.together(e).as_numer_denom()[0].is_polynomial(*e.free_symbols) for e in exprs)
    except Exception:
        return False


def follows(premises: list, target) -> bool:
    """Does target = 0 follow from premises = 0? Groebner for polynomials, substitution otherwise (04-formulas)."""
    gens = sorted(set().union(*[p.free_symbols for p in premises], target.free_symbols), key=str)
    if premises and _is_poly(premises + [target]):
        try:
            P = [sp.numer(sp.together(p)) for p in premises]
            G = sp.groebner(P, *gens, order="lex")
            if G.reduce(sp.expand(sp.numer(sp.together(target))))[1] == 0:
                return True
        except Exception:
            pass
    subs: dict = {}
    for p in premises:
        e = p.xreplace(subs)
        num = sp.numer(sp.together(e))

        def linear_first(s):
            try:
                return (0 if sp.degree(num, s) == 1 else 1, str(s))
            except Exception:
                return (1, str(s))
        for s in sorted(e.free_symbols, key=linear_first):
            if s in subs:
                continue
            try:
                sol = sp.solve(e, s, dict=False)
            except Exception:
                continue
            sol = [x for x in sol if x != 0]
            if len(sol) == 1:
                subs = {k: v.xreplace({s: sol[0]}) for k, v in subs.items()}
                subs[s] = sol[0]
                break
    t = sp.simplify(target.xreplace(subs))
    if t == 0:
        return True
    rnd = random.Random(7)
    free = sorted(t.free_symbols, key=str)
    for _ in range(6):
        vals = {s: rnd.uniform(0.5, 3.0) for s in free}
        try:
            if abs(complex(t.evalf(subs=vals))) > 1e-9:
                return False
        except Exception:
            return False
    return True


# -------------------------------------------------------------------- library
class Library:
    def __init__(self, entries: dict[str, FormulaEntry] | None = None, version: int = 0, suspect=()):
        self.entries = dict(entries or {})
        self.version = version
        self.suspect = set(suspect)

    def __contains__(self, k):
        return k in self.entries

    def get(self, k):
        return self.entries.get(k)

    def holds_under(self, name: str, seen=None) -> list[str]:
        e = self.entries[name]
        seen = seen if seen is not None else set()
        out = list(e.assumes) if e.kind == "model" else [a for a in e.assumes if "=" not in a]
        for u in e.uses:
            if u.formula in self.entries and u.formula not in seen:
                seen.add(u.formula)
                out += self.holds_under(u.formula, seen)
        return sorted(set(out))

    def premises(self, name: str) -> list[str]:
        e = self.entries[name]
        return [f"{u.formula} ({self.entries[u.formula].kind})" for u in e.uses if u.formula in self.entries]

    def flag_text(self, name: str, what: str = "inconsistent with") -> str:
        e = self.entries[name]
        word = {"definition": "contradicts definition", "model": "inconsistent with model",
                "bound": "outside bound", "derived": "inconsistent with derived formula"}[e.kind]
        hu = self.holds_under(name)
        tail = f" (holds under: {', '.join(hu)})" if hu else ""
        prem = self.premises(name)
        chain = f" ← {' + '.join(prem)}" if prem else ""
        return f"{word}: {name}{tail}{chain}"


def check_entry(e: FormulaEntry, lib: Library, vocab=None) -> list[str]:
    """Every proposed formula must pass, all by code (04-formulas, New formulas)."""
    probs: list[str] = []
    name = e.formula
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        probs.append(f"{name}: names are snake_case")
    if name in lib.entries:
        probs.append(f"{name}: already in the library")
    try:
        dmap = {sp.Symbol(k, real=True): dim_of(v) for k, v in e.variables.items()}
    except Exception as ex:
        return [f"{name}: cannot read variable dimensions ({ex})"]
    vs = symtab(e.variables)
    rels = []
    for s in e.equations:
        try:
            lhs, op, rhs = parse_rel(s, vs)
        except Exception as ex:
            probs.append(f"{name}: cannot parse {s!r} ({ex})")
            continue
        free = (lhs - rhs).free_symbols - set(vs.values())
        if free:
            probs.append(f"{name}: {s!r} uses undeclared variables {sorted(map(str, free))}")
            continue
        try:
            dl = dimension(lhs, dmap) if lhs != 0 else None
            dr = dimension(rhs, dmap) if rhs != 0 else None
            if dl is not None and dr is not None and sp.simplify(dl / dr) != 1:
                probs.append(f"{name}: dimensions disagree in {s!r}: {dl} vs {dr}")
        except DimMismatch as ex:
            probs.append(f"{name}: dimensions disagree in {s!r}: {ex.args[0]}")
        rels.append((lhs, op, rhs))
    if not rels:
        probs.append(f"{name}: no equations")
    ineq = any(op in ("<", ">", "<=", ">=") for _, op, _ in rels)
    if e.kind == "bound" and not ineq:
        probs.append(f"{name}: a bound needs an inequality")
    if e.kind == "derived" and ineq:
        probs.append(f"{name}: derived inequalities are not proved by code yet; propose it as a cited bound")
    if e.kind in ("definition", "model", "bound"):
        if e.cites is None or not (e.cites.quote or e.cites.url or e.cites.anchor):
            probs.append(f"{name}: a given entry needs cites with a quote, url or anchor to a source that states it")
        if e.uses:
            probs.append(f"{name}: only a derived entry has premises (uses)")
    if e.kind == "model" and not e.assumes:
        probs.append(f"{name}: a model states its assumptions")
    if e.kind == "derived":
        if not e.uses:
            probs.append(f"{name}: a derived entry names its premises in uses")
        prem = []
        for u in e.uses:
            p = lib.get(u.formula)
            if p is None:
                probs.append(f"{name}: premise {u.formula} is not an accepted entry")
                continue
            if u.formula in lib.suspect:
                probs.append(f"{name}: premise {u.formula} is held as suspect")
            prem += instantiate(p, u.subs)
        pvs = symtab(e.variables, positive=True)
        for a in e.assumes:
            if "=" in a and not any(x in a for x in "<>"):
                try:
                    lhs, _, rhs = parse_rel(a, pvs)
                    prem.append(lhs - rhs)
                except Exception as ex:
                    probs.append(f"{name}: cannot parse assumption {a!r} ({ex})")
        if prem and not probs:
            for s in e.equations:
                lhs, op, rhs = parse_rel(s, pvs)
                if op in ("=", "==") and not follows(prem, lhs - rhs):
                    probs.append(f"{name}: {s} does not follow from its premises")
    if vocab is not None:
        for f, terms in e.applies_when.items():
            if f not in vocab.fields:
                probs.append(f"{name}: applies_when names field {f!r}, not in the vocabulary")
            for t in terms:
                if t not in vocab.terms:
                    probs.append(f"{name}: applies_when names {t!r}, not a vocabulary term")
    if not (e.does_not_apply or any(t.does_not_apply for t in e.tests)):
        probs.append(f"{name}: needs a case where it does not apply (does_not_apply)")
    probs += run_tests(e)
    # no contradiction: the combined equations still have a positive solution
    if not probs and e.kind != "bound":
        probs += contradiction(e, lib)
    return probs


def run_tests(e: FormulaEntry) -> list[str]:
    probs = []
    vs = symtab(e.variables)
    ran = 0
    for t in e.tests:
        if t.does_not_apply:
            continue
        ran += 1
        vals = {**t.given, **t.expect}
        sub = {vs[k]: sp.Float(v) for k, v in vals.items() if k in vs}
        for s in e.equations:
            lhs, op, rhs = parse_rel(s, vs)
            if not (lhs - rhs).free_symbols <= set(sub):
                continue
            l, r = complex(lhs.xreplace(sub).evalf()), complex(rhs.xreplace(sub).evalf())
            if op in ("=", "=="):
                if abs(l - r) > 1e-6 * max(1.0, abs(l), abs(r)):
                    probs.append(f"{e.formula}: test {vals} fails {s!r} ({l.real:.6g} vs {r.real:.6g})")
            else:
                ok = {"<": l.real < r.real, ">": l.real > r.real, "<=": l.real <= r.real, ">=": l.real >= r.real}[op]
                if not ok:
                    probs.append(f"{e.formula}: test {vals} fails {s!r}")
    if ran == 0:
        probs.append(f"{e.formula}: needs at least one test where it applies")
    return probs


def contradiction(e: FormulaEntry, lib: Library) -> list[str]:
    """The entry's equations, with its tests' values, must not contradict entries sharing its variable names."""
    vs = symtab(e.variables)
    for t in e.tests:
        if t.does_not_apply:
            continue
        vals = {**t.given, **t.expect}
        for other in lib.entries.values():
            if other.kind == "bound" or set(other.variables) != set(e.variables):
                continue
            ovs = symtab(other.variables)
            sub = {ovs[k]: sp.Float(v) for k, v in vals.items() if k in ovs}
            for s in other.equations:
                lhs, op, rhs = parse_rel(s, ovs)
                if op in ("=", "==") and (lhs - rhs).free_symbols <= set(sub):
                    d = complex((lhs - rhs).xreplace(sub).evalf())
                    if abs(d) > 1e-6 * max(1.0, abs(complex(lhs.xreplace(sub).evalf()))):
                        return [f"{e.formula}: contradicts {other.formula} on its own test values"]
    return []


def evaluate(e: FormulaEntry, given: dict[str, float], want: str) -> float | None:
    """Evaluate an entry's explicit equations ('v = expr') in order until `want` is known."""
    vs = symtab(e.variables)
    known = {k: v for k, v in given.items() if k in vs}
    for _ in range(len(e.equations) + 1):
        for s in e.equations:
            lhs, op, rhs = parse_rel(s, vs)
            if op not in ("=", "==") or not lhs.is_Symbol or str(lhs) in known:
                continue
            if {str(x) for x in rhs.free_symbols} <= set(known):
                val = rhs.xreplace({vs[k]: sp.Float(v) for k, v in known.items()}).evalf()
                try:
                    known[str(lhs)] = float(val)
                except TypeError:
                    return None
        if want in known:
            return known[want]
    return known.get(want)


# -------------------------------------------------------------------- files
def _dump(o) -> str:
    return yaml.safe_dump(o, sort_keys=False, allow_unicode=True, width=120)


def load_log(d: Path) -> list[dict]:
    p = d / "changes.yaml"
    return (yaml.safe_load(p.read_text()) or []) if p.exists() else []


def load_library(field: str = DEFAULT_FIELD, root: Path = FIELDS_DIR) -> Library:
    """The field's library extends fields/_shared/formulas (04-formulas, Shared across fields)."""
    lib = Library()
    for d in (root / "_shared" / "formulas", root / field / "formulas"):
        for ver in load_log(d):
            for ev in ver.get("events", []):
                if ev["event"] == "add":
                    e = FormulaEntry.model_validate(ev["entry"])
                    lib.entries[e.formula] = e
                elif ev["event"] == "suspect":
                    lib.suspect.add(ev["formula"])
                elif ev["event"] == "revoke":
                    lib.entries.pop(ev["formula"], None)
            if d.parent.name == field:
                lib.version = max(lib.version, int(ver["version"]))
    return lib


def append_entries(entries: list[FormulaEntry], d: Path, paper: str | None, agent: dict | None = None) -> int | None:
    if not entries:
        return None
    log = load_log(d)
    version = (log[-1]["version"] if log else 0) + 1
    log.append({"version": version, "paper": paper, "agent": agent,
                "events": [{"event": "add", "entry": e.model_dump(exclude_none=True, exclude_defaults=True)
                            | {"formula": e.formula, "kind": e.kind}} for e in entries]})
    d.mkdir(parents=True, exist_ok=True)
    (d / "changes.yaml").write_text("# Append-only log of accepted formula entries (04-formulas). Entry files are rebuilt from it.\n" + _dump(log))
    write_entry_files(d)
    return version


def write_entry_files(d: Path) -> None:
    for ver in load_log(d):
        for ev in ver.get("events", []):
            if ev["event"] == "add":
                (d / f"{ev['entry']['formula']}.yaml").write_text(
                    f"# Written by code from changes.yaml (version {ver['version']}); never edited.\n" + _dump(ev["entry"]))
