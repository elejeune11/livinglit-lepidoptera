"""Unified visual QA overlay contact-sheet renderer for livinglit-lepidoptera.

Renders three verification contact sheets straight from `panels.yaml` + `digitized/panels_extracted.json`
using the exact same `overlay_meta` geometric contract rendered live in the browser:
1. `render_bbox_sheets(paper, out_dir)`  — Full-figure bounding-box contact sheets (atomic 1-letter proof)
2. `render_plot_overlay_sheet(paper, out_path)` — Plot pixel overlays (curves, ±SD/CI, errorbars, boxplots, dotplots)
3. `render_fft_overlay_sheet(paper, out_path)`  — Microscopy scale-bar + ROI + phase-aligned FFT grating + transects
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

from livinglit_lepidoptera import PAPERS_DIR, RECORDS_DIR

# Vivid high-contrast BGR palette for OpenCV overlays
OVERLAY_BGR = [
    (64, 230, 0),     # bright green
    (166, 42, 255),   # vivid magenta
    (255, 212, 0),    # bright cyan
    (0, 149, 255),    # vivid orange
    (0, 230, 255),    # yellow
    (255, 77, 184),   # purple
    (77, 77, 255),    # red
    (238, 211, 34),   # sky
]


def _make_grid(tiles: list[np.ndarray], cols: int = 3, pad: int = 10) -> np.ndarray:
    if not tiles:
        return np.full((120, 480, 3), 245, dtype=np.uint8)
    th = max(t.shape[0] for t in tiles)
    tw = max(t.shape[1] for t in tiles)
    rows = (len(tiles) + cols - 1) // cols
    canvas = np.full((rows * (th + pad) + pad, cols * (tw + pad) + pad, 3), 232, dtype=np.uint8)
    for idx, tile in enumerate(tiles):
        r, c = divmod(idx, cols)
        y0 = pad + r * (th + pad)
        x0 = pad + c * (tw + pad)
        canvas[y0:y0 + tile.shape[0], x0:x0 + tile.shape[1]] = tile
    return canvas


def _fit_tile(img: np.ndarray, header: str, tw: int = 620, th: int = 480, hdr_col=(20, 20, 20)) -> np.ndarray:
    h, w = img.shape[:2]
    hdr_h = 30
    sc = min((tw - 12) / max(w, 1), (th - hdr_h - 10) / max(h, 1))
    rs = cv2.resize(img, (max(1, int(w * sc)), max(1, int(h * sc))), interpolation=cv2.INTER_AREA)
    tile = np.full((th, tw, 3), 250, dtype=np.uint8)
    ox = (tw - rs.shape[1]) // 2
    oy = hdr_h + (th - hdr_h - rs.shape[0]) // 2
    tile[oy:oy + rs.shape[0], ox:ox + rs.shape[1]] = rs
    cv2.putText(tile, header[:82], (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.48, hdr_col, 1, cv2.LINE_AA)
    return tile


def render_bbox_sheet(paper: str, out_path: Path, papers_dir: Path = PAPERS_DIR, records_dir: Path = RECORDS_DIR) -> Path:
    """Render every full figure of a paper with colored labeled panel bounding boxes."""
    py = yaml.safe_load((records_dir / paper / "panels.yaml").read_text(encoding="utf-8"))
    tiles = []
    for fid, fig in (py.get("figures") or {}).items():
        img = cv2.imread(str(papers_dir / paper / fig["file"]))
        if img is None:
            continue
        vis = img.copy()
        h, w = vis.shape[:2]
        lw = max(2, min(h, w) // 260)
        fsc = max(0.55, min(h, w) / 1400.0)
        panels = fig.get("panels") or {}
        for idx, (pid, p) in enumerate(panels.items()):
            col = OVERLAY_BGR[idx % len(OVERLAY_BGR)]
            x0, y0, x1, y1 = [int(v) for v in p["bbox"]]
            cv2.rectangle(vis, (x0, y0), (x1, y1), col, lw)
            lbl = str(p.get("panel_label") or pid)
            (tw_t, th_t), _ = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_SIMPLEX, fsc, max(1, lw // 2))
            cv2.rectangle(vis, (x0, y0), (min(w - 1, x0 + tw_t + 10), min(h - 1, y0 + th_t + 10)), col, -1)
            cv2.putText(vis, lbl, (x0 + 5, min(h - 3, y0 + th_t + 5)), cv2.FONT_HERSHEY_SIMPLEX, fsc, (255, 255, 255), max(1, lw // 2), cv2.LINE_AA)
        tiles.append(_fit_tile(vis, f"{paper} · {fid} ({len(panels)} atomic panels) · {fig['file']}", tw=760, th=600))
    grid = _make_grid(tiles, cols=2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), grid)
    return out_path


def draw_plot_overlay(crop_bgr: np.ndarray, panel_obj: dict[str, Any]) -> np.ndarray:
    """Project curves (+ ±SD/CI bands), scatter (+ x/y errorbars), boxplots, and dotplots onto crop_bgr."""
    vis = crop_bgr.copy()
    h, w = vis.shape[:2]
    d = panel_obj.get("data") or {}
    lw = max(1, min(h, w) // 260)

    if "dotplot_matrix" in d and d["dotplot_matrix"].get("cells"):
        for c in d["dotplot_matrix"]["cells"]:
            if c.get("r_px", 0) > 0:
                cv2.circle(vis, (int(c["px"]), int(c["py"])), max(2, int(round(c["r_px"]))), (64, 230, 0), max(2, lw), cv2.LINE_AA)
        return vis

    om = d.get("overlay_meta") or {}
    pb = om.get("plot_box")
    if not pb or len(pb) != 4:
        return vis
    px0, py0, px1, py1 = [int(round(v)) for v in pb]
    pw, ph = max(1, px1 - px0), max(1, py1 - py0)
    cv2.rectangle(vis, (px0, py0), (px1, py1), (212, 182, 6), max(1, lw))

    xr = om.get("x_range")
    yr = om.get("y_range")
    x_log = om.get("x_scale") == "log10"
    y_log = om.get("y_scale") == "log10"

    def x2p(v: float) -> int:
        if x_log:
            f = (math.log10(max(v, 1e-12)) - math.log10(max(xr[0], 1e-12))) / max(math.log10(xr[1]) - math.log10(xr[0]), 1e-9)
        else:
            f = (v - xr[0]) / max(xr[1] - xr[0], 1e-9)
        return int(round(px0 + f * pw))

    def y2p(v: float) -> int:
        if y_log:
            f = (math.log10(max(v, 1e-12)) - math.log10(max(yr[0], 1e-12))) / max(math.log10(yr[1]) - math.log10(yr[0]), 1e-9)
        else:
            f = (v - yr[0]) / max(yr[1] - yr[0], 1e-9)
        return int(round(py1 - f * ph))

    # Curves + optional ±SD / 95% CI ribbons
    if "curves" in d and xr and yr:
        for idx, c in enumerate(d["curves"].values()):
            xs, ys = c.get("x") or [], c.get("y") or []
            if len(xs) < 2:
                continue
            col = OVERLAY_BGR[idx % len(OVERLAY_BGR)]
            lo, hi = c.get("lo") or [], c.get("hi") or []
            if len(lo) == len(xs) and len(hi) == len(xs):
                pts_hi = np.array([[x2p(x), y2p(y)] for x, y in zip(xs, hi)], dtype=np.int32)
                pts_lo = np.array([[x2p(x), y2p(y)] for x, y in zip(xs, lo)], dtype=np.int32)
                cv2.polylines(vis, [pts_hi], False, col, max(1, lw), cv2.LINE_AA)
                cv2.polylines(vis, [pts_lo], False, col, max(1, lw), cv2.LINE_AA)
            pts = np.array([[x2p(x), y2p(y)] for x, y in zip(xs, ys)], dtype=np.int32)
            cv2.polylines(vis, [pts], False, (0, 0, 0), max(3, lw * 3), cv2.LINE_AA)
            cv2.polylines(vis, [pts], False, col, max(1, int(lw * 1.4)), cv2.LINE_AA)

    # Scatter + per-point x/y errorbars
    if "digitized_scatter" in d and yr:
        is_bee = om.get("mode") == "beeswarm_1d"
        gmap = {g["name"]: g for g in (om.get("groups") or [])}
        for idx, (gn, g) in enumerate(d["digitized_scatter"].items()):
            col = OVERLAY_BGR[idx % len(OVERLAY_BGR)]
            gx, gy = g.get("x") or [], g.get("y") or []
            xlo, xhi = g.get("x_lo") or [], g.get("x_hi") or []
            ylo, yhi = g.get("y_lo") or [], g.get("y_hi") or []
            mg = gmap.get(gn)
            rad = max(3, lw * 2 + 1)
            for i, (xv, yv) in enumerate(zip(gx, gy)):
                if is_bee and mg:
                    xf = ((xv - mg["x_val"]) / 0.36) + 0.5
                    px = int(round(px0 + (mg["x_frac"][0] + xf * (mg["x_frac"][1] - mg["x_frac"][0])) * pw))
                elif xr:
                    px = x2p(xv)
                else:
                    continue
                py = y2p(yv)
                if i < len(xlo) and i < len(xhi) and xlo[i] is not None and xhi[i] is not None and xr:
                    cv2.line(vis, (x2p(xlo[i]), py), (x2p(xhi[i]), py), col, max(1, lw), cv2.LINE_AA)
                if i < len(ylo) and i < len(yhi) and ylo[i] is not None and yhi[i] is not None:
                    cv2.line(vis, (px, y2p(ylo[i])), (px, y2p(yhi[i])), col, max(1, lw), cv2.LINE_AA)
                cv2.circle(vis, (px, py), rad + 1, (0, 0, 0), -1, cv2.LINE_AA)
                cv2.circle(vis, (px, py), rad - 1, col, -1, cv2.LINE_AA)

    # Boxplots
    if "digitized_boxplots" in d and yr and om.get("groups"):
        for idx, gm in enumerate(om["groups"]):
            b = d["digitized_boxplots"].get(gm["name"])
            if not b:
                continue
            col = OVERLAY_BGR[idx % len(OVERLAY_BGR)]
            cx = int(round(px0 + 0.5 * (gm["x_frac"][0] + gm["x_frac"][1]) * pw))
            bw = max(8, int(round((gm["x_frac"][1] - gm["x_frac"][0]) * pw * 0.42)))
            if b.get("whisker_lo") is not None and b.get("whisker_hi") is not None:
                cv2.line(vis, (cx, y2p(b["whisker_lo"])), (cx, y2p(b["whisker_hi"])), col, max(2, lw), cv2.LINE_AA)
            if b.get("q1") is not None and b.get("q3") is not None:
                cv2.rectangle(vis, (cx - bw // 2, y2p(b["q3"])), (cx + bw // 2, y2p(b["q1"])), col, max(2, lw))
            if b.get("median") is not None:
                cv2.line(vis, (cx - bw // 2 - 2, y2p(b["median"])), (cx + bw // 2 + 2, y2p(b["median"])), (30, 30, 240), max(2, lw + 1), cv2.LINE_AA)

    return vis


def draw_microscopy_overlay(crop_bgr: np.ndarray, panel_obj: dict[str, Any]) -> np.ndarray:
    """Project scale-bar bracket, cyan FFT ROI, phase-aligned green grating lines, and transect peaks."""
    vis = crop_bgr.copy()
    h, w = vis.shape[:2]
    d = panel_obj.get("data") or {}
    om = d.get("overlay_meta") or {}
    lw = max(1, min(h, w) // 220)

    # 1. FFT ROI + Phase-aligned parallel grating lines
    roi = om.get("roi_px")
    grating = om.get("grating")
    if roi and len(roi) == 4:
        rx0, ry0, rx1, ry1 = [int(round(v)) for v in roi]
        if grating and grating.get("period_px", 0) > 1:
            period_px = float(grating["period_px"])
            ang_rad = math.radians(float(grating["wavevector_deg"]))
            shift = float(grating.get("phase_shift_px", 0.0))
            nx, ny = math.cos(ang_rad), math.sin(ang_rad)
            tx, ty = -ny, nx
            cx, cy = 0.5 * (rx0 + rx1), 0.5 * (ry0 + ry1)
            diag = math.hypot(rx1 - rx0, ry1 - ry0)
            ov = vis.copy()
            n_lines = int(diag / max(period_px, 4.0)) + 2
            for k in range(-n_lines, n_lines + 1):
                s = k * period_px + shift
                px, py = cx + s * nx, cy + s * ny
                p1 = (int(round(px - diag * tx)), int(round(py - diag * ty)))
                p2 = (int(round(px + diag * tx)), int(round(py + diag * ty)))
                cv2.line(ov, p1, p2, (70, 255, 0), max(1, lw), cv2.LINE_AA)
            vis[ry0:ry1, rx0:rx1] = cv2.addWeighted(ov[ry0:ry1, rx0:rx1], 0.52, vis[ry0:ry1, rx0:rx1], 0.48, 0)

        # Orthogonal crossrib grating (magenta, subtle) if measured
        cr = om.get("crossrib_grating")
        if cr and cr.get("period_px", 0) > 1:
            period_px = float(cr["period_px"])
            ang_rad = math.radians(float(cr["wavevector_deg"]))
            shift = float(cr.get("phase_shift_px", 0.0))
            nx, ny = math.cos(ang_rad), math.sin(ang_rad)
            tx, ty = -ny, nx
            cx, cy = 0.5 * (rx0 + rx1), 0.5 * (ry0 + ry1)
            diag = math.hypot(rx1 - rx0, ry1 - ry0)
            ov2 = vis.copy()
            n_lines = int(diag / max(period_px, 4.0)) + 2
            for k in range(-n_lines, n_lines + 1):
                s = k * period_px + shift
                px, py = cx + s * nx, cy + s * ny
                cv2.line(ov2, (int(px - diag * tx), int(py - diag * ty)), (int(px + diag * tx), int(py + diag * ty)), (220, 60, 255), max(1, lw), cv2.LINE_AA)
            vis[ry0:ry1, rx0:rx1] = cv2.addWeighted(ov2[ry0:ry1, rx0:rx1], 0.30, vis[ry0:ry1, rx0:rx1], 0.70, 0)

        # Transect lines (show middle 3 to stay crisp) + peak dots
        transects = om.get("transects") or []
        for tr in transects[::max(1, len(transects) // 3)]:
            p0 = tuple(int(round(v)) for v in tr["p0"])
            p1 = tuple(int(round(v)) for v in tr["p1"])
            cv2.line(vis, p0, p1, (0, 215, 255), max(1, lw), cv2.LINE_AA)
            for pk in tr.get("peaks_px") or []:
                cv2.circle(vis, (int(round(pk[0])), int(round(pk[1]))), max(2, lw + 1), (0, 230, 255), -1, cv2.LINE_AA)

        # Crisp cyan ROI box
        cv2.rectangle(vis, (rx0, ry0), (rx1, ry1), (255, 220, 0), max(2, lw + 1))

    # 2. Yellow scale-bar bracket
    sb = om.get("scale_bar_px")
    if sb:
        bx0, by0, bx1, by1 = int(round(sb["x0"])), int(round(sb["y0"])), int(round(sb["x1"])), int(round(sb["y1"]))
        cv2.rectangle(vis, (bx0 - 2, by0 - 2), (bx1 + 2, by1 + 2), (0, 225, 255), max(2, lw + 1))
        lbl = f"{sb['um']:g} um ({sb['um_per_px']*1000:.1f} nm/px)"
        cv2.putText(vis, lbl, (max(4, bx0 - 20), max(16, by0 - 6)), cv2.FONT_HERSHEY_SIMPLEX, max(0.38, w / 1200.0), (0, 225, 255), max(1, lw), cv2.LINE_AA)
    return vis


def render_plot_overlay_sheet(paper: str, out_path: Path, papers_dir: Path = PAPERS_DIR, records_dir: Path = RECORDS_DIR) -> Path:
    panels = json.loads((records_dir / paper / "digitized" / "panels_extracted.json").read_text(encoding="utf-8"))
    img_cache: dict[str, np.ndarray] = {}
    tiles = []
    for p in panels:
        d = p.get("data") or {}
        if not any(k in d for k in ("curves", "digitized_scatter", "digitized_boxplots", "dotplot_matrix")):
            continue
        if p["file"] not in img_cache:
            img_cache[p["file"]] = cv2.imread(str(papers_dir / paper / p["file"]))
        x0, y0, x1, y1 = p["bbox"]
        crop = img_cache[p["file"]][y0:y1, x0:x1]
        vis = draw_plot_overlay(crop, p)
        tag = f" [{Path(p['extractor_script']).name}]" if p.get("extractor_script") else ""
        hdr = f"{p['id']}{tag} | {p.get('n_digitized_points', 0)} pts"
        tiles.append(_fit_tile(vis, hdr, tw=620, th=470))
    grid = _make_grid(tiles, cols=3)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), grid)
    return out_path


def render_fft_overlay_sheet(paper: str, out_path: Path, papers_dir: Path = PAPERS_DIR, records_dir: Path = RECORDS_DIR) -> Path:
    panels = json.loads((records_dir / paper / "digitized" / "panels_extracted.json").read_text(encoding="utf-8"))
    img_cache: dict[str, np.ndarray] = {}
    tiles = []
    for p in panels:
        d = p.get("data") or {}
        if d.get("periodic_fft_um") is None and d.get("um_per_px") is None:
            continue
        if p["file"] not in img_cache:
            img_cache[p["file"]] = cv2.imread(str(papers_dir / paper / p["file"]))
        x0, y0, x1, y1 = p["bbox"]
        crop = img_cache[p["file"]][y0:y1, x0:x1]
        vis = draw_microscopy_overlay(crop, p)
        if d.get("periodic_fft_um") is not None:
            hg = d.get("harmonic_guard") or {}
            st = hg.get("status", "ok")
            hdr_col = (0, 0, 200) if st == "flagged" else ((0, 120, 200) if st == "low_snr_verify" else (20, 110, 40))
            hdr = f"{p['id']} | FFT={d['periodic_fft_um']:.3f} tr={d.get('periodic_transect_um')} um | snr={d.get('periodic_snr',0):.0f} [{st}]"
        else:
            hdr_col = (60, 60, 60)
            hdr = f"{p['id']} | scale={d['um_per_px']*1000:.1f} nm/px FOV={d.get('fov_um')} um"
        tiles.append(_fit_tile(vis, hdr, tw=520, th=410, hdr_col=hdr_col))
    grid = _make_grid(tiles, cols=3)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), grid)
    return out_path
