"""Bespoke extractor for Lloyd et al. (2024) Figure 2 (41467_2024_48060_Fig2_HTML.jpg):
- F2/D: Ridge number vs Scale width — occlusion-aware matched-filter peeling of ALL blue/black
  cover (circle) and ground (triangle) markers (including overlapping clusters & points sitting
  inside shaded 95% CI ribbons) + IRLS OLS lines & 95% CI ribbons.
- F2/E: Ridge number vs Ridge spacing — occlusion-aware matched-filter peeling of ALL markers.
- F2/F: Ridge spacing vs Ridge width — occlusion-aware matched-filter peeling of ALL markers
  (including inside both shaded 95% CI ribbons) + IRLS OLS lines & 95% CI ribbons.
- F2/J, F2/K, F2/L: Pupal actin bundle width, spacing, and number (50%) — BOTH notched boxplots
  (Q1/median/Q3/whiskers) AND individual pupal jitter scatter dots (on white AND inside shaded boxes!).
"""
from __future__ import annotations

from typing import Any
import cv2
import numpy as np

from livinglit_lepidoptera.extract_lib import (
    detect_markers_matched_filter,
    fit_irls_line_and_ci,
    shaded_bg_residual,
)


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


def _detect_circles_and_triangles(tgt: np.ndarray, occ: np.ndarray) -> list[dict[str, Any]]:
    """Two-pass occlusion-aware matched-filter peeling for mixed circle + upward-triangle markers."""
    pts1 = detect_markers_matched_filter(
        tgt, occ, radius=1.95, shape="disk",
        min_visible=0.38, max_bg=0.19, min_score=0.32,
        min_sep_factor=1.65, peel=True, peel_radius_factor=1.22, upsample=3, border_px=1,
    )
    tgt2 = tgt.copy()
    occ2 = occ.copy()
    H, W = tgt.shape
    yy, xx = np.mgrid[0:H, 0:W]
    for p in pts1:
        foot = ((xx - p["x"]) ** 2 + (yy - p["y"]) ** 2) <= (2.55 ** 2)
        occ2 |= (tgt2 & foot)
        tgt2 &= ~foot
    pts2 = detect_markers_matched_filter(
        tgt2, occ2, radius=2.55, shape="triangle_up",
        min_visible=0.40, max_bg=0.19, min_score=0.32,
        min_sep_factor=1.45, peel=True, peel_radius_factor=1.10, upsample=3, border_px=1,
    )
    out = list(pts1)
    for p in pts2:
        if all((p["x"] - q["x"]) ** 2 + (p["y"] - q["y"]) ** 2 >= 3.6 ** 2 for q in out):
            out.append(p)
    return out


