"""Fig. 1E-H (PLOS Biology, Colias eurytheme): four top-down SEM panels of scale ridges.

Scale bar in each panel (bottom-left white bar) = 2 um (Fig 1 caption).
Calculates ridge spacing via 2D FFT + 12 perpendicular 1D transects per panel.
"""
from livinglit_lepidoptera.figures.microscopy import detect_scale_bar, measure_periodic_fft, measure_transect_spacing

PANELS = {
    "fig1e_black":    ((979, 926, 1360, 1456),  (20, 50, 360, 460), (0.6, 5.0)),
    "fig1f_orange":   ((1370, 926, 1751, 1456), (20, 50, 360, 460), (0.6, 5.0)),
    "uvi_male":       ((1763, 926, 2144, 1456), (20, 50, 360, 460), (0.5, 3.0)),
    "spatulate_male": ((2155, 926, 2547, 1456), (25, 10, 365, 475), (2.0, 6.0)),
}


def read(fig):
    img, _ = fig.render()
    groups = {}
    for label, ((x0, y0, x1, y1), roi, srange) in PANELS.items():
        panel = img[y0:y1, x0:x1]
        cal = detect_scale_bar(panel, (5, 480, 150, 528), physical_um=2.0, polarity="bright")
        fft_r = measure_periodic_fft(panel, cal, roi, spacing_range_um=srange, wavevector_angle_deg=(75, -75))
        tr_r = measure_transect_spacing(panel, cal, roi, fft_r["wavevector_deg"], fft_r["spacing_px"], n_transects=12)
        pts = [
            {"value": t["value"], "lo": t["lo"], "hi": t["hi"],
             "at": [float(x0 + (roi[0] + roi[2]) / 2), float(y0 + roi[1] + t["y_frac"] * (roi[3] - roi[1]))]}
            for t in tr_r["transects"]
        ]
        groups[label] = {
            "points": pts,
            "countable": True,
            "bar": {"mean": [fft_r["spacing_um"], fft_r["lo_um"], fft_r["hi_um"]]},
        }
    return {"groups": groups}
