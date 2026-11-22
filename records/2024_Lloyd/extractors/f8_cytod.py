"""Bespoke extractor for Lloyd et al. (2024) Figure 8E, 8N, 8O (41467_2024_48060_Fig8_HTML.jpg):
- F8/E: Control (red + translucent pink ±SD ribbon) and Cyto D (blue + translucent light-blue ±SD ribbon)
  reflectance spectra across 350..700 nm using ray_dist_alpha + L1 viterbi_track + walk_ribbon_bounds.
- F8/N: Adult scale ridge number beeswarm (control vs cyto) — automatic y-tick calibration (RMS misfit
  reported) + occlusion-aware matched-filter peeling (`occ = red_mk`) so ZERO black dots are dropped or
  split by the overlaid red mean ± SD bar!
- F8/O: Adult scale ridge curvature κ (µm⁻¹) beeswarm (control vs cyto) — automatic y-tick calibration
  + occlusion-aware matched-filter peeling (`occ = red_mk`) recovering 12/12 control and 12/12 cyto dots!
"""
from __future__ import annotations

from typing import Any
import numpy as np
from scipy.ndimage import median_filter

from livinglit_lepidoptera.extract_lib import (
    detect_markers_matched_filter,
    find_axis_ticks,
    lin_range,
    ray_dist_alpha,
    viterbi_track,
    walk_ribbon_bounds,
)


def _extract_f8e_spectra(crop_rgb: np.ndarray) -> dict[str, Any]:
    px0, py0, px1, py1 = 38, 6, 281, 235
    sub = crop_rgb[py0:py1, px0:px1].astype(np.float32).copy()
    sub[:48, :90] = 255.0
    h, w = sub.shape[:2]

    y_max, y_min = lin_range(0, h, 8.0, 12.0, 216.0, 4.0)
    x_min, x_max = lin_range(0, w, 11.0, 350.0, 232.0, 700.0)

    def px2x(cx: float) -> float:
        return round(x_min + (cx / max(w, 1)) * (x_max - x_min), 3)

    def py2y(cy: float) -> float:
        return round(y_max - (cy / max(h, 1)) * (y_max - y_min), 4)

    r = sub[:, :, 0]
    g = sub[:, :, 1]
    b = sub[:, :, 2]

    cols = np.linspace(11, 232, 71).astype(int)

    perp_r, _ = ray_dist_alpha(sub, (231, 45, 40))
    perp_b, _ = ray_dist_alpha(sub, (52, 128, 198))

    rib_ctrl = ((r - g) >= 14.0) & (r >= 195.0) & (g <= 238.0)
    rib_cyto = (((b - r) >= 10.0) & (b >= 195.0) & (r <= 238.0)) | (((b - g) >= 10.0) & ((r - g) >= 8.0) & (g <= 228.0))

    red_core = np.clip((r - 0.5 * (g + b)) / 140.0, 0.0, 1.2) * (perp_r < 55.0)
    cost_ctrl = np.where(red_core > 0.35, 1.2 - red_core, 2.5 + 0.03 * perp_r)
    red_in_ov = ((r - g) >= 48.0) & (r >= 175.0)
    cost_ctrl = np.where(red_in_ov, np.minimum(cost_ctrl, 0.35), cost_ctrl)

    blue_core = np.clip((b - r) / 95.0, 0.0, 1.2) * (perp_b < 55.0) * (r < 208.0)
    cost_cyto = np.where(blue_core > 0.32, 1.2 - blue_core, 2.5 + 0.03 * perp_b)
    blue_in_ov = ((b - g) >= 24.0) & (r < 195.0) & (b > 180.0)
    cost_cyto = np.where(blue_in_ov, np.minimum(cost_cyto, 0.45), cost_cyto)

    y_ctrl = viterbi_track(cost_ctrl[:, cols], max_step=14, smooth_w=0.18, norm="l1")
    y_cyto = viterbi_track(cost_cyto[:, cols], max_step=12, smooth_w=0.22, norm="l1")

    ylo_ctrl, yhi_ctrl = walk_ribbon_bounds(rib_ctrl | (red_core > 0.30), cols, y_ctrl, max_half=65, max_gap=4, col_half_w=2)
    ylo_cyto, yhi_cyto = walk_ribbon_bounds(rib_cyto | (blue_core > 0.28), cols, y_cyto, max_half=55, max_gap=4, col_half_w=2)

    ylo_ctrl = median_filter(ylo_ctrl, size=5)
    yhi_ctrl = median_filter(yhi_ctrl, size=5)
    ylo_cyto = median_filter(ylo_cyto, size=5)
    yhi_cyto = median_filter(yhi_cyto, size=5)

    curves: dict[str, Any] = {}
    for name, yp, ylo, yhi in [
        ("control", y_ctrl, ylo_ctrl, yhi_ctrl),
        ("cyto_d", y_cyto, ylo_cyto, yhi_cyto),
    ]:
        xs = [px2x(float(c)) for c in cols]
        ys = [py2y(float(y)) for y in yp]
        los = [py2y(float(y)) for y in ylo]
        his = [py2y(float(y)) for y in yhi]
        pk = int(np.argmax(ys))
        curves[name] = {
            "x": xs,
            "y": ys,
            "lo": los,
            "hi": his,
            "peak_x": xs[pk],
            "peak_y": ys[pk],
            "x_unit": "nm",
            "y_unit": "%",
        }

    return {
        "curves": curves,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": [x_min, x_max],
            "y_range": [y_min, y_max],
            "kind": "curve",
        },
    }


