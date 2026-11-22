"""Bespoke extractor for Finet et al. (2026) Figure 4A, 4B, 4C, 4D (gr4.jpg):
- A (4A): 39-scale scatter plot (34 species) extracting BOTH marker centers AND x/y ±SD error bars!
- B (4B): Cohort 1 (shorter ridges) — extracts BOTH individual black species scatter dots AND PGLS line + 95% CI!
- C (4C): Cohort 2 (taller ridges) — extracts BOTH individual black species scatter dots AND PGLS line + 95% CI!
- D (4D): Thin-film interference theoretical curves (i = 2 orange, i = 4 magenta, i = 6 black).
"""
from __future__ import annotations

from typing import Any
import numpy as np
from scipy.ndimage import distance_transform_edt

from livinglit_lepidoptera.extract_lib import (
    lin_range,
    ray_dist_alpha,
    trace_error_arms,
    viterbi_track,
)
from livinglit_lepidoptera.figures.source import blobs


def _nms_peaks(dist: np.ndarray, min_dist: int, thr: float) -> list[tuple[int, int]]:
    ys, xs = np.where(dist >= thr)
    if not len(ys):
        return []
    order = np.argsort(-dist[ys, xs])
    kept: list[tuple[int, int]] = []
    md2 = min_dist * min_dist
    for idx in order:
        x, y = int(xs[idx]), int(ys[idx])
        if all((x - kx) ** 2 + (y - ky) ** 2 >= md2 for kx, ky in kept):
            kept.append((x, y))
    return kept


def _extract_4a(crop_rgb: np.ndarray) -> dict[str, Any]:
    px0, py0, px1, py1 = (242, 31, 2491, 1776)
    sub = crop_rgb[py0:py1, px0:px1].astype(np.int16)
    h, w = sub.shape[:2]
    x_min, x_max = 365.5, 609.3
    y_min, y_max = 138.3, 2613.5

    def px2x(px: float) -> float:
        return round(x_min + (px / max(w, 1)) * (x_max - x_min), 2)

    def py2y(py: float) -> float:
        return round(y_max - (py / max(h, 1)) * (y_max - y_min), 1)

    groups_cfg = [
        ("order1_268_1036nm", (205, 88, 22), 62, None, None),
        ("order2_1126_2184nm", (188, 38, 138), 62, None, None),
        ("order3_esmeralda", (20, 20, 20), 45, (100, 500), (20, 300)),
    ]
    sat = np.max(sub, axis=2) - np.min(sub, axis=2)
    lum = np.mean(sub, axis=2)
    sc_out: dict[str, Any] = {}

    for gname, rgb, tol, xsp, ysp in groups_cfg:
        tgt = np.array(rgb, dtype=np.int16)[None, None, :]
        d = np.max(np.abs(sub - tgt), axis=2)
        if max(rgb) - min(rgb) > 20:
            dot_mask = (d <= tol) & (sat >= 20)
            arm_mask = (d <= tol + 28) & (sat >= 16)
        else:
            dot_mask = (d <= tol) & (lum < 120)
            arm_mask = (d <= tol + 35) & (lum < 165)

        gx0, gx1 = xsp if xsp else (0, w)
        gy0, gy1 = ysp if ysp else (0, h)
        pts_rel = _nms_peaks(distance_transform_edt(dot_mask[gy0:gy1, gx0:gx1]), min_dist=16, thr=7.5)
        pts = sorted([(gx0 + px, gy0 + py) for px, py in pts_rel], key=lambda ab: ab[0])

        xs, ys, x_lo, x_hi, y_lo, y_hi = [], [], [], [], [], []
        for cx, cy in pts:
            xl, xr, yd, yu = trace_error_arms(arm_mask, cx, cy, max_len=240, max_gap=3, band_half=2)
            xs.append(px2x(cx))
            ys.append(py2y(cy))
            x_lo.append(px2x(xl) if cx - xl > 14 else px2x(cx))
            x_hi.append(px2x(xr) if xr - cx > 14 else px2x(cx))
            y_lo.append(py2y(yd) if yd - cy > 14 else py2y(cy))
            y_hi.append(py2y(yu) if cy - yu > 14 else py2y(cy))

        sc_out[gname] = {
            "n": len(xs),
            "x": xs,
            "y": ys,
            "x_lo": x_lo,
            "x_hi": x_hi,
            "y_lo": y_lo,
            "y_hi": y_hi,
            "mean_x": round(float(np.mean(xs)), 2) if xs else None,
            "mean_y": round(float(np.mean(ys)), 1) if ys else None,
            "x_unit": "nm",
            "y_unit": "nm",
        }

    return {
        "digitized_scatter": sc_out,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": [x_min, x_max],
            "y_range": [y_min, y_max],
            "mode": "scatter_2d",
            "kind": "scatter",
        },
    }


