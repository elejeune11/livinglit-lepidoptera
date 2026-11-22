"""Bespoke extractor for Finet et al. (2026) Figure 2B, 2C, and 2E–J (gr2.jpg):
- B (2B): Isolated ridge reflectance spectra (WT brown, G6 purple, G8 blue) + ±SD ribbons
- C (2C): Isolated crossrib reflectance spectra (WT brown, G6 purple, G8 blue) + ±SD ribbons
  (tightened cross-curve repulsion at 350 nm eliminates the 3-px kiss between G8 and WT!)
- E–J (2E–J): Violin + white IQR boxplots for ridge height, crossrib height, sub-ridge air,
  sub-crossrib air, ridge+air height, and crossrib+air height across WT, G6, and G8.
"""
from __future__ import annotations

from typing import Any
import cv2
import numpy as np

from livinglit_lepidoptera.extract_lib import (
    lin_range,
    ray_dist_alpha,
    viterbi_track,
    walk_ribbon_bounds,
)


_SPEC_CFGS = {
    "B": {
        "plot_box": (166, 39, 979, 803),
        "x_range": lin_range(1006, 1819, 1003.0, 350.0, 1821.5, 700.0),
        "y_range": (
            lin_range(39, 803, 36.0, 24.0, 807.0, 0.0)[1],
            lin_range(39, 803, 36.0, 24.0, 807.0, 0.0)[0],
        ),
    },
    "C": {
        "plot_box": (163, 39, 977, 802),
        "x_range": lin_range(2033, 2847, 2030.0, 350.0, 2849.0, 700.0),
        "y_range": (
            lin_range(39, 802, 35.5, 24.0, 806.5, 0.0)[1],
            lin_range(39, 802, 35.5, 24.0, 806.5, 0.0)[0],
        ),
    },
}

_TRACES = [
    ("WT", (147, 78, 33)),
    ("G6", (117, 76, 167)),
    ("G8", (35, 69, 166)),
]

_VIOLIN_CFGS = {
    "E": {"pbox": (140, 177, 925, 832), "yr": (448.869, 757.54), "groups": {"WT": 148, "G6": 392, "G8": 637}},
    "F": {"pbox": (140, 138, 929, 780), "yr": (312.596, 595.105), "groups": {"WT": 148, "G6": 397, "G8": 647}},
    "G": {"pbox": (162, 176, 955, 833), "yr": (507.965, 1024.779), "groups": {"WT": 150, "G6": 405, "G8": 659}},
    "H": {"pbox": (162, 134, 960, 783), "yr": (257.836, 810.647), "groups": {"WT": 152, "G6": 406, "G8": 659}},
    "I": {"pbox": (152, 178, 977, 836), "yr": (1034.707, 1691.885), "groups": {"WT": 154, "G6": 412, "G8": 670}},
    "J": {"pbox": (150, 129, 980, 783), "yr": (635.857, 1330.677), "groups": {"WT": 154, "G6": 414, "G8": 674}},
}


