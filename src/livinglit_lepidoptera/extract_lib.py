"""Shared, figure-agnostic CV, DP, and microscopy metrology primitives for livinglit-lepidoptera.

Zero paper- or figure-specific pixel coordinates live here. Individual figure extractors under
`records/<paper>/extractors/<fig>.py` import these unit-tested building blocks and supply only
figure-local calibration and trace definitions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter1d, map_coordinates
from scipy.signal import fftconvolve, find_peaks

from livinglit_lepidoptera.figures.microscopy import (
    ScaleBarCal,
    detect_scale_bar,
    measure_periodic_fft,
    to_gray,
)


# ---------------------------------------------------------------------------
# 1. Axis & coordinate calibration helpers (with RMS tick-misfit reporting)
# ---------------------------------------------------------------------------

def lin_range(p0: float, p1: float, t_lo: float, v_lo: float, t_hi: float, v_hi: float) -> tuple[float, float]:
    """Extrapolate linear axis bounds [p0, p1] from two tick positions (t_lo -> v_lo, t_hi -> v_hi)."""
    s = (v_hi - v_lo) / (t_hi - t_lo)
    return (round(v_lo + (p0 - t_lo) * s, 4), round(v_lo + (p1 - t_lo) * s, 4))


def log_range(p0: float, p1: float, t_lo: float, v_lo: float, t_hi: float, v_hi: float) -> tuple[float, float]:
    """Extrapolate log10 axis bounds [p0, p1] from two tick positions (t_lo -> v_lo, t_hi -> v_hi)."""
    lv0, lv1 = math.log10(v_lo), math.log10(v_hi)
    s = (lv1 - lv0) / (t_hi - t_lo)
    return (round(10.0 ** (lv0 + (p0 - t_lo) * s), 6), round(10.0 ** (lv0 + (p1 - t_lo) * s), 6))


@dataclass
class AxisCal:
    """Linear or log10 axis fitted from detected tick-mark pixel positions and printed labels."""

    scale: str  # "linear" | "log10"
    tick_px: list[float]
    labels: list[float]
    slope: float         # px = slope * t(val) + intercept
    intercept: float
    misfit_px: float     # RMS residual in pixels across all detected ticks
    max_residual_px: float

    @classmethod
    def fit(cls, tick_px: list[float], labels: list[float], scale: str = "linear") -> "AxisCal":
        if len(tick_px) != len(labels) or len(tick_px) < 2:
            raise ValueError(f"AxisCal requires >=2 matched (tick_px, label) pairs; got {len(tick_px)} vs {len(labels)}")
        p = np.asarray(tick_px, dtype=np.float64)
        v = np.asarray(labels, dtype=np.float64)
        if scale == "log10":
            if np.any(v <= 0):
                raise ValueError("log10 axis requires strictly positive labels")
            t = np.log10(v)
        elif scale == "linear":
            t = v
        else:
            raise ValueError(f"Unknown axis scale: {scale!r}")
        slope, intercept = np.polyfit(t, p, 1)
        resid = p - (slope * t + intercept)
        rms = float(np.sqrt(np.mean(resid ** 2))) if len(p) > 2 else 0.5
        mx = float(np.max(np.abs(resid))) if len(p) > 2 else 0.5
        return cls(
            scale=scale,
            tick_px=[round(float(x), 2) for x in p],
            labels=[float(x) for x in v],
            slope=float(slope),
            intercept=float(intercept),
            misfit_px=round(rms, 3),
            max_residual_px=round(mx, 3),
        )

    def to_pixel(self, val: float) -> float:
        t = math.log10(val) if self.scale == "log10" else float(val)
        return float(self.slope * t + self.intercept)

    def to_value(self, px: float) -> float:
        t = (float(px) - self.intercept) / self.slope
        return float(10.0 ** t if self.scale == "log10" else t)

    def range_for_span(self, p0: float, p1: float, ndigits: int = 4) -> tuple[float, float]:
        """Return (val_at_p0, val_at_p1) sorted as (min_val, max_val) when slope < 0 (y-axis)."""
        v0, v1 = self.to_value(p0), self.to_value(p1)
        return (round(v0, ndigits), round(v1, ndigits))


def _bool_runs(v: np.ndarray) -> list[tuple[int, int]]:
    m = np.concatenate([[False], np.asarray(v, dtype=bool), [False]]).astype(np.int8)
    d = np.diff(m)
    return list(zip(np.flatnonzero(d == 1).tolist(), (np.flatnonzero(d == -1) - 1).tolist()))


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


def find_axis_ticks(
    img_rgb: np.ndarray,
    y_labels: list[float],
    x_labels: list[float] | None = None,
    y_scale: str = "linear",
    x_scale: str = "linear",
    dark_thr: float = 135.0,
    max_sat: float = 55.0,
    min_spine_frac: float = 0.35,
    probe: tuple[int, int] = (2, 8),
    y_probe: tuple[int, int] | None = None,
    x_probe: tuple[int, int] | None = None,
    tick_min_frac: float = 0.55,
) -> dict[str, Any]:
    """Detect left y-axis & bottom x-axis spines and perpendicular tick stubs from pixel ink.

    Inspired by boxgraph-public/andreu2021/_kit.py: raises ValueError immediately if the number of
    detected tick stubs does not match the printed labels, and reports RMS pixel misfit.
    """
    f = img_rgb.astype(np.float32)
    h, w = f.shape[:2]
    sat = f.max(axis=2) - f.min(axis=2)
    dk = (f.mean(axis=2) < dark_thr) & (sat < max_sat)

    # Left vertical spine: leftmost column with a long dark run (>= min_spine_frac * h)
    best_v: list[tuple[int, int, int]] = []
    for c in range(w):
        rs = _bool_runs(dk[:, c])
        if rs:
            a, b = max(rs, key=lambda r: r[1] - r[0])
            if b - a + 1 >= min_spine_frac * h:
                best_v.append((c, a, b))
    if not best_v:
        raise ValueError("No vertical y-axis spine detected")
    c_left = best_v[0][0]
    v_cols = [x for x in best_v if x[0] - c_left <= 6]
    vc0, vc1 = min(x[0] for x in v_cols), max(x[0] for x in v_cols)
    vr0 = int(np.median([x[1] for x in v_cols]))
    vr1 = int(np.median([x[2] for x in v_cols]))

    # Bottom horizontal spine: lowest row with a long dark run (>= min_spine_frac * w)
    best_h: list[tuple[int, int, int]] = []
    for r in range(h):
        rs = _bool_runs(dk[r, :])
        if rs:
            a, b = max(rs, key=lambda c: c[1] - c[0])
            if b - a + 1 >= min_spine_frac * w:
                best_h.append((r, a, b))
    if not best_h:
        raise ValueError("No horizontal x-axis spine detected")
    r_bot = best_h[-1][0]
    h_rows = [x for x in best_h if r_bot - x[0] <= 6]
    hr0, hr1 = min(x[0] for x in h_rows), max(x[0] for x in h_rows)
    hc0 = int(np.median([x[1] for x in h_rows]))
    hc1 = int(np.median([x[2] for x in h_rows]))

    # Top/right frame borders if closed box exists
    top_rows = [x for x in best_h if x[0] < hr0 - 15]
    right_cols = [x for x in best_v if x[0] > vc1 + 15]
    p_top = (max(x[0] for x in top_rows if x[0] - top_rows[0][0] <= 6) + 1) if top_rows else vr0
    p_right = (min(x[0] for x in right_cols if right_cols[-1][0] - x[0] <= 6) - 1) if right_cols else hc1
    plot_box = (vc1 + 1, p_top, p_right, hr0 - 1)

    yp0, yp1 = y_probe or probe
    y_band = dk[:, max(0, vc0 - yp1):max(1, vc0 - yp0)]
    y_hits = [r for r in np.flatnonzero(y_band.mean(axis=1) >= tick_min_frac).tolist() if vr0 - 4 <= r <= vr1 + 4]
    y_ticks = sorted(_group_centres(y_hits, gap=2), reverse=True)  # bottom -> top matches ascending y_labels
    if len(y_ticks) != len(y_labels):
        raise ValueError(f"y-axis tick count mismatch: found {len(y_ticks)} at {y_ticks}, expected {len(y_labels)}")
    y_cal = AxisCal.fit(y_ticks, y_labels, scale=y_scale)

    x_cal = None
    x_ticks: list[float] = []
    if x_labels is not None:
        xp0, xp1 = x_probe or probe
        x_band = dk[min(h - 1, hr1 + xp0 + 1):min(h, hr1 + xp1 + 1), :]
        x_hits = [c for c in np.flatnonzero(x_band.mean(axis=0) >= tick_min_frac).tolist() if hc0 - 4 <= c <= hc1 + 4]
        x_ticks = sorted(_group_centres(x_hits, gap=2))
        if len(x_ticks) != len(x_labels):
            raise ValueError(f"x-axis tick count mismatch: found {len(x_ticks)} at {x_ticks}, expected {len(x_labels)}")
        x_cal = AxisCal.fit(x_ticks, x_labels, scale=x_scale)

    return {
        "plot_box": plot_box,
        "x_cal": x_cal,
        "y_cal": y_cal,
        "x_ticks": x_ticks,
        "y_ticks": y_ticks,
        "x_misfit_px": x_cal.misfit_px if x_cal else None,
        "y_misfit_px": y_cal.misfit_px,
    }



# ---------------------------------------------------------------------------
# 2. Color-ray decomposition & L1 Viterbi DP curve tracking
# ---------------------------------------------------------------------------

def ray_dist_alpha(
    sub_f: np.ndarray,
    rgb: tuple[int, int, int],
    bg_rgb: tuple[float, float, float] = (255.0, 255.0, 255.0),
) -> tuple[np.ndarray, np.ndarray]:
    """Perpendicular RGB distance and ink opacity alpha along the bg_rgb -> target rgb ray.

    Core curves sit at high alpha (~0.85..1.1) while translucent ±SD / 95% CI ribbons sit along
    the exact same ray at lower alpha (~0.08..0.40).
    """
    W = np.array(bg_rgb, dtype=np.float32)
    T = np.array(rgb, dtype=np.float32)
    v = T - W
    vn2 = max(float(np.dot(v, v)), 1.0)
    dv = sub_f - W[None, None, :]
    alpha = np.sum(dv * v[None, None, :], axis=2) / vn2
    a_clip = np.clip(alpha, 0.0, 1.35)
    proj = W[None, None, :] + a_clip[:, :, None] * v[None, None, :]
    perp = np.linalg.norm(sub_f - proj, axis=2)
    return perp, a_clip


def viterbi_track(
    cost_grid: np.ndarray,
    max_step: int = 45,
    smooth_w: float = 0.25,
    norm: str = "l1",
) -> np.ndarray:
    """Minimum-cost continuous curve y[t] across columns t=0..T-1 via Viterbi dynamic programming.

    Uses L1 slope penalty (`smooth_w * |dy|`) by default so steep reflectance/FDTD peaks climb
    cleanly without quadratic flattening while still rejecting vertical jumps across crossings.
    """
    H, T = cost_grid.shape
    dp = np.full((H, T), 1e9, dtype=np.float64)
    back = np.zeros((H, T), dtype=np.int32)
    dp[:, 0] = cost_grid[:, 0]
    offs = np.arange(-max_step, max_step + 1)
    if norm == "l2":
        pen = smooth_w * (offs.astype(np.float64) ** 2)
    else:
        pen = smooth_w * np.abs(offs.astype(np.float64))

    rows_all = np.arange(H, dtype=np.int32)
    for t in range(1, T):
        prev = dp[:, t - 1]
        best_val = np.full(H, 1e9, dtype=np.float64)
        best_idx = rows_all.copy()
        for d, p_cost in zip(offs, pen):
            if d == 0:
                cand = prev + p_cost
                better = cand < best_val
                best_val = np.where(better, cand, best_val)
                best_idx = np.where(better, rows_all, best_idx)
            elif d > 0:
                cand = prev[:-d] + p_cost
                better = cand < best_val[d:]
                best_val[d:] = np.where(better, cand, best_val[d:])
                best_idx[d:] = np.where(better, rows_all[:H - d], best_idx[d:])
            else:
                k = -d
                cand = prev[k:] + p_cost
                better = cand < best_val[:-k]
                best_val[:-k] = np.where(better, cand, best_val[:-k])
                best_idx[:-k] = np.where(better, rows_all[k:], best_idx[:-k])
        dp[:, t] = cost_grid[:, t] + best_val
        back[:, t] = best_idx

    path = np.zeros(T, dtype=np.int32)
    path[-1] = int(np.argmin(dp[:, -1]))
    for t in range(T - 2, -1, -1):
        path[t] = back[path[t + 1], t + 1]
    return path


def walk_ribbon_bounds(
    ribbon_mask: np.ndarray,
    x_cols: np.ndarray,
    y_path: np.ndarray,
    max_half: int = 95,
    max_gap: int = 5,
    top_pad: int = 0,
    bot_pad: int = 0,
    col_half_w: int = 2,
) -> tuple[np.ndarray, np.ndarray]:
    """Walk continuously up/down from y_path across ribbon_mask to measure ±SD / 95% CI envelopes.

    Returns (y_lo_px, y_hi_px) in image row coordinates (y_hi_px <= y_path <= y_lo_px).
    Walking continuously prevents jumping across white space onto axis ticks or legend boxes.
    """
    H, W = ribbon_mask.shape
    y_hi_px = y_path.astype(np.float64).copy()
    y_lo_px = y_path.astype(np.float64).copy()
    r_min_lim = max(0, top_pad)
    r_max_lim = min(H - 1, H - 1 - bot_pad)
    for i, (cx, cy) in enumerate(zip(x_cols, y_path)):
        c0, c1 = max(0, int(cx) - col_half_w), min(W, int(cx) + col_half_w + 1)
        col = ribbon_mask[:, c0:c1].any(axis=1)
        cy_i = int(np.clip(round(float(cy)), r_min_lim, r_max_lim))
        up = cy_i
        gap = 0
        for r in range(cy_i, max(r_min_lim, cy_i - max_half) - 1, -1):
            if col[r]:
                up = r
                gap = 0
            else:
                gap += 1
                if gap > max_gap:
                    break
        dn = cy_i
        gap = 0
        for r in range(cy_i, min(r_max_lim, cy_i + max_half) + 1):
            if col[r]:
                dn = r
                gap = 0
            else:
                gap += 1
                if gap > max_gap:
                    break
        y_hi_px[i] = float(up)
        y_lo_px[i] = float(dn)
    return y_lo_px, y_hi_px


# ---------------------------------------------------------------------------
# 3. Robust regression + CI ribbon fitter, error bars, vertical bars, boxplots
# ---------------------------------------------------------------------------

def fit_irls_line_and_ci(
    ribbon_mask: np.ndarray,
    c_lo: int,
    c_hi: int,
    n_pts: int = 36,
    max_hw: float = 24.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Fit a straight regression line (IRLS) + smooth quadratic 95% CI envelope to ribbon pixels.

    Returns (x_cols, y_mid_px, y_lo_px, y_hi_px) in image pixel coordinates.
    """
    H, W = ribbon_mask.shape
    ry, rx = np.where(ribbon_mask)
    if len(rx) < 20:
        raise ValueError("insufficient ribbon pixels for IRLS regression fit")
    rxf, ryf = rx.astype(np.float64), ry.astype(np.float64)
    m, b = np.polyfit(rxf, ryf, 1)
    for _ in range(3):
        resid = np.abs(ryf - (m * rxf + b))
        thr = max(4.5, float(np.percentile(resid, 72)))
        inliers = resid <= thr
        if inliers.sum() < 15:
            break
        m, b = np.polyfit(rxf[inliers], ryf[inliers], 1)

    cols = np.linspace(max(1, c_lo), min(W - 2, c_hi), n_pts).astype(int)
    hw_x, hw_y = [], []
    for cx in cols:
        yc = m * cx + b
        ys_c = np.where(ribbon_mask[:, max(0, cx - 1):min(W, cx + 2)].any(axis=1))[0]
        near = ys_c[np.abs(ys_c - yc) <= max_hw + 4.0]
        if len(near) >= 3:
            hw = 0.5 * (float(near.max()) - float(near.min()))
            if 1.2 <= hw <= max_hw:
                hw_x.append(float(cx))
                hw_y.append(hw)
    if len(hw_x) >= 6:
        q2, q1, q0 = np.polyfit(np.array(hw_x), np.array(hw_y), 2)
    else:
        q2, q1, q0 = 0.0, 0.0, 5.0

    ym = m * cols + b
    hw_fit = np.clip(q2 * cols * cols + q1 * cols + q0, 1.5, max_hw)
    return cols, ym, ym + hw_fit, ym - hw_fit


