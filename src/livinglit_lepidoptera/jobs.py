"""Running agent jobs from a script (07-building, No needless compute).

Each job is one headless LLM agent run (the command line is configuration, `agent.yaml`;
see `agent.py`) with its brief as system prompt. It writes its files and ends with a short report; the runner then runs the
review rules and the job's gate, writes both next to the report, and resumes the
agent with the gate's output if the gate fails (up to `attempts`). The
orchestrator reads reports and gate results, never transcripts. A figure job is
made only for a figure some item needs (`figures_needed`), one job per figure.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import date
from pathlib import Path

from . import PAPERS_DIR, RECORDS_DIR
from . import agent as _agent

ROOT = RECORDS_DIR.parent
BRIEFS = {"record": "record_reader.md", "figures": "figures_and_data.md", "vocabulary": "vocabulary_agent.md",
          "formula": "formula_agent.md", "survey": "survey.md", "merge": "survey_merge.md", "check": "independent_check.md"}
GATES = {"record": "record", "figures": "figures", "vocabulary": "terms", "formula": "derived"}
FIGURE_WHERE = re.compile(r"fig", re.I)


def figures_needed(rec, data_rows=(), figures=None) -> dict[str, list[str]]:
    """Figure units with item groups whose values no printed value, table, data row or existing reading gives, for
    items whose test a check can verify from individual points (`readings_use`). Units a figure job found to plot no
    points (`figures.yaml: no_points`) are not listed again (07-building, No needless compute)."""
    have = {(r.item, r.group) for r in data_rows}
    skipped = set()
    if figures is not None:
        have |= {(gl.item, gl.group) for f in figures.figures.values() for gl in f.groups.values()}
        skipped = set(figures.no_points)
    out: dict[str, list[str]] = {}
    for iid, it in rec.evidence.items():
        u = rec.units.get(it.unit)
        if u is None or not FIGURE_WHERE.search(u.where) or it.unit in skipped:
            continue
        if readings_use(it) == "none":
            continue  # no check could use this item's readings
        printed = set()
        for v in it.values.values():
            if v.group:
                printed.add(v.group)
            printed |= set(v.over or [])
        for g in it.group_ids():
            if g not in printed and (iid, g) not in have:
                out.setdefault(it.unit, []).append(f"{iid}/{g}")
    return out


def readings_use(it) -> str:
    """What a check could do with an item's figure readings, decided from the printed test as the checks do:
    'points' when a check can use individual points read from the figure (n against points, points to P, spread
    from points), 'none' when no check applies. No check uses a mean and error bar read from a bar: read summaries
    feed only comparisons with printed values and across papers."""
    from .numbers import parse_p, test_kind
    from .posthoc import NOT_IN_LIBRARY
    n_stated = it.n != "not stated"
    kind = it.kind_of_test
    if kind is None:  # a measurement: points can be counted against the printed n
        return "points" if n_stated else "none"
    test = it.stats.test or ""
    pp = parse_p(it.stats.p)
    if pp is None or pp.op == "sig" or NOT_IN_LIBRARY.search(test):
        return "none"
    tk = test_kind(test)
    if kind in ("main effect", "interaction"):
        return "points" if tk.family == "two_way_anova" else "none"
    if kind == "omnibus":
        return "points" if tk.family == "one_way_anova" else "none"
    if tk.family in ("kruskal_wallis", "friedman", "mann_whitney", "wilcoxon_signed_rank", "paired_t", "correlation",
                     "contingency", "other"):
        return "none"
    return "points"


def job_prompt(job: str, paper: str, figure: str | None = None) -> str:
    what = {"record": f"Read the paper {paper} into records/{paper}/record.yaml.",
            "figures": f"Read figure unit {figure} of {paper}: write its script under records/{paper}/figures/ and its "
                       f"entries in figures.yaml and readings.yaml, or data.yaml rows where released data hold the values.",
            "vocabulary": f"Map {paper}'s stated context and measures: records/{paper}/terms.yaml and library edits.",
            "formula": f"Write {paper}'s derivations: records/{paper}/derived.yaml and formula library edits.",
            "survey": f"Survey {paper}'s methods and figure legends: survey/{paper}.yaml.",
            "merge": "Name each untagged survey condition: survey/merge.yaml. Your whole input is survey/untagged.yaml "
                     "(paper -> index -> condition text, written by code); open a survey file only to read a quote.",
            "check": f"Run the independent check for {paper}."}[job]
    return (f"{what} Papers are in {PAPERS_DIR.name}/{paper}/. Run your gate with `livinglit gate` as you work. "
            f"Finish with a short report (at most 15 lines): what you wrote, every judgement you were unsure of, "
            f"and anything you could not record.")


def job_argv(job: str, paper: str, figure: str | None = None, cfg: dict | None = None, resume: str | None = None,
             prompt: str | None = None) -> list[str]:
    others = [d.name for d in RECORDS_DIR.iterdir() if d.is_dir() and d.name != paper] if RECORDS_DIR.is_dir() else []
    denied = [ROOT / "archive", ROOT / "docs" / "archive", PAPERS_DIR / "_benchmark"] + [RECORDS_DIR / o for o in others]
    return _agent.job_argv(cfg or _agent.load(), prompt or job_prompt(job, paper, figure),
                           str(ROOT / "readers" / "instructions" / BRIEFS[job]), resume, [str(d) for d in denied])


def job_gate(job: str, paper: str, apply: bool = False) -> list[str]:
    """The orchestrator's own run of a job's gate ([] = passes)."""
    if job == "survey":
        from .record import load_yaml
        from .survey import check_survey
        from .vocab import field_config
        f = ROOT / "survey" / f"{paper}.yaml"
        if not f.exists():
            return [f"survey/{paper}.yaml was not written"]
        return check_survey(load_yaml(f), PAPERS_DIR / paper, field_config())
    if job == "merge":
        import yaml as _y
        from .survey import tally
        sd = ROOT / "survey"
        if not (sd / "merge.yaml").exists():
            return ["survey/merge.yaml was not written"]
        surveys = {f.stem: _y.safe_load(f.read_text()) for f in sd.glob("*.yaml") if f.stem not in ("merge", "untagged")}
        try:
            tally(surveys, (_y.safe_load((sd / "merge.yaml").read_text()) or {}).get("names", {}))
        except ValueError as e:
            return [str(e)]
        return []
    if job in GATES:
        if not (RECORDS_DIR / paper / "record.yaml").exists():
            return [f"records/{paper}/record.yaml was not written"]
        from .cli import gate
        return gate(GATES[job], paper, apply)
    return []


def run_job(job: str, paper: str, figure: str | None = None, attempts: int = 3, cfg: dict | None = None) -> dict:
    """Run one job to a passing gate (or out of attempts); write report, review and gate output; return the summary."""
    from .review import review
    out = ROOT / "runs" / f"{date.today().isoformat()}_jobs" / paper
    out.mkdir(parents=True, exist_ok=True)
    name = job + (f"_{figure}" if figure else "")
    cfg = cfg or _agent.load()
    env = _agent.env(cfg)
    if job == "merge":  # code hands the merge job only the untagged conditions
        import yaml as _y
        from .survey import untagged
        sd = ROOT / "survey"
        surveys = {f.stem: _y.safe_load(f.read_text()) for f in sd.glob("*.yaml") if f.stem not in ("merge", "untagged")}
        (sd / "untagged.yaml").write_text(_y.safe_dump(untagged(surveys), allow_unicode=True, sort_keys=False))
    session, cost, turns, result, probs, rev = None, 0.0, 0, "", [], {"blocking": [], "for_review": []}
    prompt = None
    for attempt in range(1, attempts + 1):
        p = subprocess.run(job_argv(job, paper, figure, cfg, resume=session, prompt=prompt), cwd=ROOT, env=env,
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        ev = _agent.parse(p.stdout, p.stderr)
        session = ev["session"] or session
        cost += ev["cost"]
        turns += ev["turns"]
        result = ev["result"]
        if _agent.usage_limited(cfg, result):
            probs = ["usage limit"]
            break
        if job == "record" and (RECORDS_DIR / paper / "record.yaml").exists():
            rev = review(paper)  # a job that wrote no record fails its gate below and is retried
        probs = rev["blocking"] + job_gate(job, paper)
        if not probs:
            if job in ("vocabulary", "formula"):
                probs = job_gate(job, paper, apply=True)  # only the orchestrator's own run applies edits
            if not probs:
                break
        prompt = "The gate found these problems; fix them and report again:\n" + "\n".join(probs[:60])
    summary = {"job": name, "paper": paper, "attempts": attempt, "passed": not probs, "cost_usd": round(cost, 2),
               "turns": turns, "gate": probs, "for_review": rev["for_review"], "usage_limit": probs == ["usage limit"]}
    (out / f"{name}.report.md").write_text(result)
    (out / f"{name}.json").write_text(json.dumps(summary, indent=1))
    return summary


def _needed_units(paper: str) -> list[str]:
    from .gate_record import load_record_files
    rec, figs, rd, data = load_record_files(paper)
    return list(figures_needed(rec, data.data, figs))


def _mark(paper: str, unit: str, reason: str) -> None:
    from .first_look import mark_no_points
    mark_no_points(RECORDS_DIR / paper, unit, reason)


def add_paper(paper: str, run=None, gate=None, needed=None, look=None, mark=None) -> dict:
    """Add one paper: record, one job per figure that needs reading (points only), vocabulary, formula; each step
    runs only if its gate does not already pass, so adding is safe to repeat after a stop (07-building, Jobs).
    Before each figure job a first look may rule the figure out (`first_look`); the unit is then marked no_points.
    Returns status 'added', 'parked' (a gate kept failing; the paper waits for a person) or 'usage limit'."""
    from .first_look import first_look
    run = run or run_job
    gate = gate or (lambda job, p: job_gate(job, p))
    needed = needed or _needed_units
    look = look or first_look
    mark = mark or _mark
    cost = 0.0
    looked_off = []

    def step(job, figure=None):
        nonlocal cost
        r = run(job, paper, figure=figure)
        cost += float(r.get("cost_usd") or 0)
        name = job + (f"_{figure}" if figure else "")
        if r.get("usage_limit"):
            return {"paper": paper, "status": "usage limit", "step": name, "cost_usd": cost}
        if not r.get("passed"):
            return {"paper": paper, "status": "parked", "step": name, "problems": r.get("gate", []), "cost_usd": cost}
        return None

    if gate("record", paper):
        stop = step("record")
        if stop:
            return stop
    tried = set()
    for unit in needed(paper):
        if unit in tried:
            continue
        tried.add(unit)
        lk = look(paper, unit)
        cost += float(lk.get("cost_usd") or 0)
        if lk.get("skip"):
            mark(paper, unit, lk["reason"])
            looked_off.append(unit)
            continue
        stop = step("figures", unit)
        if stop:
            return stop
    for job in ("vocabulary", "formula"):
        if gate(job, paper):
            stop = step(job)
            if stop:
                return stop
    return {"paper": paper, "status": "added", "cost_usd": round(cost, 2), "looked_off": looked_off}
