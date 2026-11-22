"""Bespoke extractor for McDougal et al. (2021) Figure 5A (Bottom) and 5B (Bottom) (pnas.202112009fig05.jpg):
- F5/A_bot: Unwrapped phase height profile h (nm) at 35% pupal development (smooth scale surface, 0–7 µm).
- F5/B_bot: Unwrapped phase height profile h (nm) at 41% pupal development (~100 nm regular proto-ridges, 0–7 µm).

Calibrates axes from detected inward right-spine y-ticks ([0, 50, 100, 150] nm) and bottom-spine
x-ticks ([0, 2, 4, 6] µm) via `AxisCal.fit`, then traces the continuous profile via `ray_dist_alpha`
+ L1 `viterbi_track`.
"""
from __future__ import annotations

from typing import Any
import numpy as np
from scipy.signal import find_peaks

from livinglit_lepidoptera.extract_lib import AxisCal, ray_dist_alpha, viterbi_track


def _group_centres(idx: list[int], gap: int = 2) -> list[float]:
    if not idx:
        return []
    groups: list[list[int]] = [[int(idx[0])]]
    for i in idx[1:]:
        if int(i) - groups[-1][-1] <= gap:
            groups[-1].append(int(i))
        else:
            groups.append([int(i)])
    return [float(np.mean(g)) for g in groups]


