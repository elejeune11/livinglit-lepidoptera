---
name: segment-panels
description: Stage 2 skill — Atomically segment every multi-panel figure into 1-letter subpanels, locate scale bars and microscopy FFT ROIs, write panels.yaml, and visually verify bounding boxes.
---

# `segment-panels` — Atomic 1-Letter Panel Segmentation & BBox QA

## Objective
Decompose every main (and key supplemental) figure of `papers_dont_ever_commit/<paper>/` into **atomic 1-letter panels** (`A`, `A_prime`, `A_dprime`, `B`, `C`, …), classify each panel's `archetype` (`planar_microscopy`, `cross_section`, `macro_morphology`, `quantitative_plot`, `spectral_or_profile`, `phylogeny_or_schematic`, `crispant_phenotype_plate`, `expression_imaging`, `expression_matrix`, `genomic_track_or_locus`), localize scale bars and microscopy ROIs, record genetic channel/crispant/locus metadata, and verify every crop visually.

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
   - For calibrated micrographs (`planar_microscopy`, `cross_section`, `macro_morphology`):
     - Record `scale_bar`: `{um, search_box: [rx0, ry0, rx1, ry1], polarity: "bright"|"dark"}` where `search_box` is relative to the panel crop (`[0..w, 0..h]`) tightly framing ONLY the scale bar line (not text above/below it!). Cross-check adjacent zoom panels for caption scale-bar typos!
     - **Fluorescent & Optical FFT Triage (NEVER skip fluorescent micrographs!)**:
       1. Check text & caption cues for periodicity (`"parallel"`, `"periodic"`, `"regularly spaced"`, `"regular intervals"`, `"organized actin bundles"`, `"maximally spaced"`, `"between the ridges"`, `"perpendicularly to the ridge"`, `"crossribs"`, pupal stage `>= 37.5–44%`) AND screen all calibrated planar micrographs with `scale_bar <= 15 µm`.
       2. Check physical feasibility: **Nyquist gate** `expected_spacing_um / um_per_px >= 3.0 px/cycle` and `>= 3.5–4` cycles inside a flat, non-fanning ROI.
       3. **Channel isolation**: On dual-channel green+magenta merges (interleaved actin & chitin), NEVER run `channel: gray` (causes false `2×` frequency!). Specify `channel: green_isolated` or `magenta` (and optional `crossrib_channel` for perpendicular cross-ribs/actin rungs); use `channel: max_rgb` for rainbow z-depth-coded STED.
     - Record `view_orientation` explicitly (`top-down apical`, `tilted oblique`, `cross-section`) — tilted SEMs foreshorten spacing by `cos(theta)`!
   - For **genetic / evo-devo / genomics panels**:
     - `expression_imaging` (HCR 3.0 in situ, IF, reporter imaging): populate `channel_gene_map` (e.g., `{green: "Bric-a-brac (Bab)", magenta: "F-actin", blue: "DAPI"}`).
     - `crispant_phenotype_plate` (CRISPR G0 mosaic, KO, RNAi wings): populate `crispant_summary` (`{target_gene, element_type, perturbation, sex, phenotype_summary, ...}`).
     - `genomic_track_or_locus` (ChIP-seq / ATAC-seq browser tracks, MEME-ChIP motifs): populate `genomic_locus` (`{scaffold, interval, locus_gene, stages}`).
     - `expression_matrix` (snRNA-seq / scRNA-seq dotplots, heatmaps, UMAPs): assign bespoke extractor if quantitative dotplot matrix can be extracted (`dotplot_matrix`).

3. **Write `records/<paper>/panels.yaml`**
   - Include figure metadata (`label`, `file`, `xml_id`, `title`, `caption_anchor`, `context`) and every atomic panel with `label`, `title`, `bbox`, `archetype`, `context`, and optional `scale_bar` / `periodic_spec` / `channel_gene_map` / `crispant_summary` / `genomic_locus` / `extractor`.

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
