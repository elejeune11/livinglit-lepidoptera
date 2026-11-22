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
    assert len(bundle["papers"]) == 10
    assert len(bundle["panels"]) >= 590
    assert len(bundle["field_decls"]) >= 17
    assert len(bundle["terms"]) >= 260
    assert len(bundle["term_usage"]) >= 60
    assert "taxon:heliconius_sara" in bundle["term_usage"]
    assert len(bundle["term_usage"]["taxon:heliconius_sara"]["panels"]) > 0
    assert "taxon:agrotis_infusa" in bundle["term_usage"]

    terms_by_id = {t["id"]: t for t in bundle["terms"]}
    assert "FlyBase:FBgn0004870" in (terms_by_id["target_gene:bric_a_brac"].get("xref") or [])
    assert "taxon:agrotis_infusa" in terms_by_id

    formulas_by_id = {f["formula"]: f for f in bundle["formulas"]}
    assert len(formulas_by_id) >= 40
    lep_formulas = [f for f in bundle["formulas"] if f.get("scope") == "lepidoptera"]
    assert len(lep_formulas) >= 13
    tf = formulas_by_id["thin_film_ridge_interference"]
    assert tf["scope"] == "lepidoptera"
    assert tf["equations"] == ["lam = 2*(n_r - n_a)*h/m"]
    assert "h" in tf["variables"] and len(tf["tests"]) >= 2
    assert any(d.get("library_formula") == "thin_film_ridge_interference" for d in bundle["derivations"])
    assert "fold_change_from_log2fc" in formulas_by_id
    assert any(d.get("library_formula") == "fold_change_from_log2fc" for d in bundle["derivations"])

    assert len(bundle["genetic_relations"]) >= 33
    ivory_papers = {
        r["paper"] for r in bundle["genetic_relations"]
        if r["source"] == "target_gene:ivory_lncrna" or r["target"] == "target_gene:ivory_lncrna"
    }
    assert {"2024_Livraghi", "2025_Loh"}.issubset(ivory_papers)

    tables_by_id = {t["id"]: t for t in bundle["genomic_tables"]}
    assert len(tables_by_id) >= 3
    assert "bab_uvi_de_targets" in tables_by_id
    assert tables_by_id["bab_uvi_de_targets"]["n_rows"] == 87
    assert "fourier_interridge_170" in tables_by_id
    assert tables_by_id["fourier_interridge_170"]["n_rows"] == 170
    assert "seah_fig4s5_source_data1" in tables_by_id
    assert tables_by_id["seah_fig4s5_source_data1"]["n_rows"] == 270


