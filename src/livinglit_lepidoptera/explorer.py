"""The explorer: one page that shows a release by question, down to each result (06-releases, The explorer).

`pack(release_dir)` packs the release's own tables into one JSON, written into `explorer_template.html` twice:
`explorer.html`, a standalone page, and `explorer_artifact.html`, the same page without document tags, to embed in a
host page (the host adds them). Each paper's result details (values, checks, derivations, resolved context) go in
`explorer_data/items_<paper>.js`, which the page loads only when a result is opened, so no file grows with the corpus.
Everything the page shows is built by code from the release; the context fields it highlights and links papers by are
chosen from the data (stated and varied), never listed here.
"""
from __future__ import annotations

import collections
import csv
import json
import math
import re
from pathlib import Path

import yaml

TEMPLATE = Path(__file__).with_name("explorer_template.html")
FIGURE = Path(__file__).resolve().parents[2] / "docs" / "design" / "figures" / "fig1_architecture.png"
PLACEHOLDER = "/*DATA*/null"
N_CTX = 7          # context fields offered for highlighting values
UNSET = {"not stated", "not applicable", "none", "unmapped", "flagged", "state", "by reference", "quantity", "assigned"}
TERMISH = re.compile(r"^([a-z_]+:[a-z0-9_]+|[A-Z][A-Za-z]*[:_][A-Za-z0-9_]+)$")
SCALE = {  # unit -> (unit shown, factor); display conversion only, labelled on the page
    "ms": ("ms", 1), "s": ("ms", 1000), "sec": ("ms", 1000),
    "nm": ("µm", 1e-3), "µm": ("µm", 1), "μm": ("µm", 1), "um": ("µm", 1),
    "μm2": ("µm²", 1), "µm2": ("µm²", 1), "µm²": ("µm²", 1), "μm²": ("µm²", 1),
    "Hz": ("Hz", 1), "bpm": ("Hz", 1 / 60), "beats/min": ("Hz", 1 / 60),
    "mN": ("mN", 1), "µN": ("mN", 1e-3), "μN": ("mN", 1e-3), "uN": ("mN", 1e-3), "nN": ("mN", 1e-6),
    "mN/mm2": ("mN/mm²", 1), "mN/mm²": ("mN/mm²", 1), "kPa": ("kPa", 1), "Pa": ("kPa", 1e-3),
}
DIMS = ["direction", "support", "comparison", "scope", "replication", "strength", "presence"]

csv.field_size_limit(10**9)


def _rows(rel: Path, name: str) -> list[dict]:
    f = rel / f"{name}.csv"
    return list(csv.DictReader(open(f, encoding="utf-8"))) if f.exists() else []


def _j(s, d=None):
    return json.loads(s) if s else d


def _int(s) -> int:
    try:
        return int(s)
    except (TypeError, ValueError):
        return 0


def cover(rel: Path) -> dict | None:
    """The cover: the field's source review (the release's cover.yaml) and LivingLit's whole-plan diagram."""
    f = Path(rel) / "cover.yaml"
    if not f.exists():
        return None
    c = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    if FIGURE.exists():
        import base64
        c["image"] = "data:image/png;base64," + base64.b64encode(FIGURE.read_bytes()).decode()
    return c