def _extract_scatter(crop_rgb: np.ndarray, panel_id: str) -> dict[str, Any]:
    cfg = _SCATTER_CFGS[panel_id]
    px0, py0, px1, py1 = cfg["pbox"]
    sub_f = crop_rgb[py0:py1, px0:px1].astype(np.float32)
    h, w = sub_f.shape[:2]
    x_min, x_max = cfg["xr"]
    y_min, y_max = cfg["yr"]

    def px2x(px: float) -> float:
        return round(x_min + (px / max(w, 1)) * (x_max - x_min), 4)

    def py2y(py: float) -> float:
        return round(y_max - (py / max(h, 1)) * (y_max - y_min), 4)

    r, g, b = sub_f[:, :, 0], sub_f[:, :, 1], sub_f[:, :, 2]
    sat = np.max(sub_f, axis=2) - np.min(sub_f, axis=2)
    lum = np.mean(sub_f, axis=2)

    # Measured pixel physics: empty gray CI ribbon has lum >= 176 and empty blue CI ribbon has R >= 184;
    # every real marker (on white OR inside either translucent ribbon) sits strictly below these thresholds,
    # while thin ~1.5 px regression lines fail the disk/triangle matched-filter background penalty!
    r_thr = 175.0 if cfg["has_fit"] else 195.0
    g_thr = 164.0 if cfg["has_fit"] else 185.0
    blue_tgt = ((b - r) >= 32.0) & (r <= r_thr) & (b >= 170.0)
    gray_tgt = (sat < 22.0) & (lum <= g_thr) & ~blue_tgt
    both_ov = ((b - r) >= 14.0) & ((b - r) < 32.0) & (r <= 152.0) & (lum <= 164.0)

    sc_out: dict[str, Any] = {}
    for gname, tgt, occ in [
        ("blue_iridescent", blue_tgt, gray_tgt | both_ov),
        ("black_noniridescent", gray_tgt, blue_tgt | both_ov),
    ]:
        pts = _detect_circles_and_triangles(tgt, occ)
        xs = [px2x(p["x"]) for p in pts]
        ys = [py2y(p["y"]) for p in pts]
        order = np.argsort(xs)
        xs = [xs[i] for i in order]
        ys = [ys[i] for i in order]
        sc_out[gname] = {
            "n": len(xs),
            "x": xs,
            "y": ys,
            "mean_x": round(float(np.mean(xs)), 4) if xs else None,
            "mean_y": round(float(np.mean(ys)), 4) if ys else None,
            "n_occluded": int(sum(1 for p in pts if p["occluded"])),
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
        blue_rib = ((b - r) >= 16.0) & (lum >= 182.0) & (lum <= 242.0)
        gray_rib = (sat < 14.0) & (lum >= 168.0) & (lum <= 232.0)
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


def _big_box_polygon(raw_mask: np.ndarray, min_area: int = 120) -> np.ndarray:
    num, lab, stats, _ = cv2.connectedComponentsWithStats(raw_mask.astype(np.uint8))
    out = np.zeros_like(raw_mask, dtype=bool)
    for k in range(1, num):
        if stats[k, cv2.CC_STAT_AREA] >= min_area:
            out |= (lab == k)
    return cv2.dilate(out.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0


def _extract_boxplot(crop_rgb: np.ndarray, panel_id: str) -> dict[str, Any]:
    cfg = _BOX_CFGS[panel_id]
    px0, py0, px1, py1 = cfg["pbox"]
    sub_u8 = crop_rgb[py0:py1, px0:px1]
    sub = sub_u8.astype(np.int16)
    sub_f = sub_u8.astype(np.float32)
    h, w = sub.shape[:2]
    y_min, y_max = cfg["yr"]

    def py2y(py: float) -> float:
        return round(y_max - (py / max(h, 1)) * (y_max - y_min), 4)

    bp_out: dict[str, Any] = {}
    sc_out: dict[str, Any] = {}
    groups_meta: dict[str, dict[str, int]] = {}
    r_ch, g_ch, b_ch = sub_f[:, :, 0], sub_f[:, :, 1], sub_f[:, :, 2]
    lum = np.mean(sub_f, axis=2)
    sat = np.max(sub_f, axis=2) - np.min(sub_f, axis=2)
    _, res_m = shaded_bg_residual(sub_u8, marker_diam_px=7, mode="median")
    res_lum = res_m.mean(axis=2)
    res_r = res_m[:, :, 0]

    gray_box_poly = _big_box_polygon((sat < 16.0) & (lum >= 122.0) & (lum <= 172.0))
    blue_box_poly = _big_box_polygon(((b_ch - r_ch) >= 40.0) & (r_ch >= 125.0) & (r_ch <= 185.0) & (b_ch >= 210.0))

    for gname, gcfg in cfg["groups"].items():
        xc = int(gcfg["xc"])
        hw = int(gcfg["hw"])
        groups_meta[gname] = {"x_center": xc, "half_width": hw}
        x_lo = max(0, xc - hw)
        x_hi = min(w, xc + hw)
        strip = sub[:, x_lo:x_hi]
        strip_lum = lum[:, x_lo:x_hi]
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
        else:
            q3_px = int(box_rows[0])
            q1_px = int(box_rows[-1])
            mid_r0 = q3_px + max(2, int(0.18 * (q1_px - q3_px)))
            mid_r1 = q1_px - max(2, int(0.18 * (q1_px - q3_px)))
            if mid_r1 <= mid_r0:
                mid_r0, mid_r1 = q3_px, q1_px + 1
            c0 = max(0, hw - 10)
            c1 = min(strip.shape[1], hw + 10)
            row_med_lum = strip_lum[mid_r0:mid_r1, c0:c1].mean(axis=1)
            med_px = int(mid_r0 + int(np.argmin(row_med_lum)))

            c_w0, c_w1 = max(0, hw - 6), min(strip.shape[1], hw + 7)
            stem = strip_lum[:, c_w0:c_w1].min(axis=1)
            w_hi_px = q3_px
            gap = 0
            for rr in range(q3_px - 1, valid_r0 - 1, -1):
                if stem[rr] < 215:
                    w_hi_px = rr
                    gap = 0
                else:
                    gap += 1
                    if gap > 5:
                        break
            w_lo_px = q1_px
            gap = 0
            for rr in range(q1_px + 1, h - 1):
                if stem[rr] < 215:
                    w_lo_px = rr
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

        # Extract ALL individual pupal jitter scatter dots (both on white AND inside the shaded notched box!)
        jx0, jx1 = max(2, xc - 16), min(w - 2, xc + 16)
        if "blue" in gname:
            on_white = (~blue_box_poly) & ((b_ch - r_ch) >= 22.0) & (r_ch <= 216.0)
            on_box = blue_box_poly & ((b_ch - r_ch) >= 52.0) & (r_ch <= 142.0) & (res_r >= 10.0)
            tgt = on_white | on_box
            occ = (sat < 22.0) & (lum < 155.0)
        else:
            on_white = (~gray_box_poly) & (sat < 18.0) & (lum <= 212.0) & (lum >= 95.0)
            on_box = gray_box_poly & (sat < 18.0) & (lum <= 128.0) & (res_lum >= 10.0)
            tgt = on_white | on_box
            occ = (sat < 20.0) & (lum < 95.0)

        tgt[:2, :] = False
        tgt[:13, 62:132] = False  # significance bracket "***"
        tgt[:, :jx0] = False
        tgt[:, jx1:] = False

        pts = detect_markers_matched_filter(
            tgt, occ, radius=2.65, shape="disk",
            min_visible=0.38, max_bg=0.22, min_score=0.28,
            min_sep_factor=1.50, peel=True, peel_radius_factor=1.12, upsample=3, border_px=1,
        )
        pts.sort(key=lambda p: p["y"], reverse=True)
        sc_out[gname] = {
            "n": len(pts),
            "x": [round(p["x"] / max(w, 1), 4) for p in pts],
            "y": [py2y(p["y"]) for p in pts],
            "mean_y": round(float(np.mean([py2y(p["y"]) for p in pts])), 4) if pts else None,
            "sd_y": round(float(np.std([py2y(p["y"]) for p in pts], ddof=1)), 4) if len(pts) > 1 else None,
            "n_occluded": int(sum(1 for p in pts if p["occluded"])),
            "x_unit": "",
            "y_unit": cfg["yu"],
        }

    return {
        "digitized_boxplots": bp_out,
        "digitized_scatter": sc_out,
        "overlay_meta": {
            "plot_box": list(cfg["pbox"]),
            "x_range": [0.0, 1.0],
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
