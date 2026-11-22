"""Bespoke extractor for Finet et al. (2026) Figure 5C', 5D', 5C'', 5D'' (gr5.jpg):
- C_prime  (5C'): Morpho didius full-ridge FIB milling measured spectra (4 curves + ±SD ribbons)
- D_prime  (5D'): Morpho didius lamellae FIB milling measured spectra (4 curves + ±SD ribbons)
- C_dprime (5C''): Morpho didius full-ridge FDTD simulations (6 crossing curves)
- D_dprime (5D''): Morpho didius lamellae FDTD simulations (6 crossing curves)

Computes per-pixel ray-cost likelihood BEFORE horizontal column pooling (preventing white-edge
perp=0 pixels from pairing with adjacent curves' high alpha!), then tracks every crossing curve
cleanly with L1 Viterbi dynamic programming and continuous ribbon walking.
"""
from __future__ import annotations

from typing import Any
import numpy as np

from livinglit_lepidoptera.extract_lib import (
    lin_range,
    ray_dist_alpha,
    viterbi_track,
    walk_ribbon_bounds,
)


_CONFIGS: dict[str, dict[str, Any]] = {
    "C_prime": {
        "plot_box": (198, 74, 1388, 948),
        "x_range": lin_range(198, 1388, 226.5, 350.0, 1390.5, 700.0),
        "y_range": (
            lin_range(2004, 2878, 2000.0, 80.0, 2882.0, 0.0)[1],
            lin_range(2004, 2878, 2000.0, 80.0, 2882.0, 0.0)[0],
        ),
        "exclude": [(620, 0, 1190, 390)],
        "ribbons": True,
        "traces": [
            ("control_unmilled", (68, 178, 232),  None, 0.24),
            ("z_100nm",          (110, 118, 188), None, 0.26),
            ("z_500nm",          (138, 112, 166), None, 0.26),
            ("z_800nm",          (140, 90, 82),   None, 0.28),
        ],
    },
    "D_prime": {
        "plot_box": (223, 75, 1414, 949),
        "x_range": lin_range(1683, 2874, 1712.5, 350.0, 2876.5, 700.0),
        "y_range": (
            lin_range(2005, 2879, 2000.5, 80.0, 2883.5, 0.0)[1],
            lin_range(2005, 2879, 2000.5, 80.0, 2883.5, 0.0)[0],
        ),
        "exclude": [(620, 0, 1190, 390)],
        "ribbons": True,
        "traces": [
            ("control_unmilled", (56, 195, 234),  [(440.0, 76.5)], 0.24),
            ("z_500nm",          (101, 137, 197), [(438.0, 58.0)], 0.30),
            ("z_1000nm",         (120, 140, 198), [(438.0, 36.0)], 0.25),
            ("z_1300nm",         (79, 92, 124),   [(445.0, 11.0)], 0.28),
        ],
    },
    "C_dprime": {
        "plot_box": (195, 61, 1385, 932),
        "x_range": lin_range(195, 1385, 224.5, 350.0, 1386.5, 700.0),
        "y_range": (
            lin_range(3101, 3972, 3096.5, 60.0, 3977.0, 0.0)[1],
            lin_range(3101, 3972, 3096.5, 60.0, 3977.0, 0.0)[0],
        ),
        "exclude": [(620, 0, 1190, 505)],
        "ribbons": False,
        "traces": [
            ("control_unmilled", (12, 12, 14),    None, 0.42),
            ("z_100nm",          (238, 32, 34),   None, 0.28),
            ("z_300nm",          (51, 82, 164),   None, 0.28),
            ("z_500nm",          (8, 130, 131),   None, 0.28),
            ("z_800nm",          (185, 84, 162),  None, 0.28),
            ("z_1000nm",         (128, 131, 52),  None, 0.28),
        ],
    },
    "D_dprime": {
        "plot_box": (230, 61, 1410, 935),
        "x_range": lin_range(1690, 2870, 1717.5, 350.0, 2871.5, 700.0),
        "y_range": (
            lin_range(3101, 3975, 3096.5, 60.0, 3979.5, 0.0)[1],
            lin_range(3101, 3975, 3096.5, 60.0, 3979.5, 0.0)[0],
        ),
        "exclude": [(620, 0, 1180, 505)],
        "ribbons": False,
        "traces": [
            ("control_unmilled", (12, 12, 14),    None, 0.42),
            ("z_300nm",          (237, 33, 34),   None, 0.28),
            ("z_500nm",          (51, 83, 166),   None, 0.28),
            ("z_700nm",          (10, 130, 128),  None, 0.28),
            ("z_1000nm",         (181, 87, 161),  None, 0.28),
            ("z_1300nm",         (129, 130, 54),  None, 0.28),
        ],
    },
}


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    cfg = _CONFIGS[panel_id]
    px0, py0, px1, py1 = cfg["plot_box"]
    sub = crop_rgb[py0:py1, px0:px1].copy()
    for ex0, ey0, ex1, ey1 in cfg["exclude"]:
        sub[ey0:ey1, ex0:ex1, :] = 255
    sub_f = sub.astype(np.float32)
    h, w = sub_f.shape[:2]
    x_min, x_max = cfg["x_range"]
    y_min, y_max = cfg["y_range"]

    n_cols = 150
    x_cols = np.linspace(4, w - 5, n_cols).astype(int)
    perps, alphas = {}, {}
    for name, rgb, _, _ in cfg["traces"]:
        perps[name], alphas[name] = ray_dist_alpha(sub_f, rgb)

    curves: dict[str, Any] = {}
    pix_sat = np.max(sub_f, axis=2) - np.min(sub_f, axis=2)
    empty_cost = 120.0

    for name, rgb, anchors, min_a in cfg["traces"]:
        p_map, a_map = perps[name], alphas[name]
        t_sat = float(max(rgb) - min(rgb))
        # Per-pixel validity & competition BEFORE horizontal window pooling!
        if t_sat > 25.0:
            valid_px = (p_map <= 32.0) & (a_map >= min_a) & (pix_sat >= (10.0 if cfg["ribbons"] else 16.0))
        else:
            valid_px = (p_map <= 24.0) & (a_map >= 0.45) & (pix_sat < 26.0)
        cost_px = np.where(valid_px, 0.75 * p_map + 34.0 * (1.15 - np.clip(a_map, 0.0, 1.15)), empty_cost)

        for oname, orgb, _, _ in cfg["traces"]:
            if oname == name:
                continue
            if np.linalg.norm(np.array(rgb) - np.array(orgb)) > 26.0:
                stolen_px = (perps[oname] + 4.0 < p_map) & (alphas[oname] >= 0.30)
                cost_px = np.where(stolen_px, empty_cost, cost_px)

        cost = np.full((h, n_cols), empty_cost, dtype=np.float64)
        for ti, cx in enumerate(x_cols):
            cost[:, ti] = cost_px[:, max(0, cx - 2):min(w, cx + 3)].min(axis=1)

        if anchors:
            for ax_nm, ay_pct in anchors:
                t_a = int(np.argmin(np.abs(x_min + (x_cols / max(w, 1)) * (x_max - x_min) - ax_nm)))
                y_a = int(round((y_max - ay_pct) / max(y_max - y_min, 1e-9) * h))
                ys = np.arange(h)
                cost[:, t_a] += np.where(np.abs(ys - y_a) > 22, 350.0, 0.3 * np.abs(ys - y_a))

        if panel_id == "D_prime" and name == "z_500nm":
            for ti, cx in enumerate(x_cols):
                wl = x_min + (cx / max(w, 1)) * (x_max - x_min)
                if 385.0 <= wl <= 465.0:
                    y_cut = int(round((y_max - 42.0) / (y_max - y_min) * h))
                    cost[y_cut:, ti] += 220.0
        elif panel_id == "D_prime" and name == "z_1000nm":
            for ti, cx in enumerate(x_cols):
                wl = x_min + (cx / max(w, 1)) * (x_max - x_min)
                if 380.0 <= wl <= 485.0:
                    y_cut = int(round((y_max - 43.0) / (y_max - y_min) * h))
                    cost[:y_cut, ti] += 220.0

        y_path = viterbi_track(cost, max_step=55, smooth_w=0.22, norm="l1")
        xs_out = [round(x_min + (cx / max(w, 1)) * (x_max - x_min), 2) for cx in x_cols]
        ys_out = [round(y_max - (py / max(h, 1)) * (y_max - y_min), 3) for py in y_path]

        c_entry: dict[str, Any] = {
            "x": xs_out,
            "y": ys_out,
            "peak_x": xs_out[int(np.argmax(ys_out))],
            "peak_y": max(ys_out),
            "x_unit": "nm",
            "y_unit": "%",
        }
        if cfg["ribbons"]:
            rib_mask = (p_map <= 34.0) & (a_map >= 0.08) & (pix_sat >= 8.0)
            y_lo_px, y_hi_px = walk_ribbon_bounds(rib_mask, x_cols, y_path, max_half=95, max_gap=5)
            c_entry["lo"] = [round(y_max - (py / max(h, 1)) * (y_max - y_min), 3) for py in y_lo_px]
            c_entry["hi"] = [round(y_max - (py / max(h, 1)) * (y_max - y_min), 3) for py in y_hi_px]
        curves[name] = c_entry

    return {
        "curves": curves,
        "overlay_meta": {
            "plot_box": list(cfg["plot_box"]),
            "x_range": list(cfg["x_range"]),
            "y_range": list(cfg["y_range"]),
            "kind": "curves",
        },
    }
