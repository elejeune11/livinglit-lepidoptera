"""Shared microscopy image-measurement primitives (generic; no paper-specific coordinates).

Provides auditable, deterministic measurements of periodic scale nanostructures
(longitudinal ridge spacing, transverse crossrib spacing) from top-down SEM,
confocal, or phase microscopy panels:

1. Scale bar detection & calibration (`detect_scale_bar`, `ScaleBarCal`).
2. 2D FFT power-spectrum periodic spacing + dominant orientation (`measure_periodic_fft`).
3. Rotated multi-transect 1D autocorrelation & peak-to-peak spacing (`measure_transect_spacing`).
4. Audit overlay rendering (`save_audit_overlay`) written outside the repository.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d, rotate
from scipy.signal import find_peaks


@dataclass
class ScaleBarCal:
    """Linear scale-bar calibration from pixels to micrometres, with uncertainty."""
    px_length: float
    physical_um: float
    px_unc: float = 1.0
    bbox: tuple[int, int, int, int] | None = None  # (x, y, w, h) in panel coordinates

    @property
    def um_per_px(self) -> float:
        return self.physical_um / self.px_length

    @property
    def rel_unc(self) -> float:
        return self.px_unc / self.px_length

    def to_um(self, px: float, px_err: float = 0.0) -> tuple[float, float, float]:
        """Convert a pixel distance to (value_um, lo_um, hi_um)."""
        val = px * self.um_per_px
        rel = math.hypot(self.rel_unc, (px_err / px) if px > 0 else 0.0)
        return val, val * (1.0 - rel), val * (1.0 + rel)


def to_gray(img: np.ndarray) -> np.ndarray:
    """Convert RGB or grayscale image to float64 [0, 255]."""
    if img.ndim == 3:
        return (0.299 * img[:, :, 0] + 0.587 * img[:, :, 1] + 0.114 * img[:, :, 2]).astype(np.float64)
    return img.astype(np.float64)


def detect_scale_bar(
    img: np.ndarray,
    search_box: tuple[int, int, int, int],
    physical_um: float,
    polarity: str = "bright",
    threshold: float | None = None,
    min_aspect: float = 3.0,
    px_unc: float = 1.0,
) -> ScaleBarCal:
    """Detect a horizontal rectangular scale bar inside search_box=(x0, y0, x1, y1).

    Returns a ScaleBarCal whose px_length is measured from the bar's horizontal span
    at half-maximum contrast along its central rows (subpixel-refined).
    """
    gray = to_gray(img)
    x0, y0, x1, y1 = [int(v) for v in search_box]
    sub = gray[y0:y1, x0:x1]
    if sub.size == 0:
        raise ValueError("empty scale-bar search_box")
    if polarity == "bright":
        thr = float(threshold) if threshold is not None else max(220.0, float(np.percentile(sub, 98)) - 15.0)
        mask = (sub >= thr).astype(np.uint8)
    else:
        thr = float(threshold) if threshold is not None else min(35.0, float(np.percentile(sub, 2)) + 15.0)
        mask = (sub <= thr).astype(np.uint8)

    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    best = None
    for i in range(1, n):
        bx, by, bw, bh, area = [int(stats[i, k]) for k in range(5)]
        if bw < 12 or bh < 1:
            continue
        aspect = bw / max(bh, 1)
        fill = area / max(bw * bh, 1)
        if aspect >= min_aspect and fill >= 0.70:
            score = bw * fill
            if best is None or score > best[0]:
                best = (score, bx, by, bw, bh)
    if best is None:
        raise ValueError(f"no horizontal {polarity} scale bar found in {search_box}")
    _, bx, by, bw, bh = best
    # Subpixel horizontal span from central row profile
    cy0 = by + max(0, bh // 4)
    cy1 = by + max(cy0 - by + 1, bh - bh // 4)
    pad = 4
    rx0 = max(0, bx - pad)
    rx1 = min(sub.shape[1], bx + bw + pad)
    prof = sub[cy0:cy1, rx0:rx1].mean(axis=0)
    bg = float(np.median(np.concatenate([prof[:2], prof[-2:]])))
    fg = float(np.max(prof) if polarity == "bright" else np.min(prof))
    mid = 0.5 * (bg + fg)
    above = prof >= mid if polarity == "bright" else prof <= mid
    idx = np.where(above)[0]
    if len(idx) >= 2:
        l_idx, r_idx = int(idx[0]), int(idx[-1])
        # Linear interpolation at edges
        left = float(l_idx)
        if l_idx > 0 and prof[l_idx] != prof[l_idx - 1]:
            left = l_idx - 1 + (mid - prof[l_idx - 1]) / (prof[l_idx] - prof[l_idx - 1])
        right = float(r_idx)
        if r_idx + 1 < len(prof) and prof[r_idx + 1] != prof[r_idx]:
            right = r_idx + (mid - prof[r_idx]) / (prof[r_idx + 1] - prof[r_idx])
        px_len = float(right - left)
    else:
        px_len = float(bw)
    return ScaleBarCal(
        px_length=px_len,
        physical_um=float(physical_um),
        px_unc=float(px_unc),
        bbox=(x0 + bx, y0 + by, bw, bh),
    )


def _pad_fft(gray: np.ndarray) -> tuple[np.ndarray, int, int]:
    """Mean-subtract, Hann-window, and zero-pad a 2D ROI for high-resolution FFT."""
    g = gray.astype(np.float64)
    g = g - g.mean()
    wy = np.hanning(g.shape[0])[:, None]
    wx = np.hanning(g.shape[1])[None, :]
    win = g * wy * wx
    # Zero-pad to at least 2x (power of 2) for fine frequency interpolation
    nh = 1 << int(math.ceil(math.log2(max(256, g.shape[0] * 2))))
    nw = 1 << int(math.ceil(math.log2(max(256, g.shape[1] * 2))))
    F = np.fft.fftshift(np.fft.fft2(win, s=(nh, nw)))
    power = np.abs(F) ** 2
    return power, nh, nw


def measure_periodic_fft(
    img: np.ndarray,
    cal: ScaleBarCal,
    roi: tuple[int, int, int, int],
    spacing_range_um: tuple[float, float] = (0.35, 6.0),
    wavevector_angle_deg: tuple[float, float] | None = None,
) -> dict:
    """Estimate dominant periodic spacing (e.g. longitudinal ridge spacing) via 2D FFT.

    Parameters
    ----------
    img : RGB or grayscale panel array
    cal : ScaleBarCal
    roi : (x0, y0, x1, y1) pixel box on a single flat scale region (no scale bars or labels)
    spacing_range_um : (min_um, max_um) plausible physical spacing range
    wavevector_angle_deg : optional (lo_deg, hi_deg) restricting the wavevector direction
        in (-90, 90] degrees (0 = horizontal wavevector = vertical ridges;
        90 = vertical wavevector = horizontal ridges). Useful to separate longitudinal
        ridges from orthogonal crossribs when both are strong.

    Returns dict with spacing_um, lo_um, hi_um, spacing_px, wavevector_deg, ridge_angle_deg,
    peak_snr, freq_cyc_per_px, and peak_xy.
    """
    gray = to_gray(img)
    x0, y0, x1, y1 = [int(v) for v in roi]
    patch = gray[y0:y1, x0:x1]
    if patch.shape[0] < 32 or patch.shape[1] < 32:
        raise ValueError(f"ROI too small: {patch.shape}")

    power, nh, nw = _pad_fft(patch)
    fy = np.fft.fftshift(np.fft.fftfreq(nh))[:, None]  # cycles / px
    fx = np.fft.fftshift(np.fft.fftfreq(nw))[None, :]
    fr = np.hypot(fx, fy)
    # Angle of wavevector in (-90, 90] deg (symmetric upper/right half-plane)
    ang = np.degrees(np.arctan2(fy, fx))
    # Map to (-90, 90]
    ang_folded = ((ang + 90.0) % 180.0) - 90.0

    # Convert physical spacing range to spatial frequency range (cycles/px)
    f_min = cal.um_per_px / spacing_range_um[1]
    f_max = cal.um_per_px / spacing_range_um[0]
    # Also require at least ~1.8 cycles across the ROI so DC leakage isn't picked
    min_dim = min(patch.shape[0], patch.shape[1])
    f_min = max(f_min, 1.8 / max(patch.shape[0], patch.shape[1]))

    mask = (fr >= f_min) & (fr <= f_max) & ((fy > 0) | ((fy == 0) & (fx > 0)))
    if wavevector_angle_deg is not None:
        a0, a1 = wavevector_angle_deg
        if a0 <= a1:
            amask = (ang_folded >= a0) & (ang_folded <= a1)
        else:
            # Wrap-around around ±90 deg (e.g. (70, -70) for nearly vertical wavevector)
            amask = (ang_folded >= a0) | (ang_folded <= a1)
        mask &= amask

    if not np.any(mask):
        raise ValueError("no valid FFT frequencies inside spacing_range_um and angle bounds")

    masked_p = np.where(mask, power, -1.0)
    iy, ix = np.unravel_index(int(np.argmax(masked_p)), power.shape)
    peak_val = float(power[iy, ix])
    bg_med = float(np.median(power[mask]))
    snr = peak_val / max(bg_med, 1e-12)

    # Sub-bin quadratic peak interpolation in log-power
    dy, dx = 0.0, 0.0
    if 1 <= iy < nh - 1:
        p0, p1, p2 = math.log(power[iy - 1, ix] + 1e-12), math.log(peak_val + 1e-12), math.log(power[iy + 1, ix] + 1e-12)
        denom = (p0 - 2 * p1 + p2)
        if denom < 0:
            dy = float(np.clip(0.5 * (p0 - p2) / denom, -0.5, 0.5))
    if 1 <= ix < nw - 1:
        p0, p1, p2 = math.log(power[iy, ix - 1] + 1e-12), math.log(peak_val + 1e-12), math.log(power[iy, ix + 1] + 1e-12)
        denom = (p0 - 2 * p1 + p2)
        if denom < 0:
            dx = float(np.clip(0.5 * (p0 - p2) / denom, -0.5, 0.5))

    fx_peak = (ix + dx - nw / 2) / nw
    fy_peak = (iy + dy - nh / 2) / nh
    f0 = math.hypot(fx_peak, fy_peak)
    spacing_px = 1.0 / f0
    wv_deg = ((math.degrees(math.atan2(fy_peak, fx_peak)) + 90.0) % 180.0) - 90.0
    # Ridges run perpendicular to the wavevector
    ridge_deg = ((wv_deg + 90.0 + 90.0) % 180.0) - 90.0

    # Spectral resolution uncertainty: half a native ROI frequency bin (0.5 / N_perp)
    theta = math.radians(wv_deg)
    n_along_wv = abs(patch.shape[1] * math.cos(theta)) + abs(patch.shape[0] * math.sin(theta))
    df_res = 0.5 / max(n_along_wv, 1.0)
    spacing_px_err = (df_res / (f0 ** 2))
    val_um, lo_um, hi_um = cal.to_um(spacing_px, spacing_px_err)

    return {
        "spacing_um": val_um,
        "lo_um": lo_um,
        "hi_um": hi_um,
        "spacing_px": spacing_px,
        "spacing_px_err": spacing_px_err,
        "wavevector_deg": wv_deg,
        "ridge_angle_deg": ridge_deg,
        "peak_snr": snr,
        "freq_cyc_per_px": f0,
        "peak_xy": (float(ix + dx), float(iy + dy)),
        "fft_shape": (nh, nw),
        "roi": (x0, y0, x1, y1),
    }


def measure_transect_spacing(
    img: np.ndarray,
    cal: ScaleBarCal,
    roi: tuple[int, int, int, int],
    wavevector_deg: float,
    expected_spacing_px: float,
    n_transects: int = 12,
    ridge_polarity: str = "bright",
) -> dict:
    """Measure ridge spacing along n_transects parallel 1D profiles perpendicular to the ridges.

    Rotates the ROI so the wavevector runs horizontally (ridges vertical), averages bands
    into n_transects profiles, and extracts per-transect peak-to-peak ridge spacings
    (returning individual transect mean spacings suitable as `points` in LivingLit).
    """
    gray = to_gray(img)
    x0, y0, x1, y1 = [int(v) for v in roi]
    patch = gray[y0:y1, x0:x1]
    # Rotate so the wavevector aligns with +x (columns), keeping full extent along the wavevector
    rot = rotate(patch, angle=wavevector_deg, reshape=True, order=1, mode="nearest")
    # Also rotate a mask of valid pixels (ones) so we crop only strictly inside the original ROI
    valid = rotate(np.ones_like(patch), angle=wavevector_deg, reshape=True, order=0, mode="constant", cval=0.0) > 0.5
    # Find largest clean rows/cols: shrink gently from rotated bounding box edges
    ys, xs = np.where(valid)
    r_lo, r_hi = int(ys.min()), int(ys.max()) + 1
    c_lo, c_hi = int(xs.min()), int(xs.max()) + 1
    # For nearly axis-aligned wavevectors (0 or ±90 deg), zero corner shrinkage is needed!
    rad = abs(math.radians(wavevector_deg)) % (math.pi / 2)
    shrink = min(0.18, 0.25 * math.sin(2 * rad))
    h, w = r_hi - r_lo, c_hi - c_lo
    my, mx = int(h * shrink), int(w * shrink)
    inner = rot[r_lo + my:r_hi - my, c_lo + mx:c_hi - mx] if (h - 2 * my > 20 and w - 2 * mx > 20) else rot[r_lo:r_hi, c_lo:c_hi]

    band_h = max(3, inner.shape[0] // n_transects)
    sigma = min(8.0, max(1.0, expected_spacing_px * 0.10))
    min_dist = max(3, int(round(expected_spacing_px * 0.65)))

    transect_spacings_um = []
    all_pair_spacings_px = []
    sample_profile = None
    sample_peaks = None

    for i in range(n_transects):
        r0 = i * band_h
        r1 = min(inner.shape[0], r0 + band_h)
        if r1 - r0 < 2:
            break
        prof = inner[r0:r1, :].mean(axis=0)
        if ridge_polarity == "dark":
            prof = -prof
        smooth = gaussian_filter1d(prof - prof.mean(), sigma=sigma)
        prom = max(0.22 * float(np.std(smooth)), 1e-6)
        peaks, _ = find_peaks(smooth, distance=min_dist, prominence=prom)
        if len(peaks) >= 2:
            # Subpixel peak refinement
            refined = []
            for p in peaks:
                if 1 <= p < len(smooth) - 1:
                    y_l, y_c, y_r = smooth[p - 1], smooth[p], smooth[p + 1]
                    denom = y_l - 2 * y_c + y_r
                    dp = float(np.clip(0.5 * (y_l - y_r) / denom, -0.5, 0.5)) if denom < 0 else 0.0
                    refined.append(p + dp)
                else:
                    refined.append(float(p))
            diffs = np.diff(refined)
            # Reject single-missed-ridge outliers (>1.65x expected) or false splits (<0.55x)
            good = diffs[(diffs >= 0.55 * expected_spacing_px) & (diffs <= 1.65 * expected_spacing_px)]
            if len(good) >= 1:
                all_pair_spacings_px.extend(good.tolist())
                m_px = float(np.mean(good))
                se_px = float(np.std(good, ddof=1) / math.sqrt(len(good))) if len(good) > 1 else 0.8
                v_um, lo_um, hi_um = cal.to_um(m_px, max(se_px, 0.5))
                transect_spacings_um.append({
                    "value": v_um,
                    "lo": lo_um,
                    "hi": hi_um,
                    "n_pairs": int(len(good)),
                    "y_frac": (r0 + r1) / (2.0 * inner.shape[0]),
                })
                if sample_profile is None and i >= n_transects // 3:
                    sample_profile = smooth
                    sample_peaks = peaks

    if not transect_spacings_um:
        return {"transects": [], "mean_um": None, "sd_um": None, "lo_um": None, "hi_um": None,
                "n_pairs": 0, "sample_profile": None, "sample_peaks": None}

    vals = np.array([t["value"] for t in transect_spacings_um], dtype=float)
    mean_um = float(np.mean(vals))
    sd_um = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
    se_um = sd_um / math.sqrt(len(vals)) if len(vals) > 1 else mean_um * cal.rel_unc
    comb_err = math.hypot(se_um, mean_um * cal.rel_unc)
    return {
        "transects": transect_spacings_um,
        "mean_um": mean_um,
        "sd_um": sd_um,
        "lo_um": mean_um - comb_err,
        "hi_um": mean_um + comb_err,
        "n_pairs": len(all_pair_spacings_px),
        "sample_profile": sample_profile,
        "sample_peaks": sample_peaks,
    }


def save_audit_overlay(
    img: np.ndarray,
    cal: ScaleBarCal,
    fft_res: dict,
    transect_res: dict,
    out_path: Path,
    title: str = "",
) -> Path:
    """Write a 3-panel visual audit image (panel+ROI+bar | 2D FFT | 1D transect profile)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vis = img.copy()
    if vis.ndim == 2:
        vis = np.stack([vis] * 3, axis=-1)
    vis = np.ascontiguousarray(vis[:, :, ::-1])  # BGR for cv2

    # Draw ROI in cyan and wavevector arrow in yellow
    x0, y0, x1, y1 = fft_res["roi"]
    cv2.rectangle(vis, (x0, y0), (x1, y1), (255, 220, 0), 2)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    rad = math.radians(fft_res["wavevector_deg"])
    L = min(x1 - x0, y1 - y0) * 0.3
    cv2.arrowedLine(vis, (int(cx - L * math.cos(rad)), int(cy - L * math.sin(rad))),
                    (int(cx + L * math.cos(rad)), int(cy + L * math.sin(rad))), (0, 255, 255), 2, tipLength=0.2)
    # Draw scale bar box in green
    if cal.bbox:
        bx, by, bw, bh = cal.bbox
        cv2.rectangle(vis, (bx - 2, by - 2), (bx + bw + 2, by + bh + 2), (0, 255, 0), 2)
        ty = by + bh + 15 if by < 24 else by - 6
        cv2.putText(vis, f"{cal.physical_um:g} um ({cal.px_length:.1f} px)", (max(4, min(vis.shape[1] - 140, bx - 20)), min(vis.shape[0] - 4, ty)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 255, 0), 1, cv2.LINE_AA)

    # Label panel
    label = f"{title} | FFT={fft_res['spacing_um']:.3f} um"
    if transect_res.get("mean_um") is not None:
        label += f" | Transect={transect_res['mean_um']:.3f} +/- {transect_res['sd_um']:.3f} um"
    cv2.rectangle(vis, (0, 0), (vis.shape[1], 24), (20, 20, 20), -1)
    cv2.putText(vis, label[:85], (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)

    # Panel 2: Log 2D FFT spectrum centered on DC
    gray = to_gray(img)
    patch = gray[y0:y1, x0:x1]
    power, nh, nw = _pad_fft(patch)
    logp = np.log1p(power)
    # Zoom into central 40% of FFT
    cyf, cxf = nh // 2, nw // 2
    zh, zw = nh // 5, nw // 5
    crop_fft = logp[cyf - zh:cyf + zh, cxf - zw:cxf + zw]
    crop_fft = ((crop_fft - crop_fft.min()) / max(crop_fft.max() - crop_fft.min(), 1e-9) * 255).astype(np.uint8)
    fft_bgr = cv2.applyColorMap(crop_fft, cv2.COLORMAP_INFERNO)
    px_f, py_f = fft_res["peak_xy"]
    # Mark fundamental peak & its conjugate
    for sgn in (1, -1):
        mx = int(round(zw + sgn * (px_f - cxf)))
        my = int(round(zh + sgn * (py_f - cyf)))
        if 0 <= mx < fft_bgr.shape[1] and 0 <= my < fft_bgr.shape[0]:
            cv2.circle(fft_bgr, (mx, my), 6, (0, 255, 255), 1, cv2.LINE_AA)

    # Resize panels to same height
    H = max(320, vis.shape[0])
    w1 = int(round(vis.shape[1] * H / vis.shape[0]))
    p1 = cv2.resize(vis, (w1, H), interpolation=cv2.INTER_AREA)
    p2 = cv2.resize(fft_bgr, (H, H), interpolation=cv2.INTER_AREA)
    cv2.putText(p2, f"2D FFT (SNR={fft_res['peak_snr']:.0f})", (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    # Panel 3: 1D transect profile with detected peaks
    p3 = np.full((H, H, 3), 24, dtype=np.uint8)
    prof = transect_res.get("sample_profile")
    peaks = transect_res.get("sample_peaks")
    if prof is not None and len(prof) > 4:
        pmin, pmax = float(prof.min()), float(prof.max())
        span = max(pmax - pmin, 1e-6)
        xs = np.linspace(16, H - 16, len(prof)).astype(int)
        ys = (H - 36 - ((prof - pmin) / span) * (H - 80)).astype(int)
        pts = np.stack([xs, ys], axis=1).reshape(-1, 1, 2)
        cv2.polylines(p3, [pts], False, (255, 200, 80), 1, cv2.LINE_AA)
        if peaks is not None:
            for pk in peaks:
                cv2.circle(p3, (int(xs[pk]), int(ys[pk])), 4, (60, 240, 120), -1, cv2.LINE_AA)
    cv2.putText(p3, "1D Transect Profile & Peaks", (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    out = np.hstack([p1, p2, p3])
    cv2.imwrite(str(out_path), out)
    return out_path
