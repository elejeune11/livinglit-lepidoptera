"""Bespoke extractor for McDougal et al. (2021) Figure 5G and 5H (pnas.202112009fig05.jpg):
- F5/G: Actin/ridge spacing (µm) over 28–95% pupal development (Group 1 black early-actin X markers +
  Group 2 four cyan/teal single-scale tracks 47–61% + Group 3 three dark-teal single-scale tracks 61–89%).
- F5/H_height: Pooled mean ± SD nascent ridge height (nm, purple vertical error bars) across 10 time points (34.8–41.0%).
- F5/H_spacing: Mean ± SD nascent ridge periodicity (µm, teal vertical error bars) across 10 time points (34.8–41.0%).

Uses inward-tick `AxisCal.fit`, uniform-column background subtraction, diagonal X-marker matching,
teal-channel multi-track Viterbi/band extraction, and vertical error-bar stem extraction.
"""
from __future__ import annotations

from typing import Any
import numpy as np
from scipy.signal import fftconvolve

from livinglit_lepidoptera.extract_lib import AxisCal, viterbi_track


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


def _extract_5g(crop_rgb: np.ndarray) -> dict[str, Any]:
    g = crop_rgb.mean(axis=2)
    h, w = g.shape
    dk = g < 155.0
    v_cols = [c for c in range(w) if dk[:, c].sum() >= 0.50 * h]
    h_rows = [r for r in range(h) if dk[r, :].sum() >= 0.50 * w]
    vc_l, vc_r = min(v_cols), max(v_cols)
    hr_t, hr_b = min(h_rows), max(h_rows)

    # Calibrate y-axis from the 6 crisp right-spine inward ticks [1.0, 1.2, 1.4, 1.6, 1.8, 2.0] um
    y_hits = [r for r in range(hr_t + 3, hr_b - 3) if g[r, vc_r - 1] < 205.0]
    y_ticks = sorted(_group_centres(y_hits, gap=2), reverse=True)
    y_labels = [1.0, 1.2, 1.4, 1.6, 1.8, 2.0]
    if len(y_ticks) != 6:
        raise ValueError(f"F5/G expected 6 right-spine y-ticks, got {len(y_ticks)} at {y_ticks}")
    y_cal = AxisCal.fit(y_ticks, y_labels, scale="linear")
    x_cal = AxisCal.fit([float(vc_l), float(vc_r)], [28.0, 95.0], scale="linear")

    px0, py0, px1, py1 = vc_l + 1, hr_t + 1, vc_r - 1, hr_b - 1
    sub = crop_rgb[py0:py1, px0:px1].astype(np.float32)
    sh, sw = sub.shape[:2]

    # 1. Group 1 (early widening actin bundles, black 'x' markers < 47% development)
    col_bg = np.percentile(sub, 82, axis=0, keepdims=True)
    res = np.clip(col_bg - sub, 0.0, 255.0)
    sat = sub.max(axis=2) - sub.min(axis=2)
    blk_sig = np.where(sat < 35.0, res.mean(axis=2), 0.0)
    excl = np.zeros((sh, sw), dtype=bool)
    excl[:58, :] = True   # "smooth" label + double arrow
    excl[:, 50:] = True   # restrict to early actin region (<47%)

    ker = np.array([
        [ 0.8, -0.4, -0.6, -0.4,  0.8],
        [-0.4,  1.2, -0.2,  1.2, -0.4],
        [-0.6, -0.2,  1.4, -0.2, -0.6],
        [-0.4,  1.2, -0.2,  1.2, -0.4],
        [ 0.8, -0.4, -0.6, -0.4,  0.8],
    ], dtype=np.float64)
    ker /= np.maximum(ker, 0.0).sum()
    resp = fftconvolve(blk_sig, ker, mode="same")
    cnt = fftconvolve((blk_sig >= 45.0).astype(np.float64), np.ones((5, 5)), mode="same")
    valid = (resp >= 42.0) & (cnt >= 7.0) & (blk_sig >= 32.0) & (~excl)
    valid[:2, :] = False; valid[-2:, :] = False; valid[:, :3] = False; valid[:, -3:] = False

    picked = np.zeros((sh, sw), dtype=bool)
    g1_pts: list[tuple[float, float]] = []
    for _ in range(15):
        m = valid & ~picked
        if not np.any(m):
            break
        cy, cx = divmod(int(np.argmax(np.where(m, resp, -1e9))), sw)
        y0s, y1s = max(0, cy - 1), min(sh, cy + 2)
        x0s, x1s = max(0, cx - 1), min(sw, cx + 2)
        patch = np.maximum(0.0, resp[y0s:y1s, x0s:x1s] - resp[cy, cx] * 0.40)
        yy, xx = np.mgrid[y0s:y1s, x0s:x1s]
        ry = float((yy * patch).sum() / max(float(patch.sum()), 1e-6))
        rx = float((xx * patch).sum() / max(float(patch.sum()), 1e-6))
        g1_pts.append((round(x_cal.to_value(px0 + rx), 2), round(y_cal.to_value(py0 + ry), 3)))
        ey0, ey1 = max(0, cy - 5), min(sh, cy + 6)
        ex0, ex1 = max(0, cx - 5), min(sw, cx + 6)
        yy_e, xx_e = np.mgrid[ey0:ey1, ex0:ex1]
        picked[ey0:ey1, ex0:ex1] |= ((yy_e - cy) ** 2 + (xx_e - cx) ** 2 <= 3.5 ** 2)
    g1_pts.sort()

    # 2. Group 2 (4 cyan/teal single-scale curves, ~47–61%) & Group 3 (3 dark-teal single-scale curves, ~61–89%)
    tex = np.clip(np.minimum(sub[:, :, 1], sub[:, :, 2]) - sub[:, :, 0], 0.0, 255.0)
    # Group 2 spans columns corresponding to ~46.5%..60.8% (cols ~48..86)
    g2_c0 = int(round(x_cal.to_pixel(46.8) - px0))
    g2_c1 = int(round(x_cal.to_pixel(60.8) - px0))
    # 4 non-overlapping y-bands (um) for the 4 individual scales in Group 2
    g2_bands = [
        ("group2_scale1_upper", (1.88, 1.98)),
        ("group2_scale2_midhi", (1.79, 1.88)),
        ("group2_scale3_midlo", (1.63, 1.74)),
        ("group2_scale4_lower", (1.53, 1.63)),
    ]
    curves: dict[str, Any] = {}
    for name, (ylo_u, yhi_u) in g2_bands:
        r_top = max(1, int(round(y_cal.to_pixel(yhi_u) - py0)))
        r_bot = min(sh - 2, int(round(y_cal.to_pixel(ylo_u) - py0)))
        band = tex[r_top:r_bot + 1, g2_c0:g2_c1 + 1]
        norm_b = band / max(float(band.max()), 1.0)
        path = viterbi_track(1.0 - norm_b, max_step=3, smooth_w=0.22, norm="l1")
        xs_c = [round(x_cal.to_value(px0 + g2_c0 + k), 2) for k in range(len(path))]
        ys_c = [round(y_cal.to_value(py0 + r_top + ry), 3) for ry in path]
        curves[name] = {
            "x": xs_c, "y": ys_c,
            "peak_x": xs_c[int(np.argmax(ys_c))], "peak_y": max(ys_c),
            "x_unit": "% development", "y_unit": "µm",
        }

    # Group 3 (dark-teal tracks, ~61.5%..88.5%): dark teal has low R (< 95) and positive teal excess
    g3_c0 = int(round(x_cal.to_pixel(61.5) - px0))
    g3_c1 = int(round(x_cal.to_pixel(88.5) - px0))
    dark_teal = np.where((sub[:, :, 0] < 130.0) & (tex > 24.0), tex, 0.0)
    # Track upper, middle, and lower dark-teal ridges across 61.5–88.5%
    r3_top = max(1, int(round(y_cal.to_pixel(1.89) - py0)))
    r3_bot = min(sh - 2, int(round(y_cal.to_pixel(1.74) - py0)))
    b3 = dark_teal[r3_top:r3_bot + 1, g3_c0:g3_c1 + 1]
    # Track mean/envelope of the tightly bundled 3 dark-teal scales via top/bottom edges and Viterbi ridge
    xs_g3, ys_g3_hi, ys_g3_lo, ys_g3_mid = [], [], [], []
    for k in range(b3.shape[1]):
        col = b3[:, k]
        hits = np.where(col >= 24.0)[0]
        if len(hits):
            xv = round(x_cal.to_value(px0 + g3_c0 + k), 2)
            xs_g3.append(xv)
            ys_g3_hi.append(round(y_cal.to_value(py0 + r3_top + float(hits[0])), 3))
            ys_g3_lo.append(round(y_cal.to_value(py0 + r3_top + float(hits[-1])), 3))
            wts = col[hits]
            ys_g3_mid.append(round(y_cal.to_value(py0 + r3_top + float(np.sum(hits * wts) / wts.sum())), 3))
    curves["group3_late_ridges_band"] = {
        "x": xs_g3, "y": ys_g3_mid, "lo": ys_g3_lo, "hi": ys_g3_hi,
        "peak_x": xs_g3[int(np.argmax(ys_g3_mid))] if xs_g3 else None,
        "peak_y": max(ys_g3_mid) if ys_g3_mid else None,
        "x_unit": "% development", "y_unit": "µm",
    }

    scatter = {
        "group1_early_actin": {
            "x": [p[0] for p in g1_pts],
            "y": [p[1] for p in g1_pts],
            "n": len(g1_pts),
            "x_unit": "% development",
            "y_unit": "µm",
        }
    }

    x_min, x_max = round(x_cal.to_value(px0), 4), round(x_cal.to_value(px1), 4)
    y_min, y_max = round(y_cal.to_value(py1), 4), round(y_cal.to_value(py0), 4)

    return {
        "digitized_scatter": scatter,
        "curves": curves,
        "overlay_meta": {
            "plot_box": [int(px0), int(py0), int(px1), int(py1)],
            "x_range": [x_min, x_max],
            "y_range": [y_min, y_max],
            "y_misfit_px": round(float(y_cal.misfit_px), 3),
            "mode": "scatter_2d",
            "kind": "scatter",
        },
        "extracted_data": {
            "y_tick_misfit_px": round(float(y_cal.misfit_px), 3),
            "group1_n_points": len(g1_pts),
            "group1_spacing_range_um": [min(p[1] for p in g1_pts), max(p[1] for p in g1_pts)] if g1_pts else None,
            "group2_mean_um": round(float(np.mean([v for k, c in curves.items() if k.startswith("group2") for v in c["y"]])), 3),
            "group3_mean_um": round(float(np.mean(ys_g3_mid)), 3) if ys_g3_mid else None,
        },
    }