def trace_error_arms(
    arm_mask: np.ndarray,
    cx: float,
    cy: float,
    max_len: int = 80,
    max_gap: int = 3,
    band_half: int = 2,
) -> tuple[float, float, float, float]:
    """Walk left/right/up/down from marker center (cx, cy) along error-bar strokes.

    Returns (x_left_px, x_right_px, y_bot_px, y_top_px) in image pixel coordinates.
    """
    H, W = arm_mask.shape
    ix, iy = int(round(cx)), int(round(cy))
    x0_b, x1_b = max(0, ix - band_half), min(W, ix + band_half + 1)
    y0_b, y1_b = max(0, iy - band_half), min(H, iy + band_half + 1)

    row_line = arm_mask[y0_b:y1_b, :].any(axis=0)
    col_line = arm_mask[:, x0_b:x1_b].any(axis=1)

    xl, xr = ix, ix
    gap = 0
    for c in range(ix, max(0, ix - max_len) - 1, -1):
        if row_line[c]:
            xl, gap = c, 0
        else:
            gap += 1
            if gap > max_gap:
                break
    gap = 0
    for c in range(ix, min(W - 1, ix + max_len) + 1):
        if row_line[c]:
            xr, gap = c, 0
        else:
            gap += 1
            if gap > max_gap:
                break

    yt, yb = iy, iy
    gap = 0
    for r in range(iy, max(0, iy - max_len) - 1, -1):
        if col_line[r]:
            yt, gap = r, 0
        else:
            gap += 1
            if gap > max_gap:
                break
    gap = 0
    for r in range(iy, min(H - 1, iy + max_len) + 1):
        if col_line[r]:
            yb, gap = r, 0
        else:
            gap += 1
            if gap > max_gap:
                break
    return float(xl), float(xr), float(yb), float(yt)


