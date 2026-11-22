"""Bespoke extractor for Finet et al. (2026) Figure 1B, 1C, 1D (gr1.jpg):
- F1/B: |Δλ| (nm) shift in peak reflectance wavelength (Δλ < 0 gray violin vs Δλ > 0 black violin)
- F1/C: |ΔRmax| (%) shift in peak reflectance intensity (fixes white inner box span across median line!)
- F1/D: |ΔFWHM| (nm) shift in spectral bandwidth

Each violin contains a centered white IQR box split horizontally by a black median stroke and bounded
above/below by thin vertical 1.5×IQR whiskers. Scanning across the median gap (<= 8 px) while verifying
colored/dark violin walls on either side captures the complete [Q1, Q3] box even for asymmetric distributions.
"""
from __future__ import annotations

from typing import Any
import numpy as np


_CFGS = {
    "B": {
        "pbox": (191, 24, 1008, 843),
        "yr": (-32.083, 104.417),
        "yu": "nm",
        "groups": {
            "dlambda_lt_0": {"xc": 222, "hw": 16},
            "dlambda_gt_0": {"xc": 594, "hw": 16},
        },
    },
    "C": {
        "pbox": (235, 16, 1054, 846),
        "yr": (-27.278, 105.125),
        "yu": "%",
        "groups": {
            "dRmax_lt_0": {"xc": 222, "hw": 16},
            "dRmax_gt_0": {"xc": 595, "hw": 16},
        },
    },
    "D": {
        "pbox": (233, 20, 1050, 849),
        "yr": (-44.946, 177.504),
        "yu": "nm",
        "groups": {
            "dFWHM_lt_0": {"xc": 221, "hw": 16},
            "dFWHM_gt_0": {"xc": 593, "hw": 16},
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
    sat = (sub_rgb.max(axis=2).astype(np.int16) - sub_rgb.min(axis=2).astype(np.int16))

    def py2y(py: float) -> float:
        return round(y_max - (py / max(h, 1)) * (y_max - y_min), 3)

    # A row belongs to the white IQR box if its central strip [xc-6..xc+6] is mostly pure white (>238)
    # AND it has a dark box border stroke at xc ± (8..18) (preventing background white outside the violin!)
    c_in0, c_in1 = max(0, xc - 5), min(w, xc + 6)
    center_white = ((lum[:, c_in0:c_in1] > 235) & (sat[:, c_in0:c_in1] < 20)).mean(axis=1) >= 0.70

    # Left & right vertical box walls sit within [xc-20..xc-6] and [xc+6..xc+20]
    l_wall = lum[:, max(0, xc - 22):max(1, xc - 6)].min(axis=1) < 155
    r_wall = lum[:, min(w - 1, xc + 6):min(w, xc + 22)].min(axis=1) < 155
    in_box_row = center_white & l_wall & r_wall

    # Also allow the thin horizontal black/dark median bar inside the box (dark across c_in0..c_in1)
    center_dark = lum[:, c_in0:c_in1].mean(axis=1) < 175
    # Bridge across the median line (up to 10 px gap) using morphological closing along 1D rows
    box_rows = np.where(in_box_row)[0]
    if len(box_rows) < 4:
        return {"median": None, "q1": None, "q3": None, "whisker_lo": None, "whisker_hi": None, "y_unit": y_unit}

    # Group contiguous segments separated by <= 14 px (bridging the dark horizontal median stroke + anti-aliasing)
    segs: list[tuple[int, int]] = []
    s0, prev = int(box_rows[0]), int(box_rows[0])
    for r in box_rows[1:]:
        ri = int(r)
        if ri > prev + 14:
            segs.append((s0, prev))
            s0 = ri
        prev = ri
    segs.append((s0, prev))
    # Pick longest bridged segment (the true IQR box!)
    q3_px, q1_px = max(segs, key=lambda ab: ab[1] - ab[0])

    # Median: darkest horizontal line strictly inside [q3_px + 2, q1_px - 2]
    m0 = min(q1_px, q3_px + max(2, int(0.08 * (q1_px - q3_px))))
    m1 = max(m0 + 1, q1_px - max(2, int(0.08 * (q1_px - q3_px))))
    med_profile = lum[m0:m1, c_in0:c_in1].mean(axis=1)
    med_px = int(m0 + int(np.argmin(med_profile)))

    # Whiskers: ggplot2 boxplot whiskers extend at most 1.5 * IQR beyond Q1/Q3
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
    y_min, y_max = cfg["yr"]

    bp_out: dict[str, Any] = {}
    groups_meta: dict[str, dict[str, int]] = {}
    for gname, gcfg in cfg["groups"].items():
        xc, hw = int(gcfg["xc"]), int(gcfg["hw"])
        groups_meta[gname] = {"x_center": xc, "half_width": hw}
        bp_out[gname] = extract_white_box_in_violin(sub, xc, y_min, y_max, cfg["yu"], box_half_w=hw)

    return {
        "digitized_boxplots": bp_out,
        "overlay_meta": {
            "plot_box": list(cfg["pbox"]),
            "y_range": list(cfg["yr"]),
            "groups": groups_meta,
            "kind": "boxplot",
        },
    }
