"""Digitize Fig 8N (ridge number) and Fig 8O (ridge curvature) beeswarms using bespoke f8_cytod."""
import importlib.util
from pathlib import Path
from livinglit_lepidoptera.figures.source import FigureSource


def _load_ext():
    p = Path(__file__).resolve().parent.parent / "extractors" / "f8_cytod.py"
    spec = importlib.util.spec_from_file_location("lloyd_f8_ext", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(src: FigureSource) -> dict:
    sub, _ = src.render(dpi=72)
    ext = _load_ext()
    groups = {}
    rn = ext.extract(sub[:, 2:372], "N")["digitized_scatter"]
    for src_k, dst_k in [("control", "n_ctrl"), ("cyto_d", "n_cyto")]:
        d = rn[src_k]
        groups[dst_k] = {
            "points": [
                {"value": round(yv, 2), "lo": round(yv - 0.8, 2), "hi": round(yv + 0.8, 2), "at": [50.0, 700.0]}
                for yv in d["y"]
            ]
        }
    ro = ext.extract(sub[:, 375:749], "O")["digitized_scatter"]
    for src_k, dst_k in [("control", "k_ctrl"), ("cyto_d", "k_cyto")]:
        d = ro[src_k]
        pts = [
            {"value": round(yv, 5), "lo": round(max(0.0, yv - 0.003), 5), "hi": round(yv + 0.003, 5), "at": [420.0, 700.0]}
            for yv in d["y"]
        ]
        groups[dst_k] = {"points": pts}
    return {"groups": groups}
