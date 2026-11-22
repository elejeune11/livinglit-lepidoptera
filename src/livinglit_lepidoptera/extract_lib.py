"""Shared, figure-agnostic CV, DP, and microscopy metrology primitives for livinglit-lepidoptera.

Zero paper- or figure-specific pixel coordinates live here. Individual figure extractors under
`records/<paper>/extractors/<fig>.py` import these unit-tested building blocks and supply only
figure-local calibration and trace definitions.
"""
from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d, map_coordinates
from scipy.signal import find_peaks

from livinglit_lepidoptera.figures.microscopy import (
    ScaleBarCal,
    detect_scale_bar,
    measure_periodic_fft,
    to_gray,
)


# ---------------------------------------------------------------------------
# 1. Axis & coordinate calibration helpers
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
    "ScaleBarCal",
    "detect_scale_bar",
    "lin_range",
    "log_range",
    "ray_dist_alpha",
    "viterbi_track",
    "walk_ribbon_bounds",
    "fit_irls_line_and_ci",
    "trace_error_arms",
    "extract_vertical_bars",
    "compute_curve_rmse",
    "measure_periodic_fft_verified",
    "measure_transects_with_coords",
    "check_fft_harmonics",
]
