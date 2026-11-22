---
name: segment-panels
description: Stage 2 skill — Atomically segment every multi-panel figure into 1-letter subpanels, locate scale bars and microscopy FFT ROIs, write panels.yaml, and visually verify bounding boxes.
---

# `segment-panels` — Atomic 1-Letter Panel Segmentation & BBox QA

## Objective
Decompose every main (and key supplemental) figure of `papers_dont_ever_commit/<paper>/` into **atomic 1-letter panels** (`A`, `A_prime`, `A_dprime`, `B`, `C`, …), classify each panel's modality (`microscopy_sem`, `microscopy_tem`, `microscopy_confocal`, `microscopy_optical`, `plot_spectrum`, `plot_scatter`, `plot_boxplot`, `plot_bar`, `plot_dotplot`, `plot_timeseries`, `photograph_macro`, `schematic`), localize scale bars and microscopy ROIs, and verify every crop visually.

## Hard Rules (Enforced by `gate panels`)
1. **No composite multi-panel boxes**: Panel IDs like `AB`, `CD`, `top`, `bottom`, `A-C`, `left`, `right` are **REJECTED** unless `composite_justification` explicitly proves inseparable overlapping typography (almost never needed — split them!).
2. **Primes are atomic**: Sub-panels labeled `A`, `A'`, `A''` in the figure MUST be segmented as separate panels with IDs `A`, `A_prime`, `A_dprime` (and human labels `"A"`, `"A'"`, `"A''"`).
3. **Tight, bleed-free crops**: `bbox: [x0, y0, x1, y1]` (in full-resolution image pixel coordinates) must include the panel's own axis labels, tick marks, legend, and scale bar, WITHOUT clipping text and WITHOUT bleeding neighboring panels' axis ticks or labels into the crop.

## Steps

1. **Inspect Every Figure Image Directly**
   - Check pixel dimensions `(W, H)` of every figure image in `papers_dont_ever_commit/<paper>/`.
   - View every full figure image with `view_file` and cross-reference its exact figure caption from JATS XML (`<fig><caption...>`).

2. **Measure Exact Pixel Coordinates**
   - Write a small helper check (or inspect grayscale row/column whitespace gutters) to place exact pixel `bbox: [x0, y0, x1, y1]` for every atomic panel.
   - For calibrated micrographs (`microscopy_sem`, `microscopy_confocal`, `microscopy_tem`, `microscopy_optical`):
     - Record `scale_bar`: `{length_um, search_box: [rx0, ry0, rx1, ry1], polarity: "bright"|"dark"}` where `search_box` is relative to the panel crop (`[0..w, 0..h]`) tightly framing ONLY the scale bar line (not text above/below it!).
     - If the micrograph shows periodic scale nanostructures (longitudinal ridges, actin bundles, cross-ribs, lamellae), set `ridge_fft` with a clean `roi: [rx0, ry0, rx1, ry1]` strictly inside the **planar scale lamina** (avoiding scale margins, sockets, orthogonal XZ cross-section strips, text annotations, and scale-bar insets!), plus physically informed `spacing_range_um` (e.g. `[0.55, 1.4]` for butterfly ridges, `[0.15, 0.55]` for cross-ribs).
     - Record `view_orientation` explicitly (`planar_apical`, `tilted_oblique`, `cross_section`, `top_down`, `side_view`) — tilted SEMs foreshorten spacing by `cos(theta)`!

3. **Write `records/<paper>/panels.yaml`**
   - Include figure metadata (`id`, `file`, `title`, `caption_summary`) and every atomic panel with `id`, `label`, `kind`, `bbox`, `summary`, `taxon`, `scale_type`, `imaging_modality`, `view_orientation`, `hydration_and_prep`, `perturbation`, and optional `scale_bar` / `ridge_fft`.

4. **Render & Visually Verify the BBox Contact Sheet**
   ```bash
   uv run livinglit-lep qa <paper> --out qa_renders
   ```
   - Open `qa_renders/bbox_<paper>.png` with `view_file`.
   - Inspect **every single figure**:
     - Does every panel have its own distinct rectangle?
     - Are any axis labels, panel letters, or scale bars clipped?
     - Do any adjacent panels bleed into a plot box?
   - Adjust any imperfect `bbox` in `panels.yaml` and re-render until spotless.
