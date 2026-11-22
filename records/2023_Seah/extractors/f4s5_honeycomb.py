"""Bespoke extractor for Seah & Saranathan (2023) Figure 4—figure supplement 5A and 5D
(elife-89082-fig4-figsupp5.jpg):
- Panel A: Parides eurimedes adult honeycomb lattice height (nm) violins + boxplots across
  5 pupal injection groups (52% Control, 52% Treatment, 57% Control, 57% Treatment, 67% Control).
- Panel D: Parides iphidamas adult honeycomb lattice height (nm) violins + boxplots across
  2 pupal injection groups (52% Control, 52% Treatment).

Automatically detects the ggplot2 frame spines, all 4 y-axis tick marks (0, 1000, 2000, 3000 nm)
with sub-pixel RMS linear calibration (`AxisCal`), bottom category ticks, white IQR box bounds,
black median bars, vertical whiskers, and circular ggplot2 outlier dots.
"""
from __future__ import annotations

from typing import Any
import cv2
import numpy as np

from livinglit_lepidoptera.extract_lib import AxisCal


def _group_segments(indices: np.ndarray, max_gap: int = 2) -> list[tuple[int, int]]:
    segs: list[list[int]] = []
    for idx in indices:
        i = int(idx)
        if not segs or i > segs[-1][1] + max_gap:
            segs.append([i, i])
        else:
            segs[-1][1] = i
    return [(s[0], s[1]) for s in segs]