def trace_error_arms_occluded(
    arm_mask: np.ndarray,
    occ_mask: np.ndarray,
    cx: float,
    cy: float,
    max_len: int = 120,
    max_gap: int = 3,
    band_half: int = 2,
    marker_r: float = 4.0,
) -> tuple[float, float, float, float, dict[str, bool]]:
    """Occlusion-crossing error-bar walker (inspired by boxgraph-public/andreu2021/_kit.py:_walk).

    Walks left/right/up/down from (cx, cy) through `arm_mask`, bridging pixels occupied by
    `occ_mask` (other series' markers, lines, or ribbons) instead of stopping prematurely.
    If an arm terminates inside an occluder without re-emerging, mirrors the opposite visible arm
    and flags that arm as hidden.
    """
    H, W = arm_mask.shape
    ix, iy = int(round(cx)), int(round(cy))
    x0_b, x1_b = max(0, ix - band_half), min(W, ix + band_half + 1)
    y0_b, y1_b = max(0, iy - band_half), min(H, iy + band_half + 1)

    row_t = arm_mask[y0_b:y1_b, :].any(axis=0)
    row_o = occ_mask[y0_b:y1_b, :].any(axis=0)
    col_t = arm_mask[:, x0_b:x1_b].any(axis=1)
    col_o = occ_mask[:, x0_b:x1_b].any(axis=1)

    def _walk_1d(t_arr: np.ndarray, o_arr: np.ndarray, start: int, step: int, lim: int) -> tuple[int, bool]:
        last_t = start
        last_o: int | None = None
        gap = 0
        pos = start + step
        steps = 0
        while 0 <= pos < lim and steps < max_len:
            if t_arr[pos]:
                last_t, last_o, gap = pos, None, 0
            elif o_arr[pos]:
                last_o, gap = pos, 0
            else:
                gap += 1
                if gap > max_gap:
                    break
            pos += step
            steps += 1
        hidden = (
            last_o is not None
            and abs(last_o - start) > marker_r + 1.5
            and abs(last_o - last_t) > max(4.0, marker_r)
        )
        return last_t, hidden

    xl, hl = _walk_1d(row_t, row_o, ix, -1, W)
    xr, hr = _walk_1d(row_t, row_o, ix, +1, W)
    yt, ht = _walk_1d(col_t, col_o, iy, -1, H)
    yb, hb = _walk_1d(col_t, col_o, iy, +1, H)

    # Mirror single-sided hidden ends against the visible opposite arm
    if hl and not hr and abs(xr - ix) > marker_r + 2:
        xl = int(round(max(0, 2 * ix - xr)))
    elif hr and not hl and abs(ix - xl) > marker_r + 2:
        xr = int(round(min(W - 1, 2 * ix - xl)))
    if ht and not hb and abs(yb - iy) > marker_r + 2:
        yt = int(round(max(0, 2 * iy - yb)))
    elif hb and not ht and abs(iy - yt) > marker_r + 2:
        yb = int(round(min(H - 1, 2 * iy - yt)))

    return float(xl), float(xr), float(yb), float(yt), {
        "x_lo_hidden": hl,
        "x_hi_hidden": hr,
        "y_hi_hidden": ht,
        "y_lo_hidden": hb,
    }