def _extract_errorbars(
    mask: np.ndarray,
    strength: np.ndarray,
    x_cal: AxisCal,
    y_cal: AxisCal,
    px0: int,
    py0: int,
    min_run: int = 5,
    min_sep_px: int = 5,
) -> list[dict[str, float]]:
    """Extract vertical mean ± SD error bars by locating local-maximum vertical stem runs."""
    H, W = mask.shape

    def longest_run(col: np.ndarray) -> tuple[int, int, int]:
        m = np.concatenate([[0], col.astype(int), [0]])
        d = np.diff(m)
        starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1
        if not len(starts):
            return 0, 0, 0
        lens = ends - starts + 1
        i = int(np.argmax(lens))
        return int(lens[i]), int(starts[i]), int(ends[i])

    vruns = np.zeros(W, dtype=int)
    tops = np.zeros(W, dtype=int)
    bots = np.zeros(W, dtype=int)
    scores = np.zeros(W, dtype=np.float64)
    for c in range(W):
        ln, st, en = longest_run(mask[:, c])
        vruns[c], tops[c], bots[c] = ln, st, en
        if ln >= min_run:
            # Prefer tall continuous vertical stems with strong ink contrast (rejects 1-2 px cap overhangs)
            scores[c] = ln * float(strength[st:en + 1, c].mean())

    # Greedy NMS across columns by score (min_sep_px prevents picking cap edges next to a stem)
    picked_cols: list[int] = []
    avail = scores > 0
    while np.any(avail):
        cx = int(np.argmax(np.where(avail, scores, -1.0)))
        picked_cols.append(cx)
        c_lo, c_hi = max(0, cx - min_sep_px), min(W, cx + min_sep_px + 1)
        avail[c_lo:c_hi] = False
    picked_cols.sort()

    bars: list[dict[str, float]] = []
    for cx in picked_cols:
        r_top, r_bot = float(tops[cx]), float(bots[cx])
        r_mid = 0.5 * (r_top + r_bot)
        bars.append({
            "x": round(x_cal.to_value(px0 + cx), 2),
            "y": round(y_cal.to_value(py0 + r_mid), 3),
            "y_lo": round(y_cal.to_value(py0 + r_bot), 3),
            "y_hi": round(y_cal.to_value(py0 + r_top), 3),
        })
    return bars