def _detect_frame_and_ticks(
    crop_rgb: np.ndarray,
    y_labels: list[float],
    n_groups: int,
) -> tuple[tuple[int, int, int, int], AxisCal, float, list[int]]:
    gray = crop_rgb.astype(np.float64).mean(axis=2)
    dark = gray < 105.0
    v_cols = np.where(dark.mean(axis=0) > 0.60)[0]
    h_rows = np.where(dark.mean(axis=1) > 0.60)[0]
    if len(v_cols) < 2 or len(h_rows) < 2:
        raise ValueError("Could not detect ggplot2 panel frame borders")
    lx, rx = int(v_cols[0]), int(v_cols[-1])
    ty, by = int(h_rows[0]), int(h_rows[-1])

    # Left y-axis tick marks protruding left of lx
    tick_strip = gray[ty:by, max(0, lx - 6):max(1, lx - 1)].min(axis=1)
    y_segs = _group_segments(np.where(tick_strip < 185.0)[0] + ty, max_gap=2)
    y_ticks_px = [0.5 * (s0 + s1) for s0, s1 in y_segs]
    if len(y_ticks_px) != len(y_labels):
        raise ValueError(f"Expected {len(y_labels)} y-ticks, found {len(y_ticks_px)} at {y_ticks_px}")

    # Linear fit via AxisCal.fit (descending y_labels: 3000 -> 0)
    vals_desc = sorted(y_labels, reverse=True)
    y_cal = AxisCal.fit(y_ticks_px, vals_desc, scale="linear")
    rms_px = float(y_cal.misfit_px)

    # Bottom x-axis tick marks protruding below by
    btick_strip = gray[min(gray.shape[0] - 1, by + 2):min(gray.shape[0], by + 7), lx:rx].min(axis=0)
    x_segs = _group_segments(np.where(btick_strip < 185.0)[0] + lx, max_gap=2)
    x_centers = [int(round(0.5 * (s0 + s1))) for s0, s1 in x_segs]
    if len(x_centers) != n_groups:
        raise ValueError(f"Expected {n_groups} bottom ticks, found {len(x_centers)} at {x_centers}")

    return (lx, ty, rx, by), y_cal, rms_px, x_centers


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    if panel_id == "A":
        gnames = [
            "52pct_control",
            "52pct_treatment",
            "57pct_control",
            "57pct_treatment",
            "67pct_control",
        ]
        y_labels = [0.0, 1000.0, 2000.0, 3000.0]
        box_hw = 12
    elif panel_id == "D":
        gnames = [
            "52pct_control",
            "52pct_treatment",
        ]
        y_labels = [0.0, 1000.0, 2000.0, 3000.0]
        box_hw = 22
    else:
        raise ValueError(f"Unsupported F4S5 panel_id: {panel_id}")

    (lx, ty, rx, by), y_cal, rms_px, x_centers_abs = _detect_frame_and_ticks(
        crop_rgb, y_labels=y_labels, n_groups=len(gnames)
    )
    sub = crop_rgb[ty:by, lx:rx].astype(np.float64)
    ph, pw = sub.shape[:2]
    y_max = round(float(y_cal.to_value(ty)), 2)
    y_min = round(float(y_cal.to_value(by)), 2)

    # Lavender/purple ggplot2 violin fill mask
    purple = (sub[:, :, 2] - sub[:, :, 0] > 18.0) & (sub[:, :, 2] - sub[:, :, 1] > 18.0) & (sub[:, :, 2] > 145.0)
    gray_sub = sub.mean(axis=2)

    boxplots: dict[str, Any] = {}
    outliers_scatter: dict[str, Any] = {}
    groups_meta: dict[str, Any] = {}

    for gname, cx_abs in zip(gnames, x_centers_abs):
        cx = cx_abs - lx
        # Locate white IQR box interior bordered laterally by purple violin body
        inner_hw = max(4, box_hw // 2)
        c_lum = gray_sub[:, max(0, cx - inner_hw):min(pw, cx + inner_hw + 1)].mean(axis=1)
        flank_l = purple[:, max(0, cx - box_hw - 16):max(1, cx - box_hw - 2)].any(axis=1)
        flank_r = purple[:, min(pw - 1, cx + box_hw + 2):min(pw, cx + box_hw + 16)].any(axis=1)
        in_box = (c_lum > 238.0) & flank_l & flank_r
        rows = np.where(in_box)[0]
        if len(rows) < 4:
            raise ValueError(f"{panel_id}/{gname}: white IQR box not found at cx={cx}")

        r_top, r_bot = int(rows.min()), int(rows.max())
        # Refine median as darkest horizontal bar inside [r_top, r_bot]
        r_med = r_top + int(np.argmin(c_lum[r_top:r_bot + 1]))

        # Refine exact box border top/bottom dark edges (+/- 2 px outside white interior)
        r_q3 = r_top - 1
        r_q1 = r_bot + 1

        # Walk vertical dark whisker stems at cx +/- 1 above r_q3 and below r_q1
        w_min = gray_sub[:, max(0, cx - 1):min(pw, cx + 2)].min(axis=1)
        up = r_q3
        for r in range(r_q3 - 1, 1, -1):
            if w_min[r] < 130.0:
                up = r
            elif r > 2 and w_min[r - 1] < 130.0:
                continue
            else:
                break
        dn = r_q1
        for r in range(r_q1 + 1, ph - 2):
            if w_min[r] < 130.0:
                dn = r
            elif r < ph - 3 and w_min[r + 1] < 130.0:
                continue
            else:
                break

        # Detect compact circular ggplot2 outlier dots strictly inside the violin interior beyond whiskers
        v_rows = np.where(purple[:, max(0, cx - 10):min(pw, cx + 11)].any(axis=1))[0]
        vmin, vmax = int(v_rows.min()), int(v_rows.max())
        # A true circular outlier dot sits centered at cx with dark core (<75) and is bounded left/right by purple!
        strip_patch = (gray_sub[:, max(0, cx - 6):min(pw, cx + 7)] < 90.0).astype(np.uint8)
        num_lbl, labels, stats, centroids = cv2.connectedComponentsWithStats(strip_patch, connectivity=8)
        ox_vals: list[float] = []
        oy_vals: list[float] = []
        for cid in range(1, num_lbl):
            bx, by_c, bw_c, bh_c, area = [int(v) for v in stats[cid]]
            cy_c = float(centroids[cid][1])
            cx_c = float(centroids[cid][0]) + max(0, cx - 6)
            # Exclude box/whiskers [up-3 .. dn+3] and violin sharp tip ends (within 10px of vmin/vmax)
            if (up - 3) <= cy_c <= (dn + 3):
                continue
            if not (vmin + 10 <= cy_c <= vmax - 10):
                continue
            # Circular ggplot2 dot: 3..9 px diameter, compact aspect ratio, flanked by purple (not border)
            if 3 <= bw_c <= 9 and 3 <= bh_c <= 9 and area >= 8 and abs(cx_c - cx) <= 2.5:
                cy_i = int(round(cy_c))
                if purple[cy_i, max(0, cx - 9):max(1, cx - 4)].any() and purple[cy_i, min(pw - 1, cx + 5):min(pw, cx + 10)].any():
                    ox_vals.append(round(cx_c / max(pw, 1), 4))
                    oy_vals.append(round(float(y_cal.to_value(ty + cy_c)), 1))

        # Measure actual half-width of white box at r_top + 3
        sample_row = min(r_bot, r_top + max(2, (r_bot - r_top) // 4))
        w_cols = np.where(gray_sub[sample_row, max(0, cx - box_hw - 10):min(pw, cx + box_hw + 11)] > 235.0)[0]
        hw_meas = int(round(0.5 * (w_cols.max() - w_cols.min()))) if len(w_cols) >= 4 else box_hw

        boxplots[gname] = {
            "median": round(float(y_cal.to_value(ty + r_med)), 1),
            "q1": round(float(y_cal.to_value(ty + r_q1)), 1),
            "q3": round(float(y_cal.to_value(ty + r_q3)), 1),
            "whisker_lo": round(float(y_cal.to_value(ty + dn)), 1),
            "whisker_hi": round(float(y_cal.to_value(ty + up)), 1),
            "y_unit": "nm",
        }
        groups_meta[gname] = {"x_center": int(cx), "half_width": int(hw_meas)}
        if oy_vals:
            order = np.argsort(oy_vals)
            outliers_scatter[gname] = {
                "n": len(oy_vals),
                "x": [ox_vals[i] for i in order],
                "y": [oy_vals[i] for i in order],
                "x_unit": "group_x_frac",
                "y_unit": "nm",
            }

    out: dict[str, Any] = {
        "digitized_boxplots": boxplots,
        "overlay_meta": {
            "plot_box": [lx, ty, rx, by],
            "x_range": [0.0, 1.0],
            "y_range": [y_min, y_max],
            "y_misfit_px": round(rms_px, 4),
            "groups": groups_meta,
            "kind": "boxplots",
        },
        "extracted_data": {
            "y_tick_misfit_px": round(rms_px, 4),
            "n_groups": len(gnames),
            "n_outlier_dots": sum(v["n"] for v in outliers_scatter.values()),
        },
    }
    if outliers_scatter:
        out["digitized_scatter"] = outliers_scatter
    return out
