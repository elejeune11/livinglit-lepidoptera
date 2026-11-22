"""Bespoke extractor for McDougal et al. (2021) Figure 5C, 5D, 5E, and 5F (pnas.202112009fig05.jpg):
- F5/C: Cover scale length (µm) vs pupal development (28–55%).
- F5/D: Cover scale width (µm) vs pupal development (28–55%).
- F5/E: Cover scale thickness (µm) vs pupal development (28–55%).
- F5/F: Estimated scale volume (pink) and surface area (black) as % of maximum vs pupal development (28–55%).

Uses uniform-column percentile background subtraction (removing white, dark-gray, and light-gray
vertical phase shading cleanly without edge halos), diagonal X-marker matched-filter detection
for all individual scale observations, and time-clustered mean trajectory reconstruction.
"""
from __future__ import annotations

from typing import Any
import numpy as np
from scipy.signal import fftconvolve

from livinglit_lepidoptera.extract_lib import AxisCal


_CFGS: dict[str, dict[str, Any]] = {
    "C": {"y_ticks_labels": [0.0, 100.0, 200.0], "y_max_exact": 243.51, "y_unit": "µm", "series": "cover_scale_length"},
    "D": {"y_ticks_labels": [0.0, 50.0],         "y_max_exact": 60.77,  "y_unit": "µm", "series": "cover_scale_width"},
    "E": {"y_ticks_labels": [0.0, 5.0],          "y_max_exact": 8.41,   "y_unit": "µm", "series": "cover_scale_thickness"},
    "F": {"y_ticks_labels": [0.0, 50.0, 100.0],  "y_max_exact": 140.0,  "y_unit": "%",  "series": "surface_area_pct"},
}


def _group_centres(idx: list[int], gap: int = 2) -> list[float]:
    if not idx:
        return []
    groups: list[list[int]] = [[int(idx[0])]]
    for i in idx[1:]:
        if int(i) - groups[-1][-1] <= gap:
            groups[-1].append(int(i))
        else:
            groups.append([int(i)])
    return [float(np.mean(g)) for g in groups]


def _detect_frame(crop_rgb: np.ndarray, panel_id: str) -> dict[str, Any]:
    g = crop_rgb.mean(axis=2)
    h, w = g.shape
    dk = g < 155.0
    v_cols = [c for c in range(w) if dk[:, c].sum() >= 0.50 * h]
    h_rows = [r for r in range(h) if dk[r, :].sum() >= 0.50 * w]
    vc_l, vc_r = min(v_cols), max(v_cols)
    hr_t, hr_b = min(h_rows), max(h_rows)

    cfg = _CFGS[panel_id]
    # Calibrate y-axis from bottom spine (y=0) and right-spine inward ticks
    y_hits = [r for r in range(hr_t + 3, hr_b - 3) if g[r, vc_r - 1] < 200.0]
    in_ticks = sorted(_group_centres(y_hits, gap=2), reverse=True)
    y_labels = cfg["y_ticks_labels"]
    if len(in_ticks) == len(y_labels) - 1:
        y_ticks = [float(hr_b)] + in_ticks
        y_cal = AxisCal.fit(y_ticks, y_labels, scale="linear")
    else:
        y_cal = AxisCal.fit([float(hr_b), float(hr_t)], [0.0, cfg["y_max_exact"]], scale="linear")

    # Shared x-axis spans [28.0, 55.0] % pupal development (makeFig5CDEF.m)
    x_cal = AxisCal.fit([float(vc_l), float(vc_r)], [28.0, 55.0], scale="linear")
    return {
        "plot_box": (vc_l + 1, hr_t + 1, vc_r - 1, hr_b - 1),
        "x_cal": x_cal,
        "y_cal": y_cal,
        "y_misfit_px": y_cal.misfit_px,
    }


def _col_residual(sub_rgb: np.ndarray) -> np.ndarray:
    f = sub_rgb.astype(np.float32)
    col_bg = np.percentile(f, 82, axis=0, keepdims=True)
    return np.clip(col_bg - f, 0.0, 255.0)


def _detect_x_markers(
    sig: np.ndarray,
    min_resp: float = 42.0,
    min_dark_cnt: float = 7.0,
    dark_thr: float = 42.0,
    min_dist: float = 3.5,
    excl: np.ndarray | None = None,
    max_pts: int = 20,
) -> list[tuple[float, float]]:
    """Diagonal 5x5 X-marker matched filter rejecting 1-px dotted lines and axis ticks."""
    ker = np.array([
        [ 0.8, -0.4, -0.6, -0.4,  0.8],
        [-0.4,  1.2, -0.2,  1.2, -0.4],
        [-0.6, -0.2,  1.4, -0.2, -0.6],
        [-0.4,  1.2, -0.2,  1.2, -0.4],
        [ 0.8, -0.4, -0.6, -0.4,  0.8],
    ], dtype=np.float64)
    ker /= np.maximum(ker, 0.0).sum()
    resp = fftconvolve(sig, ker, mode="same")
    cnt = fftconvolve((sig >= dark_thr).astype(np.float64), np.ones((5, 5)), mode="same")
    valid = (resp >= min_resp) & (cnt >= min_dark_cnt) & (sig >= dark_thr * 0.70)
    valid[:2, :] = False
    valid[-2:, :] = False
    valid[:, :3] = False
    valid[:, -3:] = False
    if excl is not None:
        valid &= ~excl

    H, W = sig.shape
    picked = np.zeros((H, W), dtype=bool)
    pts: list[tuple[float, float]] = []
    for _ in range(max_pts):
        m = valid & ~picked
        if not np.any(m):
            break
        sc = np.where(m, resp, -1e9)
        cy, cx = divmod(int(np.argmax(sc)), W)
        y0, y1 = max(0, cy - 1), min(H, cy + 2)
        x0, x1 = max(0, cx - 1), min(W, cx + 2)
        patch = np.maximum(0.0, resp[y0:y1, x0:x1] - resp[cy, cx] * 0.40)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        ry = float((yy * patch).sum() / max(float(patch.sum()), 1e-6))
        rx = float((xx * patch).sum() / max(float(patch.sum()), 1e-6))
        pts.append((rx, ry))
        ey0, ey1 = max(0, cy - 5), min(H, cy + 6)
        ex0, ex1 = max(0, cx - 5), min(W, cx + 6)
        yy_e, xx_e = np.mgrid[ey0:ey1, ex0:ex1]
        picked[ey0:ey1, ex0:ex1] |= ((yy_e - cy) ** 2 + (xx_e - cx) ** 2 <= min_dist ** 2)
    return pts