def shaded_bg_residual(
    sub_rgb: np.ndarray,
    marker_diam_px: int = 7,
    mode: str = "close",
) -> tuple[np.ndarray, np.ndarray]:
    """Estimate smooth local background (white paper, 95% CI ribbon, notched box, or violin fill)
    so compact darker/colored markers sitting ON shaded overlays pop out cleanly.

    Returns (bg_rgb_f32, residual_f32) where `residual = bg_rgb - sub_rgb` (positive wherever a
    pixel is darker than its smooth local ribbon/box/violin background).
    """
    k = max(5, int(round(marker_diam_px * 2.5)))
    if k % 2 == 0:
        k += 1
    u8 = np.clip(sub_rgb, 0, 255).astype(np.uint8)
    if mode == "median":
        bg = cv2.medianBlur(u8, k)
    else:
        se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        bg = cv2.morphologyEx(u8, cv2.MORPH_CLOSE, se)
    bg_f = bg.astype(np.float32)
    res_f = bg_f - sub_rgb.astype(np.float32)
    return bg_f, res_f


def _marker_kernel(r: float, shape: str = "disk") -> np.ndarray:
    k = max(1, int(math.ceil(r)))
    yy, xx = np.mgrid[-k:k + 1, -k:k + 1]
    if shape == "triangle_up":
        # Equilateral-ish upward triangle inscribed in radius r (e.g., ggplot2 shape=17)
        h = 1.65 * r
        y_top = -0.85 * r
        y_bot = 0.80 * r
        frac = (yy - y_top) / max(h, 1e-6)
        half_w = frac * (1.05 * r)
        return ((yy >= y_top) & (yy <= y_bot) & (np.abs(xx) <= half_w)).astype(np.float64)
    return (xx * xx + yy * yy <= r * r + 1e-6).astype(np.float64)


