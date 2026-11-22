"""Bespoke extractor for Totz et al. (2024) Figure 3F & 3G (fig3.jpg):
- 3F: Distribution of width-normalized in vivo protoridge amplitudes w_0 (nm, L = 1.6 µm)
- 3G: Distribution of unscaled in vivo protoridge widths L (µm)
across 5 developmental time points (39.6%, 40.0%, 40.3%, 40.7%, 41.0%; n = 607, 639, 744, 821, 911).

Uses inward tick detection (`AxisCal`), white-dot anchored gray-box segmentation,
and color-invariant local-contrast whisker tracing.
"""
from __future__ import annotations

from typing import Any
import numpy as np

from livinglit_lepidoptera.extract_lib import AxisCal


_STAGES = ["39.6pct", "40.0pct", "40.3pct", "40.7pct", "41.0pct"]
_STAGE_NS = [607, 639, 744, 821, 911]


def _detect_axes(crop_rgb: np.ndarray, panel_id: str) -> dict[str, Any]:
    f = crop_rgb.astype(np.float32)
    h, w = f.shape[:2]
    sat = f.max(axis=2) - f.min(axis=2)
    dk = (f.mean(axis=2) < 120.0) & (sat < 40.0)

    def _centres(idx: list[int], gap: int = 4) -> list[float]:
        if not idx:
            return []
        gs: list[list[int]] = [[int(idx[0])]]
        for i in idx[1:]:
            if int(i) - gs[-1][-1] <= gap:
                gs[-1].append(int(i))
            else:
                gs.append([int(i)])
        return [float(np.mean(g)) for g in gs]

    v_cols = np.flatnonzero(dk.mean(axis=0) >= 0.45).tolist()
    c_left = v_cols[0]
    v_left = [c for c in v_cols if c - c_left <= 10]
    vc1 = max(v_left)
    v_right = [c for c in v_cols if c > vc1 + 200]
    p_right = min(c for c in v_right if v_right[-1] - c <= 10) - 1

    h_rows = np.flatnonzero(dk[:, vc1:p_right + 1].mean(axis=1) >= 0.55).tolist()
    r_bot = h_rows[-1]
    h_bot = [r for r in h_rows if r_bot - r <= 10]
    hr0, hr1 = min(h_bot), max(h_bot)
    h_top_all = [r for r in h_rows if r < hr0 - 200]
    h_top = [r for r in h_top_all if r - h_top_all[0] <= 10]
    p_top0, p_top1 = min(h_top), max(h_top)
    p_top = p_top1 + 1

    yb = dk[:, vc1 + 3:vc1 + 10]
    y_hits = [r for r in np.flatnonzero(yb.mean(axis=1) >= 0.55).tolist() if p_top + 20 <= r <= hr0 - 20]
    y_mid = sorted(_centres(y_hits, gap=5), reverse=True)
    y_bot_c = 0.5 * (hr0 + hr1)
    y_top_c = 0.5 * (p_top0 + p_top1)
    if panel_id == "F":
        y_ticks = [y_bot_c] + y_mid + [y_top_c]
        y_cal = AxisCal.fit(y_ticks, [0.0, 50.0, 100.0, 150.0, 200.0], scale="linear")
    else:
        y_ticks = [y_bot_c] + y_mid + [y_top_c]
        y_cal = AxisCal.fit(y_ticks, [0.0, 1.5, 3.0], scale="linear")

    xb_top = dk[p_top + 2:p_top + 9, :]
    x_hits = [c for c in np.flatnonzero(xb_top.mean(axis=0) >= 0.55).tolist() if vc1 + 25 <= c <= p_right - 25]
    x_ticks = sorted(_centres(x_hits, gap=5))
    if len(x_ticks) != 5:
        xb_bot = dk[hr0 - 9:hr0 - 2, :]
        x_hits = [c for c in np.flatnonzero(xb_bot.mean(axis=0) >= 0.55).tolist() if vc1 + 25 <= c <= p_right - 25]
        x_ticks = sorted(_centres(x_hits, gap=5))
    x_cal = AxisCal.fit(x_ticks, [1.0, 2.0, 3.0, 4.0, 5.0], scale="linear")

    return {"plot_box": (vc1 + 1, p_top, p_right, hr0 - 1), "x_cal": x_cal, "y_cal": y_cal, "x_ticks": x_ticks}


