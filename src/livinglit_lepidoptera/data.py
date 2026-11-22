"""Values taken from released data, a checked cache (02-audit, Readings and data are stored as a checked cache).

Each data.yaml row names a file, sheet and cell; every audit reads the cell again
and the stored value must come back exactly. Nothing read is written anywhere
but the record's data.yaml.
"""
from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

from .models import DataValue

CELL = re.compile(r"^([A-Z]+)(\d+)$")


def as_stored(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() and abs(v) < 1e15 else repr(v)
    if isinstance(v, int):
        return str(v)
    return str(v).strip()


def col_letters(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


@lru_cache(maxsize=64)
def sheet_cells(path: str, sheet: str | None, _mtime: int) -> dict[str, str]:
    p = Path(path)
    suf = p.suffix.lower()
    cells: dict[str, str] = {}
    if suf in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(p, data_only=True, read_only=True)
        ws = wb[sheet] if sheet else wb.worksheets[0]
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None and getattr(c, "coordinate", None):
                    cells[c.coordinate] = as_stored(c.value)
        wb.close()
    elif suf == ".xls":
        import xlrd
        wb = xlrd.open_workbook(str(p))
        ws = wb.sheet_by_name(sheet) if sheet else wb.sheet_by_index(0)
        for r in range(ws.nrows):
            for c in range(ws.ncols):
                v = ws.cell_value(r, c)
                if v not in (None, ""):
                    cells[f"{col_letters(c + 1)}{r + 1}"] = as_stored(v)
    elif suf == ".xlsb":
        from pyxlsb import open_workbook
        with open_workbook(str(p)) as wb:
            with wb.get_sheet(sheet or wb.sheets[0]) as ws:
                for row in ws.rows():
                    for c in row:
                        if c.v is not None:
                            cells[f"{col_letters(c.c + 1)}{c.r + 1}"] = as_stored(c.v)
    elif suf in (".csv", ".tsv", ".txt"):
        delim = "\t" if suf != ".csv" else ","
        with open(p, newline="", encoding="utf-8", errors="replace") as f:
            for r, row in enumerate(csv.reader(f, delimiter=delim), start=1):
                for c, v in enumerate(row, start=1):
                    if v != "":
                        cells[f"{col_letters(c)}{r}"] = v.strip()
    else:
        raise ValueError(f"no reader for {suf} data files")
    return cells


def xlsb_sheets(path: str) -> list[str]:
    from pyxlsb import open_workbook
    with open_workbook(path) as wb:
        return list(wb.sheets)


def read_cell(paper_dir: Path, file: str, sheet: str | None, cell: str) -> str:
    p = Path(paper_dir) / file
    if not p.is_file():
        raise FileNotFoundError(f"data file missing: {file}")
    return sheet_cells(str(p), sheet, p.stat().st_mtime_ns).get(cell, "")


def check_rows(rows: list[DataValue], paper_dir: Path) -> list[str]:
    """Every stored value must come back exactly from its cell."""
    probs = []
    for i, r in enumerate(rows):
        if not CELL.match(r.cell):
            probs.append(f"data[{i}]: cell {r.cell!r} is not a single cell like B7")
            continue
        try:
            got = read_cell(paper_dir, r.file, r.sheet, r.cell)
        except (FileNotFoundError, KeyError, ValueError) as e:
            probs.append(f"data[{i}] {r.item}/{r.group}: {e}")
            continue
        if got != r.value:
            probs.append(f"data[{i}] {r.item}/{r.group} {r.file}!{r.sheet or ''}!{r.cell}: stored {r.value!r}, cell holds {got!r}")
    return probs
