"""Bespoke extractor for Totz et al. (2024) Figure 3A–E (fig3.jpg):
In vivo mean protoridge height profile (solid black) ± 1 SD shaded gray envelope
overlaid with weakly nonlinear FvK plate model fit (colored dashed curve) across
39.6% (A), 40.0% (B), 40.3% (C), 40.7% (D), and 41.0% (E) pupal development.

Uses inward tick detection (`AxisCal`), color-ray extraction (`ray_dist_alpha`),
centroid-refined L1 Viterbi DP (`viterbi_track`), and continuous ribbon boundary
walking (`walk_ribbon_bounds`).
"""
from __future__ import annotations

from typing import Any
import numpy as np
from scipy.ndimage import gaussian_filter1d

from livinglit_lepidoptera.extract_lib import AxisCal, ray_dist_alpha, viterbi_track, walk_ribbon_bounds


_PANEL_CFG = {
    "A": ("39.6pct", (255, 199, 0)),
    "B": ("40.0pct", (237, 138, 41)),
    "C": ("40.3pct", (237, 101, 84)),
    "D": ("40.7pct", (212, 101, 161)),
    "E": ("41.0pct", (191, 112, 255)),
}


def _detect_axes(crop_rgb: np.ndarray) -> dict[str, Any]:
    f = crop_rgb.astype(np.float32)
    h, w = f.shape[:2]
    sat = f.max(axis=2) - f.min(axis=2)
    dk = (f.mean(axis=2) < 120.0) & (sat < 40.0)

    def _runs(v: np.ndarray) -> list[tuple[int, int]]:
        m = np.concatenate([[False], v, [False]]).astype(np.int8)
        d = np.diff(m)
        return list(zip(np.flatnonzero(d == 1).tolist(), (np.flatnonzero(d == -1) - 1).tolist()))

    def _centres(idx: list[int], gap: int = 3) -> list[float]:
        if not idx:
            return []
        gs: list[list[int]] = [[int(idx[0])]]
        for i in idx[1:]:
            if int(i) - gs[-1][-1] <= gap:
                gs[-1].append(int(i))
            else:
                gs.append([int(i)])
        return [float(np.mean(g)) for g in gs]

    bv = [(c, *max(_runs(dk[:, c]), key=lambda r: r[1] - r[0])) for c in range(w) if _runs(dk[:, c])]
    bv = [x for x in bv if x[2] - x[1] + 1 >= 0.45 * h]
    c_left = bv[0][0]
    v_left = [x for x in bv if x[0] - c_left <= 8]
    vc1 = max(x[0] for x in v_left)
    v_right = [x for x in bv if x[0] > vc1 + 100]
    p_right = min(x[0] for x in v_right if v_right[-1][0] - x[0] <= 8) - 1

    bh = [(r, *max(_runs(dk[r, :]), key=lambda c: c[1] - c[0])) for r in range(h) if _runs(dk[r, :])]
    bh = [x for x in bh if x[2] - x[1] + 1 >= 0.45 * w]
    r_bot = bh[-1][0]
    h_bot = [x for x in bh if r_bot - x[0] <= 8]
    hr0 = min(x[0] for x in h_bot)
    h_top = [x for x in bh if x[0] < hr0 - 100]
    p_top = max(x[0] for x in h_top if x[0] - h_top[0][0] <= 8) + 1

    # Inward y-ticks at 25, 50, 75, 100 nm along left spine (0 nm tick overlaps the gray ribbon/curve endpoint)
    yb = dk[:, vc1 + 2:vc1 + 6]
    y_hits = [r for r in np.flatnonzero(yb.mean(axis=1) >= 0.55).tolist() if p_top + 10 <= r <= hr0 - 80]
    y_ticks = sorted(_centres(y_hits, gap=4), reverse=True)
    y_cal = AxisCal.fit(y_ticks, [25.0, 50.0, 75.0, 100.0], scale="linear")

    # Inward x-ticks at -0.8, -0.4, 0.0, +0.4, +0.8 µm (L = 1.6 µm)
    xb = dk[hr0 - 10:hr0 - 2, :]
    x_hits = [c for c in np.flatnonzero(xb.mean(axis=0) >= 0.55).tolist() if vc1 + 2 <= c <= p_right - 2]
    x_ticks = sorted(_centres(x_hits, gap=4))
    x_cal = AxisCal.fit(x_ticks, [-0.8, -0.4, 0.0, 0.4, 0.8], scale="linear")

    return {"plot_box": (vc1 + 1, p_top, p_right, hr0 - 1), "x_cal": x_cal, "y_cal": y_cal}


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    stage_lbl, model_rgb = _PANEL_CFG[panel_id]
    cal = _detect_axes(crop_rgb)
    px0, py0, px1, py1 = cal["plot_box"]
    x_cal, y_cal = cal["x_cal"], cal["y_cal"]

    sub = crop_rgb[py0:py1, px0:px1].astype(np.float32)
    h, w = sub.shape[:2]

    perp_m, alpha_m = ray_dist_alpha(sub, model_rgb)
    sat = sub.max(axis=2) - sub.min(axis=2)
    lum = sub.mean(axis=2)

    is_model = (perp_m < 38.0) & (alpha_m > 0.45) & (sat > 45.0)
    is_black_mean = (lum < 68.0) & (sat < 35.0)
    is_center_stroke = is_black_mean | is_model

    # Shaded ±1 SD gray ribbon (light gray fill + dark gray outline)
    is_ribbon = ((lum < 245.0) & (sat < 35.0)) | is_model
    is_ribbon[:8, :] = False
    is_ribbon[-14:, :] = False
    is_ribbon[:, :10] = False
    is_ribbon[:, -10:] = False

    c_lo = max(4, int(round(x_cal.to_pixel(-0.8) - px0)))
    c_hi = min(w - 5, int(round(x_cal.to_pixel(0.8) - px0)))
    n_pts = 80
    cols = np.linspace(c_lo, c_hi, n_pts).astype(int)

    # Track the smooth centerline of the solid black empirical mean and the colored dashed FvK model
    cost_mean = np.full((h, n_pts), 3.0, dtype=np.float64)
    cost_model = np.full((h, n_pts), 3.0, dtype=np.float64)
    for ti, cx in enumerate(cols):
        b_col = is_black_mean[:, max(0, cx - 2):min(w, cx + 3)].any(axis=1)
        m_col = is_model[:, max(0, cx - 2):min(w, cx + 3)].any(axis=1)
        cost_mean[:, ti] = np.where(b_col, 0.05, np.where(m_col, 0.20, 2.8))
        cost_model[:, ti] = np.where(m_col, 0.05, np.where(b_col, 0.25, 2.4))

    path_mean_raw = viterbi_track(cost_mean, max_step=16, smooth_w=0.08, norm="l1").astype(np.float64)
    path_model_raw = viterbi_track(cost_model, max_step=16, smooth_w=0.10, norm="l1").astype(np.float64)

    # Refine each column to exact stroke vertical centroid within ±10 px so thick dashes don't zig-zag
    pm_ref = path_mean_raw.copy()
    pd_ref = path_model_raw.copy()
    for i, cx in enumerate(cols):
        # Mean curve centroid: prefer black ink where visible, else combined centerline stroke
        r0, r1 = max(0, int(round(path_mean_raw[i])) - 10), min(h, int(round(path_mean_raw[i])) + 11)
        bm = is_black_mean[r0:r1, cx]
        cm = is_center_stroke[r0:r1, cx]
        if bm.sum() >= 2:
            pm_ref[i] = float(r0 + np.mean(np.flatnonzero(bm)))
        elif cm.sum() >= 2:
            pm_ref[i] = float(r0 + np.mean(np.flatnonzero(cm)))
        # Model curve centroid: prefer colored dash where visible, else interpolate between dashes
        r0d, r1d = max(0, int(round(path_model_raw[i])) - 10), min(h, int(round(path_model_raw[i])) + 11)
        mm = is_model[r0d:r1d, cx]
        if mm.sum() >= 2:
            pd_ref[i] = float(r0d + np.mean(np.flatnonzero(mm)))
        elif cm.sum() >= 2:
            pd_ref[i] = float(r0d + np.mean(np.flatnonzero(cm)))

    # Smooth gently to remove dash-gap micro-steps while preserving exact peak height
    pm_smooth = gaussian_filter1d(pm_ref, sigma=1.4, mode="nearest")
    pd_smooth = gaussian_filter1d(pd_ref, sigma=1.8, mode="nearest")

    # Walk ±1 SD gray ribbon continuously up/down from smoothed mean curve
    y_lo_px, y_hi_px = walk_ribbon_bounds(
        is_ribbon, cols, pm_smooth, max_half=220, max_gap=4, top_pad=4, bot_pad=4, col_half_w=2
    )
    y_lo_px = gaussian_filter1d(y_lo_px, sigma=1.0, mode="nearest")
    y_hi_px = gaussian_filter1d(y_hi_px, sigma=1.0, mode="nearest")

    xs_v: list[float] = []
    mean_v: list[float] = []
    lo_v: list[float] = []
    hi_v: list[float] = []
    model_v: list[float] = []
    for cx, pm, pd, ylo_p, yhi_p in zip(cols, pm_smooth, pd_smooth, y_lo_px, y_hi_px):
        xs_v.append(round(x_cal.to_value(px0 + float(cx)), 4))
        mean_v.append(round(y_cal.to_value(py0 + float(pm)), 2))
        lo_v.append(round(y_cal.to_value(py0 + float(ylo_p)), 2))
        hi_v.append(round(y_cal.to_value(py0 + float(yhi_p)), 2))
        model_v.append(round(y_cal.to_value(py0 + float(pd)), 2))

    pk_m = int(np.argmax(mean_v))
    pk_d = int(np.argmax(model_v))
    curves = {
        f"in_vivo_mean_{stage_lbl}": {
            "x": xs_v,
            "y": mean_v,
            "lo": lo_v,
            "hi": hi_v,
            "peak_x": xs_v[pk_m],
            "peak_y": mean_v[pk_m],
            "peak_hi_sd": hi_v[pk_m],
            "peak_lo_sd": lo_v[pk_m],
            "x_unit": "µm",
            "y_unit": "nm",
        },
        f"fvk_model_{stage_lbl}": {
            "x": xs_v,
            "y": model_v,
            "peak_x": xs_v[pk_d],
            "peak_y": model_v[pk_d],
            "x_unit": "µm",
            "y_unit": "nm",
        },
    }

    return {
        "curves": curves,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": [round(x_cal.to_value(px0), 4), round(x_cal.to_value(px1), 4)],
            "y_range": [round(y_cal.to_value(py1), 3), round(y_cal.to_value(py0), 3)],
            "x_misfit_px": x_cal.misfit_px,
            "y_misfit_px": y_cal.misfit_px,
            "kind": "curves",
        },
        "extracted_data": {
            "stage": stage_lbl,
            "x_tick_misfit_px": x_cal.misfit_px,
            "y_tick_misfit_px": y_cal.misfit_px,
            "in_vivo_peak_nm": mean_v[pk_m],
            "in_vivo_peak_plus_sd_nm": hi_v[pk_m],
            "in_vivo_peak_minus_sd_nm": lo_v[pk_m],
            "fvk_model_peak_nm": model_v[pk_d],
        },
    }
