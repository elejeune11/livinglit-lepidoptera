"""Bespoke extractor for McDougal et al. (2021) Figure 2J and 2K (pnas.202112009fig02.jpg):
- F2/J: Surface height profile (nm) across longitudinal ridges at 83% pupal development (0–9 µm).
- F2/K: Surface height profile (nm) along a single ridge showing ridge lamellae height (0–9 µm).

Uses `find_axis_ticks` (ascending y_labels & x_labels) for subpixel tick calibration,
`ray_dist_alpha` for anti-aliased black ink detection, and `viterbi_track` (L1 DP) for
exact continuous profile tracing across 100% of the distance axis.
"""
from __future__ import annotations

from typing import Any
import numpy as np
from scipy.signal import find_peaks

from livinglit_lepidoptera.extract_lib import AxisCal, find_axis_ticks, ray_dist_alpha, viterbi_track


def _calibrate_panel(crop_rgb: np.ndarray, panel_id: str) -> dict[str, Any]:
    x_labels = [float(k) for k in range(10)]
    y_labels = [0.0, 100.0, 200.0, 300.0]
    if panel_id == "J":
        ax = find_axis_ticks(
            crop_rgb,
            y_labels=y_labels,
            x_labels=x_labels,
            dark_thr=185.0,
            probe=(0, 2),
            tick_min_frac=0.45,
        )
        return ax
    # In F2/K the 0-nm tick sits 3.5 px above the bottom spine, matching F2/J's exact 19.5 px/100 nm scale;
    # run find_axis_ticks for x_ticks and spine detection, then refine the 0-nm tick above the bottom spine.
    ax = find_axis_ticks(
        crop_rgb,
        y_labels=y_labels,
        x_labels=x_labels,
        dark_thr=185.0,
        probe=(0, 2),
        tick_min_frac=0.45,
    )
    px0, py0, px1, py1 = ax["plot_box"]
    g = crop_rgb.mean(axis=2)
    # Detect outward left y-ticks strictly above bottom spine py1 (leaving out spine bleed at py1+1)
    yt_hits = [r for r in range(py0 - 2, py1) if g[r, px0 - 2] < 195.0]
    # Group contiguous hits
    grps: list[list[int]] = []
    for r in yt_hits:
        if not grps or r > grps[-1][-1] + 2:
            grps.append([r])
        else:
            grps[-1].append(r)
    y_ticks = sorted([float(np.mean(gr)) for gr in grps], reverse=True)
    if len(y_ticks) == 3:
        # 0 nm tick sits right next to bottom spine; extrapolate evenly from 300, 200, 100 nm ticks
        step = 0.5 * (y_ticks[0] - y_ticks[2])
        y_ticks = [y_ticks[0] + step] + y_ticks
    if len(y_ticks) == 4:
        y_cal = AxisCal.fit(y_ticks, y_labels, scale="linear")
        ax["y_cal"] = y_cal
        ax["y_ticks"] = y_ticks
        ax["y_misfit_px"] = y_cal.misfit_px
    return ax


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    ax = _calibrate_panel(crop_rgb, panel_id)
    px0, py0, px1, py1 = ax["plot_box"]
    x_cal = ax["x_cal"]
    y_cal = ax["y_cal"]

    sub_f = crop_rgb[py0:py1, px0:px1].astype(np.float32)
    h, w = sub_f.shape[:2]

    # Compute black-ink opacity alpha along white -> black ray
    perp, alpha = ray_dist_alpha(sub_f, (15, 15, 15), bg_rgb=(255.0, 255.0, 255.0))
    # Mask panel label letter ("J" or "K") in top-left corner inside plot box
    alpha[:16, :18] = 0.0
    # Reject saturated colors if any and require close to grayscale ray
    ink = np.where(perp < 38.0, alpha, 0.0)

    # Trace continuous curve from first to last active ink column via L1 Viterbi DP
    col_max = ink.max(axis=0)
    active = np.where(col_max >= 0.28)[0]
    c0, c1 = int(active[0]), int(active[-1])
    sub_ink = ink[:, c0:c1 + 1]
    cost = 1.0 - np.clip(sub_ink, 0.0, 1.0)
    # Mild penalty for rows near top/bottom frame border (avoid snapping onto frame bleed)
    cost[0, :] += 0.35
    cost[-1, :] += 0.35
    path = viterbi_track(cost, max_step=16, smooth_w=0.14, norm="l1")

    # Subpixel vertical centroid refinement within +-1 px around Viterbi path
    xs: list[float] = []
    ys: list[float] = []
    for k, ry in enumerate(path):
        cx = c0 + k
        r0, r1 = max(0, int(ry) - 1), min(h, int(ry) + 2)
        wts = np.maximum(0.0, ink[r0:r1, cx])
        if float(wts.sum()) > 1e-4:
            py_sub = float(np.sum(np.arange(r0, r1) * wts) / wts.sum())
        else:
            py_sub = float(ry)
        xs.append(round(x_cal.to_value(px0 + cx), 3))
        ys.append(round(y_cal.to_value(py0 + py_sub), 2))

    # Quantify peaks and spacing along the profile
    arr_y = np.asarray(ys, dtype=np.float64)
    arr_x = np.asarray(xs, dtype=np.float64)
    pks, _ = find_peaks(arr_y, distance=12, prominence=25.0)
    peak_xs = [round(float(arr_x[i]), 2) for i in pks]
    peak_ys = [round(float(arr_y[i]), 1) for i in pks]
    mean_sp = round(float(np.mean(np.diff(arr_x[pks]))), 3) if len(pks) >= 2 else None

    series_name = "across_ridges_profile" if panel_id == "J" else "along_ridge_lamellae_profile"
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
            "peak_positions_um": peak_xs,
            "peak_heights_nm": peak_ys,
            "mean_peak_spacing_um": mean_sp,
        },
    }