def pack(rel: Path) -> dict:
    """The explorer data for one release folder."""
    rel = Path(rel)
    terms = _rows(rel, "terms")
    label = {t["id"]: t["label"] for t in terms}
    papers = _rows(rel, "papers")

    I = [[it["paper"], it["item"], it["unit"], _j(it["measure_terms"], []) or [], it["finding"], it["status"],
          it["depth"], it["direction"], it["n"], it["p"], it["test"]] for it in _rows(rel, "items")]
    U = {u["paper"] + "/" + u["unit"]: [u["title"], u["where"]] for u in _rows(rel, "units")}

    strata = _rows(rel, "strata")
    ST = [{"id": s["stratum"], "measure": s["measure"], "part": s["part"], "key": s["key"], "papers": _int(s["papers"]),
           "items": _j(s["items"], []), "values": _j(s["values"], []), "verdicts": _j(s["verdicts"], {})}
          for s in strata if _int(s["papers"]) >= 2]

    verdicts, drop_any, drop_one, ndrops = (collections.Counter() for _ in range(4))
    AG = []
    comps = _rows(rel, "comparisons")
    for c in comps:
        v = c["verdict"]
        verdicts[v] += 1
        drops = re.findall(r"drop ([A-Za-z_@0-9.]+)", c.get("relaxation") or "")
        ndrops[len(drops)] += 1
        for d in drops:
            drop_any[d] += 1
        if len(drops) == 1:
            drop_one[drops[0]] += 1
        if v.startswith(("agree", "differ", "same direction")):
            AG.append([c["a"], c["b"], c["measure"], v, drops, c["part"]])

    parent_of = {t["id"]: t["parent"] for t in terms if t.get("parent")}

    def _lineage(tid: str) -> list[str]:
        out, cur = [], tid
        while cur and cur not in out:
            out.append(cur)
            cur = parent_of.get(cur)
        return out

    depth_of = {t["id"]: len(_lineage(t["id"])) - 1 for t in terms}

    # values: one context per reported group; central values for the one-axis view
    ctx_of, vals = {}, []
    stated = collections.Counter()
    spread = collections.defaultdict(collections.Counter)
    not_stated = collections.defaultdict(collections.Counter)
    ctxp_items = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(set)))
    item_terms = collections.defaultdict(set)
    for r in _rows(rel, "values"):
        key = (r["paper"], r["item"], r["group"])
        ik = f"{r['paper']}/{r['item']}"
        if key not in ctx_of:
            ctx = dict(p.split("=", 1) for p in (r.get("context_terms") or "").split("; ") if "=" in p)
            ctx_of[key] = ctx
            for k, v in ctx.items():
                state = v if v in ("not stated", "not applicable") else "stated"
                not_stated[k][state] += 1
                if state == "stated" and v not in UNSET:
                    stated[k] += 1
                    spread[k][v] += 1
                for t in v.split("|"):
                    t = t.strip()
                    if t and t not in UNSET and (t in label or TERMISH.match(t)):
                        for anc in _lineage(t):
                            ctxp_items[k][anc][r["paper"]].add(r["item"])
                            item_terms[ik].add(anc)
        if r["kind"] not in ("mean", "median", "value"):
            continue
        try:
            x = float(r["value"])
        except (TypeError, ValueError):
            continue
        unit, f = SCALE.get(r["unit_of_value"].strip(), (r["unit_of_value"].strip(), 1))
        for m in (r.get("measure_terms") or "").split("|"):
            if m:
                vals.append([m, unit, r["paper"], r["item"], r["group_label"] or r["group"], x * f,
                             r["value_printed"], r["unit_of_value"], r["origin"], key, r.get("x", "")])
    ctxp = {k: {t: {p: len(its) for p, its in pmap.items()} for t, pmap in tmap.items()} for k, tmap in ctxp_items.items()}
    # fields worth highlighting: often stated, and not the same value everywhere (stated groups outside the commonest value)
    varied = {k: n - max(spread[k].values()) for k, n in stated.items()}
    CTX = [k for k in sorted(varied, key=lambda k: (-varied[k], k)) if varied[k] > 0][:N_CTX]
    papers_in = collections.defaultdict(set)
    for v in vals:
        papers_in[(v[0], v[1])].add(v[2])
    keep = {k for k, ps in papers_in.items() if len(ps) >= 2}
    V = [v[:9] + [[ctx_of[v[9]].get(k, "") for k in CTX], v[10]] for v in vals if (v[0], v[1]) in keep]
    VM = sorted(({"measure": m, "unit": u, "papers": len(papers_in[(m, u)]),
                  "n": sum(1 for v in V if v[0] == m and v[1] == u)} for m, u in keep),
                key=lambda d: (-d["papers"], -d["n"], d["measure"], d["unit"]))

    F = [[f["paper"], f["id"], f["unit"], f["check"], f["verdict"], f["source"], _j(f["items"], []), f["example"]]
         for f in _rows(rel, "findings")]
    CL = []
    for c in _rows(rel, "claims"):
        j = _j(c["judgement"], {}) or {}
        CL.append([c["paper"], c["claim"], c["kind"], c["verdict"], c["quote"], c["scope"],
                   {k: v for k, v in j.items() if v != "follows"}, _j(c["rests_on"], [])])
    COV = [[r["field"], r["label"], r["term"], _int(r["labs"]), _int(r["sources"]), _int(r["values"])]
           for r in _rows(rel, "coverage")]
    for r in COV:
        label.setdefault(r[2], r[1])

    summ = yaml.safe_load(open(rel / "summary.yaml")) if (rel / "summary.yaml").exists() else {}
    pp = summ.get("per_paper", {}) or {}
    P = []
    for p in sorted(papers, key=lambda p: (p["year"], p["paper"])):
        s = pp.get(p["paper"], {}) or {}
        P.append({"id": p["paper"], "title": p["title"], "year": p["year"], "lab": p["lab"], "doi": p["doi"],
                  "depth": p["depth"], "units": s.get("units"), "items": s.get("items"), "claims": s.get("claims"),
                  "status": s.get("status", {})})
    return {
        "tag": summ.get("tag", rel.name), "vocab_version": summ.get("vocabulary_version"),
        "formula_version": summ.get("formula_library_version"), "label": label,
        "P": P, "I": I, "U": U, "ST": ST, "STRATA_TOTAL": len(strata),
        "CMP": {"n": len(comps), "verdicts": verdicts, "drop_any": drop_any, "drop_one": drop_one, "ndrops": ndrops},
        "AG": AG, "V": V, "VM": VM, "CTX": CTX, "F": F, "CL": CL, "DIMS": DIMS,
        "SDR": [[r["paper"], _int(r["items_cannot_check"]), _int(r["items_total"])] for r in _rows(rel, "source_data_requests")],
        "MS": [[r["paper"], _j(r["missing"], [])] for r in _rows(rel, "missing_supplements")],
        "COMP": [[_int(r["rank"]), r["citation"], _j(r["records"], []), _int(r["values"]), len(_j(r["locations"], []))]
                 for r in _rows(rel, "completeness")],
        "NS": sorted(([k, c["stated"], c["not stated"], c["not applicable"]] for k, c in not_stated.items()),
                     key=lambda r: (-(r[2] / max(1, r[1] + r[2])), r[0])),
        "T": [[t["id"], t["label"], _j(t["fields"], []), t["parent"], t["definition"], _j(t["synonyms"], []),
               t["added"], t["source"], t["scope"]] for t in terms],
        "COV": COV,
        "FO": [[f["formula"], f["kind"], f["statement"], _j(f["equations"], []), _j(f["holds_under"], [])]
               for f in _rows(rel, "formulas")],
        "CTXP": ctxp,
        "IT": {k: sorted(v) for k, v in item_terms.items()},
        "DEPTH": depth_of,
        "COVER": cover(rel),
    }