def detect_markers_matched_filter(
    tgt: np.ndarray,
    occ: np.ndarray,
    radius: float | None = None,
    shape: str = "disk",
    min_visible: float = 0.22,
    max_bg: float = 0.16,
    min_score: float = 0.20,
    min_sep_factor: float = 1.35,
    peel: bool = True,
    peel_radius_factor: float = 0.88,
    upsample: int = 1,
    max_markers: int = 400,
    border_px: int = 2,
) -> list[dict[str, Any]]:
    """Occlusion-aware matched-filter marker detector with iterative greedy marker peeling.

    Combines boxgraph-public/andreu2021/_kit.py's occlusion score:
        S = T + 0.5 * O - 3.0 * B
    (where T = target pixels, O = occluder pixels such as other series / regression lines / red
    SD bars / shaded ribbon borders, B = background pixels inside the marker template) with
    greedy marker peeling: each picked marker's core is moved from `tgt` -> `occ` (NOT background!),
    so overlapping markers in dense clusters keep B ~= 0 and still score cleanly without merging!

    Returns list of dicts with subpixel native coordinates:
        {"x": float, "y": float, "t_frac": float, "o_frac": float, "b_frac": float,
         "score": float, "occluded": bool, "radius_px": float}
    """
    H0, W0 = tgt.shape
    up = max(1, int(upsample))
    if up > 1:
        t_u = cv2.resize(tgt.astype(np.uint8), (W0 * up, H0 * up), interpolation=cv2.INTER_NEAREST) > 0
        o_u = cv2.resize(occ.astype(np.uint8), (W0 * up, H0 * up), interpolation=cv2.INTER_NEAREST) > 0
        o_u &= ~t_u
    else:
        t_u = tgt.astype(bool).copy()
        o_u = (occ.astype(bool) & ~t_u).copy()

    if radius is None:
        edt = distance_transform_edt(t_u)
        mx = float(edt.max())
        r = max(1.5 * up, mx) if mx > 0 else 2.5 * up
    else:
        r = float(radius) * up

    ker = _marker_kernel(r, shape=shape)
    kh, kw = ker.shape
    ry_k, rx_k = kh // 2, kw // 2
    n = float(ker.sum())
    if n < 1.0:
        return []

    T = np.rint(fftconvolve(t_u.astype(np.float64), ker, mode="same"))
    O = np.rint(fftconvolve(o_u.astype(np.float64), ker, mode="same"))

    H, W = t_u.shape
    bm = max(0, int(border_px * up))
    min_sep = max(2.0, min_sep_factor * r)
    min_sep2 = min_sep * min_sep
    r_peel = max(1.0, peel_radius_factor * r)
    peel_k = _marker_kernel(r_peel, shape=shape) > 0.5
    ph_k, pw_k = peel_k.shape
    pr_y, pr_x = ph_k // 2, pw_k // 2

    # Mirror kernel for exact correlation vs convolution symmetry when doing local updates
    ker_flip = ker[::-1, ::-1]
    picked_mask = np.zeros((H, W), dtype=bool)
    results: list[dict[str, Any]] = []

    for _ in range(max_markers):
        B = np.maximum(0.0, n - T - O)
        S = T + 0.5 * O - 3.0 * B
        valid = (T >= min_visible * n) & (B <= max_bg * n) & (S >= min_score * n) & (~picked_mask)
        if bm > 0:
            valid[:bm, :] = False
            valid[H - bm:, :] = False
            valid[:, :bm] = False
            valid[:, W - bm:] = False
        if not np.any(valid):
            break

        masked_S = np.where(valid, S, -1e12)
        flat_idx = int(np.argmax(masked_S))
        cy, cx = divmod(flat_idx, W)
        t_val, o_val, b_val, s_val = float(T[cy, cx]), float(O[cy, cx]), float(B[cy, cx]), float(S[cy, cx])

        # Local quadratic/centroid refinement inside 3x3 valid neighborhood around peak for subpixel x, y
        y0_s, y1_s = max(0, cy - 1), min(H, cy + 2)
        x0_s, x1_s = max(0, cx - 1), min(W, cx + 2)
        patch_s = S[y0_s:y1_s, x0_s:x1_s]
        wts = np.maximum(0.0, patch_s - (s_val - 0.15 * n))
        if float(wts.sum()) > 1e-6:
            yy_s, xx_s = np.mgrid[y0_s:y1_s, x0_s:x1_s]
            ry_sub = float((yy_s * wts).sum() / wts.sum())
            rx_sub = float((xx_s * wts).sum() / wts.sum())
        else:
            ry_sub, rx_sub = float(cy), float(cx)

        results.append({
            "x": round((rx_sub + 0.5) / up - 0.5, 3) if up > 1 else round(rx_sub, 3),
            "y": round((ry_sub + 0.5) / up - 0.5, 3) if up > 1 else round(ry_sub, 3),
            "t_frac": round(t_val / n, 3),
            "o_frac": round(o_val / n, 3),
            "b_frac": round(b_val / n, 3),
            "score": round(s_val / n, 3),
            "occluded": bool((t_val / n) < 0.85),
            "radius_px": round(r / up, 2),
        })

        # Suppress immediate center exclusion disk so same marker cannot re-fire
        ey0, ey1 = max(0, int(cy - math.ceil(min_sep))), min(H, int(cy + math.ceil(min_sep)) + 1)
        ex0, ex1 = max(0, int(cx - math.ceil(min_sep))), min(W, int(cx + math.ceil(min_sep)) + 1)
        yy_e, xx_e = np.mgrid[ey0:ey1, ex0:ex1]
        picked_mask[ey0:ey1, ex0:ex1] |= ((yy_e - cy) ** 2 + (xx_e - cx) ** 2 <= min_sep2)

        if peel:
            # Move this marker's claimed target pixels into occluder & update T, O locally!
            py0_i, py1_i = max(0, cy - pr_y), min(H, cy + pr_y + 1)
            px0_i, px1_i = max(0, cx - pr_x), min(W, cx + pr_x + 1)
            ky0_i, kx0_i = py0_i - (cy - pr_y), px0_i - (cx - pr_x)
            ky1_i, kx1_i = ky0_i + (py1_i - py0_i), kx0_i + (px1_i - px0_i)
            foot = peel_k[ky0_i:ky1_i, kx0_i:kx1_i]
            changed = t_u[py0_i:py1_i, px0_i:px1_i] & foot
            if np.any(changed):
                t_u[py0_i:py1_i, px0_i:px1_i] &= ~changed
                o_u[py0_i:py1_i, px0_i:px1_i] |= changed
                # Local delta convolution: moving `changed` from tgt -> occ decreases T and increases O by delta!
                pad_y, pad_x = ry_k, rx_k
                uy0, uy1 = max(0, py0_i - pad_y), min(H, py1_i + pad_y)
                ux0, ux1 = max(0, px0_i - pad_x), min(W, px1_i + pad_x)
                d_patch = np.zeros((uy1 - uy0, ux1 - ux0), dtype=np.float64)
                d_patch[(py0_i - uy0):(py1_i - uy0), (px0_i - ux0):(px1_i - ux0)] = changed.astype(np.float64)
                delta = np.rint(fftconvolve(d_patch, ker_flip, mode="same"))
                T[uy0:uy1, ux0:ux1] = np.maximum(0.0, T[uy0:uy1, ux0:ux1] - delta)
                O[uy0:uy1, ux0:ux1] = np.minimum(n, O[uy0:uy1, ux0:ux1] + delta)

    return results



