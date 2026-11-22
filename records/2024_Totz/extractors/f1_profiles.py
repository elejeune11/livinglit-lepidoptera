"""Bespoke extractor for Totz et al. (2024) Figure 1E, 1F, 1G (fig1.jpg):
In vivo speckle-correlation reflection phase microscopy centerline height profiles
across nascent Vanessa cardui protoridges at 35.8% (E), 40.0% (F), and 41.0% (G)
of pupal development.

Uses inward tick detection (`AxisCal`) + L1 Viterbi DP (`viterbi_track`) on monochrome
dark ink while masking the z/x coordinate triad inset in panel 1E.
"""
from __future__ import annotations

from typing import Any
import numpy as np

from livinglit_lepidoptera.extract_lib import AxisCal, viterbi_track


def _detect_box_and_ticks(crop_rgb: np.ndarray) -> dict[str, Any]:
    f = crop_rgb.astype(np.float32)
    h, w = f.shape[:2]
    sat = f.max(axis=2) - f.min(axis=2)
    dk = (f.mean(axis=2) < 135.0) & (sat < 45.0)

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
    bv = [x for x in bv if x[2] - x[1] + 1 >= 0.40 * h]
    c_left = bv[0][0]
    v_left = [x for x in bv if x[0] - c_left <= 4]
    vc1 = max(x[0] for x in v_left)
    v_right = [x for x in bv if x[0] > vc1 + 30]
    p_right = min(x[0] for x in v_right if v_right[-1][0] - x[0] <= 4) - 1

    bh = [(r, *max(_runs(dk[r, :]), key=lambda c: c[1] - c[0])) for r in range(h) if _runs(dk[r, :])]
    bh = [x for x in bh if x[2] - x[1] + 1 >= 0.45 * w]
    r_bot = bh[-1][0]
    h_bot = [x for x in bh if r_bot - x[0] <= 4]
    hr0 = min(x[0] for x in h_bot)
    h_top = [x for x in bh if x[0] < hr0 - 30]
    p_top = max(x[0] for x in h_top if x[0] - h_top[0][0] <= 4) + 1

    # Inward y-ticks at 0, 50, 100 nm along left spine (depth 1..5 px)
    yb = dk[:, vc1 + 1:vc1 + 5]
    y_hits = [r for r in np.flatnonzero(yb.mean(axis=1) >= 0.50).tolist() if p_top + 3 <= r <= hr0 - 3]
    y_ticks = sorted(_centres(y_hits, gap=3), reverse=True)
    y_cal = AxisCal.fit(y_ticks, [0.0, 50.0, 100.0], scale="linear")

    # Inward x-ticks at 0, 1, 2, 3, 4, 5 µm along bottom spine (1..3 px above hr0)
    xb = dk[hr0 - 2:hr0, :]
    x_hits = [c for c in np.flatnonzero(xb.mean(axis=0) >= 0.45).tolist() if vc1 + 15 <= c <= p_right - 15]
    x_ticks = sorted(_centres(x_hits, gap=4))
    x_cal = AxisCal.fit(x_ticks, [0.0, 1.0, 2.0, 3.0, 4.0, 5.0], scale="linear")

    return {"plot_box": (vc1 + 1, p_top, p_right, hr0 - 1), "x_cal": x_cal, "y_cal": y_cal}


_STAGES = {
    "E": "profile_35_8pct",
    "F": "profile_40_0pct",
    "G": "profile_41_0pct",
}


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    cal = _detect_box_and_ticks(crop_rgb)
    px0, py0, px1, py1 = cal["plot_box"]
    x_cal, y_cal = cal["x_cal"], cal["y_cal"]

    sub = crop_rgb[py0:py1, px0:px1].astype(np.float32).copy()
    h, w = sub.shape[:2]

    # Mask the small z/x coordinate axes inset in upper-right of 1E
    if panel_id == "E":
        sub[:int(0.68 * h), int(0.73 * w):] = 255.0

    # Mask inward ticks near borders (5 px left/right, 4 px bottom/top)
    sub[:3, :] = 255.0
    sub[-4:, :] = 255.0
    sub[:, :5] = 255.0
    sub[:, -5:] = 255.0

    gray = sub.mean(axis=2)
    dark = np.clip(255.0 - gray, 0.0, 255.0)
    # Find valid x-range where profile line exists
    col_max = dark.max(axis=0)
    valid_cols = np.where(col_max > 95.0)[0]
    c_start, c_end = int(valid_cols[0]), int(valid_cols[-1])

    # Viterbi L1 tracking along dark curve ink
    n_pts = 90
    xs_cols = np.linspace(c_start, c_end, n_pts).astype(int)
    cost = np.zeros((h, n_pts), dtype=np.float64)
    for ti, cx in enumerate(xs_cols):
        band = dark[:, max(0, cx - 1):min(w, cx + 2)].max(axis=1)
        cost[:, ti] = np.where(band >= 45.0, (255.0 - band) / 255.0, 2.2)

    path = viterbi_track(cost, max_step=16, smooth_w=0.06, norm="l1")

    # Refine each column to weighted ink centroid within ±3 px of Viterbi path
    xs_val: list[float] = []
    ys_val: list[float] = []
    for cx, py in zip(xs_cols, path):
        r0, r1 = max(0, int(py) - 3), min(h, int(py) + 4)
        wts = np.clip(dark[r0:r1, cx] - 30.0, 0.0, 255.0)
        py_ref = float(r0 + np.sum(np.arange(r1 - r0) * wts) / float(wts.sum())) if wts.sum() > 10.0 else float(py)
        xs_val.append(round(x_cal.to_value(px0 + float(cx)), 4))
        ys_val.append(round(y_cal.to_value(py0 + py_ref), 2))

    pk_i = int(np.argmax(ys_val))
    tr_i = int(np.argmin(ys_val))
    series_name = _STAGES[panel_id]
    curves = {
        series_name: {
            "x": xs_val,
            "y": ys_val,
            "peak_x": xs_val[pk_i],
            "peak_y": ys_val[pk_i],
            "trough_y": ys_val[tr_i],
            "ptp_nm": round(ys_val[pk_i] - ys_val[tr_i], 2),
            "x_unit": "µm",
            "y_unit": "nm",
        }
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
            "peak_height_nm": ys_val[pk_i],
            "min_height_nm": ys_val[tr_i],
            "peak_to_trough_nm": round(ys_val[pk_i] - ys_val[tr_i], 2),
        },
    }