def _extract_pgls(crop_rgb: np.ndarray, panel_id: str, bbox: tuple[int, int, int, int]) -> dict[str, Any]:
    # Compute plot_box dynamically relative to crop bbox so tightening crop y0 never breaks calibration!
    bx0, by0 = bbox[0], bbox[1]
    if panel_id == "B":
        # Global plot box in gr4.jpg: x in [2703, 3386], y in [67, 737]
        px0, py0, px1, py1 = 2703 - bx0, 67 - by0, 3386 - bx0, 737 - by0
        x_range = lin_range(2703, 3386, 2792.5, 400.0, 3375.5, 600.0)
        yr_tb = lin_range(67, 737, 145.0, 1200.0, 629.0, 400.0)
        y_range = (yr_tb[1], yr_tb[0])
        line_rgb = (210, 88, 25)
        cname = "cohort1_pgls_fit"
        gname = "cohort1_species"
        txt_excl = (0, 0, 265, 185)  # excludes "PGLS p= 3.1e-03" text
    else:
        # Global plot box in gr4.jpg: x in [2703, 3389], y in [778, 1230]
        px0, py0, px1, py1 = 2703 - bx0, 778 - by0, 3389 - bx0, 1230 - by0
        x_range = lin_range(2703, 3389, 2792.0, 400.0, 3360.5, 600.0)
        yr_tb = lin_range(778, 1230, 799.5, 2400.0, 1129.0, 1200.0)
        y_range = (yr_tb[1], yr_tb[0])
        line_rgb = (188, 38, 138)
        cname = "cohort2_pgls_fit"
        gname = "cohort2_species"
        txt_excl = (0, 0, 255, 175)  # excludes "PGLS p< 1e-04" text

    sub = crop_rgb[py0:py1, px0:px1]
    sub_f = sub.astype(np.float32)
    h, w = sub_f.shape[:2]
    x_min, x_max = x_range
    y_min, y_max = y_range

    def px2x(px: float) -> float:
        return round(x_min + (px / max(w, 1)) * (x_max - x_min), 2)

    def py2y(py: float) -> float:
        return round(y_max - (py / max(h, 1)) * (y_max - y_min), 1)

    perp, alpha = ray_dist_alpha(sub_f, line_rgb)
    sat = np.max(sub_f, axis=2) - np.min(sub_f, axis=2)
    lum = np.mean(sub_f, axis=2)

    ribbon_mk = (perp <= 48.0) & (alpha >= 0.08) & (sat >= 10.0)
    core_mk = (perp <= 32.0) & (alpha >= 0.45) & (sat >= 30.0)

    n_bins = 55
    x_cols = np.linspace(4, w - 5, n_bins).astype(int)
    xs, ys, lo, hi = [], [], [], []
    for cx in x_cols:
        c0, c1 = max(0, cx - 2), min(w, cx + 3)
        ry = np.where(ribbon_mk[:, c0:c1].any(axis=1))[0]
        cy_arr = np.where(core_mk[:, c0:c1].any(axis=1))[0]
        if len(cy_arr) >= 1 and len(ry) >= 2:
            a_col = np.where(core_mk[:, c0:c1], alpha[:, c0:c1], 0.0).max(axis=1)
            ym = float(np.argmax(a_col))
            xs.append(px2x(cx))
            ys.append(py2y(ym))
            lo.append(py2y(float(ry.max())))
            hi.append(py2y(float(ry.min())))

    # Also extract individual black species scatter dots inside 4B & 4C!
    dot_mk = (lum < 90.0) & (sat < 35.0)
    ex0, ey0, ex1, ey1 = txt_excl
    dot_mk[ey0:ey1, ex0:ex1] = False
    # Exclude 2px margins on edges
    dot_mk[:3, :] = False
    dot_mk[-3:, :] = False
    dot_mk[:, :3] = False
    dot_mk[:, -3:] = False
    bs = blobs(dot_mk, min_area=6, max_area=180)
    dxs = [px2x(b["x"]) for b in bs]
    dys = [py2y(b["y"]) for b in bs]
    ord_i = np.argsort(dxs)
    dxs = [dxs[i] for i in ord_i]
    dys = [dys[i] for i in ord_i]

    return {
        "curves": {
            cname: {
                "x": xs,
                "y": ys,
                "lo": lo,
                "hi": hi,
                "peak_x": xs[-1] if xs else None,
                "peak_y": ys[-1] if ys else None,
                "x_unit": "nm",
                "y_unit": "nm",
            }
        },
        "digitized_scatter": {
            gname: {
                "n": len(dxs),
                "x": dxs,
                "y": dys,
                "mean_x": round(float(np.mean(dxs)), 2) if dxs else None,
                "mean_y": round(float(np.mean(dys)), 1) if dys else None,
                "x_unit": "nm",
                "y_unit": "nm",
            }
        },
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": list(x_range),
            "y_range": list(y_range),
            "mode": "scatter_2d",
            "kind": "scatter",
        },
    }


