"""Reviewing agent reports: the failure patterns a rule can decide (07-building, Reviewing agent reports).

- ids are never silently removed: a re-read keeps every id of the committed record
  unless it lists the id under `removed` with a reason (blocking);
- one stated wording in two fields of one context is listed for review, since no
  field is filled from another field's text (not blocking: it can be right).
The other patterns (a value computed rather than read, one of two conflicting
values chosen, a group's kind set to avoid inheriting context, a flag for what code
matches) are examples in the agents' briefs.
"""
from __future__ import annotations

import subprocess

import yaml

from . import RECORDS_DIR
from .models import ContextObj, Record, stated_text

NOT_WORDING = {"not stated", "not applicable", "none", "not stated in this source"}


def _ids(raw: dict) -> set[str]:
    out = set()
    for uid, u in (raw.get("units") or {}).items():
        out.add(f"units.{uid}")
        out |= {f"units.{uid}.groups.{g}" for g in (u.get("groups") or {})}
    out |= {f"evidence.{i}" for i in (raw.get("evidence") or {})}
    out |= {f"claims.{c}" for c in (raw.get("claims") or {})}
    return out


def removed_ids(before: dict, after: dict) -> list[str]:
    declared = {r["id"] for r in (after.get("removed") or [])}
    return sorted(i for i in _ids(before) - _ids(after) if i not in declared)


def copied_wording(rec: Record) -> list[str]:
    out = []
    places = [(f"units.{u}", U.context) for u, U in rec.units.items()] + \
             [(f"units.{u}.groups.{g}", G.context) for u, U in rec.units.items() for g, G in U.groups.items()]
    for at, ctx in places:
        by_text = {}
        for f, v in ctx.items():
            t = stated_text(v)
            if t and t not in NOT_WORDING:
                by_text.setdefault(t, []).append(f)
        for t, fs in by_text.items():
            if len(fs) > 1:
                out.append(f"{at}: {t!r} in {' and '.join(sorted(fs))}")
    return out


def committed_record(paper: str) -> dict | None:
    try:
        txt = subprocess.run(["git", "show", f"HEAD:records/{paper}/record.yaml"], capture_output=True, text=True,
                             cwd=RECORDS_DIR.parent, check=True).stdout
    except subprocess.CalledProcessError:
        return None
    return yaml.safe_load(txt)


def review(paper: str) -> dict:
    """{'blocking': [...], 'for_review': [...]} for a record as it stands against the committed one."""
    raw = yaml.safe_load((RECORDS_DIR / paper / "record.yaml").read_text())
    before = committed_record(paper)
    blocking = [f"{i}: removed without a `removed` entry" for i in removed_ids(before, raw)] if before else []
    return {"blocking": blocking, "for_review": copied_wording(Record.model_validate(raw))}
