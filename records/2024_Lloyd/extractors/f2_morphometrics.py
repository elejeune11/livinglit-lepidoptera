"""Bespoke extractor for Lloyd et al. (2024) Figure 2 (41467_2024_48060_Fig2_HTML.jpg):
- F2/D: Ridge number vs Scale width — individual blue/black scatter points + IRLS OLS lines & 95% CI ribbons.
- F2/E: Ridge number vs Ridge spacing — individual blue/black scatter points.
- F2/F: Ridge spacing vs Ridge width — individual blue/black scatter points + IRLS OLS lines & 95% CI ribbons.
- F2/J: Pupal actin bundle width (50%) — notched boxplots (Q1/median/Q3/whiskers) + jittered scale dots.
- F2/K: Pupal actin bundle spacing (50%) — notched boxplots + jittered scale dots.
- F2/L: Pupal actin bundle number (50%) — notched boxplots + jittered scale dots + adult ridge ref lines.
"""
from __future__ import annotations

from typing import Any
import numpy as np

from livinglit_lepidoptera.extract_lib import fit_irls_line_and_ci
from livinglit_lepidoptera.figures.source import blobs


_SCATTER_CFGS = {
    "D": {"pbox": (35, 30, 208, 185), "xr": (24.2, 51.8), "yr": (21.0, 66.2), "xu": "µm", "yu": "ridges", "has_fit": True},
    "E": {"pbox": (35, 32, 209, 187), "xr": (0.645, 1.17), "yr": (21.5, 65.8), "xu": "µm", "yu": "ridges", "has_fit": False},
    "F": {"pbox": (39, 34, 211, 190), "xr": (0.268, 0.378), "yr": (0.65, 1.14), "xu": "µm", "yu": "µm", "has_fit": True},
}

_BOX_CFGS = {
    "J": {
        "pbox": (55, 18, 242, 212),
        "yr": (0.384, 0.504),
        "yu": "µm",
        "groups": {
            "black_pupal": {"xc": 54, "hw": 26, "rgb": (145, 145, 145)},
            "blue_pupal": {"xc": 138, "hw": 26, "rgb": (157, 205, 244)},
        },
    },
    "K": {
        "pbox": (45, 18, 242, 213),
        "yr": (0.796, 1.626),
        "yu": "µm",
        "groups": {
            "black_pupal": {"xc": 54, "hw": 26, "rgb": (145, 145, 145)},
            "blue_pupal": {"xc": 144, "hw": 26, "rgb": (157, 205, 244)},
        },
    },
    "L": {
        "pbox": (39, 18, 242, 216),
        "yr": (23.765, 55.83),
        "yu": "bundles",
        "groups": {
            "black_pupal": {"xc": 54, "hw": 26, "rgb": (145, 145, 145)},
            "blue_pupal": {"xc": 145, "hw": 26, "rgb": (157, 205, 244)},
        },
    },
}


def _extract_scatter(crop_rgb: np.ndarray, panel_id: str) -> dict[str, Any]:
    cfg = _SCATTER_CFGS[panel_id]
    px0, py0, px1, py1 = cfg["pbox"]
    sub = crop_rgb[py0:py1, px0:px1].astype(np.int16)
    h, w = sub.shape[:2]
    x_min, x_max = cfg["xr"]
    y_min, y_max = cfg["yr"]

    def px2x(px: float) -> float:
        return round(x_min + (px / max(w, 1)) * (x_max - x_min), 4)

    def py2y(py: float) -> float:
        return round(y_max - (py / max(h, 1)) * (y_max - y_min), 4)

    sat = np.max(sub, axis=2) - np.min(sub, axis=2)
    lum = np.mean(sub, axis=2)

    blue_d = np.max(np.abs(sub - np.array([115, 182, 238], dtype=np.int16)), axis=2)
    blue_mk = (blue_d <= 48) & (sat >= 22)
    gray_d = np.max(np.abs(sub - np.array([108, 108, 108], dtype=np.int16)), axis=2)
    gray_mk = (gray_d <= 38) & (sat < 18) & (lum < 155)

    sc_out: dict[str, Any] = {}
    for gname, mk in [("blue_iridescent", blue_mk), ("black_noniridescent", gray_mk)]:
        bs = blobs(mk, min_area=3, max_area=600)
        xs = [px2x(b["x"]) for b in bs]
        ys = [py2y(b["y"]) for b in bs]
        order = np.argsort(xs)
        xs = [xs[i] for i in order]
        ys = [ys[i] for i in order]
        sc_out[gname] = {
            "n": len(xs),
            "x": xs,
            "y": ys,
            "mean_x": round(float(np.mean(xs)), 4) if xs else None,
            "mean_y": round(float(np.mean(ys)), 4) if ys else None,
            "x_unit": cfg["xu"],
            "y_unit": cfg["yu"],
        }

    out: dict[str, Any] = {
        "digitized_scatter": sc_out,
        "overlay_meta": {
            "plot_box": list(cfg["pbox"]),
            "x_range": list(cfg["xr"]),
            "y_range": list(cfg["yr"]),
            "mode": "scatter_2d",
            "kind": "scatter",
        },
    }

    if cfg["has_fit"]:
        curves: dict[str, Any] = {}
        blue_rib = ((sub[:, :, 2] - sub[:, :, 0]) >= 16) & (lum >= 182) & (lum <= 242)
        gray_rib = (sat < 14) & (lum >= 168) & (lum <= 232)
        for cname, gkey, rmk in [
            ("blue_regression", "blue_iridescent", blue_rib),
            ("black_regression", "black_noniridescent", gray_rib),
        ]:
            gxs = sc_out[gkey]["x"]
            if not gxs:
                continue
            c_lo = max(2, int(round((min(gxs) - x_min) / max(x_max - x_min, 1e-9) * w)))
            c_hi = min(w - 3, int(round((max(gxs) - x_min) / max(x_max - x_min, 1e-9) * w)))
            try:
                cols, ym, ylo, yhi = fit_irls_line_and_ci(rmk, c_lo, c_hi, n_pts=32, max_hw=18.0)
            except ValueError:
                continue
            cxs = [px2x(float(c)) for c in cols]
            cys = [py2y(float(y)) for y in ym]
            clo = [py2y(float(y)) for y in ylo]
            chi = [py2y(float(y)) for y in yhi]
            curves[cname] = {
                "x": cxs,
                "y": cys,
                "lo": clo,
                "hi": chi,
                "peak_x": cxs[-1],
                "peak_y": cys[-1],
                "x_unit": cfg["xu"],
                "y_unit": cfg["yu"],
            }
        if curves:
            out["curves"] = curves

    return out