def _max_vrun(col_bool: np.ndarray) -> int:
    best = cur = 0
    for v in col_bool:
        if v:
            cur += 1
            if cur > best:
                best = cur
        else:
            cur = 0
    return best


def extract_vertical_bars(
    mask: np.ndarray,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    min_run: int = 5,
    max_dx: int = 2,
) -> tuple[list[float], list[float], list[float], list[float]]:
    """Detect discrete vertical error/range bars via contiguous vertical stem runs."""
    H, W = mask.shape
    x_min, x_max = x_range
    y_min, y_max = y_range
    vruns = np.array([_max_vrun(mask[:, c]) for c in range(W)], dtype=np.int32)
    stem_cols = np.where(vruns >= min_run)[0]
    if not len(stem_cols):
        return [], [], [], []
    clusters: list[list[int]] = [[int(stem_cols[0])]]
    for c in stem_cols[1:]:
        if int(c) - clusters[-1][-1] <= max_dx:
            clusters[-1].append(int(c))
        else:
            clusters.append([int(c)])

    xs, ymids, ylos, yhis = [], [], [], []
    for cl in clusters:
        stem_x = cl[int(np.argmax([vruns[c] for c in cl]))]
        ys = np.where(mask[:, max(0, stem_x - 1):min(W, stem_x + 2)].any(axis=1))[0]
        if len(ys) < 2:
            continue
        r_top, r_bot = float(ys.min()), float(ys.max())
        r_mid = 0.5 * (r_top + r_bot)
        xs.append(round(x_min + (stem_x / max(W, 1)) * (x_max - x_min), 3))
        yhis.append(round(y_max - (r_top / max(H, 1)) * (y_max - y_min), 3))
        ylos.append(round(y_max - (r_bot / max(H, 1)) * (y_max - y_min), 3))
        ymids.append(round(y_max - (r_mid / max(H, 1)) * (y_max - y_min), 3))
    return xs, ymids, ylos, yhis