def _extract_spectra(crop_rgb: np.ndarray, panel_id: str) -> dict[str, Any]:
    cfg = _SPEC_CFGS[panel_id]
    px0, py0, px1, py1 = cfg["plot_box"]
    sub = crop_rgb[py0:py1, px0:px1].copy()
    # Mask top-left legend and title text
    sub[35:200, 10:150, :] = 255
    sub[0:55, 260:580, :] = 255
    # Mask solid black arrowheads (▼)
    gray = sub.mean(axis=2)
    sat = sub.max(axis=2).astype(int) - sub.min(axis=2).astype(int)
    black_ink = ((gray < 65) & (sat < 30)).astype(np.uint8)
    black_dil = cv2.dilate(black_ink, np.ones((5, 5), np.uint8)) > 0
    sub[black_dil] = 255

    sub_f = sub.astype(np.float32)
    h, w = sub_f.shape[:2]
    x_min, x_max = cfg["x_range"]
    y_min, y_max = cfg["y_range"]
    pix_sat = np.max(sub_f, axis=2) - np.min(sub_f, axis=2)

    n_cols = 82
    x_cols = np.linspace(4, w - 5, n_cols).astype(int)
    perps, alphas = {}, {}
    for nm, rgb in _TRACES:
        perps[nm], alphas[nm] = ray_dist_alpha(sub_f, rgb)

    curves: dict[str, Any] = {}
    for nm, rgb in _TRACES:
        p_map, a_map = perps[nm], alphas[nm]
        cost = np.full((h, n_cols), 70.0, dtype=np.float64)
        valid_col = np.zeros(n_cols, dtype=bool)
        for ti, cx in enumerate(x_cols):
            c0, c1 = max(0, cx - 2), min(w, cx + 3)
            p_col = p_map[:, c0:c1].min(axis=1)
            a_col = a_map[:, c0:c1].max(axis=1)
            s_col = pix_sat[:, c0:c1].max(axis=1)
            ok = (p_col <= 30.0) & (a_col >= 0.25) & (s_col >= 14.0)
            rc = np.where(ok, 0.85 * p_col + 46.0 * (1.15 - np.clip(a_col, 0.0, 1.15)), 70.0)
            for onm, _ in _TRACES:
                if onm == nm:
                    continue
                op = perps[onm][:, c0:c1].min(axis=1)
                oa = alphas[onm][:, c0:c1].max(axis=1)
                # Stronger repulsion keeps G8 blue cleanly separate from WT brown right at 350 nm on F2/C!
                rc = np.where((op + 4.5 < p_col) & (oa >= 0.28), np.maximum(rc, 62.0), rc)
            # On F2/C at 350-365 nm, G8 starts near ~11.8% (below WT brown at ~14.5%)
            if panel_id == "C" and nm == "G8" and ti < 4:
                y_cut = int(round((y_max - 13.5) / max(y_max - y_min, 1e-9) * h))
                rc[:y_cut] += 40.0
            if np.any(rc < 42.0):
                valid_col[ti] = True
            cost[:, ti] = rc

        y_path = viterbi_track(cost, max_step=24, smooth_w=0.22, norm="l1")
        rib_mask = (p_map <= 34.0) & (a_map >= 0.10) & (pix_sat >= 10.0)
        y_lo_px, y_hi_px = walk_ribbon_bounds(rib_mask, x_cols, y_path, max_half=85, max_gap=5)

        xs_out, ys_out, lo_out, hi_out = [], [], [], []
        for ti, (cx, cy, ylo, yhi) in enumerate(zip(x_cols, y_path, y_lo_px, y_hi_px)):
            if not valid_col[ti] and (ti > n_cols - 15 and cy < 25):
                continue
            xs_out.append(round(x_min + (cx / max(w, 1)) * (x_max - x_min), 2))
            ys_out.append(round(y_max - (cy / max(h, 1)) * (y_max - y_min), 3))
            lo_out.append(round(y_max - (ylo / max(h, 1)) * (y_max - y_min), 3))
            hi_out.append(round(y_max - (yhi / max(h, 1)) * (y_max - y_min), 3))

        curves[nm] = {
            "x": xs_out,
            "y": ys_out,
            "lo": lo_out,
            "hi": hi_out,
            "peak_x": xs_out[int(np.argmax(ys_out))] if ys_out else None,
            "peak_y": max(ys_out) if ys_out else None,
            "x_unit": "nm",
            "y_unit": "%",
        }

    return {
        "curves": curves,
        "overlay_meta": {
            "plot_box": list(cfg["plot_box"]),
            "x_range": list(cfg["x_range"]),
            "y_range": list(cfg["y_range"]),
            "kind": "curves",
        },
    }


