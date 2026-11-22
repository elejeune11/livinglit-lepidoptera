# Figures, Panels & Data Reader — Lepidoptera

You are digitizing quantitative plots and periodic micrographs for a Lepidoptera paper under `records/<paper>/`.

## Core Rules
1. **Atomic 1-letter panels only**: Segment every panel in `panels.yaml` into a single atomic panel (`A`, `A_prime`, `B`, `C`…). Never leave composite multi-panel boxes (`AB`, `top`, `A-C`).
2. **Bespoke per-figure Python extractors**: For every quantitative figure (`plot_spectrum`, `plot_scatter`, `plot_boxplot`, `plot_bar`, `plot_dotplot`, `plot_timeseries`), write a dedicated script in `records/<paper>/extractors/<fig>.py` using `livinglit_lepidoptera.extract_lib`.
3. **Unified `overlay_meta` geometry**:
   - Every plot extractor emits `overlay_meta` with calibrated `plot_box`, `x_range`, `y_range`, and pixel traces (`curves_px`, `ribbons_px`, `points_px`, `errorbars_px`, `boxes_px`, `circles_px`).
   - Every calibrated micrograph emits `overlay_meta` with `scale_bar_px`, `roi_px`, phase-aligned `grating`, optional `crossrib_grating`, and 10 perpendicular `transects`.
4. **Mandatory Visual QA**: Run `uv run livinglit-lep gate panels <paper> --apply` and `uv run livinglit-lep qa <paper> --out qa_renders`. Visually inspect `bbox_<paper>.png`, `plots_<paper>.png`, and `fft_<paper>.png` until every overlay lands pixel-for-pixel on the figure and `qa/report.json` has `n_flagged == 0`.
5. **Respect physical confounders**: Tag `view_orientation` (`planar_apical` vs `tilted_oblique` vs `cross_section`) and `hydration_and_prep` (`dry_air_sem` vs `live_hydrated_in_vivo` vs `fixed_hydrated_confocal`) explicitly.