def _extract_5h(crop_rgb: np.ndarray, panel_id: str) -> dict[str, Any]:
    # Shared x-axis across F5/H_height and F5/H_spacing: [34, 36, 38, 40, 42] % at crop cols [53, 97, 140.5, 184, 228]
    x_cal = AxisCal.fit([53.0, 97.0, 140.5, 184.0, 228.0], [34.0, 36.0, 38.0, 40.0, 42.0], scale="linear")

    if panel_id == "H_height":
        # Crop bbox [530, 186, 764, 301]: purple inward ticks [0, 50, 100, 150] nm at crop rows [114, 80, 46, 12]
        y_cal = AxisCal.fit([114.0, 80.0, 46.0, 12.0], [0.0, 50.0, 100.0, 150.0], scale="linear")
        px0, py0, px1, py1 = (54, 11, 227, 114)
        sub = crop_rgb[py0:py1, px0:px1].astype(np.float32)
        # Mask top regime text + arrows ("smooth | irregular | ridges")
        sub[:22, :] = 220.0
        purp_ex = np.clip((sub[:, :, 2] - sub[:, :, 1]) + 0.5 * (sub[:, :, 0] - sub[:, :, 1]), 0.0, 255.0)
        mask = (sub[:, :, 2] - sub[:, :, 1] > 18.0) & (sub[:, :, 0] - sub[:, :, 1] > 6.0)
        bars = _extract_errorbars(mask, purp_ex, x_cal, y_cal, px0, py0, min_run=5, min_sep_px=5)
        sname, y_unit = "ridge_height_mean_sd", "nm"
    else:
        # H_spacing: crop bbox [530, 300, 764, 361]: divider y=0 (300), tick 2um y=14 (314), 0um spine y=32 (332)
        y_cal = AxisCal.fit([32.0, 14.0], [0.0, 2.0], scale="linear")
        px0, py0, px1, py1 = (54, 2, 227, 31)
        sub = crop_rgb[py0:py1, px0:px1].astype(np.float32)
        teal_ex = np.clip(np.minimum(sub[:, :, 1], sub[:, :, 2]) - sub[:, :, 0], 0.0, 255.0)
        mask = teal_ex > 22.0
        bars = _extract_errorbars(mask, teal_ex, x_cal, y_cal, px0, py0, min_run=2, min_sep_px=5)
        sname, y_unit = "ridge_spacing_mean_sd", "µm"

    x_min, x_max = round(x_cal.to_value(px0), 4), round(x_cal.to_value(px1), 4)
    y_min, y_max = round(y_cal.to_value(py1), 4), round(y_cal.to_value(py0), 4)

    scatter = {
        sname: {
            "x": [b["x"] for b in bars],
            "y": [b["y"] for b in bars],
            "y_lo": [b["y_lo"] for b in bars],
            "y_hi": [b["y_hi"] for b in bars],
            "n": len(bars),
            "x_unit": "% development",
            "y_unit": y_unit,
        }
    }

    return {
        "digitized_scatter": scatter,
        "overlay_meta": {
            "plot_box": [int(px0), int(py0), int(px1), int(py1)],
            "x_range": [x_min, x_max],
            "y_range": [y_min, y_max],
            "x_misfit_px": round(float(x_cal.misfit_px), 3),
            "y_misfit_px": round(float(y_cal.misfit_px), 3),
            "mode": "crosshair_errorbars",
            "kind": "scatter",
        },
        "extracted_data": {
            "x_tick_misfit_px": round(float(x_cal.misfit_px), 3),
            "y_tick_misfit_px": round(float(y_cal.misfit_px), 3),
            "n_timepoints": len(bars),
            "final_41pct_mean": bars[-1]["y"] if bars else None,
            "final_41pct_sd": round(0.5 * (bars[-1]["y_hi"] - bars[-1]["y_lo"]), 3) if bars else None,
        },
    }


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    if panel_id == "G":
        return _extract_5g(crop_rgb)
    return _extract_5h(crop_rgb, panel_id)
