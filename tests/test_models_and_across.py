"""Unit tests for Manifest OA policy, atomic 1-letter panel guard, Shift #2 relaxed context_diff, and pilot records."""
from __future__ import annotations

import json
from pathlib import Path
import yaml
import pytest

from livinglit_lepidoptera import RECORDS_DIR
from livinglit_lepidoptera.across import Unit, compute_context_diff
from livinglit_lepidoptera.matching import Side
from livinglit_lepidoptera.gate_record import check_record
from livinglit_lepidoptera.models import GeneticsFile, Manifest, Record
from livinglit_lepidoptera.panels import PanelsFile, _is_composite_panel
from livinglit_lepidoptera.vocab import field_config, load_vocab


def test_atomic_one_letter_panel_guard():
    # Valid atomic panel IDs & labels
    for pid, lbl in [("A", "A"), ("A_prime", "A'"), ("A_dprime", "A''"), ("Ai", "Ai"), ("B", "2B"), ("G", "G")]:
        assert not _is_composite_panel(pid, lbl), f"Should accept atomic panel {pid}/{lbl}"
    # Composite panel IDs & labels MUST be rejected
    for pid, lbl in [("AB", "A-B"), ("CD", "CD"), ("top", "top"), ("bottom", "bottom"), ("A_C", "A–C"), ("left", "left")]:
        assert _is_composite_panel(pid, lbl), f"Should reject composite panel {pid}/{lbl}"


def test_manifest_schema_and_oa_policy():
    cfg = field_config("lepidoptera")
    assert cfg["policy"]["oa_only"] is True
    m_oa = Manifest(
        id="2024_Test",
        doi="10.1000/test",
        title="Test Lepidoptera Paper",
        year=2024,
        journal="Nature Communications",
        oa_status="open_access",
        license="CC-BY-4.0",
        figure_embed_policy="public_thumbnails",
    )
    assert m_oa.oa_status == "open_access"
    with pytest.raises(Exception):
        Manifest(id="bad", doi="x", title="t", year=2024, journal="j", oa_status="paywalled", license="none")


def test_relaxed_context_diff_and_confounders():
    v = load_vocab("lepidoptera")
    assert len(v.terms) >= 230
    assert "genetic_element_type" in v.fields
    assert "allele_or_zygosity" in v.fields
    assert "FlyBase:FBgn0004870" in (v.terms["target_gene:bric_a_brac"].xref or [])
    # All standing keys in field_set 4 are relaxed (must_match == [])
    for k, sk in v.keys.items():
        assert sk.value.must_match == [], f"Standing key {k} should have relaxed must_match=[]"

    ua = Unit(
        paper="2024_Lloyd", unit="U1", item="I1", group="g1",
        measure_terms=("measure:ridge_spacing",),
        measure_qualifiers={},
        context={
            "taxon": Side(terms={"taxon:heliconius_sara"}),
            "scale_type": Side(terms={"scale_type:cover_scale"}),
            "view_orientation": Side(terms={"view_orientation:top_down_apical"}),
            "hydration_and_prep": Side(terms={"hydration_and_prep:vacuum_sputter_coated"}),
        },
    )
    ub = Unit(
        paper="2026_Finet", unit="U2", item="I2", group="g2",
        measure_terms=("measure:ridge_spacing",),
        measure_qualifiers={},
        context={
            "taxon": Side(terms={"taxon:morpho_didius"}),
            "scale_type": Side(terms={"scale_type:cover_scale"}),
            "view_orientation": Side(terms={"view_orientation:tilted_oblique"}),
            "hydration_and_prep": Side(terms={"hydration_and_prep:dry_native"}),
        },
    )
    diff = compute_context_diff(v, ua, ub)
    assert "scale_type" in diff["matched"]
    assert "taxon" in diff["differing"]
    assert any("view_orientation" in c for c in diff["confounders"])
    assert any("hydration_and_prep" in c for c in diff["confounders"])


