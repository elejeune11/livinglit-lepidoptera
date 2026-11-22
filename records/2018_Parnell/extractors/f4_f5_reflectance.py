"""Bespoke extractor for Parnell et al. (2018) Figures 4 & 5 reflectance panels
(rsif20170948-g4.jpg panels A, C, E, G and rsif20170948-g5.jpg panels A, C, E):
Mean ± SD optical reflectance spectra (300–700 nm, 0–40%) for forewing (red solid line +
pink SD ribbon) and hindwing (blue dashed line + lavender SD ribbon) across all 7 Heliconius taxa.

Uses `find_axis_ticks` for exact tick-mark calibration (misfit <= 0.19 px), color-ray ink
decomposition (`ray_dist_alpha`) + L1 Viterbi curve tracking (`viterbi_track`) for mean lines,
and continuous ribbon boundary walking (`walk_ribbon_bounds`) for ±SD envelopes.
"""
from __future__ import annotations

from typing import Any
import numpy as np

from livinglit_lepidoptera.extract_lib import (
    find_axis_ticks,
    ray_dist_alpha,
    viterbi_track,
    walk_ribbon_bounds,
)


def _extract_panel_spectra(crop_rgb: np.ndarray, fig_id: str, panel_id: str) -> dict[str, Any]:
    ax = find_axis_ticks(
        crop_rgb,
        y_labels=[0.0, 10.0, 20.0, 30.0, 40.0],
        x_labels=[300.0, 400.0, 500.0, 600.0, 700.0],
        dark_thr=195.0,
        probe=(2, 5),
        tick_min_frac=0.45,
        min_spine_frac=0.30,
    )
    px0, py0, px1, py1 = ax["plot_box"]
    x_cal, y_cal = ax["x_cal"], ax["y_cal"]
    xr = list(x_cal.range_for_span(px0, px1, ndigits=3))
    yr = list(y_cal.range_for_span(py1, py0, ndigits=3))

    sub = crop_rgb[py0:py1, px0:px1].astype(np.float32).copy()
    h, w = sub.shape[:2]

    # Mask top-left species title text + optional top-right legend in F4/A & F5/A
    mask_excl = np.zeros((h, w), dtype=bool)
    mask_excl[:26, :165] = True
    if panel_id == "A":
        # Legend sits in top-right of F4/A and F5/A
        mask_excl[:52, int(w * 0.56):] = True

    R, G, B = sub[:, :, 0], sub[:, :, 1], sub[:, :, 2]

    # Sample columns spanning exact [300, 700] nm
    c_start = max(1, int(round(x_cal.to_pixel(300.0) - px0)))
    c_end = min(w - 2, int(round(x_cal.to_pixel(700.0) - px0)))
    cols = np.linspace(c_start, c_end, 81).astype(int)
    xs_val = [round(float(x_cal.to_value(px0 + c)), 2) for c in cols]

    # Red (forewing) and blue (hindwing) color-ray separation
    # Core curves have depressed green channel (G << max(R, B)), ribbons sit at lower opacity along same ray.
    perp_r, alpha_r = ray_dist_alpha(sub, (225, 35, 35))
    perp_b, alpha_b = ray_dist_alpha(sub, (45, 55, 225))

    # Chromatic excess strongly separates red solid core vs blue dashed core even where ribbons overlap!
    red_excess = np.clip(R - G, 0.0, 255.0)
    blue_excess = np.clip(B - G, 0.0, 255.0)
    red_dom = np.clip(R - B, -255.0, 255.0)
    blue_dom = np.clip(B - R, -255.0, 255.0)
    dark_g = np.clip(255.0 - G, 0.0, 255.0)

    # Ribbon masks (include purple overlap region where both red and blue ribbons superimpose!)
    ribbon_r = (red_excess >= 10.0) & (~mask_excl) & ((R - B) > -45.0)
    ribbon_b = (blue_excess >= 10.0) & (~mask_excl) & ((B - R) > -45.0)
    # Include dark curve pixels inside their own ribbons so ribbon walker never stops at the curve itself
    ribbon_r |= (red_excess >= 25.0) & (~mask_excl)
    ribbon_b |= (blue_excess >= 25.0) & (~mask_excl)

    # For low-reflectance melanic taxa (F4/C H. e. demophoon, F5/C H. m. rosina), both curves hug 0-2.5%
    is_dark_taxon = (panel_id == "C")
    max_step = 8 if is_dark_taxon else 14
    smooth_w = 0.55 if is_dark_taxon else 0.35

    # Build per-column Viterbi cost grids
    def _track_trace(is_red: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        cost = np.full((h, len(cols)), 35.0, dtype=np.float64)
        for ti, c in enumerate(cols):
            c0, c1 = max(0, c - 1), min(w, c + 2)
            if is_red:
                # Red solid line: strong R-G and low G (saturated red, not pale pink)
                re_col = red_excess[:, c0:c1].max(axis=1)
                dg_col = dark_g[:, c0:c1].max(axis=1)
                rd_col = red_dom[:, c0:c1].max(axis=1)
                pr_col = perp_r[:, c0:c1].min(axis=1)
                al_col = alpha_r[:, c0:c1].max(axis=1)
                # Core score rewards saturated dark red (high R-G & high 255-G) and allows purple overlap
                core = (re_col >= 26.0) & (dg_col >= 45.0) & (rd_col >= -25.0) & (~mask_excl[:, c])
                strength = 0.65 * re_col + 0.35 * dg_col + 0.15 * np.maximum(rd_col, 0.0)
                if is_dark_taxon:
                    # Constrain flat melanic spectra below 8% reflectance (bottom 22% of plot)
                    core &= (np.arange(h) >= int(h * 0.72))
                c_col = np.where(core, np.maximum(0.0, 26.0 - 0.14 * strength + 0.05 * pr_col), 32.0 - 4.0 * np.clip(al_col, 0, 1))
            else:
                # Blue dashed line: strong B-G and low G; dashed gaps bridge smoothly via L1 Viterbi!
                be_col = blue_excess[:, c0:c1].max(axis=1)
                dg_col = dark_g[:, c0:c1].max(axis=1)
                bd_col = blue_dom[:, c0:c1].max(axis=1)
                pb_col = perp_b[:, c0:c1].min(axis=1)
                al_col = alpha_b[:, c0:c1].max(axis=1)
                core = (be_col >= 24.0) & (dg_col >= 45.0) & (bd_col >= -25.0) & (~mask_excl[:, c])
                strength = 0.65 * be_col + 0.35 * dg_col + 0.15 * np.maximum(bd_col, 0.0)
                if is_dark_taxon:
                    core &= (np.arange(h) >= int(h * 0.72))
                c_col = np.where(core, np.maximum(0.0, 26.0 - 0.14 * strength + 0.05 * pb_col), 32.0 - 4.0 * np.clip(al_col, 0, 1))
            c_col[mask_excl[:, c]] = 100.0
            cost[:, ti] = c_col

        y_path = viterbi_track(cost, max_step=max_step, smooth_w=smooth_w, norm="l1")
        rmask = ribbon_r if is_red else ribbon_b
        y_lo_px, y_hi_px = walk_ribbon_bounds(
            rmask, cols, y_path, max_half=95, max_gap=4, top_pad=10, bot_pad=1, col_half_w=1
        )
        return y_path, y_lo_px, y_hi_px

    curves: dict[str, Any] = {}
    for cname, is_red in [("forewing", True), ("hindwing", False)]:
        yp, ylo_px, yhi_px = _track_trace(is_red)
        ys = [round(max(0.0, float(y_cal.to_value(py0 + r))), 3) for r in yp]
        lo = [round(max(0.0, float(y_cal.to_value(py0 + r))), 3) for r in ylo_px]
        hi = [round(max(0.0, float(y_cal.to_value(py0 + r))), 3) for r in yhi_px]
        # Ensure lo <= y <= hi
        lo = [min(a, b) for a, b in zip(lo, ys)]
        hi = [max(a, b) for a, b in zip(hi, ys)]
        pk = int(np.argmax(ys))
        curves[cname] = {
            "x": xs_val,
            "y": ys,
            "lo": lo,
            "hi": hi,
            "peak_x": xs_val[pk],
            "peak_y": ys[pk],
            "x_unit": "nm",
            "y_unit": "%",
        }

    return {
        "curves": curves,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": xr,
            "y_range": yr,
            "x_misfit_px": ax["x_misfit_px"],
            "y_misfit_px": ax["y_misfit_px"],
            "kind": "curves",
        },
        "extracted_data": {
            "x_tick_misfit_px": ax["x_misfit_px"],
            "y_tick_misfit_px": ax["y_misfit_px"],
            "forewing_peak_nm": curves["forewing"]["peak_x"],
            "forewing_peak_pct": curves["forewing"]["peak_y"],
            "hindwing_peak_nm": curves["hindwing"]["peak_x"],
            "hindwing_peak_pct": curves["hindwing"]["peak_y"],
        },
    }


def extract(crop_rgb: np.ndarray, panel_id: str, fig_id: str = "", **_: Any) -> dict[str, Any]:
    return _extract_panel_spectra(crop_rgb, fig_id, panel_id)
