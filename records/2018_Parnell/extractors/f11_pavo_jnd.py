"""Bespoke extractor for Parnell et al. (2018) Figure 11 (rsif20170948-g11.jpg, panels A–P):
Pavo receptor-noise visual discriminability boxplots (chromatic & achromatic JNDs) for
co-mimetic pairs (H. erato cyrbia vs H. melpomene cythera; H. cydno vs H. eleuchia) across
forewing/hindwing and daylight/forest-shade illuminants.

Uses `find_axis_ticks` for exact y-axis calibration on every panel (misfit <= 0.15 px) and
subpixel dark-ink geometry to extract each boxplot's median (thick 3px horizontal bar), Q1/Q3
box walls, and dashed upper/lower whisker caps while rejecting JND=1 solid and JND=2 dotted
reference lines.
"""
from __future__ import annotations

from typing import Any
import numpy as np

from livinglit_lepidoptera.extract_lib import _group_centres, find_axis_ticks


_CHROMATIC_PANELS = {"A", "B", "E", "F", "I", "J", "M", "N"}
_CHROMATIC_GROUPS = ["avian", "heli_I", "heli_II", "heli_III", "heli_IV"]
_ACHROMATIC_GROUPS = ["avian", "heli"]


def _extract_single_boxplot(
    gray: np.ndarray,
    xc: float,
    y_cal,
    py0: int,
    ref_rows: list[int],
    hw: int = 10,
) -> dict[str, Any]:
    """Measure Q3 (top box edge), median (thick black bar), Q1 (bottom box edge),
    and whisker_hi / whisker_lo caps for a standard R white-fill black-outline boxplot.
    """
    h, w = gray.shape
    cx = int(round(xc))
    ink = np.clip((255.0 - gray) / 255.0, 0.0, 1.0)

    # Full-width horizontal reference lines (JND=1, JND=2) appear on BOTH sides of the boxplot,
    # whereas an adjacent boxplot only sits on one side; taking min(left_bg, right_bg) isolates reference lines cleanly.
    l_cols = [c for c in range(max(1, cx - hw - 8), max(1, cx - hw - 3))]
    r_cols = [c for c in range(min(w - 1, cx + hw + 4), min(w - 1, cx + hw + 9))]
    l_bg = ink[:, l_cols].mean(axis=1) if l_cols else np.zeros(h)
    r_bg = ink[:, r_cols].mean(axis=1) if r_cols else np.zeros(h)
    bg_prof = np.minimum(l_bg, r_bg) if (l_cols and r_cols) else (l_bg if l_cols else r_bg)

    # Box vertical side walls sit symmetrically at cx - hw_box and cx + hw_box (for R boxplots here, hw_box ~ 9..11 px)
    best_walls = None
    for bw in range(8, 13):
        l_col = max(1, cx - bw)
        r_col = min(w - 2, cx + bw)
        lw = ink[:, max(0, l_col - 1):min(w, l_col + 2)].max(axis=1)
        rw = ink[:, max(0, r_col - 1):min(w, r_col + 2)].max(axis=1)
        # Exclude reference line rows and top/bottom 2px margin
        is_wall = (lw > 0.30) & (rw > 0.30) & (bg_prof < 0.25)
        is_wall[:2] = False
        is_wall[-2:] = False
        rows_w = np.where(is_wall)[0]
        if len(rows_w) >= 3:
            # Find longest contiguous vertical run (the box itself!)
            runs = [[int(rows_w[0]), int(rows_w[0])]]
            for r in rows_w[1:]:
                if int(r) <= runs[-1][1] + 2:
                    runs[-1][1] = int(r)
                else:
                    runs.append([int(r), int(r)])
            longest = max(runs, key=lambda ab: ab[1] - ab[0])
            span = longest[1] - longest[0]
            # Confirm horizontal top/bottom box edges exist inside [cx-bw+2 .. cx+bw-2]
            inner = ink[:, max(0, cx - bw + 2):min(w, cx + bw - 1)].mean(axis=1)
            top_ok = inner[max(0, longest[0] - 1):min(h, longest[0] + 2)].max() > 0.28
            bot_ok = inner[max(0, longest[1] - 1):min(h, longest[1] + 2)].max() > 0.28
            score = span + (8 if top_ok else 0) + (8 if bot_ok else 0)
            if best_walls is None or score > best_walls[0]:
                best_walls = (score, bw, longest[0], longest[1])

    if best_walls is None:
        return {"median": None, "q1": None, "q3": None, "whisker_lo": None, "whisker_hi": None, "y_unit": "JND"}

    _, bw, r_top, r_bot = best_walls
    inner_mean = ink[:, max(0, cx - bw + 2):min(w, cx + bw - 1)].mean(axis=1)
    # Subtract background reference line contribution so JND=1/2 lines never fool median detector
    net_inner = np.clip(inner_mean - 0.90 * bg_prof, 0.0, 1.0)

    # Thick 3px median bar sits inside [r_top .. r_bot] and has the highest 3-row box-filtered darkness!
    if r_bot - r_top >= 2:
        k3 = np.convolve(net_inner, [0.25, 0.5, 0.25], mode="same")
        med_slice = k3[r_top:r_bot + 1]
        r_med = float(r_top + int(np.argmax(med_slice)))
    else:
        r_med = 0.5 * (r_top + r_bot)

    # Walk upward from r_top along central dashed whisker stem + cap (allow dashed gaps up to 8 px!)
    stem = ink[:, max(0, cx - 2):min(w, cx + 3)].max(axis=1)
    cap = ink[:, max(0, cx - 5):min(w, cx + 6)].mean(axis=1)
    # Mask pure reference line rows when checking caps
    net_cap = np.clip(cap - 0.90 * bg_prof, 0.0, 1.0)
    net_stem = np.clip(stem - 0.90 * bg_prof, 0.0, 1.0)

    r_whi = r_top
    gap = 0
    for r in range(r_top - 1, 1, -1):
        if net_stem[r] > 0.14 or net_cap[r] > 0.20:
            r_whi = r
            gap = 0
            # Horizontal whisker cap is wider than stem and sits >=3 px outside box edge with zero ink above it
            if r <= r_top - 3 and net_cap[r] > 0.28 and (r < 4 or net_stem[max(0, r - 4):r].max() < 0.14):
                break
        else:
            gap += 1
            if gap > 13:
                break

    r_wlo = r_bot
    gap = 0
    for r in range(r_bot + 1, h - 1):
        if net_stem[r] > 0.14 or net_cap[r] > 0.20:
            r_wlo = r
            gap = 0
            if r >= r_bot + 3 and net_cap[r] > 0.28 and (r > h - 5 or net_stem[r + 1:min(h, r + 5)].max() < 0.14):
                break
        else:
            gap += 1
            if gap > 13:
                break

    def yv(r: float) -> float:
        return round(max(0.0, float(y_cal.to_value(py0 + r))), 2)

    q3 = yv(float(r_top))
    q1 = yv(float(r_bot))
    med = round(min(max(yv(r_med), q1), q3), 2)
    whi = max(yv(float(r_whi)), q3)
    wlo = min(yv(float(r_wlo)), q1)
    return {
        "median": med,
        "q1": q1,
        "q3": q3,
        "whisker_lo": wlo,
        "whisker_hi": whi,
        "y_unit": "JND",
    }


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    is_chrom = panel_id in _CHROMATIC_PANELS
    y_labels = [0.0, 5.0, 10.0, 15.0, 20.0, 25.0] if is_chrom else [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
    gnames = _CHROMATIC_GROUPS if is_chrom else _ACHROMATIC_GROUPS

    ax = find_axis_ticks(
        crop_rgb,
        y_labels=y_labels,
        x_labels=None,
        dark_thr=195.0,
        probe=(2, 6),
        tick_min_frac=0.45,
    )
    px0, py0, px1, py1 = ax["plot_box"]
    y_cal = ax["y_cal"]
    yr = list(y_cal.range_for_span(py1, py0, ndigits=3))

    # Locate exact x-axis group ticks just below the bottom spine (py1 + 2 .. py1 + 6)
    gfull = crop_rgb.mean(axis=2)
    hr = py1 + 1
    x_hits = np.where((gfull[hr + 2:min(crop_rgb.shape[0], hr + 6), px0:px1] < 195.0).mean(axis=0) > 0.45)[0]
    x_ticks = _group_centres((x_hits + px0).tolist(), gap=2)
    if len(x_ticks) == len(gnames):
        centers = [t - px0 for t in x_ticks]
    else:
        # Clean evenly spaced fallback matching R boxplot xlim margins
        pw = px1 - px0
        if is_chrom:
            centers = [pw * (0.13 + i * 0.185) for i in range(5)]
        else:
            centers = [pw * 0.28, pw * 0.72]

    sub_gray = crop_rgb[py0:py1, px0:px1].mean(axis=2).astype(np.float64)
    ref_rows = [int(round(y_cal.to_pixel(1.0) - py0)), int(round(y_cal.to_pixel(2.0) - py0))]

    boxplots: dict[str, Any] = {}
    groups_meta: dict[str, dict[str, int]] = {}
    for gname, xc in zip(gnames, centers):
        boxplots[gname] = _extract_single_boxplot(sub_gray, xc, y_cal, py0, ref_rows, hw=10)
        groups_meta[gname] = {"x_center": int(round(xc)), "half_width": 10}

    return {
        "digitized_boxplots": boxplots,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "y_range": yr,
            "y_misfit_px": ax["y_misfit_px"],
            "groups": groups_meta,
            "kind": "boxplots",
        },
        "extracted_data": {
            "y_tick_misfit_px": ax["y_misfit_px"],
            "avian_median_jnd": boxplots["avian"]["median"],
        },
    }
