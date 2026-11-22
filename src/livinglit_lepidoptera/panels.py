"""Sub-panel data objects (`panels.yaml`), digitized plot/curve series, and associated external resources.

Turns every figure and every sub-panel in a paper into a first-class, context-resolved,
typed data object, and saves every digitized plot/curve/profile/table and harvested
supplement/dataset/code asset as clean machine-readable files on disk.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np
import yaml
from pydantic import Field
from scipy.ndimage import distance_transform_edt

from . import PAPERS_DIR, RECORDS_DIR
from .extract_lib import (
    ScaleBarCal,
    check_fft_harmonics,
    detect_scale_bar,
    measure_periodic_fft_verified,
    measure_transects_with_coords,
)
from .figures.source import blobs
from .models import Anchor, Strict, check_id
from .text import find_quote

PanelArchetype = Literal[
    "planar_microscopy",
    "cross_section",
    "macro_morphology",
    "quantitative_plot",
    "spectral_or_profile",
    "phylogeny_or_schematic",
]


class ScaleBarSpec(Strict):
    um: float
    search_box: tuple[int, int, int, int] | None = None
    px: float | None = None
    polarity: Literal["bright", "dark"] = "bright"
    source: str = "caption"


class PeriodicMeasureSpec(Strict):
    roi: tuple[int, int, int, int]
    spacing_range_um: tuple[float, float] = (0.3, 6.0)
    wavevector_angle_deg: tuple[float, float] | None = None
    channel: Literal["gray", "green", "green_isolated", "magenta", "red", "blue", "max_rgb"] = "gray"
    measure_crossrib: bool = False
    crossrib_range_um: tuple[float, float] = (0.25, 1.5)
    crossrib_channel: Literal["gray", "green", "green_isolated", "magenta", "red", "blue", "max_rgb"] | None = None


class CurveTraceSpec(Strict):
    plot_box: tuple[int, int, int, int]  # (x0, y0, x1, y1) inside panel crop
    x_range: tuple[float, float]
    y_range: tuple[float, float]
    x_unit: str
    y_unit: str
    traces: dict[str, tuple[int, int, int]]  # label -> target RGB color
    exclude_boxes: list[tuple[int, int, int, int]] = Field(default_factory=list)
    bg_polarity: Literal["light", "dark"] = "light"
    mode: Literal["auto", "nearest_ray", "ribbon_dual_rb", "dark_bg", "monochrome"] = "auto"
    ribbon_core: bool = False
    color_tol: int = 58
    max_ray_dist: float = 34.0
    min_alpha: float = 0.22
    smooth_jump_px: float = 20.0
    y_bands: dict[str, tuple[int, int]] = Field(default_factory=dict)
    n_bins: int = 55


class ScatterGroupSpec(Strict):
    rgb: tuple[int, int, int] | None = None  # None = dark/greyscale markers
    tol: int = 48
    x_span: tuple[int, int] | None = None  # optional x-band in plot_box px
    y_span: tuple[int, int] | None = None  # optional y-band in plot_box px


class ScatterDigitizeSpec(Strict):
    plot_box: tuple[int, int, int, int]  # (x0, y0, x1, y1) inside panel crop
    x_range: tuple[float, float] = (0.0, 1.0)
    y_range: tuple[float, float]
    x_unit: str = ""
    y_unit: str
    mode: Literal["scatter_2d", "beeswarm_1d", "crosshair_errorbars"] = "scatter_2d"
    exclude_boxes: list[tuple[int, int, int, int]] = Field(default_factory=list)
    min_dist_px: int = 7
    disc_thr_px: float = 3.2
    use_edt: bool = False
    groups: dict[str, ScatterGroupSpec]


class BoxplotGroupSpec(Strict):
    x_center: int  # inside plot_box px
    half_width: int = 12
    fill_rgb: tuple[int, int, int] | None = None


class BoxplotDigitizeSpec(Strict):
    plot_box: tuple[int, int, int, int]
    y_range: tuple[float, float]
    y_unit: str
    style: Literal["dark_ink", "white_box", "gray_box_white_dot", "shaded_notch"] = "dark_ink"
    groups: dict[str, BoxplotGroupSpec]


class AssociatedResource(Strict):
    id: str
    kind: Literal["dataset", "code", "supplement", "image_collection"]
    repository: Literal["Zenodo", "Figshare", "OSF", "Dryad", "eLife_CDN", "PMC_Supplement", "Publisher_Supplement", "NCBI_SRA"]
    title: str
    url: str
    doi: str | None = None
    license: str = "not stated"
    local_files: list[str] = Field(default_factory=list)  # relative to papers_dont_ever_commit/<paper>/associated/
    feeds_panels: list[str] = Field(default_factory=list)
    feeds_items: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class ResourcesFile(Strict):
    record: str
    resources: list[AssociatedResource] = Field(default_factory=list)


class PanelSpec(Strict):
    label: str
    title: str
    bbox: tuple[int, int, int, int]
    archetype: PanelArchetype
    context: dict[str, str] = Field(default_factory=dict)
    stains_or_markers: list[str] = Field(default_factory=list)
    scale_bar: ScaleBarSpec | None = None
    periodic_spec: PeriodicMeasureSpec | None = None
    curve_spec: CurveTraceSpec | None = None
    scatter_spec: ScatterDigitizeSpec | None = None
    boxplot_spec: BoxplotDigitizeSpec | None = None
    extractor: str | None = None  # relative to records/<paper>/, e.g. "extractors/f3_angles.py:extract"
    composite_justification: str | None = None
    harmonic_verified: bool = False
    partial_x_range: bool = False
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    linked_items: list[str] = Field(default_factory=list)
    linked_claims: list[str] = Field(default_factory=list)
    linked_resources: list[str] = Field(default_factory=list)


class FigureManifest(Strict):
    label: str
    file: str
    xml_id: str | None = None
    title: str
    caption_anchor: Anchor
    context: dict[str, str] = Field(default_factory=dict)
    panels: dict[str, PanelSpec]


class PanelsFile(Strict):
    record: str
    default_context: dict[str, str] = Field(default_factory=dict)
    figures: dict[str, FigureManifest]


def _extract_channel(panel_rgb: np.ndarray, ch: str) -> np.ndarray:
    if ch == "green":
        return panel_rgb[:, :, 1].astype(np.float64)
    if ch == "green_isolated":
        return np.clip(
            panel_rgb[:, :, 1].astype(np.float64)
            - 0.45 * (panel_rgb[:, :, 0].astype(np.float64) + panel_rgb[:, :, 2].astype(np.float64)),
            0.0,
            255.0,
        )
    if ch == "red":
        return panel_rgb[:, :, 0].astype(np.float64)
    if ch == "blue":
        return panel_rgb[:, :, 2].astype(np.float64)
    if ch == "magenta":
        return np.clip(0.6 * panel_rgb[:, :, 0].astype(np.float64) + 0.4 * panel_rgb[:, :, 2].astype(np.float64)
                       - 0.5 * panel_rgb[:, :, 1].astype(np.float64), 0, 255)
    if ch == "max_rgb":
        return np.max(panel_rgb.astype(np.float64), axis=2)
    return panel_rgb


def _despike_track(xs: list[float], ys_px: list[float], max_jump_px: float) -> tuple[list[float], list[float]]:
    """Reject isolated 1-bin outlier spikes using a 5-point local median reference."""
    if len(ys_px) < 5 or max_jump_px <= 0:
        return xs, ys_px
    arr = np.asarray(ys_px, dtype=np.float64)
    keep = np.ones(len(arr), dtype=bool)
    for i in range(len(arr)):
        lo = max(0, i - 2)
        hi = min(len(arr), i + 3)
        neigh = np.delete(arr[lo:hi], i - lo)
        if len(neigh) >= 2 and abs(arr[i] - float(np.median(neigh))) > max_jump_px:
            keep[i] = False
    return [x for x, k in zip(xs, keep) if k], [y for y, k in zip(ys_px, keep) if k]


def _ray_match_score(sub_f: np.ndarray, rgb: tuple[int, int, int], max_perp: float, min_alpha: float) -> tuple[np.ndarray, np.ndarray]:
    """Match anti-aliased pixels lying along the white->target color ray W + alpha*(T - W).

    Returns (mask, alpha_score) where alpha in [min_alpha, 1.35] measures ink opacity along W->T.
    A 1-px anti-aliased line blended with white stays near zero perpendicular distance from the ray,
    and when a curve sits inside a translucent same-hue ribbon, the core curve has maximum alpha!
    """
    W = np.array([255.0, 255.0, 255.0], dtype=np.float32)
    T = np.array(rgb, dtype=np.float32)
    v = T - W  # vector from white to target
    v_norm2 = float(np.dot(v, v))
    if v_norm2 < 100.0:
        # Very pale target (rare): fall back to Euclidean distance
        d = np.linalg.norm(sub_f - T[None, None, :], axis=2)
        return d <= max_perp, np.clip(1.0 - d / max(max_perp, 1.0), 0.0, 1.0)
    dv = sub_f - W[None, None, :]
    alpha = np.sum(dv * v[None, None, :], axis=2) / v_norm2
    proj = W[None, None, :] + np.clip(alpha, 0.0, 1.35)[:, :, None] * v[None, None, :]
    perp = np.linalg.norm(sub_f - proj, axis=2)
    # Require target chromaticity match for chromatic colors so black text/axes don't steal colored lines
    t_sat = float(max(rgb) - min(rgb))
    pix_sat = np.max(sub_f, axis=2) - np.min(sub_f, axis=2)
    if t_sat > 25.0:
        mask = (perp <= max_perp) & (alpha >= min_alpha) & (alpha <= 1.35) & (pix_sat >= max(10.0, 0.14 * t_sat))
    else:
        # Monochrome / black-gray trace: require low saturation and darkness
        mask = (perp <= max_perp) & (alpha >= max(0.30, min_alpha)) & (pix_sat < 28.0)
    return mask, np.clip(alpha, 0.0, 1.35)


def trace_color_curves(panel_rgb: np.ndarray, spec: CurveTraceSpec) -> dict[str, Any]:
    """Deterministically digitize multi-color, ribbon-core, dashed, dark-bg, or monochrome curves."""
    px0, py0, px1, py1 = spec.plot_box
    sub_u8 = panel_rgb[py0:py1, px0:px1].copy()
    fill_val = 0 if spec.bg_polarity == "dark" else 255
    for ex0, ey0, ex1, ey1 in spec.exclude_boxes:
        sub_u8[max(0, ey0):ey1, max(0, ex0):ex1, :] = fill_val
    sub = sub_u8.astype(np.int16)
    sub_f = sub_u8.astype(np.float32)
    h, w = sub.shape[:2]
    x_min, x_max = spec.x_range
    y_min, y_max = spec.y_range
    edges = np.linspace(0, w, spec.n_bins + 1).astype(int)

    mode = spec.mode
    if mode == "auto":
        if spec.bg_polarity == "dark":
            mode = "dark_bg"
        elif len(spec.traces) == 1 and max(next(iter(spec.traces.values()))) - min(next(iter(spec.traces.values()))) <= 25:
            mode = "monochrome"
        else:
            mode = "nearest_ray"

    out: dict[str, Any] = {}

    if mode == "ribbon_dual_rb":
        # Specialized exact core-ridge extractor for red + blue (solid or dashed) curves with overlapping translucent SD ribbons.
        # Both pure red, pure blue, and overlapping dark purple sharply depress the green channel (G << max(R, B)),
        # while pale translucent ribbons keep high green (G > 165).
        R = sub_f[:, :, 0]
        G = sub_f[:, :, 1]
        B = sub_f[:, :, 2]
        dark_g = np.clip(255.0 - G, 0.0, 255.0)
        red_excess = np.clip(R - G, 0.0, 255.0)
        blue_excess = np.clip(B - G, 0.0, 255.0)
        # Penalize neutral black ticks/axes (where both R and B are very low, so R-G ~ 0 and B-G ~ 0)
        red_score = red_excess * (dark_g / 255.0)
        blue_score = blue_excess * (dark_g / 255.0)
        # Suppress pale ribbon background where dark_g is small and color contrast is weak
        red_mask = (red_excess >= 28.0) & (dark_g >= 55.0) & (red_score >= 16.0)
        blue_mask = (blue_excess >= 24.0) & (dark_g >= 50.0) & (blue_score >= 13.0)

        for name, rgb in spec.traces.items():
            is_blue = rgb[2] > rgb[0]
            sc = blue_score if is_blue else red_score
            mk = blue_mask if is_blue else red_mask
            yb0, yb1 = spec.y_bands.get(name, (0, h))
            xs_raw, ys_px_raw = [], []
            for b in range(spec.n_bins):
                c0, c1 = int(edges[b]), int(edges[b + 1])
                if c1 <= c0:
                    continue
                col_mk = mk[yb0:yb1, c0:c1]
                if not np.any(col_mk):
                    continue
                col_sc = np.where(col_mk, sc[yb0:yb1, c0:c1], 0.0)
                row_sc = col_sc.max(axis=1)
                peak_s = float(row_sc.max())
                if peak_s <= 0:
                    continue
                # Weighted centroid of top-80% ridge core locks straight onto the 1-2 px mean line inside any ribbon
                top_rows = np.where(row_sc >= 0.78 * peak_s)[0]
                wts = row_sc[top_rows]
                cy = float(yb0 + np.sum(top_rows * wts) / max(float(np.sum(wts)), 1e-6))
                xv = x_min + ((c0 + c1) / 2.0 / max(w, 1)) * (x_max - x_min)
                xs_raw.append(round(xv, 3))
                ys_px_raw.append(cy)
            xs_clean, ys_px_clean = _despike_track(xs_raw, ys_px_raw, spec.smooth_jump_px)
            ys_val = [round(y_max - (py / max(h, 1)) * (y_max - y_min), 4) for py in ys_px_clean]
            peak_x, peak_y = (None, None)
            if ys_val:
                idx = int(np.argmax(ys_val))
                peak_x, peak_y = xs_clean[idx], ys_val[idx]
            out[name] = {"x": xs_clean, "y": ys_val, "peak_x": peak_x, "peak_y": peak_y,
                         "x_unit": spec.x_unit, "y_unit": spec.y_unit}
        return out

    if mode == "dark_bg":
        for name, rgb in spec.traces.items():
            lum = np.max(sub, axis=2)
            target = np.array(rgb, dtype=np.int16)[None, None, :]
            dist = np.max(np.abs(sub - target), axis=2)
            if rgb[1] > rgb[0] + 60:
                mask = (sub[:, :, 1] - sub[:, :, 0] > 35) & (sub[:, :, 1] > 60)
                score = (sub[:, :, 1] - sub[:, :, 0]).astype(np.float32)
            elif rgb[0] > rgb[1] + 60 and rgb[2] > 60:
                mask = (sub[:, :, 0] - sub[:, :, 1] > 35) & (sub[:, :, 0] > 60)
                score = (sub[:, :, 0] - sub[:, :, 1]).astype(np.float32)
            else:
                mask = (dist <= spec.color_tol) & (lum > 55)
                score = lum.astype(np.float32)
            xs_raw, ys_px_raw = [], []
            for b in range(spec.n_bins):
                c0, c1 = int(edges[b]), int(edges[b + 1])
                if c1 <= c0:
                    continue
                ym, xm = np.where(mask[:, c0:c1])
                if len(ym) >= 1:
                    wts = score[ym, c0 + xm]
                    # If a sharp spike spans > 10 px vertically in this bin, track its peak apex (min y) rather than averaging the vertical legs
                    if int(ym.max()) - int(ym.min()) > 10:
                        y_apex = int(ym.min())
                        sel = ym <= y_apex + 3
                        cy = float(np.sum(ym[sel] * wts[sel]) / max(float(np.sum(wts[sel])), 1e-6))
                    else:
                        cy = float(np.sum(ym * wts) / max(float(np.sum(wts)), 1e-6))
                    xv = x_min + ((c0 + c1) / 2.0 / max(w, 1)) * (x_max - x_min)
                    xs_raw.append(round(xv, 3))
                    ys_px_raw.append(cy)
            xs_clean, ys_px_clean = _despike_track(xs_raw, ys_px_raw, spec.smooth_jump_px)
            ys_val = [round(y_max - (py / max(h, 1)) * (y_max - y_min), 4) for py in ys_px_clean]
            peak_x, peak_y = (None, None)
            if ys_val:
                idx = int(np.argmax(ys_val))
                peak_x, peak_y = xs_clean[idx], ys_val[idx]
            out[name] = {"x": xs_clean, "y": ys_val, "peak_x": peak_x, "peak_y": peak_y,
                         "x_unit": spec.x_unit, "y_unit": spec.y_unit}
        return out

    if mode == "monochrome":
        gray = np.mean(sub_f, axis=2)
        sat = np.max(sub_f, axis=2) - np.min(sub_f, axis=2)
        dark = np.clip(255.0 - gray, 0.0, 255.0)
        mask_all = (dark >= 70.0) & (sat < 35.0)
        for name in spec.traces:
            yb0, yb1 = spec.y_bands.get(name, (0, h))
            xs_raw, ys_px_raw = [], []
            for b in range(spec.n_bins):
                c0, c1 = int(edges[b]), int(edges[b + 1])
                if c1 <= c0:
                    continue
                cm = mask_all[yb0:yb1, c0:c1]
                if not np.any(cm):
                    continue
                cd = np.where(cm, dark[yb0:yb1, c0:c1], 0.0)
                rmax = cd.max(axis=1)
                pk = float(rmax.max())
                top_r = np.where(rmax >= 0.72 * pk)[0]
                wts = rmax[top_r]
                cy = float(yb0 + np.sum(top_r * wts) / max(float(np.sum(wts)), 1e-6))
                xv = x_min + ((c0 + c1) / 2.0 / max(w, 1)) * (x_max - x_min)
                xs_raw.append(round(xv, 3))
                ys_px_raw.append(cy)
            xs_clean, ys_px_clean = _despike_track(xs_raw, ys_px_raw, spec.smooth_jump_px)
            ys_val = [round(y_max - (py / max(h, 1)) * (y_max - y_min), 4) for py in ys_px_clean]
            peak_x, peak_y = (None, None)
            if ys_val:
                idx = int(np.argmax(ys_val))
                peak_x, peak_y = xs_clean[idx], ys_val[idx]
            out[name] = {"x": xs_clean, "y": ys_val, "peak_x": peak_x, "peak_y": peak_y,
                         "x_unit": spec.x_unit, "y_unit": spec.y_unit}
        return out

    # Default upgraded multi-curve mode: nearest_ray (white->target color ray projection + optional ribbon-core ridge selection)
    names = list(spec.traces.keys())
    per_trace_mask: dict[str, np.ndarray] = {}
    per_trace_alpha: dict[str, np.ndarray] = {}
    per_trace_perp: dict[str, np.ndarray] = {}

    W = np.array([255.0, 255.0, 255.0], dtype=np.float32)
    for name, rgb in spec.traces.items():
        mk, al = _ray_match_score(sub_f, rgb, spec.max_ray_dist, spec.min_alpha)
        if name in spec.y_bands:
            yb0, yb1 = spec.y_bands[name]
            band_mk = np.zeros_like(mk)
            band_mk[max(0, yb0):min(h, yb1), :] = True
            mk = mk & band_mk
        T = np.array(rgb, dtype=np.float32)
        v = T - W
        proj = W[None, None, :] + al[:, :, None] * v[None, None, :]
        perp = np.linalg.norm(sub_f - proj, axis=2)
        per_trace_mask[name] = mk
        per_trace_alpha[name] = al
        per_trace_perp[name] = perp

    # When multiple traces exist, assign each pixel to its closest matching ray (winner-take-all on perp distance)
    if len(names) > 1:
        inf_arr = np.full((h, w), 1e6, dtype=np.float32)
        stack_perp = np.stack([np.where(per_trace_mask[nm], per_trace_perp[nm], inf_arr) for nm in names], axis=0)
        best_idx = np.argmin(stack_perp, axis=0)
        best_val = np.min(stack_perp, axis=0)
        for ti, nm in enumerate(names):
            # Keep pixel if it is the closest ray (or within 4 units of best, for curve crossings!)
            per_trace_mask[nm] = per_trace_mask[nm] & ((best_idx == ti) | (per_trace_perp[nm] <= best_val + 4.0))

    for name in names:
        mk = per_trace_mask[name]
        al = per_trace_alpha[name]
        yb0, yb1 = spec.y_bands.get(name, (0, h))
        xs_raw, ys_px_raw = [], []
        for b in range(spec.n_bins):
            c0, c1 = int(edges[b]), int(edges[b + 1])
            if c1 <= c0:
                continue
            cm = mk[yb0:yb1, c0:c1]
            if not np.any(cm):
                continue
            if spec.ribbon_core:
                col_al = np.where(cm, al[yb0:yb1, c0:c1], 0.0)
                row_al = col_al.max(axis=1)
                pk = float(row_al.max())
                top_r = np.where(row_al >= 0.80 * pk)[0]
                wts = row_al[top_r]
                cy = float(yb0 + np.sum(top_r * wts) / max(float(np.sum(wts)), 1e-6))
            else:
                ym, xm = np.where(cm)
                wts = al[yb0 + ym, c0 + xm]
                # Use highest-alpha core if spread across y is large (e.g. near ribbon or touching legend)
                if len(ym) >= 3 and (int(ym.max()) - int(ym.min())) > 14:
                    pk = float(wts.max())
                    sel = wts >= 0.72 * pk
                    ym, wts = ym[sel], wts[sel]
                cy = float(yb0 + np.median(ym))
            xv = x_min + ((c0 + c1) / 2.0 / max(w, 1)) * (x_max - x_min)
            xs_raw.append(round(xv, 3))
            ys_px_raw.append(cy)
        xs_clean, ys_px_clean = _despike_track(xs_raw, ys_px_raw, spec.smooth_jump_px)
        ys_val = [round(y_max - (py / max(h, 1)) * (y_max - y_min), 4) for py in ys_px_clean]
        peak_x, peak_y = (None, None)
        if ys_val:
            idx = int(np.argmax(ys_val))
            peak_x, peak_y = xs_clean[idx], ys_val[idx]
        out[name] = {"x": xs_clean, "y": ys_val, "peak_x": peak_x, "peak_y": peak_y,
                     "x_unit": spec.x_unit, "y_unit": spec.y_unit}
    return out


def _nms_peaks(dist: np.ndarray, min_dist: int, thr: float) -> list[tuple[int, int]]:
    ys, xs = np.where(dist >= thr)
    if not len(ys):
        return []
    order = np.argsort(-dist[ys, xs])
    kept: list[tuple[int, int]] = []
    md2 = min_dist * min_dist
    for idx in order:
        x, y = int(xs[idx]), int(ys[idx])
        if all((x - kx) ** 2 + (y - ky) ** 2 >= md2 for kx, ky in kept):
            kept.append((x, y))
    return kept


def digitize_scatter(panel_rgb: np.ndarray, spec: ScatterDigitizeSpec) -> dict[str, Any]:
    """Digitize 2D scatter plots, 1D beeswarm dotplots, and crosshair errorbar plots into point arrays."""
    px0, py0, px1, py1 = spec.plot_box
    sub = panel_rgb[py0:py1, px0:px1].copy().astype(np.int16)
    for ex0, ey0, ex1, ey1 in spec.exclude_boxes:
        sub[max(0, ey0):ey1, max(0, ex0):ex1, :] = 255
    h, w = sub.shape[:2]
    x_min, x_max = spec.x_range
    y_min, y_max = spec.y_range
    out = {}

    for gname, gspec in spec.groups.items():
        gx0, gx1 = gspec.x_span if gspec.x_span is not None else (0, w)
        gy0, gy1 = gspec.y_span if gspec.y_span is not None else (0, h)
        gx0, gx1 = max(0, gx0), min(w, gx1)
        gy0, gy1 = max(0, gy0), min(h, gy1)
        band = sub[gy0:gy1, gx0:gx1]
        if spec.mode == "beeswarm_1d":
            dark = np.max(band, axis=2) < 95
            red = (band[:, :, 0] - band[:, :, 1] > 80) & (band[:, :, 0] > 150)
            # Heal thin vertical red mean±SD bars that slice through the center of black dots
            closed = cv2.morphologyEx(dark.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((1, 7), np.uint8)) > 0
            healed = dark | (closed & red)
            dist = distance_transform_edt(healed)
            pts_px = _nms_peaks(dist, min_dist=spec.min_dist_px, thr=spec.disc_thr_px)
            ry, _ = np.where(red)
            red_mean, red_sd = None, None
            if len(ry) > 4:
                hi_v = y_max - (float(gy0 + ry.min()) / max(h, 1)) * (y_max - y_min)
                lo_v = y_max - (float(gy0 + ry.max()) / max(h, 1)) * (y_max - y_min)
                red_mean = round(0.5 * (hi_v + lo_v), 5)
                red_sd = round(0.5 * abs(hi_v - lo_v), 5)
            xs_v = [round(gx0 + x, 1) for x, _ in pts_px]
            ys_v = [round(y_max - ((gy0 + y) / max(h, 1)) * (y_max - y_min), 5) for _, y in pts_px]
            order = np.argsort(ys_v)
            xs_v = [xs_v[i] for i in order]
            ys_v = [ys_v[i] for i in order]
            out[gname] = {
                "n": len(ys_v),
                "x": xs_v,
                "y": ys_v,
                "mean": round(float(np.mean(ys_v)), 5) if ys_v else red_mean,
                "sd": round(float(np.std(ys_v, ddof=1)), 5) if len(ys_v) > 1 else red_sd,
                "overlay_mean": red_mean,
                "overlay_sd": red_sd,
                "x_unit": spec.x_unit or "category_px",
                "y_unit": spec.y_unit,
            }
        elif spec.mode == "crosshair_errorbars":
            if gspec.rgb is not None:
                tgt = np.array(gspec.rgb, dtype=np.int16)[None, None, :]
                d = np.max(np.abs(band - tgt), axis=2)
                sat = np.max(band, axis=2) - np.min(band, axis=2)
                mask = (d <= gspec.tol) & (sat >= 16)
            else:
                mask = np.mean(band, axis=2) < 160
            my, mx = np.where(mask)
            if len(my) >= 5:
                # Horizontal bar row = row with maximum horizontal span; vertical bar col = col with maximum vertical span
                row_counts = np.bincount(my)
                cy_rel = int(np.argmax(row_counts))
                col_counts = np.bincount(mx)
                cx_rel = int(np.argmax(col_counts))
                hx = mx[np.abs(my - cy_rel) <= 2]
                vy = my[np.abs(mx - cx_rel) <= 2]
                x_lo_px = gx0 + (int(hx.min()) if len(hx) else cx_rel)
                x_hi_px = gx0 + (int(hx.max()) if len(hx) else cx_rel)
                y_hi_px = gy0 + (int(vy.min()) if len(vy) else cy_rel)
                y_lo_px = gy0 + (int(vy.max()) if len(vy) else cy_rel)
                cx_px = 0.5 * (x_lo_px + x_hi_px)
                cy_px = 0.5 * (y_lo_px + y_hi_px)
                xv = round(x_min + (cx_px / max(w, 1)) * (x_max - x_min), 3)
                yv = round(y_max - (cy_px / max(h, 1)) * (y_max - y_min), 4)
                x_lo = round(x_min + (x_lo_px / max(w, 1)) * (x_max - x_min), 3)
                x_hi = round(x_min + (x_hi_px / max(w, 1)) * (x_max - x_min), 3)
                y_lo = round(max(y_min, y_max - (y_lo_px / max(h, 1)) * (y_max - y_min)), 4)
                y_hi = round(y_max - (y_hi_px / max(h, 1)) * (y_max - y_min), 4)
                out[gname] = {
                    "n": 1, "x": [xv], "y": [yv],
                    "x_interval": [x_lo, x_hi], "y_interval": [y_lo, y_hi],
                    "x_sd": round(0.5 * (x_hi - x_lo), 3), "y_sd": round(0.5 * (y_hi - y_lo), 4),
                    "x_unit": spec.x_unit, "y_unit": spec.y_unit,
                }
            else:
                out[gname] = {"n": 0, "x": [], "y": [], "x_unit": spec.x_unit, "y_unit": spec.y_unit}
        else:
            if gspec.rgb is not None:
                tgt = np.array(gspec.rgb, dtype=np.int16)[None, None, :]
                d = np.max(np.abs(band - tgt), axis=2)
                sat = np.max(band, axis=2) - np.min(band, axis=2)
                mask = (d <= gspec.tol) & (sat >= 20 if max(gspec.rgb) - min(gspec.rgb) > 20 else np.mean(band, axis=2) < 210)
            else:
                sat = np.max(band, axis=2) - np.min(band, axis=2)
                mask = (sat < 22) & (np.mean(band, axis=2) < 150)
            if spec.use_edt or spec.disc_thr_px > 5.0:
                pts_px = _nms_peaks(distance_transform_edt(mask), min_dist=spec.min_dist_px, thr=spec.disc_thr_px)
                bs = [{"x": float(px), "y": float(py)} for px, py in pts_px]
            else:
                bs = blobs(mask, min_area=3, max_area=950)
            xs_v, ys_v = [], []
            for b in bs:
                cx_p = gx0 + b["x"]
                cy_p = gy0 + b["y"]
                xv = x_min + (cx_p / max(w, 1)) * (x_max - x_min)
                yv = y_max - (cy_p / max(h, 1)) * (y_max - y_min)
                xs_v.append(round(xv, 4))
                ys_v.append(round(yv, 4))
            order = np.argsort(xs_v)
            xs_v = [xs_v[i] for i in order]
            ys_v = [ys_v[i] for i in order]
            out[gname] = {
                "n": len(ys_v),
                "x": xs_v,
                "y": ys_v,
                "mean_x": round(float(np.mean(xs_v)), 4) if xs_v else None,
                "mean_y": round(float(np.mean(ys_v)), 4) if ys_v else None,
                "x_unit": spec.x_unit,
                "y_unit": spec.y_unit,
            }
    return out


def digitize_boxplots(panel_rgb: np.ndarray, spec: BoxplotDigitizeSpec) -> dict[str, Any]:
    """Digitize box-and-whisker or violin+boxplot plots into {median, q1, q3, whisker_lo, whisker_hi}."""
    px0, py0, px1, py1 = spec.plot_box
    sub = panel_rgb[py0:py1, px0:px1].astype(np.float64)
    h, w = sub.shape[:2]
    y_min, y_max = spec.y_range
    mean_rgb = np.mean(sub, axis=2)
    sat = np.max(sub, axis=2) - np.min(sub, axis=2)
    ink = 1.0 - mean_rgb / 255.0  # 0 white, ~1 black

    def y_val(r: float) -> float:
        return round(y_max - (r / max(h, 1)) * (y_max - y_min), 4)

    out = {}
    for gname, gspec in spec.groups.items():
        c = gspec.x_center
        hw = gspec.half_width

        if spec.style == "white_box":
            # Finet ggplot2 violins: colored/black violin body with a bright white narrow IQR box split by a dark median bar
            center_strip = mean_rgb[:, max(0, c - 3):min(w, c + 4)].mean(axis=1)
            flank_l = mean_rgb[:, max(0, c - hw - 18):max(1, c - hw - 4)].mean(axis=1)
            flank_r = mean_rgb[:, min(w - 1, c + hw + 4):min(w, c + hw + 18)].mean(axis=1)
            in_violin = (flank_l < 235) & (flank_r < 235)
            # White IQR box rows sit inside the violin body (center bright white > 230)
            white_in_violin = in_violin & (center_strip > 225)
            # Find largest contiguous cluster (allowing a 1-6 px dark median gap inside the white box)
            w_rows = np.where(white_in_violin)[0]
            if len(w_rows) >= 6:
                # Group white segments separated by <= 14 px (the black median bar!)
                segs = []
                s0 = w_rows[0]
                prev = w_rows[0]
                for r in w_rows[1:]:
                    if r - prev > 18:
                        segs.append((s0, prev))
                        s0 = r
                    prev = r
                segs.append((s0, prev))
                r_top, r_bot = max(segs, key=lambda ab: ab[1] - ab[0])
                i0, i1 = int(r_top), int(r_bot)
                # Median = darkest horizontal bar inside [i0, i1]
                interior = center_strip[i0:i1 + 1]
                r_med = float(i0 + int(np.argmin(interior)))
                # Whiskers / violin body extent along center +/- 20 px
                body_rows = np.where(mean_rgb[:, max(0, c - 2):min(w, c + 3)].mean(axis=1) < 235)[0]
                # Restrict to connected violin mass around [i0, i1]
                r_whi, r_wlo = float(i0), float(i1)
                if len(body_rows):
                    # Walk up from i0 and down from i1 while violin/whisker ink stays present
                    up = i0
                    gap = 0
                    for r in range(i0, -1, -1):
                        if mean_rgb[r, max(0, c - 4):min(w, c + 5)].min() < 220:
                            up = r
                            gap = 0
                        else:
                            gap += 1
                            if gap > 14:
                                break
                    dn = i1
                    gap = 0
                    for r in range(i1, h):
                        if mean_rgb[r, max(0, c - 4):min(w, c + 5)].min() < 220:
                            dn = r
                            gap = 0
                        else:
                            gap += 1
                            if gap > 14:
                                break
                    r_whi, r_wlo = float(up), float(dn)
                out[gname] = {
                    "median": y_val(r_med),
                    "q1": y_val(float(i1)),
                    "q3": y_val(float(i0)),
                    "whisker_lo": y_val(r_wlo),
                    "whisker_hi": y_val(r_whi),
                    "y_unit": spec.y_unit,
                }
            else:
                out[gname] = {"median": None, "q1": None, "q3": None, "whisker_lo": None, "whisker_hi": None, "y_unit": spec.y_unit}
            continue

        if spec.style == "gray_box_white_dot":
            # Totz Fig 3F/G violins: colored pastel violin, central solid gray IQR box (~22px wide), bright white median dot
            bw = min(hw, 7)
            strip_m = mean_rgb[4:h - 4, max(0, c - bw):min(w, c + bw + 1)]
            strip_s = sat[4:h - 4, max(0, c - bw):min(w, c + bw + 1)]
            gray_px = (strip_s < 28) & (strip_m >= 95) & (strip_m <= 182)
            # Solid gray box rows fill >= 52% of the 15px core strip (rejects thin 2px vertical stems and top/bottom ticks)
            gray_rows = np.where(gray_px.mean(axis=1) >= 0.52)[0] + 4
            if len(gray_rows) >= 6:
                # Group segments separated by <= 32 px (to bridge across the circular bright white median dot!)
                segs = []
                s0 = int(gray_rows[0])
                prev = int(gray_rows[0])
                for r in gray_rows[1:]:
                    r = int(r)
                    if r - prev > 32:
                        segs.append((s0, prev))
                        s0 = r
                    prev = r
                segs.append((s0, prev))
                r_top, r_bot = max(segs, key=lambda ab: ab[1] - ab[0])
                # White median circle inside [r_top, r_bot] along center +/- 3 px
                c_mean = mean_rgb[:, max(0, c - 3):min(w, c + 4)].mean(axis=1)
                inner = c_mean[r_top:r_bot + 1]
                r_med = float(r_top + int(np.argmax(inner)))
                # Walk violin extent up from r_top and down from r_bot (stop at gap > 14 px or 4 px inside border)
                up = r_top
                gap = 0
                for r in range(r_top, 3, -1):
                    if mean_rgb[r, max(0, c - 4):min(w, c + 5)].min() < 232:
                        up = r
                        gap = 0
                    else:
                        gap += 1
                        if gap > 14:
                            break
                dn = r_bot
                gap = 0
                for r in range(r_bot, h - 4):
                    if mean_rgb[r, max(0, c - 4):min(w, c + 5)].min() < 232:
                        dn = r
                        gap = 0
                    else:
                        gap += 1
                        if gap > 14:
                            break
                out[gname] = {
                    "median": y_val(r_med),
                    "q1": y_val(float(r_bot)),
                    "q3": y_val(float(r_top)),
                    "whisker_lo": y_val(float(dn)),
                    "whisker_hi": y_val(float(up)),
                    "y_unit": spec.y_unit,
                }
            else:
                out[gname] = {"median": None, "q1": None, "q3": None, "whisker_lo": None, "whisker_hi": None, "y_unit": spec.y_unit}
            continue

        if spec.style == "shaded_notch":
            # ggplot2 filled notched boxplots (e.g. Lloyd F2/J,K,L): solid gray or light-blue filled box + dark median bar + vertical whiskers
            x0b = max(0, c - hw)
            x1b = min(w, c + hw + 1)
            strip = sub[:, x0b:x1b, :]
            if gspec.fill_rgb is not None:
                frgb = np.array(gspec.fill_rgb, dtype=np.float64)[None, None, :]
                shaded = np.max(np.abs(strip - frgb), axis=2) <= 45.0
            else:
                shaded = np.mean(strip, axis=2) < 220.0
            # Box rows have >= 45% of strip columns filled (notches narrow the center slightly, so 45% keeps the notch intact while rejecting stray dots/text)
            row_fill = shaded.mean(axis=1)
            box_rows = np.where(row_fill >= 0.45)[0]
            if len(box_rows) >= 6:
                # Pick largest contiguous block (allowing small 1-3 px median line gap)
                segs = []
                s0 = int(box_rows[0])
                prev = int(box_rows[0])
                for r in box_rows[1:]:
                    r = int(r)
                    if r - prev > 6:
                        segs.append((s0, prev))
                        s0 = r
                    prev = r
                segs.append((s0, prev))
                r_top, r_bot = max(segs, key=lambda ab: ab[1] - ab[0])
                # Median = darkest horizontal bar across the central notch [c - hw//2, c + hw//2] inside [r_top+2, r_bot-2]
                nhw = max(3, hw // 2)
                inner_lum = mean_rgb[r_top + 2:max(r_top + 3, r_bot - 1), max(0, c - nhw):min(w, c + nhw + 1)].mean(axis=1)
                r_med = float(r_top + 2 + int(np.argmin(inner_lum)))
                # Walk vertical whisker stem up from r_top and down from r_bot at center +/- 2 px
                up = r_top
                gap = 0
                for r in range(r_top - 1, -1, -1):
                    # Stop if horizontal bracket (wide dark line across full width) or gap > 4 px
                    if mean_rgb[r, max(0, c - 2):min(w, c + 3)].min() < 205:
                        up = r
                        gap = 0
                    else:
                        gap += 1
                        if gap > 4:
                            break
                dn = r_bot
                gap = 0
                for r in range(r_bot + 1, h):
                    if mean_rgb[r, max(0, c - 2):min(w, c + 3)].min() < 205:
                        dn = r
                        gap = 0
                    else:
                        gap += 1
                        if gap > 4:
                            break
                out[gname] = {
                    "median": y_val(r_med),
                    "q1": y_val(float(r_bot)),
                    "q3": y_val(float(r_top)),
                    "whisker_lo": y_val(float(dn)),
                    "whisker_hi": y_val(float(up)),
                    "y_unit": spec.y_unit,
                }
            else:
                out[gname] = {"median": None, "q1": None, "q3": None, "whisker_lo": None, "whisker_hi": None, "y_unit": spec.y_unit}
            continue

        # Default dark_ink style
        bg_cols = [k for k in range(max(0, c - hw - 9), min(w, c + hw + 10)) if k < c - hw - 2 or k > c + hw + 2]
        bg_prof = ink[:, bg_cols].mean(axis=1) if bg_cols else np.zeros(h)

        # Vertical box walls at c - hw and c + hw
        lw = ink[:, max(0, c - hw - 1):min(w, c - hw + 2)].max(axis=1)
        rw = ink[:, max(0, c + hw - 1):min(w, c + hw + 2)].max(axis=1)
        wall_rows = np.where((lw > 0.25) & (rw > 0.25) & (bg_prof < 0.45))[0]

        inner_w = max(2, hw - 2)
        net_h = np.clip(ink[:, max(0, c - inner_w):min(w, c + inner_w + 1)].mean(axis=1) - 0.85 * bg_prof, 0, 1)

        if len(wall_rows) >= 2:
            r_top = float(wall_rows.min())
            r_bot = float(wall_rows.max())
            i0, i1 = int(r_top), int(r_bot)
            if i1 > i0 + 2:
                interior = net_h[i0 + 1:i1]
                r_med = float(i0 + 1 + int(np.argmax(interior)))
            else:
                r_med = 0.5 * (r_top + r_bot)
            c_prof = np.clip(ink[:, max(0, c - 2):min(w, c + 3)].max(axis=1) - 0.85 * bg_prof, 0, 1)
            w_all = np.where(c_prof > 0.22)[0]
            r_whi = float(w_all.min()) if len(w_all) else r_top
            r_wlo = float(w_all.max()) if len(w_all) else r_bot
            out[gname] = {
                "median": y_val(r_med),
                "q1": y_val(r_bot),
                "q3": y_val(r_top),
                "whisker_lo": y_val(r_wlo),
                "whisker_hi": y_val(r_whi),
                "y_unit": spec.y_unit,
            }
        else:
            out[gname] = {"median": None, "q1": None, "q3": None, "whisker_lo": None, "whisker_hi": None, "y_unit": spec.y_unit}
    return out


_EXTRACTOR_CACHE: dict[Path, Any] = {}


def _run_custom_extractor(
    extractor_spec: str,
    records_dir: Path,
    paper: str,
    fig_id: str,
    panel_id: str,
    crop_rgb: np.ndarray,
    full_rgb: np.ndarray,
    bbox: tuple[int, int, int, int],
) -> dict[str, Any]:
    """Load and execute a bespoke per-figure Python extractor in `records/<paper>/extractors/`."""
    if ":" in extractor_spec:
        rel_path, fn_name = extractor_spec.split(":", 1)
    else:
        rel_path, fn_name = extractor_spec, "extract"
    script_path = (records_dir / paper / rel_path).resolve()
    if not script_path.is_file():
        raise FileNotFoundError(f"Custom extractor not found: {script_path}")
    mod = _EXTRACTOR_CACHE.get(script_path)
    if mod is None:
        spec = importlib.util.spec_from_file_location(f"ll_ext_{paper}_{script_path.stem}", str(script_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load extractor module: {script_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _EXTRACTOR_CACHE[script_path] = mod
    fn = getattr(mod, fn_name)
    return fn(crop_rgb=crop_rgb, panel_id=panel_id, fig_id=fig_id, full_rgb=full_rgb, bbox=bbox)


def compute_panel_object(
    paper: str,
    fig_id: str,
    fig: FigureManifest,
    panel_id: str,
    pspec: PanelSpec,
    default_ctx: dict[str, str],
    paper_dir: Path,
    records_dir: Path = RECORDS_DIR,
) -> tuple[dict[str, Any], np.ndarray | None, list[dict], list[str]]:
    """Resolve context, crop pixels, calibrate scale bar, run all extractors, and emit flat series rows."""
    probs: list[str] = []
    series_rows: list[dict] = []
    img_path = paper_dir / fig.file
    if not img_path.is_file():
        return {}, None, [], [f"{fig_id}.{panel_id}: image missing {fig.file}"]
    bgr = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
    if bgr is None:
        return {}, None, [], [f"{fig_id}.{panel_id}: failed to decode {fig.file}"]
    rgb = bgr[:, :, ::-1]
    H, W = rgb.shape[:2]
    x0, y0, x1, y1 = pspec.bbox
    if not (0 <= x0 < x1 <= W and 0 <= y0 < y1 <= H):
        probs.append(f"{fig_id}.{panel_id}: bbox {pspec.bbox} outside image {W}x{H}")
        return {}, None, [], probs
    crop = rgb[y0:y1, x0:x1].copy()

    ctx = {**default_ctx, **fig.context, **pspec.context}
    computed: dict[str, Any] = dict(pspec.extracted_data)
    cal: ScaleBarCal | None = None
    full_id = f"{paper}/{fig_id}/{panel_id}"

    sb_overlay: dict[str, Any] | None = None
    if pspec.scale_bar is not None:
        sb = pspec.scale_bar
        try:
            if sb.search_box is not None:
                cal = detect_scale_bar(crop, sb.search_box, sb.um, polarity=sb.polarity)
            elif sb.px is not None and sb.px > 0:
                cal = ScaleBarCal(px_length=float(sb.px), physical_um=float(sb.um), px_unc=1.0)
            if cal is not None:
                computed["scale_bar_px"] = round(cal.px_length, 2)
                computed["um_per_px"] = round(cal.um_per_px, 5)
                computed["fov_um"] = [round(crop.shape[1] * cal.um_per_px, 2), round(crop.shape[0] * cal.um_per_px, 2)]
                if cal.bbox is not None:
                    bx, by, bw, bh = cal.bbox
                    sb_overlay = {"x0": bx, "y0": by, "x1": bx + bw, "y1": by + bh, "um": float(sb.um), "um_per_px": round(cal.um_per_px, 6)}
                elif sb.search_box is not None:
                    sb_overlay = {"x0": sb.search_box[0], "y0": sb.search_box[1], "x1": sb.search_box[2], "y1": sb.search_box[3], "um": float(sb.um), "um_per_px": round(cal.um_per_px, 6)}
        except Exception as e:
            if sb.px is not None and sb.px > 0:
                cal = ScaleBarCal(px_length=float(sb.px), physical_um=float(sb.um), px_unc=1.5)
                computed["scale_bar_px"] = round(cal.px_length, 2)
                computed["um_per_px"] = round(cal.um_per_px, 5)
                computed["fov_um"] = [round(crop.shape[1] * cal.um_per_px, 2), round(crop.shape[0] * cal.um_per_px, 2)]
                if sb.search_box is not None:
                    sb_overlay = {"x0": sb.search_box[0], "y0": sb.search_box[1], "x1": sb.search_box[2], "y1": sb.search_box[3], "um": float(sb.um), "um_per_px": round(cal.um_per_px, 6)}
            else:
                probs.append(f"{fig_id}.{panel_id}: scale bar detection failed: {e}")

    if pspec.periodic_spec is not None:
        if cal is None:
            probs.append(f"{fig_id}.{panel_id}: periodic_spec requires scale_bar")
        else:
            ps = pspec.periodic_spec
            ch_img = _extract_channel(crop, ps.channel)
            try:
                fft_r = measure_periodic_fft_verified(
                    ch_img, cal, ps.roi,
                    spacing_range_um=ps.spacing_range_um,
                    wavevector_angle_deg=ps.wavevector_angle_deg,
                )
                tr_r = measure_transects_with_coords(
                    ch_img, cal, ps.roi,
                    fft_r["wavevector_deg"], fft_r["spacing_px"], n_transects=10,
                )
                computed["periodic_fft_um"] = round(fft_r["spacing_um"], 4)
                computed["periodic_fft_interval_um"] = [round(fft_r["lo_um"], 4), round(fft_r["hi_um"], 4)]
                computed["periodic_snr"] = round(fft_r["peak_snr"], 1)
                computed["wavevector_deg"] = round(fft_r["wavevector_deg"], 1)
                series_rows.append({
                    "panel_id": full_id, "series": "ridge_fft", "kind": "fft_period", "index": 0,
                    "x": "", "y": round(fft_r["spacing_um"], 4),
                    "lo": round(fft_r["lo_um"], 4), "hi": round(fft_r["hi_um"], 4),
                    "x_unit": "", "y_unit": "µm",
                })
                if tr_r["mean_um"] is not None:
                    computed["periodic_transect_um"] = round(tr_r["mean_um"], 4)
                    computed["periodic_transect_sd_um"] = round(tr_r["sd_um"], 4)
                    computed["transect_points_um"] = [round(t["value"], 4) for t in tr_r["transects"]]
                    for idx, t in enumerate(tr_r["transects"]):
                        series_rows.append({
                            "panel_id": full_id, "series": "ridge_transect", "kind": "transect_point", "index": idx,
                            "x": round(t["y_frac"], 3), "y": round(t["value"], 4),
                            "lo": round(t["lo"], 4), "hi": round(t["hi"], 4),
                            "x_unit": "roi_fraction", "y_unit": "µm",
                        })
                hg = check_fft_harmonics(
                    fft_r["spacing_um"],
                    tr_r["mean_um"],
                    fft_r["harmonic_ratio_2f"],
                    fft_r["peak_snr"],
                )
                if hg["status"] == "flagged" and pspec.harmonic_verified:
                    hg["status"] = "verified"
                    hg["verified_note"] = "visually confirmed 1x fundamental grating"
                computed["harmonic_guard"] = hg
                if hg["status"] == "flagged":
                    probs.append(f"{fig_id}.{panel_id}: FFT harmonic guard flagged: {'; '.join(hg['issues'])}")

                crossrib_ov = None
                if ps.measure_crossrib:
                    orth = ((fft_r["wavevector_deg"] + 90.0 + 90.0) % 180.0) - 90.0
                    lo_a, hi_a = orth - 25.0, orth + 25.0
                    if lo_a < -90.0:
                        w_bounds = (lo_a + 180.0, hi_a)
                    elif hi_a > 90.0:
                        w_bounds = (lo_a, hi_a - 180.0)
                    else:
                        w_bounds = (lo_a, hi_a)
                    cr_img = _extract_channel(crop, ps.crossrib_channel) if ps.crossrib_channel else ch_img
                    c_fft = measure_periodic_fft_verified(
                        cr_img, cal, ps.roi,
                        spacing_range_um=ps.crossrib_range_um,
                        wavevector_angle_deg=w_bounds,
                    )
                    computed["crossrib_fft_um"] = round(c_fft["spacing_um"], 4)
                    computed["crossrib_snr"] = round(c_fft["peak_snr"], 1)
                    crossrib_ov = {
                        "period_px": round(float(c_fft["spacing_px"]), 2),
                        "period_um": round(float(c_fft["spacing_um"]), 4),
                        "wavevector_deg": round(float(c_fft["wavevector_deg"]), 1),
                        "phase_shift_px": round(float(c_fft["phase_shift_px"]), 2),
                        "snr": round(float(c_fft["peak_snr"]), 1),
                    }
                    series_rows.append({
                        "panel_id": full_id, "series": "crossrib_fft", "kind": "fft_period", "index": 0,
                        "x": "", "y": round(c_fft["spacing_um"], 4),
                        "lo": round(c_fft["lo_um"], 4), "hi": round(c_fft["hi_um"], 4),
                        "x_unit": "", "y_unit": "µm",
                    })

                computed["overlay_meta"] = {
                    "kind": "microscopy_fft",
                    "scale_bar_px": sb_overlay,
                    "roi_px": [int(v) for v in ps.roi],
                    "grating": {
                        "period_px": round(float(fft_r["spacing_px"]), 2),
                        "period_um": round(float(fft_r["spacing_um"]), 4),
                        "wavevector_deg": round(float(fft_r["wavevector_deg"]), 1),
                        "phase_shift_px": round(float(fft_r["phase_shift_px"]), 2),
                        "snr": round(float(fft_r["peak_snr"]), 1),
                    },
                    "crossrib_grating": crossrib_ov,
                    "transects": [
                        {"p0": t["p0"], "p1": t["p1"], "peaks_px": t["peaks_px"]}
                        for t in tr_r["transects"]
                    ],
                }
            except Exception as e:
                probs.append(f"{fig_id}.{panel_id}: periodic measurement failed: {e}")
    elif sb_overlay is not None:
        # Calibrated micrograph without periodic FFT still emits scale-bar overlay proof!
        computed["overlay_meta"] = {
            "kind": "microscopy_scale",
            "scale_bar_px": sb_overlay,
        }

    def _append_curve_rows(curves: dict[str, Any]) -> None:
        for cname, cdict in curves.items():
            los = cdict.get("lo") or []
            his = cdict.get("hi") or []
            for idx, (xv, yv) in enumerate(zip(cdict["x"], cdict["y"])):
                series_rows.append({
                    "panel_id": full_id, "series": cname, "kind": "curve_point", "index": idx,
                    "x": xv, "y": yv,
                    "lo": los[idx] if idx < len(los) and los[idx] is not None else "",
                    "hi": his[idx] if idx < len(his) and his[idx] is not None else "",
                    "x_unit": cdict["x_unit"], "y_unit": cdict["y_unit"],
                })

    def _append_scatter_rows(sc: dict[str, Any]) -> None:
        for gname, gdict in sc.items():
            yi = gdict.get("y_interval")
            ylos = gdict.get("y_lo") or []
            yhis = gdict.get("y_hi") or []
            for idx, (xv, yv) in enumerate(zip(gdict["x"], gdict["y"])):
                lo_v = ylos[idx] if idx < len(ylos) and ylos[idx] is not None else (yi[0] if yi and idx == 0 else "")
                hi_v = yhis[idx] if idx < len(yhis) and yhis[idx] is not None else (yi[1] if yi and idx == 0 else "")
                series_rows.append({
                    "panel_id": full_id, "series": gname, "kind": "scatter_point", "index": idx,
                    "x": xv, "y": yv, "lo": lo_v, "hi": hi_v,
                    "x_unit": gdict["x_unit"], "y_unit": gdict["y_unit"],
                })

    def _append_boxplot_rows(bp: dict[str, Any]) -> None:
        for idx, (gname, bdict) in enumerate(bp.items()):
            if bdict.get("median") is not None:
                series_rows.append({
                    "panel_id": full_id, "series": gname, "kind": "boxplot_summary", "index": idx,
                    "x": gname, "y": bdict["median"], "lo": bdict["q1"], "hi": bdict["q3"],
                    "x_unit": f"whiskers:[{bdict['whisker_lo']},{bdict['whisker_hi']}]",
                    "y_unit": bdict["y_unit"],
                })

    if pspec.extractor is not None:
        try:
            ext_out = _run_custom_extractor(
                pspec.extractor, records_dir, paper, fig_id, panel_id, crop, rgb, pspec.bbox
            )
            if "curves" in ext_out:
                computed["curves"] = ext_out["curves"]
                _append_curve_rows(ext_out["curves"])
            if "digitized_scatter" in ext_out:
                computed["digitized_scatter"] = ext_out["digitized_scatter"]
                _append_scatter_rows(ext_out["digitized_scatter"])
            if "digitized_boxplots" in ext_out:
                computed["digitized_boxplots"] = ext_out["digitized_boxplots"]
                _append_boxplot_rows(ext_out["digitized_boxplots"])
            if "dotplot_matrix" in ext_out:
                dm = ext_out["dotplot_matrix"]
                computed["dotplot_matrix"] = dm
                for idx, cell in enumerate(dm.get("cells", [])):
                    series_rows.append({
                        "panel_id": full_id, "series": cell["gene"], "kind": "dotplot_cell", "index": idx,
                        "x": cell["cluster"], "y": cell["expr"],
                        "lo": cell["pct"], "hi": "",
                        "x_unit": "cluster", "y_unit": "avg_expr (lo=pct_expressing)",
                    })
            if "overlay_meta" in ext_out:
                computed["overlay_meta"] = ext_out["overlay_meta"]
            if "extracted_data" in ext_out:
                computed.update(ext_out["extracted_data"])
        except Exception as e:
            probs.append(f"{fig_id}.{panel_id}: custom extractor {pspec.extractor} failed: {e}")

    if pspec.curve_spec is not None and "curves" not in computed:
        try:
            curves = trace_color_curves(crop, pspec.curve_spec)
            computed["curves"] = curves
            computed.setdefault("overlay_meta", {
                "plot_box": list(pspec.curve_spec.plot_box),
                "x_range": list(pspec.curve_spec.x_range),
                "y_range": list(pspec.curve_spec.y_range),
                "kind": "curves",
            })
            _append_curve_rows(curves)
        except Exception as e:
            probs.append(f"{fig_id}.{panel_id}: curve digitization failed: {e}")

    if pspec.scatter_spec is not None and "digitized_scatter" not in computed:
        try:
            sc = digitize_scatter(crop, pspec.scatter_spec)
            computed["digitized_scatter"] = sc
            computed.setdefault("overlay_meta", {
                "plot_box": list(pspec.scatter_spec.plot_box),
                "x_range": list(pspec.scatter_spec.x_range),
                "y_range": list(pspec.scatter_spec.y_range),
                "mode": pspec.scatter_spec.mode,
                "kind": "scatter",
            })
            _append_scatter_rows(sc)
        except Exception as e:
            probs.append(f"{fig_id}.{panel_id}: scatter digitization failed: {e}")

    if pspec.boxplot_spec is not None and "digitized_boxplots" not in computed:
        try:
            bp = digitize_boxplots(crop, pspec.boxplot_spec)
            computed["digitized_boxplots"] = bp
            computed.setdefault("overlay_meta", {
                "plot_box": list(pspec.boxplot_spec.plot_box),
                "y_range": list(pspec.boxplot_spec.y_range),
                "groups": [{"name": k, "x_frac": [g.x_center - g.half_width, g.x_center + g.half_width]} for k, g in pspec.boxplot_spec.groups.items()],
                "kind": "boxplots",
            })
            _append_boxplot_rows(bp)
        except Exception as e:
            probs.append(f"{fig_id}.{panel_id}: boxplot digitization failed: {e}")

    # Plot Span Completeness Guard (>= 85% of calibrated x_range unless partial_x_range=True)
    if "curves" in computed and not pspec.partial_x_range and "digitized_scatter" not in computed:
        om_xr = (computed.get("overlay_meta") or {}).get("x_range")
        if om_xr and len(om_xr) == 2 and om_xr[1] > om_xr[0]:
            full_span = float(om_xr[1] - om_xr[0])
            for cname, cdict in computed["curves"].items():
                xs_c = cdict.get("x") or []
                if len(xs_c) < 2:
                    probs.append(f"{fig_id}.{panel_id}.{cname}: curve has < 2 points")
                else:
                    cov = (max(xs_c) - min(xs_c)) / max(full_span, 1e-9)
                    if cov < 0.80:
                        probs.append(f"{fig_id}.{panel_id}.{cname}: curve spans only {cov*100:.1f}% of x-axis (set partial_x_range: true if truncated)")

    obj = {
        "id": full_id,
        "paper": paper,
        "figure_id": fig_id,
        "figure_label": fig.label,
        "panel_id": panel_id,
        "panel_label": pspec.label,
        "title": pspec.title,
        "archetype": pspec.archetype,
        "file": fig.file,
        "bbox": list(pspec.bbox),
        "pixel_size": [int(crop.shape[1]), int(crop.shape[0])],
        "context": ctx,
        "stains_or_markers": list(pspec.stains_or_markers),
        "scale_bar_um": pspec.scale_bar.um if pspec.scale_bar else None,
        "extractor_script": pspec.extractor.split(":", 1)[0] if pspec.extractor else None,
        "data": computed,
        "n_digitized_points": len(series_rows),
        "linked_items": list(pspec.linked_items),
        "linked_claims": list(pspec.linked_claims),
        "linked_resources": list(pspec.linked_resources),
        "caption_quote": fig.caption_anchor.quote,
    }
    return obj, crop, series_rows, probs


def _is_composite_panel(panel_id: str, label: str) -> bool:
    if panel_id.lower() in {"top", "bottom", "left", "right", "ab", "cd", "ef", "ij", "gh"}:
        return True
    if any(ch in label for ch in ("–", "—")) and not any(tok in label.lower() for tok in ("nm", "µm", "um", "°")):
        return True
    if len(panel_id) == 2 and panel_id.isupper() and panel_id not in {"UV", "XZ", "XY", "3D"}:
        return True
    return False


def _build_qa_report(paper: str, pf: PanelsFile, objs: list[dict]) -> dict[str, Any]:
    panels_qa: dict[str, Any] = {}
    n_comp = 0
    for obj in objs:
        pid = obj["id"]
        d = obj.get("data") or {}
        fid, sub_id = obj["figure_id"], obj["panel_id"]
        pspec = pf.figures[fid].panels[sub_id]
        if _is_composite_panel(sub_id, obj["panel_label"]):
            n_comp += 1
        entry: dict[str, Any] = {
            "archetype": obj["archetype"],
            "n_points": obj["n_digitized_points"],
            "method": (f"custom:{obj['extractor_script']}" if obj.get("extractor_script")
                       else ("microscopy_fft" if d.get("periodic_fft_um") is not None
                             else ("microscopy_scale" if d.get("um_per_px") is not None else "crop_only"))),
            "has_overlay": bool(d.get("overlay_meta") or d.get("dotplot_matrix")),
        }
        if d.get("harmonic_guard"):
            hg = d["harmonic_guard"]
            entry["fft_um"] = d.get("periodic_fft_um")
            entry["transect_um"] = d.get("periodic_transect_um")
            entry["fft_transect_delta_pct"] = hg.get("fft_transect_delta_pct")
            entry["harmonic_ratio_2f"] = hg.get("harmonic_ratio_2f")
            entry["harmonic_guard"] = hg.get("status")
            entry["snr"] = hg.get("snr")
            if hg.get("status") == "flagged" and not pspec.harmonic_verified:
                entry["confidence"] = "flagged"
            elif hg.get("status") == "low_snr_verify":
                entry["confidence"] = "low_snr_verified"
            else:
                entry["confidence"] = "verified"
        elif obj["n_digitized_points"] > 0:
            entry["confidence"] = "verified"
        else:
            entry["confidence"] = "crop_verified"
        panels_qa[pid] = entry
    return {
        "paper": paper,
        "n_figures": len(pf.figures),
        "n_atomic_panels": len(objs),
        "composite_panels": n_comp,
        "n_custom_extractors": len({o["extractor_script"] for o in objs if o.get("extractor_script")}),
        "n_fft_panels": sum(1 for o in objs if (o.get("data") or {}).get("periodic_fft_um") is not None),
        "flagged_panels": [k for k, v in panels_qa.items() if v.get("confidence") == "flagged"],
        "panels": panels_qa,
    }


def save_digitized_store(paper: str, objs: list[dict], series_rows: list[dict], records_dir: Path = RECORDS_DIR, qa_report: dict[str, Any] | None = None) -> Path:
    """Persist digitized quantitative series, panel objects, and qa/report.json."""
    out_dir = records_dir / paper / "digitized"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "series.csv"
    cols = ["panel_id", "series", "kind", "index", "x", "y", "lo", "hi", "x_unit", "y_unit"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in series_rows:
            w.writerow(r)
    (out_dir / "panels_extracted.json").write_text(json.dumps(objs, indent=2), encoding="utf-8")
    if qa_report is not None:
        qa_dir = records_dir / paper / "qa"
        qa_dir.mkdir(parents=True, exist_ok=True)
        (qa_dir / "report.json").write_text(json.dumps(qa_report, indent=2), encoding="utf-8")
    return out_dir


def check_panels_gate(
    paper: str,
    records_dir: Path = RECORDS_DIR,
    papers_dir: Path = PAPERS_DIR,
    store: bool = False,
) -> tuple[list[dict], list[str]]:
    pfile = records_dir / paper / "panels.yaml"
    pdir = papers_dir / paper
    if not pfile.is_file():
        return [], [f"{paper}: missing panels.yaml"]
    try:
        pf = PanelsFile.model_validate(yaml.safe_load(pfile.read_text(encoding="utf-8")))
    except Exception as e:
        return [], [f"schema: {e}"]

    probs: list[str] = []
    xml_files = sorted(pdir.glob("*.xml"))
    if xml_files:
        root = ET.parse(str(xml_files[0])).getroot()
        xml_fig_ids = [
            f.attrib.get("id", "")
            for f in root.findall(".//fig")
            if f.attrib.get("id")
            and f.find(".//graphic") is not None
            and f.find("caption") is not None
            and f.attrib.get("specific-use") != "child-fig"
            and "figsupp" not in f.attrib.get("id", "")
            and not f.attrib.get("id", "").startswith("undfig")
        ]
        covered_xml_ids = {f.xml_id for f in pf.figures.values() if f.xml_id}
        missing = [x for x in xml_fig_ids if x not in covered_xml_ids]
        if missing:
            probs.append(f"{paper}: XML figures missing from panels.yaml (100% figure rule): {missing}")

    objs: list[dict] = []
    all_series: list[dict] = []
    for fid, fig in pf.figures.items():
        check_id(fid, "figure")
        if len(fig.caption_anchor.quote.split()) > 30:
            probs.append(f"{fid}: caption_anchor > 30 words")
        elif find_quote(fig.caption_anchor.quote, pdir) is None:
            probs.append(f"{fid}: caption_anchor quote not found: {fig.caption_anchor.quote!r}")
        if not fig.panels:
            probs.append(f"{fid}: has no sub-panels")
        for pid, pspec in fig.panels.items():
            check_id(pid, "panel")
            # Atomic 1-Letter Panel Guard (Shift #1)
            if _is_composite_panel(pid, pspec.label) and not pspec.composite_justification:
                probs.append(f"{fid}.{pid}: composite panel ({pspec.label!r}) rejected by atomic 1-letter guard; split into individual panels or set composite_justification")
            obj, _, srows, p_errs = compute_panel_object(
                paper, fid, fig, pid, pspec, pf.default_context, pdir, records_dir=records_dir
            )
            probs.extend(p_errs)
            if obj:
                objs.append(obj)
                all_series.extend(srows)

    rfile = records_dir / paper / "resources.yaml"
    if rfile.is_file():
        try:
            rf = ResourcesFile.model_validate(yaml.safe_load(rfile.read_text(encoding="utf-8")))
            for res in rf.resources:
                for lf in res.local_files:
                    if not (pdir / "associated" / lf).is_file():
                        probs.append(f"resources.{res.id}: local file missing associated/{lf}")
        except Exception as e:
            probs.append(f"resources.yaml schema: {e}")

    qa_report = _build_qa_report(paper, pf, objs)
    if store and objs:
        save_digitized_store(paper, objs, all_series, records_dir=records_dir, qa_report=qa_report)
    elif not store and not probs:
        stored_json = records_dir / paper / "digitized" / "panels_extracted.json"
        if not stored_json.is_file():
            probs.append(f"{paper}: digitized/panels_extracted.json missing (run gate panels --apply)")
    return objs, probs
