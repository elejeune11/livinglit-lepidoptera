"""Dual-target zero-dependency build compiler for LivingLit · Lepidoptera (`web/build.py`).

Compiles `web/` + `releases/<tag>/` into BOTH:
  1. Multi-file static site (`docs/site/`) — ideal for GitHub Pages caching
  2. Portable self-contained single-file HTML (`releases/<tag>/overview.html`) — offline & artifact-ready

Enforces strict hygiene assertions:
  - Zero external CDN links (`cdn.jsdelivr.net`, `unpkg.com`, `fonts.googleapis.com`, etc.)
  - Zero internal `href="#..."` links
  - Embeds figure thumbnails ONLY for papers with `oa_status == "open_access"` and `figure_embed_policy == "public_thumbnails"`.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import re
import shutil
from pathlib import Path
from typing import Any

import cv2

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"

CSS_FILES = [
    "styles/tokens.css",
    "styles/components.css",
]

JS_FILES = [
    "js/state.js",
    "js/overlays.js",
    "js/charts.js",
    "js/views/drawer.js",
    "js/views/overview.js",
    "js/views/atlas.js",
    "js/views/vault.js",
    "js/views/scale_comparator.js",
    "js/views/figures.js",
    "js/views/compare.js",
    "js/views/audit.js",
    "js/views/graph.js",
    "js/views/vocab_formulas.js",
    "js/views/papers_schema.js",
    "js/main.js",
]

FORBIDDEN_CDNS = (
    "cdn.jsdelivr.net",
    "unpkg.com",
    "cdnjs.cloudflare.com",
    "fonts.googleapis.com",
    "esm.sh",
    "tailwindcss.com",
)


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    csv.field_size_limit(10**9)
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _jparse(s: str | None, default: Any = None) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def _load_schema_metadata() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Load rich field declarations and formula library details directly from fields/."""
    import sys

    src_dir = str(ROOT / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from livinglit_lepidoptera import DEFAULT_FIELD, FIELDS_DIR
    from livinglit_lepidoptera.formulas import load_library, load_log as load_formula_log
    from livinglit_lepidoptera.vocab import load_fields

    field_decls: list[dict[str, Any]] = []
    for name, decl in load_fields().items():
        field_decls.append({
            "name": name,
            "kind": decl.kind,
            "ontology": decl.ontology,
            "set": bool(decl.set),
            "scope": decl.scope,
            "states": list(decl.states or []),
        })

    lib = load_library()
    provenance: dict[str, dict[str, Any]] = {}
    for scope_name, fdir in (("shared", FIELDS_DIR / "_shared" / "formulas"), ("lepidoptera", FIELDS_DIR / DEFAULT_FIELD / "formulas")):
        for ver in load_formula_log(fdir):
            for ev in ver.get("events", []):
                if ev.get("event") == "add":
                    fname = ev["entry"]["formula"]
                    provenance[fname] = {
                        "scope": scope_name,
                        "added_version": ver.get("version"),
                        "added_paper": ver.get("paper") or scope_name,
                    }

    used_by_map: dict[str, list[str]] = {}
    for fname, entry in lib.entries.items():
        for u in entry.uses or []:
            used_by_map.setdefault(u.formula, [])
            if fname not in used_by_map[u.formula]:
                used_by_map[u.formula].append(fname)

    formula_meta: dict[str, dict[str, Any]] = {}
    for fname, entry in lib.entries.items():
        prov = provenance.get(fname, {"scope": "shared", "added_version": None, "added_paper": None})
        cites_obj = None
        if entry.cites:
            cites_obj = {
                "text": entry.cites.text,
                "url": entry.cites.url,
                "quote": entry.cites.quote,
                "anchor": entry.cites.anchor,
            }
        formula_meta[fname] = {
            "scope": prov["scope"],
            "added_version": prov["added_version"],
            "added_paper": prov["added_paper"],
            "equations": list(entry.equations or []),
            "variables": dict(entry.variables or {}),
            "assumes": list(entry.assumes or []),
            "holds_under": list(lib.holds_under(fname) or []),
            "uses": [{"formula": u.formula, "subs": dict(u.subs or {})} for u in (entry.uses or [])],
            "used_by": used_by_map.get(fname, []),
            "does_not_apply": entry.does_not_apply or "",
            "tests": [{"given": dict(t.given or {}), "expect": dict(t.expect or {})} for t in (entry.tests or [])],
            "cites": cites_obj,
        }
    return field_decls, formula_meta


def _build_term_usage(
    terms: list[dict[str, Any]],
    mappings_rows: list[dict[str, Any]],
    items: list[dict[str, Any]],
    panels: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Aggregate live corpus usage (papers, author phrasings, items, panels) for every vocabulary term."""
    usage: dict[str, dict[str, Any]] = {}

    def _slot(tid: str) -> dict[str, Any]:
        if tid not in usage:
            usage[tid] = {"papers": [], "items": [], "panels": [], "stated_examples": []}
        return usage[tid]

    # 1. Canonical term mappings from mappings.csv
    for m in mappings_rows:
        paper = m.get("paper", "")
        tids = _jparse(m.get("terms"), [])
        for tid in tids:
            s = _slot(tid)
            if paper and paper not in s["papers"]:
                s["papers"].append(paper)
            ex = {
                "paper": paper,
                "at": m.get("at", ""),
                "stated": m.get("stated", ""),
                "origin": m.get("origin", ""),
            }
            if len(s["stated_examples"]) < 12 and ex not in s["stated_examples"]:
                s["stated_examples"].append(ex)

    # 2. Item measure_terms
    for it in items:
        ikey = f"{it.get('paper', '')}/{it.get('item', '')}"
        paper = it.get("paper", "")
        for tid in it.get("measure_terms") or []:
            s = _slot(tid)
            if paper and paper not in s["papers"]:
                s["papers"].append(paper)
            if ikey not in s["items"]:
                s["items"].append(ikey)

    # 3. Link items via item-level context/unit mappings + match panels via context labels/synonyms & linked_items
    label_to_tids: dict[str, list[str]] = {}
    for t in terms:
        tid = t["id"]
        cands = [t.get("label", ""), tid.split(":", 1)[-1].replace("_", " ")] + list(t.get("synonyms") or [])
        for c in cands:
            norm = re.sub(r"\s+", " ", str(c or "").strip().lower())
            if len(norm) >= 2:
                label_to_tids.setdefault(norm, [])
                if tid not in label_to_tids[norm]:
                    label_to_tids[norm].append(tid)

    # Map panel.context values -> matching terms
    for p in panels:
        pid = p.get("id", "")
        paper = p.get("paper", "")
        ctx = p.get("context") or {}
        matched_tids: set[str] = set()
        for val in ctx.values():
            if not val:
                continue
            vals = val if isinstance(val, list) else [val]
            for v in vals:
                sv = re.sub(r"\s+", " ", str(v).strip().lower())
                if sv in label_to_tids:
                    matched_tids.update(label_to_tids[sv])
                else:
                    # Also check clean phrase boundary matches for composite strings like "Papilionoidea (34 species)"
                    head = sv.split("(", 1)[0].strip()
                    if head in label_to_tids:
                        matched_tids.update(label_to_tids[head])
        # Also inherit measure_terms from linked items
        for it_name in p.get("linked_items") or []:
            ikey = f"{paper}/{it_name}"
            for it in items:
                if f"{it.get('paper', '')}/{it.get('item', '')}" == ikey:
                    matched_tids.update(it.get("measure_terms") or [])
        for tid in matched_tids:
            s = _slot(tid)
            if paper and paper not in s["papers"]:
                s["papers"].append(paper)
            if pid and pid not in s["panels"]:
                s["panels"].append(pid)

    return usage


def _build_thumbs(
    panels: list[dict[str, Any]],
    manifests: dict[str, dict[str, Any]],
    papers_dir: Path,
    cache_path: Path,
    max_side: int = 480,
    max_side_hi: int = 640,
    webp_q: int = 72,
) -> dict[str, str]:
    cache: dict[str, str] = {}
    if cache_path.is_file():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    img_cache: dict[Path, Any] = {}
    thumbs: dict[str, str] = {}
    dirty = False

    for p in panels:
        pid = p["id"]
        paper = p["paper"]
        mf = manifests.get(paper) or {}
        if mf.get("oa_status", "open_access") != "open_access" or mf.get("figure_embed_policy", "public_thumbnails") != "public_thumbnails":
            continue
        if pid in cache:
            thumbs[pid] = cache[pid]
            continue
        img_p = papers_dir / paper / p["file"]
        if not img_p.is_file():
            continue
        if img_p not in img_cache:
            img_cache[img_p] = cv2.imread(str(img_p), cv2.IMREAD_COLOR)
        im = img_cache[img_p]
        if im is None:
            continue
        x0, y0, x1, y1 = p["bbox"]
        crop = im[y0:y1, x0:x1]
        if crop.size == 0:
            continue
        d = p.get("data") or {}
        is_hi = (
            any(d.get(k) for k in ("curves", "digitized_scatter", "digitized_boxplots", "dotplot_matrix"))
            or d.get("periodic_fft_um") is not None
        )
        limit = max_side_hi if is_hi else max_side
        h, w = crop.shape[:2]
        scale = min(1.0, limit / max(h, w))
        if scale < 1.0:
            crop = cv2.resize(crop, (max(1, int(round(w * scale))), max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".webp", crop, [int(cv2.IMWRITE_WEBP_QUALITY), webp_q])
        if ok:
            b64 = "data:image/webp;base64," + base64.b64encode(buf.tobytes()).decode("ascii")
            thumbs[pid] = b64
            cache[pid] = b64
            dirty = True

    if dirty:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache), encoding="utf-8")
    return thumbs


def assemble_bundle(tag: str, releases_dir: Path = ROOT / "releases", papers_dir: Path = ROOT / "papers_dont_ever_commit") -> dict[str, Any]:
    rel = releases_dir / tag
    if not rel.is_dir():
        raise FileNotFoundError(f"Release directory not found: {rel} (run livinglit-lep release {tag} && harvest --build-hub {tag})")

    hub = json.loads((rel / "data_hub.json").read_text(encoding="utf-8")) if (rel / "data_hub.json").is_file() else {}
    panels = json.loads((rel / "panels_all.json").read_text(encoding="utf-8")) if (rel / "panels_all.json").is_file() else []

    papers = _read_csv(rel / "papers.csv")
    items = []
    for r in _read_csv(rel / "items.csv"):
        r["measure_terms"] = _jparse(r.get("measure_terms"), [])
        items.append(r)
    values = _read_csv(rel / "values.csv")
    comparisons = []
    for r in _read_csv(rel / "comparisons.csv"):
        r["context_diff"] = _jparse(r.get("context_diff"), {"matched": [], "differing": {}, "confounders": []})
        comparisons.append(r)
    claims = []
    for r in _read_csv(rel / "claims.csv"):
        r["rests_on"] = _jparse(r.get("rests_on"), [])
        r["judgement"] = _jparse(r.get("judgement"), {})
        claims.append(r)
    derivations = []
    for r in _read_csv(rel / "derivations.csv"):
        r["inputs"] = _jparse(r.get("inputs"), {})
        r["rebuilt"] = _jparse(r.get("rebuilt"), {})
        r["notes"] = _jparse(r.get("notes"), [])
        r["parameter_kinds"] = _jparse(r.get("parameter_kinds"), {})
        derivations.append(r)
    checks = _read_csv(rel / "checks.csv")
    findings = _read_csv(rel / "findings.csv")
    missing_supplements = []
    for r in _read_csv(rel / "missing_supplements.csv"):
        r["missing"] = _jparse(r.get("missing"), [])
        missing_supplements.append(r)
    terms = []
    term_labels: dict[str, str] = {}
    for r in _read_csv(rel / "terms.csv"):
        r["fields"] = _jparse(r.get("fields"), [])
        r["synonyms"] = _jparse(r.get("synonyms"), [])
        r["xref"] = _jparse(r.get("xref"), [])
        term_labels[r["id"]] = r["label"]
        terms.append(r)

    field_decls, formula_meta = _load_schema_metadata()
    eq_to_formula: dict[str, str] = {}
    for fname, meta in formula_meta.items():
        for eq in meta.get("equations") or []:
            eq_to_formula[re.sub(r"\s+", "", eq)] = fname
    for d in derivations:
        lib_col = d.get("library", "")
        if lib_col in formula_meta:
            d["library_formula"] = lib_col
        else:
            norm_eq = re.sub(r"\s+", "", d.get("formula", ""))
            d["library_formula"] = eq_to_formula.get(norm_eq, "")
    formulas = []
    for r in _read_csv(rel / "formulas.csv"):
        r["equations"] = _jparse(r.get("equations"), [])
        r["holds_under"] = _jparse(r.get("holds_under"), [])
        r["derivations"] = int(r["derivations"]) if str(r.get("derivations", "")).isdigit() else 0
        r["papers_using"] = int(r["papers_using"]) if str(r.get("papers_using", "")).isdigit() else 0
        r["papers_in_conflict"] = int(r["papers_in_conflict"]) if str(r.get("papers_in_conflict", "")).isdigit() else 0
        r["suspect"] = str(r.get("suspect", "")).lower() == "true"
        meta = formula_meta.get(r["formula"], {})
        r.update({
            "scope": meta.get("scope", "shared"),
            "added_version": meta.get("added_version"),
            "added_paper": meta.get("added_paper"),
            "variables": meta.get("variables", {}),
            "assumes": meta.get("assumes", []),
            "uses": meta.get("uses", []),
            "used_by": meta.get("used_by", []),
            "does_not_apply": meta.get("does_not_apply", ""),
            "tests": meta.get("tests", []),
            "cites": meta.get("cites"),
        })
        if meta.get("equations"):
            r["equations"] = meta["equations"]
        if meta.get("holds_under"):
            r["holds_under"] = meta["holds_under"]
        formulas.append(r)

    mappings_rows = _read_csv(rel / "mappings.csv")
    term_usage = _build_term_usage(terms, mappings_rows, items, panels)

    manifests = hub.get("manifests") or {}
    thumbs = _build_thumbs(panels, manifests, papers_dir, rel / "thumbs_cache_webp.json")

    return {
        "tag": tag,
        "summary": hub.get("summary") or {},
        "papers": papers,
        "items": items,
        "values": values,
        "comparisons": comparisons,
        "claims": claims,
        "derivations": derivations,
        "checks": checks,
        "findings": findings,
        "missing_supplements": missing_supplements,
        "field_decls": field_decls,
        "terms": terms,
        "term_labels": term_labels,
        "term_usage": term_usage,
        "formulas": formulas,
        "genetic_relations": hub.get("genetic_relations") or [],
        "genomic_tables": hub.get("genomic_tables") or [],
        "panels": panels,
        "manifests": manifests,
        "qa_reports": hub.get("qa_reports") or {},
        "code_registry": hub.get("code_registry") or [],
        "extractor_scripts": hub.get("extractor_scripts") or {},
        "thumbs": thumbs,
    }


def verify_html_hygiene(html_text: str, label: str) -> None:
    low = html_text.lower()
    for cdn in FORBIDDEN_CDNS:
        if cdn in low:
            raise AssertionError(f"{label}: forbidden external CDN reference found: {cdn}")
    if re.search(r'href\s*=\s*["\']#', html_text, flags=re.I):
        raise AssertionError(f"{label}: forbidden internal href='#...' link found")


def build_all(tag: str = "pilot-v1", site_dir: Path = ROOT / "docs" / "site", releases_dir: Path = ROOT / "releases") -> tuple[Path, Path]:
    bundle = assemble_bundle(tag, releases_dir=releases_dir)
    template = (WEB_DIR / "index.template.html").read_text(encoding="utf-8")

    # 1. Multi-file static site (docs/site/)
    if site_dir.exists():
        shutil.rmtree(site_dir)
    (site_dir / "styles").mkdir(parents=True, exist_ok=True)
    (site_dir / "js" / "views").mkdir(parents=True, exist_ok=True)
    (site_dir / "data").mkdir(parents=True, exist_ok=True)

    for rel_css in CSS_FILES:
        shutil.copy2(WEB_DIR / rel_css, site_dir / rel_css)
    for rel_js in JS_FILES:
        shutil.copy2(WEB_DIR / rel_js, site_dir / rel_js)
    (site_dir / "data" / "bundle.json").write_text(json.dumps(bundle, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    css_links = "\n  ".join(f'<link rel="stylesheet" href="{c}" />' for c in CSS_FILES)
    js_tags = "\n  ".join(f'<script src="{j}"></script>' for j in JS_FILES)
    site_html = (
        template.replace("<!--STYLES-->", css_links)
        .replace("<!--DATA_SCRIPT-->", "")
        .replace("<!--APP_SCRIPTS-->", js_tags)
    )
    verify_html_hygiene(site_html, "docs/site/index.html")
    site_index = site_dir / "index.html"
    site_index.write_text(site_html, encoding="utf-8")

    # 2. Single-file self-contained portable artifact (releases/<tag>/overview.html)
    css_inline = "<style>\n" + "\n".join((WEB_DIR / c).read_text(encoding="utf-8") for c in CSS_FILES) + "\n</style>"
    js_inline = "<script>\n" + "\n".join((WEB_DIR / j).read_text(encoding="utf-8") for j in JS_FILES) + "\n</script>"
    safe_json = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    data_inline = f"<script>window.__LL_DATA__ = {safe_json};</script>"
    single_html = (
        template.replace("<!--STYLES-->", css_inline)
        .replace("<!--DATA_SCRIPT-->", data_inline)
        .replace("<!--APP_SCRIPTS-->", js_inline)
    )
    verify_html_hygiene(single_html, f"releases/{tag}/overview.html")
    out_single = releases_dir / tag / "overview.html"
    out_single.write_text(single_html, encoding="utf-8")
    return site_index, out_single


def main() -> None:
    ap = argparse.ArgumentParser(description="Build LivingLit · Lepidoptera modular static site & single-file HTML.")
    ap.add_argument("--tag", default="pilot-v1", help="Release tag under releases/<tag>/")
    args = ap.parse_args()
    site_index, out_single = build_all(args.tag)
    print(f"Built multi-file site:  {site_index} ({site_index.stat().st_size:,} B + bundle.json {(site_index.parent / 'data' / 'bundle.json').stat().st_size:,} B)")
    print(f"Built single-file HTML: {out_single} ({out_single.stat().st_size:,} B)")


if __name__ == "__main__":
    main()
