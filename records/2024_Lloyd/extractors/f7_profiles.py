"""Bespoke extractor for Lloyd et al. (2024) Figure 7E & 7F (41467_2024_48060_Fig7_HTML.jpg):
- F7/E & F7/F: TauSTED spatial fluorescence intensity profiles across developing Parides arcas ridges
  for actin (green) and chitin (magenta) on a black background.

Separates overlapping green/magenta spikes cleanly by independent chromatic excess:
  green_score   = G - 0.5 * (R + B)
  magenta_score = 0.5 * (R + B) - G
"""
from __future__ import annotations

from typing import Any
import numpy as np


_CFGS = {
    "E": {"pbox": (21, 5, 210, 181), "xr": (-0.2, 7.1), "yr": (-1.0, 70.0)},
    "F": {"pbox": (21, 5, 210, 222), "xr": (-0.2, 8.4), "yr": (-1.0, 70.0)},
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

    green_excess = g - 0.5 * (r + b)
    magenta_excess = 0.5 * (r + b) - g

    # Sample densely (~120 columns across active curve span)
    cols = np.linspace(4, w - 5, 118).astype(int)
    curves: dict[str, Any] = {}

    for name, score_map, thr in [
        ("actin", green_excess, 32.0),
        ("chitin", magenta_excess, 32.0),
    ]:
        xs: list[float] = []
        ys: list[float] = []
        for cx in cols:
            col = score_map[:, max(0, cx - 1):min(w, cx + 2)].max(axis=1)
            hits = np.where(col >= thr)[0]
            if len(hits) == 0:
                continue
            # Use highest intensity (top-most peak / weighted centroid of strongest band)
            # On single-valued 1D profiles, the highest bright pixel (smallest row index) traces sharp peak crests cleanly
            top_r = int(hits[0])
            band = hits[hits <= top_r + 4]
            weights = col[band]
            py = float(np.sum(band * weights) / max(float(np.sum(weights)), 1e-6))
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
