---
name: digitize-panels
description: Stage 3 skill — Write bespoke per-figure Python extractors using extract_lib, verify microscopy 2D-FFT + transects against 2x harmonic locks, and visually verify every plot and microscopy overlay.
---

# `digitize-panels` — Bespoke Extraction, Unified Overlays & Visual QA

## Objective
Extract publication-grade numerical data from **every quantitative plot and periodic micrograph** in a paper with 100% auditable code, emit unified `overlay_meta` geometry for live UI verification, pass all automated quality guards, and visually verify EVERY extracted overlay.

## Core Design Principle (Shift #1 & Shift #3)
- **Never rely on brittle generic black-box curve heuristics.** Write a dedicated, clean, readable Python script per quantitative figure at `records/<paper>/extractors/<fig_slug>.py` importing shared primitives from `livinglit_lepidoptera.extract_lib`.
- **Every extraction emits `overlay_meta`** so BOTH `qa_overlays.py` (offline PNG QA sheets) AND `web/js/overlays.js` (live interactive browser `Overlay check`) render the exact extracted geometry directly on top of the source crop.

## `extract_lib.py` Primitives
Import from `livinglit_lepidoptera.extract_lib`:
- Axis calibration: `lin_range`, `log_range`, `px_to_data_x`, `px_to_data_y`, `data_to_px_x`, `data_to_px_y`
- Curve & band extraction: `ray_dist_alpha` (color-distance / alpha-blended band detector), `viterbi_track` (L1-slope dynamic programming optimal curve tracker), `walk_ribbon_bounds` (`±SD` / 95% CI ribbon envelope walker)
- Regression, errorbars & bars: `fit_irls_line_and_ci`, `trace_error_arms` (per-point horizontal `x_lo/x_hi` and vertical `y_lo/y_hi` whiskers), `extract_vertical_bars`, `compute_curve_rmse`
- Calibrated Microscopy Metrology: `measure_periodic_fft_verified` (2D-FFT returning `spacing_um`, `angle_deg`, `phase_shift_px`, `snr`, `harmonic_ratio_2f`, `harmonic_ratio_half`, `harmonic_flag`) + `measure_transects_with_coords` (10 perpendicular intensity transects with exact `p0`, `p1`, `peaks_px`)

## Extractor Function Contract
In `panels.yaml`, point any quantitative panel to its custom function:
```yaml
custom_extractor:
  script: extractors/f5_milling.py
  func: extract_f5_panel
  params:
    panel_id: D_prime
```
Each extractor function signature:
```python
def extract_f5_panel(crop_bgr: np.ndarray, spec: PanelSpec, params: dict) -> dict:
    return {
        "plot_type": "curve_series",        # curve_series | scatter | boxplot | bar | dotplot
        "x_label": "Wavelength", "x_unit": "nm", "x_range": [300.0, 700.0],
        "y_label": "Reflectance", "y_unit": "%", "y_range": [0.0, 40.0],
        "series": [...],                    # or "points": [...], "boxes": [...], "groups": [...]
        "overlay_meta": {
            "kind": "plot",
            "plot_box": [px0, py0, px1, py1],
            "x_range": [300.0, 700.0], "y_range": [0.0, 40.0],
            "x_scale": "linear", "y_scale": "linear",
            # optional: curves_px, ribbons_px, points_px, errorbars_px, boxes_px, circles_px
        },
        "notes": "L1-Viterbi curve + alpha ribbon extraction",
    }
```

## Automated Quality Guards (Run by `gate panels <paper> --apply`)
1. **Atomic 1-letter Panel Guard**: Rejects composite panel IDs.
2. **FFT 2× Harmonic / Subharmonic Guard**: Flags any micrograph where FFT-vs-transect delta exceeds 12%, `harmonic_ratio_2f > 0.35`, or `harmonic_ratio_half > 0.45` (catching locks onto every other ridge!).
3. **Plot Span Completeness Guard**: Flags curves covering `< 70%` of the calibrated `x_range` unless `partial_x_range: true` is declared.
4. **Raw-Data Benchmark RMSE**: When raw repository CSV/XLSX data exists, cross-checks digitized series RMSE against the raw source.
5. **Persisted QA Manifest**: Automatically writes `records/<paper>/qa/report.json`.

## Execution & Mandatory Visual Self-Check Loop

```bash
uv run livinglit-lep gate panels <paper> --apply
uv run livinglit-lep qa <paper> --out qa_renders
```

1. **Inspect `qa_renders/plots_<paper>.png` with `view_file`**:
   - Confirm cyan `plot_box` hugs the exact inner axes ticks.
   - Confirm every curve, `±SD`/CI ribbon, scatter dot, errorbar cap, box median/IQR/whisker, and dotplot circle lands cleanly on the underlying pixels.
   - Confirm zero legend contamination, zero cross-curve jump/kiss, and zero dropped uncertainty bands.
2. **Inspect `qa_renders/fft_<paper>.png` with `view_file`**:
   - Confirm the yellow scale-bar bracket aligns with the exact pixel endpoints of the image scale bar.
   - Confirm the cyan FFT ROI sits cleanly inside the periodic scale lamina (never on XZ strips, scale edges, or insets).
   - Confirm the bright-green phase-aligned grating lines sit **1-to-1 on EVERY SINGLE ridge crest** (not every other ridge = 2× harmonic, and not twice per ridge = 0.5×!).
3. **Iterate**: If ANY panel has a visual flaw or `flagged` status in `records/<paper>/qa/report.json`, refine the extractor / ROI / `spacing_range_um`, re-run `gate panels --apply` and `qa`, and re-inspect via `view_file` until 100% spotless!
