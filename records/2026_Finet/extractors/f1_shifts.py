"""Bespoke extractor for Finet et al. (2026) Figure 1B, 1C, 1D (gr1.jpg):
- F1/B: |Δλ| (nm) shift in peak reflectance wavelength (Δλ < 0 gray violin vs Δλ > 0 black violin)
- F1/C: |ΔRmax| (%) shift in peak reflectance intensity
- F1/D: |ΔFWHM| (nm) shift in spectral bandwidth

Extracts BOTH the centered white IQR boxplots (Q1/median/Q3/whiskers) AND observable individual
jitter scatter dots on the shaded gray left violin via `shaded_bg_residual` + matched-filter peeling.
Note: on the right solid-black (#000) violin, interior black dots share identical RGB with the violin
fill and are optically unobservable; visible exterior jitter/outlier dots are extracted where present.
"""
from __future__ import annotations

from typing import Any
import cv2
import numpy as np

from livinglit_lepidoptera.extract_lib import (
    detect_markers_matched_filter,
    shaded_bg_residual,
)


_CFGS = {
    "B": {
        "pbox": (191, 24, 1008, 843),
        "yr": (-32.083, 104.417),
        "yu": "nm",
        "groups": {
            "dlambda_lt_0": {"xc": 222, "hw": 16, "is_black_fill": False},
            "dlambda_gt_0": {"xc": 594, "hw": 16, "is_black_fill": True},
        },
    },
    "C": {
        "pbox": (235, 16, 1054, 846),
        "yr": (-27.278, 105.125),
        "yu": "%",
        "groups": {
            "dRmax_lt_0": {"xc": 222, "hw": 16, "is_black_fill": False},
            "dRmax_gt_0": {"xc": 595, "hw": 16, "is_black_fill": True},
        },
    },
    "D": {
        "pbox": (233, 20, 1050, 849),
        "yr": (-44.946, 177.504),
        "yu": "nm",
        "groups": {
            "dFWHM_lt_0": {"xc": 221, "hw": 16, "is_black_fill": False},
            "dFWHM_gt_0": {"xc": 593, "hw": 16, "is_black_fill": True},
        },
    },
}


