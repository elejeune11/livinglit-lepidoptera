"""Digitize Fig 2E ridge spacing scatter points (blue vs black scales) using bespoke f2_morphometrics."""
import importlib.util
from pathlib import Path
from livinglit_lepidoptera.figures.source import FigureSource


def _load_ext():
    p = Path(__file__).resolve().parent.parent / "extractors" / "f2_morphometrics.py"
    spec = importlib.util.spec_from_file_location("lloyd_f2_ext", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(src: FigureSource) -> dict:
    rgb, _ = src.render(dpi=72)
    res = _load_ext().extract(rgb, "E")["digitized_scatter"]
    groups = {}
    for src_k, dst_k in [("blue_iridescent", "blue_all"), ("black_noniridescent", "black_all")]:
        d = res[src_k]
        groups[dst_k] = {
            "points": [
                {"value": xv, "lo": round(xv - 0.02, 4), "hi": round(xv + 0.02, 4), "at": [260.0, 270.0]}
                for xv in d["x"]
            ]
        }
    return {"groups": groups}
