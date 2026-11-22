"""Bespoke extractor for Parnell et al. (2018) Figure 9 (rsif20170948-g9.jpg):
- Panel A: Longitudinal AFM single-ridge height profiles (0–7 µm, offset 0–4.5 µm) for all 7 Heliconius taxa.
- Panels C, D, E, F: Transverse AFM cross-ridge topography height profiles for H. sara (C),
  H. erato demophoon (D), H. erato cyrbia (E), and H. melpomene rosina (F).

Uses exact inward-tick `AxisCal.fit` calibration + `ray_dist_alpha` + L1 `viterbi_track`.
"""
from __future__ import annotations

from typing import Any
import numpy as np

from livinglit_lepidoptera.extract_lib import (
    AxisCal,
    _group_centres,
    ray_dist_alpha,
    viterbi_track,
)


def _extract_panel_a(crop_rgb: np.ndarray) -> dict[str, Any]:
    f = crop_rgb.astype(np.float32)
    h_img, w_img = f.shape[:2]
    sat = f.max(axis=2) - f.min(axis=2)
    dk = (f.mean(axis=2) < 155.0) & (sat < 35.0)

    # Left spine (~47) and bottom spine (~291)
    vl = min(c for c in range(80) if dk[:, c].sum() > 150)
    hb = max(r for r in range(h_img - 60, h_img) if dk[r, :].sum() > 140)
    # Inward x-ticks (1, 2, 3, 4, 5, 6 um) just above bottom spine
    xt_hits = np.where(dk[hb - 5:hb - 2, vl + 10:w_img - 5].mean(axis=0) > 0.45)[0] + vl + 10
    xt_raw = _group_centres(xt_hits.tolist(), gap=2)
    # Filter to ticks with ~30.4 px step starting from vl (=0)
    x_ticks = [float(vl)]
    for k in range(1, 7):
        tgt = vl + k * 30.35
        cand = [t for t in xt_raw if abs(t - tgt) <= 3.5]
        x_ticks.append(min(cand, key=lambda t: abs(t - tgt)) if cand else tgt)
    x_cal = AxisCal.fit(x_ticks, [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0])

    # Inward y-ticks along right of left spine (vl+1..vl+3) with exact 52.67 px/um grid anchored at hb (=0)
    yt_hits = np.where(dk[45:hb - 4, vl + 1:vl + 4].mean(axis=1) > 0.45)[0] + 45
    yt_raw = _group_centres(yt_hits.tolist(), gap=2)
    # Match y = 0.5, 1.5, 2.5, 3.5 (at ~265, 212.3, 159.7, 107.0)
    y_pairs = []
    for val, approx in [(0.5, hb - 26.3), (1.5, hb - 79.0), (2.5, hb - 131.7), (3.5, hb - 184.3)]:
        cand = [t for t in yt_raw if abs(t - approx) <= 3.5]
        if cand:
            y_pairs.append((min(cand, key=lambda t: abs(t - approx)), val))
    y_cal = AxisCal.fit([p[0] for p in y_pairs], [p[1] for p in y_pairs])

    px0 = vl + 1
    px1 = int(round(x_cal.to_pixel(7.0)))
    py0 = int(round(y_cal.to_pixel(4.5)))
    py1 = hb - 1
    xr = list(x_cal.range_for_span(px0, px1, ndigits=3))
    yr = list(y_cal.range_for_span(py1, py0, ndigits=3))

    sub = f[py0:py1, px0:px1].copy()
    h, w = sub.shape[:2]
    # Mask top-left inset AFM cartoon + top-right legend box without clipping orange trace (~3.3 um)
    excl = np.zeros((h, w), dtype=bool)
    excl[:46, :115] = True
    excl[:62, 115:] = True

    # 7 stacked longitudinal ridge traces (y_band in plot_box local px, x_end_um)
    traces_cfg = [
        ("H_erato_cyrbia",      (237, 158, 43),  55.0, 0.28, (46, 96),   7.0, "color"),
        ("H_erato_demophoon",   (140, 28, 15),   55.0, 0.28, (86, 128),  7.0, "color"),
        ("H_sara",              (22, 126, 23),   55.0, 0.28, (108, 142), 5.7, "color"),
        ("H_eleuchia",          (30, 60, 188),   58.0, 0.28, (128, 166), 7.0, "color"),
        ("H_cydno",             (246, 245, 148), 48.0, 0.22, (150, 192), 7.0, "yellow"),
        ("H_melpomene_cythera", (37, 145, 218),  58.0, 0.28, (175, 215), 7.0, "color"),
        ("H_melpomene_rosina",  (10, 10, 10),    38.0, 0.45, (198, 236), 7.0, "black"),
    ]

    sub_sat = sub.max(axis=2) - sub.min(axis=2)
    sub_lum = sub.mean(axis=2)
    curves: dict[str, Any] = {}

    for name, rgb, max_perp, min_alpha, (yb0, yb1), x_end_um, mode in traces_cfg:
        c_end = min(w - 2, int(round(x_cal.to_pixel(x_end_um) - px0)))
        cols = np.linspace(1, c_end, 65).astype(int)
        xs_val = [round(max(0.0, float(x_cal.to_value(px0 + c))), 3) for c in cols]
        perp, alpha = ray_dist_alpha(sub, rgb)
        cost = np.full((h, len(cols)), 35.0, dtype=np.float64)
        for ti, c in enumerate(cols):
            c0, c1 = max(0, c - 1), min(w, c + 2)
            p_col = perp[:, c0:c1].min(axis=1)
            a_col = alpha[:, c0:c1].max(axis=1)
            s_col = sub_sat[:, c0:c1].max(axis=1)
            l_col = sub_lum[:, c0:c1].min(axis=1)
            if mode == "black":
                hit = (l_col < 90.0) & (s_col < 35.0) & (~excl[:, c])
                c_col = np.where(hit, 0.15 * l_col - 15.0, 35.0)
            elif mode == "yellow":
                # Pale yellow: R & G very high (>220), B clearly depressed (R - B > 35)
                rb_diff = (sub[:, c0:c1, 0] - sub[:, c0:c1, 2]).max(axis=1)
                hit = (rb_diff > 32.0) & (sub[:, c0:c1, 1].max(axis=1) > 205.0) & (~excl[:, c])
                c_col = np.where(hit, -0.25 * rb_diff, 35.0)
            else:
                t_sat = float(max(rgb) - min(rgb))
                hit = (p_col <= max_perp) & (a_col >= min_alpha) & (s_col >= max(24.0, 0.22 * t_sat)) & (~excl[:, c])
                c_col = np.where(hit, 0.40 * p_col - 14.0 * np.minimum(a_col, 1.0), 35.0)
            c_col[:yb0] = 95.0
            c_col[min(h, yb1):] = 95.0
            c_col[excl[:, c]] = 98.0
            cost[:, ti] = c_col

        y_path = viterbi_track(cost, max_step=14, smooth_w=0.45, norm="l1")
        ys = [round(max(0.0, float(y_cal.to_value(py0 + r))), 3) for r in y_path]
        curves[name] = {
            "x": xs_val,
            "y": ys,
            "x_unit": "µm",
            "y_unit": "µm",
            "height_range_um": round(float(max(ys) - min(ys)), 3),
        }

    return {
        "curves": curves,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": xr,
            "y_range": yr,
            "x_misfit_px": x_cal.misfit_px,
            "y_misfit_px": y_cal.misfit_px,
            "kind": "curves",
        },
        "extracted_data": {
            "x_tick_misfit_px": x_cal.misfit_px,
            "y_tick_misfit_px": y_cal.misfit_px,
            "sara_profile_range_um": curves["H_sara"]["height_range_um"],
            "rosina_profile_range_um": curves["H_melpomene_rosina"]["height_range_um"],
        },
    }


