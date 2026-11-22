"""The field survey and promotion at checkpoints (03-vocabulary, Fields are designed from the corpus).

A survey job reads one paper's methods and legends and lists every stated
condition with a quote, tagged with an existing field or 'no field'. A merge job
names each untagged condition (the one judgement: which wordings are the same
condition). Code counts and the rule decides: varied between groups in 3 or more of
the surveyed papers, or stated in at least a third of them -> a field; otherwise ->
other_conditions. At each later checkpoint a
condition in other_conditions becomes a field once stated in at least 5 % of the
papers read and at least 3.
"""
from __future__ import annotations

import math
from pathlib import Path

from pydantic import ValidationError

from .gate_record import check_anchor, holds
from .models import Anchor, Strict

NO_FIELD = "no field"
SURVEY_MIN_VARIED = 3   # papers that vary the condition between groups
SURVEY_STATED_SHARE = 1 / 3  # or papers that state it at all
PROMOTE_SHARE = 0.05
PROMOTE_MIN_PAPERS = 3


class SurveyCondition(Strict):
    text: str
    field: str
    varied: bool  # this paper varies the condition between its groups
    anchor: Anchor


class SurveyFile(Strict):
    paper: str
    conditions: list[SurveyCondition]


def check_survey(raw: dict, paper_dir: Path, field_cfg: dict, check_text: bool = True) -> list[str]:
    try:
        s = SurveyFile.model_validate(raw)
    except ValidationError as e:
        return [f"schema: {err['loc']}: {err['msg']}" for err in e.errors()]
    probs = []
    fields = set(field_cfg["fields"])
    for i, c in enumerate(s.conditions):
        if c.field != NO_FIELD and c.field not in fields:
            probs.append(f"conditions[{i}]: {c.field!r} is neither a field nor {NO_FIELD!r}")
        if not holds(c.anchor.quote, c.text):
            probs.append(f"conditions[{i}] ({c.text!r}): the quote does not hold the condition's words")
        if check_text:
            p = check_anchor(c.anchor, paper_dir, None)
            if p:
                probs.append(f"conditions[{i}]: {p}")
    return probs


def tally(surveys: dict[str, dict], names: dict[str, dict]) -> list[dict]:
    """surveys: paper -> survey; names: paper -> {index of an untagged condition: its merged name}."""
    stated: dict[str, set] = {}
    varied: dict[str, set] = {}
    for paper, raw in surveys.items():
        s = SurveyFile.model_validate(raw)
        for i, c in enumerate(s.conditions):
            if c.field != NO_FIELD:
                continue
            name = (names.get(paper) or {}).get(i)
            if not name:
                raise ValueError(f"{paper} conditions[{i}] ({c.text!r}) has no name from the merge job")
            stated.setdefault(name, set()).add(paper)
            if c.varied:
                varied.setdefault(name, set()).add(paper)
    need_stated = math.ceil(SURVEY_STATED_SHARE * len(surveys))
    rows = []
    for n, ps in stated.items():
        v = len(varied.get(n, ()))
        rows.append({"condition": n, "papers": len(ps), "varied_in": v,
                     "decision": "field" if v >= SURVEY_MIN_VARIED or len(ps) >= need_stated else "other_conditions",
                     "sources": sorted(ps)})
    return sorted(rows, key=lambda r: (r["decision"] != "field", -r["varied_in"], -r["papers"], r["condition"]))


def promote(counts: dict[str, int], papers_read: int) -> list[str]:
    """Conditions in other_conditions that become fields at this checkpoint."""
    need = max(PROMOTE_MIN_PAPERS, math.ceil(PROMOTE_SHARE * papers_read))
    return sorted(n for n, k in counts.items() if k >= need)


def untagged(surveys: dict[str, dict]) -> dict[str, dict[int, str]]:
    """paper -> {index: text} of every condition tagged 'no field': the merge job's whole input."""
    out = {}
    for paper, raw in sorted(surveys.items()):
        s = SurveyFile.model_validate(raw)
        ix = {i: c.text for i, c in enumerate(s.conditions) if c.field == NO_FIELD}
        if ix:
            out[paper] = ix
    return out
