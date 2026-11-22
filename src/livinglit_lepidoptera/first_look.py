"""The first look (07-building, No needless compute).

Before a figure job, one cheap look at the page decides whether the figure unit plots
individual points. Code finds the page where the unit's legend starts and the page
before it; a small model is shown both pages and answers yes, no or unsure, naming
the page that shows the unit. The figure job is skipped only on "no" with a page
named, and the unit is recorded in `figures.yaml: no_points` marked *first look*.
Anything else (yes, unsure, no page, a unit naming several figures, a legend not
found or found in more than one file) runs the figure job as before.

Studied in runs/2026-11-10_figure_first_look/: no misses in 82 units with points.
Page images are rendered to a temporary folder named *dont_commit* and deleted;
legend text stays in memory.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

import yaml

from . import PAPERS_DIR, RECORDS_DIR

DPI = 110
NAME = {"F": "Figure ", "S": "Supplementary Figure ", "ED": "Extended Data Figure "}

_ONE = r"[A-Za-z](?![A-Za-z])"
SUPP = r"Suppl(?:ement(?:ary|al)?|\.)?"
REF = re.compile(r"(?P<ed>Extended\s+Data\s+)?(?P<sup>" + SUPP + r"\s*)?(?:Fig(?:ure)?s?\.?)\s*(?P<s>S)?(?P<num>\d{1,2})"
                 r"(?P<p>" + _ONE + r"(?:\s*(?:[–\-,]|and|to)\s*(?:S?\d{1,2})?" + _ONE + r")*)?", re.I)

SEP = r"[\s,]+"
HEAD = re.compile(r"(?m)^[\s,]*(?P<ed>Extended" + SEP + r"Data" + SEP + r")?(?P<sup>Supplementa(?:ry|l)" + SEP + r")?"
                  r"(?:Figure|Fig\.?)[\s,]*(?P<s>S)?(?P<num>\d{1,2})(?=[\s\.\|:,])"
                  r"(?![\s,]*(?:and|to|&|shows?|illustrates?)\b)")


def figure_refs(where: str) -> list[tuple[str, str, list[str]]]:
    """(kind, number, panels) for each figure a unit's `where` names; kind is F, S or ED."""
    out = []
    for m in REF.finditer(where):
        kind = "ED" if m.group("ed") else ("S" if (m.group("sup") or m.group("s")) else "F")
        p = re.sub(r"\b(?:and|to)\b", " ", m.group("p") or "", flags=re.I)
        panels = re.findall(r"(?<![A-Za-z])[A-Za-z](?![A-Za-z])", re.sub(r"S?\d+", " ", p))
        out.append((kind, m.group("num"), panels))
    return out


def label(kind: str, num: str, panels: list[str]) -> str:
    if not panels:
        p = "all panels"
    elif len(panels) == 1:
        p = f"panel {panels[0]}"
    elif len(panels) == 2:
        p = f"panels {panels[0]} to {panels[1]}"
    else:
        p = "panels " + ", ".join(panels)
    return f"{NAME[kind]}{num}, {p}"


def _panel_count(seg: str) -> int:
    return max(len(re.findall(r"\(\s*" + a + r"\s*[\),–\-]", seg)) for a in ("[A-P]", "[a-p]"))


SUPP_FILE = re.compile(r"supp|(?<![a-z])si(?![a-z])|mmc\d|esm|moesm|extended data", re.I)
MAX_FILES = 3


def is_supplement(name: str, pages: list[str]) -> bool:
    return bool(SUPP_FILE.search(name) or (pages and re.search(r"Supplementa(?:ry|l)", pages[0][:1500])))


def legend_pages(texts: dict[str, list[str]], key: tuple[str, str]) -> list[tuple[str, int]]:
    """[(file, page)]: in each file with the figure's legend, the page before the legend and the legend's page
    (1-based). A main figure's legend found in a main file is not looked for in supplements, which may number their
    own figures 1, 2, .... [] when no file, or more than MAX_FILES files, have the legend."""
    found, titled = {}, {}
    for f, pages in texts.items():
        for pi, txt in enumerate(pages):
            for m in HEAD.finditer(txt):
                kind = "ED" if m.group("ed") else ("S" if (m.group("sup") or m.group("s")) else "F")
                if (kind, m.group("num")) != key:
                    continue
                n = _panel_count(txt[m.start(): m.start() + 3000])
                if f not in found or n > found[f][1]:
                    found[f] = (pi, n)
                if n == 0:  # a heading with no legend after it: the page that holds the figure, legends batched elsewhere
                    titled.setdefault(f, pi)
    if key[0] == "F" and any(not is_supplement(f, texts[f]) for f in found):
        found = {f: v for f, v in found.items() if not is_supplement(f, texts[f])}
    if not found or len(found) > MAX_FILES:
        return []
    out = []
    for f, (pi, _) in found.items():
        ps = {p for p in (pi - 1, pi) if p >= 0}
        if f in titled:
            ps.add(titled[f])
        out += [(f, p + 1) for p in sorted(ps)]
    return out


