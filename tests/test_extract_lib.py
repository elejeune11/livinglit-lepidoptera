"""Unit tests for livinglit_lepidoptera.extract_lib CV, DP, and 2D-FFT microscopy metrology primitives."""
from __future__ import annotations

import math
import numpy as np
import pytest

from livinglit_lepidoptera.extract_lib import (
    ScaleBarCal,
    check_fft_harmonics,
    compute_curve_rmse,
    fit_irls_line_and_ci,
    lin_range,
    log_range,
    measure_periodic_fft_verified,
    measure_transects_with_coords,
    ray_dist_alpha,
    trace_error_arms,
    viterbi_track,
    walk_ribbon_bounds,
)


def test_lin_and_log_range():
    lo, hi = lin_range(0, 100, 10.0, 350.0, 90.0, 750.0)
    assert math.isclose(lo, 300.0, abs_tol=1e-3)
    assert math.isclose(hi, 800.0, abs_tol=1e-3)
    llo, lhi = log_range(0, 100, 0.0, 1.0, 100.0, 100.0)
    assert math.isclose(llo, 1.0, rel_tol=1e-4)
    assert math.isclose(lhi, 100.0, rel_tol=1e-4)


def test_ray_dist_alpha_and_ribbon_walker():
    # Synthetic white image (120x80) with a red core line at y=60 and pink ±SD ribbon at y=42..78
    img = np.full((120, 80, 3), 255.0, dtype=np.float32)
    target = np.array([220.0, 40.0, 40.0], dtype=np.float32)
    bg = np.array([255.0, 255.0, 255.0], dtype=np.float32)
    img[42:79, 5:75] = bg + 0.25 * (target - bg)
    img[59:62, 5:75] = target

    perp, alpha = ray_dist_alpha(img, (220, 40, 40))
    assert float(perp[60, 40]) < 1.0
    assert float(alpha[60, 40]) > 0.95
    assert 0.20 < float(alpha[48, 40]) < 0.30

    x_cols = np.arange(10, 70, 5)
    y_path = np.full(len(x_cols), 60, dtype=np.int32)
    rib_mask = (perp < 5.0) & (alpha > 0.15)
    y_lo, y_hi = walk_ribbon_bounds(rib_mask, x_cols, y_path, max_half=40, max_gap=2)
    assert np.allclose(y_hi, 42.0, atol=1.0)
    assert np.allclose(y_lo, 78.0, atol=1.0)


def test_viterbi_track_climbs_sharp_peak_without_flattening():
    H, T = 100, 40
    true_y = np.round(80 - 55 * np.exp(-0.5 * ((np.arange(T) - 20) / 4.0) ** 2)).astype(int)
    cost = np.full((H, T), 50.0, dtype=np.float64)
    for t, y in enumerate(true_y):
        cost[y, t] = 0.0
    # Add a false horizontal distractor at y=75 across the middle
    cost[75, 10:30] = 3.0
    path = viterbi_track(cost, max_step=25, smooth_w=0.20, norm="l1")
    assert np.max(np.abs(path - true_y)) <= 1


def test_fit_irls_line_and_ci():
    mask = np.zeros((100, 120), dtype=bool)
    xs = np.arange(10, 110)
    for x in xs:
        yc = int(round(80 - 0.5 * x))
        mask[max(0, yc - 6):min(100, yc + 7), x] = True
    # Inject dense outlier block far away from line
    mask[5:15, 20:35] = True
    cols, ym, ylo, yhi = fit_irls_line_and_ci(mask, 15, 105, n_pts=20, max_hw=15.0)
    expected = 80.0 - 0.5 * cols
    assert float(np.max(np.abs(ym - expected))) < 2.0
    assert np.all(ylo > ym) and np.all(yhi < ym)


def test_trace_error_arms_and_curve_rmse():
    mask = np.zeros((100, 100), dtype=bool)
    mask[50, 30:76] = True  # x error bar from 30..75
    mask[25:71, 50] = True  # y error bar from 25..70
    xl, xr, yd, yu = trace_error_arms(mask, 50, 50, max_len=40)
    assert (xl, xr, yd, yu) == (30, 75, 70, 25)

    rmse = compute_curve_rmse([0.0, 1.0, 2.0], [10.0, 20.0, 30.0], [0.0, 1.0, 2.0], [10.5, 20.5, 30.5])
    assert math.isclose(rmse, 0.5, abs_tol=1e-4)


def test_synthetic_2d_fft_and_harmonic_guard():
    # Generate a crisp rotated periodic grating with exact 16.0 px period and scale 0.05 um/px -> 0.800 um!
    H, W = 240, 240
    yy, xx = np.mgrid[0:H, 0:W]
    theta = math.radians(20.0)
    proj = xx * math.cos(theta) + yy * math.sin(theta)
    period_px = 16.0
    img = (127.5 + 100.0 * np.cos(2.0 * math.pi * proj / period_px)).astype(np.float64)

    cal = ScaleBarCal(px_length=40.0, physical_um=2.0, px_unc=0.5)  # 0.05 um/px
    roi = (20, 20, 220, 220)
    fft_r = measure_periodic_fft_verified(img, cal, roi, spacing_range_um=(0.4, 2.0))
    assert math.isclose(fft_r["spacing_um"], 0.80, rel_tol=0.03)
    assert fft_r["peak_snr"] > 50.0

    tr_r = measure_transects_with_coords(img, cal, roi, fft_r["wavevector_deg"], fft_r["spacing_px"], n_transects=8)
    assert tr_r["mean_um"] is not None
    assert math.isclose(tr_r["mean_um"], 0.80, rel_tol=0.04)
    assert len(tr_r["transects"]) >= 5
    assert "p0" in tr_r["transects"][0] and "peaks_px" in tr_r["transects"][0]

    hg_ok = check_fft_harmonics(fft_r["spacing_um"], tr_r["mean_um"], fft_r["harmonic_ratio_2f"], fft_r["peak_snr"])
    assert hg_ok["status"] == "pass"

    # Simulate a 2x subharmonic lock (FFT=1.60 um while real transect peaks are 0.80 um and strong 2f harmonic!)
    hg_bad = check_fft_harmonics(1.60, 0.80, 0.72, 200.0)
    assert hg_bad["status"] == "flagged"
    assert len(hg_bad["issues"]) >= 1
