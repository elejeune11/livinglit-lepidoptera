"""Bespoke extractor for Parnell et al. (2018) Figure 3 (rsif20170948-g3.jpg, panels A–G):
Multi-angle optical reflectance spectra (300–700 nm, 0–25%) from one individual forewing of
each of the 7 Heliconius taxa rotated along the anterior–posterior axis.

Uses `find_axis_ticks` for exact tick-mark calibration (with 4-tick linear fit on F3/D where
the printed 700 nm tick sits slightly left of the linear grid), `ray_dist_alpha` ink
decomposition, and L1 Viterbi curve tracking (`viterbi_track`) to extract key angular traces
(peak-reflectance angle, normal incidence 0°, and off-peak high-angle traces) per taxon.
"""
from __future__ import annotations

from typing import Any
import numpy as np

from livinglit_lepidoptera.extract_lib import (
    AxisCal,
    find_axis_ticks,
    ray_dist_alpha,
    viterbi_track,
)


# Legend exclusion boxes inside plot_box (x0, y0, x1, y1) and distinct color traces per panel
_PANEL_CFG: dict[str, dict[str, Any]] = {
    "A": {  # H. erato cyrbia (-18..20 deg)
        "leg": (132, 2, 232, 112),
        "traces": [
            ("peak_12deg_purple",  (145, 35, 205), 54.0, 0.24, (10, 200), True),
            ("angle_8deg_blue",    (28, 42, 212),  44.0, 0.28, (70, 200), False),
            ("angle_20deg_crimson",(202, 20, 72),  46.0, 0.28, (90, 200), False),
            ("normal_0deg_cyan",   (85, 225, 230), 42.0, 0.25, (176, 200), False),
        ],
    },
    "B": {  # H. melpomene cythera (0..20 deg)
        "leg": (178, 8, 228, 148),
        "traces": [
            ("peak_6deg_green",    (112, 225, 42), 52.0, 0.25, (100, 200), True),
            ("normal_0deg_red",    (222, 32, 32),  48.0, 0.25, (115, 200), False),
            ("angle_18deg_magenta",(210, 25, 195), 48.0, 0.25, (115, 200), False),
        ],
    },
    "C": {  # H. erato demophoon (0..24 deg, non-iridescent)
        "leg": (176, 8, 226, 125),
        "traces": [
            ("normal_0deg_red",    (222, 30, 30),  48.0, 0.25, (160, 200), False),
            ("angle_24deg_magenta",(210, 25, 175), 48.0, 0.25, (165, 200), False),
        ],
    },
    "D": {  # H. melpomene rosina (0..14 deg, non-iridescent)
        "leg": (177, 8, 227, 104),
        "traces": [
            ("angle_6deg_green",   (45, 215, 115), 55.0, 0.25, (165, 200), False),
            ("angle_14deg_magenta",(215, 30, 185), 50.0, 0.25, (165, 200), False),
        ],
    },
    "E": {  # H. eleuchia (0..14 deg)
        "leg": (173, 5, 229, 117),
        "traces": [
            ("peak_0deg_red",      (225, 28, 28),  48.0, 0.28, (80, 200), True),
            ("angle_6deg_green",   (45, 220, 110), 50.0, 0.25, (110, 200), False),
            ("angle_10deg_blue",   (28, 65, 225),  48.0, 0.28, (145, 200), False),
            ("angle_14deg_magenta",(185, 76, 158), 42.0, 0.28, (176, 200), False),
        ],
    },
    "F": {  # H. cydno (0..30 deg)
        "leg": (102, 8, 231, 127),
        "traces": [
            ("peak_16deg_cyan",    (35, 205, 225), 55.0, 0.22, (160, 200), True),
            ("normal_0deg_red",    (225, 35, 28),  50.0, 0.22, (165, 200), False),
        ],
    },
    "G": {  # H. sara (0..10 deg)
        "leg": (173, 7, 229, 95),
        "traces": [
            ("peak_4deg_green",    (55, 225, 55),  52.0, 0.28, (10, 200), True),
            ("normal_0deg_red",    (225, 30, 30),  48.0, 0.28, (45, 200), False),
            ("angle_8deg_blue",    (28, 35, 220),  48.0, 0.28, (75, 200), False),
            ("angle_10deg_magenta",(220, 20, 195), 48.0, 0.28, (125, 200), False),
        ],
    },
}


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    ax = find_axis_ticks(
        crop_rgb,
        y_labels=[0.0, 5.0, 10.0, 15.0, 20.0, 25.0],
        x_labels=[300.0, 400.0, 500.0, 600.0, 700.0],
        probe=(1, 5),
        tick_min_frac=0.45,
    )
    px0, py0, px1, py1 = ax["plot_box"]
    x_cal, y_cal = ax["x_cal"], ax["y_cal"]
    # In panel D (H. melpomene rosina), the first 4 ticks (300..600) sit on an exact 55.0 px step while the
    # 700 label/tick sits slightly left at 271.5; fit x_cal on the 4 strictly linear ticks for subpixel accuracy.
    if panel_id == "D" and len(ax["x_ticks"]) == 5:
        x_cal = AxisCal.fit(ax["x_ticks"][:4], [300.0, 400.0, 500.0, 600.0], scale="linear")

    xr = list(x_cal.range_for_span(px0, px1, ndigits=3))
    yr = list(y_cal.range_for_span(py1, py0, ndigits=3))

    sub = crop_rgb[py0:py1, px0:px1].astype(np.float32).copy()
    h, w = sub.shape[:2]
    cfg = _PANEL_CFG[panel_id]
    lx0, ly0, lx1, ly1 = cfg["leg"]
    excl = np.zeros((h, w), dtype=bool)
    excl[max(0, ly0):min(h, ly1), max(0, lx0):min(w, lx1)] = True

    c_start = max(1, int(round(x_cal.to_pixel(300.0) - px0)))
    c_end = min(w - 2, int(round(x_cal.to_pixel(700.0) - px0)))
    cols = np.linspace(c_start, c_end, 65).astype(int)
    xs_val = [round(float(x_cal.to_value(px0 + c)), 2) for c in cols]

    rows_idx = np.arange(h, dtype=np.float64)
    curves: dict[str, Any] = {}
    for tname, rgb, max_perp, min_alpha, (yb0, yb1), prefer_upper in cfg["traces"]:
        perp, alpha = ray_dist_alpha(sub, rgb)
        sat = sub.max(axis=2) - sub.min(axis=2)
        t_sat = float(max(rgb) - min(rgb))
        cost = np.full((h, len(cols)), 32.0, dtype=np.float64)
        for ti, c in enumerate(cols):
            c0, c1 = max(0, c - 1), min(w, c + 2)
            p_col = perp[:, c0:c1].min(axis=1)
            a_col = alpha[:, c0:c1].max(axis=1)
            s_col = sat[:, c0:c1].max(axis=1)
            hit = (p_col <= max_perp) & (a_col >= min_alpha) & (s_col >= max(18.0, 0.16 * t_sat)) & (~excl[:, c])
            base_cost = 0.45 * p_col - 14.0 * np.minimum(a_col, 1.05)
            if prefer_upper:
                # Favor the upper peak curve when neighboring angles share nearly identical hue
                base_cost = base_cost - 14.0 * (1.0 - rows_idx / max(h, 1))
            c_col = np.where(hit, base_cost, 32.0)
            c_col[:yb0] = 90.0
            c_col[yb1:] = 90.0
            c_col[excl[:, c]] = 95.0
            cost[:, ti] = c_col

        y_path = viterbi_track(cost, max_step=18 if prefer_upper else 12, smooth_w=0.22 if prefer_upper else 0.45, norm="l1")
        ys = [round(max(0.0, float(y_cal.to_value(py0 + r))), 3) for r in y_path]
        pk = int(np.argmax(ys))
        curves[tname] = {
            "x": xs_val,
            "y": ys,
            "peak_x": xs_val[pk],
            "peak_y": ys[pk],
            "x_unit": "nm",
            "y_unit": "%",
        }

    top_curve = max(curves.values(), key=lambda c: c["peak_y"])
    return {
        "curves": curves,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": xr,
            "y_range": yr,
            "x_misfit_px": x_cal.misfit_px,
            "y_misfit_px": y_cal.misfit_px,
            "kind": "curves",
        },
        "extracted_data": {
            "x_tick_misfit_px": x_cal.misfit_px,
            "y_tick_misfit_px": y_cal.misfit_px,
            "max_curve_peak_nm": top_curve["peak_x"],
            "max_curve_peak_pct": top_curve["peak_y"],
        },
    }
