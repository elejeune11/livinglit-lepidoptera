"""What changed since the last release, and why (06-releases, Living).

`changelog(previous, current)` compares two release folders by their own files: papers, terms and formulas added or
removed, items whose status changed, and comparisons whose verdict changed, each with what changed in its row (a side
now compared on a rebuilt value, fields assumed). It is written into the release as `changes.yaml` and `CHANGES.md`.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import yaml

csv.field_size_limit(10**9)
LIST_LIMIT = 500  # rows listed per section; the counts are always complete


def _rows(d: Path, name: str) -> list[dict]:
    f = d / f"{name}.csv"
    return list(csv.DictReader(open(f, encoding="utf-8"))) if f.exists() else []


def _j(s):
    try:
        return json.loads(s) if s else []
    except json.JSONDecodeError:
        return [s]


def previous_release(root: Path, tag: str) -> Path | None:
    """The most recently built release under `root` other than `tag`."""
    root = Path(root)
    if not root.is_dir():
        return None
    cands = [d for d in root.iterdir() if d.is_dir() and d.name != tag and (d / "summary.yaml").exists()]
    return max(cands, key=lambda d: (d / "summary.yaml").stat().st_mtime, default=None)


def _added_removed(old: set, new: set) -> dict:
    return {"added": sorted(new - old), "removed": sorted(old - new)}


def changelog(prev: Path, cur: Path) -> dict:
    prev, cur = Path(prev), Path(cur)
    ps = yaml.safe_load((prev / "summary.yaml").read_text()) or {}
    cs = yaml.safe_load((cur / "summary.yaml").read_text()) or {}
    out = {"tag": cs.get("tag", cur.name), "since": ps.get("tag", prev.name),
           "vocabulary_version": [ps.get("vocabulary_version"), cs.get("vocabulary_version")],
           "formula_library_version": [ps.get("formula_library_version"), cs.get("formula_library_version")],
           "papers": _added_removed(set(ps.get("papers") or []), set(cs.get("papers") or [])),
           "terms": _added_removed({r["id"] for r in _rows(prev, "terms")}, {r["id"] for r in _rows(cur, "terms")}),
           "formulas": _added_removed({r["formula"] for r in _rows(prev, "formulas")},
                                      {r["formula"] for r in _rows(cur, "formulas")})}
    old_st = {f"{r['paper']}/{r['item']}": r["status"] for r in _rows(prev, "items")}
    changed = [{"item": k, "from": old_st[k], "to": r["status"]}
               for r in _rows(cur, "items") for k in [f"{r['paper']}/{r['item']}"] if k in old_st and old_st[k] != r["status"]]
    out["items"] = {"status_changed": changed[:LIST_LIMIT], "status_changed_count": len(changed),
                    "transitions": dict(Counter(f"{c['from']} -> {c['to']}" for c in changed).most_common())}
    key = lambda r: (r["a"], r["b"], r["part"])
    old_c = {key(r): r for r in _rows(prev, "comparisons")}
    vc, new = [], 0
    for r in _rows(cur, "comparisons"):
        o = old_c.get(key(r))
        if o is None:
            new += 1
            continue
        if o["verdict"] == r["verdict"]:
            continue
        why = []
        rb_o, rb_n = set(_j(o.get("rebuilt"))), set(_j(r.get("rebuilt")))
        if rb_n != rb_o:
            why += [f"rebuilt: {x}" for x in sorted(rb_n - rb_o)] + [f"no longer rebuilt: {x}" for x in sorted(rb_o - rb_n)]
        as_o, as_n = set(_j(o.get("assumes"))), set(_j(r.get("assumes")))
        if as_n != as_o:
            why.append(f"assumes {sorted(as_n) or 'nothing'} (was {sorted(as_o) or 'nothing'})")
        vc.append({"a": r["a"], "b": r["b"], "part": r["part"], "measure": r.get("measure", ""),
                   "from": o["verdict"], "to": r["verdict"],
                   "why": "; ".join(why) or "the sides' values or mapped terms changed"})
    gone = len(set(old_c) - {key(r) for r in _rows(cur, "comparisons")})
    out["comparisons"] = {"new": new, "no_longer_listed": gone, "verdict_changed_count": len(vc),
                          "transitions": dict(Counter(f"{c['from']} -> {c['to']}" for c in vc).most_common()),
                          "verdict_changed": vc[:LIST_LIMIT]}
    return out


def changes_md(c: dict) -> str:
    """A short readable version of changes.yaml."""
    L = [f"# Changes in {c['tag']} since {c['since']}", ""]
    vv, fv = c["vocabulary_version"], c["formula_library_version"]
    L += [f"- Vocabulary version {vv[0]} → {vv[1]}; formula library version {fv[0]} → {fv[1]}.",
          f"- Papers added: {len(c['papers']['added'])} ({', '.join(c['papers']['added']) or 'none'}); "
          f"removed: {len(c['papers']['removed'])}.",
          f"- Terms added: {len(c['terms']['added'])}; removed: {len(c['terms']['removed'])}. "
          f"Formulas added: {len(c['formulas']['added'])}; removed: {len(c['formulas']['removed'])}.",
          f"- Items whose status changed: {c['items']['status_changed_count']}"
          + (f" ({'; '.join(f'{k}: {v}' for k, v in c['items']['transitions'].items())})" if c['items']['transitions'] else "")
          + ".",
          f"- Comparisons: {c['comparisons']['new']} new, {c['comparisons']['no_longer_listed']} no longer listed, "
          f"{c['comparisons']['verdict_changed_count']} with a changed verdict"
          + (f" ({'; '.join(f'{k}: {v}' for k, v in c['comparisons']['transitions'].items())})"
             if c['comparisons']['transitions'] else "") + ".", ""]
    if c["comparisons"]["verdict_changed"]:
        L += ["## Comparisons whose verdict changed", "", "| a | b | part | from | to | why |", "| --- | --- | --- | --- | --- | --- |"]
        L += [f"| {r['a']} | {r['b']} | {r['part']} | {r['from']} | {r['to']} | {r['why']} |"
              for r in c["comparisons"]["verdict_changed"][:100]]
        L.append("")
    return "\n".join(L)


def write_history(out: Path, field_dir: Path, root: Path, since: str | None = None) -> dict | None:
    """Copy the logs the release was built from into `out/logs/`, and write changes.yaml and CHANGES.md against the
    release `since` (or the latest other release under `root`). Returns the changelog, or None for a first release."""
    import shutil
    out, field_dir = Path(out), Path(field_dir)
    logs = out / "logs"
    logs.mkdir(exist_ok=True)
    for src, name in ((field_dir / "changes.yaml", "vocabulary_changes.yaml"),
                      (field_dir / "formulas" / "changes.yaml", "formula_changes.yaml"),
                      (field_dir.parent / "_shared" / "formulas" / "changes.yaml", "shared_formula_changes.yaml")):
        if src.exists():
            shutil.copyfile(src, logs / name)
    prev = Path(root) / since if since else previous_release(root, out.name)
    if prev is None or not (prev / "summary.yaml").exists():
        return None
    c = changelog(prev, out)
    (out / "changes.yaml").write_text(yaml.safe_dump(c, sort_keys=False, allow_unicode=True))
    (out / "CHANGES.md").write_text(changes_md(c))
    return c
