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


def test_find_axis_ticks_and_misfit():
    from livinglit_lepidoptera.extract_lib import AxisCal, find_axis_ticks

    # Draw a crisp 200x240 plot with left y-axis at x=40 (y=20..170), bottom x-axis at y=170 (x=40..220)
    img = np.full((200, 240, 3), 255, dtype=np.uint8)
    img[20:171, 39:41] = 10   # left spine
    img[169:171, 40:221] = 10  # bottom spine
    # 4 y-ticks at rows 160, 120, 80, 40 (values 0, 10, 20, 30)
    for r in (160, 120, 80, 40):
        img[r - 1:r + 1, 32:39] = 10
    # 4 x-ticks at cols 55, 105, 155, 205 (values 100, 200, 300, 400)
    for c in (55, 105, 155, 205):
        img[171:178, c - 1:c + 1] = 10

    cal = find_axis_ticks(img, y_labels=[0.0, 10.0, 20.0, 30.0], x_labels=[100.0, 200.0, 300.0, 400.0], probe=(2, 6))
    assert cal["x_misfit_px"] <= 0.6
    assert cal["y_misfit_px"] <= 0.6
    assert math.isclose(cal["x_cal"].to_value(130.0), 250.0, abs_tol=2.5)
    assert math.isclose(cal["y_cal"].to_value(100.0), 15.0, abs_tol=0.6)

    # Wrong label count must fail loudly instead of silently miscalibrating
    with pytest.raises(ValueError, match="tick count mismatch"):
        find_axis_ticks(img, y_labels=[0.0, 10.0, 20.0], x_labels=[100.0, 200.0, 300.0, 400.0], probe=(2, 6))

    # Log10 axis calibration check
    lcal = AxisCal.fit([50.0, 150.0, 250.0], [1.0, 10.0, 100.0], scale="log10")
    assert math.isclose(lcal.to_value(200.0), math.sqrt(1000.0), rel_tol=1e-3)


def test_detect_markers_overlapping_occluded_and_shaded():
    from livinglit_lepidoptera.extract_lib import (
        detect_markers_matched_filter,
        shaded_bg_residual,
        trace_error_arms_occluded,
    )

    # 1. Synthetic 120x160 image: orange shaded CI ribbon across middle + 2 overlapping black dots + 1 dot sliced by a red SD bar!
    img = np.full((120, 160, 3), 255, dtype=np.uint8)
    img[35:85, 10:150] = [242, 182, 142]  # translucent orange shaded ribbon

    yy, xx = np.mgrid[0:120, 0:160]
    true_pts = [(42, 58), (52, 58), (105, 60)]  # (42,58) & (52,58) overlap tightly! (105,60) sits behind a red line!
    for cx, cy in true_pts:
        disk = (xx - cx) ** 2 + (yy - cy) ** 2 <= 6.2 ** 2
        # Blended dark-brown dot inside the shaded orange ribbon (simulating ggplot2 ribbon over geom_point!)
        img[disk] = [62, 38, 26]
    # Draw vertical red SD bar straight through (105, 60)
    img[30:90, 104:107] = [230, 30, 30]

    _, res = shaded_bg_residual(img, marker_diam_px=13, mode="median")
    res_lum = res.mean(axis=2)
    lum = img.astype(np.float32).mean(axis=2)
    red_occ = (img[:, :, 0].astype(np.float32) - img[:, :, 1].astype(np.float32) > 100.0) & (lum < 150.0)
    tgt = (lum < 110.0) & (res_lum >= 45.0) & ~red_occ

    pts = detect_markers_matched_filter(
        tgt, red_occ, radius=6.0, shape="disk",
        min_visible=0.35, max_bg=0.20, min_score=0.30,
        min_sep_factor=1.30, peel=True, peel_radius_factor=0.90, upsample=1,
    )
    assert len(pts) == 3
    # Every true point recovered within 1.5 px (including BOTH overlapping dots AND the red-bar-occluded dot!)
    for tx, ty in true_pts:
        assert min(math.hypot(p["x"] - tx, p["y"] - ty) for p in pts) <= 1.5

    # 2. Occlusion-crossing error bar test (walks through crossing occluder AND mirrors hidden lower end!)
    arm = np.zeros((120, 120), dtype=bool)
    occ = np.zeros((120, 120), dtype=bool)
    arm[20:60, 60] = True      # upper arm from y=60 up to y=20 (len=40)
    occ[35:42, 56:65] = True   # crossing bar through upper arm -> must bridge!
    arm[35:42, 60] = False
    occ[64:105, 56:65] = True  # occluder hiding the entire lower arm -> must mirror to y=100!
    xl, xr, yd, yu, flags = trace_error_arms_occluded(arm, occ, 60, 60, max_len=60, marker_r=4.0)
    assert yu == 20.0
    assert flags["y_lo_hidden"] is True
    assert yd == 100.0

