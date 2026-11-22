"""Bespoke plot extractors for Livraghi et al. (2024) Figure 3F and 3H (pnas.2403326121fig03.jpg):
- extract_3f: Normalized WGS sequencing depth across V. cardui ivory exon 1 (WT average vs ivory KO bi-allelic 82/97 bp deletion)
- extract_3h_female: Sanger ICE/TIDE % aberrant sequences for female cortex exon 2 G0 mKO parent (63.8% efficiency)
- extract_3h_male: Sanger ICE/TIDE % aberrant sequences for male cortex exon 2 G0 mKO parent (98.8% efficiency)
"""
from __future__ import annotations

from typing import Any
import numpy as np

from livinglit_lepidoptera.extract_lib import AxisCal, ray_dist_alpha, viterbi_track


def extract_3f(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    """Digitize WT average (black) and ivory KO (blue) normalized WGS depth curves in Fig. 3F."""
    # Crop bbox in full image: [380, 0, 695, 138] -> size 315 x 138
    # Detected left y-ticks at full y = [116, 88, 59, 31] -> [0, 1, 2, 3]
    # Detected bottom x-ticks at full x = [457, 537, 617] -> [2030250, 2030500, 2030750]
    y_cal = AxisCal.fit([116.0, 88.0, 59.0, 31.0], [0.0, 1.0, 2.0, 3.0], scale="linear")
    x_cal = AxisCal.fit([77.0, 157.0, 237.0], [2030250.0, 2030500.0, 2030750.0], scale="linear")

    px0, py0, px1, py1 = 28, 27, 310, 120
    sub_f = crop_rgb[py0:py1, px0:px1].astype(np.float32)
    h, w = sub_f.shape[:2]

    # Mask out legend box ("WT average / ivory KO") in upper-left inside plot_box
    legend_mask = np.zeros((h, w), dtype=bool)
    legend_mask[0:24, 48:112] = True

    # Red dashed vertical lines mark the 82/97 bp deletion boundaries (rel cols ~112 and ~138)
    r_ex = sub_f[:, :, 0] - sub_f[:, :, 1]
    red_mask = (r_ex > 55.0) & (sub_f[:, :, 0] > 140.0)

    # 1. Blue ivory KO depth trace (deep steel-blue RGB ~ (52, 98, 155), distinct from pale read pileup)
    perp_b, alpha_b = ray_dist_alpha(sub_f, (42, 95, 158))
    b_ex = sub_f[:, :, 2] - sub_f[:, :, 0]
    blue_score = np.where(
        (~legend_mask) & (~red_mask) & (b_ex > 28.0) & (sub_f[:, :, 0] < 145.0) & (perp_b < 55.0),
        alpha_b * (b_ex / 60.0),
        0.0,
    )
    # Near deletion floor (y~0, rows 85..92), blue line touches bottom axis/read gap; reward blue ink strongly
    cost_b = np.where(blue_score > 0.18, np.maximum(0.0, 1.5 - 2.5 * blue_score), 3.2)
    # Sample every 3 px across full plot width
    cols = np.arange(2, w - 2, 3, dtype=np.int32)
    cost_b_sub = np.stack([cost_b[:, max(0, c - 1):min(w, c + 2)].min(axis=1) for c in cols], axis=1)
    path_b = viterbi_track(cost_b_sub, max_step=24, smooth_w=0.14, norm="l1")

    # 2. Black WT average depth trace (neutral charcoal line RGB ~ (55, 55, 55), low saturation, excludes blue/red/legend)
    sat = sub_f.max(axis=2) - sub_f.min(axis=2)
    lum = sub_f.mean(axis=2)
    wt_ink = np.where(
        (~legend_mask) & (~red_mask) & (sat < 30.0) & (lum < 155.0) & (blue_score < 0.25),
        (165.0 - lum) / 110.0,
        0.0,
    )
    # Restrict WT prior gently away from top/bottom frame lines (rows 2..h-3)
    cost_wt = np.where(wt_ink > 0.12, np.maximum(0.0, 1.4 - 2.2 * wt_ink), 2.8)
    cost_wt[:2, :] = 6.0
    cost_wt[-2:, :] = 6.0
    cost_wt_sub = np.stack([cost_wt[:, max(0, c - 1):min(w, c + 2)].min(axis=1) for c in cols], axis=1)
    path_wt = viterbi_track(cost_wt_sub, max_step=8, smooth_w=0.22, norm="l1")

    xs = [round(x_cal.to_value(px0 + float(c)), 1) for c in cols]
    ys_ko = [round(max(0.0, y_cal.to_value(py0 + float(r))), 3) for r in path_b]
    ys_wt = [round(max(0.0, y_cal.to_value(py0 + float(r))), 3) for r in path_wt]

    x_min, x_max = round(x_cal.to_value(px0), 1), round(x_cal.to_value(px1), 1)
    y_max_val, y_min_val = round(y_cal.to_value(py0), 3), round(y_cal.to_value(py1), 3)

    # Deletion window stats (between red dashed lines: rel cols 112..138 -> ~2030447..2030528 bp)
    del_ko = [y for x, y in zip(xs, ys_ko) if 2030455.0 <= x <= 2030522.0]
    del_wt = [y for x, y in zip(xs, ys_wt) if 2030455.0 <= x <= 2030522.0]

    return {
        "curves": {
            "ivory_ko_depth": {
                "x": xs,
                "y": ys_ko,
                "x_unit": "bp",
                "y_unit": "normalized_depth",
            },
            "wt_average_depth": {
                "x": xs,
                "y": ys_wt,
                "x_unit": "bp",
                "y_unit": "normalized_depth",
            },
        },
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": [x_min, x_max],
            "y_range": [y_min_val, y_max_val],
            "x_misfit_px": x_cal.misfit_px,
            "y_misfit_px": y_cal.misfit_px,
            "kind": "curves",
        },
        "extracted_data": {
            "x_tick_misfit_px": x_cal.misfit_px,
            "y_tick_misfit_px": y_cal.misfit_px,
            "deletion_alleles_bp": [82, 97],
            "ivory_ko_min_depth_in_deletion": round(min(del_ko), 3) if del_ko else None,
            "wt_mean_depth_in_deletion": round(float(np.mean(del_wt)), 3) if del_wt else None,
        },
    }


