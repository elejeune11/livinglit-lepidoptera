"""Papers needed for completeness, and source-data requests (02-audit, Stated by reference; 06-releases; 08 decision 19).

A value stated only by citation counts once per field and paper. Cited papers
not in the corpus are ranked by how many values depend on them.
"""
from __future__ import annotations

from collections import defaultdict

from .models import ByReference, ContextObj
from .record import all_context_values
from .text import normalize


def by_reference_uses(rec) -> list[tuple[str, str, str]]:
    """(citation key, field or slot, location) for every value stated only by citation."""
    out = []
    for at, f, v in all_context_values(rec):
        if isinstance(v, ContextObj) and v.by_reference:
            out.append((v.by_reference.citation, f, at))
    for iid, it in rec.evidence.items():
        if isinstance(it.definition, ByReference):
            out.append((it.definition.citation, f"measure definition: {it.measure}", f"evidence.{iid}.definition"))
    return out


def completeness(records: dict, derived: dict) -> list[dict]:
    corpus_dois = {normalize(r.source.doi): pid for pid, r in records.items() if r.source.doi}
    agg: dict = {}
    for pid, rec in records.items():
        uses = by_reference_uses(rec)
        df = derived.get(pid)
        if df:
            for k, d in df.derived.items():
                for n, i in d.inputs.items():
                    if i.by_reference:
                        uses.append((i.by_reference.citation, f"parameter {n} of {k}", f"derived.{k}"))
        for cit, slot, at in uses:
            c = rec.citations.get(cit)
            if c is None:
                continue
            key = normalize(c.doi) if c.doi else normalize(c.text)[:80]
            if c.doi and normalize(c.doi) in corpus_dois:
                continue  # in the corpus: carried from its record on the next build
            e = agg.setdefault(key, {"citation": c.text, "doi": c.doi, "fields": set(), "records": set(), "locations": []})
            e["fields"].add((pid, slot.split(":")[0] if slot.startswith("measure") else slot))
            e["records"].add(pid)
            e["locations"].append(f"{pid}:{at}")
    rows = []
    for e in agg.values():
        rows.append({"citation": e["citation"], "doi": e["doi"], "values": len(e["fields"]),
                     "records": sorted(e["records"]), "fields": sorted(f"{p}:{s}" for p, s in e["fields"]),
                     "locations": e["locations"][:50]})
    rows.sort(key=lambda r: (-r["values"], r["citation"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def source_data_requests(audits: dict) -> list[dict]:
    """Papers whose items stay cannot check for lack of per-sample data, ranked by items it would open."""
    rows = []
    for pid, a in audits.items():
        n = sum(1 for i in a["items"].values() if i["status"] == "cannot check" and i["depth"] in ("none", "printed only"))
        if n:
            rows.append({"paper": pid, "items_cannot_check": n,
                         "items_total": len(a["items"])})
    rows.sort(key=lambda r: -r["items_cannot_check"])
    return rows


def missing_supplements(records: dict, papers_dir) -> list[dict]:
    rows = []
    for pid, r in records.items():
        missing = [f for f in r.source.files if not (papers_dir / pid / f).exists()] + list(r.source.missing)
        if missing:
            rows.append({"paper": pid, "missing": missing})
    return rows