_TRANSVERSE_CFG: dict[str, dict[str, Any]] = {
    "C": {"name": "H_sara",             "rgb": (22, 129, 22),  "leg": (150, 95, 255, 126)},
    "D": {"name": "H_erato_demophoon",  "rgb": (166, 40, 26),  "leg": (90, 2, 255, 24)},
    "E": {"name": "H_erato_cyrbia",     "rgb": (34, 104, 225), "leg": (105, 2, 255, 24)},
    "F": {"name": "H_melpomene_rosina", "rgb": (233, 118, 48), "leg": (95, 2, 255, 24)},
}


def _extract_transverse(crop_rgb: np.ndarray, panel_id: str) -> dict[str, Any]:
    f = crop_rgb.astype(np.float32)
    h_img, w_img = f.shape[:2]
    sat = f.max(axis=2) - f.min(axis=2)
    dk = (f.mean(axis=2) < 155.0) & (sat < 35.0)

    vcols = [c for c in range(w_img) if dk[:, c].sum() > 0.45 * h_img]
    hrows = [r for r in range(h_img) if dk[r, :].sum() > 0.45 * w_img]
    vl, vr = min(vcols), max(vcols)
    ht, hb = min(hrows), max(hrows)
    px0, py0, px1, py1 = vl + 1, ht + 1, vr - 1, hb - 1

    # Inward x-ticks (0..7 um) on bottom spine
    xt_hits = np.where(dk[hb - 5:hb - 2, vl + 1:vr + 2].mean(axis=0) > 0.45)[0] + vl + 1
    xt_raw = _group_centres(xt_hits.tolist(), gap=2)
    step_x = (vr - vl) / 7.0
    x_ticks = [float(vl)]
    for k in range(1, 7):
        tgt = vl + k * step_x
        cand = [t for t in xt_raw if abs(t - tgt) <= 3.0]
        x_ticks.append(min(cand, key=lambda t: abs(t - tgt)) if cand else tgt)
    x_ticks.append(float(vr))
    x_cal = AxisCal.fit(x_ticks, [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])

    # Inward y-ticks (0.5, 1.0, 1.5 um; panel F has 0.5/1.0/1.5 at 40 px step, C/D/E at 35.5 px step)
    yt_hits = np.where(dk[ht + 3:hb - 2, vl + 2:vl + 5].mean(axis=1) > 0.45)[0] + ht + 3
    yt_raw = _group_centres(yt_hits.tolist(), gap=2)
    step_y = 40.0 if panel_id == "F" else 35.5
    y_pairs = [(float(hb), 0.0)]
    for k, val in [(1, 0.5), (2, 1.0), (3, 1.5)]:
        tgt = hb - k * step_y
        cand = [t for t in yt_raw if abs(t - tgt) <= 3.5]
        y_pairs.append((min(cand, key=lambda t: abs(t - tgt)) if cand else tgt, val))
    y_cal = AxisCal.fit([p[0] for p in y_pairs], [p[1] for p in y_pairs])

    xr = list(x_cal.range_for_span(px0, px1, ndigits=3))
    yr = list(y_cal.range_for_span(py1, py0, ndigits=3))

    sub = f[py0:py1, px0:px1].copy()
    h, w = sub.shape[:2]
    cfg = _TRANSVERSE_CFG[panel_id]
    excl = np.zeros((h, w), dtype=bool)
    lx0, ly0, lx1, ly1 = cfg["leg"]
    excl[max(0, ly0):min(h, ly1), max(0, lx0):min(w, lx1)] = True

    perp, alpha = ray_dist_alpha(sub, cfg["rgb"])
    sub_sat = sub.max(axis=2) - sub.min(axis=2)
    hit_all = (perp <= 58.0) & (alpha >= 0.30) & (sub_sat >= 40.0) & (~excl)

    # Detect actual horizontal span of the scanned AFM trace (e.g. H. sara ends at ~5.8 um)
    active_cols = np.where(hit_all.any(axis=0))[0]
    c_start = int(active_cols[0]) if len(active_cols) else 2
    c_end = int(active_cols[-1]) if len(active_cols) else w - 3
    cols = np.linspace(c_start, c_end, min(140, max(40, c_end - c_start + 1))).astype(int)
    xs_val = [round(max(0.0, float(x_cal.to_value(px0 + c))), 3) for c in cols]

    cost = np.full((h, len(cols)), 35.0, dtype=np.float64)
    for ti, c in enumerate(cols):
        c0, c1 = max(0, c - 1), min(w, c + 2)
        p_col = perp[:, c0:c1].min(axis=1)
        a_col = alpha[:, c0:c1].max(axis=1)
        s_col = sub_sat[:, c0:c1].max(axis=1)
        hit = (p_col <= 58.0) & (a_col >= 0.30) & (s_col >= 40.0) & (~excl[:, c])
        c_col = np.where(hit, 0.35 * p_col - 16.0 * np.minimum(a_col, 1.05), 35.0)
        c_col[excl[:, c]] = 95.0
        cost[:, ti] = c_col

    y_path = viterbi_track(cost, max_step=18, smooth_w=0.28, norm="l1")
    ys = [round(max(0.0, float(y_cal.to_value(py0 + r))), 3) for r in y_path]

    curves = {
        cfg["name"]: {
            "x": xs_val,
            "y": ys,
            "peak_x": xs_val[int(np.argmax(ys))],
            "peak_y": max(ys),
            "min_y": min(ys),
            "ridge_relief_um": round(float(max(ys) - min(ys)), 3),
            "x_unit": "µm",
            "y_unit": "µm",
        }
    }
    return {
        "curves": curves,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": xr,
            "y_range": yr,
            "x_misfit_px": x_cal.misfit_px,
            "y_misfit_px": y_cal.misfit_px,
            "kind": "curves",
        },
        "extracted_data": {
            "x_tick_misfit_px": x_cal.misfit_px,
            "y_tick_misfit_px": y_cal.misfit_px,
            "ridge_relief_um": curves[cfg["name"]]["ridge_relief_um"],
        },
    }


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    if panel_id == "A":
        return _extract_panel_a(crop_rgb)
    return _extract_transverse(crop_rgb, panel_id)
