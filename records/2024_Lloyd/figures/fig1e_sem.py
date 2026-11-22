"""Fig. 1E (Nature Communications, Heliconius sara): top-down SEM of iridescent scale ridges."""
from livinglit_lepidoptera.figures.microscopy import detect_scale_bar, measure_periodic_fft, measure_transect_spacing


def read(fig):
    panel, _ = fig.render()
    cal = detect_scale_bar(panel, (350, 445, 495, 492), physical_um=2.0, polarity="bright")
    roi = (60, 50, 440, 430)
    fft_r = measure_periodic_fft(panel, cal, roi, spacing_range_um=(0.4, 2.0), wavevector_angle_deg=(65, -65))
    tr_r = measure_transect_spacing(panel, cal, roi, fft_r["wavevector_deg"], fft_r["spacing_px"], n_transects=12)
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
            "blue_cover_sem": {
                "points": pts,
                "countable": True,
                "bar": {"mean": [fft_r["spacing_um"], fft_r["lo_um"], fft_r["hi_um"]]},
            }
        }
    }
