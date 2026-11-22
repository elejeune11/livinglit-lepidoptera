"""Shared parts for reading figures (02-audit, Reading figures; CONTRIBUTING, Fixed rules).

Offered, not imposed: vector objects and markers, raster colour masks and blobs,
axis calibration from matched tick labels, intervals, overlays. Nothing about a
particular figure lives here: crops, pages, colours, group labels and axis ranges
belong to each paper's own scripts. Page renders go to a temporary folder outside
the repository and are deleted.
"""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

VECTOR_UNCERTAINTY_PT = 0.5
RASTER_UNCERTAINTY_PX_300DPI = 0.6


@dataclass
class Calibration:
    """A linear (or log) map from page coordinate to axis value, fitted to matched tick marks."""
    slope: float
    intercept: float
    residual: float
    log: bool = False

    def value(self, pos: float) -> float:
        v = self.slope * pos + self.intercept
        return 10 ** v if self.log else v

    def interval(self, pos: float, uncertainty: float) -> tuple[float, float]:
        a, b = self.value(pos - uncertainty), self.value(pos + uncertainty)
        return min(a, b), max(a, b)


def calibrate(marks: list[tuple[float, float]], log: bool = False) -> Calibration:
    """Least-squares fit of axis value against page position from ≥2 (position, value) tick marks."""
    if len(marks) < 2:
        raise ValueError("axis calibration needs at least two tick marks")
    pos = np.array([m[0] for m in marks], float)
    val = np.array([np.log10(m[1]) if log else m[1] for m in marks], float)
    A = np.vstack([pos, np.ones_like(pos)]).T
    (s, c), *_ = np.linalg.lstsq(A, val, rcond=None)
    res = float(np.max(np.abs(A @ np.array([s, c]) - val))) if len(marks) > 2 else 0.0
    return Calibration(float(s), float(c), res, log)


def point(cal: Calibration, pos: float, uncertainty: float, at: tuple[float, float], x=None) -> dict:
    """A reading with its interval and page position, in the shape read() returns."""
    v = cal.value(pos)
    lo, hi = cal.interval(pos, uncertainty)
    d = {"value": v, "lo": min(lo, v), "hi": max(hi, v), "at": [float(at[0]), float(at[1])]}
    if x is not None:
        d["x"] = x
    return d


def _overlaps(r, crop, tol: float = 0.01) -> bool:
    """Rectangles overlap, counting zero-width or zero-height ones (lines)."""
    x0, y0, x1, y1 = r
    a0, b0, a1, b1 = crop
    return x1 >= a0 - tol and x0 <= a1 + tol and y1 >= b0 - tol and y0 <= b1 + tol


IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")


