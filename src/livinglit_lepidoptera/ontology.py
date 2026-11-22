"""Pinned ontology releases: index, lookup and id checks (03-vocabulary, Adopted ontologies; 08 decision 18).

Each file is parsed once into an index under ontologies_dont_commit/_index/
(never into git). Agents look terms up here; no web lookups.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from . import ONTOLOGY_DIR
from .text import normalize

FILES = {"chebi": "chebi_core.obo.gz", "cl": "cl-basic.obo", "mondo": "mondo.obo", "uo": "uo.obo",
         "cellosaurus": "cellosaurus.txt", "ncbitaxon": "taxslim.obo", "flybase": "flybase_orthologs.obo"}
PREFIX = {"CHEBI": "chebi", "CL": "cl", "MONDO": "mondo", "UO": "uo", "CVCL": "cellosaurus",
          "NCBITaxon": "ncbitaxon", "FBgn": "flybase"}
KEEP = {"ncbitaxon": "NCBITaxon", "flybase": "FBgn"}  # the id prefix kept from a file, when it is not the name in upper case


def _open(p: Path):
    return gzip.open(p, "rt", encoding="utf-8", errors="replace") if p.suffix == ".gz" else open(p, encoding="utf-8", errors="replace")


def parse_obo(path: Path, keep_prefix: str) -> tuple[dict, str]:
    terms, cur, version = {}, None, ""
    syn = re.compile(r'^synonym: "(.*)" (EXACT|RELATED|NARROW|BROAD)')
    with _open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("data-version:") and not version:
                version = line.split(":", 1)[1].strip()
            if line == "[Term]":
                cur = {"id": None, "label": "", "synonyms": [], "parents": [], "obsolete": False}
                continue
            if line.startswith("[") and line.endswith("]"):
                cur = None
                continue
            if cur is None or not line:
                if cur is not None and cur["id"] and cur["id"].startswith(keep_prefix + ":"):
                    terms[cur["id"]] = cur
                    cur = None
                continue
            k, _, v = line.partition(": ")
            if k == "id":
                cur["id"] = v.strip()
            elif k == "name":
                cur["label"] = v.strip()
            elif k == "synonym":
                m = syn.match(line)
                if m and m.group(2) in ("EXACT", "RELATED"):
                    cur["synonyms"].append(m.group(1))
            elif k == "is_a":
                cur["parents"].append(v.split("!")[0].strip().split(" ")[0])
            elif k == "is_obsolete" and v.strip() == "true":
                cur["obsolete"] = True
    if cur is not None and cur.get("id", "") and cur["id"].startswith(keep_prefix + ":"):
        terms[cur["id"]] = cur
    return terms, version


def parse_cellosaurus(path: Path) -> tuple[dict, str]:
    terms, cur, version = {}, None, ""
    with _open(path) as f:
        for line in f:
            if not version and line.startswith(" Version:"):
                version = line.split(":", 1)[1].strip()
            if line.startswith("ID   "):
                cur = {"label": line[5:].strip(), "synonyms": [], "parents": [], "obsolete": False, "species": ""}
            elif line.startswith("AC   ") and cur is not None:
                cur["id"] = line[5:].strip()
            elif line.startswith("SY   ") and cur is not None:
                cur["synonyms"] += [s.strip() for s in line[5:].split(";") if s.strip()]
            elif line.startswith("OX   ") and cur is not None:
                cur["species"] += line[5:].strip()
            elif line.startswith("CA   ") and cur is not None:
                cur["category"] = line[5:].strip()
            elif line.startswith("HI   ") and cur is not None:
                cur["parents"].append(line[5:].split("!")[0].strip())
            elif line.startswith("//") and cur is not None:
                if cur.get("id") and ("Homo sapiens" in cur["species"]):
                    terms[cur["id"]] = cur
                cur = None
    return terms, version


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_index(name: str, odir: Path = ONTOLOGY_DIR) -> dict:
    src = odir / FILES[name]
    terms, version = parse_cellosaurus(src) if name == "cellosaurus" else parse_obo(src, KEEP.get(name, name.upper()))
    idx = {"name": name, "file": FILES[name], "version": version, "sha256": sha256(src), "terms": terms}
    out = odir / "_index"
    out.mkdir(exist_ok=True)
    (out / f"{name}.json").write_text(json.dumps(idx))
    return idx


@lru_cache(maxsize=8)
def load_index(name: str, odir: Path = ONTOLOGY_DIR) -> dict:
    p = odir / "_index" / f"{name}.json"
    if not p.exists():
        return build_index(name, odir)
    return json.loads(p.read_text())


class Ontologies:
    """check(id) → {label, obsolete} or None; search(text) → candidates; ancestors(id) → set."""

    def __init__(self, odir: Path = ONTOLOGY_DIR):
        self.odir = odir

    def _idx(self, oid: str):
        pre = oid.split(":")[0] if ":" in oid else oid.split("_")[0]
        name = PREFIX.get(pre)
        return load_index(name, self.odir) if name else None

    def check(self, oid: str):
        idx = self._idx(oid)
        if idx is None:
            return None
        t = idx["terms"].get(oid)
        if t is None:
            return None
        return {"label": t["label"], "obsolete": t["obsolete"], "ontology": idx["name"], "release": idx["version"]}

    def ancestors(self, oid: str) -> set[str]:
        idx = self._idx(oid)
        if idx is None or oid not in idx["terms"]:
            return set()
        out, stack = set(), list(idx["terms"][oid]["parents"])
        while stack:
            p = stack.pop()
            if p in out:
                continue
            out.add(p)
            stack += idx["terms"].get(p, {}).get("parents", [])
        return out

    def search(self, ontology: str, text: str, limit: int = 15) -> list[dict]:
        idx = load_index(ontology, self.odir)
        q = normalize(text)
        exact, part = [], []
        for oid, t in idx["terms"].items():
            if t["obsolete"]:
                continue
            names = [t["label"]] + t["synonyms"]
            keys = [normalize(n) for n in names]
            if q in keys:
                exact.append(oid)
            elif any(q in k for k in keys):
                part.append(oid)
            if len(exact) >= limit:
                break
        out = []
        for oid in (exact + sorted(part, key=lambda o: len(idx["terms"][o]["label"])))[:limit]:
            t = idx["terms"][oid]
            out.append({"id": oid, "label": t["label"], "synonyms": t["synonyms"][:6],
                        "exact": oid in exact})
        return out


def write_pins(path: Path, odir: Path = ONTOLOGY_DIR) -> dict:
    import yaml
    pins = {}
    for name in FILES:
        idx = load_index(name, odir)
        pins[name] = {"file": idx["file"], "release": idx["version"], "sha256": idx["sha256"],
                      "terms": len(idx["terms"])}
    path.write_text("# Pinned ontology releases (08 decision 18). The files stay out of git, in ontologies_dont_commit/.\n"
                    + yaml.safe_dump(pins, sort_keys=False))
    return pins
