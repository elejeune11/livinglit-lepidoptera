"""Bespoke extractor for Totz et al. (2024) Figure 2E sub-plots (fig2.jpg):
- E_g: Growth strain g sweep (0.0%, 0.5%, 1.0%)
- E_Y: Young's modulus Y sweep (10^5 Pa, 10^6 Pa, 10^8 Pa)
- E_L: Actin bundle distance L sweep (0.5L, 1.0L, 1.5L)
- E_p: Transmembrane pressure p sweep (10 Pa, 50 Pa, 100 Pa)

Uses inward tick detection (`AxisCal`), color-ray decomposition (`ray_dist_alpha`),
and L1 Viterbi DP (`viterbi_track`) to track all 12 weakly nonlinear FvK profiles.
"""
from __future__ import annotations

from typing import Any
import numpy as np

from livinglit_lepidoptera.extract_lib import AxisCal, ray_dist_alpha, viterbi_track


_TRACE_SPECS: dict[str, dict[str, Any]] = {
    "E_g": {
        "legend_box": (0.48, 0.0, 1.0, 0.38),
        "traces": [
            ("g_1_0pct", (0, 1, 117),     (-0.50, 0.50)),
            ("g_0_5pct", (0, 3, 252),     (-0.50, 0.50)),
            ("g_0_0pct", (180, 177, 254), (-0.50, 0.50)),
        ],
    },
    "E_Y": {
        "legend_box": (0.48, 0.0, 1.0, 0.36),
        "traces": [
            ("Y_1e8Pa", (0, 129, 129),   (-0.50, 0.50)),
            ("Y_1e6Pa", (3, 252, 254),   (-0.50, 0.50)),
            ("Y_1e5Pa", (180, 255, 254), (-0.50, 0.50)),
        ],
    },
    "E_L": {
        "legend_box": (0.48, 0.0, 1.0, 0.38),
        "traces": [
            ("L_1_5x", (64, 0, 70),      (-0.74, 0.74)),
            ("L_1_0x", (130, 0, 129),    (-0.50, 0.50)),
            ("L_0_5x", (214, 179, 212),  (-0.25, 0.25)),
        ],
    },
    "E_p": {
        "legend_box": (0.45, 0.0, 1.0, 0.36),
        "traces": [
            ("p_100Pa", (1, 124, 0),     (-0.50, 0.50)),
            ("p_50Pa",  (0, 255, 4),     (-0.50, 0.50)),
            ("p_10Pa",  (179, 253, 178), (-0.50, 0.50)),
        ],
    },
}


