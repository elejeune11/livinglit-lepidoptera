"""livinglit: gates as tools for agents, and the build (07-building, Jobs).

  livinglit gate record <paper>     record schema, anchors, units, groups, context
  livinglit gate figures <paper>    every figure script and data cell reproduces what is stored
  livinglit gate terms <paper>      mapping complete, edits anchored and checked
  livinglit gate derived <paper>    derivations anchored, formulas checked
  livinglit lookup <ontology> <text>   search a pinned ontology release (chebi, cl, mondo, uo, cellosaurus)
  livinglit check-id <id>           check an id against the pinned releases
  livinglit vocab show [field]      the current vocabulary
  livinglit stated <paper>          the record's stated values and what code matches
  livinglit formula check <name>    replay an entry's checks
  livinglit audit <paper>           write audit.yaml and values.csv
  livinglit release <tag>           build releases/<tag>/

Only the orchestrator's own run of a gate counts.
"""
from __future__ import annotations

import argparse
import json
import sys

import yaml

from . import PAPERS_DIR, RECORDS_DIR, DEFAULT_FIELD


def _found_fn(paper):
    from .text import find_quote
    return lambda q: find_quote(q, PAPERS_DIR / paper) is not None


def _anchor_of(rec):
    def f(path):
        parts = path.split(".")
        try:
            if parts[0] == "evidence":
                return rec.evidence[parts[1]].anchor.quote
            if parts[0] == "claims":
                return rec.claims[parts[1]].quote
            if parts[0] == "citations":
                return rec.citations[parts[1]].anchor.quote
            if parts[0] == "units" and parts[-1] == "anchor":
                u = rec.units[parts[1]]
                if len(parts) == 3:
                    return u.anchor.quote
                return u.groups[parts[3]].anchor.quote
        except (KeyError, AttributeError, IndexError):
            return None
        return None
    return f