def _extract_violin_panel(crop_rgb: np.ndarray, panel_id: str) -> dict[str, Any]:
    cfg = _VIOLIN_CFGS[panel_id]
    px0, py0, px1, py1 = cfg["pbox"]
    sub = crop_rgb[py0:py1, px0:px1]
    h, w = sub.shape[:2]
    y_min, y_max = cfg["yr"]
    lum = sub.astype(np.float32).mean(axis=2)
    sat = sub.max(axis=2).astype(np.int16) - sub.min(axis=2).astype(np.int16)

    def py2y(py: float) -> float:
        return round(y_max - (py / max(h, 1)) * (y_max - y_min), 2)

    bp_out: dict[str, Any] = {}
    groups_meta: dict[str, dict[str, int]] = {}
    for gname, xc in cfg["groups"].items():
        groups_meta[gname] = {"x_center": xc, "half_width": 16}
        c_in0, c_in1 = max(0, xc - 6), min(w, xc + 7)
        center_white = ((lum[:, c_in0:c_in1] > 235) & (sat[:, c_in0:c_in1] < 22)).mean(axis=1) >= 0.70
        # Inside brown/purple/blue violins, immediate left & right flanking walls are strongly saturated or dark
        l_wall = (lum[:, max(0, xc - 26):max(1, xc - 8)].min(axis=1) < 165)
        r_wall = (lum[:, min(w - 1, xc + 8):min(w, xc + 26)].min(axis=1) < 165)
        box_rows = np.where(center_white & l_wall & r_wall)[0]
        if len(box_rows) < 5:
            bp_out[gname] = {"median": None, "q1": None, "q3": None, "whisker_lo": None, "whisker_hi": None, "y_unit": "nm"}
            continue
        segs = []
        s0, prev = int(box_rows[0]), int(box_rows[0])
        for r in box_rows[1:]:
            ri = int(r)
            if ri > prev + 14:
                segs.append((s0, prev))
                s0 = ri
            prev = ri
        segs.append((s0, prev))
        q3_px, q1_px = max(segs, key=lambda ab: ab[1] - ab[0])

        m0 = min(q1_px, q3_px + max(2, int(0.10 * (q1_px - q3_px))))
        m1 = max(m0 + 1, q1_px - max(2, int(0.10 * (q1_px - q3_px))))
        med_px = int(m0 + int(np.argmin(lum[m0:m1, c_in0:c_in1].mean(axis=1))))

        # Vertical black whisker stem inside the colored violin body (robust on dark blue G8 fill)
        stem = lum[:, max(0, xc - 3):min(w, xc + 4)].min(axis=1)
        flank = 0.5 * (
            lum[:, max(0, xc - 14):max(1, xc - 7)].mean(axis=1)
            + lum[:, min(w - 1, xc + 7):min(w, xc + 14)].mean(axis=1)
        )
        has_stem = (stem < 58) | ((flank - stem) > 22.0)
        iqr_px = max(12, q1_px - q3_px)
        max_w = int(round(1.65 * iqr_px))
        w_hi_px = q3_px
        gap = 0
        for r in range(q3_px - 1, max(8, q3_px - max_w), -1):
            if has_stem[r]:
                w_hi_px = r
                gap = 0
            else:
                gap += 1
                if gap > 6:
                    break
        w_lo_px = q1_px
        gap = 0
        for r in range(q1_px + 1, min(h - 4, q1_px + max_w)):
            if has_stem[r]:
                w_lo_px = r
                gap = 0
            else:
                gap += 1
                if gap > 6:
                    break

        bp_out[gname] = {
            "median": py2y(med_px),
            "q1": py2y(q1_px),
            "q3": py2y(q3_px),
            "whisker_lo": py2y(w_lo_px),
            "whisker_hi": py2y(w_hi_px),
            "y_unit": "nm",
        }

    return {
        "digitized_boxplots": bp_out,
        "overlay_meta": {
            "plot_box": list(cfg["pbox"]),
            "y_range": list(cfg["yr"]),
            "groups": groups_meta,
            "kind": "boxplot",
        },
    }


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    if panel_id in _SPEC_CFGS:
        return _extract_spectra(crop_rgb, panel_id)
    if panel_id in _VIOLIN_CFGS:
        return _extract_violin_panel(crop_rgb, panel_id)
    raise ValueError(f"Unknown Finet Fig 2 panel_id: {panel_id}")