def decide(answer, n_images: int) -> str | None:
    """The look's reason when its answer allows skipping the figure job, else None."""
    if not isinstance(answer, dict) or answer.get("points") != "no":
        return None
    page, why = answer.get("page"), answer.get("why")
    if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= n_images:
        return None
    if not isinstance(why, str) or not why.strip():
        return None
    return why.strip()


def look_argv(prompt: str, cfg: dict | None = None) -> list[str]:
    from . import agent
    return agent.look_argv(cfg or agent.load(), prompt)


def look_prompt(what: str, images: list[str]) -> str:
    listing = " ".join(f"Image {i + 1}: {im}" for i, im in enumerate(images))
    return (f"Read these image files, pages of one scientific paper. {listing}. Find {what} "
            "(the figure itself, not only its legend text). Question: does that panel plot individual data points, "
            "one marker per sample or replicate (dots or symbols on their own, over bars, or beside box plots)? "
            "Bars, curves, traces, or means with error bars only, without one marker per sample, count as no. "
            "If the panel is an image, blot or schematic with no plot, answer no. If several panels are named, "
            "answer yes if any of them plots such points. Answer with one line of JSON only: "
            '{"page": <image number that shows the panel, or 0 if none does>, '
            '"points": "yes" | "no" | "unsure", "why": "<at most 12 words>"}')


def _page_texts(paper_dir: Path) -> dict[str, list[str]]:
    exe = shutil.which("pdftotext")
    out = {}
    if exe is None:
        return out
    for p in sorted(paper_dir.glob("*.pdf")):
        r = subprocess.run([exe, "-q", str(p), "-"], capture_output=True, text=True)
        if r.returncode == 0:
            out[p.name] = r.stdout.split("\f")
    return out


def first_look(paper: str, unit: str, cfg: dict | None = None, log: bool = True) -> dict:
    """Look at one figure unit: {'skip', 'reason', 'cost_usd'}; the look is logged next to the paper's job reports."""
    from . import agent
    from .jobs import ROOT
    rec_file = RECORDS_DIR / paper / "record.yaml"
    if not rec_file.exists():
        return {"skip": False, "reason": "no look: no record", "cost_usd": 0.0}
    u = (yaml.safe_load(rec_file.read_text()).get("units") or {}).get(unit)
    refs = figure_refs((u or {}).get("where", ""))
    if len(refs) != 1:
        return {"skip": False, "reason": f"no look: unit names {len(refs)} figures", "cost_usd": 0.0}
    kind, num, panels = refs[0]
    pages = legend_pages(_page_texts(PAPERS_DIR / paper), (kind, num))
    if not pages:
        return {"skip": False, "reason": "no look: legend not found in one file", "cost_usd": 0.0}
    import pymupdf
    tmp = tempfile.mkdtemp(prefix="first_look_dont_commit_")
    try:
        images = []
        for f, pg in pages:
            png = os.path.join(tmp, f"p{len(images) + 1}.png")
            with pymupdf.open(str(PAPERS_DIR / paper / f)) as doc:
                doc[pg - 1].get_pixmap(dpi=DPI).save(png)
            images.append(png)
        cfg = cfg or agent.load()
        r = subprocess.run(look_argv(look_prompt(label(kind, num, panels), images), cfg), cwd=tmp, env=agent.env(cfg),
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    answer, cost = None, 0.0
    ev = agent.parse(r.stdout, r.stderr)
    cost = ev["cost"]
    try:
        answer = json.loads(re.search(r"\{.*\}", ev["result"], re.S).group(0))
    except (ValueError, AttributeError):
        pass
    why = decide(answer, len(images))
    if why is not None:
        f, pg = pages[answer["page"] - 1]
        out = {"skip": True, "reason": f"first look ({agent.look_model(cfg) or 'small model'}): {why} ({f} p. {pg})", "cost_usd": cost}
    else:
        out = {"skip": False, "reason": f"look: {json.dumps(answer, ensure_ascii=False)[:200]}", "cost_usd": cost}
    if not log:
        return {**out, "answer": answer, "pages": pages}
    log = ROOT / "runs" / f"{date.today().isoformat()}_jobs" / paper
    log.mkdir(parents=True, exist_ok=True)
    (log / f"look_{unit}.json").write_text(json.dumps({**out, "unit": unit, "pages": pages, "answer": answer}, indent=1,
                                                      ensure_ascii=False))
    return out


def mark_no_points(record_dir: Path, unit: str, reason: str) -> None:
    """Add `unit: reason` to the record's figures.yaml `no_points`, keeping everything else."""
    record_dir = Path(record_dir)
    record_dir.mkdir(parents=True, exist_ok=True)
    f = record_dir / "figures.yaml"
    d = (yaml.safe_load(f.read_text()) if f.exists() else None) or {}
    d.setdefault("figures", {})
    d.setdefault("no_points", {})[unit] = reason
    f.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=120))