def compute_curve_rmse(
    dig_x: list[float],
    dig_y: list[float],
    ref_x: list[float],
    ref_y: list[float],
) -> float | None:
    """Compute RMSE between a digitized curve and a Tier-1 raw reference curve over overlapping x."""
    if len(dig_x) < 3 or len(ref_x) < 3:
        return None
    dx, dy = np.asarray(dig_x, dtype=np.float64), np.asarray(dig_y, dtype=np.float64)
    rx, ry = np.asarray(ref_x, dtype=np.float64), np.asarray(ref_y, dtype=np.float64)
    order_d = np.argsort(dx)
    order_r = np.argsort(rx)
    dx, dy = dx[order_d], dy[order_d]
    rx, ry = rx[order_r], ry[order_r]
    lo, hi = max(dx[0], rx[0]), min(dx[-1], rx[-1])
    if hi <= lo:
        return None
    grid = np.linspace(lo, hi, 80)
    diff = np.interp(grid, dx, dy) - np.interp(grid, rx, ry)
    return round(float(np.sqrt(np.mean(diff ** 2))), 4)


# ---------------------------------------------------------------------------
# 4. Microscopy 2D-FFT with Phase Alignment, Harmonic Guard & Transect Coords
# ---------------------------------------------------------------------------

def _power_at_freq(
    power: np.ndarray,
    nh: int,
    nw: int,
    fx: float,
    fy: float,
    rad: int = 2,
) -> float:
    """Peak power inside a small (2*rad+1)^2 window around spatial frequency (fx, fy)."""
    ix = int(round(fx * nw + nw / 2))
    iy = int(round(fy * nh + nh / 2))
    if not (rad <= ix < nw - rad and rad <= iy < nh - rad):
        return 0.0
    return float(power[iy - rad:iy + rad + 1, ix - rad:ix + rad + 1].max())


def measure_periodic_fft_verified(
    img: np.ndarray,
    cal: ScaleBarCal,
    roi: tuple[int, int, int, int],
    spacing_range_um: tuple[float, float] = (0.35, 6.0),
    wavevector_angle_deg: tuple[float, float] | None = None,
    ridge_polarity: str = "bright",
) -> dict[str, Any]:
    """Run 2D-FFT ridge periodicity + exact crest phase alignment + 2f / 0.5f harmonic diagnostics."""
    base = measure_periodic_fft(
        img, cal, roi,
        spacing_range_um=spacing_range_um,
        wavevector_angle_deg=wavevector_angle_deg,
    )
    gray = to_gray(img)
    x0, y0, x1, y1 = [int(v) for v in roi]
    patch = gray[y0:y1, x0:x1]
    period_px = float(base["spacing_px"])
    ang_rad = math.radians(float(base["wavevector_deg"]))
    nx, ny = math.cos(ang_rad), math.sin(ang_rad)
    cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)

    # Phase-align fundamental cosine to bright (or dark) ridge crests inside ROI!
    yy, xx = np.mgrid[y0:y1, x0:x1]
    proj = (xx - cx) * nx + (yy - cy) * ny
    sig = (patch - patch.mean()) * (1.0 if ridge_polarity == "bright" else -1.0)
    cval = np.sum(sig * np.exp(-1j * 2.0 * math.pi * proj / max(period_px, 1e-6)))
    phase_shift_px = float((np.angle(cval) / (2.0 * math.pi)) * period_px)

    # Check 2*f0 (half-spacing = true fundamental if f0 hit 2x subharmonic!) and 0.5*f0 spectral power
    wy = np.hanning(patch.shape[0])[:, None]
    wx = np.hanning(patch.shape[1])[None, :]
    nh, nw = base["fft_shape"]
    F = np.fft.fftshift(np.fft.fft2((patch - patch.mean()) * wy * wx, s=(nh, nw)))
    power = np.abs(F) ** 2
    f0 = float(base["freq_cyc_per_px"])
    fx0, fy0 = f0 * nx, f0 * ny
    p_f0 = max(_power_at_freq(power, nh, nw, fx0, fy0, rad=2), 1e-12)
    p_2f = _power_at_freq(power, nh, nw, 2.0 * fx0, 2.0 * fy0, rad=3)
    p_half = _power_at_freq(power, nh, nw, 0.5 * fx0, 0.5 * fy0, rad=3)
    ratio_2f = float(p_2f / p_f0)
    ratio_half = float(p_half / p_f0)

    # Flag if strong 2f power suggests f0 might be a 2x subharmonic (every-other-ridge beat)
    harmonic_flag = None
    if ratio_2f >= 0.60:
        harmonic_flag = f"strong_2f_harmonic (P(2f)/P(f0)={ratio_2f:.2f}; verify period isn't 2x true pitch)"
    elif ratio_half >= 0.85:
        harmonic_flag = f"strong_half_f_subharmonic (P(0.5f)/P(f0)={ratio_half:.2f})"

    return {
        **base,
        "phase_shift_px": round(phase_shift_px, 3),
        "harmonic_ratio_2f": round(ratio_2f, 3),
        "harmonic_ratio_half": round(ratio_half, 3),
        "harmonic_flag": harmonic_flag,
    }


