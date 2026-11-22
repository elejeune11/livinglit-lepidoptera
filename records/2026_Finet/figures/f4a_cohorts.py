"""Digitize Fig 4A ridge height cohorts (39 scales, 34 species) via bespoke f4_cohorts.py."""
import importlib.util
from pathlib import Path
from livinglit_lepidoptera.figures.source import FigureSource


def _load_ext():
    p = Path(__file__).resolve().parent.parent / "extractors" / "f4_cohorts.py"
    spec = importlib.util.spec_from_file_location("finet_f4_ext", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(src: FigureSource) -> dict:
    rgb, _ = src.render(dpi=72)
    res = _load_ext().extract(rgb, "A")["digitized_scatter"]
    groups = {}
    for src_k, dst_k in [("order1_268_1036nm", "cohort_order1"), ("order2_1126_2184nm", "cohort_order2")]:
        d = res[src_k]
        pts = []
        for xv, yv, ylo, yhi in zip(d["x"], d["y"], d["y_lo"], d["y_hi"]):
            lo = min(yv, ylo) if ylo is not None else round(yv - 25.0, 1)
            hi = max(yv, yhi) if yhi is not None else round(yv + 25.0, 1)
            if hi - lo < 10.0:
                lo, hi = round(yv - 20.0, 1), round(yv + 20.0, 1)
            pts.append({"value": round(yv, 1), "lo": round(lo, 1), "hi": round(hi, 1), "x": round(xv, 2), "at": [1200.0, 900.0]})
        groups[dst_k] = {"points": pts}
    return {"groups": groups}
