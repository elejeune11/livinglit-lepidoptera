"""Running a figure's reading code, per paper (02-audit, Reading figures).

read(fig) returns {"groups": {label: {"points": [{value, lo, hi, at: [x, y], x?}], "countable": bool,
                                      "bar": {"mean": [v, lo, hi], "error": [v, lo, hi]}}}}
("error" is the upper end of the error bar in axis units). Each paper's helpers
(figures/_util.py) are that paper's alone: a helper of the same name from another
paper is never used.
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

from ..models import FigureEntry, Reading

ROUND = 6


def sig(x: float, digits: int = ROUND) -> float:
    if x == 0 or not math.isfinite(x):
        return float(x)
    return float(f"{x:.{digits}g}")


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def load_read(script: Path):
    folder = script.parent.resolve()
    for name, m in list(sys.modules.items()):  # forget helpers loaded from any other paper's figures folder
        f = getattr(m, "__file__", None)
        if f and Path(f).resolve().parent != folder and Path(f).parent.name == "figures" \
                and "livinglit" not in Path(f).resolve().parts:
            del sys.modules[name]
    sys.path.insert(0, str(folder))
    try:
        spec = importlib.util.spec_from_file_location(f"ll_fig_{abs(hash(str(script.resolve())))}", script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        if str(folder) in sys.path:
            sys.path.remove(str(folder))
        for name, m in list(sys.modules.items()):  # and drop this paper's helpers afterwards too
            f = getattr(m, "__file__", None)
            if f and Path(f).resolve().parent == folder:
                del sys.modules[name]
    if not hasattr(mod, "read"):
        raise AttributeError(f"{script.name} has no read(fig)")
    return mod.read


def to_rows(name: str, raw, entry: FigureEntry | None = None) -> tuple[list[Reading], list[str]]:
    errs, rows = [], []
    if not isinstance(raw, dict) or not isinstance(raw.get("groups"), dict) or not raw["groups"]:
        return [], [f"{name}: read() must return a dict with non-empty 'groups'"]
    for label, g in raw["groups"].items():
        where = f"{name}.{label}"
        if entry is not None and label not in entry.groups:
            errs.append(f"{where}: label not in figures.yaml groups")
        if not isinstance(g, dict) or not isinstance(g.get("points", []), list):
            errs.append(f"{where}: needs points (a list)")
            continue
        countable = g.get("countable", True)
        if entry is not None and entry.kind == "raster" and g.get("points") and countable is False:
            errs.append(f"{where}: raster points that do not each stand alone are not readable; return bar only")
        for i, p in enumerate(g.get("points", [])):
            v, lo, hi = p.get("value"), p.get("lo"), p.get("hi")
            if not (_num(v) and _num(lo) and _num(hi) and lo <= v <= hi):
                errs.append(f"{where}.points.{i}: needs value with lo <= value <= hi")
                continue
            at = p.get("at") or [None, None]
            rows.append(Reading(figure=name, group=label, kind="point", index=i, value=sig(v), lo=sig(lo), hi=sig(hi),
                                x=p.get("x"), page_x=sig(at[0]) if _num(at[0]) else None,
                                page_y=sig(at[1]) if _num(at[1]) else None))
        bar = g.get("bar") or {}
        for kind in ("mean", "error", "median", "q1", "q3", "whisker_lo", "whisker_hi"):
            if kind in bar:
                b = bar[kind]
                if not (isinstance(b, (list, tuple)) and len(b) == 3 and all(map(_num, b)) and b[1] <= b[0] <= b[2]):
                    errs.append(f"{where}.bar.{kind}: needs [value, lo, hi]")
                    continue
                rows.append(Reading(figure=name, group=label, kind=kind, index=0, value=sig(b[0]), lo=sig(b[1]),
                                    hi=sig(b[2]), x=bar.get("x")))
    return rows, errs


def run_figure(name: str, entry: FigureEntry, record_dir: Path, paper_dir: Path) -> tuple[list[Reading], list[str]]:
    from .source import FigureSource
    script = Path(record_dir) / entry.script
    if not script.is_file():
        return [], [f"{name}: script {entry.script} missing"]
    pdf = Path(paper_dir) / entry.file
    if not pdf.is_file():
        return [], [f"{name}: source {entry.file} missing"]
    try:
        read = load_read(script)
        src = FigureSource(pdf, entry.page, entry.crop)
        try:
            raw = read(src)
        finally:
            src.close()
    except Exception as e:  # a script error is a gate failure, reported
        return [], [f"{name}: {type(e).__name__}: {e}"]
    return to_rows(name, raw, entry)


def compare_readings(stored: list[Reading], fresh: list[Reading]) -> list[str]:
    """A stored reading that does not come back exactly fails the audit."""
    key = lambda r: (r.figure, r.group, r.kind, r.index, r.x)
    a = {key(r): r for r in stored}
    b = {key(r): r for r in fresh}
    probs = []
    for k in sorted(set(a) | set(b), key=str):
        if k not in b:
            probs.append(f"readings: {k} stored but not produced by the script")
        elif k not in a:
            probs.append(f"readings: {k} produced by the script but not stored")
        elif (a[k].value, a[k].lo, a[k].hi) != (b[k].value, b[k].lo, b[k].hi):
            probs.append(f"readings: {k} stored {a[k].value} [{a[k].lo}, {a[k].hi}], script gives {b[k].value} [{b[k].lo}, {b[k].hi}]")
    return probs
