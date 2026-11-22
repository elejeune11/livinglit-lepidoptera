# 05 · Autonomous 5-Stage Agent Skill Pipeline (`skills/`)

This document defines **Shift #3**: turning paper ingestion from ad-hoc prototype scripting into a **deterministic, autonomous, self-verifying agent skill pipeline** that requires zero human babysitting once validated on our initial 2-paper pilot.

![Autonomous 5-Stage Agent Skill Pipeline & Self-Closing QA Loops](figures/fig4_autonomous_skill_pipeline.svg)

---

## 1. Design Principle: Autonomous Self-Closing Loops

After the initial human review of the 2-paper gold-standard pilot, adding a new open-access Lepidoptera paper must run **autonomously from DOI/folder to published visualizer** without silently introducing bad curves, merged panels, or 2× FFT harmonic errors. Every stage therefore pairs **code execution** with a **self-closing verification gate**:

| Stage | Skill | Inputs | Outputs | Autonomous Verification Loop & Hard Exit Criteria |
|---|---|---|---|---|
| **1** | `skills/ingest-paper/SKILL.md` | Paper DOI / URL / local OA folder | `papers_dont_ever_commit/<paper>/` + `manifest.yaml` + `resources.yaml` | Downloads OA PDF/XML, high-res figures, and linked repos (Dryad/OSF/Figshare/eLife/GitHub); verifies OA license; enforces 100% file accounting and zero source files tracked in git. |
| **2** | `skills/segment-panels/SKILL.md` | Full-res figures + captions | Atomic `panels.yaml` + `qa/bboxes_*.png` | Splits every figure into 1-letter panels with archetypes & `scale_bar` coords; renders **Full-Figure BBox Contact Sheets**; agent visually inspects every sheet and iterates coords until zero merged panels or clipped axis ticks remain. |
| **3** | `skills/digitize-panels/SKILL.md` | `panels.yaml` + full-res figures + Tier-1 raw files | `extractors/*.py` + `digitized/{panels_extracted.json,series.csv}` + `qa/report.json` | **Parallelizable per figure via subagents**: writes bespoke `extractors/fN.py` using `extract_lib.py` (or configures microscopy FFT ROI); renders Plot & FFT Grating Overlays; visually inspects every overlay + runs **FFT harmonic, curve span, and raw-data RMSE guards**; retries up to 3× and flags any unresolved ambiguity transparently in `qa/report.json`. |
| **4** | `skills/read-record/SKILL.md` | Full text, tables, SI docs, raw data, `panels.yaml` | `record.yaml`, `data.yaml`, `terms.yaml`, `derived.yaml`, `readings.yaml` | Executes Lepidoptera-native LivingLit reading (all printed values, raw cells, `context_anchors`, `other_conditions`, SymPy formulas, full 7-dim within-paper claims, panel ↔ item links); loops until all 5 gates (`record`, `figures`, `terms`, `derived`, `panels`) print `GATE PASSES`. |
| **5** | `skills/publish-site/SKILL.md` | All `records/*/` | `releases/` + `docs/` + `overview.html` | Runs `audit` → `release` → `harvest` → modular `web/` build → headless Playwright visual & 0-JS-error smoke tests across light & dark themes. |

Top-level orchestrator skill **`skills/add-paper/SKILL.md`** chains Stages 1–5 end-to-end with a single invocation.

---

## 2. Autonomous Confidence Logging (`records/<paper>/qa/report.json`)

Because autonomous ingestion must **never hide uncertainty or silently fake precision**, Stage 3 writes a committed, machine-readable `qa/report.json` per paper:

```json
{
  "paper": "2024_Lloyd",
  "n_figures": 8,
  "n_atomic_panels": 87,
  "composite_panels": 0,
  "panels": {
    "2024_Lloyd/F2/F": {
      "method": "custom:extractors/f2_morphometrics.py",
      "overlay_checked": true,
      "span_coverage": 0.98,
      "retries": 1,
      "confidence": "verified"
    },
    "2024_Lloyd/F8/I": {
      "method": "microscopy_fft",
      "overlay_checked": true,
      "fft_um": 0.864,
      "transect_um": 0.851,
      "fft_transect_delta_pct": 1.5,
      "harmonic_guard": "pass",
      "snr": 842.0,
      "confidence": "verified"
    }
  }
}
```

Confidence states (`verified`, `low_snr_verified`, `partial_occlusion`, `flagged_needs_review`) are surfaced right inside the Panel Inspector and Audit views so readers immediately know the exact provenance and QA status of every single number.

---

## 3. Two-Phase Rollout Plan

### Phase A · Gold-Standard Validation Pilot (Human Check Checkpoint)
Run **two contrasting open-access papers** completely through Stages 1–5 with zero shortcuts:
1. **`2024_Lloyd`** (*Heliconius sara*, *Nature Communications*, CC-BY-4.0) — stress-tests confocal + SIM + SEM microscopy, actin & ridge 2D-FFT (including fixing the `F8/I` 2× harmonic error, `F7/D` XZ ROI, and `F6/G` inset overlap), Cytochalasin D perturbation, joint scatter + OLS + 95% CI plots (`F2/D–F`), reflectance spectra + `±SD` bands (`F8/E`), beeswarm dotplots (`F8/N–O`), notched boxplots (`F2/J–L`), and full text/table/supplement/claim auditing.
2. **`2026_Finet`** (34 butterfly species + *Bicyclus anynana* + *Morpho didius*, *Current Biology* OA) — stress-tests 34-species comparative phylogenetics, 39-scale scatter with per-point horizontal & vertical `±SD` errorbars (`F4/A`), PGLS regressions + dots + 95% CI ribbons (`F4/B–C`), FIB-SEM cross-sections & depth-stepped milling (`F5` split atomically into `A, B, C, D, C', D', C'', D''`), crossing experimental + FDTD reflectance spectra with `±SD` bands, selection spectra (`F2/B–C`), violin/boxplots (`F1`, `F2/E–J`), and full claim auditing.

**Human review checkpoint**: Inspect the live pilot repo, QA contact sheets, `qa/report.json`, and rebuilt visualizer. Any schema, gate, or UX refinement happens *once* here.

### Phase B · Autonomous Scale-Up to Full Seed Corpus & New Papers
Once the pilot is signed off, run the remaining **6 OA seed papers** (`2018_Parnell`, `2021_McDougal`, `2023_Banerjee`, `2023_Seah`, `2024_Totz`, `2025_Loh`) autonomously through `skills/add-paper` (parallelized across papers/figures) — atomically splitting all remaining composite panels, replacing every flawed declarative plot with bespoke `.py` extractors, verifying every FFT grating, and completing full LivingLit text/table/claim reads — followed by any new butterfly or moth OA papers added in the future.
