"""Fig. 5C (iScience 2026, Morpho didius): top-down SEM of intact unmilled cover scale ridges."""
from livinglit_lepidoptera.figures.microscopy import detect_scale_bar, measure_periodic_fft, measure_transect_spacing


def read(fig):
    panel, _ = fig.render()
    cal = detect_scale_bar(panel, (1177, 850, 1339, 892), physical_um=1.0, polarity="bright")
    roi = (495, 78, 1360, 255)
    fft_r = measure_periodic_fft(panel, cal, roi, spacing_range_um=(0.45, 1.1), wavevector_angle_deg=(-20.0, 20.0))
    tr_r = measure_transect_spacing(panel, cal, roi, fft_r["wavevector_deg"], fft_r["spacing_px"], n_transects=10)
    pts = [
        {
            "value": t["value"],
            "lo": t["lo"],
            "hi": t["hi"],
            "at": [float((roi[0] + roi[2]) / 2), float(roi[1] + t["y_frac"] * (roi[3] - roi[1]))],
        }
        for t in tr_r["transects"]
    ]
    return {
        "groups": {
            "morpho_unmilled_sem": {
                "points": pts,
                "countable": True,
                "bar": {"mean": [fft_r["spacing_um"], fft_r["lo_um"], fft_r["hi_um"]]},
            }
        }
    }
