"""One paper's audit, computed from its files (02-audit; 06-releases, Values as a dataset).

Writes records/<paper>/audit.yaml and values.csv (generated, git-ignored). Nothing
here is stored by an agent; everything is recomputed on every build.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import RECORDS_DIR, PAPERS_DIR
from .across import Unit, item_direction
from .chains import run_chains, scaling_checks, bound_checks, assumption_verdicts, same_n_checks
from .checks import check_item, status, depth, gather
from .groups import item_contrast, unit_design, stated_signatures
from .mapping import map_record, signer, wording_copies, Mapped
from .matching import Side
from .models import TermsFile, DerivedFile, claim_verdict, ContextObj
from .numbers import split_pm, parse_number, parse_p
from .record import resolve_context, load_yaml, group_context
from .gate_record import load_record_files


@dataclass
class PaperAudit:
    paper: str
    rec: object
    items: dict = field(default_factory=dict)
    units: dict = field(default_factory=dict)
    mapped: dict = field(default_factory=dict)
    chains: dict = field(default_factory=dict)
    extra_checks: list = field(default_factory=list)
    across_units: list = field(default_factory=list)
    terms_file: object = None
    derived_file: object = None
    figures: object = None
    readings: object = None
    data: object = None
    wording_copies: list = field(default_factory=list)
    findings: list = field(default_factory=list)


def mapped_side(m: Mapped | None) -> Side:
    if m is None:
        return Side(state="not stated")
    if m.origin in ("matched", "assigned"):
        return Side(terms=set(m.terms), qualifiers=dict(m.qualifiers))
    if m.origin == "state":
        from .text import normalize as _n
        return Side(terms={f"state:{_n(m.text or '')}"}, qualifiers={**m.qualifiers, "_text": m.text or ""})
    if m.origin == "quantity":
        return Side(qualifiers={**m.qualifiers, "_text": m.text or ""})
    if m.origin == "flagged":
        return Side(state="flagged", flag=m.flag)
    if m.origin in ("not stated", "not applicable", "none", "by reference", "unmapped"):
        return Side(state=m.origin if m.origin != "none" else "not applicable", qualifiers=dict(m.qualifiers))
    return Side(state="unmapped")


def _where(rec, iid, group, f):
    it = rec.evidence[iid]
    if f in it.context:
        return f"evidence.{iid}.context.{f}"
    u = rec.units[it.unit]
    if group and group in u.groups and f in u.groups[group].context:
        return f"units.{it.unit}.groups.{group}.context.{f}"
    if f in u.context:
        return f"units.{it.unit}.context.{f}"
    return f"default_context.{f}"


LATER_FIELDS: dict = {}  # field -> the field set that added it (from field.yaml 'since')


def item_context_sides(rec, mapped, iid, group) -> dict:
    ctx = resolve_context(rec, iid, group)
    out = {f: mapped_side(mapped.get(_where(rec, iid, group, f))) for f in ctx}
    for f, since in LATER_FIELDS.items():
        if f not in out and since > rec.field_set:
            out[f] = Side(state="not yet read")  # open world: added after this record was read
    return out


def value_qualifiers(mapping_quals: dict, values: list) -> dict:
    """A value's own expressed_as / normalised_to (from its legend) win over the measure mapping's
    (03-vocabulary, Relative measures)."""
    out = dict(mapping_quals)
    for v in values:
        for q in ("expressed_as", "normalised_to"):
            if getattr(v, q, None):
                out[q] = getattr(v, q)
    return out


def expressed_as_from_unit(unit: str | None) -> str | None:
    """A rule on the printed unit only (03-vocabulary, Relative measures)."""
    u = (unit or "").lower().strip()
    if "baseline" in u and "%" in u:
        return "% of baseline"
    if "%" in u and "change" in u:
        return "% change"
    if u in ("fold", "fold change", "-fold", "x-fold"):
        return "fold"
    if u and "%" not in u:
        from .numbers import try_unit
        tu = try_unit(unit)
        rel = {"fluorescence_change": "% change", "fluorescence_ratio": "fold"}
        if tu.dimension in rel:
            return rel[tu.dimension]
        if tu.name and tu.dimension not in (None, "", "dimensionless", "arbitrary"):
            return "absolute"
    return None


def audit_paper(paper: str, vocab, lib, records_dir: Path = RECORDS_DIR, papers_dir: Path = PAPERS_DIR) -> PaperAudit:
    rec, figs, rd, data = load_record_files(paper, records_dir)
    d = records_dir / paper
    tf = TermsFile.model_validate(load_yaml(d / "terms.yaml")) if (d / "terms.yaml").exists() else None
    df = DerivedFile.model_validate(load_yaml(d / "derived.yaml")) if (d / "derived.yaml").exists() else None
    pa = PaperAudit(paper, rec, terms_file=tf, derived_file=df, figures=figs, readings=rd, data=data)
    pa.mapped = map_record(vocab, rec, tf)
    pa.wording_copies = wording_copies(vocab, rec, pa.mapped)
    sign = signer(vocab, rec, tf)
    sigs_by_unit = {uid: stated_signatures(rec, uid, sign) for uid in rec.units}
    from .vocab import field_config
    _cfg = field_config(vocab.name)
    linked = _cfg.get("linked", [])
    LATER_FIELDS.clear()
    LATER_FIELDS.update({f: int(d.get("since", 1)) for f, d in _cfg["fields"].items() if int(d.get("since", 1)) > 1})
    pa.chains = run_chains(rec, df, lib, data.data, rd.readings, figs)
    # the derivation that gives each (item, group) value, for comparisons on rebuilt values
    rebuilt_for = {(df.derived[k].item, df.derived[k].group): c for k, c in pa.chains.items()} if df else {}
    pa.extra_checks = scaling_checks(rec, df, lib) if df else []
    pa.extra_checks += bound_checks(rec, df, lib)
    pa.extra_checks += same_n_checks(rec, df) if df else []
    assumptions = assumption_verdicts(df, lib, rec)
    for uid, u in rec.units.items():
        des = unit_design(rec, uid, sigs_by_unit[uid],
                          set_fields=[f for f, d in vocab.fields.items() if d.set and d.kind in ('terms', 'adopted')])
        pa.units[uid] = {"where": u.where, "title": u.title, "groups": list(u.groups),
                         "design": {"factorial": des.factorial, "factors": des.factors, "levels": des.levels} if des.factorial else None,
                         "items": [], "status": None, "depth": None}
    derivation_of = {}
    if df:
        for k, dv in df.derived.items():
            if dv.library:
                derivation_of.setdefault(dv.item, dv.library.formula)
    for iid, it in rec.evidence.items():
        cs = check_item(rec, iid, lib, data.data, rd.readings, figs)
        chain_rows = [c.as_dict() for k, c in pa.chains.items() if df.derived[k].item == iid] if df else []
        upstream = [f for k, c in pa.chains.items() if df.derived[k].item == iid for f in c.flags] if df else []
        chain_checks = [c for c in chain_rows if c["verdict"] != "cannot check"]
        from .checks import Check
        all_checks = cs + [Check("along a derivation", c["verdict"], c["derivation"], basis="printed") for c in chain_checks]
        all_checks += [Check(x["check"], x["verdict"], x.get("derivation", x.get("target", "")), x.get("entry"), basis="printed",
                             note=x.get("note", "")) for x in pa.extra_checks
                       if (x.get("derivation") and df.derived[x["derivation"]].item == iid)
                       or (x.get("target", "").split(".")[0] == iid)]
        evs = gather(rec, iid, data.data, rd.readings, figs)
        contrast = item_contrast(rec, it, sigs_by_unit[it.unit], linked=linked)
        from .across import direction_with_suspects
        direction = direction_with_suspects(it, rec, iid, data.data, rd.readings, figs)
        if contrast is not None and contrast.benchmark:
            from .across import Direction
            direction = Direction(None, None, "against benchmark: value comparisons only (02-audit, Groups)")
        if it.scaling is not None and not direction.direction:
            from .across import Direction
            pp_s = parse_p(it.stats.p)
            orig_s = "computed" if (pp_s and pp_s.significant) or chain_checks else "stated"
            direction = Direction(it.scaling.direction, orig_s, f"scaling with {it.scaling.independent_measure}")
        pa.items[iid] = {
            "unit": it.unit, "measure": it.measure, "status": status(all_checks), "depth": depth(all_checks),
            "checks": [c.as_dict() for c in all_checks],
            "derivations": chain_rows, "upstream_flags": upstream,
            "contrast": None if contrast is None else {
                "kind": contrast.kind, "fields": contrast.fields, "confound": contrast.confound,
                "balanced": contrast.balanced, "problems": contrast.problems, "aliased": contrast.aliased,
                "benchmark": contrast.benchmark, "linked": contrast.linked},
            "direction": {"direction": direction.direction, "origin": direction.origin, "basis": direction.basis}
            if direction.direction else None,
        }
        if direction.origin == "stated":
            pa.items[iid]["direction"]["note"] = "direction: stated, not computed"
        pa.units[it.unit]["items"].append(iid)
        # across-sources units
        mm = pa.mapped.get(f"evidence.{iid}.measure")
        mterms = tuple(sorted(mm.terms)) if mm and mm.origin in ("matched", "assigned") else ()
        mquals = dict(mm.qualifiers) if mm else {}
        base = dict(paper=paper, unit=it.unit, item=iid, measure_terms=mterms, measure_qualifiers=mquals,
                    method=it.method, derivation=derivation_of.get(iid), lab=rec.source.lab)
        if contrast is not None and contrast.kind in ("pair", "main effect"):
            cg = contrast.condition[0] if contrast.condition else None
            rg = contrast.reference[0] if contrast.reference else None
            pa.across_units.append(Unit(group=None, context=item_context_sides(rec, pa.mapped, iid, rg),
                                        contrast=contrast, cond_ctx=item_context_sides(rec, pa.mapped, iid, cg),
                                        ref_ctx=item_context_sides(rec, pa.mapped, iid, rg), direction=direction, **base))
        if it.scaling is not None:
            from .matching import match_text
            from types import SimpleNamespace
            ind_m = match_text(vocab, "measure", it.scaling.independent_measure)
            ind_key = "+".join(sorted(ind_m.terms)) if ind_m.terms else it.scaling.independent_measure
            sc_obj = SimpleNamespace(kind="scaling", field=f"scaling:{ind_key}", fields=[f"scaling:{ind_key}"],
                                     condition=[], reference=[], confound=False, balanced=True,
                                     problems=[], aliased=False, benchmark=False, linked=False)
            g0 = (it.group_ids() or [None])[0]
            pa.across_units.append(Unit(group=None, context=item_context_sides(rec, pa.mapped, iid, g0),
                                        contrast=sc_obj, cond_ctx={}, ref_ctx={}, direction=direction, **base))
        for g in (it.group_ids() or []):
            from .across import group_mean, group_sd
            m, unit_, basis_ = group_mean(evs[g])
            sp = group_sd(evs[g], basis_) if m is not None else None
            from .across import rebuilt_side
            m, sp, unit_, rb = rebuilt_side(m, sp, unit_, rebuilt_for.get((iid, g)))
            if m is not None:
                b = dict(base)
                own = [v for v in it.values.values() if v.group == g and v.x is None]
                b["measure_qualifiers"] = value_qualifiers(b["measure_qualifiers"], own)
                ea = expressed_as_from_unit(unit_)
                if ea and "expressed_as" not in b["measure_qualifiers"]:
                    b["measure_qualifiers"] = {**b["measure_qualifiers"], "expressed_as": ea}
                pa.across_units.append(Unit(group=g, context=item_context_sides(rec, pa.mapped, iid, g), mean=m,
                                            spread=sp, value_unit=unit_, rebuilt=rb, **b))
    order = ["inconsistent", "close", "consistent within reading", "consistent", "cannot check"]
    for uid, u in pa.units.items():
        sts = [pa.items[i]["status"] for i in u["items"]]
        u["status"] = "sound" if sts and all(s in ("consistent", "consistent within reading", "cannot check") for s in sts) else (
            "not sound" if sts else "no items")
        deps = [pa.items[i]["depth"] for i in u["items"]]
        for dd in ("data", "readings", "printed only", "none"):
            if dd in deps:
                u["depth"] = dd
                break
    pa.assumptions = assumptions
    from .findings import group_findings
    pa.findings = group_findings(rec, pa.items, data.data)
    return pa


def claim_direction_flags(rec, directions: dict) -> dict[str, list[str]]:
    """A claim judged 'follows' on direction whose asserted direction is opposite to an item's computed direction is
    flagged beside its verdict; the verdict is not changed (02-audit, A stated claim against its own evidence)."""
    out = {}
    for cid, c in rec.claims.items():
        if not c.judgement or c.judgement.get("direction") != "follows" or c.asserts_direction is None:
            continue
        for iid in c.rests_on:
            d = directions.get(iid) or {}
            if d.get("origin") == "computed" and {d.get("direction"), c.asserts_direction} == {"up", "down"}:
                out.setdefault(cid, []).append(
                    f"judged direction contradicts computed direction: claim asserts {c.asserts_direction}, "
                    f"{iid} computes {d['direction']} ({d.get('basis', '')})")
    return out


def audit_dict(pa: PaperAudit, vocab, lib) -> dict:
    rec = pa.rec
    from collections import Counter
    flags = Counter(m.flag for m in pa.mapped.values() if m.origin == "flagged")
    origins = Counter(m.origin for m in pa.mapped.values())
    cflags = claim_direction_flags(rec, {k: v["direction"] for k, v in pa.items.items()})
    claims = {cid: {"verdict": claim_verdict(c), "judgement": c.judgement, "flags": cflags.get(cid, [])}
              for cid, c in rec.claims.items()}
    return {
        "paper": pa.paper, "vocabulary_version": vocab.version, "formula_library_version": lib.version,
        "summary": {
            "units": len(rec.units), "items": len(rec.evidence), "claims": len(rec.claims),
            "status": dict(Counter(i["status"] for i in pa.items.values())),
            "depth": dict(Counter(i["depth"] for i in pa.items.values())),
            "mapping_origins": dict(origins), "flags": dict(flags),
            "split_requests": sum(len(m.split) for m in pa.terms_file.mappings) if pa.terms_file else 0,
            "confounds": sum(1 for i in pa.items.values() if i["contrast"] and i["contrast"]["confound"]),
            "confounds_aliased": sum(1 for i in pa.items.values() if i["contrast"] and i["contrast"].get("aliased")),
            "against_benchmark": sum(1 for i in pa.items.values() if i["contrast"] and i["contrast"].get("benchmark")),
            "linked_contrasts": sum(1 for i in pa.items.values() if i["contrast"] and i["contrast"].get("linked")),
            "contrast_problems": sum(1 for i in pa.items.values() if i["contrast"] and i["contrast"]["problems"]),
            "factorial_units": [u for u, v in pa.units.items() if v["design"]],
            "directions": dict(Counter((i["direction"] or {}).get("origin") or "not available" for i in pa.items.values()
                                       if i["contrast"] and i["contrast"]["kind"] in ("pair", "main effect"))),
            "claim_verdicts": dict(Counter(c["verdict"] or "no verdict" for c in claims.values())),
            "claims_contradicting_direction": sum(1 for c in claims.values() if c["flags"]),
            "findings": dict(Counter(f["verdict"] for f in pa.findings)),
        },
        "findings": pa.findings,
        "units": pa.units, "items": pa.items,
        "mappings": {at: {"origin": m.origin, "terms": m.terms, "qualifiers": m.qualifiers, "flag": m.flag, "stated": m.text}
                     for at, m in pa.mapped.items()},
        "wording_copies": pa.wording_copies,
        "derivations": {k: c.as_dict() for k, c in pa.chains.items()},
        "extra_checks": pa.extra_checks, "assumptions": getattr(pa, "assumptions", []),
        "claims": claims, "cross_references": [x.model_dump() for x in rec.cross_references],
    }


VALUE_COLUMNS = ["paper", "unit", "item", "group", "group_label", "group_terms", "kind", "value_printed", "value",
                 "unit_of_value", "origin", "interval_lo", "interval_hi", "x", "measure_terms", "context_terms", "contrast"]


def value_rows(pa: PaperAudit) -> list[dict]:
    rec = pa.rec
    rows = []
    links = {}
    for fid, f in pa.figures.figures.items():
        for label, gl in f.groups.items():
            links[(fid, label)] = gl

    def ctx_terms(iid, g):
        out = []
        for f in sorted(resolve_context(rec, iid, g)):
            m = pa.mapped.get(_where(rec, iid, g, f))
            if m is None:
                continue
            val = "|".join(m.terms) if m.terms else (m.text if m.origin == "quantity" else m.origin)
            out.append(f"{f}={val}")
        return "; ".join(out)

    def base(iid, g):
        it = rec.evidence[iid]
        u = rec.units[it.unit]
        mm = pa.mapped.get(f"evidence.{iid}.measure")
        gl = u.groups[g].label if g and g in u.groups else ""
        gterms = ""
        if g and g in u.groups:
            gterms = "; ".join(f"{f}={'|'.join(pa.mapped[f'units.{it.unit}.groups.{g}.context.{f}'].terms) or pa.mapped[f'units.{it.unit}.groups.{g}.context.{f}'].text}"
                               for f in u.groups[g].context)
        c = pa.items[iid]["contrast"]
        return {"paper": pa.paper, "unit": it.unit, "item": iid, "group": g or "", "group_label": gl, "group_terms": gterms,
                "measure_terms": "|".join(mm.terms) if mm and mm.terms else "", "context_terms": ctx_terms(iid, g),
                "contrast": ",".join(c["fields"]) if c else ""}

    for iid, it in rec.evidence.items():
        for vn, v in it.values.items():
            g = v.group
            try:
                m, s = split_pm(v.printed)
            except ValueError:
                m, s = None, None
            r = base(iid, g)
            r.update(kind=v.kind if v.kind in ("mean", "sd", "sem", "n") else ("mean" if v.kind == "value" else v.kind),
                     value_printed=v.printed, value=m or "", unit_of_value=v.unit, origin=v.origin, x=v.x or "",
                     interval_lo="", interval_hi="")
            if v.between:
                r["group"] = ",".join(v.between)
            rows.append(r)
            if s is not None:
                rows.append({**r, "kind": v.spread.lower() if v.spread in ("SD", "SEM") else "spread", "value": s,
                             "value_printed": v.printed})
        if it.n != "not stated":
            for g, n in (it.n.per_group or {"": it.n.printed}).items():
                rows.append({**base(iid, g or None), "kind": "n", "value_printed": n, "value": "", "unit_of_value": "",
                             "origin": it.n.origin, "x": "", "interval_lo": "", "interval_hi": ""})
        pp = parse_p(it.stats.p)
        if pp:
            rows.append({**base(iid, None), "kind": "p", "value_printed": it.stats.p,
                         "value": "" if pp.op == "sig" else pp.value, "unit_of_value": "",
                         "origin": "stated", "x": "", "interval_lo": "", "interval_hi": ""})
    for r in pa.data.data:
        if r.item in rec.evidence:
            rows.append({**base(r.item, r.group if r.group != "_" else None), "kind": r.kind, "value_printed": r.value,
                         "value": r.value, "unit_of_value": r.unit, "origin": "from data", "x": r.x or "",
                         "interval_lo": "", "interval_hi": ""})
    for rd in pa.readings.readings:
        gl = links.get((rd.figure, rd.group))
        if gl is None or gl.item not in rec.evidence:
            continue
        kind = {"point": "point", "mean": "mean", "error": "error"}.get(rd.kind, rd.kind)
        rows.append({**base(gl.item, gl.group if gl.group != "_" else None), "kind": kind, "value_printed": "",
                     "value": rd.value, "unit_of_value": gl.unit_of_value, "origin": "read", "x": "" if rd.x is None else rd.x,
                     "interval_lo": rd.lo, "interval_hi": rd.hi})
    for k, c in pa.chains.items():
        if c.rebuilt is not None:
            dv = pa.derived_file.derived[k]
            rows.append({**base(dv.item, dv.group), "kind": "mean", "value_printed": "", "value": f"{c.rebuilt:.6g}",
                         "unit_of_value": c.rebuilt_unit or "", "origin": "derived by LivingLit", "x": "",
                         "interval_lo": "", "interval_hi": ""})
    return rows


def write_audit(pa: PaperAudit, vocab, lib, records_dir: Path = RECORDS_DIR) -> dict:
    d = records_dir / pa.paper
    a = audit_dict(pa, vocab, lib)
    (d / "audit.yaml").write_text("# Generated by code on every build; never edited, never committed.\n" +
                                  yaml.safe_dump(a, sort_keys=False, allow_unicode=True, width=140))
    rows = value_rows(pa)
    with open(d / "values.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=VALUE_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return a