def render(data: dict) -> str:
    """The page body: the template with the data in place ('</' escaped so release text cannot end the script)."""
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return TEMPLATE.read_text(encoding="utf-8").replace(PLACEHOLDER, js, 1)


def standalone(body: str) -> str:
    """The same page as a complete document, to open in a browser."""
    head, sep, rest = body.partition("<style>")
    return ('<!doctype html>\n<html lang="en">\n<head>\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
            + head + sep + rest.replace("</style>\n", "</style>\n</head>\n<body>\n", 1) + "\n</body>\n</html>\n")


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _layer(at: str) -> str:
    if ".groups." in at:
        return "group"
    return {"default_context": "paper", "units": "unit", "evidence": "item"}.get(at.split(".")[0], "")


def result_detail(pa, a: dict, iid: str, rows: list[dict]) -> dict:
    """One result as its page shows it: anchor, status, measure and context with their mapped terms, groups and
    contrast, values and points, the checks code ran, and the derivations along the formula library."""
    from .audit import _where
    from .models import stated_text
    from .record import resolve_context
    rec = pa.rec
    it, ai = rec.evidence[iid], a["items"][iid]
    unit = rec.units[it.unit]
    gids = it.group_ids()
    ref_group = gids[-1] if len(gids) == 2 else (gids[0] if gids else None)
    mp = a["mappings"]
    context = {}
    for f, v in resolve_context(rec, iid, ref_group).items():
        at = _where(rec, iid, ref_group, f)
        m = mp.get(at)
        origin = m["origin"] if m else ("not stated" if stated_text(v) in ("not stated", None) else "unmapped")
        context[f] = [origin, (m or {}).get("terms") or [], stated_text(v) or "by reference",
                      (m or {}).get("flag") or "", _layer(at)]
    mm = mp.get(f"evidence.{iid}.measure")
    values, points = [], collections.defaultdict(list)
    for r in rows:
        label = r.get("group_label") or r.get("group") or ""
        if r["kind"] == "point":
            v = _num(r["value"])
            if v is not None:
                points[f"{label}|{r['origin']}|{r.get('unit_of_value') or ''}"].append(v)
            continue
        values.append([label, r["kind"], r.get("value_printed") or "", _num(r.get("value")), r.get("unit_of_value") or "",
                       r["origin"], _num(r.get("interval_lo")), _num(r.get("interval_hi"))])
    groups = [{"id": g, "label": unit.groups[g].label, "kind": unit.groups[g].kind,
               "context": {f: stated_text(v) or "by reference" for f, v in unit.groups[g].context.items()}}
              for g in gids if g in unit.groups]
    chains = []
    for c in ai["derivations"]:
        dv = pa.derived_file.derived.get(c["derivation"]) if pa.derived_file else None
        rb = c.get("rebuilt") or {}
        note = f"rebuilt {rb['value']:.4g} {rb.get('unit') or ''} (derived by LivingLit)" if rb.get("value") is not None else ""
        chains.append([c["derivation"], dv.library.formula if dv and dv.library else None, c["verdict"], note,
                       c.get("flags") or []])
    return {
        "unit": it.unit, "item": iid,
        "unit_title": a["units"].get(it.unit, {}).get("title", ""), "unit_where": a["units"].get(it.unit, {}).get("where", ""),
        "measure": it.measure, "finding": it.finding, "status": ai["status"], "depth": ai["depth"],
        "anchor": it.anchor.quote, "where": it.anchor.where, "anchor_kind": it.anchor.kind,
        "suspected_error": it.suspected_error.what if it.suspected_error else "",
        "method": it.method or "", "software": it.software or "",
        "n": it.n if isinstance(it.n, str) else it.n.printed, "test": it.stats.test, "p": it.stats.p,
        "map": {"measure": [mm["origin"] if mm else "unmapped", (mm or {}).get("terms") or []], "context": context},
        "groups": groups, "test_of": it.kind_of_test or "measurement",
        "contrast": ai["contrast"], "direction": ai["direction"],
        "values": values, "points": dict(points),
        "checks": [[c["check"], c["verdict"], " ".join(x for x in (c.get("entry") or "", c.get("note") or "") if x)]
                   for c in ai["checks"]],
        "chains": chains, "upstream": ai["upstream_flags"],
    }