def measure_transects_with_coords(
    img: np.ndarray,
    cal: ScaleBarCal,
    roi: tuple[int, int, int, int],
    wavevector_deg: float,
    expected_spacing_px: float,
    n_transects: int = 10,
    ridge_polarity: str = "bright",
) -> dict[str, Any]:
    """Measure spacing along n_transects orthogonal profiles AND return exact panel-space endpoints & peak coords."""
    gray = to_gray(img)
    x0, y0, x1, y1 = [int(v) for v in roi]
    rw, rh = x1 - x0, y1 - y0
    cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
    ang = math.radians(wavevector_deg)
    nx, ny = math.cos(ang), math.sin(ang)  # along wavevector (across ridges)
    tx, ty = -ny, nx                       # along ridges

    # Maximum safe half-extent along wavevector and along ridges inside ROI rectangle
    half_n = 0.45 * min(rw / max(abs(nx), 1e-4), rh / max(abs(ny), 1e-4), math.hypot(rw, rh))
    half_t = 0.38 * min(rw / max(abs(tx), 1e-4), rh / max(abs(ty), 1e-4), math.hypot(rw, rh))
    half_n = max(half_n, min(rw, rh) * 0.35)
    half_t = max(half_t, min(rw, rh) * 0.25)

    n_samples = max(64, int(round(2.0 * half_n)))
    s_grid = np.linspace(-half_n, half_n, n_samples)
    offsets = np.linspace(-half_t, half_t, n_transects)

    transects_out: list[dict[str, Any]] = []
    vals_um: list[float] = []
    for idx, off in enumerate(offsets):
        xs = cx + off * tx + s_grid * nx
        ys = cy + off * ty + s_grid * ny
        inside = (xs >= x0 + 1) & (xs <= x1 - 2) & (ys >= y0 + 1) & (ys <= y1 - 2)
        if inside.sum() < max(20, int(1.6 * expected_spacing_px)):
            continue
        xs_in, ys_in = xs[inside], ys[inside]
        s_in = s_grid[inside]
        prof = map_coordinates(gray, [ys_in, xs_in], order=1, mode="nearest")
        if ridge_polarity != "bright":
            prof = -prof
        prof_s = gaussian_filter1d(prof, sigma=max(1.0, expected_spacing_px * 0.08))
        min_dist = max(3, int(round(expected_spacing_px * 0.58)))
        peaks, _ = find_peaks(prof_s, distance=min_dist, prominence=max(2.0, float(np.std(prof_s)) * 0.22))
        if len(peaks) < 2:
            continue
        diffs_px = np.diff(s_in[peaks])
        # Keep adjacent-crest diffs within [0.55x, 1.55x] of expected_spacing_px (reject missed-crest double jumps!)
        good = diffs_px[(diffs_px >= 0.55 * expected_spacing_px) & (diffs_px <= 1.55 * expected_spacing_px)]
        if not len(good):
            good = diffs_px
        med_px = float(np.median(good))
        val_um, lo_um, hi_um = cal.to_um(med_px, px_err=0.5)
        vals_um.append(val_um)
        transects_out.append({
            "index": idx,
            "y_frac": round((idx + 0.5) / n_transects, 3),
            "value": round(val_um, 4),
            "lo": round(lo_um, 4),
            "hi": round(hi_um, 4),
            "n_peaks": int(len(peaks)),
            "p0": [round(float(xs_in[0]), 1), round(float(ys_in[0]), 1)],
            "p1": [round(float(xs_in[-1]), 1), round(float(ys_in[-1]), 1)],
            "peaks_px": [[round(float(xs_in[k]), 1), round(float(ys_in[k]), 1)] for k in peaks],
        })

    return {
        "mean_um": round(float(np.mean(vals_um)), 4) if vals_um else None,
        "median_um": round(float(np.median(vals_um)), 4) if vals_um else None,
        "sd_um": round(float(np.std(vals_um, ddof=1)), 4) if len(vals_um) >= 2 else 0.0,
        "transects": transects_out,
    }


def check_fft_harmonics(
    fft_um: float,
    transect_um: float | None,
    harmonic_ratio_2f: float,
    snr: float,
    rel_tol: float = 0.12,
) -> dict[str, Any]:
    """Evaluate automated FFT harmonic & transect consistency guard."""
    issues: list[str] = []
    delta_pct = None
    if transect_um is not None and fft_um > 0:
        delta_pct = round(100.0 * abs(fft_um - transect_um) / fft_um, 2)
        if delta_pct > rel_tol * 100.0:
            issues.append(f"fft_transect_mismatch ({delta_pct:.1f}% > {rel_tol*100:.0f}%; fft={fft_um:.3f} vs transect={transect_um:.3f} um)")
    if harmonic_ratio_2f >= 0.60:
        issues.append(f"strong_2f_harmonic (ratio={harmonic_ratio_2f:.2f}; possible 2x subharmonic lock)")
    status = "flagged" if issues else ("low_snr_verify" if snr < 8.0 else "pass")
    return {
        "status": status,
        "fft_transect_delta_pct": delta_pct,
        "harmonic_ratio_2f": round(harmonic_ratio_2f, 3),
        "snr": round(snr, 1),
        "issues": issues,
    }


__all__ = [
    "AxisCal",
    "ScaleBarCal",
    "detect_scale_bar",
    "lin_range",
    "log_range",
    "find_axis_ticks",
    "ray_dist_alpha",
    "viterbi_track",
    "walk_ribbon_bounds",
    "fit_irls_line_and_ci",
    "trace_error_arms",
    "trace_error_arms_occluded",
    "shaded_bg_residual",
    "detect_markers_matched_filter",
    "extract_vertical_bars",
    "compute_curve_rmse",
    "measure_periodic_fft_verified",
    "measure_transects_with_coords",
    "check_fft_harmonics",
]
