"""Tests for zero-dependency modular web/build.py hygiene and dual-target output."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_builder():
    spec = importlib.util.spec_from_file_location("web_build", str(ROOT / "web" / "build.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_verify_html_hygiene_blocks_cdn_and_hash_href():
    wb = _load_builder()
    wb.verify_html_hygiene("<!doctype html><html><body><button>OK</button></body></html>", "clean")
    with pytest.raises(AssertionError):
        wb.verify_html_hygiene('<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>', "cdn")
    with pytest.raises(AssertionError):
        wb.verify_html_hygiene('<a href="#atlas">Jump</a>', "hash")


def test_web_template_and_static_assets_present():
    wb = _load_builder()
    assert (ROOT / "web" / "index.template.html").is_file()
    for f in wb.CSS_FILES + wb.JS_FILES:
        assert (ROOT / "web" / f).is_file(), f"Missing web asset: web/{f}"
    # Verify template itself contains zero CDNs and zero href=# links
    tpl = (ROOT / "web" / "index.template.html").read_text(encoding="utf-8")
    wb.verify_html_hygiene(tpl, "web/index.template.html")


def test_assemble_bundle_enriches_vocab_and_formulas():
    wb = _load_builder()
    rel = ROOT / "releases" / "pilot-v1"
    if not rel.is_dir():
        pytest.skip("releases/pilot-v1 not built in this workspace")
    bundle = wb.assemble_bundle("pilot-v1")
    assert len(bundle["field_decls"]) >= 14
    assert len(bundle["terms"]) >= 170
    assert len(bundle["term_usage"]) >= 20
    assert "taxon:heliconius_sara" in bundle["term_usage"]
    assert len(bundle["term_usage"]["taxon:heliconius_sara"]["panels"]) > 0

    formulas_by_id = {f["formula"]: f for f in bundle["formulas"]}
    assert len(formulas_by_id) >= 34
    lep_formulas = [f for f in bundle["formulas"] if f.get("scope") == "lepidoptera"]
    assert len(lep_formulas) >= 7
    tf = formulas_by_id["thin_film_ridge_interference"]
    assert tf["scope"] == "lepidoptera"
    assert tf["equations"] == ["lam = 2*(n_r - n_a)*h/m"]
    assert "h" in tf["variables"] and len(tf["tests"]) >= 2
    assert any(d.get("library_formula") == "thin_film_ridge_interference" for d in bundle["derivations"])

