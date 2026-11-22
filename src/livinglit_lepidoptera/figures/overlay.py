"""Overlays for a person to inspect a figure's readings (02-audit, Reading figures).

`figure_overlay(paper, figure, out_dir)` draws every stored reading of one figure at its page position over the
figure's crop, one colour per group, and writes a PNG outside the repository (overlays are never committed).
"""
from __future__ import annotations

from pathlib import Path

from .. import PAPERS_DIR, RECORDS_DIR, ROOT

COLOURS = [(0, 0, 230), (220, 120, 0), (0, 160, 0), (200, 0, 200), (0, 170, 220), (120, 60, 0)]  # BGR


def default_dir() -> Path:
    return ROOT.parent / "livinglit_overlays_dont_commit"


def figure_overlay(paper: str, figure: str, out_dir: Path | None = None, records_dir: Path = RECORDS_DIR,
                   papers_dir: Path = PAPERS_DIR) -> Path:
    import cv2
    import numpy as np
    from ..models import FiguresFile, ReadingsFile
    from ..record import load_yaml
    from .source import FigureSource
    out_dir = Path(out_dir or default_dir() / paper)
    if ROOT in out_dir.resolve().parents or out_dir.resolve() == ROOT:
        raise ValueError("overlays are kept out of the repository")
    d = Path(records_dir) / paper
    e = FiguresFile.model_validate(load_yaml(d / "figures.yaml")).figures[figure]
    rds = [r for r in ReadingsFile.model_validate(load_yaml(d / "readings.yaml")).readings
           if r.figure == figure and r.page_x is not None and r.page_y is not None]
    src = FigureSource(Path(papers_dir) / paper / e.file, e.page, e.crop)
    try:
        img, scale = src.render(150)
    finally:
        src.close()
    img = np.ascontiguousarray(img[:, :, ::-1])
    groups = list(dict.fromkeys(r.group for r in rds))
    for r in rds:
        col = COLOURS[groups.index(r.group) % len(COLOURS)]
        x, y = int((r.page_x - e.crop[0]) * scale), int((r.page_y - e.crop[1]) * scale)
        if r.kind == "point":
            cv2.circle(img, (x, y), 5, col, 2)
        else:
            cv2.line(img, (x - 8, y), (x + 8, y), col, 2)
    for i, g in enumerate(groups):
        cv2.putText(img, str(g), (4, 14 + 14 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.4, COLOURS[i % len(COLOURS)], 1)
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{figure}_overlay.png"
    cv2.imwrite(str(p), img)
    return p