def write_results(rel: Path, pas: dict, audits: dict) -> list[str]:
    """Write each paper's result details to `explorer_data/items_<paper>.js` under the release; return the paths."""
    from .audit import value_rows
    ddir = Path(rel) / "explorer_data"
    ddir.mkdir(parents=True, exist_ok=True)
    written = []
    for pid, pa in sorted(pas.items()):
        rows = collections.defaultdict(list)
        for r in value_rows(pa):
            rows[r["item"]].append(r)
        part = {}
        for iid in pa.rec.evidence:
            part[f"{pid}/{iid}"] = {"paper": pid, **result_detail(pa, audits[pid], iid, rows.get(iid, []))}
        body = json.dumps(part, default=str, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        (ddir / f"items_{pid}.js").write_text("window.LL_ITEMS = window.LL_ITEMS || {};\n"
                                              f"Object.assign(window.LL_ITEMS, {body});\n", encoding="utf-8")
        written.append(f"explorer_data/items_{pid}.js")
    return written


def write_explorer(rel: Path, pas: dict | None = None, audits: dict | None = None) -> None:
    """Write the explorer into a release folder: the page, its artifact body, and (given the audits) the result files."""
    rel = Path(rel)
    if pas is not None and audits is not None:
        write_results(rel, pas, audits)
    body = render(pack(rel))
    (rel / "explorer_artifact.html").write_text(body, encoding="utf-8")
    (rel / "explorer.html").write_text(standalone(body), encoding="utf-8")


def make_site(release_dir, site_dir) -> list[str]:
    """Copy a release's explorer into a folder a static host serves as is: the page as index.html, explorer_data/, and
    .nojekyll; files from an earlier site are removed first. Returns the files written, relative to the folder."""
    import shutil
    release_dir, site_dir = Path(release_dir), Path(site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(site_dir / "explorer_data", ignore_errors=True)
    (site_dir / "explorer.html").unlink(missing_ok=True)  # the page is index.html; no second copy
    shutil.copytree(release_dir / "explorer_data", site_dir / "explorer_data")
    shutil.copyfile(release_dir / "explorer.html", site_dir / "index.html")
    (site_dir / ".nojekyll").write_text("")
    return ["index.html", ".nojekyll"] + sorted(f"explorer_data/{f.name}" for f in (site_dir / "explorer_data").iterdir())