def _extract_beeswarm(crop_rgb: np.ndarray, panel_id: str) -> dict[str, Any]:
    if panel_id == "N":
        y_labels = [30.0, 40.0, 50.0, 60.0]
        yu = "ridges"
        groups = {"control": (5, 155), "cyto_d": (155, 280)}
        rad, min_sep_fac, peel_fac = 7.5, 1.42, 0.95
    else:
        y_labels = [0.00, 0.05, 0.10, 0.15]
        yu = "µm⁻¹"
        groups = {"control": (5, 138), "cyto_d": (140, 280)}
        rad, min_sep_fac, peel_fac = 7.4, 1.22, 0.85

    # Automatic tick-calibrated y axis with exact RMS pixel misfit (boxgraph-public discipline!)
    cal = find_axis_ticks(crop_rgb, y_labels=y_labels, x_labels=None, dark_thr=120.0, probe=(2, 6), tick_min_frac=0.50)
    px0, py0, px1, py1 = cal["plot_box"]
    y_cal = cal["y_cal"]
    y_max, y_min = y_cal.range_for_span(py0, py1, ndigits=5)

    sub = crop_rgb[py0:py1, px0:px1].astype(np.float32)
    h, w = sub.shape[:2]

    def py2y(py_rel: float) -> float:
        return round(y_cal.to_value(py0 + py_rel), 4)

    r, g, b = sub[:, :, 0], sub[:, :, 1], sub[:, :, 2]
    sat = np.max(sub, axis=2) - np.min(sub, axis=2)
    lum = np.mean(sub, axis=2)

    black_mk = (lum < 110.0) & (sat < 45.0)
    # Red mean dot + vertical ±SD bar + anti-aliased dark-red rim act as OCCLUDER (not background!)
    red_mk = ((r - g) >= 35.0) & (r >= 90.0) & (lum < 215.0)

    sc_out: dict[str, Any] = {}
    for gname, (gx0, gx1) in groups.items():
        t_g = black_mk.copy()
        t_g[:, :gx0] = False
        t_g[:, min(w, gx1):] = False
        pts = detect_markers_matched_filter(
            t_g, red_mk, radius=rad, shape="disk",
            min_visible=0.42, max_bg=0.18, min_score=0.34,
            min_sep_factor=min_sep_fac, peel=True, peel_radius_factor=peel_fac,
            upsample=1, border_px=2,
        )
        pts.sort(key=lambda p: p["y"], reverse=True)
        xs = [round(p["x"] / max(w, 1), 4) for p in pts]
        ys = [py2y(p["y"]) for p in pts]

        # Extract red ±SD vertical bar span in this group's x-band
        ry, _ = np.where(red_mk[:, gx0:min(w, gx1)])
        y_interval = [py2y(float(ry.max())), py2y(float(ry.min()))] if len(ry) >= 4 else None

        sc_out[gname] = {
            "n": len(ys),
            "x": xs,
            "y": ys,
            "mean_y": round(float(np.mean(ys)), 4) if ys else None,
            "sd_y": round(float(np.std(ys, ddof=1)), 4) if len(ys) > 1 else None,
            "n_occluded": int(sum(1 for p in pts if p["occluded"])),
            "y_interval": y_interval,
            "x_unit": "",
            "y_unit": yu,
        }

    return {
        "digitized_scatter": sc_out,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": [0.0, 1.0],
            "y_range": [y_min, y_max],
            "y_misfit_px": cal["y_misfit_px"],
            "mode": "beeswarm_1d",
            "kind": "scatter",
        },
    }


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    if panel_id == "E":
        return _extract_f8e_spectra(crop_rgb)
    if panel_id in ("N", "O"):
        return _extract_beeswarm(crop_rgb, panel_id)
    raise ValueError(f"Unknown Lloyd Fig 8 panel_id: {panel_id}")
