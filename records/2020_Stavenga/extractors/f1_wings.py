"""Bespoke extractor for Stavenga et al. (2020) Figure 1B (fphys-11-00095-g001.jpg):
- Dorsal hindwing (olive green, exits y=0.3 ceiling near ~703 nm) and dorsal forewing
  (dark maroon) reflectance spectra measured with a bifurcated reflection probe (300–800 nm).
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
        y_labels=[0.0, 0.1, 0.2, 0.3],
        x_labels=[300.0, 400.0, 500.0, 600.0, 700.0, 800.0],
        dark_thr=215.0,
        max_sat=256.0,
        min_spine_frac=0.55,
        probe=(2, 7),
    )
    px0, py0, px1, py1 = ax["plot_box"]
    x_cal, y_cal = ax["x_cal"], ax["y_cal"]
    # Expand plot_box slightly onto the calibrated tick span so 300..800 nm & 0.0..0.3 are covered cleanly
    px0 = int(round(x_cal.to_pixel(300.0)))
    px1 = int(round(x_cal.to_pixel(800.0)))
    py0 = int(round(y_cal.to_pixel(0.3)))
    py1 = int(round(y_cal.to_pixel(0.0)))
    plot_box = (px0, py0, px1, py1)

    sub = crop_rgb[py0:py1, px0:px1].copy()
    # Mask legend box ("hind wing" / "fore wing") in upper-left
    sub[35:110, 40:265, :] = 255
    sub_f = sub.astype(np.float32)
    h, w = sub_f.shape[:2]
    pix_sat = np.max(sub_f, axis=2) - np.min(sub_f, axis=2)

    traces = [
        ("dorsal_hindwing", (128, 130, 35), True),
        ("dorsal_forewing", (120, 12, 14),  False),
    ]
    perps, alphas = {}, {}
    for name, rgb, _ in traces:
        perps[name], alphas[name] = ray_dist_alpha(sub_f, rgb)

    n_cols = 126
    x_cols = np.linspace(2, w - 3, n_cols).astype(int)
    empty_cost = 120.0
    curves: dict[str, Any] = {}

    for name, rgb, clips_top in traces:
        p_map, a_map = perps[name], alphas[name]
        valid_px = (p_map <= 38.0) & (a_map >= 0.30) & (pix_sat >= 22.0)
        cost_px = np.where(valid_px, 0.8 * p_map + 36.0 * (1.15 - np.clip(a_map, 0.0, 1.15)), empty_cost)
        for oname, _, _ in traces:
            if oname == name:
                continue
            stolen = (perps[oname] + 4.0 < p_map) & (alphas[oname] >= 0.30)
            cost_px = np.where(stolen, empty_cost, cost_px)

        cost = np.full((h, n_cols), empty_cost, dtype=np.float64)
        valid_col = np.zeros(n_cols, dtype=bool)
        for ti, cx in enumerate(x_cols):
            col_c = cost_px[:, max(0, cx - 2):min(w, cx + 3)].min(axis=1)
            if np.any(col_c < 45.0):
                valid_col[ti] = True
            cost[:, ti] = col_c

        if clips_top:
            # Find last valid column where the rising hindwing trace reaches the top frame (y = 0.3)
            last_ti = int(np.max(np.where(valid_col)[0])) if np.any(valid_col) else n_cols - 1
            cost_use = cost[:, :last_ti + 1]
            x_use = x_cols[:last_ti + 1]
        else:
            cost_use = cost
            x_use = x_cols

        y_path = viterbi_track(cost_use, max_step=28, smooth_w=0.25, norm="l1")
        xs_out = [round(x_cal.to_value(px0 + cx), 2) for cx in x_use]
        ys_out = [round(y_cal.to_value(py0 + py), 4) for py in y_path]

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
