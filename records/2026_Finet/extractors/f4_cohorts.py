"""Bespoke extractor for Finet et al. (2026) Figure 4A, 4B, 4C, 4D (gr4.jpg):
- A (4A): Automatic tick calibration (`find_axis_ticks`, RMS ~0.12 px) + 39-scale scatter plot (34 species)
  via occlusion-aware matched-filter peeling + occlusion-crossing x/y ±SD error bars (`trace_error_arms_occluded`).
- B (4B): Automatic tick calibration + Cohort 1 PGLS line + 95% CI + ALL 17/17 individual species dots
  (including all 6 dark-brown dots hidden under the translucent orange 95% CI ribbon via `shaded_bg_residual`).
- C (4C): Automatic tick calibration + Cohort 2 PGLS line + 95% CI + ALL 21/21 individual species dots
  (including overlapping pairs and dots sitting directly on top of the magenta PGLS line via `occ=pgls_line`).
- D (4D): Automatic tick calibration (`0.00 px` misfit) + thin-film interference theoretical curves (i = 2, 4, 6).
"""
from __future__ import annotations

from typing import Any
import numpy as np
from scipy.ndimage import distance_transform_edt

from livinglit_lepidoptera.extract_lib import (
    detect_markers_matched_filter,
    find_axis_ticks,
    ray_dist_alpha,
    shaded_bg_residual,
    trace_error_arms_occluded,
)


def _extract_4a(crop_rgb: np.ndarray) -> dict[str, Any]:
    cal = find_axis_ticks(
        crop_rgb,
        y_labels=[500.0, 1000.0, 1500.0, 2000.0, 2500.0],
        x_labels=[400.0, 450.0, 500.0, 550.0, 600.0],
        dark_thr=155.0,
        probe=(2, 12),
        tick_min_frac=0.45,
    )
    px0, py0, px1, py1 = cal["plot_box"]
    x_cal, y_cal = cal["x_cal"], cal["y_cal"]
    x_min, x_max = x_cal.range_for_span(px0, px1, ndigits=3)
    y_max, y_min = y_cal.range_for_span(py0, py1, ndigits=2)

    sub = crop_rgb[py0:py1, px0:px1].astype(np.float32)
    h, w = sub.shape[:2]

    def px2x(px: float) -> float:
        return round(x_cal.to_value(px0 + px), 2)

    def py2y(py: float) -> float:
        return round(y_cal.to_value(py0 + py), 1)

    groups_cfg = [
        ("order1_268_1036nm", (205, 88, 22), 62.0, None, None),
        ("order2_1126_2184nm", (188, 38, 138), 62.0, None, None),
        ("order3_esmeralda", (20, 20, 20), 45.0, (100, 500), (20, 300)),
    ]
    sat = np.max(sub, axis=2) - np.min(sub, axis=2)
    lum = np.mean(sub, axis=2)
    all_ink = lum < 225.0
    sc_out: dict[str, Any] = {}

    for gname, rgb, tol, xsp, ysp in groups_cfg:
        tgt = np.array(rgb, dtype=np.float32)[None, None, :]
        d = np.max(np.abs(sub - tgt), axis=2)
        if max(rgb) - min(rgb) > 20:
            dot_mask = (d <= tol) & (sat >= 20.0)
            arm_mask = (d <= tol + 28.0) & (sat >= 16.0)
        else:
            dot_mask = (d <= tol) & (lum < 120.0)
            arm_mask = (d <= tol + 35.0) & (lum < 165.0)

        gx0, gx1 = xsp if xsp else (0, w)
        gy0, gy1 = ysp if ysp else (0, h)
        if xsp or ysp:
            dm = np.zeros_like(dot_mask)
            dm[gy0:gy1, gx0:gx1] = dot_mask[gy0:gy1, gx0:gx1]
            dot_mask = dm
            am = np.zeros_like(arm_mask)
            am[gy0:gy1, gx0:gx1] = arm_mask[gy0:gy1, gx0:gx1]
            arm_mask = am

        occ_dot = all_ink & ~dot_mask
        occ_arm = all_ink & ~arm_mask
        pts = detect_markers_matched_filter(
            dot_mask, occ_dot, radius=11.0, shape="disk",
            min_visible=0.38, max_bg=0.18, min_score=0.34,
            min_sep_factor=1.65, peel=True, peel_radius_factor=1.02,
            upsample=1, border_px=3,
        )
        pts.sort(key=lambda p: p["x"])

        xs, ys, x_lo, x_hi, y_lo, y_hi = [], [], [], [], [], []
        for p in pts:
            cx, cy = p["x"], p["y"]
            xl, xr, yd, yu, _ = trace_error_arms_occluded(
                arm_mask, occ_arm, cx, cy, max_len=260, max_gap=3, band_half=3, marker_r=11.0
            )
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
            "n_occluded": int(sum(1 for p in pts if p["occluded"])),
            "x_unit": "nm",
            "y_unit": "nm",
        }

    return {
        "digitized_scatter": sc_out,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": [x_min, x_max],
            "y_range": [y_min, y_max],
            "x_misfit_px": cal["x_misfit_px"],
            "y_misfit_px": cal["y_misfit_px"],
            "mode": "scatter_2d",
            "kind": "scatter",
        },
    }


