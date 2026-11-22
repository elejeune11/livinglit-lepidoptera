"""The agent command line, read from configuration (07-building, Jobs).

LivingLit's jobs are headless runs of an LLM coding agent: it reads a brief, writes files, runs its gate as a tool and
ends with a report. Which agent runs, and how its command line is spelled, is configuration: `agent.yaml` at the repo
root (or the file named by LIVINGLIT_AGENT). `agent.example.yaml` documents the keys. The agent must print, as the
last line of its output, one JSON object with `result` (the report), and may add `session_id` (to resume it with the
gate's output), `total_cost_usd` and `num_turns`.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml

from . import ROOT


def path() -> Path:
    return Path(os.environ.get("LIVINGLIT_AGENT") or ROOT / "agent.yaml")


def load() -> dict:
    f = path()
    if not f.exists():
        raise FileNotFoundError(f"no agent config at {f}: copy agent.example.yaml to agent.yaml and fill it in")
    return yaml.safe_load(f.read_text(encoding="utf-8")) or {}


def _fill(args, **kw) -> list[str]:
    return [a.format(**kw) for a in args or []]


def job_argv(cfg: dict, prompt: str, brief: str, session: str | None, denied: list[str]) -> list[str]:
    j = cfg["job"]
    a = [cfg["command"], *_fill(j["args"], prompt=prompt)]
    a += _fill(j["resume"], session=session) if session else _fill(j["new"], brief=brief)
    a += list(j.get("deny") or []) + [j["deny_read"].format(path=p) for p in denied if j.get("deny_read")]
    return a


def look_argv(cfg: dict, prompt: str) -> list[str]:
    lk = cfg["look"]
    return [cfg["command"], *_fill(lk["args"], prompt=prompt, model=lk.get("model", ""))]


def look_model(cfg: dict) -> str:
    return cfg.get("look", {}).get("model", "")


def env(cfg: dict, base: dict | None = None) -> dict:
    drop = set(cfg.get("clear_env") or [])
    return {k: v for k, v in (os.environ if base is None else base).items() if k not in drop}


def parse(stdout: str, stderr: str) -> dict:
    """The agent's final JSON line, or an error carrying stderr's tail."""
    ev = None
    for line in reversed(stdout.strip().splitlines()):
        try:
            ev = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    if not isinstance(ev, dict):
        return {"result": stderr[-2000:], "session": None, "cost": 0.0, "turns": 0, "error": True}
    return {"result": str(ev.get("result") or ""), "session": ev.get("session_id"),
            "cost": float(ev.get("total_cost_usd") or 0), "turns": int(ev.get("num_turns") or 0),
            "error": bool(ev.get("is_error"))}


def usage_limited(cfg: dict, text: str) -> bool:
    pat = cfg.get("usage_limit")
    return bool(pat and re.search(pat, text, re.I))