def _extract_4d(crop_rgb: np.ndarray, bbox: tuple[int, int, int, int]) -> dict[str, Any]:
    bx0, by0 = bbox[0], bbox[1]
    # Global plot box in gr4.jpg: x in [2702, 3374], y in [1277, 1747]
    px0, py0, px1, py1 = 2702 - bx0, 1277 - by0, 3374 - bx0, 1747 - by0
    sub = crop_rgb[py0:py1, px0:px1].copy()
    # Mask bottom-right legend ("i = 2 / i = 4 / i = 6") strictly below the i=2 line
    sub[365:, 505:, :] = 255
    sub_f = sub.astype(np.float32)
    h, w = sub_f.shape[:2]
    x_min, x_max = 301.382, 611.06
    y_min, y_max = 268.868, 2485.849
    sat = np.max(sub_f, axis=2) - np.min(sub_f, axis=2)

    cols = np.linspace(4, w - 5, 55).astype(int)
    curves: dict[str, Any] = {}
    for name, rgb, is_mono in [
        ("order_i2", (210, 88, 25), False),
        ("order_i4", (186, 36, 136), False),
        ("order_i6", (18, 18, 18), True),
    ]:
        perp, alpha = ray_dist_alpha(sub_f, rgb)
        xs, ys = [], []
        for cx in cols:
            c0, c1 = max(0, cx - 2), min(w, cx + 3)
            p_col = perp[:, c0:c1].min(axis=1)
            a_col = alpha[:, c0:c1].max(axis=1)
            s_col = sat[:, c0:c1].max(axis=1)
            if is_mono:
                if x_min + (cx / max(w, 1)) * (x_max - x_min) > 472.0:
                    continue
                ok = (p_col <= 32.0) & (a_col >= 0.45) & (s_col < 28.0)
            else:
                ok = (p_col <= 38.0) & (a_col >= 0.35) & (s_col >= 20.0)
            hits = np.where(ok)[0]
            if len(hits) == 0:
                continue
            ym = float(np.median(hits))
            xs.append(round(x_min + (cx / max(w, 1)) * (x_max - x_min), 2))
            ys.append(round(y_max - (ym / max(h, 1)) * (y_max - y_min), 1))
        curves[name] = {
            "x": xs,
            "y": ys,
            "peak_x": xs[-1] if xs else None,
            "peak_y": ys[-1] if ys else None,
            "x_unit": "nm",
            "y_unit": "nm",
        }

    return {
        "curves": curves,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": [x_min, x_max],
            "y_range": [y_min, y_max],
            "kind": "curves",
        },
    }


def extract(crop_rgb: np.ndarray, panel_id: str, bbox: tuple[int, int, int, int] = (0, 0, 0, 0), **_: Any) -> dict[str, Any]:
    if panel_id == "A":
        return _extract_4a(crop_rgb)
    if panel_id in ("B", "C"):
        return _extract_pgls(crop_rgb, panel_id, bbox)
    if panel_id == "D":
        return _extract_4d(crop_rgb, bbox)
    raise ValueError(f"Unknown Finet Fig 4 panel_id: {panel_id}")