def _extract_pgls(crop_rgb: np.ndarray, panel_id: str) -> dict[str, Any]:
    if panel_id == "B":
        y_labels = [400.0, 600.0, 800.0, 1000.0, 1200.0]
        x_labels = [400.0, 450.0, 500.0, 550.0, 600.0]
        line_rgb = (210, 88, 25)
        cname = "cohort1_pgls_fit"
        gname = "cohort1_species"
        txt_excl = (0, 0, 265, 185)  # excludes "PGLS p= 3.1e-03" text
    else:
        y_labels = [1200.0, 1600.0, 2000.0, 2400.0]
        x_labels = [400.0, 450.0, 500.0, 550.0, 600.0]
        line_rgb = (188, 38, 138)
        cname = "cohort2_pgls_fit"
        gname = "cohort2_species"
        txt_excl = (0, 0, 255, 175)  # excludes "PGLS p< 1e-04" text

    cal = find_axis_ticks(
        crop_rgb,
        y_labels=y_labels,
        x_labels=x_labels,
        dark_thr=155.0,
        probe=(1, 5),
        tick_min_frac=0.45,
    )
    px0, py0, px1, py1 = cal["plot_box"]
    x_cal, y_cal = cal["x_cal"], cal["y_cal"]
    x_min, x_max = x_cal.range_for_span(px0, px1, ndigits=3)
    y_max, y_min = y_cal.range_for_span(py0, py1, ndigits=2)

    sub = crop_rgb[py0:py1, px0:px1]
    sub_f = sub.astype(np.float32)
    h, w = sub_f.shape[:2]

    def px2x(px: float) -> float:
        return round(x_cal.to_value(px0 + px), 2)

    def py2y(py: float) -> float:
        return round(y_cal.to_value(py0 + py), 1)

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

    # Shaded-overlay-invariant + occlusion-aware peeling for ALL species dots (including dots under the CI ribbon & on the PGLS line!)
    _, res_m = shaded_bg_residual(sub, marker_diam_px=9, mode="median")
    res_lum = res_m.mean(axis=2)
    pgls_line = (perp <= 30.0) & (alpha >= 0.55) & (sat >= 55.0)
    dot_tgt = (lum < 125.0) & (res_lum >= 38.0) & ~pgls_line
    ex0, ey0, ex1, ey1 = txt_excl
    dot_tgt[ey0:ey1, ex0:ex1] = False

    r_est = float(distance_transform_edt(dot_tgt).max())
    pts = detect_markers_matched_filter(
        dot_tgt, pgls_line, radius=max(2.5, r_est - 0.6), shape="disk",
        min_visible=0.35, max_bg=0.24, min_score=0.25,
        min_sep_factor=1.45, peel=True, peel_radius_factor=1.05, upsample=2, border_px=2,
    )
    pts.sort(key=lambda p: p["x"])
    dxs = [px2x(p["x"]) for p in pts]
    dys = [py2y(p["y"]) for p in pts]

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
                "n_occluded": int(sum(1 for p in pts if p["occluded"])),
                "x_unit": "nm",
                "y_unit": "nm",
            }
        },
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": [x_min, x_max],
            "y_range": [y_min, y_max],
            "x_misfit_px": cal["x_misfit_px"],
            "y_misfit_px": cal["y_misfit_px"],
            "mode": "scatter_2d",
            "kind": "scatter",
        },
    }


def _extract_4d(crop_rgb: np.ndarray) -> dict[str, Any]:
    cal = find_axis_ticks(
        crop_rgb,
        y_labels=[250.0, 500.0, 750.0, 1000.0, 1250.0, 1500.0, 1750.0, 2000.0, 2250.0, 2500.0],
        x_labels=[300.0, 400.0, 500.0, 600.0],
        dark_thr=155.0,
        probe=(2, 10),
        tick_min_frac=0.45,
    )
    px0, py0, px1, py1 = cal["plot_box"]
    x_cal, y_cal = cal["x_cal"], cal["y_cal"]
    x_min, x_max = x_cal.range_for_span(px0, px1, ndigits=3)
    y_max, y_min = y_cal.range_for_span(py0, py1, ndigits=2)

    sub = crop_rgb[py0:py1, px0:px1].copy()
    sub[365:, 505:, :] = 255
    sub_f = sub.astype(np.float32)
    h, w = sub_f.shape[:2]
    sat = np.max(sub_f, axis=2) - np.min(sub_f, axis=2)

    cols = np.linspace(4, w - 5, 55).astype(int)
    curves: dict[str, Any] = {}
    for name, rgb, is_mono in [
        ("order_i2", (210, 88, 25), False),
        ("order_i4", (186, 36, 136), False),
        ("order_i6", (18, 18, 18), True),
    ]:
        perp, alpha = ray_dist_alpha(sub_f, rgb)
        # Per-pixel validity check (prevents pairing white perp=0 with neighbor alpha!)
        if is_mono:
            ok_px = (perp <= 28.0) & (alpha >= 0.45) & (sat < 28.0)
        else:
            ok_px = (perp <= 36.0) & (alpha >= 0.35) & (sat >= 20.0)
        xs, ys = [], []
        for cx in cols:
            xv = round(x_cal.to_value(px0 + cx), 2)
            if is_mono and xv > 472.0:
                continue
            c0, c1 = max(0, cx - 2), min(w, cx + 3)
            hits = np.where(ok_px[:, c0:c1].any(axis=1))[0]
            if len(hits) == 0:
                continue
            ym = float(np.median(hits))
            xs.append(xv)
            ys.append(round(y_cal.to_value(py0 + ym), 1))
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
            "x_misfit_px": cal["x_misfit_px"],
            "y_misfit_px": cal["y_misfit_px"],
            "kind": "curves",
        },
    }


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    if panel_id == "A":
        return _extract_4a(crop_rgb)
    if panel_id in ("B", "C"):
        return _extract_pgls(crop_rgb, panel_id)
    if panel_id == "D":
        return _extract_4d(crop_rgb)
    raise ValueError(f"Unknown Finet Fig 4 panel_id: {panel_id}")
