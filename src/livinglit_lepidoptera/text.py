"""Source text for anchors (02-audit, Anchors and origins; Quote matching).

Text is extracted twice (pdftotext and PyMuPDF) and kept in memory only; nothing
extracted is written to disk. A quote is found if any of its variants is in
either extractor's normalized text.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
from functools import lru_cache
from pathlib import Path

KEPT_SIGNS = set("+−±<>=≤≥/%.×")
MINUS_LIKE = dict.fromkeys(map(ord, "−‒﹣－"), "−")
LINE_BREAK_HYPHEN = re.compile(r"[-‐­]\s*\n\s*")
TEXT_SUFFIXES = (".pdf", ".docx", ".txt", ".md", ".xml")
GREEK_AS_LATIN = {"α": "a", "β": "b", "γ": "g", "δ": "d", "ε": "e", "κ": "k", "λ": "l", "µ": "m", "μ": "m",
                  "σ": "s", "τ": "t", "θ": "q", "Δ": "d", "χ": "c", "ω": "w", "η": "h", "π": "p", "ρ": "r",
                  "φ": "f", "ψ": "y", "ν": "n", "ζ": "z", "ξ": "x", "ι": "i", "ο": "o", "υ": "u", "Ω": "w"}


class SourceUnavailable(Exception):
    """The source file is missing or cannot be read as text."""


def is_greek_or_micro(ch: str) -> bool:
    return ch in "µμ" or "Ͱ" <= ch <= "Ͽ" or "ἀ" <= ch <= "῿"


def normalize(s: str) -> str:
    """NFKC, line-break hyphens joined, lower case; keep alphanumerics and the signs that change meaning."""
    s = s.replace("µ", "μ")
    s = unicodedata.normalize("NFKC", s)
    s = LINE_BREAK_HYPHEN.sub("", s)
    s = s.translate(MINUS_LIKE).lower()
    s = re.sub(r"(?<=[+/])[-–]|[-–](?=/)", "−", s)
    return "".join(ch for ch in s if ch.isalnum() or ch in KEPT_SIGNS)


def quote_variants(quote: str) -> set[str]:
    """Greek and µ dropped; Greek as Latin letters (µ→m); µ→u (02-audit, Quote matching)."""
    dropped = "".join(ch for ch in quote if not is_greek_or_micro(ch))
    latin = "".join(GREEK_AS_LATIN.get(ch, ch) for ch in quote)
    micro_u = "".join("u" if ch in "µμ" else GREEK_AS_LATIN.get(ch, ch) for ch in quote)
    out = {normalize(quote), normalize(dropped), normalize(latin), normalize(micro_u)}
    if "×" in quote:  # fonts that extract the times sign as '3'
        out |= {q.replace("×", "3") for q in list(out)}
    return {q for q in out if q}


def _text_variants(t: str) -> tuple[str, ...]:
    return (t, "".join(ch for ch in t if not is_greek_or_micro(ch)))


def quote_in_texts(quote: str, texts) -> bool:
    qs = quote_variants(quote)
    return any(q in tv for t in texts for tv in _text_variants(t) for q in qs)


def _pdftotext(path: Path) -> str | None:
    exe = shutil.which("pdftotext")
    if exe is None:
        return None
    r = subprocess.run([exe, "-q", str(path), "-"], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return r.stdout


def _pymupdf(path: Path) -> str:
    import pymupdf
    with pymupdf.open(str(path)) as doc:
        return "\n".join(page.get_text() for page in doc)


def _xml_text(path: Path) -> str:
    import xml.etree.ElementTree as ET
    root = ET.parse(str(path)).getroot()
    return " ".join(t.strip() for t in root.itertext() if t and t.strip())


def extract_texts(path: Path) -> list[str]:
    path = Path(path)
    if not path.is_file():
        raise SourceUnavailable(f"source file missing: {path}")
    suf = path.suffix.lower()
    if suf in (".txt", ".md"):
        return [path.read_text(encoding="utf-8", errors="replace")]
    if suf == ".xml":
        return [_xml_text(path)]
    if suf == ".pdf":
        texts = [_pymupdf(path)]
        pt = _pdftotext(path)
        if pt:
            texts.insert(0, pt)
        return texts
    if suf == ".docx":
        import docx
        d = docx.Document(str(path))
        parts = [p.text for p in d.paragraphs]
        for table in d.tables:
            for row in table.rows:
                parts += [c.text for c in row.cells]
        return ["\n".join(parts)]
    raise SourceUnavailable(f"no text extractor for {suf}")


@lru_cache(maxsize=256)
def _normalized(path: Path, _mtime: int) -> tuple[str, ...]:
    out = []
    for t in extract_texts(path):
        if t:
            n = normalize(t)
            out.append(n)
    return tuple(out)


def normalized_texts(path: Path) -> tuple[str, ...]:
    path = Path(path)
    if not path.is_file():
        raise SourceUnavailable(f"source file missing: {path}")
    return _normalized(path, path.stat().st_mtime_ns)


def source_files(paper_dir: Path) -> list[Path]:
    paper_dir = Path(paper_dir)
    if not paper_dir.is_dir():
        return []
    return sorted(p for p in paper_dir.iterdir() if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES)


def find_quote(quote: str, paper_dir: Path, files: list[str] | None = None) -> str | None:
    """The file whose text contains the quote (either extractor, any variant), or None."""
    for f in source_files(paper_dir):
        if files and f.name not in files:
            continue
        if quote_in_texts(quote, normalized_texts(f)):
            return f.name
    return None


def word_count(quote: str) -> int:
    return len(quote.split())
