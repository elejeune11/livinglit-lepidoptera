"""Custom per-figure extractor for Loh et al. (2025) Figure 10 (pbio.3003233.g010.png):
- 10A: Auto-calibrated boxplots of -log10(p_val_adj) by Bab ChIP peak count (0, 1-10, 10+)
- 10B: Complete 21-gene x 8-cluster UVI-DE expression dotplot matrix (168 cells) extracting:
       (a) % expressing cells from exact circle diameter calibrated against the figure's own 0/25/50/75/100% legend
       (b) average expression within cluster from exact RGB nearest-neighbor lookup along the figure's [-1, +2.5] colorbar
- 10C: Auto-calibrated volcano plot (-log10 p_val_adj vs log2FC) extracting colored Bab-bound UVI-DE genes
"""
from __future__ import annotations

from typing import Any
import numpy as np

from livinglit_lepidoptera.extract_lib import detect_markers_matched_filter, find_axis_ticks


_CLUSTERS = ["1a", "1b", "1c", "1d", "1e", "2 (spatulate)", "3 (UVI)", "4"]
_GENES = [
    "Bab", "Eip75B", "Mwh", "Drak", "CAP", "Dachsous", "Bazooka", "Fimbrin", "Formin-like",
    "Cog3", "Arl4", "Klp31E", "Steppke", "Ectodermal", "ObstE/Gasp", "Osi17", "Cpr92F",
    "Cpr92F-like", "ChLD3", "lncRNA (bantam)", "ABCG20",
]
_ROW_YS = [418, 510, 602, 694, 786, 878, 970, 1062]
_COL_XS = [1765, 1854, 1943, 2032, 2121, 2210, 2299, 2388, 2477, 2567, 2655, 2744, 2833, 2922, 3011, 3100, 3189, 3279, 3366, 3455, 3539]


def _extract_10a(crop_rgb: np.ndarray) -> dict[str, Any]:
    px0, py0, px1, py1 = (150, 240, 1050, 1440)
    ax = find_axis_ticks(
        crop_rgb,
        y_labels=[0.0, 50.0, 100.0, 150.0],
        x_labels=None,
        min_spine_frac=0.55,
        probe=(2, 11),
    )
    y_cal = ax["y_cal"]
    y_max = y_cal.to_value(py0)
    y_min = y_cal.to_value(py1)
    sub = crop_rgb[py0:py1, px0:px1].astype(np.float64)
    h, _ = sub.shape[:2]
    sat = np.max(sub, axis=2) - np.min(sub, axis=2)
    mean = np.mean(sub, axis=2)

    def y_val(r: float) -> float:
        return round(max(0.0, y_cal.to_value(py0 + r)), 2)

    groups_cfg = [
        ("bab_peaks_0",    159, 55),
        ("bab_peaks_1_10", 426, 55),
        ("bab_peaks_10p",  695, 55),
    ]
    bp: dict[str, Any] = {}
    gmeta: dict[str, Any] = {}
    for gname, cx, hw in groups_cfg:
        strip_sat = sat[:, cx - hw:cx + hw + 1]
        strip_m = mean[:, cx - hw:cx + hw + 1]
        box_rows = np.where((strip_sat > 45.0).mean(axis=1) >= 0.45)[0]
        if len(box_rows) >= 4:
            r_top, r_bot = int(box_rows.min()), int(box_rows.max())
            inner_m = strip_m[r_top:r_bot + 1, hw // 2:hw + hw // 2].mean(axis=1)
            r_med = float(r_top + int(np.argmin(inner_m)))
            up = r_top
            for r in range(r_top - 1, max(0, r_top - 400), -1):
                if mean[r, cx - 5:cx + 6].min() < 75.0:
                    up = r
                else:
                    break
            dn = r_bot
            for r in range(r_bot + 1, min(h - 1, r_bot + 100)):
                if mean[r, cx - 5:cx + 6].min() < 75.0:
                    dn = r
                else:
                    break
            bp[gname] = {
                "median": y_val(r_med),
                "q1": y_val(float(r_bot)),
                "q3": y_val(float(r_top)),
                "whisker_lo": y_val(float(dn)),
                "whisker_hi": y_val(float(up)),
                "y_unit": "-log10(p_adj)",
            }
            gmeta[gname] = {"x_center": cx, "half_width": hw}

    return {
        "digitized_boxplots": bp,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "y_range": [round(y_min, 2), round(y_max, 2)],
            "y_misfit_px": round(float(ax["y_misfit_px"]), 3),
            "groups": gmeta,
            "kind": "boxplots",
        },
    }