@pytest.mark.parametrize("paper,expected_fs,min_claims,min_ext", [
    ("2018_Parnell", 4, 7, 6),
    ("2020_Stavenga", 4, 7, 5),
    ("2021_McDougal", 4, 7, 4),
    ("2023_Banerjee", 4, 8, 0),
    ("2023_Seah", 4, 7, 1),
    ("2024_Livraghi", 4, 7, 1),
    ("2024_Lloyd", 3, 7, 3),
    ("2024_Totz", 4, 7, 6),
    ("2025_Loh", 4, 6, 2),
    ("2026_Finet", 3, 7, 3),
])
def test_pilot_records_schema_and_qa_clean(paper: str, expected_fs: int, min_claims: int, min_ext: int):
    rdir = RECORDS_DIR / paper
    mf = Manifest.model_validate(yaml.safe_load((rdir / "manifest.yaml").read_text(encoding="utf-8")))
    assert mf.oa_status == "open_access"

    rec = Record.model_validate(yaml.safe_load((rdir / "record.yaml").read_text(encoding="utf-8")))
    assert rec.field_set == expected_fs
    assert len(rec.claims) >= min_claims
    assert len(rec.context_anchors) >= 12

    pf = PanelsFile.model_validate(yaml.safe_load((rdir / "panels.yaml").read_text(encoding="utf-8")))
    for fid, fig in pf.figures.items():
        for pid, pspec in fig.panels.items():
            assert not _is_composite_panel(pid, pspec.label), f"{paper}/{fid}/{pid} is composite"

    qa = json.loads((rdir / "qa" / "report.json").read_text(encoding="utf-8"))
    assert qa["composite_panels"] == 0
    assert qa["flagged_panels"] == []
    assert qa["n_custom_extractors"] >= min_ext


def test_genetics_schema_and_binding_tier_guard(tmp_path: Path):
    total_rels = 0
    total_tables = 0
    for paper, min_rels in [("2023_Banerjee", 10), ("2023_Seah", 3), ("2024_Livraghi", 8), ("2025_Loh", 12)]:
        gf = GeneticsFile.model_validate(yaml.safe_load((RECORDS_DIR / paper / "genetics.yaml").read_text(encoding="utf-8")))
        assert len(gf.relations) >= min_rels
        total_rels += len(gf.relations)
        total_tables += len(gf.genomic_tables)
    assert total_rels >= 33
    assert total_tables >= 3

    rdir = RECORDS_DIR / "2025_Loh"
    gf = GeneticsFile.model_validate(yaml.safe_load((rdir / "genetics.yaml").read_text(encoding="utf-8")))
    assert any(r.id == "bab_binds_represses_mwh" for r in gf.relations)
    assert any(gt.id == "bab_uvi_de_targets" for gt in gf.genomic_tables)

    # Guard test: claiming direct binding / chromatin_or_binding_only without a binding assay MUST fail gate_record
    rec_copy = tmp_path / "2025_Loh_bad"
    rec_copy.mkdir()
    (rec_copy / "record.yaml").write_text((rdir / "record.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (rec_copy / "manifest.yaml").write_text((rdir / "manifest.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    bad_genetics = {
        "record": "2025_Loh_bad",
        "relations": [
            {
                "id": "bad_direct_claim",
                "source": "target_gene:bric_a_brac",
                "source_label": "Bab",
                "relation": "directly_binds_cre",
                "target": "target_gene:multiple_wing_hairs",
                "target_label": "Mwh",
                "evidence_tier": "direct_binding_and_perturbation",
                "assays": ["crispr_g0_mosaic"],
                "anchor": {"quote": "Bab", "where": "Results"},
            }
        ],
    }
    (rec_copy / "genetics.yaml").write_text(yaml.safe_dump(bad_genetics), encoding="utf-8")
    raw_rec = yaml.safe_load((rec_copy / "record.yaml").read_text(encoding="utf-8"))
    raw_rec["id"] = "2025_Loh_bad"
    _, probs = check_record(raw_rec, tmp_path, field_config("lepidoptera"), check_text=False, record_dir=rec_copy)
    assert any("binding/chromatin assay" in p.lower() for p in probs), f"Expected binding-assay guard error, got: {probs}"