def _cluster_mean_curve(xs: list[float], ys: list[float], x_unit: str, y_unit: str) -> dict[str, Any]:
    if not xs:
        return {"x": [], "y": [], "peak_x": None, "peak_y": None, "x_unit": x_unit, "y_unit": y_unit}
    pairs = sorted(zip(xs, ys))
    clusters: list[list[tuple[float, float]]] = [[pairs[0]]]
    for p in pairs[1:]:
        if p[0] - clusters[-1][-1][0] <= 1.8:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    mx = [round(float(np.mean([p[0] for p in cl])), 2) for cl in clusters]
    my = [round(float(np.mean([p[1] for p in cl])), 2) for cl in clusters]
    idx = int(np.argmax(my))
    return {"x": mx, "y": my, "peak_x": mx[idx], "peak_y": my[idx], "x_unit": x_unit, "y_unit": y_unit}


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    ax = _detect_frame(crop_rgb, panel_id)
    px0, py0, px1, py1 = ax["plot_box"]
    x_cal = ax["x_cal"]
    y_cal = ax["y_cal"]
    cfg = _CFGS[panel_id]
    y_unit = cfg["y_unit"]

    sub = crop_rgb[py0:py1, px0:px1]
    res = _col_residual(sub)

    scatter: dict[str, Any] = {}
    curves: dict[str, Any] = {}

    if panel_id == "F":
        excl = np.zeros(sub.shape[:2], dtype=bool)
        # Exclude bottom-right legend box ("Volume / Surface Area")
        excl[36:, 44:] = True
        pink_ex = np.clip(sub[:, :, 0].astype(np.float32) - sub[:, :, 1].astype(np.float32), 0.0, 255.0)
        pink_sig = np.where(pink_ex > 22.0, res[:, :, 1] * 1.15, 0.0)
        blk_sig = np.where(pink_ex <= 22.0, res.mean(axis=2), 0.0)
        for name, sig, mr, mc, dt in [
            ("est_volume_pct", pink_sig, 36.0, 6.0, 36.0),
            ("est_surface_area_pct", blk_sig, 40.0, 6.0, 40.0),
        ]:
            pts = _detect_x_markers(sig, min_resp=mr, min_dark_cnt=mc, dark_thr=dt, min_dist=3.4, excl=excl)
            pairs = sorted((round(x_cal.to_value(px0 + rx), 2), round(y_cal.to_value(py0 + ry), 2)) for rx, ry in pts)
            xs_o = [p[0] for p in pairs]
            ys_o = [p[1] for p in pairs]
            scatter[name] = {"x": xs_o, "y": ys_o, "n": len(xs_o), "x_unit": "% development", "y_unit": y_unit}
            curves[f"{name}_mean"] = _cluster_mean_curve(xs_o, ys_o, "% development", y_unit)
    else:
        lum_res = res.mean(axis=2)
        pts = _detect_x_markers(lum_res, min_resp=42.0, min_dark_cnt=7.0, dark_thr=42.0, min_dist=3.5)
        pairs = sorted((round(x_cal.to_value(px0 + rx), 2), round(y_cal.to_value(py0 + ry), 2)) for rx, ry in pts)
        xs_o = [p[0] for p in pairs]
        ys_o = [p[1] for p in pairs]
        sname = cfg["series"]
        scatter[sname] = {"x": xs_o, "y": ys_o, "n": len(xs_o), "x_unit": "% development", "y_unit": y_unit}
        curves[f"{sname}_mean"] = _cluster_mean_curve(xs_o, ys_o, "% development", y_unit)

    x_min, x_max = round(x_cal.to_value(px0), 4), round(x_cal.to_value(px1), 4)
    y_min, y_max = round(y_cal.to_value(py1), 4), round(y_cal.to_value(py0), 4)

    return {
        "digitized_scatter": scatter,
        "curves": curves,
        "overlay_meta": {
            "plot_box": [int(px0), int(py0), int(px1), int(py1)],
            "x_range": [x_min, x_max],
            "y_range": [y_min, y_max],
            "y_misfit_px": round(float(ax["y_misfit_px"]), 3),
            "mode": "scatter_2d",
            "kind": "scatter",
        },
        "extracted_data": {
            "y_tick_misfit_px": round(float(ax["y_misfit_px"]), 3),
            "n_markers_total": int(sum(g["n"] for g in scatter.values())),
        },
    }
