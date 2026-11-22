"""Bespoke extractor for Totz et al. (2024) Figure 4C (fig4.jpg):
Phase space of weakly nonlinear FvK buckling amplitude w_0 (nm) over actin bundle spacing L
(0.0 to 2.0 µm) and growth strain g (0.0 to 0.725%), digitizing:
1. Three constant-amplitude gray isocontours (0.1 nm, 1 nm, 10 nm) via background-residual
   Viterbi DP along the y-axis.
2. Five empirical vertical black dashed lines (Colias eurytheme L2 & L1, Agraulis vanillae
   L2 & L1, and Vanessa cardui L) detected directly from column ink density.
"""
from __future__ import annotations

from typing import Any
import cv2
import numpy as np

from livinglit_lepidoptera.extract_lib import AxisCal, viterbi_track


def _detect_axes(crop_rgb: np.ndarray) -> dict[str, Any]:
    f = crop_rgb.astype(np.float32)
    h, w = f.shape[:2]
    sat = f.max(axis=2) - f.min(axis=2)
    dk = (f.mean(axis=2) < 100.0) & (sat < 40.0)

    def _runs(v: np.ndarray) -> list[tuple[int, int]]:
        m = np.concatenate([[False], v, [False]]).astype(np.int8)
        d = np.diff(m)
        return list(zip(np.flatnonzero(d == 1).tolist(), (np.flatnonzero(d == -1) - 1).tolist()))

    def _centres(idx: list[int], gap: int = 4) -> list[float]:
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
    v_clusters: list[list[tuple[int, int, int]]] = [[bv[0]]]
    for x in bv[1:]:
        if x[0] - v_clusters[-1][-1][0] <= 10:
            v_clusters[-1].append(x)
        else:
            v_clusters.append([x])
    # First cluster = left spine (L=0.0), second cluster = right spine of phase plot (L=2.0)
    vc0_l, vc1_l = min(x[0] for x in v_clusters[0]), max(x[0] for x in v_clusters[0])
    vc0_r, vc1_r = min(x[0] for x in v_clusters[1]), max(x[0] for x in v_clusters[1])

    bh = [(r, *max(_runs(dk[r, vc0_l:vc1_r + 1]), key=lambda c: c[1] - c[0])) for r in range(h) if _runs(dk[r, vc0_l:vc1_r + 1])]
    bh = [x for x in bh if x[2] - x[1] + 1 >= 0.70 * (vc1_r - vc0_l)]
    r_bot = bh[-1][0]
    h_bot = [x for x in bh if r_bot - x[0] <= 8]
    hr0, hr1 = min(x[0] for x in h_bot), max(x[0] for x in h_bot)
    h_top = [x for x in bh if x[0] < hr0 - 150]
    p_top = max(x[0] for x in h_top if x[0] - h_top[0][0] <= 8) + 1

    # Y ticks: bottom frame = 0.0 plus 3 long inward ticks (depth 5..14 px) at 0.2, 0.4, 0.6
    yb = dk[:, vc1_l + 5:vc1_l + 14]
    y_hits = [r for r in np.flatnonzero(yb.mean(axis=1) >= 0.55).tolist() if p_top + 18 <= r <= hr0 - 18]
    y_ticks = [0.5 * (hr0 + hr1)] + sorted(_centres(y_hits, gap=5), reverse=True)
    y_cal = AxisCal.fit(y_ticks, [0.0, 0.2, 0.4, 0.6], scale="linear")

    # X ticks: bottom-frame long inward ticks (depth 11..15 px) at 0.5, 1.0, 1.5 µm give sub-pixel calibration!
    xb = dk[hr0 - 15:hr0 - 11, :]
    x_hits = [c for c in np.flatnonzero(xb.mean(axis=0) >= 0.55).tolist() if vc1_l + 40 <= c <= vc0_r - 40]
    x_mid = sorted(_centres(x_hits, gap=5))
    x_cal = AxisCal.fit(x_mid, [0.5, 1.0, 1.5], scale="linear")

    return {"plot_box": (vc1_l + 1, p_top, vc0_r - 1, hr0 - 1), "x_cal": x_cal, "y_cal": y_cal}


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    cal = _detect_axes(crop_rgb)
    px0, py0, px1, py1 = cal["plot_box"]
    x_cal, y_cal = cal["x_cal"], cal["y_cal"]

    sub_u8 = crop_rgb[py0:py1, px0:px1]
    sub = sub_u8.astype(np.float32)
    h, w = sub.shape[:2]

    # 1. Detect the 5 vertical black dashed lines directly from dark neutral column density
    sat = sub.max(axis=2) - sub.min(axis=2)
    lum = sub.mean(axis=2)
    is_black = (lum < 65.0) & (sat < 30.0)
    col_frac = is_black[20:-20, :].mean(axis=0)
    xs_dash = np.where(col_frac > 0.16)[0].tolist()
    d_groups: list[list[int]] = []
    for x in xs_dash:
        if not d_groups or x - d_groups[-1][-1] > 4:
            d_groups.append([x])
        else:
            d_groups[-1].append(x)
    dash_x_px = [float(np.mean(g)) for g in d_groups]
    dash_L_um = [round(x_cal.to_value(px0 + cx), 3) for cx in dash_x_px]

    dash_labels = [
        "L2_colias_lower",
        "L2_agraulis_narrow",
        "L1_colias_upper",
        "L1_agraulis_wide",
        "L_vanessa_upper",
    ]
    species_spacings = {
        lbl: val for lbl, val in zip(dash_labels, dash_L_um)
    }

    # 2. Track the 3 smooth gray isocontours (0.1 nm, 1 nm, 10 nm) using local median background residual!
    med_bg = cv2.medianBlur(sub_u8, 25).astype(np.float32)
    diff_bg = np.linalg.norm(sub - med_bg, axis=2)
    is_gray = (diff_bg > 18.0) & (lum > 105.0) & (lum < 205.0) & (sat < 42.0)

    for cx in dash_x_px:
        ic = int(round(cx))
        is_gray[:, max(0, ic - 4):min(w, ic + 5)] = False

    def _mask_rect(l0: float, l1: float, g0: float, g1: float) -> None:
        c0 = max(0, int(round(x_cal.to_pixel(l0) - px0)))
        c1 = min(w, int(round(x_cal.to_pixel(l1) - px0)))
        r0 = max(0, int(round(y_cal.to_pixel(g1) - py0)))
        r1 = min(h, int(round(y_cal.to_pixel(g0) - py0)))
        is_gray[r0:r1, c0:c1] = False

    _mask_rect(0.18, 0.29, 0.04, 0.35)
    _mask_rect(0.42, 0.49, 0.04, 0.25)
    _mask_rect(0.50, 0.66, 0.38, 0.64)

    n_rows = 64
    rows = np.linspace(12, h - 12, n_rows).astype(int)

    contour_specs = [
        ("contour_0_1nm", (0.20, 0.27)),
        ("contour_1nm",   (0.32, 0.46)),
        ("contour_10nm",  (0.46, 0.85)),
    ]

    curves: dict[str, Any] = {}
    contour_intercepts: dict[str, list[float]] = {}

    for cname, (l_lo, l_hi) in contour_specs:
        c_lo = max(4, int(round(x_cal.to_pixel(l_lo) - px0)))
        c_hi = min(w - 5, int(round(x_cal.to_pixel(l_hi) - px0)))
        W_sub = c_hi - c_lo
        cost = np.full((W_sub, n_rows), 2.5, dtype=np.float64)
        for ti, ry in enumerate(rows):
            r0_w, r1_w = max(0, ry - 2), min(h, ry + 3)
            g_hit = is_gray[r0_w:r1_w, c_lo:c_hi].any(axis=0)
            d_loc = diff_bg[r0_w:r1_w, c_lo:c_hi].max(axis=0)
            cost[:, ti] = np.where(g_hit, np.clip(1.0 - d_loc / 80.0, 0.05, 0.9), 2.4)

        # Track x(y) from top (g=0.72) down to bottom (g=0.0)
        x_path = viterbi_track(cost, max_step=14, smooth_w=0.12, norm="l1") + c_lo
        # Smooth monotonic rightward drift as g decreases (smaller g needs larger L for same amplitude!)
        x_mono = np.maximum.accumulate(x_path)

        xs_v = [round(x_cal.to_value(px0 + float(cx)), 4) for cx in x_mono]
        ys_v = [round(max(0.0, y_cal.to_value(py0 + float(ry))), 4) for ry in rows]
        contour_intercepts[cname] = [xs_v[0], xs_v[-1]]
        curves[cname] = {
            "x": xs_v,
            "y": ys_v,
            "L_at_top_um": xs_v[0],
            "L_at_g0_um": xs_v[-1],
            "x_unit": "µm",
            "y_unit": "%",
        }

    # Also add the 5 vertical empirical spacing lines as clean 2-point vertical reference lines
    # so they render directly over the dashed lines in the QA overlay!
    g_top = round(y_cal.to_value(py0 + 6), 4)
    for lbl, l_val in species_spacings.items():
        curves[lbl] = {
            "x": [l_val, l_val],
            "y": [0.0, g_top],
            "x_unit": "µm",
            "y_unit": "%",
        }

    return {
        "curves": curves,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": [round(x_cal.to_value(px0), 4), round(x_cal.to_value(px1), 4)],
            "y_range": [round(y_cal.to_value(py1), 4), round(y_cal.to_value(py0), 4)],
            "x_misfit_px": x_cal.misfit_px,
            "y_misfit_px": y_cal.misfit_px,
            "kind": "curves",
        },
        "extracted_data": {
            "x_tick_misfit_px": x_cal.misfit_px,
            "y_tick_misfit_px": y_cal.misfit_px,
            "species_actin_spacings_um": species_spacings,
            "contour_L_spans_um": contour_intercepts,
        },
    }
