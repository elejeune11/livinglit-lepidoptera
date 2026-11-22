"""Bespoke extractor for Totz et al. (2024) Figure 3H (fig3.jpg):
Phase space of weakly nonlinear FvK buckling amplitude w_0 (nm) across log10 Young's modulus Y
(10^5 to 10^8 Pa) and linear growth strain g (0.0 to 0.725%), digitizing the 5 colored dashed
isocontours matching the mean in vivo protoridge amplitudes at 39.6%, 40.0%, 40.3%, 40.7%, and 41.0%.

Uses inward major-tick detection (`AxisCal` with x_scale='log10') + color-matched dash detection
and steep-climbing L1 Viterbi DP (`viterbi_track`).
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
    vc0_l, vc1_l = min(x[0] for x in v_clusters[0]), max(x[0] for x in v_clusters[0])
    vc0_r, vc1_r = min(x[0] for x in v_clusters[1]), max(x[0] for x in v_clusters[1])

    bh = [(r, *max(_runs(dk[r, vc0_l:vc1_r + 1]), key=lambda c: c[1] - c[0])) for r in range(h) if _runs(dk[r, vc0_l:vc1_r + 1])]
    bh = [x for x in bh if x[2] - x[1] + 1 >= 0.70 * (vc1_r - vc0_l)]
    r_bot = bh[-1][0]
    h_bot = [x for x in bh if r_bot - x[0] <= 8]
    hr0, hr1 = min(x[0] for x in h_bot), max(x[0] for x in h_bot)
    h_top = [x for x in bh if x[0] < hr0 - 200]
    p_top = max(x[0] for x in h_top if x[0] - h_top[0][0] <= 8) + 1

    yb = dk[:, vc1_l + 6:vc1_l + 18]
    y_hits = [r for r in np.flatnonzero(yb.mean(axis=1) >= 0.55).tolist() if p_top + 20 <= r <= hr0 - 20]
    y_ticks = [0.5 * (hr0 + hr1)] + sorted(_centres(y_hits, gap=5), reverse=True)
    y_cal = AxisCal.fit(y_ticks, [0.0, 0.2, 0.4, 0.6], scale="linear")

    xb_top = dk[p_top + 7:p_top + 16, :]
    x_hits = [c for c in np.flatnonzero(xb_top.mean(axis=0) >= 0.55).tolist() if vc1_l + 40 <= c <= vc0_r - 40]
    x_mid = sorted(_centres(x_hits, gap=5))
    x_ticks = [0.5 * (vc0_l + vc1_l)] + x_mid + [0.5 * (vc0_r + vc1_r)]
    x_cal = AxisCal.fit(x_ticks, [1e5, 1e6, 1e7, 1e8], scale="log10")

    return {"plot_box": (vc1_l + 1, p_top, vc0_r - 1, hr0 - 1), "x_cal": x_cal, "y_cal": y_cal}


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    cal = _detect_axes(crop_rgb)
    px0, py0, px1, py1 = cal["plot_box"]
    x_cal, y_cal = cal["x_cal"], cal["y_cal"]

    sub = crop_rgb[py0:py1, px0:px1].astype(np.float32)
    h, w = sub.shape[:2]

    # Black outline framing each colored dash (only mask thin 8px bottom minor ticks so steep legs reach g=0!)
    sat = sub.max(axis=2) - sub.min(axis=2)
    lum = sub.mean(axis=2)
    is_black_outline = (lum < 95.0) & (sat < 70.0)
    is_black_outline[:22, :] = False
    is_black_outline[-8:, :] = False
    is_black_outline[:, :22] = False
    is_black_outline[:, -22:] = False

    # Dilate slightly so the colored interior core of every dash sits inside dash_band
    dash_band = cv2.dilate(is_black_outline.astype(np.uint8), np.ones((15, 7), np.uint8)) > 0

    specs = [
        ("iso_41_0pct_purple", (191, 112, 255), 3.40e5, (0.0, 0.65)),
        ("iso_40_7pct_pink",   (217, 95, 156),  1.05e6, (0.0, 0.34)),
        ("iso_40_3pct_coral",  (237, 101, 84),  1.08e6, (0.0, 0.34)),
        ("iso_40_0pct_orange", (245, 138, 32),  1.78e6, (0.0, 0.25)),
        ("iso_39_6pct_yellow", (255, 199, 0),   3.50e6, (0.0, 0.18)),
    ]

    color_maps = {}
    for name, rgb, _, _ in specs:
        t = np.array(rgb, dtype=np.float32)
        color_maps[name] = np.linalg.norm(sub - t[None, None, :], axis=2)

    curves: dict[str, Any] = {}
    asymptotes: dict[str, float] = {}

    for name, rgb, y_start_pa, (g_lo, g_hi) in specs:
        # Auto-detect the exact column where this colored dash exits the bottom g=0 axis (within ±35 px of nominal)
        c_nom = int(round(x_cal.to_pixel(y_start_pa) - px0))
        d_own = color_maps[name]
        bot_band = (d_own[h - 32:h - 4, max(4, c_nom - 35):min(w - 4, c_nom + 35)] < 75.0)
        if np.any(bot_band):
            _, bx = np.where(bot_band)
            c_start = max(4, c_nom - 35) + int(np.percentile(bx, 15))
        else:
            c_start = max(4, c_nom)

        c_end = w - 6
        n_pts = 110
        cols = np.linspace(c_start, c_end, n_pts).astype(int)

        r_top_lim = max(2, int(round(y_cal.to_pixel(g_hi) - py0)))
        r_bot_lim = min(h - 2, int(round(y_cal.to_pixel(g_lo) - py0)))

        siblings = [
            color_maps[o]
            for o, _, _, _ in specs
            if o != name and not ({name, o} == {"iso_40_7pct_pink", "iso_40_3pct_coral"})
        ]
        d_sib = np.minimum.reduce(siblings)

        cost = np.full((h, n_pts), 4.0, dtype=np.float64)
        for ti, cx in enumerate(cols):
            # Use narrow ±6 px horizontal window on the steep ascending left leg so vertical slope isn't smeared,
            # widening to ±12 px on the flat horizontal asymptote to bridge inter-dash gaps smoothly
            hw = 6 if ti < 25 else 12
            c0_w, c1_w = max(0, cx - hw), min(w, cx + hw + 1)
            d_loc = d_own[:, c0_w:c1_w].min(axis=1)
            ds_loc = d_sib[:, c0_w:c1_w].min(axis=1)
            db_loc = dash_band[:, c0_w:c1_w].any(axis=1)
            good = db_loc & (d_loc < 78.0) & (d_loc <= ds_loc + 8.0)
            col_c = np.where(good, d_loc / 85.0, 3.2)
            col_c[:r_top_lim] = 10.0
            col_c[r_bot_lim + 1:] = 10.0
            if ti == 0:
                col_c[h - 10:] = np.minimum(col_c[h - 10:], 0.05)
            cost[:, ti] = col_c

        # Large max_step=75 + gentle L1 slope penalty lets Viterbi climb the steep left leg cleanly from g=0!
        path = viterbi_track(cost, max_step=75, smooth_w=0.014, norm="l1")
        path_mono = np.minimum.accumulate(path)

        xs_v: list[float] = []
        ys_v: list[float] = []
        for cx, py in zip(cols, path_mono):
            yv = max(0.0, y_cal.to_value(py0 + float(py)))
            xs_v.append(round(x_cal.to_value(px0 + float(cx)), 1))
            ys_v.append(round(yv, 4))

        asymptotes[name] = ys_v[-1]
        curves[name] = {
            "x": xs_v,
            "y": ys_v,
            "start_Y_Pa": xs_v[0],
            "asymptotic_g_pct": ys_v[-1],
            "x_unit": "Pa",
            "y_unit": "%",
        }

    return {
        "curves": curves,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": [round(x_cal.to_value(px0), 2), round(x_cal.to_value(px1), 2)],
            "y_range": [round(y_cal.to_value(py1), 4), round(y_cal.to_value(py0), 4)],
            "x_scale": "log10",
            "x_misfit_px": x_cal.misfit_px,
            "y_misfit_px": y_cal.misfit_px,
            "kind": "curves",
        },
        "extracted_data": {
            "x_tick_misfit_px": x_cal.misfit_px,
            "y_tick_misfit_px": y_cal.misfit_px,
            "asymptotic_growth_strain_pct": asymptotes,
            "y_min_bound_Pa": 3500000.0,
        },
    }
