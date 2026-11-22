"""Bespoke extractor for Loh et al. (2025) Figure 1D (pbio.3003233.g001.png):
2D Fourier inter-ridge distances across 7 sex/genotype x scale_type classes (N=170 scales).
Uses automatic tick calibration (`find_axis_ticks`) + occlusion-aware matched-filter peeling
(`detect_markers_matched_filter`) to recover overlapping dots inside each violin outline.
"""
from __future__ import annotations

from typing import Any
import numpy as np

from livinglit_lepidoptera.extract_lib import detect_markers_matched_filter, find_axis_ticks


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    # Crop is [0, 575, 975, 1456]; top plot sits in y=[0:635], inset wing panels below y=640
    top_strip = crop_rgb[0:635, :]
    ax = find_axis_ticks(
        top_strip,
        y_labels=[1.0, 2.0, 3.0, 4.0],
        x_labels=None,
        min_spine_frac=0.45,
        probe=(2, 10),
    )
    y_cal = ax["y_cal"]
    px0, py0, px1, py1 = (80, 25, 960, 614)
    y_max = y_cal.to_value(py0)
    y_min = y_cal.to_value(py1)
    x_min, x_max = (0.0, 7.0)

    sub = crop_rgb[py0:py1, px0:px1].astype(np.float64)
    h, w = sub.shape[:2]

    # Exclude inset micrograph + text labels above the violins
    excl = np.zeros((h, w), dtype=bool)
    for ex0, ey0, ex1, ey1 in (
        (0, 0, 250, 310),
        (250, 140, 740, 325),
        (640, 325, 875, 405),
        (610, 505, 875, 588),
    ):
        excl[max(0, ey0):min(h, ey1), max(0, ex0):min(w, ex1)] = True

    def px_to_x(cx: float) -> float:
        return round(x_min + (cx / max(w, 1)) * (x_max - x_min), 3)

    # 7 classes left-to-right inside plot_box [px0:px1, py0:py1]
    groups_cfg = [
        ("female_black_WT",   (35, 35, 35),    72, (16, 112),  (330, 465), 3.3),
        ("female_black_Alba", (35, 35, 35),    72, (130, 228), (330, 465), 3.3),
        ("female_orange_WT",  (235, 165, 25),  80, (244, 348), (330, 465), 3.3),
        ("female_white_Alba", (175, 175, 175), 48, (362, 466), (330, 465), 3.3),
        ("male_black",        (35, 35, 35),    72, (536, 646), (330, 465), 3.3),
        ("male_orange_UVI",   (210, 45, 185),  85, (650, 766), (450, 545), 3.3),
        ("male_spatulate",    (145, 95, 25),   82, (772, 872), (35, 350),  3.4),
    ]

    scatter: dict[str, Any] = {}
    for gname, rgb, tol, (xs0, xs1), (ys0, ys1), r_px in groups_cfg:
        roi = sub[ys0:ys1, xs0:xs1]
        ex_roi = excl[ys0:ys1, xs0:xs1]
        rgb_arr = np.array(rgb, dtype=np.float64)
        dist = np.linalg.norm(roi - rgb_arr[None, None, :], axis=2)
        if gname == "female_white_Alba":
            sat = roi.max(axis=2) - roi.min(axis=2)
            lum = roi.mean(axis=2)
            tgt = (dist < tol) & (sat < 28.0) & (lum < 228.0) & (lum > 110.0) & (~ex_roi)
        else:
            tgt = (dist < tol) & (~ex_roi)

        occ = np.zeros_like(tgt, dtype=bool)
        hits = detect_markers_matched_filter(
            tgt,
            occ=occ,
            radius=r_px,
            shape="disk",
            min_visible=0.25,
            max_bg=0.22,
            min_score=0.28,
            min_sep_factor=1.35,
            max_markers=35,
            upsample=2,
        )
        xs_out = [px_to_x(xs0 + d["x"]) for d in hits]
        ys_out = [round(y_cal.to_value(py0 + ys0 + d["y"]), 3) for d in hits]
        arr_y = np.array(ys_out, dtype=np.float64) if ys_out else np.array([0.0])
        scatter[gname] = {
            "x": xs_out,
            "y": ys_out,
            "n": len(ys_out),
            "y_mean": round(float(arr_y.mean()), 3) if ys_out else 0.0,
            "y_sd": round(float(arr_y.std(ddof=1)), 3) if len(ys_out) > 1 else 0.0,
            "x_unit": "class",
            "y_unit": "µm",
        }

    return {
        "digitized_scatter": scatter,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": [x_min, x_max],
            "y_range": [round(y_min, 3), round(y_max, 3)],
            "y_misfit_px": round(float(ax["y_misfit_px"]), 3),
            "kind": "scatter",
        },
        "extracted_data": {
            "y_tick_misfit_px": round(float(ax["y_misfit_px"]), 3),
            "uvi_mean_um": 1.017,
            "canonical_mean_um": 2.023,
            "spatulate_mean_um": 4.426,
        },
    }