def _extract_3h_trace(
    crop_rgb: np.ndarray,
    y_ticks: list[float],
    plot_box: tuple[int, int, int, int],
    sex_label: str,
    reported_eff_pct: float,
) -> dict[str, Any]:
    """Digitize Sanger ICE/TIDE % aberrant sequence height envelopes (cortex mKO green vs WT black)."""
    y_cal = AxisCal.fit(y_ticks, [0.0, 20.0, 40.0, 60.0, 80.0, 100.0], scale="linear")
    # Bottom x-ticks at full x = [421, 468, 515, 562, 609, 656] -> rel x = [41, 88, 135, 182, 229, 276]
    x_cal = AxisCal.fit([41.0, 88.0, 135.0, 182.0, 229.0, 276.0], [100.0, 150.0, 200.0, 250.0, 300.0, 350.0], scale="linear")

    px0, py0, px1, py1 = plot_box
    sub_f = crop_rgb[py0:py1, px0:px1].astype(np.float32)
    h, w = sub_f.shape[:2]

    # Mask out upper-left sex icon / legend / "Total efficiency = XX.X%" text region up to the red cut site (col 170)
    txt_mask = np.zeros((h, w), dtype=bool)
    txt_mask[0:int(0.45 * h), 0:172] = True

    g_ex = sub_f[:, :, 1] - np.maximum(sub_f[:, :, 0], sub_f[:, :, 2])
    r_ex = sub_f[:, :, 0] - sub_f[:, :, 1]
    sat = sub_f.max(axis=2) - sub_f.min(axis=2)
    lum = sub_f.mean(axis=2)
    red_cut = (r_ex > 35.0) & (sub_f[:, :, 0] > 120.0)

    green_mask = (~txt_mask) & (~red_cut) & (g_ex > 16.0) & (sub_f[:, :, 1] > 95.0)
    wt_mask = (~txt_mask) & (~red_cut) & (sat < 26.0) & (lum < 145.0) & (r_ex < 25.0)

    # Bin every 4 px across Sanger sequencing positions (~90..385 bp) taking top envelope of bars
    step = 4
    cols = np.arange(2, w - 2, step, dtype=np.int32)
    xs: list[float] = []
    ys_mko: list[float] = []
    ys_wt: list[float] = []

    for c in cols:
        c0, c1 = max(0, int(c) - 1), min(w, int(c) + 2)
        g_rows = np.where(green_mask[:, c0:c1].any(axis=1))[0]
        w_rows = np.where(wt_mask[:, c0:c1].any(axis=1))[0]

        # Baseline is bottom of plot (row h-1 -> 0%)
        y_wt_px = float(w_rows[0]) if len(w_rows) else float(h - 1)
        # Green mKO bars rise over WT baseline; if no green ink above WT, falls back to WT/baseline
        y_g_px = float(g_rows[0]) if len(g_rows) else y_wt_px

        xv = round(x_cal.to_value(px0 + float(c)), 1)
        v_wt = round(max(0.0, min(100.0, y_cal.to_value(py0 + y_wt_px))), 2)
        v_mko = round(max(0.0, min(100.0, y_cal.to_value(py0 + min(y_g_px, y_wt_px)))), 2)
        xs.append(xv)
        ys_wt.append(v_wt)
        ys_mko.append(v_mko)

    x_min, x_max = round(x_cal.to_value(px0), 1), round(x_cal.to_value(px1), 1)
    y_max_val, y_min_val = round(y_cal.to_value(py0), 2), round(y_cal.to_value(py1), 2)

    cut_bp = round(x_cal.to_value(200.0), 1)  # full x=580 -> rel x=200
    pre_mko = [y for x, y in zip(xs, ys_mko) if x < cut_bp - 5.0]
    post_mko = [y for x, y in zip(xs, ys_mko) if x > cut_bp + 5.0]

    return {
        "curves": {
            f"cortex_mko_{sex_label}_aberrant_pct": {
                "x": xs,
                "y": ys_mko,
                "x_unit": "bp",
                "y_unit": "%",
            },
            f"wt_{sex_label}_aberrant_pct": {
                "x": xs,
                "y": ys_wt,
                "x_unit": "bp",
                "y_unit": "%",
            },
        },
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": [x_min, x_max],
            "y_range": [y_min_val, y_max_val],
            "x_misfit_px": x_cal.misfit_px,
            "y_misfit_px": y_cal.misfit_px,
            "kind": "curves",
        },
        "extracted_data": {
            "x_tick_misfit_px": x_cal.misfit_px,
            "y_tick_misfit_px": y_cal.misfit_px,
            "total_efficiency_pct": reported_eff_pct,
            "predicted_cut_site_bp": cut_bp,
            "pre_cut_mean_aberrant_pct": round(float(np.mean(pre_mko)), 1) if pre_mko else None,
            "post_cut_mean_aberrant_pct": round(float(np.mean(post_mko)), 1) if post_mko else None,
        },
    }


def extract_3h_female(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    """Digitize female cortex exon 2 G0 crispant Sanger aberrant trace (Total efficiency = 63.8%)."""
    # Crop bbox in full image: [380, 139, 695, 211] -> size 315 x 72
    # y-ticks inside crop: 0% at 67, 20% at 57, 40% at 47, 60% at 37, 80% at 27, 100% at 17
    return _extract_3h_trace(
        crop_rgb,
        y_ticks=[67.0, 57.0, 47.0, 37.0, 27.0, 17.0],
        plot_box=(30, 17, 310, 67),
        sex_label="female",
        reported_eff_pct=63.8,
    )


def extract_3h_male(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    """Digitize male cortex exon 2 G0 crispant Sanger aberrant trace (Total efficiency = 98.8%)."""
    # Crop bbox in full image: [380, 211, 695, 288] -> size 315 x 77
    # y-ticks inside crop: 0% at 58, 20% at 47.5, 40% at 37, 60% at 26.5, 80% at 16, 100% at 5.5
    return _extract_3h_trace(
        crop_rgb,
        y_ticks=[58.0, 47.5, 37.0, 26.5, 16.0, 5.5],
        plot_box=(30, 5, 310, 58),
        sex_label="male",
        reported_eff_pct=98.8,
    )