def gate(kind: str, paper: str, apply: bool = False) -> list[str]:
    if kind == "panels":
        from .panels import check_panels_gate
        objs, p_probs = check_panels_gate(paper, RECORDS_DIR, PAPERS_DIR, store=apply)
        if apply and not p_probs:
            tot_pts = sum(o.get("n_digitized_points", 0) for o in objs)
            print(f"stored {len(objs)} panel objects and {tot_pts} digitized data points in records/{paper}/digitized/")
        return p_probs
    from .gate_record import check_record, check_figures_and_data
    from .record import load_yaml
    from .vocab import field_config
    d = RECORDS_DIR / paper
    pdir = PAPERS_DIR / paper
    cfg = field_config()
    raw = load_yaml(d / "record.yaml")
    rec, probs = check_record(raw, pdir, cfg, check_text=True)
    if kind == "record":
        return probs
    if rec is None or probs:
        return ["record gate fails first:"] + probs
    if kind == "figures":
        return check_figures_and_data(rec, d, pdir)
    if kind == "terms":
        from .gate_terms import check_terms
        from .models import TermsFile
        from .ontology import Ontologies
        from .vocab import load_vocab, check_edits, append_version, save_vocab, edit_kind
        from .gate_terms import resolve_anchor_paths
        onto = Ontologies()
        v = load_vocab(ontology=onto)
        try:
            tf = TermsFile.model_validate(load_yaml(d / "terms.yaml"))
        except Exception as e:
            return [f"schema: {e}"]
        from .vocab import load_log
        from .gate_terms import pending_edits
        # edits already logged for this paper are not checked again; a re-map's new edits are (03-vocabulary, Earlier papers)
        pending = pending_edits(resolve_anchor_paths(tf.edits, _anchor_of(rec)), load_log(), paper)
        tf = tf.model_copy(update={"edits": pending})
        out = check_terms(v, rec, tf, found=_found_fn(paper), ontology=onto, anchor_of=_anchor_of(rec),
                          check_edits_too=bool(pending))
        if apply and not pending and not out:
            print("nothing new: every edit is already in the log; mappings checked against the current vocabulary")
            return out
        if apply and not out:
            edits = pending
            ver = append_version(edits, paper, tf.agent.model_dump() if tf.agent else None)
            save_vocab(load_vocab(ontology=onto))
            print(f"applied: vocabulary version {ver}" if ver else "nothing new: no version added")
        return out
    if kind == "derived":
        from .gate_derived import check_derived
        from .formulas import load_library, append_entries
        from .models import DerivedFile, FiguresFile, ReadingsFile, DataFile
        from .vocab import load_vocab
        from .gate_record import load_record_files
        _, figs, rd, data = load_record_files(paper)
        lib = load_library()
        try:
            df = DerivedFile.model_validate(load_yaml(d / "derived.yaml"))
        except Exception as e:
            return [f"schema: {e}"]
        probs, rejected = check_derived(rec, df, lib, found=_found_fn(paper), vocab=load_vocab(),
                                        data_rows=data.data, readings=rd.readings, figures=figs)
        if rejected:
            probs = probs + [f"proposal rejected (non-blocking; mark the step no_formula or fix it): {r}" for r in rejected]
        if apply and not [p for p in probs if not p.startswith("proposal rejected")]:
            from . import FIELDS_DIR
            from .formulas import check_entry, Library
            work = Library(dict(lib.entries), lib.version, lib.suspect)
            ok = []
            for p in df.proposals:
                if not check_entry(p, work, load_vocab()):
                    work.entries[p.formula] = p
                    ok.append(p)
            ver = append_entries(ok, FIELDS_DIR / DEFAULT_FIELD / "formulas", paper, df.agent.model_dump() if df.agent else None)
            print(f"applied: formula library version {ver}" if ver else "nothing new: no version added")
            return [p for p in probs if not p.startswith("proposal rejected")]
        return probs
    if kind == "panels":
        from .panels import check_panels_gate
        objs, p_probs = check_panels_gate(paper, RECORDS_DIR, PAPERS_DIR, store=apply)
        if apply and not p_probs:
            tot_pts = sum(o.get("n_digitized_points", 0) for o in objs)
            print(f"stored {len(objs)} panel objects and {tot_pts} digitized data points in records/{paper}/digitized/")
        return p_probs
    raise SystemExit(f"unknown gate {kind}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="livinglit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gate")
    g.add_argument("kind", choices=["record", "figures", "terms", "derived", "panels"])
    g.add_argument("paper")
    g.add_argument("--apply", action="store_true")
    lk = sub.add_parser("lookup")
    lk.add_argument("ontology")
    lk.add_argument("text", nargs="+")
    ci = sub.add_parser("check-id")
    ci.add_argument("id")
    vs = sub.add_parser("vocab")
    vs.add_argument("what", choices=["show"])
    st = sub.add_parser("stated")
    st.add_argument("paper")
    fc = sub.add_parser("formula")
    fc.add_argument("what", choices=["check", "list"])
    fc.add_argument("name", nargs="?")
    au = sub.add_parser("audit")
    au.add_argument("paper")
    rl = sub.add_parser("release")
    rl.add_argument("tag")
    rl.add_argument("--since", help="the release to compare with (default: the latest other release)")
    ce = sub.add_parser("cells")
    ce.add_argument("paper")
    ce.add_argument("file")
    ce.add_argument("sheet")
    ce.add_argument("range")
    fg = sub.add_parser("figure")
    fg.add_argument("paper")
    fg.add_argument("name")
    fg.add_argument("--store", action="store_true")
    ov = sub.add_parser("overlay", help="draw a figure's stored readings over it, outside the repository")
    ov.add_argument("paper")
    ov.add_argument("figure", nargs="?", help="a figure in figures.yaml (default: every figure)")
    ov.add_argument("--out", help="folder (default: ../livinglit_overlays_dont_commit/<paper>)")
    rn = sub.add_parser("run")
    rn.add_argument("job", choices=["record", "figures", "vocabulary", "formula", "survey", "merge", "check"])
    rn.add_argument("paper")
    rn.add_argument("--figure")
    ad = sub.add_parser("add", help="add papers: every job to a passing gate; safe to repeat")
    ad.add_argument("papers", nargs="+")
    st_ = sub.add_parser("site", help="copy a release's explorer into a folder for static hosting (as index.html)")
    st_.add_argument("release", help="release tag under releases/")
    st_.add_argument("folder")
    fn = sub.add_parser("figures-needed")
    fn.add_argument("paper")
    rv = sub.add_parser("review")
    rv.add_argument("paper")
    sv = sub.add_parser("survey")
    sv.add_argument("what", choices=["gate", "tally"])
    sv.add_argument("paper", nargs="?")
    rq = sub.add_parser("requests")
    rq.add_argument("out", help="folder for the drafts")
    hv = sub.add_parser("harvest", help="scan JATS XML supplements/repositories and build unified data-hub release")
    hv.add_argument("paper", nargs="?", help="optional paper to scan JATS XML links; omit with --build-hub")
    hv.add_argument("--build-hub", default=None, metavar="TAG", help="build releases/<TAG>/data_hub.json")
    qa = sub.add_parser("qa", help="render BBox, Plot Overlay, and Microscopy FFT Grating QA sheets")
    qa.add_argument("paper", help="paper record id")
    qa.add_argument("--out", default=None, help="output folder (default /tmp/livinglit_qa_<paper>)")
    a = ap.parse_args(argv)
    if a.cmd == "qa":
        from pathlib import Path as _P
        from .qa_overlays import render_bbox_sheet, render_plot_overlay_sheet, render_fft_overlay_sheet
        out_dir = _P(a.out) if a.out else _P(f"/tmp/livinglit_qa_{a.paper}")
        out_dir.mkdir(parents=True, exist_ok=True)
        print("bbox:", render_bbox_sheet(a.paper, out_dir / f"bbox_{a.paper}.png"))
        print("plots:", render_plot_overlay_sheet(a.paper, out_dir / f"plots_{a.paper}.png"))
        print("fft:", render_fft_overlay_sheet(a.paper, out_dir / f"fft_{a.paper}.png"))
        rp = RECORDS_DIR / a.paper / "qa" / "report.json"
        if rp.is_file():
            r = json.loads(rp.read_text(encoding="utf-8"))
            print(f"qa/report.json: {r['n_figures']} figs, {r['n_atomic_panels']} atomic panels, {r['composite_panels']} composites, {len(r['flagged_panels'])} flagged")
        return
    if a.cmd == "harvest":
        from .harvest import scan_jats_resources, build_data_hub
        if a.paper:
            print(yaml.safe_dump(scan_jats_resources(a.paper), sort_keys=False, allow_unicode=True))
        if a.build_hub:
            hub = build_data_hub(a.build_hub)
            print(yaml.safe_dump(hub["summary"], sort_keys=False))
        return
    if a.cmd == "run":
        from .jobs import run_job
        print(json.dumps(run_job(a.job, a.paper, a.figure), indent=1))
        return
    if a.cmd == "site":
        from .explorer import make_site
        from . import RELEASES_DIR
        print("\n".join(make_site(RELEASES_DIR / a.release, a.folder)))
        return
    if a.cmd == "add":
        from .jobs import add_paper
        out = []
        for p in a.papers:
            r = add_paper(p)
            out.append(r)
            print(json.dumps(r))
            if r["status"] == "usage limit":
                break  # resume after the reset: add skips what is done
        sys.exit(0 if all(r["status"] == "added" for r in out) and len(out) == len(a.papers) else 1)
    if a.cmd == "figures-needed":
        from .jobs import figures_needed
        from .gate_record import load_record_files
        rec, figs, rd, data = load_record_files(a.paper)
        for uid, gs in figures_needed(rec, data.data, figs).items():
            print(f"{uid}\t{rec.units[uid].where}\t{len(gs)} item groups: {', '.join(gs[:8])}{' ...' if len(gs) > 8 else ''}")
        return
    if a.cmd == "review":
        from .review import review
        r = review(a.paper)
        print(yaml.safe_dump(r, sort_keys=False, allow_unicode=True))
        sys.exit(1 if r["blocking"] else 0)
    if a.cmd == "survey":
        from .survey import check_survey, tally
        from .record import load_yaml
        from .vocab import field_config
        sd = RECORDS_DIR.parent / "survey"
        if a.what == "gate":
            probs = check_survey(load_yaml(sd / f"{a.paper}.yaml"), PAPERS_DIR / a.paper, field_config())
            print("\n".join(probs) or "survey gate passes")
            sys.exit(1 if probs else 0)
        surveys = {p.stem: load_yaml(p) for p in sd.glob("*.yaml") if p.stem not in ("merge", "untagged")}
        names = (load_yaml(sd / "merge.yaml") or {}).get("names", {}) if (sd / "merge.yaml").exists() else {}
        print(yaml.safe_dump(tally(surveys, names), sort_keys=False, allow_unicode=True))
        return
    if a.cmd == "requests":
        from .requests import write_drafts
        from .audit import audit_paper
        from .formulas import load_library
        from .ontology import Ontologies
        from .vocab import load_vocab
        from .release import papers as _papers
        from pathlib import Path as _P
        vocab, lib = load_vocab(DEFAULT_FIELD, ontology=Ontologies()), load_library(DEFAULT_FIELD)
        pas = {p: audit_paper(p, vocab, lib) for p in _papers(RECORDS_DIR)}
        from .audit import audit_dict
        print("drafts:", write_drafts({p: audit_dict(pa, vocab, lib) for p, pa in pas.items()},
                                      {p: pa.rec for p, pa in pas.items()}, _P(a.out)))
        return
    if a.cmd == "gate":
        probs = gate(a.kind, a.paper, a.apply)
        if probs:
            print(f"GATE FAILS ({len(probs)}):")
            for p in probs[:300]:
                print(" -", p)
            if len(probs) > 300:
                print(f" ... and {len(probs) - 300} more")
            sys.exit(1)
        print("GATE PASSES")
    elif a.cmd == "lookup":
        from .ontology import Ontologies
        for r in Ontologies().search(a.ontology, " ".join(a.text)):
            print(json.dumps(r, ensure_ascii=False))
    elif a.cmd == "check-id":
        from .ontology import Ontologies
        print(Ontologies().check(a.id) or "not in the pinned releases")
    elif a.cmd == "vocab":
        from .vocab import load_vocab
        print(yaml.safe_dump(load_vocab().to_yaml(), sort_keys=False, allow_unicode=True, width=140))
    elif a.cmd == "stated":
        from .mapping import occurrences, map_occurrence
        from .gate_record import load_record_files
        from .vocab import load_vocab
        from .text import normalize
        rec = load_record_files(a.paper)[0]
        v = load_vocab()
        seen = {}
        for o in occurrences(rec):
            k = (o.field, normalize(o.text or ""))
            if k in seen:
                continue
            m = map_occurrence(v, o, {})
            seen[k] = 1
            print(f"{o.field}\t{o.text!r}\t{m.origin}\t{','.join(m.terms)}\t(first at {o.at})")
    elif a.cmd == "formula":
        from .formulas import load_library, check_entry, Library
        lib = load_library()
        if a.what == "list":
            for e in lib.entries.values():
                print(f"{e.formula}\t{e.kind}\t{e.equations}\tholds under: {lib.holds_under(e.formula)}")
        else:
            e = lib.get(a.name)
            rest = Library({k: v for k, v in lib.entries.items() if k != a.name})
            print(check_entry(e, rest) or "all checks pass")
    elif a.cmd == "audit":
        from .audit import audit_paper, write_audit
        from .formulas import load_library
        from .vocab import load_vocab
        v, lib = load_vocab(), load_library()
        s = write_audit(audit_paper(a.paper, v, lib), v, lib)["summary"]
        print(yaml.safe_dump(s, sort_keys=False))
    elif a.cmd == "cells":
        from .data import sheet_cells, col_letters
        import re as _re
        p = PAPERS_DIR / a.paper / a.file
        if a.sheet == "?":  # list the sheets
            if p.suffix.lower() == ".xlsb":
                from .data import xlsb_sheets
                print("\n".join(xlsb_sheets(str(p))))
            else:
                import openpyxl
                print("\n".join(openpyxl.load_workbook(p, read_only=True).sheetnames))
            return
        cells = sheet_cells(str(p), None if a.sheet in ("-", "") else a.sheet, p.stat().st_mtime_ns)
        m = _re.match(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", a.range)
        def ci(x):
            n = 0
            for ch in x:
                n = n * 26 + ord(ch) - 64
            return n
        c0, r0, c1, r1 = ci(m.group(1)), int(m.group(2)), ci(m.group(3)), int(m.group(4))
        for r in range(r0, r1 + 1):
            row = [f"{col_letters(c)}{r}={cells[f'{col_letters(c)}{r}']}" for c in range(c0, c1 + 1) if f"{col_letters(c)}{r}" in cells]
            if row:
                print("  ".join(row))
    elif a.cmd == "overlay":
        from .figures.overlay import figure_overlay
        from .models import FiguresFile
        from .record import load_yaml
        names = [a.figure] if a.figure else list(FiguresFile.model_validate(
            load_yaml(RECORDS_DIR / a.paper / "figures.yaml")).figures)
        for n in names:
            from pathlib import Path as _P
            print(figure_overlay(a.paper, n, _P(a.out) if a.out else None))
    elif a.cmd == "figure":
        from .figures.run import run_figure
        from .models import FiguresFile, ReadingsFile
        from .record import load_yaml
        d = RECORDS_DIR / a.paper
        figs = FiguresFile.model_validate(load_yaml(d / "figures.yaml"))
        e = figs.figures[a.name]
        rows, errs = run_figure(a.name, e, d, PAPERS_DIR / a.paper)
        for er in errs:
            print("ERROR", er)
        from collections import defaultdict
        by = defaultdict(list)
        for r in rows:
            by[(r.group, r.kind)].append(r.value)
        for (g, k), vs in by.items():
            print(f"{g}\t{k}\tcount={len(vs)}\t" + ", ".join(f"{v:.4g}" for v in vs[:40]))
        if a.store and not errs:
            rp = d / "readings.yaml"
            old = ReadingsFile.model_validate(load_yaml(rp)) if rp.exists() else ReadingsFile()
            keep = [r for r in old.readings if r.figure != a.name] + rows
            rp.write_text(yaml.safe_dump({"readings": [r.model_dump(exclude_none=True) for r in keep]}, sort_keys=False))
            print(f"stored {len(rows)} readings for {a.name}")
    elif a.cmd == "release":
        from .release import build
        print(yaml.safe_dump(build(a.tag, since=a.since), sort_keys=False, allow_unicode=True)[:4000])


if __name__ == "__main__":
    main()