def extract_white_box_in_violin(
    sub_rgb: np.ndarray,
    xc: int,
    y_min: float,
    y_max: float,
    y_unit: str,
    box_half_w: int = 8,
    wall_offset: int = 24,
) -> dict[str, Any]:
    """Locate a white IQR box (split by a horizontal median line) centered inside a shaded violin."""
    h, w = sub_rgb.shape[:2]
    lum = sub_rgb.astype(np.float32).mean(axis=2)
    sat = sub_rgb.max(axis=2).astype(np.int16) - sub_rgb.min(axis=2).astype(np.int16)

    def py2y(py: float) -> float:
        return round(y_max - (py / max(h, 1)) * (y_max - y_min), 3)

    c_in0, c_in1 = max(0, xc - 5), min(w, xc + 6)
    center_white = ((lum[:, c_in0:c_in1] > 235) & (sat[:, c_in0:c_in1] < 20)).mean(axis=1) >= 0.70

    l_wall = lum[:, max(0, xc - 22):max(1, xc - 6)].min(axis=1) < 155
    r_wall = lum[:, min(w - 1, xc + 6):min(w, xc + 22)].min(axis=1) < 155
    in_box_row = center_white & l_wall & r_wall

    box_rows = np.where(in_box_row)[0]
    if len(box_rows) < 4:
        return {"median": None, "q1": None, "q3": None, "whisker_lo": None, "whisker_hi": None, "y_unit": y_unit}

    segs: list[tuple[int, int]] = []
    s0, prev = int(box_rows[0]), int(box_rows[0])
    for r in box_rows[1:]:
        ri = int(r)
        if ri > prev + 14:
            segs.append((s0, prev))
            s0 = ri
        prev = ri
    segs.append((s0, prev))
    q3_px, q1_px = max(segs, key=lambda ab: ab[1] - ab[0])

    m0 = min(q1_px, q3_px + max(2, int(0.08 * (q1_px - q3_px))))
    m1 = max(m0 + 1, q1_px - max(2, int(0.08 * (q1_px - q3_px))))
    med_profile = lum[m0:m1, c_in0:c_in1].mean(axis=1)
    med_px = int(m0 + int(np.argmin(med_profile)))

    iqr_px = max(8, q1_px - q3_px)
    max_whisk_px = int(round(1.65 * iqr_px))
    stem_c = lum[:, max(0, xc - 2):min(w, xc + 3)].mean(axis=1)
    flank_l = lum[:, max(0, xc - 12):max(1, xc - 6)].mean(axis=1)
    flank_r = lum[:, min(w - 1, xc + 6):min(w, xc + 12)].mean(axis=1)
    flank = 0.5 * (flank_l + flank_r)
    has_stem = (np.abs(stem_c - flank) > 18.0) | ((flank > 235) & (stem_c < 200))

    w_hi_px = q3_px
    gap = 0
    for r in range(q3_px - 1, max(2, q3_px - max_whisk_px), -1):
        if has_stem[r]:
            w_hi_px = r
            gap = 0
        else:
            gap += 1
            if gap > 6:
                break

    w_lo_px = q1_px
    gap = 0
    for r in range(q1_px + 1, min(h - 3, q1_px + max_whisk_px)):
        if has_stem[r]:
            w_lo_px = r
            gap = 0
        else:
            gap += 1
            if gap > 6:
                break

    return {
        "median": py2y(med_px),
        "q1": py2y(q1_px),
        "q3": py2y(q3_px),
        "whisker_lo": py2y(w_lo_px),
        "whisker_hi": py2y(w_hi_px),
        "y_unit": y_unit,
    }


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    cfg = _CFGS[panel_id]
    px0, py0, px1, py1 = cfg["pbox"]
    sub = crop_rgb[py0:py1, px0:px1]
    h, w = sub.shape[:2]
    y_min, y_max = cfg["yr"]
    lum = sub.astype(np.float32).mean(axis=2)

    def py2y(py: float) -> float:
        return round(y_max - (py / max(h, 1)) * (y_max - y_min), 3)

    _, res_m = shaded_bg_residual(sub, marker_diam_px=7, mode="median")
    res_lum = res_m.mean(axis=2)
    raw_dark = (lum < 85.0) & (res_lum >= 30.0)
    num, lab, stats, _ = cv2.connectedComponentsWithStats(raw_dark.astype(np.uint8))
    clean_dots = np.zeros_like(raw_dark, dtype=bool)
    for k in range(1, num):
        wc, hc, ac = stats[k, cv2.CC_STAT_WIDTH], stats[k, cv2.CC_STAT_HEIGHT], stats[k, cv2.CC_STAT_AREA]
        if 4 <= ac <= 90 and wc <= 16 and hc <= 16:
            clean_dots |= (lab == k)

    bp_out: dict[str, Any] = {}
    sc_out: dict[str, Any] = {}
    groups_meta: dict[str, dict[str, int]] = {}

    for gname, gcfg in cfg["groups"].items():
        xc, hw = int(gcfg["xc"]), int(gcfg["hw"])
        groups_meta[gname] = {"x_center": xc, "half_width": hw}
        bp_out[gname] = extract_white_box_in_violin(sub, xc, y_min, y_max, cfg["yu"], box_half_w=hw)

        if not gcfg["is_black_fill"]:
            # Extract observable black jitter dots sitting inside/near the shaded gray violin
            tg = clean_dots.copy()
            tg[:, :max(0, xc - 130)] = False
            tg[:, min(w, xc + 130):] = False
            pts = detect_markers_matched_filter(
                tg, np.zeros_like(tg), radius=1.9, shape="disk",
                min_visible=0.45, max_bg=0.25, min_score=0.30,
                min_sep_factor=1.60, peel=True, peel_radius_factor=1.05, upsample=2, border_px=2,
            )
            pts.sort(key=lambda p: p["y"], reverse=True)
            ys_j = [py2y(p["y"]) for p in pts]
            sc_out[gname] = {
                "n": len(ys_j),
                "x": [round(p["x"] / max(w, 1), 4) for p in pts],
                "y": ys_j,
                "mean_y": round(float(np.mean(ys_j)), 3) if ys_j else None,
                "sd_y": round(float(np.std(ys_j, ddof=1)), 3) if len(ys_j) > 1 else None,
                "x_unit": "",
                "y_unit": cfg["yu"],
            }

    out: dict[str, Any] = {
        "digitized_boxplots": bp_out,
        "overlay_meta": {
            "plot_box": list(cfg["pbox"]),
            "x_range": [0.0, 1.0],
            "y_range": list(cfg["yr"]),
            "groups": groups_meta,
            "kind": "boxplot",
            "jitter_visibility_note": "Gray left violin jitter dots extracted; right black violin interior dots share #000 fill RGB and are optically unobservable.",
        },
    }
    if sc_out:
        out["digitized_scatter"] = sc_out
    return out
