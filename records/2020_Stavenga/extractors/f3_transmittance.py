"""Bespoke extractor for Stavenga et al. (2020) Figure 3 (fphys-11-00095-g003.jpg):
- Transmittance spectra of an isolated Bogong moth forewing scale immersed in oil (n = 1.515)
  measured across the root (1, red), middle (2, green), and tip (3, blue) regions (350–800 nm).
"""
from __future__ import annotations

from typing import Any
import cv2
import numpy as np

from livinglit_lepidoptera.extract_lib import (
    find_axis_ticks,
    ray_dist_alpha,
    viterbi_track,
)


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    ax = find_axis_ticks(
        crop_rgb,
        y_labels=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        x_labels=[400.0, 500.0, 600.0, 700.0, 800.0],
        dark_thr=215.0,
        max_sat=256.0,
        min_spine_frac=0.55,
        probe=(2, 7),
    )
    x_cal, y_cal = ax["x_cal"], ax["y_cal"]
    # Note: y-axis starts at 350 nm (vertical spine at x_cal(350)) and extends to 800 nm;
    # top of plot is the y=1.0 tick (not the inset scale image!)
    px0 = int(round(x_cal.to_pixel(350.0)))
    px1 = int(round(x_cal.to_pixel(800.0)))
    py0 = int(round(y_cal.to_pixel(1.0)))
    py1 = int(round(y_cal.to_pixel(0.0)))
    plot_box = (px0, py0, px1, py1)

    sub = crop_rgb[py0:py1, px0:px1].copy()
    # Mask inset transmitted-light scale micrograph (between curves 1 and 2, x_sub=20..505, y_sub=100..240)
    sub[100:242, 20:505, :] = 255
    # Mask pure-black text labels '1', '2', '3'
    lum = sub.mean(axis=2)
    sat = sub.max(axis=2).astype(int) - sub.min(axis=2).astype(int)
    black_ink = ((lum < 80) & (sat < 30)).astype(np.uint8)
    sub[cv2.dilate(black_ink, np.ones((5, 5), np.uint8)) > 0] = 255

    sub_f = sub.astype(np.float32)
    h, w = sub_f.shape[:2]
    pix_sat = np.max(sub_f, axis=2) - np.min(sub_f, axis=2)

    traces = [
        ("root_1",   (232, 18, 20)),
        ("middle_2", (20, 238, 22)),
        ("tip_3",    (12, 10, 220)),
    ]
    perps, alphas = {}, {}
    for name, rgb in traces:
        perps[name], alphas[name] = ray_dist_alpha(sub_f, rgb)

    n_cols = 115
    x_cols = np.linspace(2, w - 3, n_cols).astype(int)
    empty_cost = 120.0
    curves: dict[str, Any] = {}

    for name, rgb in traces:
        p_map, a_map = perps[name], alphas[name]
        valid_px = (p_map <= 42.0) & (a_map >= 0.30) & (pix_sat >= 35.0)
        cost_px = np.where(valid_px, 0.8 * p_map + 34.0 * (1.15 - np.clip(a_map, 0.0, 1.15)), empty_cost)
        for oname, _ in traces:
            if oname == name:
                continue
            stolen = (perps[oname] + 4.0 < p_map) & (alphas[oname] >= 0.30)
            cost_px = np.where(stolen, empty_cost, cost_px)

        cost = np.full((h, n_cols), empty_cost, dtype=np.float64)
        for ti, cx in enumerate(x_cols):
            cost[:, ti] = cost_px[:, max(0, cx - 2):min(w, cx + 3)].min(axis=1)

        y_path = viterbi_track(cost, max_step=24, smooth_w=0.25, norm="l1")
        xs_out = [round(x_cal.to_value(px0 + cx), 2) for cx in x_cols]
        ys_out = [round(y_cal.to_value(py0 + py), 4) for py in y_path]

        curves[name] = {
            "x": xs_out,
            "y": ys_out,
            "peak_x": xs_out[int(np.argmax(ys_out))],
            "peak_y": max(ys_out),
            "x_unit": "nm",
            "y_unit": "transmittance",
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
