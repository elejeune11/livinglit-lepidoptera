"""A release: tagged, documented tables generated from the files (06-releases).

releases/<tag>/ is generated and git-ignored. Gaps are values, not blanks.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from . import RECORDS_DIR, RELEASES_DIR, PAPERS_DIR, FIELDS_DIR, DEFAULT_FIELD
from .across import comparisons, strata
from .audit import audit_paper, write_audit, value_rows, VALUE_COLUMNS
from .completeness import completeness, source_data_requests, missing_supplements
from .formulas import load_library
from .models import claim_verdict
from .ontology import Ontologies
from .vocab import load_vocab, field_config


def papers(records_dir: Path = RECORDS_DIR) -> list[str]:
    return sorted(p.name for p in records_dir.iterdir() if (p / "record.yaml").exists())


def _write_csv(path: Path, rows: list[dict], cols: list[str] | None = None):
    cols = cols or sorted({k for r in rows for k in r})
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else ("" if v is None else v)) for k, v in r.items()})


def key_for(vocab, cfg):
    dk = cfg.get("default_key", {"value": {"must_match": []}, "direction": {"must_match": ["contrast"]}})

    def k(mt):
        for t in mt:
            if t in vocab.keys:
                kk = vocab.keys[t]
                return {"value": kk.value.__dict__, "direction": kk.direction.__dict__}
        return dk
    return k


def build(tag: str, field: str = DEFAULT_FIELD, records_dir: Path = RECORDS_DIR, out_root: Path = RELEASES_DIR,
          papers_dir: Path = PAPERS_DIR, only: list[str] | None = None, since: str | None = None) -> dict:
    onto = Ontologies()
    vocab = load_vocab(field, ontology=onto)
    from .vocab import recheck_ontology  # every adopted id and xref against the pinned releases (03-vocabulary)
    stale = recheck_ontology(vocab, onto)
    if stale:
        raise ValueError("ontology re-check failed; fix these terms or the pins before releasing:\n  " + "\n  ".join(stale))
    lib = load_library(field)
    cfg = field_config(field)
    out = out_root / tag
    out.mkdir(parents=True, exist_ok=True)
    audits, pas = {}, {}
    for pid in (only or papers(records_dir)):
        pa = audit_paper(pid, vocab, lib, records_dir, papers_dir)
        pas[pid] = pa
        audits[pid] = write_audit(pa, vocab, lib, records_dir)
    units = [u for pa in pas.values() for u in pa.across_units]
    comps = comparisons(vocab, units, key_for(vocab, cfg))
    strata_rows = strata(vocab, units, key_for(vocab, cfg))
    # tables
    sources, unit_rows, group_rows, items, claims, mappings, derivs, checks, values = [], [], [], [], [], [], [], [], []
    findings = []
    for pid, pa in pas.items():
        a, r = audits[pid], pa.rec
        deps = Counter(i["depth"] for i in a["items"].values())
        sources.append({"paper": pid, "title": r.source.title, "doi": r.source.doi, "year": r.source.year,
                        "lab": r.source.lab or "not stated", "kind": "paper", "files": r.source.files,
                        "depth": next((d for d in ("data", "readings", "printed only", "none") if deps.get(d)), "none")})
        for uid, u in a["units"].items():
            unit_rows.append({"paper": pid, "unit": uid, "where": u["where"], "title": u["title"], "status": u["status"],
                              "depth": u["depth"], "design": u["design"]})
            for gid, g in r.units[uid].groups.items():
                group_rows.append({"paper": pid, "unit": uid, "group": gid, "label": g.label,
                                   "context_terms": {f: (a["mappings"].get(f"units.{uid}.groups.{gid}.context.{f}") or {}).get("terms")
                                                     or (a["mappings"].get(f"units.{uid}.groups.{gid}.context.{f}") or {}).get("origin")
                                                     for f in g.context}})
        for iid, i in a["items"].items():
            it = r.evidence[iid]
            items.append({"paper": pid, "unit": i["unit"], "item": iid, "measure": it.measure,
                          "measure_terms": (a["mappings"].get(f"evidence.{iid}.measure") or {}).get("terms"),
                          "n": it.n if isinstance(it.n, str) else it.n.printed, "test": it.stats.test, "p": it.stats.p,
                          "finding": it.finding, "anchor": it.anchor.quote, "status": i["status"], "depth": i["depth"],
                          "contrast": i["contrast"], "direction": (i["direction"] or {}).get("direction") or "not available",
                          "direction_origin": (i["direction"] or {}).get("origin") or "",
                          "upstream_flags": i["upstream_flags"], "method": it.method or "not stated",
                          "software": it.software or "not stated"})
            for c in i["checks"]:
                checks.append({"paper": pid, "item": iid, **c})
        for cid, c in r.claims.items():
            claims.append({"paper": pid, "claim": cid, "kind": c.kind, "quote": c.quote, "scope": c.scope,
                           "rests_on": c.rests_on, "judgement": c.judgement, "verdict": claim_verdict(c) or "no verdict"})
        for at, m in a["mappings"].items():
            mappings.append({"paper": pid, "at": at, "stated": m["stated"], "terms": m["terms"], "qualifiers": m["qualifiers"],
                             "origin": m["origin"], "flag": m["flag"], "vocabulary_version": vocab.version})
        for k, d in a["derivations"].items():
            dv = pa.derived_file.derived[k]
            derivs.append({"paper": pid, "derivation": k, "item": dv.item, "formula": dv.formula,
                           "library": dv.library.formula if dv.library else "no formula",
                           "kind": lib.get(dv.library.formula).kind if dv.library and lib.get(dv.library.formula) else "",
                           "parameter_kinds": {n: x.kind for n, x in dv.inputs.items()}, **d})
        values += value_rows(pa)
        findings += [{"paper": pid, **f} for f in pa.findings]
    _write_csv(out / "papers.csv", sources)
    _write_csv(out / "units.csv", unit_rows)
    _write_csv(out / "groups.csv", group_rows)
    _write_csv(out / "items.csv", items)
    _write_csv(out / "values.csv", values, VALUE_COLUMNS)
    _write_csv(out / "mappings.csv", mappings)
    _write_csv(out / "derivations.csv", derivs)
    _write_csv(out / "checks.csv", checks)
    _write_csv(out / "findings.csv", findings, ["paper", "id", "unit", "check", "verdict", "source", "items", "checks", "example"])
    _write_csv(out / "claims.csv", claims)
    # strata, not pairs (05-across-sources): comparisons.csv keeps only the pairs with a computed verdict
    _write_csv(out / "strata.csv", strata_rows, ["stratum", "measure", "part", "key", "papers", "items", "values", "verdicts", "unknowns", "links"])
    _write_csv(out / "comparisons.csv", [c for c in comps if c["verdict"] != "not comparable"])
    _write_csv(out / "terms.csv", [{"id": t.id, "fields": t.fields, "label": t.label, "parent": t.parent, "source": t.source,
                                     "definition": t.definition, "scope": t.scope, "synonyms": [s["text"] for s in t.synonyms],
                                     "added": t.added.get("paper")} for t in vocab.terms.values()])
    fu = formula_use(pas)
    _write_csv(out / "formulas.csv", [{"formula": e.formula, "kind": e.kind, "statement": e.statement, "equations": e.equations,
                                        "holds_under": lib.holds_under(e.formula), "suspect": e.formula in lib.suspect,
                                        **fu.get(e.formula, {"papers_using": 0, "derivations": 0, "papers_in_conflict": 0,
                                                             "conflict_share": ""})}
                                       for e in lib.entries.values()])
    comp = completeness({p: pa.rec for p, pa in pas.items()}, {p: pa.derived_file for p, pa in pas.items() if pa.derived_file})
    _write_csv(out / "completeness.csv", comp)
    sdr = source_data_requests(audits)
    _write_csv(out / "source_data_requests.csv", sdr)
    ms = missing_supplements({p: pa.rec for p, pa in pas.items()}, papers_dir)
    _write_csv(out / "missing_supplements.csv", ms)
    cov = coverage(pas, vocab)
    _write_csv(out / "coverage.csv", cov)
    from .measures import new_terms_per_paper, refinements, near_duplicates, flags_per_field
    from .vocab import load_log
    log = load_log(field)
    mapped_by_paper = {p: pa.mapped for p, pa in pas.items()}
    _write_csv(out / "refinements.csv", refinements(log, vocab, mapped_by_paper))
    summary = release_summary(tag, audits, comps, vocab, lib, comp)
    summary["strata"] = {"strata": len(strata_rows), "with_two_or_more_papers": sum(1 for s in strata_rows if s["papers"] >= 2),
                          "linked": sum(1 for s in strata_rows if s["links"])}
    summary["vocabulary_measures"] = {"new_terms_per_paper": new_terms_per_paper(log),
                                      "near_duplicates": near_duplicates(vocab),
                                      "flags_per_field": flags_per_field(mapped_by_paper)}
    summary["source_data_requests"] = sdr
    summary["missing_supplements"] = ms
    (out / "summary.yaml").write_text(yaml.safe_dump(summary, sort_keys=False, allow_unicode=True))
    (out / "SCHEMA.md").write_text(schema_doc())
    from .changelog import write_history  # the logs it was built from, and what changed since the last release
    write_history(out, FIELDS_DIR / field, out_root, since)
    cover = FIELDS_DIR / field / "cover.yaml"  # the field's source review, shown on the explorer's cover
    if cover.exists():
        (out / "cover.yaml").write_text(cover.read_text(encoding="utf-8"), encoding="utf-8")
    from .explorer import write_explorer
    write_explorer(out, pas, audits)
    return summary


def formula_use(pas) -> dict:
    """Per formula entry: papers and derivations that use it, and papers in conflict with it (the paper's formula
    contradicts it, or its numbers are inconsistent). Reported only: an entry is held as suspect by a logged decision,
    never from this share (04-formulas, The formula library)."""
    use = defaultdict(lambda: {"papers": set(), "derivations": 0, "conflict": set()})
    for pid, pa in pas.items():
        df = pa.derived_file
        if not df:
            continue
        for k, d in df.derived.items():
            if d.library is None:
                continue
            u = use[d.library.formula]
            u["papers"].add(pid)
            u["derivations"] += 1
            c = pa.chains.get(k)
            if c is not None and "inconsistent" in (c.verdict, c.library_verdict):
                u["conflict"].add(pid)
    return {f: {"papers_using": len(u["papers"]), "derivations": u["derivations"], "papers_in_conflict": len(u["conflict"]),
                "conflict_share": round(len(u["conflict"]) / len(u["papers"]), 2)} for f, u in sorted(use.items())}


def coverage(pas, vocab) -> list[dict]:
    agg = defaultdict(lambda: {"sources": set(), "labs": set(), "items": 0})
    states = defaultdict(lambda: Counter())
    for pid, pa in pas.items():
        for at, m in pa.mapped.items():
            f = "measure" if at.endswith(".measure") else at.rsplit(".", 1)[-1]
            if m.terms:
                for t in m.terms:
                    a = agg[(f, t)]
                    a["sources"].add(pid)
                    a["labs"].add(pa.rec.source.lab or pid)
                    a["items"] += 1
            else:
                states[f][m.origin] += 1
    rows = [{"field": f, "term": t, "label": vocab.terms[t].label if t in vocab.terms else t, "sources": len(a["sources"]),
             "labs": len(a["labs"]), "values": a["items"]} for (f, t), a in sorted(agg.items())]
    for f, c in sorted(states.items()):
        for s, n in c.items():
            rows.append({"field": f, "term": s, "label": s, "sources": "", "labs": "", "values": n})
    return rows


def release_summary(tag, audits, comps, vocab, lib, comp) -> dict:
    tot = lambda key: dict(sum((Counter(a["summary"][key]) for a in audits.values()), Counter()))
    return {"tag": tag, "papers": list(audits), "vocabulary_version": vocab.version, "terms": len(vocab.terms),
            "formula_library_version": lib.version, "formulas": len(lib.entries),
            "per_paper": {p: a["summary"] for p, a in audits.items()},
            "item_status": tot("status"), "item_depth": tot("depth"), "mapping_origins": tot("mapping_origins"),
            "flags": tot("flags"), "directions": tot("directions"), "findings": tot("findings"),
            "comparisons": {"rows": len(comps), "verdicts": dict(Counter((c["part"], c["verdict"]) for c in comps).most_common()) and
                            {f"{k[0]}: {k[1]}": v for k, v in Counter((c["part"], c["verdict"]) for c in comps).most_common()},
                            "confirmed": dict(Counter(f"{c['part']}: {c['verdict']}" for c in comps
                                                      if c["verdict"] != "not comparable" and not c.get("assumes"))),
                            "conditional": dict(Counter(f"{c['part']}: {c['verdict']}" for c in comps
                                                        if c["verdict"] != "not comparable" and c.get("assumes"))),
                            "most_assumed": dict(Counter(f for c in comps for f in (c.get("assumes") or [])).most_common(10)),
                            "blockers": dict(Counter(b.split(":")[0] for c in comps for b in c["blocking"]).most_common(15))},
            "completeness_top": comp[:10]}


def schema_doc() -> str:
    from .models import Record, Item, Value, DataValue, Reading, Mapping, Derivation, FormulaEntry
    lines = ["# Release schema", "", "Generated from the Pydantic models (06-releases, Formats).", ""]
    for m in (Record, Item, Value, DataValue, Reading, Mapping, Derivation, FormulaEntry):
        lines.append(f"## {m.__name__}")
        for n, f in m.model_fields.items():
            lines.append(f"- `{n}`: {f.annotation}".replace("typing.", ""))
        lines.append("")
    return "\n".join(lines)
