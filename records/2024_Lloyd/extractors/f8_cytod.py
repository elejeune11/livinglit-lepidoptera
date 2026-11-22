"""Bespoke extractor for Lloyd et al. (2024) Figure 8E, 8N, 8O (41467_2024_48060_Fig8_HTML.jpg):
- F8/E: Control (red + translucent pink ±SD ribbon) and Cyto D (blue + translucent light-blue ±SD ribbon)
  reflectance spectra across 350..700 nm using ray_dist_alpha + L1 viterbi_track + walk_ribbon_bounds.
- F8/N: Adult scale ridge number beeswarm (control vs cyto) + red mean ± SD summary bar.
- F8/O: Adult scale ridge curvature κ (µm⁻¹) beeswarm (control vs cyto) + red mean ± SD summary bar.
"""
from __future__ import annotations

from typing import Any
import numpy as np
from scipy.ndimage import distance_transform_edt, maximum_filter

from livinglit_lepidoptera.extract_lib import (
    lin_range,
    ray_dist_alpha,
    viterbi_track,
    walk_ribbon_bounds,
)


def _extract_f8e_spectra(crop_rgb: np.ndarray) -> dict[str, Any]:
    # Exact ggplot panel box inner bounds: x in [38, 281], y in [6, 235]
    px0, py0, px1, py1 = 38, 6, 281, 235
    sub = crop_rgb[py0:py1, px0:px1].astype(np.float32).copy()
    # Mask top-left legend ("Control / Cyto D")
    sub[:48, :90] = 255.0
    h, w = sub.shape[:2]

    # Calibrated from exact tick pixels:
    # y ticks: 12 -> y=8, 10 -> y=60, 8 -> y=112, 6 -> y=164, 4 -> y=216 (26.0 px per 1%)
    y_max, y_min = lin_range(0, h, 8.0, 12.0, 216.0, 4.0)
    # x span of plotted curves: 350 nm starts at cx=11, 700 nm ends at cx=232
    x_min, x_max = lin_range(0, w, 11.0, 350.0, 232.0, 700.0)

    def px2x(cx: float) -> float:
        return round(x_min + (cx / max(w, 1)) * (x_max - x_min), 3)

    def py2y(cy: float) -> float:
        return round(y_max - (cy / max(h, 1)) * (y_max - y_min), 4)

    r = sub[:, :, 0]
    g = sub[:, :, 1]
    b = sub[:, :, 2]

    # Dense columns covering exact 350..700 nm curve span
    cols = np.linspace(11, 232, 71).astype(int)

    # Color rays for Control red & Cyto D blue
    perp_r, alpha_r = ray_dist_alpha(sub, (231, 45, 40))
    perp_b, alpha_b = ray_dist_alpha(sub, (52, 128, 198))

    # Ribbon masks (include overlap purple zone where both red & blue tint white!)
    # Control pink ribbon: (250, 209, 210) -> R - G >= 16, R > 205
    rib_ctrl = ((r - g) >= 14.0) & (r >= 195.0) & (g <= 238.0)
    # Cyto D blue ribbon: (215, 229, 240) -> B - R >= 10, OR overlap purple (B - G >= 10 & R - G >= 8)
    rib_cyto = (((b - r) >= 10.0) & (b >= 195.0) & (r <= 238.0)) | (((b - g) >= 10.0) & ((r - g) >= 8.0) & (g <= 228.0))

    # Build sharp core curve cost grids for L1 Viterbi tracking
    # Red core line has strong (R - G) and (R - B)
    red_core = np.clip((r - 0.5 * (g + b)) / 140.0, 0.0, 1.2) * (perp_r < 55.0)
    cost_ctrl = np.where(red_core > 0.35, 1.2 - red_core, 2.5 + 0.03 * perp_r)
    # Penalize columns where line crosses inside blue ribbon gently (still detectable via R - G!)
    red_in_ov = ((r - g) >= 48.0) & (r >= 175.0)
    cost_ctrl = np.where(red_in_ov, np.minimum(cost_ctrl, 0.35), cost_ctrl)

    # Blue core line has strong (B - R) and lower luminance than light-blue ribbon
    blue_core = np.clip((b - r) / 95.0, 0.0, 1.2) * (perp_b < 55.0) * (r < 208.0)
    cost_cyto = np.where(blue_core > 0.32, 1.2 - blue_core, 2.5 + 0.03 * perp_b)
    blue_in_ov = ((b - g) >= 24.0) & (r < 195.0) & (b > 180.0)
    cost_cyto = np.where(blue_in_ov, np.minimum(cost_cyto, 0.45), cost_cyto)

    y_ctrl = viterbi_track(cost_ctrl[:, cols], max_step=14, smooth_w=0.18, norm="l1")
    y_cyto = viterbi_track(cost_cyto[:, cols], max_step=12, smooth_w=0.22, norm="l1")

    # Walk ±SD ribbon boundaries continuously from tracked core curves
    ylo_ctrl, yhi_ctrl = walk_ribbon_bounds(rib_ctrl | (red_core > 0.30), cols, y_ctrl, max_half=65, max_gap=4, col_half_w=2)
    ylo_cyto, yhi_cyto = walk_ribbon_bounds(rib_cyto | (blue_core > 0.28), cols, y_cyto, max_half=55, max_gap=4, col_half_w=2)

    # Smooth ribbon half-widths slightly to remove 1-px JPEG ringing at intersections
    from scipy.ndimage import median_filter
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
        px0, py0, px1, py1 = 79, 10, 355, 298
        # y ticks: 60 -> y=45, 30 -> y=273 (rel to crop y=0, so rel to py0=10: 35 and 263)
        y_max, y_min = lin_range(0, py1 - py0, 35.0, 60.0, 263.0, 30.0)
        yu = "ridges"
        groups = {"control": (5, 148), "cyto_d": (152, 275)}
        min_dist, disc_thr = 11, 4.0
    else:
        px0, py0, px1, py1 = 88, 10, 365, 298
        # y ticks: 0.15 -> y=29.5, 0.00 -> y=284 (rel to py0=10: 19.5 and 274.0)
        y_max, y_min = lin_range(0, py1 - py0, 19.5, 0.15, 274.0, 0.0)
        yu = "µm⁻¹"
        groups = {"control": (5, 135), "cyto_d": (140, 275)}
        min_dist, disc_thr = 9, 3.5

    sub = crop_rgb[py0:py1, px0:px1].astype(np.int16)
    h, w = sub.shape[:2]

    def py2y(py: float) -> float:
        return round(y_max - (py / max(h, 1)) * (y_max - y_min), 4)

    # Pure black dotplot discs (exclude red mean/SD bar!)
    sat = np.max(sub, axis=2) - np.min(sub, axis=2)
    lum = np.mean(sub, axis=2)
    black_mk = (lum < 85) & (sat < 30)
    # Red mean + SD vertical bar
    red_mk = (sub[:, :, 0] > 180) & (sub[:, :, 1] < 80) & (sub[:, :, 2] < 80)

    edt = distance_transform_edt(black_mk)
    local_max = (edt == maximum_filter(edt, size=min_dist)) & (edt >= disc_thr)
    py_all, px_all = np.where(local_max)

    sc_out: dict[str, Any] = {}
    for gname, (gx0, gx1) in groups.items():
        # Suppress close duplicates within min_dist
        cands = sorted(
            [(float(edt[y, x]), int(x), int(y)) for y, x in zip(py_all, px_all) if gx0 <= x < gx1],
            reverse=True,
        )
        kept: list[tuple[int, int]] = []
        for _, x, y in cands:
            if all((x - kx) ** 2 + (y - ky) ** 2 >= (min_dist - 1) ** 2 for kx, ky in kept):
                kept.append((x, y))
        kept.sort(key=lambda t: t[1])
        xs = [round(x / max(w, 1), 4) for x, _ in kept]
        ys = [py2y(y) for _, y in kept]

        # Also extract red ±SD vertical bar span in this group's x-band
        ry, _ = np.where(red_mk[:, gx0:gx1])
        y_interval = [py2y(float(ry.max())), py2y(float(ry.min()))] if len(ry) >= 4 else None

        sc_out[gname] = {
            "n": len(ys),
            "x": xs,
            "y": ys,
            "mean_y": round(float(np.mean(ys)), 4) if ys else None,
            "sd_y": round(float(np.std(ys, ddof=1)), 4) if len(ys) > 1 else None,
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
