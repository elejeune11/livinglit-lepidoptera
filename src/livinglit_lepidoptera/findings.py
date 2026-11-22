"""Findings: failing checks grouped by cause (02-audit, Findings, not item counts).

A finding is one cause: the same unit and check, resting on the same printed
source. Code decides the grouping from the record alone:
- n checks: the printed n for one group (one legend statement);
- data checks: the data file the values come from;
- P checks: the unit's printed test (one test, one family);
- anything else: the item itself.
Only inconsistent and close verdicts make findings.
"""
from __future__ import annotations

FAILING = ("inconsistent", "close")
N_CHECKS = ("n against data", "n against readings", "n from bar", "n implied by error bar")
P_CHECKS = ("points to P", "summary to P", "reported twice")


def _group_of(target: str) -> str | None:
    if "/" not in target:
        return None
    return target.split("/", 1)[1].split()[0]


def _source(rec, iid: str, c: dict, files: dict) -> tuple:
    it = rec.evidence[iid]
    chk = c["check"]
    if chk in N_CHECKS:
        g = _group_of(c.get("target", ""))
        if it.n != "not stated":
            per = (it.n.per_group or {}).get(g) if g else None
            label = f"printed {it.n.printed!r}" + (f", {g}: {per}" if per else (f", group {g}" if g else ""))
            return ("n", it.n.printed, g), label
        return ("n", None, g), f"group {g}: n not stated"
    if chk == "against data":
        g = _group_of(c.get("target", ""))
        fs = sorted(files.get((iid, g), set()) | {v.data.file for v in it.values.values() if v.data})
        f = fs[0] if fs else "data"
        return ("data", f, g), f"data file {f}" + (f", group {g}" if g else "")
    if chk in P_CHECKS and it.stats.test:
        return ("test", it.stats.test), f"printed test {it.stats.test!r}"
    return ("item", iid), f"item {iid}"


def group_findings(rec, items: dict, data_rows=()) -> list[dict]:
    """items: item id -> {"unit", "checks": [check dicts]} as in the audit; data_rows: the paper's data.yaml rows."""
    files: dict = {}
    for r in data_rows:
        files.setdefault((r.item, r.group), set()).add(r.file)
    found: dict[tuple, dict] = {}
    for iid, row in items.items():
        for c in row["checks"]:
            if c["verdict"] not in FAILING:
                continue
            key, label = _source(rec, iid, c, files)
            k = (row["unit"], c["check"], key)
            f = found.setdefault(k, {"unit": row["unit"], "check": c["check"], "source": label,
                                     "verdict": c["verdict"], "items": [], "checks": 0, "example": ""})
            f["checks"] += 1
            if iid not in f["items"]:
                f["items"].append(iid)
            if c["verdict"] == "inconsistent":
                f["verdict"] = "inconsistent"
            if not f["example"] and c.get("note"):
                f["example"] = f"{iid}: {c['note']}"
    out = sorted(found.values(), key=lambda f: (f["verdict"] != "inconsistent", f["unit"], f["check"], f["source"]))
    for i, f in enumerate(out, 1):
        f["id"] = f"FD{i}"
    return out
