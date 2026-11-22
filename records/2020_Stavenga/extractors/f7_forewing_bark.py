"""Bespoke extractor for Stavenga et al. (2020) Figure 7 (fphys-11-00095-g007.jpg):
- Reflectance spectra of various regions on the dorsal forewings of Bogong moths (7 bold curves:
  red, green, black_upper, maroon, yellow, blue, black_lower) overlaid against thin gray
  reflectance spectra of likely resting-spot tree bark (Table 1; lower & upper gray bounds).
"""
from __future__ import annotations

from typing import Any
import numpy as np

from livinglit_lepidoptera.extract_lib import (
    find_axis_ticks,
    ray_dist_alpha,
    viterbi_track,
)


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    ax = find_axis_ticks(
        crop_rgb,
        y_labels=[0.0, 0.2, 0.4, 0.6],
        x_labels=[300.0, 400.0, 500.0, 600.0, 700.0, 800.0],
        dark_thr=215.0,
        max_sat=256.0,
        min_spine_frac=0.55,
        probe=(2, 7),
    )
    x_cal, y_cal = ax["x_cal"], ax["y_cal"]
    px0 = int(round(x_cal.to_pixel(300.0)))
    px1 = int(round(x_cal.to_pixel(800.0)))
    py0 = int(round(y_cal.to_pixel(0.6)))
    py1 = int(round(y_cal.to_pixel(0.0)))
    plot_box = (px0, py0, px1, py1)

    sub_f = crop_rgb[py0:py1, px0:px1].astype(np.float32)
    h, w = sub_f.shape[:2]
    pix_sat = np.max(sub_f, axis=2) - np.min(sub_f, axis=2)
    lum = sub_f.mean(axis=2)

    # 5 chromatic bold forewing curves + 2 bold black forewing curves (upper & lower)
    chrom_traces = [
        ("forewing_1_red",    (232, 16, 14)),
        ("forewing_2_green",  (16, 122, 16)),
        ("forewing_4_maroon", (118, 10, 10)),
        ("forewing_5_yellow", (248, 248, 30)),
        ("forewing_6_blue",   (8, 6, 142)),
    ]
    perps, alphas = {}, {}
    for name, rgb in chrom_traces:
        perps[name], alphas[name] = ray_dist_alpha(sub_f, rgb)

    n_cols = 126
    x_cols = np.linspace(2, w - 3, n_cols).astype(int)
    empty_cost = 120.0
    curves: dict[str, Any] = {}
    tracked_y: dict[str, np.ndarray] = {}

    # 1. Track chromatic bold forewing curves (red, green, yellow, blue first; then maroon with red-halo excluded!)
    first_chrom = ["forewing_1_red", "forewing_2_green", "forewing_5_yellow", "forewing_6_blue"]
    for name in first_chrom:
        p_map, a_map = perps[name], alphas[name]
        if name == "forewing_1_red":
            valid_px = (p_map <= 38.0) & (a_map >= 0.45) & (sub_f[:, :, 0] > 165.0) & (sub_f[:, :, 1] < 85.0)
        elif name == "forewing_5_yellow":
            valid_px = (p_map <= 42.0) & (a_map >= 0.35) & (pix_sat >= 55.0) & (sub_f[:, :, 0] > 190.0) & (sub_f[:, :, 1] > 190.0)
        else:
            valid_px = (p_map <= 36.0) & (a_map >= 0.40) & (pix_sat >= 35.0)

        cost_px = np.where(valid_px, 0.8 * p_map + 34.0 * (1.15 - np.clip(a_map, 0.0, 1.15)), empty_cost)
        for oname in first_chrom:
            if oname == name:
                continue
            stolen = (perps[oname] + 4.0 < p_map) & (alphas[oname] >= 0.35)
            cost_px = np.where(stolen, empty_cost, cost_px)

        cost = np.full((h, n_cols), empty_cost, dtype=np.float64)
        for ti, cx in enumerate(x_cols):
            cost[:, ti] = cost_px[:, max(0, cx - 2):min(w, cx + 3)].min(axis=1)

        tracked_y[name] = viterbi_track(cost, max_step=24, smooth_w=0.25, norm="l1")

    # Track forewing_4_maroon: always strictly below forewing_1_red (exclude red + 10px halo & upper black)
    p_m, a_m = perps["forewing_4_maroon"], alphas["forewing_4_maroon"]
    valid_m = (p_m <= 36.0) & (a_m >= 0.45) & (sub_f[:, :, 0] < 155.0) & (sub_f[:, :, 0] > 70.0) & (sub_f[:, :, 1] < 55.0)
    cost_m_px = np.where(valid_m, 0.8 * p_m + 34.0 * (1.15 - np.clip(a_m, 0.0, 1.15)), empty_cost)
    cost_m = np.full((h, n_cols), empty_cost, dtype=np.float64)
    for ti, cx in enumerate(x_cols):
        col_c = cost_m_px[:, max(0, cx - 2):min(w, cx + 3)].min(axis=1).copy()
        # Exclude red curve & upper black curve region (strictly below forewing_2_green at all wavelengths!)
        y_ceil = int(tracked_y["forewing_2_green"][ti]) + 2
        col_c[:min(h - 1, y_ceil)] = empty_cost
        # Where maroon is occluded under yellow/blue (<440 nm), provide soft guide near yellow/blue band
        wl = x_cal.to_value(px0 + cx)
        if wl < 445.0 and np.min(col_c) >= empty_cost - 1.0:
            y_guide = int(round(0.5 * (tracked_y["forewing_5_yellow"][ti] + tracked_y["forewing_6_blue"][ti])))
            ys = np.arange(h)
            col_c = np.minimum(col_c, 35.0 + 1.5 * np.abs(ys - y_guide))
        cost_m[:, ti] = col_c
    tracked_y["forewing_4_maroon"] = viterbi_track(cost_m, max_step=22, smooth_w=0.28, norm="l1")

    # 2. Track the 2 bold black forewing curves (strictly pure black: lum < 55 & sat < 26)
    black_px = (lum < 55.0) & (pix_sat < 26.0)
    cost_blk_px = np.where(black_px, lum * 0.6 + pix_sat * 0.8, empty_cost)

    c_blk_hi = np.full((h, n_cols), empty_cost, dtype=np.float64)
    c_blk_lo = np.full((h, n_cols), empty_cost, dtype=np.float64)
    for ti, cx in enumerate(x_cols):
        col_c = cost_blk_px[:, max(0, cx - 2):min(w, cx + 3)].min(axis=1)
        y_sep = int(min(tracked_y["forewing_4_maroon"][ti], tracked_y["forewing_5_yellow"][ti]))
        c_hi = col_c.copy()
        c_hi[min(h - 1, y_sep):] = empty_cost
        c_lo = col_c.copy()
        y_b = int(tracked_y["forewing_6_blue"][ti])
        c_lo[:max(0, y_b - 1)] = empty_cost
        # Above ~710 nm, forewing_6_blue is drawn directly on top of forewing_7_black_lower;
        # when pure black pixels are occluded by blue, follow the lower edge of the blue trace!
        if x_cal.to_value(px0 + cx) > 700.0 and np.min(c_lo) >= empty_cost - 1.0:
            ys = np.arange(h)
            c_lo = np.minimum(c_lo, 28.0 + 2.0 * np.abs(ys - min(h - 1, y_b + 1)))
        c_blk_hi[:, ti] = c_hi
        c_blk_lo[:, ti] = c_lo

    tracked_y["forewing_3_black_upper"] = viterbi_track(c_blk_hi, max_step=20, smooth_w=0.30, norm="l1")
    tracked_y["forewing_7_black_lower"] = viterbi_track(c_blk_lo, max_step=20, smooth_w=0.30, norm="l1")

    order = [
        "forewing_1_red",
        "forewing_2_green",
        "forewing_3_black_upper",
        "forewing_4_maroon",
        "forewing_5_yellow",
        "forewing_6_blue",
        "forewing_7_black_lower",
    ]
    for name in order:
        yp = tracked_y[name]
        xs_out = [round(x_cal.to_value(px0 + cx), 2) for cx in x_cols]
        ys_out = [round(y_cal.to_value(py0 + py), 4) for py in yp]
        curves[name] = {
            "x": xs_out,
            "y": ys_out,
            "peak_x": xs_out[int(np.argmax(ys_out))],
            "peak_y": max(ys_out),
            "x_unit": "nm",
            "y_unit": "reflectance",
        }

    x_range = [round(x_cal.to_value(px0), 4), round(x_cal.to_value(px1), 4)]
    y_range = [round(y_cal.to_value(py1), 4), round(y_cal.to_value(py0), 4)]
    return {
        "curves": curves,
        "overlay_meta": {
            "plot_box": list(plot_box),
            "x_range": x_range,
            "y_range": y_range,
            "x_misfit_px": ax["x_misfit_px"],
            "y_misfit_px": ax["y_misfit_px"],
            "kind": "curves",
        },
    }