def extract(crop_rgb: np.ndarray, panel_id: str, **_: Any) -> dict[str, Any]:
    cal = _detect_axes(crop_rgb, panel_id)
    px0, py0, px1, py1 = cal["plot_box"]
    y_cal = cal["y_cal"]
    x_ticks = cal["x_ticks"]
    y_unit = "nm" if panel_id == "F" else "µm"
    ndig = 2 if panel_id == "F" else 3

    sub = crop_rgb[py0:py1, px0:px1].astype(np.float32)
    h, w = sub.shape[:2]

    boxplots: dict[str, Any] = {}
    groups_meta: dict[str, Any] = {}
    summary_means: dict[str, float] = {}

    for idx, (sname, x_full, n_prof) in enumerate(zip(_STAGES, x_ticks, _STAGE_NS)):
        cx = int(round(x_full - px0))
        groups_meta[sname] = {"x_center": cx, "half_width": 14}

        # 1. White circular marker inside gray IQR box
        w_patch = sub[18:h - 18, max(0, cx - 12):min(w, cx + 13)]
        is_w = (w_patch[:, :, 0] > 232) & (w_patch[:, :, 1] > 232) & (w_patch[:, :, 2] > 232)
        flank_l = w_patch[:, 4:8].max(axis=2).mean(axis=1) < 200
        flank_r = w_patch[:, 17:21].max(axis=2).mean(axis=1) < 200
        cand_rows = np.where((is_w[:, 10:15].mean(axis=1) > 0.45) & flank_l & flank_r)[0]
        if len(cand_rows) == 0:
            flank_l = w_patch[:, 5:8].max(axis=2).mean(axis=1) < 215
            flank_r = w_patch[:, 17:20].max(axis=2).mean(axis=1) < 215
            cand_rows = np.where((is_w[:, 10:15].mean(axis=1) > 0.40) & flank_l & flank_r)[0]
        wr = int(round(float(np.median(cand_rows)))) + 18

        # 2. Gray IQR box spanning cx-6..cx+7 (darker & lower max-RGB than surrounding colored violin)
        b_col = sub[:, max(0, cx - 6):min(w, cx + 7)]
        b_max = b_col.max(axis=2)
        b_sat = b_max - b_col.min(axis=2)
        in_box = ((b_max < 182.0) & (b_sat < 68.0)).mean(axis=1) >= 0.62

        q3_r = wr
        gap = 0
        for r in range(wr, 14, -1):
            if in_box[r]:
                q3_r, gap = r, 0
            elif abs(r - wr) <= 10:
                continue
            else:
                gap += 1
                if gap > 3:
                    break
        q1_r = wr
        gap = 0
        for r in range(wr, h - 14):
            if in_box[r]:
                q1_r, gap = r, 0
            elif abs(r - wr) <= 10:
                continue
            else:
                gap += 1
                if gap > 3:
                    break

        # 3. Horizontal gray line extending across the violin wings outside the box
        r_lo_s = max(14, q3_r - 18)
        r_hi_s = min(h - 14, q1_r + 18)
        lw = sub[r_lo_s:r_hi_s, max(0, cx - 44):max(1, cx - 12)]
        rw = sub[r_lo_s:r_hi_s, min(w - 1, cx + 12):min(w, cx + 44)]
        l_g = ((lw.max(axis=2) < 194.0) & ((lw.max(axis=2) - lw.min(axis=2)) < 50.0)).mean(axis=1)
        r_g = ((rw.max(axis=2) < 194.0) & ((rw.max(axis=2) - rw.min(axis=2)) < 50.0)).mean(axis=1)
        score_h = l_g + r_g
        hline_r = float(r_lo_s + int(np.argmax(score_h))) if score_h.max() > 0.35 else float(wr)

        # 4. Color-invariant local-contrast whisker tracing along cx-2..cx+2 vs flanking violin background
        c_lum = sub[:, max(0, cx - 1):min(w, cx + 2)].mean(axis=2).min(axis=1)
        flank_lum = 0.5 * (
            sub[:, max(0, cx - 9):max(1, cx - 5)].mean(axis=(1, 2))
            + sub[:, min(w - 1, cx + 5):min(w, cx + 9)].mean(axis=(1, 2))
        )
        c_sat = (sub[:, max(0, cx - 1):min(w, cx + 2)].max(axis=2) - sub[:, max(0, cx - 1):min(w, cx + 2)].min(axis=2)).min(axis=1)
        wh_m = ((flank_lum - c_lum) > 15.0) & (c_lum < 178.0) & (c_sat < 68.0)

        wh_hi_r = q3_r
        gap = 0
        for r in range(q3_r, 12, -1):
            if wh_m[r]:
                wh_hi_r, gap = r, 0
            else:
                gap += 1
                if gap > 8:
                    break
        wh_lo_r = q1_r
        gap = 0
        for r in range(q1_r, h - 12):
            if wh_m[r]:
                wh_lo_r, gap = r, 0
            else:
                gap += 1
                if gap > 8:
                    break

        q1_v = round(max(0.0, y_cal.to_value(py0 + float(q1_r))), ndig)
        q3_v = round(max(0.0, y_cal.to_value(py0 + float(q3_r))), ndig)
        dot_v = round(max(0.0, y_cal.to_value(py0 + float(wr))), ndig)
        hline_v = round(max(0.0, y_cal.to_value(py0 + float(hline_r))), ndig)
        wlo_v = round(max(0.0, y_cal.to_value(py0 + float(wh_lo_r))), ndig)
        whi_v = round(max(0.0, y_cal.to_value(py0 + float(wh_hi_r))), ndig)

        summary_means[sname] = dot_v
        boxplots[sname] = {
            "whisker_lo": wlo_v,
            "q1": q1_v,
            "median": hline_v,
            "mean_dot": dot_v,
            "q3": q3_v,
            "whisker_hi": whi_v,
            "n_profiles": n_prof,
            "y_unit": y_unit,
        }

    return {
        "digitized_boxplots": boxplots,
        "overlay_meta": {
            "plot_box": [px0, py0, px1, py1],
            "x_range": [0.5, 5.5],
            "y_range": [round(y_cal.to_value(py1), 3), round(y_cal.to_value(py0), 3)],
            "y_misfit_px": y_cal.misfit_px,
            "groups": groups_meta,
            "kind": "boxplots",
        },
        "extracted_data": {
            "y_tick_misfit_px": y_cal.misfit_px,
            "mean_dot_by_stage": summary_means,
        },
    }