def _detect_box_and_inward_ticks(crop_rgb: np.ndarray) -> dict[str, Any]:
    f = crop_rgb.astype(np.float32)
    h, w = f.shape[:2]
    g = f.mean(axis=2)
    dk = g < 160.0

    # Find left/right vertical spines and top/bottom horizontal spines
    v_cols = [c for c in range(w) if dk[:, c].sum() >= 0.42 * h]
    h_rows = [r for r in range(h) if dk[r, :].sum() >= 0.42 * w]
    vc_l, vc_r = min(v_cols), max(v_cols)
    hr_t, hr_b = min(h_rows), max(h_rows)

    # Symmetric left & right spine inward y-ticks: 0, 50, 100, 150 nm
    y_hits = [r for r in range(hr_t + 1, hr_b) if g[r, vc_r - 1] < 215.0 and g[r, vc_l + 1] < 225.0]
    y_cands = sorted(_group_centres(y_hits, gap=2), reverse=True)
    y_labels = [0.0, 50.0, 100.0, 150.0]
    if len(y_cands) < 4:
        raise ValueError(f"Expected >=4 symmetric y-ticks, found {len(y_cands)} at {y_cands}")
    if len(y_cands) > 4:
        from itertools import combinations
        best_cal, best_ticks = None, None
        for comb in combinations(y_cands, 4):
            cand = list(comb)
            # Require uniform step > 6 px so a curve touch next to a tick cannot win
            diffs = [cand[i] - cand[i + 1] for i in range(3)]
            if min(diffs) < 6.0:
                continue
            cal = AxisCal.fit(cand, y_labels, scale="linear")
            if best_cal is None or cal.misfit_px < best_cal.misfit_px:
                best_cal, best_ticks = cal, cand
        if best_cal is None:
            raise ValueError(f"No valid evenly spaced 4-tick progression among {y_cands}")
        y_cal = best_cal
    else:
        y_cal = AxisCal.fit(y_cands, y_labels, scale="linear")

    # Top spine inward x-ticks: 0, 2, 4, 6 um (clean from curve touches at bottom!)
    x_hits = [c for c in range(vc_l + 2, vc_r - 1) if g[hr_t + 1, c] < 210.0]
    x_ticks = sorted(_group_centres(x_hits, gap=2))
    x_labels = [0.0, 2.0, 4.0, 6.0]
    if len(x_ticks) != 4:
        raise ValueError(f"Expected 4 top-spine x-ticks, found {len(x_ticks)} at {x_ticks}")
    x_cal = AxisCal.fit(x_ticks, x_labels, scale="linear")

    return {
        "plot_box": (vc_l + 1, hr_t + 1, vc_r - 1, hr_b - 1),
        "x_cal": x_cal,
        "y_cal": y_cal,
        "x_misfit_px": x_cal.misfit_px,
        "y_misfit_px": y_cal.misfit_px,
    }


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    ax = _detect_box_and_inward_ticks(crop_rgb)
    px0, py0, px1, py1 = ax["plot_box"]
    x_cal = ax["x_cal"]
    y_cal = ax["y_cal"]

    sub_f = crop_rgb[py0:py1, px0:px1].astype(np.float32)
    h, w = sub_f.shape[:2]

    perp, alpha = ray_dist_alpha(sub_f, (15, 15, 15), bg_rgb=(255.0, 255.0, 255.0))
    ink = np.where(perp < 42.0, alpha, 0.0)
    # Suppress 1-px inward tick stubs at top/bottom/left/right border edges
    ink[0:2, :] = 0.0
    ink[-2:, :] = 0.0
    ink[:, 0:1] = 0.0
    ink[:, -1:] = 0.0

    col_max = ink.max(axis=0)
    active = np.where(col_max >= 0.25)[0]
    c0, c1 = int(active[0]), int(active[-1])
    sub_ink = ink[:, c0:c1 + 1]
    cost = 1.0 - np.clip(sub_ink, 0.0, 1.0)
    path = viterbi_track(cost, max_step=10, smooth_w=0.14, norm="l1")

    xs: list[float] = []
    ys: list[float] = []
    for k, ry in enumerate(path):
        cx = c0 + k
        r0, r1 = max(0, int(ry) - 1), min(h, int(ry) + 2)
        wts = np.maximum(0.0, ink[r0:r1, cx])
        py_sub = float(np.sum(np.arange(r0, r1) * wts) / wts.sum()) if float(wts.sum()) > 1e-4 else float(ry)
        xs.append(round(x_cal.to_value(px0 + cx), 3))
        ys.append(round(y_cal.to_value(py0 + py_sub), 2))

    arr_x = np.asarray(xs, dtype=np.float64)
    arr_y = np.asarray(ys, dtype=np.float64)
    pks, _ = find_peaks(arr_y, distance=10, prominence=25.0)
    mean_sp = round(float(np.mean(np.diff(arr_x[pks]))), 3) if len(pks) >= 2 else None

    series_name = "surface_height_35pct" if panel_id == "A_bot" else "proto_ridge_height_41pct"
    x_min, x_max = round(x_cal.to_value(px0), 4), round(x_cal.to_value(px1), 4)
    y_min, y_max = round(y_cal.to_value(py1), 4), round(y_cal.to_value(py0), 4)

    return {
        "curves": {
            series_name: {
                "x": xs,
                "y": ys,
                "peak_x": xs[int(np.argmax(ys))],
                "peak_y": max(ys),
                "x_unit": "µm",
                "y_unit": "nm",
            }
        },
        "overlay_meta": {
            "plot_box": [int(px0), int(py0), int(px1), int(py1)],
            "x_range": [x_min, x_max],
            "y_range": [y_min, y_max],
            "x_misfit_px": round(float(ax["x_misfit_px"]), 3),
            "y_misfit_px": round(float(ax["y_misfit_px"]), 3),
            "kind": "curves",
        },
        "extracted_data": {
            "x_tick_misfit_px": round(float(ax["x_misfit_px"]), 3),
            "y_tick_misfit_px": round(float(ax["y_misfit_px"]), 3),
            "height_min_nm": round(float(arr_y.min()), 1),
            "height_max_nm": round(float(arr_y.max()), 1),
            "peak_to_trough_nm": round(float(arr_y.max() - arr_y.min()), 1),
            "n_peaks": int(len(pks)),
            "mean_proto_ridge_spacing_um": mean_sp,
        },
    }
