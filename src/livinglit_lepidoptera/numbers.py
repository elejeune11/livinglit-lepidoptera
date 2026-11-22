"""Printed numbers, P values, units and test kinds (02-audit, Values; Checks within a source).

A printed value stands for everything that rounds to it. Values are strings in
records; numbers are parsed here only to judge them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

MINUS = dict.fromkeys(map(ord, "−–‒﹣－"), "-")
NUMBER = re.compile(r"[-+]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)(?:\s*[×x]\s*10\s*\^?\s*[-+]?\d+|[eE][-+]?\d+)?")
SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")


def _clean(s: str) -> str:
    return s.translate(SUPERSCRIPT).translate(MINUS)


def _to_float_text(tok: str) -> str:
    tok = tok.replace(",", "").replace(" ", "").lstrip("+")
    m = re.match(r"^(-?(?:\d+(?:\.\d+)?|\.\d+))[×x]10\^?([-+]?\d+)$", tok)
    if m:
        return f"{m.group(1)}e{m.group(2)}"
    if tok.startswith("."):
        tok = "0" + tok
    if tok.startswith("-."):
        tok = "-0" + tok[1:]
    return tok


APPROX_WORDS = re.compile(r"\b(about|approximately|approx\.?|roughly|around|nearly)\b", re.I)


def parse_number(printed: str) -> tuple[str, bool]:
    """The first number in a printed string as text, and whether it was marked approximate."""
    s = _clean(printed).strip()
    approx = "~" in s or "≈" in s or bool(APPROX_WORDS.search(s))
    m = NUMBER.search(s.replace("~", "").replace("≈", ""))
    if not m:
        raise ValueError(f"no number in {printed!r}")
    return _to_float_text(m.group(0)), approx


def numbers_in(printed: str) -> list[str]:
    return [_to_float_text(m.group(0)) for m in NUMBER.finditer(_clean(printed))]


def to_float(printed: str) -> float:
    return float(parse_number(printed)[0])


def interval(printed: str) -> tuple[float, float]:
    num, _ = parse_number(printed)
    d = Decimal(num)
    half = Decimal(1).scaleb(d.as_tuple().exponent) / 2
    return float(d - half), float(d + half)


def is_machine_precision(num: str) -> bool:
    mant = num.split("e")[0]
    return "." in mant and len(mant.split(".")[1]) > 8


def judge_value(printed: str, value: float) -> str:
    """consistent inside the printed interval; close within one more last digit; else inconsistent."""
    num, approx = parse_number(printed)
    if approx:  # '~' or '≈': approximate, judged within 10 % or one last digit, whichever is wider
        x = float(num)
        lo, hi = interval(num)
        tol = max(0.1 * abs(x), hi - lo)
        if abs(value - x) <= tol:
            return "consistent"
        return "close" if abs(value - x) <= 2 * tol else "inconsistent"
    if is_machine_precision(num):
        x = float(num)
        return "consistent" if abs(value - x) <= 1e-6 * max(abs(x), 1e-12) else "inconsistent"
    lo, hi = interval(printed)
    if lo <= value <= hi:
        return "consistent"
    w = hi - lo
    return "close" if lo - w <= value <= hi + w else "inconsistent"


def split_pm(printed: str) -> tuple[str, str | None]:
    """'578 ± 88' -> ('578', '88'); a bare number -> (number, None); a range raises."""
    s = _clean(printed)
    if "±" in s or "+/-" in s:
        a, b = re.split(r"±|\+/-", s, maxsplit=1)
        return parse_number(a)[0], parse_number(b)[0]
    if re.search(r"\d\s*-\s*\d", s) and not re.search(r"[eE×x]\s*10", s):
        raise ValueError(f"{printed!r} is a range: two values, never a mean")
    return parse_number(s)[0], None


# ------------------------------------------------------------------ P values
@dataclass(frozen=True)
class P:
    op: str  # "<", ">", "=", ">=" (n.s.)
    value: float
    text: str

    @property
    def significant(self) -> bool:
        if self.op == "sig":
            return True
        if self.op in (">", ">="):
            return False
        return self.value <= 0.05 if self.op == "<" else self.value < 0.05


P_EXPR = re.compile(r"\bp\s*(?:value)?\s*(<=|>=|≤|≥|<|>|=)\s*("
                    r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:\s*[×x]\s*10\s*\^?\s*[-+]?\d+|[eE][-+]?\d+)?)", re.I)
P_SIG_STATE = "significant, threshold not stated"  # asterisks without a key (02-audit, Values)
SIG = re.compile(r"^\W*significant,?\s*threshold not stated\W*$", re.I)
NS = re.compile(r"^\W*(n\.?\s?s\.?|not significant|non-?significant)\W*$", re.I)


def parse_p(printed: str | None) -> P | None:
    """The first 'P <op> value' in a printed string; 'n.s.' is P ≥ 0.05; asterisks alone are not a P."""
    if not printed:
        return None
    s = _clean(printed).strip()
    if NS.match(s):
        return P(">=", 0.05, printed)
    if SIG.match(s):
        return P("sig", 0.05, printed)
    m = P_EXPR.search(s)
    if not m:
        return None
    op = {"≤": "<", "<=": "<", "≥": ">", ">=": ">"}.get(m.group(1), m.group(1))
    return P(op, float(_to_float_text(m.group(2))), printed)


def judge_p(printed: str, p: float) -> str:
    pp = parse_p(printed)
    if pp is None:
        raise ValueError(f"no P in {printed!r}")
    if pp.op == "=":
        num = _to_float_text(P_EXPR.search(_clean(printed)).group(2))
        return judge_value(num, p)
    if pp.op == ">=":
        return "consistent" if p >= 0.05 else ("close" if p >= 0.045 else "inconsistent")
    m = P_EXPR.search(_clean(printed))
    lo, hi = interval(_to_float_text(m.group(2)))
    if pp.op == "<":
        return "consistent" if p < pp.value else ("close" if p < hi + (hi - lo) else "inconsistent")
    return "consistent" if p > pp.value else ("close" if p > lo - (hi - lo) else "inconsistent")


def p_interval_verdict(printed: str, lo: float, hi: float) -> str:
    """A P from read values is an interval: consistent if the whole interval agrees, close if part does."""
    a, b = judge_p(printed, lo), judge_p(printed, hi)
    if a == b == "consistent":
        return "consistent within reading"
    if "consistent" in (a, b) or "close" in (a, b):
        return "close"
    return "inconsistent"


# ------------------------------------------------------------------ units
@dataclass(frozen=True)
class Unit:
    name: str | None
    dimension: str | None
    factor: float = 1.0


UNITS: dict[str, tuple[str, float, list[str]]] = {
    "nm": ("length", 1e-3, []), "µm": ("length", 1, ["um", "micron", "microns", "micrometer", "micrometers"]),
    "mm": ("length", 1e3, []), "cm": ("length", 1e4, []), "m": ("length", 1e6, []),
    "µm²": ("area", 1, ["um2", "um^2", "µm2", "µm^2"]), "mm²": ("area", 1e6, ["mm2", "mm^2"]),
    "cm²": ("area", 1e8, ["cm2"]),
    "nN": ("force", 1e-6, []), "µN": ("force", 1e-3, ["uN"]), "mN": ("force", 1, []), "N": ("force", 1e3, []),
    "mN/mm²": ("stress", 1, ["mN/mm2", "mN/mm^2", "mN mm-2", "mNmm-2"]), "kPa": ("stress", 1, []),
    "Pa": ("stress", 1e-3, []), "MPa": ("stress", 1e3, []),
    "µm/s": ("velocity", 1, ["um/s", "um s-1", "µm s-1"]), "mm/s": ("velocity", 1e3, ["mm s-1"]),
    "cm/s": ("velocity", 1e4, ["cm s-1"]), "m/s": ("velocity", 1e6, []),
    "V/s": ("voltage_rate", 1, ["mV/ms"]),
    "F/F0": ("fluorescence_ratio", 1, ["F/Fo"]),
    "ΔF/F0": ("fluorescence_change", 1, ["dF/F0", "dF/F", "ΔF/F", "ΔF/Fo"]),
    "a.u.": ("arbitrary", 1, ["au", "AU", "a.u", "arbitrary units", "arb. units"]),
    "bpm": ("rate", 1, ["beats/min", "beats per minute", "BPM", "beats min-1", "min-1", "beats/minute"]),
    "Hz": ("rate", 60, ["hz", "beats/s"]),
    "ms": ("time", 1, ["msec"]), "s": ("time", 1e3, ["sec"]), "min": ("time", 6e4, []), "h": ("time", 3.6e6, ["hr"]),
    "day": ("day", 1, ["days", "d"]),
    "mV": ("potential", 1, []), "V": ("potential", 1e3, []),
    "%": ("fraction_percent", 1, ["percent"]),
    "% of baseline": ("percent_of_baseline", 1, ["% baseline", "% of BL", "% of control", "% control"]),
    "% change": ("percent_change", 1, ["% change from baseline", "percent change"]),
    "fold": ("fold_change", 1, ["fold change", "-fold", "relative expression", "fold-change"]),
    "nM": ("concentration", 1e-6, []), "µM": ("concentration", 1e-3, ["uM"]), "mM": ("concentration", 1, []),
    "M": ("concentration", 1e3, []),
    "mN/mm": ("stiffness", 1, ["N/m"]), "µN/µm": ("stiffness", 1, ["uN/um"]),
    "pF": ("capacitance", 1, []), "pA/pF": ("current_density", 1, []),
    "count": ("count", 1, ["cells", "#", "number"]),
    "°C": ("temperature", 1, ["C", "degC", "ºC"]),
}


def _key(s: str) -> str:
    s = s.strip().replace("μ", "µ").replace("²", "2").replace("⁻¹", "-1").replace("−", "-")
    return re.sub(r"\s+", "", s)


_LOOKUP = {}
for _n, (_d, _f, _o) in UNITS.items():
    for _s in (_n, *_o):
        _LOOKUP[_key(_s)] = _n
        _LOOKUP[_key(_s).lower()] = _LOOKUP.get(_key(_s).lower(), _n)


def parse_unit(printed: str) -> Unit:
    k = _key(printed)
    name = _LOOKUP.get(k) or (_LOOKUP.get(k.lower()) if k.lower() not in ("mm", "mn") else None)
    if name is None:
        raise ValueError(f"unit {printed!r} is not known")
    d, f, _ = UNITS[name]
    return Unit(name, d, f)


def try_unit(printed: str | None) -> Unit:
    if not printed:
        return Unit(None, None)
    try:
        return parse_unit(printed)
    except ValueError:
        return Unit(None, None)


def unit_from_axis_label(label: str) -> Unit:
    """'Force [mN]' is mN; '(msec)' is ms; a label with no unit gives Unit(None)."""
    m = re.findall(r"[\[(]([^\[\]()]+)[\])]", label)
    for cand in reversed(m):
        u = try_unit(cand)
        if u.name:
            return u
    return Unit(None, None)


def same_quantity_units(a: str, b: str) -> bool:
    ua, ub = try_unit(a), try_unit(b)
    if not ua.name or not ub.name:
        return _key(a) == _key(b)
    return ua.dimension == ub.dimension


def convert(value: float, frm: str, to: str) -> float:
    ua, ub = parse_unit(frm), parse_unit(to)
    if ua.dimension != ub.dimension:
        raise ValueError(f"{frm} and {to} are different quantities")
    return value * ua.factor / ub.factor


# ------------------------------------------------------------------ test kinds
@dataclass(frozen=True)
class TestKind:
    family: str
    posthoc: str | None = None
    text: str = ""

    @property
    def two_group_recheckable(self) -> bool:
        return self.family in ("welch_t", "student_t", "t_unpaired", "t_unspecified", "paired_t", "mann_whitney")

    @property
    def alternatives(self) -> tuple[str, ...]:
        """The two-sample tests tried for this printed test (labelled alternatives when unstated)."""
        return {"welch_t": ("t_two_sample_welch",), "student_t": ("t_two_sample_pooled",),
                "t_unpaired": ("t_two_sample_pooled", "t_two_sample_welch"),
                "t_unspecified": ("t_two_sample_pooled", "t_two_sample_welch"),
                "not stated": ("t_two_sample_pooled", "t_two_sample_welch")}.get(self.family, ())


POSTHOC = [("holm-sidak", r"holm[\s-]*[sš]i?d[aá]k"), ("tukey", r"tukey"), ("dunnett", r"dunnett"),
           ("bonferroni", r"bonferroni"), ("sidak", r"[sš]i?d[aá]k"), ("holm", r"\bholm\b"),
           ("dunn", r"\bdunn'?s?\b"), ("newman-keuls", r"newman"), ("fisher-lsd", r"\blsd\b"),
           ("unspecified", r"multiple comparison|post[\s-]?(hoc|test)")]


def test_kind(printed: str | None) -> TestKind:
    s = (printed or "not stated").lower().replace("’", "'")
    if s.strip().startswith("not stated") or not s.strip():
        return TestKind("not stated", None, printed or "")
    posthoc = next((name for name, pat in POSTHOC if re.search(pat, s)), None)
    if re.search(r"two[\s-]?way|2[\s-]?way|repeated measures anova|mixed[\s-]effects", s):
        fam = "two_way_anova"
    elif re.search(r"one[\s-]?way", s):
        fam = "one_way_anova"
    elif "kruskal" in s:
        fam = "kruskal_wallis"
    elif "friedman" in s:
        fam = "friedman"
    elif "anova" in s:
        fam = "anova_unspecified"
    elif re.search(r"mann[\s-]?whitney|wilcoxon rank[\s-]?sum", s):
        fam = "mann_whitney"
    elif "wilcoxon" in s:
        fam = "wilcoxon_signed_rank"
    elif re.search(r"correlat|pearson|spearman|regression", s):
        fam = "correlation"
    elif re.search(r"\bpaired\b", s) and not re.search(r"unpaired", s):
        fam = "paired_t"
    elif re.search(r"welch|unequal variance", s):
        fam = "welch_t"
    elif re.search(r"t[\s-]?test", s):
        if "student" in s:
            fam = "student_t"
        elif "unpaired" in s or "two-sample" in s or "independent" in s:
            fam = "t_unpaired"
        else:
            fam = "t_unspecified"
    elif re.search(r"chi|fisher'?s exact", s):
        fam = "contingency"
    else:
        fam = "other"
    if fam in ("mann_whitney",) and posthoc == "unspecified":
        posthoc = None
    return TestKind(fam, posthoc, printed or "")


test_kind.__test__ = False
TestKind.__test__ = False


def judge_p_range(printed: str, lo: float, hi: float) -> str:
    """P computed from a printed statistic is an interval (the statistic's printed precision): consistent if
    any value in it agrees with the printed P (02-audit, Checks within a source)."""
    pp = parse_p(printed)
    if pp is None:
        raise ValueError(f"no P in {printed!r}")
    lo, hi = min(lo, hi), max(lo, hi)
    if pp.op == "=":
        num = _to_float_text(P_EXPR.search(_clean(printed)).group(2))
        a, b = interval(num)
        if a <= hi and lo <= b:
            return "consistent"
        return min((judge_value(num, lo), judge_value(num, hi)), key=["consistent", "close", "inconsistent"].index)
    if pp.op == "<":
        return judge_p(printed, lo)
    return judge_p(printed, hi)


SI = {"nm": 1e-9, "µm": 1e-6, "mm": 1e-3, "cm": 1e-2, "m": 1.0, "µm²": 1e-12, "mm²": 1e-6, "cm²": 1e-4,
      "nN": 1e-9, "µN": 1e-6, "mN": 1e-3, "N": 1.0, "mN/mm²": 1e3, "kPa": 1e3, "Pa": 1.0, "MPa": 1e6,
      "µm/s": 1e-6, "mm/s": 1e-3, "cm/s": 1e-2, "m/s": 1.0, "ms": 1e-3, "s": 1.0, "min": 60.0, "h": 3600.0,
      "Hz": 1.0, "bpm": 1 / 60, "mN/mm": 1.0, "µN/µm": 1.0, "%": 0.01, "% of baseline": 0.01, "% change": 0.01,
      "nM": 1e-6, "µM": 1e-3, "mM": 1.0, "M": 1e3, "mV": 1e-3, "V": 1.0, "V/s": 1.0, "fold": 1.0}


def si_factor(unit: str | None) -> float | None:
    """Multiplier from a printed unit to SI; None when the unit is not known."""
    if not unit:
        return None
    u = try_unit(unit)
    return SI.get(u.name) if u.name else None
