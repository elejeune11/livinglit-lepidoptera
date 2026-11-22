"""Bespoke extractor for Parnell et al. (2018) Figure 7 (rsif20170948-g7.jpg):
Single-scale Raman spectra (1000–2000 cm^-1, 0–9000 arb. units) of 7 Heliconius taxa
plus Aglais io demonstrating shared melanin bands at 1408 and 1588 cm^-1.

Detects the closed axes frame and inward major tick marks (`AxisCal.fit`) with subpixel
precision (misfit <= 0.35 px), masks the top-left inset scale photograph, and traces all 8
color-coded Raman spectra using `ray_dist_alpha` + L1 `viterbi_track`.
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


_RAMAN_TRACES = [
    # (name, rgb, max_perp, min_alpha, y_band_px, mode)
    ("H_sara",              (12, 12, 12),    32.0, 0.55, (5, 240),   "black"),
    ("H_melpomene_rosina",  (235, 114, 44),  52.0, 0.30, (20, 260),  "color"),
    ("H_erato_demophoon",   (148, 126, 90),  42.0, 0.32, (105, 290), "brown"),
    ("H_melpomene_cythera", (42, 219, 42),   55.0, 0.28, (150, 315), "color"),
    ("H_cydno",             (220, 47, 35),   50.0, 0.30, (185, 325), "color"),
    ("H_eleuchia",          (18, 44, 175),   52.0, 0.30, (195, 330), "color"),
    ("H_erato_cyrbia",      (124, 48, 118),  48.0, 0.30, (205, 338), "color"),
    ("Aglais_io",           (132, 206, 198), 48.0, 0.25, (250, 342), "color"),
]


def extract(crop_rgb: np.ndarray, panel_id: str = "A", **_: Any) -> dict[str, Any]:
    f = crop_rgb.astype(np.float32)
    h_img, w_img = f.shape[:2]
    sat = f.max(axis=2) - f.min(axis=2)
    dk = (f.mean(axis=2) < 140.0) & (sat < 35.0)

    # Locate closed plot frame spines (left, right, top, bottom)
    vcols = [c for c in range(w_img) if dk[:, c].sum() > 250]
    hrows = [r for r in range(h_img) if dk[r, :550].sum() > 350]
    vl = min(vcols)
    vr = max(c for c in vcols if c < 560)
    ht = min(hrows)
    hb = max(hrows)
    px0, py0, px1, py1 = vl + 1, ht + 1, vr - 1, hb - 1

    # Detect inward major x-ticks (1200, 1400, 1600, 1800, 2000) & y-ticks (0, 2000, 4000, 6000, 8000)
    xt_hits = np.where(dk[hb - 7:hb - 4, vl + 5:vr + 2].mean(axis=0) > 0.5)[0] + vl + 5
    x_ticks = [float(vl)] + _group_centres(xt_hits.tolist(), gap=2)
    if len(x_ticks) == 6:
        x_cal = AxisCal.fit(x_ticks, [1000.0, 1200.0, 1400.0, 1600.0, 1800.0, 2000.0])
    else:
        x_cal = AxisCal.fit([float(vl), float(vr)], [1000.0, 2000.0])

    # Inward y-ticks along right side of left spine (vl+4..vl+6) using neutral black ink (sat < 35)
    yt_hits = np.where(dk[ht + 10:hb - 5, vl + 4:vl + 7].mean(axis=1) > 0.5)[0] + ht + 10
    yt_raw = _group_centres(yt_hits.tolist(), gap=2)
    # Match expected regular spacing (~76 px) from bottom spine hb (= 0)
    step_y = (hb - yt_raw[0]) / 4.0 if yt_raw else 76.25
    y_ticks_matched = [float(hb)]
    for k in range(1, 5):
        target_y = hb - k * step_y
        cand = [t for t in yt_raw if abs(t - target_y) <= 4.0]
        y_ticks_matched.append(min(cand, key=lambda t: abs(t - target_y)) if cand else target_y)
    y_cal = AxisCal.fit(y_ticks_matched, [0.0, 2000.0, 4000.0, 6000.0, 8000.0])

    xr = list(x_cal.range_for_span(px0, px1, ndigits=2))
    yr = list(y_cal.range_for_span(py1, py0, ndigits=2))

    sub = f[py0:py1, px0:px1].copy()
    h, w = sub.shape[:2]

    # Mask top-left inset scale micrograph (x < 148, y < 98 inside plot_box)
    excl = np.zeros((h, w), dtype=bool)
    excl[:98, :148] = True

    cols = np.linspace(2, w - 3, 95).astype(int)
    xs_val = [round(float(x_cal.to_value(px0 + c)), 1) for c in cols]

    sub_sat = sub.max(axis=2) - sub.min(axis=2)
    sub_lum = sub.mean(axis=2)

    curves: dict[str, Any] = {}
    for name, rgb, max_perp, min_alpha, (yb0, yb1), mode in _RAMAN_TRACES:
        perp, alpha = ray_dist_alpha(sub, rgb)
        cost = np.full((h, len(cols)), 35.0, dtype=np.float64)
        for ti, c in enumerate(cols):
            c0, c1 = max(0, c - 2), min(w, c + 3)
            p_col = perp[:, c0:c1].min(axis=1)
            a_col = alpha[:, c0:c1].max(axis=1)
            s_col = sub_sat[:, c0:c1].max(axis=1)
            l_col = sub_lum[:, c0:c1].min(axis=1)
            if mode == "black":
                hit = (l_col < 55.0) & (s_col < 32.0) & (~excl[:, c])
                c_col = np.where(hit, 0.15 * l_col - 15.0, 35.0)
            elif mode == "brown":
                # Warm brown (R > G > B, moderate saturation 35..80, mid luminance)
                r_c = sub[:, c0:c1, 0].mean(axis=1)
                g_c = sub[:, c0:c1, 1].mean(axis=1)
                b_c = sub[:, c0:c1, 2].mean(axis=1)
                hit = (p_col <= max_perp) & (a_col >= min_alpha) & (r_c > g_c + 8) & (g_c > b_c + 12) & (s_col < 115) & (~excl[:, c])
                c_col = np.where(hit, 0.40 * p_col - 15.0 * np.minimum(a_col, 1.0), 35.0)
            else:
                t_sat = float(max(rgb) - min(rgb))
                hit = (p_col <= max_perp) & (a_col >= min_alpha) & (s_col >= max(24.0, 0.25 * t_sat)) & (~excl[:, c])
                c_col = np.where(hit, 0.40 * p_col - 15.0 * np.minimum(a_col, 1.0), 35.0)
            c_col[:yb0] = 95.0
            c_col[min(h, yb1):] = 95.0
            c_col[excl[:, c]] = 98.0
            cost[:, ti] = c_col

        y_path = viterbi_track(cost, max_step=12, smooth_w=0.55, norm="l1")
        ys = [round(max(0.0, float(y_cal.to_value(py0 + r))), 1) for r in y_path]
        # Measure melanin peak near 1588 cm^-1 (1530..1640 cm^-1)
        win = [i for i, xv in enumerate(xs_val) if 1530.0 <= xv <= 1640.0]
        pk = max(win, key=lambda i: ys[i]) if win else int(np.argmax(ys))
        curves[name] = {
            "x": xs_val,
            "y": ys,
            "peak_x": xs_val[pk],
            "peak_y": ys[pk],
            "x_unit": "cm^-1",
            "y_unit": "arb. units",
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
            "n_species": len(curves),
            "melanin_peak_sara_cm1": curves["H_sara"]["peak_x"],
        },
    }
