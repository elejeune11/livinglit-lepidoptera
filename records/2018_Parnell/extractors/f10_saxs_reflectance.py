"""Bespoke extractor for Parnell et al. (2018) Figure 10 (rsif20170948-g10.jpg):
SAXS ridge spacing (nm, mean ± SD) vs maximum reflectance (%, mean ± SD) across all 7 Heliconius taxa.

Uses `find_axis_ticks` for exact tick-mark calibration, `detect_markers_matched_filter` per
species color channel to locate each hollow circular marker center, and `trace_error_arms_occluded`
to walk bidirectional horizontal (±SD SAXS ridge spacing) and vertical (±SD reflectance) error bars.
"""
from __future__ import annotations

from typing import Any
import numpy as np

from livinglit_lepidoptera.extract_lib import (
    detect_markers_matched_filter,
    find_axis_ticks,
    ray_dist_alpha,
    trace_error_arms_occluded,
)


# 7 Heliconius taxa with distinct RGB color signatures in Fig 10
_TAXA_SPEC = [
    # (name, rgb, perp_thr, min_alpha, search_x_nm, search_y_pct)
    ("H_sara",            (150, 32, 212),  48.0, 0.28, (700, 800),  (20, 42)),
    ("H_erato_cyrbia",    (10, 15, 215),   52.0, 0.30, (770, 860),  (10, 30)),
    ("H_eleuchia",        (10, 125, 10),   50.0, 0.28, (820, 960),  (8, 22)),
    ("H_melpomene_cythera", (8, 8, 120),   45.0, 0.35, (780, 860),  (2, 12)),
    ("H_cydno",           (148, 245, 142), 55.0, 0.25, (870, 990),  (0, 8)),
    ("H_melpomene_rosina",(242, 188, 196), 42.0, 0.28, (945, 1110), (0, 6)),
    ("H_erato_demophoon", (232, 10, 12),   50.0, 0.30, (1010, 1115),(0, 6)),
]


