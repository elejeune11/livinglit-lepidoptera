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
- Axis calibration: `AxisCal`, `find_axis_ticks` (auto-detect spines & tick stubs, assert exact tick count, report RMS `x_misfit_px`/`y_misfit_px`), `lin_range`, `log_range`
- Curve & band extraction: `ray_dist_alpha` (**always compute per-pixel validity & inter-trace repulsion BEFORE horizontal column pooling** so white-edge `perp=0` never pairs with a neighbor curve's high `alpha`!), `viterbi_track` (L1-slope DP), `walk_ribbon_bounds` (`±SD` / 95% CI ribbon walker)
- Scatter, overlapping markers & shaded overlays: `shaded_bg_residual` (morphological/median background subtraction so dots inside translucent 95% CI ribbons, notched boxplots, or colored violins retain full contrast), `detect_markers_matched_filter` (occlusion-aware $S = T + 0.5\,O - 3\,B$ via `fftconvolve` across `disk` and `triangle_up` kernels with iterative greedy peeling `tgt -> occ` so overlapping markers and markers behind regression lines or red ±SD bars are never merged or dropped!)
- Regression, errorbars & bars: `fit_irls_line_and_ci`, `trace_error_arms_occluded` (walks across occluders and mirrors hidden ends), `trace_error_arms`, `extract_vertical_bars`, `compute_curve_rmse`
- Calibrated Microscopy Metrology: `measure_periodic_fft_verified` + `measure_transects_with_coords` + `check_fft_harmonics` (supports `green_isolated`, `magenta`, `max_rgb` depth-colored STED, `gray`/`blue`, plus separate `crossrib_channel` for dual-channel orthogonal cross-rib/actin-rung periodicity!)

## Two-Stage Fluorescent & Optical Microscopy FFT Triage
NEVER stop at SEM panels — audit **every** confocal, TauSTED, SIM, and optical panel:
1. **Text & Caption Cues**: Scan text/captions for positive cues (`"parallel"`, `"periodic"`, `"regularly spaced"`, `"regular intervals"`, `"organized actin bundles"`, `"maximally spaced"`, `"between the ridges"`, `"perpendicularly to the ridge"`, `"crossribs"`, pupal stage `>= 37.5–44%`) and negative cues (`"nascent"`, `"cytoplasmic projections"`, `"angled out of plane"`, `"orthogonal view"`, `"hundreds of scales"`). Also screen any calibrated planar micrograph with `scale_bar <= 15 µm`.
2. **Physical Feasibility & Channel Separation**:
   - **Nyquist gate**: `expected_spacing_um / um_per_px >= 3.0 px/cycle` (skip undersampled low-mag overviews).
   - **Cycle gate**: Flat, non-fanning ROI with `>= 3.5–4` cycles.
   - **Channel isolation**: On green+magenta merges (actin between chitin ridges), **NEVER run grayscale FFT** (interleaved stripes create a false `2×` frequency!). Always isolate `green_isolated` and/or `magenta`; use `max_rgb` for rainbow z-depth-coded STED.

## Plot Digitization Rules (Zero Missed Overlapping or Shaded Points)
- **Never use naive connected-components `blobs()` on overlapping scatter plots** — touching markers merge into one centroid! Use `detect_markers_matched_filter(..., peel=True, upsample=2..3)` (with both `disk` and `triangle_up` passes for mixed shapes).
- **Never threshold raw `lum < 90 & sat < 35` on plots with translucent 95% CI ribbons or shaded violins/boxplots** — ggplot2 draws ribbons *over* points, shifting black dots to dark brown/plum! Always apply `shaded_bg_residual` and place regression lines / red ±SD bars in `occ`.
- **On boxplots/violins with overlaid jitter dots**: extract BOTH `digitized_boxplots` AND `digitized_scatter` (using box-polygon separation or adaptive dot radius `sqrt(med_area/pi)`), noting honestly if solid `#000` black violin fill makes interior black dots optically unobservable.
- **On additive black-background fluorescence profiles** (`green + magenta = white`): read `G` and `0.5*(R+B)` directly without crosstalk subtraction so colocalized overlaps never drop to zero!

## Extractor Function Contract
In `panels.yaml`, point any quantitative panel to its custom function:
```yaml
extractor: extractors/f5_milling.py:extract
```
Each extractor function signature:
```python
def extract(crop_rgb: np.ndarray, panel_id: str, fig_id: str = "", full_rgb: np.ndarray | None = None, bbox: tuple[int, int, int, int] = (0, 0, 0, 0)) -> dict:
    return {
        "curves": {...},                 # optional: {name: {x, y, lo, hi, peak_x, peak_y, x_unit, y_unit}}
        "digitized_scatter": {...},      # optional: {group: {n, x, y, x_lo, x_hi, y_lo, y_hi, y_interval, x_unit, y_unit}}
        "digitized_boxplots": {...},     # optional: {group: {median, q1, q3, whisker_lo, whisker_hi, y_unit}}
        "dotplot_matrix": {...},         # optional: {clusters, genes, expr_range, cells: [{cluster, gene, pct, expr, px, py, r_px}]}
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": [350.0, 700.0], "y_range": [0.0, 80.0],
            "x_misfit_px": 0.14, "y_misfit_px": 0.12,
            "kind": "curves",            # curves | scatter | boxplots | dotplot
        },
    }
```

## Automated Quality Guards (Run by `gate panels <paper> --apply`)
1. **Atomic 1-letter Panel Guard**: Rejects composite panel IDs.
2. **FFT 2× Harmonic / Subharmonic Guard**: Flags any micrograph where FFT-vs-transect delta exceeds 12% or `harmonic_ratio_2f >= 0.60` unless visually confirmed (`harmonic_verified: true`).
3. **Plot Span Completeness Guard**: Flags curves covering `< 70%` of the calibrated `x_range` unless `partial_x_range: true` is declared.
4. **Raw-Data Benchmark RMSE**: When raw repository CSV/XLSX data exists, cross-checks digitized series RMSE against the raw source.
5. **Persisted QA Manifest**: Automatically writes `records/<paper>/qa/report.json`.

## Execution & Mandatory Visual Self-Check Loop

```bash
uv run livinglit-lep gate panels <paper> --apply
uv run livinglit-lep qa <paper> --out qa_renders
```

1. **Inspect `qa_renders/plots_<paper>.png` (and 2–3× zoomed scatter/curve crops for dense panels) with `view_file`**:
   - Confirm cyan `plot_box` hugs exact axis ticks and `x_misfit_px` / `y_misfit_px` are sub-pixel.
   - Confirm hollow verification rings sit dead-center on **every** individual scatter dot (including overlapping clusters, dots inside translucent 95% CI ribbons, dots behind red ±SD bars, and jitter dots on boxplots/violins).
   - Confirm zero legend contamination, zero cross-curve jump/kiss, and zero dropped uncertainty bands.
2. **Inspect `qa_renders/fft_<paper>.png` with `view_file`**:
   - Confirm yellow scale-bar bracket aligns with exact scale-bar endpoints (cross-check adjacent zoom panels for caption scale-bar typos!).
   - Confirm bright-green phase-aligned grating lines sit **1-to-1 on EVERY SINGLE ridge/actin crest** (and magenta orthogonal grating on crossribs/perpendicular actin filaments where measured).
3. **Iterate**: If ANY panel has a visual flaw or `flagged` status in `records/<paper>/qa/report.json`, refine the extractor / ROI / `spacing_range_um`, re-run `gate panels --apply` and `qa`, and re-inspect via `view_file` until 100% spotless!