def _extract_10b(crop_rgb: np.ndarray, full_rgb: np.ndarray, bbox: tuple[int, int, int, int]) -> dict[str, Any]:
    """Read all 21 genes x 8 clusters = 168 dotplot circles directly from F10B pixels + colorbar."""
    bx0, by0, _, _ = bbox
    cb_strip = full_rgb[105:118, 3248:3543, :].mean(axis=0).astype(np.float64)
    cb_vals = np.linspace(-1.0, 2.5, cb_strip.shape[0])

    d_knots = np.array([0.0, 6.0, 19.0, 31.5, 44.5, 57.0])
    p_knots = np.array([0.0, 0.0, 25.0, 50.0, 75.0, 100.0])

    cells = []
    for cl_name, gy in zip(_CLUSTERS, _ROW_YS):
        for gene_name, gx in zip(_GENES, _COL_XS):
            patch = full_rgb[gy - 37:gy + 38, gx - 37:gx + 38, :].astype(np.float64)
            dist_w = np.linalg.norm(255.0 - patch, axis=2)
            dot_mk = dist_w > 18.0
            area = float(dot_mk.sum())
            if area < 9.0:
                diam, pct, expr, r_px = 0.0, 0.0, 0.0, 1.0
            else:
                diam = float(2.0 * np.sqrt(area / np.pi))
                r_px = diam / 2.0
                pct = float(np.clip(np.interp(diam, d_knots, p_knots), 0.0, 100.0))
                yy, xx = np.ogrid[-37:38, -37:38]
                core = (xx * xx + yy * yy) <= max(2.25, (0.55 * r_px) ** 2)
                mean_col = patch[core].mean(axis=0)
                idx = int(np.argmin(np.linalg.norm(cb_strip - mean_col[None, :], axis=1)))
                expr = float(cb_vals[idx])
            cells.append({
                "cluster": cl_name,
                "gene": gene_name,
                "pct": round(pct, 1),
                "expr": round(expr, 2),
                "px": int(gx - bx0),
                "py": int(gy - by0),
                "r_px": round(r_px, 1),
            })

    return {
        "dotplot_matrix": {
            "clusters": _CLUSTERS,
            "genes": _GENES,
            "cells": cells,
            "expr_range": [-1.0, 2.5],
        },
        "extracted_data": {
            "n_genes": len(_GENES),
            "n_clusters": len(_CLUSTERS),
            "n_cells_extracted": len(cells),
        },
    }


def _extract_10c(crop_rgb: np.ndarray) -> dict[str, Any]:
    """Auto-calibrated volcano plot (-log10 p_adj vs log2FC) colored by Bab ChIP peak bins."""
    px0, py0, px1, py1 = (150, 220, 1340, 1384)
    ax = find_axis_ticks(
        crop_rgb,
        y_labels=[0.0, 50.0, 100.0, 150.0],
        x_labels=[-4.0, 0.0, 4.0],
        min_spine_frac=0.55,
        y_probe=(2, 11),
        x_probe=(1, 9),
        tick_min_frac=0.40,
    )
    x_cal, y_cal = ax["x_cal"], ax["y_cal"]
    x_min, x_max = x_cal.to_value(px0), x_cal.to_value(px1)
    y_max, y_min = y_cal.to_value(py0), y_cal.to_value(py1)

    sub = crop_rgb[py0:py1, px0:px1].astype(np.float64)
    h, w = sub.shape[:2]
    excl = np.zeros((h, w), dtype=bool)
    excl[0:560, 0:340] = True

    sat = sub.max(axis=2) - sub.min(axis=2)
    lum = sub.mean(axis=2)
    high_mk = (sub[:, :, 1] > 145) & (sub[:, :, 0] > 90) & (sub[:, :, 2] < 135) & (sat > 50) & (~excl)
    med_mk = (sub[:, :, 2] > 105) & (sub[:, :, 1] > 75) & (sub[:, :, 0] < 115) & (sat > 42) & (~high_mk) & (~excl)
    low_mk = (sub[:, :, 2] > 65) & (sub[:, :, 0] < 110) & (sub[:, :, 1] < 95) & (sat > 30) & (lum < 145) & (~high_mk) & (~med_mk) & (~excl)

    scatter: dict[str, Any] = {}
    for gname, mk in [
        ("bab_peaks_10_plus", high_mk),
        ("bab_peaks_3_to_9", med_mk),
        ("bab_peaks_1_to_2", low_mk),
    ]:
        hits = detect_markers_matched_filter(
            mk,
            occ=np.zeros_like(mk, dtype=bool),
            radius=4.0,
            shape="disk",
            min_visible=0.35,
            max_bg=0.22,
            min_score=0.35,
            min_sep_factor=1.4,
            max_markers=120,
            upsample=1,
        )
        xs = [round(x_cal.to_value(px0 + d["x"]), 3) for d in hits]
        ys = [round(max(0.0, y_cal.to_value(py0 + d["y"])), 2) for d in hits]
        scatter[gname] = {
            "x": xs,
            "y": ys,
            "n": len(xs),
            "x_unit": "log2FC",
            "y_unit": "-log10(p_adj)",
        }

    return {
        "digitized_scatter": scatter,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": [round(x_min, 3), round(x_max, 3)],
            "y_range": [round(y_min, 2), round(y_max, 2)],
            "x_misfit_px": round(float(ax["x_misfit_px"]), 3),
            "y_misfit_px": round(float(ax["y_misfit_px"]), 3),
            "kind": "scatter",
        },
    }


def extract(crop_rgb: np.ndarray, panel_id: str, full_rgb: np.ndarray | None = None, bbox: tuple[int, int, int, int] = (0, 0, 0, 0), **_: Any) -> dict[str, Any]:
    if panel_id == "A":
        return _extract_10a(crop_rgb)
    if panel_id == "C":
        return _extract_10c(crop_rgb)
    return _extract_10b(crop_rgb, full_rgb if full_rgb is not None else crop_rgb, bbox)
