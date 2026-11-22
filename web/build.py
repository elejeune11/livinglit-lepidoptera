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
    "js/views/atlas.js",
    "js/views/vault.js",
    "js/views/scale_comparator.js",
    "js/views/compare.js",
    "js/views/audit.js",
    "js/views/graph.js",
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


def _build_thumbs(
    panels: list[dict[str, Any]],
    manifests: dict[str, dict[str, Any]],
    papers_dir: Path,
    cache_path: Path,
    max_side: int = 760,
    jpeg_q: int = 80,
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
        h, w = crop.shape[:2]
        scale = min(1.0, max_side / max(h, w))
        if scale < 1.0:
            crop = cv2.resize(crop, (max(1, int(round(w * scale))), max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_q])
        if ok:
            b64 = "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")
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
    derivations = _read_csv(rel / "derivations.csv")
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
        term_labels[r["id"]] = r["label"]
        terms.append(r)
    formulas = _read_csv(rel / "formulas.csv")

    manifests = hub.get("manifests") or {}
    thumbs = _build_thumbs(panels, manifests, papers_dir, rel / "thumbs_cache.json")

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
        "terms": terms,
        "term_labels": term_labels,
        "formulas": formulas,
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