def extract(crop_rgb: np.ndarray, panel_id: str = "A", **_: Any) -> dict[str, Any]:
    ax = find_axis_ticks(
        crop_rgb,
        y_labels=[0.0, 10.0, 20.0, 30.0, 40.0],
        x_labels=[700.0, 800.0, 900.0, 1000.0, 1100.0],
        probe=(2, 7),
        tick_min_frac=0.50,
    )
    px0, py0, px1, py1 = ax["plot_box"]
    x_cal, y_cal = ax["x_cal"], ax["y_cal"]
    xr = list(x_cal.range_for_span(px0, px1, ndigits=3))
    yr = list(y_cal.range_for_span(py1, py0, ndigits=3))

    sub = crop_rgb[py0:py1, px0:px1].astype(np.float32).copy()
    h, w = sub.shape[:2]

    # Mask top-right legend box
    leg_mask = np.zeros((h, w), dtype=bool)
    leg_mask[:235, 290:] = True

    # Precompute ink masks per taxon so every other taxon acts as occluder for error-bar walking
    masks: dict[str, np.ndarray] = {}
    for name, rgb, perp_thr, min_a, _, _ in _TAXA_SPEC:
        perp, alpha = ray_dist_alpha(sub, rgb)
        sat = sub.max(axis=2) - sub.min(axis=2)
        if name == "H_melpomene_cythera":
            # Navy blue: distinct from royal blue by lower B (<165) and darkness
            m = (perp <= perp_thr) & (alpha >= min_a) & (sub[:, :, 2] > sub[:, :, 0] + 25) & (sub[:, :, 2] < 175) & (~leg_mask)
        elif name == "H_erato_cyrbia":
            # Royal blue: high B (>140), low R, low G
            m = (perp <= perp_thr) & (alpha >= min_a) & (sub[:, :, 2] > sub[:, :, 0] + 55) & (sub[:, :, 2] > 140) & (~leg_mask)
        elif name == "H_melpomene_rosina":
            # Soft pink: R > G+12, R > B+5, high brightness, distinct from bright red (G < 130)
            m = (perp <= perp_thr) & (alpha >= min_a) & (sub[:, :, 0] > sub[:, :, 1] + 10) & (sub[:, :, 1] > 125) & (sub[:, :, 2] > 130) & (~leg_mask)
        elif name == "H_erato_demophoon":
            # Bright red: R > G+70 and R > B+70
            m = (perp <= perp_thr) & (alpha >= min_a) & (sub[:, :, 0] > sub[:, :, 1] + 65) & (sub[:, :, 0] > sub[:, :, 2] + 65) & (~leg_mask)
        elif name == "H_cydno":
            # Pale mint green: G > R+20 and R > 95
            m = (perp <= perp_thr) & (alpha >= min_a) & (sub[:, :, 1] > sub[:, :, 0] + 18) & (sub[:, :, 0] > 85) & (~leg_mask)
        elif name == "H_eleuchia":
            # Dark forest green: G > R+30 and R < 110
            m = (perp <= perp_thr) & (alpha >= min_a) & (sub[:, :, 1] > sub[:, :, 0] + 30) & (sub[:, :, 0] < 110) & (~leg_mask)
        else:
            # H. sara purple: R & B both high, G low
            m = (perp <= perp_thr) & (alpha >= min_a) & (sat >= 30.0) & (~leg_mask)
        masks[name] = m

    scatter: dict[str, Any] = {}
    for name, _, _, _, (sx0, sx1), (sy0, sy1) in _TAXA_SPEC:
        m = masks[name]
        occ = np.zeros((h, w), dtype=bool)
        for oname, om in masks.items():
            if oname != name:
                occ |= om

        # Search window in local crop coordinates
        c0 = max(0, int(round(x_cal.to_pixel(sx0) - px0)))
        c1 = min(w, int(round(x_cal.to_pixel(sx1) - px0)))
        r0 = max(0, int(round(y_cal.to_pixel(sy1) - py0)))
        r1 = min(h, int(round(y_cal.to_pixel(sy0) - py0)))

        # Find marker center using matched filter on a filled-disk-like neighborhood (marker diameter ~9px)
        roi_t = m[r0:r1, c0:c1]
        roi_o = occ[r0:r1, c0:c1]
        hits = detect_markers_matched_filter(
            roi_t,
            occ=roi_o,
            radius=4.0,
            shape="disk",
            min_visible=0.25,
            max_bg=0.45,
            min_score=0.05,
            min_sep_factor=2.0,
            max_markers=5,
            upsample=2,
        )
        if hits:
            # Prefer marker lying near the intersection of horizontal and vertical error arms
            best_h = max(hits, key=lambda d: d["t_frac"] * 2.0 + d["score"])
            cx = c0 + best_h["x"]
            cy = r0 + best_h["y"]
        else:
            ys_m, xs_m = np.where(roi_t)
            cx = c0 + float(np.median(xs_m))
            cy = r0 + float(np.median(ys_m))

        # Walk bidirectional horizontal & vertical ±SD error arms across occluders
        xl, xr_px, yb, yt, hidden = trace_error_arms_occluded(
            m, occ, cx, cy, max_len=140, max_gap=4, band_half=3, marker_r=4.5
        )
        # Refine marker center to midpoint of symmetric error arms when both ends are visible
        if not hidden["x_lo_hidden"] and not hidden["x_hi_hidden"] and (xr_px - xl) > 12:
            cx = 0.5 * (xl + xr_px)
        if not hidden["y_lo_hidden"] and not hidden["y_hi_hidden"] and (yb - yt) > 12:
            cy = 0.5 * (yt + yb)

        xv = round(float(x_cal.to_value(px0 + cx)), 1)
        yv = round(float(y_cal.to_value(py0 + cy)), 2)
        x_lo = round(float(x_cal.to_value(px0 + xl)), 1)
        x_hi = round(float(x_cal.to_value(px0 + xr_px)), 1)
        y_lo = round(float(y_cal.to_value(py0 + yb)), 2)
        y_hi = round(float(y_cal.to_value(py0 + yt)), 2)

        scatter[name] = {
            "x": [xv],
            "y": [yv],
            "x_lo": [x_lo],
            "x_hi": [x_hi],
            "y_lo": [y_lo],
            "y_hi": [y_hi],
            "x_sd": round(0.5 * (x_hi - x_lo), 1),
            "y_sd": round(0.5 * (y_hi - y_lo), 2),
            "x_unit": "nm",
            "y_unit": "%",
        }

    return {
        "digitized_scatter": scatter,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": xr,
            "y_range": yr,
            "x_misfit_px": ax["x_misfit_px"],
            "y_misfit_px": ax["y_misfit_px"],
            "kind": "scatter",
        },
        "extracted_data": {
            "x_tick_misfit_px": ax["x_misfit_px"],
            "y_tick_misfit_px": ax["y_misfit_px"],
            "n_taxa": len(scatter),
        },
    }
