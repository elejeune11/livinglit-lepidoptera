"""Bespoke extractor for Stavenga et al. (2020) Figure 5A, 5B, 5C (fphys-11-00095-g005.jpg):
- A (5A): Isolated scale adwing reflectance at area 1 (solid bright blue) vs modeled chitin
  thin film in air of thickness 230 nm (dotted dark navy).
- B (5B): Isolated scale adwing reflectance at area 2 (solid yellow) vs modeled chitin
  thin film in air of thickness 290 nm (dotted orange).
- C (5C): Isolated scale abwing reflectance at area 3 (gray, root), area 4 (green, middle),
  and area 5 (maroon, tip).
"""
from __future__ import annotations

from typing import Any
import cv2
import numpy as np

from livinglit_lepidoptera.extract_lib import (
    find_axis_ticks,
    ray_dist_alpha,
    viterbi_track,
)


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    ax = find_axis_ticks(
        crop_rgb,
        y_labels=[0.0, 0.1, 0.2, 0.3],
        x_labels=[400.0, 500.0, 600.0, 700.0, 800.0],
        dark_thr=215.0,
        max_sat=256.0,
        min_spine_frac=0.55,
        probe=(2, 7),
    )
    x_cal, y_cal = ax["x_cal"], ax["y_cal"]
    px0 = int(round(x_cal.to_pixel(350.0)))
    px1 = int(round(x_cal.to_pixel(800.0)))
    py0 = int(round(y_cal.to_pixel(0.3)))
    py1 = int(round(y_cal.to_pixel(0.0)))
    plot_box = (px0, py0, px1, py1)

    sub = crop_rgb[py0:py1, px0:px1].copy()
    # Mask pure-black text digits ('1', '2', '3', '4', '5') without touching medium-gray curve 3
    lum = sub.mean(axis=2)
    sat = sub.max(axis=2).astype(int) - sub.min(axis=2).astype(int)
    black_ink = ((lum < 75) & (sat < 22)).astype(np.uint8)
    sub[cv2.dilate(black_ink, np.ones((5, 5), np.uint8)) > 0] = 255

    sub_f = sub.astype(np.float32)
    h, w = sub_f.shape[:2]
    pix_sat = np.max(sub_f, axis=2) - np.min(sub_f, axis=2)

    n_cols = 115
    x_cols = np.linspace(2, w - 3, n_cols).astype(int)
    empty_cost = 120.0
    curves: dict[str, Any] = {}

    if panel_id == "A":
        # Solid bright blue (8, 4, 236) vs dotted dark navy (12, 6, 118).
        # Separate directly in RGB space because bright blue has B>175, R,G<55 whereas dark navy has B in [55..145], R,G<45!
        R, G, B = sub_f[:, :, 0], sub_f[:, :, 1], sub_f[:, :, 2]
        p_solid, a_solid = ray_dist_alpha(sub_f, (8, 4, 236))
        p_model, a_model = ray_dist_alpha(sub_f, (12, 6, 118))

        # Solid curve: bright blue core (B - R > 130 and B > 165)
        valid_solid = (p_solid <= 36.0) & (a_solid >= 0.40) & (B > 160.0) & (R < 90.0)
        cost_solid_px = np.where(valid_solid, 0.7 * p_solid + 30.0 * (1.15 - np.clip(a_solid, 0.0, 1.15)), empty_cost)

        # Dotted model curve: dark navy dots (50 < B < 155, R < 55, G < 55, B - R > 35)
        # Note: exclude immediate 3-px halo around bright-blue solid curve
        solid_dil = cv2.dilate(valid_solid.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
        valid_model = (p_model <= 36.0) & (a_model >= 0.40) & (B < 155.0) & (B > 45.0) & (R < 65.0) & (~solid_dil)
        cost_model_px = np.where(valid_model, 0.7 * p_model + 30.0 * (1.15 - np.clip(a_model, 0.0, 1.15)), empty_cost)

        # Track solid first (tight horizontal window +-2)
        c_sol = np.full((h, n_cols), empty_cost, dtype=np.float64)
        for ti, cx in enumerate(x_cols):
            c_sol[:, ti] = cost_solid_px[:, max(0, cx - 2):min(w, cx + 3)].min(axis=1)
        y_sol = viterbi_track(c_sol, max_step=32, smooth_w=0.22, norm="l1")

        # Track dotted model (wider horizontal window +-5 to bridge inter-dot gaps!)
        c_mod = np.full((h, n_cols), empty_cost, dtype=np.float64)
        for ti, cx in enumerate(x_cols):
            c_mod[:, ti] = cost_model_px[:, max(0, cx - 5):min(w, cx + 6)].min(axis=1)
            # Model curve sits strictly below solid measured curve at every wavelength
            c_mod[:int(y_sol[ti]) + 10, ti] = empty_cost
        y_mod = viterbi_track(c_mod, max_step=30, smooth_w=0.30, norm="l1")

        for name, yp in [("area1_adwing_measured", y_sol), ("thin_film_230nm_model", y_mod)]:
            xs_out = [round(x_cal.to_value(px0 + cx), 2) for cx in x_cols]
            ys_out = [round(y_cal.to_value(py0 + py), 4) for py in yp]
            curves[name] = {
                "x": xs_out,
                "y": ys_out,
                "peak_x": xs_out[int(np.argmax(ys_out))],
                "peak_y": max(ys_out),
                "x_unit": "nm",
                "y_unit": "reflectance",
            }

    elif panel_id == "B":
        # Solid yellow (250, 250, 12) vs dotted orange (245, 126, 28) — crossing near ~415 nm!
        traces_b = [
            ("area2_adwing_measured", (250, 250, 12), 2),
            ("thin_film_290nm_model", (245, 126, 28), 5),
        ]
        perps, alphas = {}, {}
        for name, rgb, _ in traces_b:
            perps[name], alphas[name] = ray_dist_alpha(sub_f, rgb)

        for name, rgb, win in traces_b:
            p_map, a_map = perps[name], alphas[name]
            valid_px = (p_map <= 38.0) & (a_map >= 0.35) & (pix_sat >= 45.0)
            cost_px = np.where(valid_px, 0.75 * p_map + 34.0 * (1.15 - np.clip(a_map, 0.0, 1.15)), empty_cost)
            for oname, _, _ in traces_b:
                if oname == name:
                    continue
                stolen = (perps[oname] + 4.0 < p_map) & (alphas[oname] >= 0.30)
                cost_px = np.where(stolen, empty_cost, cost_px)

            cost = np.full((h, n_cols), empty_cost, dtype=np.float64)
            for ti, cx in enumerate(x_cols):
                cost[:, ti] = cost_px[:, max(0, cx - win):min(w, cx + win + 1)].min(axis=1)

            y_path = viterbi_track(cost, max_step=36, smooth_w=0.28, norm="l1")
            xs_out = [round(x_cal.to_value(px0 + cx), 2) for cx in x_cols]
            ys_out = [round(y_cal.to_value(py0 + py), 4) for py in y_path]
            curves[name] = {
                "x": xs_out,
                "y": ys_out,
                "peak_x": xs_out[int(np.argmax(ys_out))],
                "peak_y": max(ys_out),
                "x_unit": "nm",
                "y_unit": "reflectance",
            }

    elif panel_id == "C":
        # Area 3 (gray, root), Area 4 (dark green, middle), Area 5 (maroon, tip)
        traces_c = [
            ("area3_abwing_root",   (128, 128, 128), False),
            ("area4_abwing_middle", (10, 125, 14),   True),
            ("area5_abwing_tip",    (128, 8, 9),     True),
        ]
        perps, alphas = {}, {}
        for name, rgb, _ in traces_c:
            perps[name], alphas[name] = ray_dist_alpha(sub_f, rgb)

        for name, rgb, is_chrom in traces_c:
            p_map, a_map = perps[name], alphas[name]
            if is_chrom:
                valid_px = (p_map <= 38.0) & (a_map >= 0.30) & (pix_sat >= 28.0)
            else:
                # Medium gray curve (128,128,128) — low saturation, medium darkness
                lum_f = sub_f.mean(axis=2)
                valid_px = (p_map <= 24.0) & (a_map >= 0.45) & (pix_sat < 22.0) & (lum_f > 85.0) & (lum_f < 185.0)
            cost_px = np.where(valid_px, 0.8 * p_map + 34.0 * (1.15 - np.clip(a_map, 0.0, 1.15)), empty_cost)
            for oname, _, _ in traces_c:
                if oname == name:
                    continue
                stolen = (perps[oname] + 4.0 < p_map) & (alphas[oname] >= 0.30)
                cost_px = np.where(stolen, empty_cost, cost_px)

            cost = np.full((h, n_cols), empty_cost, dtype=np.float64)
            for ti, cx in enumerate(x_cols):
                cost[:, ti] = cost_px[:, max(0, cx - 2):min(w, cx + 3)].min(axis=1)

            y_path = viterbi_track(cost, max_step=28, smooth_w=0.25, norm="l1")
            xs_out = [round(x_cal.to_value(px0 + cx), 2) for cx in x_cols]
            ys_out = [round(y_cal.to_value(py0 + py), 4) for py in y_path]
            curves[name] = {
                "x": xs_out,
                "y": ys_out,
                "peak_x": xs_out[int(np.argmax(ys_out))],
                "peak_y": max(ys_out),
                "x_unit": "nm",
                "y_unit": "reflectance",
            }
    else:
        raise ValueError(f"Unsupported Fig 5 panel_id: {panel_id!r}")

    x_range = [round(x_cal.to_value(px0), 4), round(x_cal.to_value(px1), 4)]
    y_range = [round(y_cal.to_value(py1), 4), round(y_cal.to_value(py0), 4)]
    return {
        "curves": curves,
        "overlay_meta": {
            "plot_box": list(plot_box),
            "x_range": x_range,
            "y_range": y_range,
            "x_misfit_px": ax["x_misfit_px"],
            "y_misfit_px": ax["y_misfit_px"],
            "kind": "curves",
        },
    }