def _extract_boxplot(crop_rgb: np.ndarray, panel_id: str) -> dict[str, Any]:
    cfg = _BOX_CFGS[panel_id]
    px0, py0, px1, py1 = cfg["pbox"]
    sub = crop_rgb[py0:py1, px0:px1].astype(np.int16)
    h, w = sub.shape[:2]
    y_min, y_max = cfg["yr"]

    def py2y(py: float) -> float:
        return round(y_max - (py / max(h, 1)) * (y_max - y_min), 4)

    bp_out: dict[str, Any] = {}
    groups_meta: dict[str, dict[str, int]] = {}
    lum = np.mean(sub, axis=2)

    for gname, gcfg in cfg["groups"].items():
        xc = int(gcfg["xc"])
        hw = int(gcfg["hw"])
        groups_meta[gname] = {"x_center": xc, "half_width": hw}
        x_lo = max(0, xc - hw)
        x_hi = min(w, xc + hw)
        strip = sub[:, x_lo:x_hi]
        strip_lum = lum[:, x_lo:x_hi]
        # Avoid significance bracket near top (y < 14 px)
        valid_r0 = 14

        rgb = np.array(gcfg["rgb"], dtype=np.int16)
        fill_dist = np.max(np.abs(strip - rgb[None, None, :]), axis=2)
        fill_mask = fill_dist <= 38
        fill_mask[:valid_r0, :] = False
        row_fill_frac = fill_mask.mean(axis=1)
        box_rows = np.where(row_fill_frac >= 0.45)[0]

        if len(box_rows) < 5:
            bp_out[gname] = {
                "median": None, "q1": None, "q3": None,
                "whisker_lo": None, "whisker_hi": None, "y_unit": cfg["yu"],
            }
            continue

        # Q3 (top) and Q1 (bottom) of notched box
        q3_px = int(box_rows[0])
        q1_px = int(box_rows[-1])
        # Median line: darkest horizontal stroke inside the notched interior
        mid_r0 = q3_px + max(2, int(0.18 * (q1_px - q3_px)))
        mid_r1 = q1_px - max(2, int(0.18 * (q1_px - q3_px)))
        if mid_r1 <= mid_r0:
            mid_r0, mid_r1 = q3_px, q1_px + 1
        # Use central narrow band (notch waist) to locate dark median stroke
        c0 = max(0, hw - 10)
        c1 = min(strip.shape[1], hw + 10)
        row_med_lum = strip_lum[mid_r0:mid_r1, c0:c1].mean(axis=1)
        med_px = int(mid_r0 + int(np.argmin(row_med_lum)))

        # Whiskers: locate the exact vertical whisker column near center (narrowest dark vertical stroke)
        # ggplot2 boxplot whiskers are ~1px dark-gray (#333/#666 -> lum < 210) centered near x_center
        c_w0, c_w1 = max(0, hw - 6), min(strip.shape[1], hw + 7)
        stem = strip_lum[:, c_w0:c_w1].min(axis=1)
        w_hi_px = q3_px
        gap = 0
        for r in range(q3_px - 1, valid_r0 - 1, -1):
            if stem[r] < 215:
                w_hi_px = r
                gap = 0
            else:
                gap += 1
                if gap > 5:
                    break
        w_lo_px = q1_px
        gap = 0
        for r in range(q1_px + 1, h - 1):
            if stem[r] < 215:
                w_lo_px = r
                gap = 0
            else:
                gap += 1
                if gap > 5:
                    break

        bp_out[gname] = {
            "median": py2y(med_px),
            "q1": py2y(q1_px),
            "q3": py2y(q3_px),
            "whisker_lo": py2y(w_lo_px),
            "whisker_hi": py2y(w_hi_px),
            "y_unit": cfg["yu"],
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
    if panel_id in _SCATTER_CFGS:
        return _extract_scatter(crop_rgb, panel_id)
    if panel_id in _BOX_CFGS:
        return _extract_boxplot(crop_rgb, panel_id)
    raise ValueError(f"Unknown Lloyd Fig 2 panel_id: {panel_id}")
