"""Bespoke extractor for Stavenga et al. (2020) Figure 6 (fphys-11-00095-g006.jpg):
- Reflectance spectra of aestivation cave granite (green, algal hump near ~560 nm + chlorophyll
  red-edge rise >680 nm) vs Argyle apple (Eucalyptus cinerea) bark (dark maroon, monotonic brown).
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
    x_cal, y_cal = ax["x_cal"], ax["y_cal"]
    px0 = int(round(x_cal.to_pixel(300.0)))
    px1 = int(round(x_cal.to_pixel(800.0)))
    # Top of plot spine extends above 0.3 up to ~0.35 (y_px = 2) because curves exceed 0.3 near 800 nm!
    py0 = int(ax["plot_box"][1])
    py1 = int(round(y_cal.to_pixel(0.0)))
    plot_box = (px0, py0, px1, py1)

    sub = crop_rgb[py0:py1, px0:px1].copy()
    # Mask legend ("granite" / "E. cinerea") in upper-center
    sub[65:145, 145:375, :] = 255
    sub_f = sub.astype(np.float32)
    h, w = sub_f.shape[:2]
    pix_sat = np.max(sub_f, axis=2) - np.min(sub_f, axis=2)

    traces = [
        ("cave_granite",            (15, 125, 18)),
        ("eucalyptus_cinerea_bark", (122, 12, 14)),
    ]
    perps, alphas = {}, {}
    for name, rgb in traces:
        perps[name], alphas[name] = ray_dist_alpha(sub_f, rgb)

    n_cols = 126
    x_cols = np.linspace(2, w - 3, n_cols).astype(int)
    empty_cost = 120.0
    curves: dict[str, Any] = {}

    for name, rgb in traces:
        p_map, a_map = perps[name], alphas[name]
        valid_px = (p_map <= 38.0) & (a_map >= 0.30) & (pix_sat >= 24.0)
        cost_px = np.where(valid_px, 0.8 * p_map + 34.0 * (1.15 - np.clip(a_map, 0.0, 1.15)), empty_cost)
        for oname, _ in traces:
            if oname == name:
                continue
            stolen = (perps[oname] + 4.0 < p_map) & (alphas[oname] >= 0.30)
            cost_px = np.where(stolen, empty_cost, cost_px)

        cost = np.full((h, n_cols), empty_cost, dtype=np.float64)
        for ti, cx in enumerate(x_cols):
            cost[:, ti] = cost_px[:, max(0, cx - 2):min(w, cx + 3)].min(axis=1)

        y_path = viterbi_track(cost, max_step=40, smooth_w=0.22, norm="l1")
        xs_out = [round(x_cal.to_value(px0 + cx), 2) for cx in x_cols]
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