class FigureSource:
    """One page region of a source PDF, or a crop of a raster microscopy image."""

    def __init__(self, pdf: Path, page: int, crop: tuple[float, float, float, float]):
        self.pdf, self.page_no, self.crop = Path(pdf), page, tuple(crop)
        self._tmp = None
        self._doc = None
        self.page = None
        self.rect = None
        self._img = None
        if self.pdf.suffix.lower() in IMAGE_SUFFIXES:
            import cv2
            bgr = cv2.imread(str(self.pdf), cv2.IMREAD_COLOR)
            if bgr is None:
                raise ValueError(f"could not open image {self.pdf}")
            rgb = bgr[:, :, ::-1]
            h, w = rgb.shape[:2]
            x0, y0, x1, y1 = self.crop
            if x1 <= x0 or y1 <= y0:
                x0, y0, x1, y1 = 0, 0, w, h
                self.crop = (0.0, 0.0, float(w), float(h))
            x0i, y0i = max(0, int(round(x0))), max(0, int(round(y0)))
            x1i, y1i = min(w, int(round(x1))), min(h, int(round(y1)))
            self._img = rgb[y0i:y1i, x0i:x1i].copy()
        else:
            import pymupdf
            self._doc = pymupdf.open(str(pdf))
            self.page = self._doc[page - 1]
            self.rect = pymupdf.Rect(*crop)

    def close(self):
        if self._doc is not None:
            self._doc.close()
        if self._tmp:
            shutil.rmtree(self._tmp, ignore_errors=True)

    # vector
    def drawings(self) -> list[dict]:
        """Vector paths inside the crop (PyMuPDF get_drawings), each with rect, fill, color and items."""
        if self.page is None:
            return []
        return [d for d in self.page.get_drawings() if _overlaps(tuple(d["rect"]), self.crop)]

    def words(self) -> list[tuple]:
        """Words inside the crop: (x0, y0, x1, y1, text)."""
        if self.page is None:
            return []
        return [(w[0], w[1], w[2], w[3], w[4]) for w in self.page.get_text("words") if _overlaps(tuple(w[:4]), self.crop)]

    def markers(self, max_size: float = 8.0, fill=None, tol: float = 0.08) -> list[tuple[float, float]]:
        """Centres of small closed vector shapes (markers), optionally of one fill colour (RGB 0–1)."""
        out = []
        for d in self.drawings():
            r = d["rect"]
            if r.width <= max_size and r.height <= max_size and r.width > 0.3 and r.height > 0.3:
                if fill is not None:
                    f = d.get("fill")
                    if f is None or max(abs(a - b) for a, b in zip(f, fill)) > tol:
                        continue
                out.append(((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))
        return sorted(set((round(x, 3), round(y, 3)) for x, y in out))

    def tick_marks(self, axis: str = "y", near: float | None = None, tol: float = 30) -> list[tuple[float, float]]:
        """(position, value) for numeric words, as candidates for calibration; the script chooses which to use."""
        out = []
        for x0, y0, x1, y1, t in self.words():
            try:
                v = float(t.replace("−", "-").replace(",", ""))
            except ValueError:
                continue
            pos = (y0 + y1) / 2 if axis == "y" else (x0 + x1) / 2
            other = (x0 + x1) / 2 if axis == "y" else (y0 + y1) / 2
            if near is None or abs(other - near) <= tol:
                out.append((pos, v))
        return out

    # raster
    def render(self, dpi: int = 300) -> tuple[np.ndarray, float]:
        """An RGB array of the crop (native pixels for raster images, dpi render for PDFs); and px per coordinate unit."""
        if self._img is not None:
            return self._img.copy(), 1.0
        import pymupdf
        if self._tmp is None:
            self._tmp = tempfile.mkdtemp(prefix="livinglit_render_")
        pix = self.page.get_pixmap(clip=self.rect, dpi=dpi)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
        return arr.copy(), dpi / 72.0

    def to_page(self, px: float, py: float, scale: float) -> tuple[float, float]:
        return self.crop[0] + px / scale, self.crop[1] + py / scale


def colour_mask(img: np.ndarray, rgb: tuple[int, int, int], tol: int = 40) -> np.ndarray:
    """Pixels within tol of an RGB colour."""
    d = np.abs(img.astype(int) - np.array(rgb, int)).max(axis=2)
    return d <= tol


def dark_mask(img: np.ndarray, threshold: int = 100) -> np.ndarray:
    return img.astype(int).mean(axis=2) < threshold


def blobs(mask: np.ndarray, min_area: int = 4, max_area: int = 10_000) -> list[dict]:
    """Connected components of a mask: centroid (px), area, bounding box; markers that stand alone."""
    import cv2
    n, lab, stats, cents = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    out = []
    for i in range(1, n):
        a = int(stats[i, cv2.CC_STAT_AREA])
        if min_area <= a <= max_area:
            out.append({"x": float(cents[i][0]), "y": float(cents[i][1]), "area": a,
                        "box": [int(stats[i, 0]), int(stats[i, 1]), int(stats[i, 2]), int(stats[i, 3])]})
    return out


def overlay(source: FigureSource, readings: list[dict], out_dir: Path) -> Path:
    """Draw every reading over the figure. Overlays stay outside the repository (out_dir must be outside it)."""
    import cv2
    from .. import ROOT
    out_dir = Path(out_dir)
    if ROOT in out_dir.resolve().parents or out_dir.resolve() == ROOT:
        raise ValueError("overlays are kept out of the repository")
    img, scale = source.render(150)
    img = np.ascontiguousarray(img[:, :, ::-1])
    for r in readings:
        if "at" in r:
            x = int((r["at"][0] - source.crop[0]) * scale)
            y = int((r["at"][1] - source.crop[1]) * scale)
            cv2.circle(img, (x, y), 4, (0, 0, 255), 1)
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{source.pdf.stem}_p{source.page_no}_overlay.png"
    cv2.imwrite(str(p), img)
    return p