def _detect_axes(crop_rgb: np.ndarray) -> dict[str, Any]:
    f = crop_rgb.astype(np.float32)
    h, w = f.shape[:2]
    sat = f.max(axis=2) - f.min(axis=2)
    dk = (f.mean(axis=2) < 130.0) & (sat < 45.0)

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
    v_left = [x for x in bv if x[0] - c_left <= 6]
    vc1 = max(x[0] for x in v_left)
    v_right = [x for x in bv if x[0] > vc1 + 50]
    p_right = min(x[0] for x in v_right if v_right[-1][0] - x[0] <= 6) - 1

    bh = [(r, *max(_runs(dk[r, :]), key=lambda c: c[1] - c[0])) for r in range(h) if _runs(dk[r, :])]
    bh = [x for x in bh if x[2] - x[1] + 1 >= 0.45 * w]
    r_bot = bh[-1][0]
    h_bot = [x for x in bh if r_bot - x[0] <= 6]
    hr0, hr1 = min(x[0] for x in h_bot), max(x[0] for x in h_bot)
    h_top = [x for x in bh if x[0] < hr0 - 50]
    p_top = max(x[0] for x in h_top if x[0] - h_top[0][0] <= 6) + 1

    # Y ticks: bottom frame = 0 nm plus 4 inward ticks at 100, 200, 300, 400 nm
    yb = dk[:, vc1 + 2:vc1 + 6]
    y_hits = [r for r in np.flatnonzero(yb.mean(axis=1) >= 0.55).tolist() if p_top + 10 <= r <= hr0 - 15]
    y_ticks = [0.5 * (hr0 + hr1)] + sorted(_centres(y_hits, gap=4), reverse=True)
    y_cal = AxisCal.fit(y_ticks, [0.0, 100.0, 200.0, 300.0, 400.0], scale="linear")

    # X ticks: probe TOP frame inward (clean of curves touching y=0!) for [-0.5, -0.25, 0, 0.25, 0.5]
    xb = dk[p_top + 1:p_top + 5, :]
    x_hits = [c for c in np.flatnonzero(xb.mean(axis=0) >= 0.50).tolist() if vc1 + 15 <= c <= p_right - 15]
    x_ticks = sorted(_centres(x_hits, gap=4))
    if len(x_ticks) == 5:
        x_cal = AxisCal.fit(x_ticks, [-0.5, -0.25, 0.0, 0.25, 0.5], scale="linear")
    else:
        # Fallback: exact symmetric [-0.75, +0.75] frame span
        x_cal = AxisCal.fit([float(vc1 + 1), float(p_right)], [-0.742, 0.742], scale="linear")

    return {"plot_box": (vc1 + 1, p_top, p_right, hr0 - 1), "x_cal": x_cal, "y_cal": y_cal}


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    spec = _TRACE_SPECS[panel_id]
    cal = _detect_axes(crop_rgb)
    px0, py0, px1, py1 = cal["plot_box"]
    x_cal, y_cal = cal["x_cal"], cal["y_cal"]

    sub = crop_rgb[py0:py1, px0:px1].astype(np.float32).copy()
    h, w = sub.shape[:2]

    # Mask top-right legend region cleanly
    lx0, ly0, lx1, ly1 = spec["legend_box"]
    sub[int(ly0 * h):int(ly1 * h), int(lx0 * w):int(lx1 * w)] = 255.0

    # Precompute Euclidean distance to each target trace RGB for clean winner-take-all separation
    # (critical because same-hue light/medium/dark curves lie on nearly collinear white->color rays!)
    dists = {}
    alphas = {}
    for tname, rgb, _ in spec["traces"]:
        t_arr = np.array(rgb, dtype=np.float32)
        dists[tname] = np.linalg.norm(sub - t_arr[None, None, :], axis=2)
        perp, alpha = ray_dist_alpha(sub, rgb)
        alphas[tname] = (perp, alpha)

    # Also compute distance to pure white background so pale traces aren't confused with white
    w_dist = np.linalg.norm(sub - 255.0, axis=2)
    # Mask neutral dark ticks/axes (low saturation + dark)
    sat = sub.max(axis=2) - sub.min(axis=2)
    is_neutral_dark = (sat < 14.0) & (sub.mean(axis=2) < 180.0)

    curves: dict[str, Any] = {}
    peaks: dict[str, float] = {}
    n_pts = 75

    for tname, rgb, (x_lo, x_hi) in spec["traces"]:
        c0 = max(1, int(round(x_cal.to_pixel(x_lo) - px0)))
        c1 = min(w - 2, int(round(x_cal.to_pixel(x_hi) - px0)))
        cols = np.linspace(c0, c1, n_pts).astype(int)

        d_own = dists[tname]
        others = [dists[o] for o, _, _ in spec["traces"] if o != tname]
        d_other = np.minimum.reduce(others)
        perp, _ = alphas[tname]

        # Cost favors pixels close to this exact RGB, not closer to sibling traces, and non-white
        cost = np.full((h, n_pts), 4.0, dtype=np.float64)
        for ti, cx in enumerate(cols):
            do = d_own[:, cx]
            dt = d_other[:, cx]
            wd = w_dist[:, cx]
            nd = is_neutral_dark[:, cx]
            # Strong match when closer to own RGB than siblings and clearly off white
            good = (do < 68.0) & (wd > 22.0) & (~nd) & (do <= dt + 10.0)
            col_c = np.where(good, do / 70.0 + 0.015 * np.maximum(0.0, do - dt), 3.5)
            # At exact endpoints x_lo / x_hi, encourage clamping smoothly to y=0 (bottom row h-1)
            if ti in (0, n_pts - 1):
                col_c[-4:] = np.minimum(col_c[-4:], 0.35)
            cost[:, ti] = col_c

        path = viterbi_track(cost, max_step=18, smooth_w=0.05, norm="l1")

        xs_v: list[float] = []
        ys_v: list[float] = []
        for cx, py in zip(cols, path):
            r0, r1 = max(0, int(py) - 4), min(h, int(py) + 5)
            d_loc = d_own[r0:r1, cx]
            good_loc = (d_loc < 70.0) & (w_dist[r0:r1, cx] > 20.0)
            if np.any(good_loc):
                wts = np.where(good_loc, np.clip(75.0 - d_loc, 0.1, 75.0), 0.0)
                py_ref = float(r0 + np.sum(np.arange(r1 - r0) * wts) / float(wts.sum()))
            else:
                py_ref = float(py)
            yv = max(0.0, y_cal.to_value(py0 + py_ref))
            xs_v.append(round(x_cal.to_value(px0 + float(cx)), 4))
            ys_v.append(round(yv, 2))

        pk_i = int(np.argmax(ys_v))
        peaks[tname] = ys_v[pk_i]
        curves[tname] = {
            "x": xs_v,
            "y": ys_v,
            "peak_x": xs_v[pk_i],
            "peak_y": ys_v[pk_i],
            "x_unit": "x/L",
            "y_unit": "nm",
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
            "x_tick_misfit_px": x_cal.misfit_px,
            "y_tick_misfit_px": y_cal.misfit_px,
            "peak_amplitudes_nm": peaks,
        },
    }
