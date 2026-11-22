"""Bespoke extractor for Lloyd et al. (2024) Figure 7E & 7F (41467_2024_48060_Fig7_HTML.jpg):
- F7/E & F7/F: TauSTED spatial fluorescence intensity profiles across developing Parides arcas ridges
  for actin (green) and chitin (magenta) on a black background.

Uses pure additive fluorescence channel extraction (green = G, magenta = 0.5 * (R + B)) instead of
crosstalk subtraction so colocalized actin+chitin overlaps (which sum to white on black) never drop
to zero, and traces every pixel column with exact sharp-peak crest localization.
"""
from __future__ import annotations

from typing import Any
import numpy as np


_CFGS = {
    "E": {"pbox": (21, 5, 210, 180), "xr": (-0.2, 7.1), "yr": (-1.0, 70.0)},
    "F": {"pbox": (21, 5, 210, 218), "xr": (-0.2, 8.4), "yr": (-1.0, 70.0)},
}


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    cfg = _CFGS[panel_id]
    px0, py0, px1, py1 = cfg["pbox"]
    sub = crop_rgb[py0:py1, px0:px1].astype(np.float32).copy()
    # Mask panel letter "(E)" / "(F)" in top-right corner
    sub[:30, 152:] = 0.0
    h, w = sub.shape[:2]
    x_min, x_max = cfg["xr"]
    y_min, y_max = cfg["yr"]

    r = sub[:, :, 0]
    g = sub[:, :, 1]
    b = sub[:, :, 2]

    # Pure additive RGB fluorescence channels: green + magenta = white preserves both channels at crossings!
    green_sig = g.copy()
    mag_sig = 0.5 * (r + b)
    # Exclude 2px margins adjacent to white axes spines
    green_sig[-2:, :] = 0.0
    green_sig[:, :2] = 0.0
    mag_sig[-2:, :] = 0.0
    mag_sig[:, :2] = 0.0

    curves: dict[str, Any] = {}
    thr = 38.0

    for name, sig in [("actin", green_sig), ("chitin", mag_sig)]:
        xs: list[float] = []
        ys: list[float] = []
        for cx in range(2, w - 2):
            col = sig[:, cx]
            hits = np.where(col >= thr)[0]
            if len(hits) == 0:
                continue
            span = int(hits[-1] - hits[0])
            if span <= 6:
                wts = col[hits]
                py = float(np.sum(hits * wts) / max(float(np.sum(wts)), 1e-6))
            else:
                l_hits = np.where(sig[:, max(0, cx - 1)] >= thr)[0]
                r_hits = np.where(sig[:, min(w - 1, cx + 1)] >= thr)[0]
                l_top = int(l_hits[0]) if len(l_hits) else h
                r_top = int(r_hits[0]) if len(r_hits) else h
                if int(hits[0]) <= l_top and int(hits[0]) <= r_top:
                    # Sharp peak crest: lock cleanly to top crest pixels
                    py = float(np.mean(hits[:min(3, len(hits))]))
                else:
                    py = float(0.5 * (hits[0] + hits[-1]))
            xv = round(x_min + (cx / max(w, 1)) * (x_max - x_min), 4)
            yv = round(y_max - (py / max(h, 1)) * (y_max - y_min), 4)
            xs.append(xv)
            ys.append(yv)

        peak_idx = int(np.argmax(ys)) if ys else 0
        curves[name] = {
            "x": xs,
            "y": ys,
            "peak_x": xs[peak_idx] if xs else None,
            "peak_y": ys[peak_idx] if ys else None,
            "x_unit": "µm",
            "y_unit": "intensity",
        }

    return {
        "curves": curves,
        "overlay_meta": {
            "plot_box": list(cfg["pbox"]),
            "x_range": list(cfg["xr"]),
            "y_range": list(cfg["yr"]),
            "kind": "curve",
        },
    }
