"""Unit tests for Manifest OA policy, atomic 1-letter panel guard, Shift #2 relaxed context_diff, and pilot records."""
from __future__ import annotations

import json
from pathlib import Path
import yaml
import pytest

from livinglit_lepidoptera import RECORDS_DIR
from livinglit_lepidoptera.across import Unit, compute_context_diff
from livinglit_lepidoptera.matching import Side
from livinglit_lepidoptera.models import Manifest, Record
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
    assert len(v.terms) >= 170
    # All standing keys in field_set 3 are relaxed (must_match == [])
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


@pytest.mark.parametrize("paper", ["2024_Lloyd", "2026_Finet"])
def test_pilot_records_schema_and_qa_clean(paper: str):
    rdir = RECORDS_DIR / paper
    mf = Manifest.model_validate(yaml.safe_load((rdir / "manifest.yaml").read_text(encoding="utf-8")))
    assert mf.oa_status == "open_access"

    rec = Record.model_validate(yaml.safe_load((rdir / "record.yaml").read_text(encoding="utf-8")))
    assert rec.field_set == 3
    assert len(rec.claims) >= 7
    assert len(rec.context_anchors) >= 15

    pf = PanelsFile.model_validate(yaml.safe_load((rdir / "panels.yaml").read_text(encoding="utf-8")))
    for fid, fig in pf.figures.items():
        for pid, pspec in fig.panels.items():
            assert not _is_composite_panel(pid, pspec.label), f"{paper}/{fid}/{pid} is composite"

    qa = json.loads((rdir / "qa" / "report.json").read_text(encoding="utf-8"))
    assert qa["composite_panels"] == 0
    assert qa["flagged_panels"] == []
    assert qa["n_custom_extractors"] >= 3
