"""Scraper, JATS XML availability scanner, and unified Data & Code Hub builder (`livinglit harvest`).

Discovers supplemental files, external dataset repositories (Zenodo, Figshare, OSF, Dryad, eLife),
and analysis code from JATS XML; validates `records/<paper>/resources.yaml`; and parses harvested
tabular datasets, synchrotron SAXS `.dat` curves, `.xlsx` developmental measurements, `.mat` surface
profiles, and R/MATLAB/Mathematica analysis scripts into unified machine-readable tables under
`releases/<tag>/`.
"""
from __future__ import annotations

import ast
import csv
import io
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import openpyxl
import scipy.io as sio
import yaml

from . import PAPERS_DIR, RECORDS_DIR, RELEASES_DIR
from .panels import ResourcesFile


REPO_PATTERNS = [
    ("Zenodo", re.compile(r"(?:zenodo\.org/records?/|10\.5281/zenodo\.)(\d+)", re.I)),
    ("Figshare", re.compile(r"(?:figshare\.com|10\.6084/m9\.figshare\.[\w.]*|10\.15131/shef\.data\.[\w.]*)", re.I)),
    ("OSF", re.compile(r"osf\.io/([a-z0-9]{5})", re.I)),
    ("Dryad", re.compile(r"(?:datadryad\.org|10\.5061/dryad\.[\w.]+)", re.I)),
    ("eLife_CDN", re.compile(r"10\.7554/eLife\.(\d+)", re.I)),
]


def scan_jats_resources(paper: str, papers_dir: Path = PAPERS_DIR) -> dict[str, Any]:
    """Scan JATS XML for <supplementary-material>, <ext-link>, <media>, and Data/Code Availability text."""
    pdir = papers_dir / paper
    xmls = sorted(pdir.glob("*.xml"))
    if not xmls:
        return {"paper": paper, "xml": None, "links": [], "availability_notes": []}
    root = ET.parse(str(xmls[0])).getroot()
    xlink = "{http://www.w3.org/1999/xlink}href"
    links: list[dict[str, str]] = []
    seen = set()
    for el in root.findall(f".//*[@{xlink}]"):
        href = el.attrib.get(xlink, "").strip()
        if not href or href in seen or "@" in href:
            continue
        seen.add(href)
        repo = "Publisher_Supplement"
        for rname, pat in REPO_PATTERNS:
            if pat.search(href):
                repo = rname
                break
        links.append({"tag": el.tag, "href": href, "repository_guess": repo})

    notes: list[str] = []
    for sec in root.findall(".//sec"):
        st = "".join(sec.findtext("title") or "").lower()
        sec_type = (sec.attrib.get("sec-type") or "").lower()
        if any(k in st or k in sec_type for k in ("data", "availability", "code", "supplement")):
            txt = " ".join("".join(sec.itertext()).split())
            if txt:
                notes.append(txt[:600])
    return {"paper": paper, "xml": xmls[0].name, "links": links, "availability_notes": notes}


def parse_parnell_saxs_and_spectra(pdir: Path) -> dict[str, Any]:
    """Extract 1D SAXS primary Bragg peaks (d = 2*pi/q*) across 80 files and individual species reflectance curves."""
    si_dir = pdir / "associated" / "parnell_si" / "forupload"
    out: dict[str, Any] = {"saxs_scans": [], "saxs_by_taxon": {}, "spectra_by_taxon": {}}
    if not si_dir.is_dir():
        return out

    taxon_map = {
        "sara": "Heliconius sara",
        "erato": "Heliconius erato cyrbia",
        "cythera": "Heliconius melpomene cythera",
        "eleuchia": "Heliconius eleuchia",
        "cydno": "Heliconius cydno",
        "rosina": "Heliconius melpomene rosina",
        "erato demorphon": "Heliconius erato demophoon",
    }

    saxs_zip = si_dir / "Butterfly SAXS 1d data.zip"
    if saxs_zip.is_file():
        by_tax: dict[str, list[float]] = defaultdict(list)
        sample_curves: dict[str, dict[str, list[float]]] = {}
        with zipfile.ZipFile(saxs_zip) as zf:
            for name in sorted(zf.namelist()):
                if not name.endswith(".dat"):
                    continue
                parts = name.split("/")
                folder = parts[1] if len(parts) > 2 else "unknown"
                species = taxon_map.get(folder, folder)
                lines = zf.read(name).decode(errors="replace").splitlines()
                qs, ints = [], []
                for ln in lines[1:]:
                    sp = ln.strip().split()
                    if len(sp) >= 2:
                        try:
                            q, iv = float(sp[0]), float(sp[1])
                            if q > 0 and iv > 0:
                                qs.append(q)
                                ints.append(iv)
                        except ValueError:
                            pass
                if len(qs) < 20:
                    continue
                qa = np.array(qs)
                ia = np.array(ints)
                # Primary ridge grating peak lies in d = 550..1350 nm => q = 2*pi/d in [0.00465, 0.0114] nm^-1
                # Use Lorentz-corrected intensity I(q) * q^2 minus linear baseline across [0.0048, 0.0112]
                mask = (qa >= 0.0048) & (qa <= 0.0112)
                if np.sum(mask) < 8:
                    continue
                qm = qa[mask]
                im = ia[mask] * (qm ** 2)
                base = im[0] + (im[-1] - im[0]) * (qm - qm[0]) / max(qm[-1] - qm[0], 1e-9)
                resid = im - base
                pk_idx = int(np.argmax(resid))
                if 0 < pk_idx < len(qm) - 1 and resid[pk_idx] > 0:
                    q_star = float(qm[pk_idx])
                    d_nm = 2.0 * math.pi / q_star
                    out["saxs_scans"].append({
                        "file": Path(name).name,
                        "species": species,
                        "q_peak_nm1": round(q_star, 6),
                        "d_spacing_nm": round(d_nm, 2),
                        "d_spacing_um": round(d_nm / 1000.0, 4),
                    })
                    by_tax[species].append(d_nm)
                    if species not in sample_curves:
                        sub_m = (qa >= 0.0042) & (qa <= 0.016)
                        qs_s = qa[sub_m][::3]
                        iq2_s = (ia[sub_m] * (qa[sub_m] ** 2))[::3]
                        iq2_norm = iq2_s / max(float(np.max(iq2_s)), 1e-12)
                        sample_curves[species] = {
                            "q_nm1": [round(float(x), 5) for x in qs_s],
                            "iq2_norm": [round(float(y), 4) for y in iq2_norm],
                            "q_peak_nm1": round(q_star, 5),
                            "d_peak_nm": round(d_nm, 1),
                        }
        for sp_name, vals in by_tax.items():
            arr = np.array(vals)
            out["saxs_by_taxon"][sp_name] = {
                "n_scans": int(len(arr)),
                "mean_nm": round(float(np.mean(arr)), 1),
                "sd_nm": round(float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0, 1),
                "mean_um": round(float(np.mean(arr)) / 1000.0, 4),
                "sample_curve": sample_curves.get(sp_name),
            }

    spec_csv = si_dir / "AP.spec.data.individual.means.csv"
    if spec_csv.is_file():
        with open(spec_csv, encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        hdr = rows[0]
        wls = [float(r[1]) for r in rows[1:]]
        # Subsample every 10 nm (41 points from 300..700 nm) for compact interactive rendering
        step_idx = [i for i, w in enumerate(wls) if int(round(w)) % 10 == 0]
        wl_sub = [int(round(wls[i])) for i in step_idx]
        col_groups: dict[str, list[list[float]]] = defaultdict(list)
        prefix_map = [
            ("cyrbia", "Heliconius erato cyrbia"),
            ("cythera", "Heliconius melpomene cythera"),
            ("demophoon", "Heliconius erato demophoon"),
            ("rosina", "Heliconius melpomene rosina"),
            ("eleuchia", "Heliconius eleuchia"),
            ("cydno", "Heliconius cydno"),
            ("sara", "Heliconius sara"),
        ]
        for ci in range(2, len(hdr)):
            cname = hdr[ci].strip()
            wing = "forewing" if cname.endswith("F") else ("hindwing" if cname.endswith("H") else "wing")
            sp_match = next((full for pref, full in prefix_map if cname.lower().startswith(pref)), None)
            if sp_match:
                vals = [float(rows[1 + idx][ci]) for idx in step_idx]
                col_groups[f"{sp_match}|{wing}"].append(vals)
        for key, mat in col_groups.items():
            arr = np.array(mat)
            sp_name, wing = key.split("|")
            out["spectra_by_taxon"].setdefault(sp_name, {})[wing] = {
                "n_individuals": int(arr.shape[0]),
                "wl_nm": wl_sub,
                "mean_pct": [round(float(x), 3) for x in np.mean(arr, axis=0)],
                "sd_pct": [round(float(x), 3) for x in (np.std(arr, axis=0, ddof=1) if arr.shape[0] > 1 else np.zeros(arr.shape[1]))],
                "peak_pct": round(float(np.max(np.mean(arr, axis=0))), 2),
            }
    return out


def parse_loh_osf(pdir: Path) -> dict[str, Any]:
    """Parse Loh 2025 OSF DataS10 (170 individual scale Fourier ridge spacings) & DataS6 (Bab ChIP DE genes)."""
    assoc = pdir / "associated"
    out: dict[str, Any] = {"interridge_rows": [], "interridge_groups": {}, "bab_targets": []}
    s10 = assoc / "DataS10_Fourier_Interridge_distances_Figure1D.csv"
    if s10.is_file():
        by_grp: dict[str, list[float]] = defaultdict(list)
        with open(s10, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                sg = r["sex_genotype"].strip()
                st = r["scale_type"].strip()
                val = float(r["Fourier_Inter-Ridge_distance_in_micrometers"])
                out["interridge_rows"].append({"sex_genotype": sg, "scale_type": st, "spacing_um": round(val, 4)})
                by_grp[f"{sg} | {st}"].append(val)
        for k, vs in by_grp.items():
            arr = np.array(vs)
            out["interridge_groups"][k] = {
                "n": int(len(arr)),
                "mean_um": round(float(np.mean(arr)), 4),
                "sd_um": round(float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0, 4),
                "min_um": round(float(np.min(arr)), 4),
                "max_um": round(float(np.max(arr)), 4),
                "values_um": [round(float(x), 4) for x in sorted(arr)],
            }
    s6 = assoc / "DataS6_DE_Scale3_3BabPeaksorMore.csv"
    if s6.is_file():
        with open(s6, encoding="utf-8") as fh:
            rd = csv.reader(fh)
            next(rd, None)
            for r in rd:
                if len(r) >= 10:
                    out["bab_targets"].append({
                        "gene_id": r[0],
                        "symbol": r[8],
                        "product": r[9].replace("_", " "),
                        "log2FC": round(float(r[2]), 3),
                        "p_adj": float(r[5]),
                        "bab_chip_peaks": int(float(r[6])),
                    })
    return out


def parse_seah_elife(pdir: Path) -> dict[str, Any]:
    """Parse Seah 2023 eLife CK-666 Arp2/3 honeycomb lattice height measurements (N=274)."""
    xf = pdir / "associated" / "elife-89082-fig4-figsupp5-data1.xlsx"
    out: dict[str, Any] = {"rows": [], "groups": {}}
    if not xf.is_file():
        return out
    wb = openpyxl.load_workbook(xf, data_only=True)
    by_grp: dict[str, list[float]] = defaultdict(list)
    for sn in wb.sheetnames:
        sp = "Parides eurimedes" if "eurimedes" in sn else "Parides iphidamas"
        for r in list(wb[sn].iter_rows(values_only=True))[4:]:
            if r and isinstance(r[0], str) and isinstance(r[1], (int, float)):
                trt = r[0].strip()
                h_nm = float(r[1])
                out["rows"].append({"species": sp, "treatment": trt, "height_nm": round(h_nm, 2), "height_um": round(h_nm / 1000.0, 4)})
                by_grp[f"{sp} | {trt}"].append(h_nm)
    for k, vs in by_grp.items():
        arr = np.array(vs)
        out["groups"][k] = {
            "n": int(len(arr)),
            "mean_nm": round(float(np.mean(arr)), 1),
            "sd_nm": round(float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0, 1),
            "values_nm": [round(float(x), 1) for x in sorted(arr)],
        }
    return out


def parse_mcdougal_and_totz(papers_dir: Path = PAPERS_DIR) -> dict[str, Any]:
    """Parse McDougal 2021 live pupal scale growth (.xlsx) and Totz 2024 experimental buckling profiles (.mat)."""
    out: dict[str, Any] = {"mcdougal_scales": [], "totz_buckling": []}
    xf = papers_dir / "2021_McDougal" / "associated" / "measured_A40ScaleMeasurements.xlsx"
    if xf.is_file():
        wb = openpyxl.load_workbook(xf, data_only=True)
        grouped: dict[tuple, dict[str, Any]] = {}
        for sname in ["Sheet1", "Sheet1 (Old)"]:
            if sname not in wb.sheetnames:
                continue
            for r in list(wb[sname].iter_rows(values_only=True))[1:]:
                if not r or r[2] is None or r[4] is None or r[5] is None:
                    continue
                key = (str(r[2]).strip(), str(r[3]).strip(), float(r[4]))
                rec = grouped.setdefault(key, {"scale_type": key[0], "scale_id": key[1], "age_days": key[2]})
                mtype = str(r[5]).strip()
                val = r[6]
                if mtype in ("Point 1", "Point 2") and isinstance(val, str) and val.startswith("["):
                    rec[mtype] = ast.literal_eval(val)
                elif mtype == "Width" and isinstance(val, (int, float)):
                    rec["width_um"] = round(float(val), 2)
                elif mtype == "Half width" and isinstance(val, (int, float)) and "width_um" not in rec:
                    rec["width_um"] = round(2.0 * float(val), 2)
                elif mtype == "Thickness" and isinstance(val, (int, float)):
                    rec["thickness_um"] = round(float(val), 2)
        for rec in sorted(grouped.values(), key=lambda d: (d["scale_type"], d["age_days"], d["scale_id"])):
            if "Point 1" in rec and "Point 2" in rec:
                p1, p2 = np.array(rec.pop("Point 1")), np.array(rec.pop("Point 2"))
                rec["length_um"] = round(float(np.linalg.norm(p2 - p1)), 2)
            else:
                rec.pop("Point 1", None)
                rec.pop("Point 2", None)
            out["mcdougal_scales"].append(rec)

    tz_zip = papers_dir / "2024_Totz" / "associated" / "plate_mechanics_code.zip"
    if tz_zip.is_file():
        with zipfile.ZipFile(tz_zip) as zf:
            raw = zf.read("bzjan-butterfly_scale_mechanics-7fdc6f9/experimental_data/meanProfileDataExperiment.mat")
            mat = sio.loadmat(io.BytesIO(raw), squeeze_me=True)["data"]
            ages = np.atleast_1d(mat["percentAge"].item())
            means = mat["meanProfile"].item()
            stds = mat["stdProfile"].item()
            xs = mat["scaledX"].item()
            ns = mat["N"].item()
            for i in range(len(ages)):
                xv = np.atleast_1d(xs[i]).astype(float)
                yv = np.atleast_1d(means[i]).astype(float)
                sv = np.atleast_1d(stds[i]).astype(float)
                step = max(1, len(xv) // 50)
                out["totz_buckling"].append({
                    "pupal_pct": round(float(ages[i]), 2),
                    "n_ridges": int(np.sum(ns[i])),
                    "scaled_x": [round(float(x), 4) for x in xv[::step]],
                    "mean_height_nm": [round(float(y) * 1000.0, 3) for y in yv[::step]],
                    "sd_height_nm": [round(float(s) * 1000.0, 3) for s in sv[::step]],
                    "peak_to_trough_nm": round(float(np.max(yv) - np.min(yv)) * 1000.0, 2),
                })
    return out


def parse_code_registry(papers_dir: Path = PAPERS_DIR) -> list[dict[str, Any]]:
    """Inspect harvested R, MATLAB, and Mathematica analysis scripts across the corpus."""
    registry: list[dict[str, Any]] = []

    # 1. Lloyd 2024 R scripts (Sheffield ORDA / Figshare)
    lloyd_assoc = papers_dir / "2024_Lloyd" / "associated"
    lloyd_fig_map = {
        "SEM_ANALYSIS_LLOYD_2024.R": ["F2/D", "F2/E", "F2/F"],
        "CONFOCAL_ANALYSIS_2024.R": ["F2/J", "F2/K", "F2/L", "F3/*"],
        "SPECTROMETRY_ANALYSIS_CYTO_D_LLOYD_2024.R": ["F8/E"],
        "RIDGE_NUMBER_CYTO_D_LLOYD_2024.R": ["F8/N"],
        "CURVATURE_ANALYSIS_CYTO_D_LLOYD_2024.R": ["F8/O"],
        "AFM_ANALYSIS_CYTO_D_LLOYD_2024.R": ["Supp_AFM"],
        "SEM_ANALYSIS_DEMOPHOON_LLOYD_2024.R": ["Supp_Demophoon"],
    }
    if lloyd_assoc.is_dir():
        for rf in sorted(lloyd_assoc.glob("*.R")):
            txt = rf.read_text(errors="replace")
            libs = sorted(set(re.findall(r"library\(([\w.]+)\)", txt)))
            csvs = sorted(set(re.findall(r"read\.csv\(['\"]([^'\"]+)['\"]", txt)))
            models = [m.strip() for m in re.findall(r"((?:lmer|glmer|lm|aov|t\.test|wilcox\.test)\([^)]+\))", txt)[:5]]
            registry.append({
                "paper": "2024_Lloyd",
                "script": rf.name,
                "language": "R",
                "bytes": rf.stat().st_size,
                "lines": len(txt.splitlines()),
                "packages": libs,
                "referenced_inputs": [Path(c).name for c in csvs],
                "inputs_in_repo": False,
                "recovered_by_digitizer": lloyd_fig_map.get(rf.name, []),
                "models_or_ops": models,
            })

    # 2. Parnell 2018 R scripts (Royal Society Figshare)
    p_si = papers_dir / "2018_Parnell" / "associated" / "parnell_si" / "forupload"
    if p_si.is_dir():
        for rf in sorted(p_si.glob("*.[rR]")):
            txt = rf.read_text(errors="replace")
            libs = sorted(set(re.findall(r"library\(([\w.]+)\)", txt)))
            csvs = sorted(set(re.findall(r"read\.csv\(['\"]([^'\"]+)['\"]", txt)))
            registry.append({
                "paper": "2018_Parnell",
                "script": rf.name,
                "language": "R",
                "bytes": rf.stat().st_size,
                "lines": len(txt.splitlines()),
                "packages": libs,
                "referenced_inputs": [Path(c).name for c in csvs],
                "inputs_in_repo": True,
                "recovered_by_digitizer": ["F3/*", "F11/*"] if "Pavo" in rf.name else ["F3/*"],
                "models_or_ops": ["pavo::vismodel + coldist (Vorobyev-Osorio receptor noise JNDs)"] if "Pavo" in rf.name else ["angle-resolved spectral plotting"],
            })

    # 3. McDougal 2021 MATLAB scripts (Zenodo)
    m_assoc = papers_dir / "2021_McDougal" / "associated"
    if m_assoc.is_dir():
        for mf in sorted(m_assoc.glob("*.m")):
            if mf.name in ("twilight.m", "ice2.m", "color3d.m"):
                continue
            txt = mf.read_text(errors="replace")
            figs = [mf.stem.replace("make", "")] if mf.name.startswith("makeFig") else ["pipeline_helper"]
            registry.append({
                "paper": "2021_McDougal",
                "script": mf.name,
                "language": "MATLAB",
                "bytes": mf.stat().st_size,
                "lines": len(txt.splitlines()),
                "packages": ["Signal Processing", "Image Processing"],
                "referenced_inputs": sorted(set(re.findall(r"['\"]([\w\-*]+\.(?:mat|xlsx|tif))['\"]", txt)))[:4],
                "inputs_in_repo": True,
                "recovered_by_digitizer": figs,
                "models_or_ops": [ln.strip("% ").strip() for ln in txt.splitlines()[:3] if ln.strip().startswith("%")][:2],
            })

    # 4. Totz 2024 Mathematica + MATLAB scripts (Zenodo)
    tz_assoc = papers_dir / "2024_Totz" / "associated"
    if (tz_assoc / "plate_mechanics_code.zip").is_file():
        registry.append({
            "paper": "2024_Totz",
            "script": "butterfly_scale_mechanics.nb + 86 MATLAB scripts",
            "language": "Mathematica / MATLAB",
            "bytes": (tz_assoc / "plate_mechanics_code.zip").stat().st_size + (tz_assoc / "buckling_data_proc.zip").stat().st_size,
            "lines": 1450,
            "packages": ["Wolfram Mathematica", "MATLAB Curve Fitting"],
            "referenced_inputs": ["meanProfileDataExperiment.mat", "scale*-3D_meas.mat"],
            "inputs_in_repo": True,
            "recovered_by_digitizer": ["Fig1_unwrapped", "Fig3_buckling_profiles"],
            "models_or_ops": ["Föppl–von Kármán elastic plate buckling on Winkler foundation"],
        })
    return registry


def _parse_genomic_row_block(
    raw_rows: list[list[str]],
    gt: Any,
    extra: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Locate header row (scanning up to first 15 rows for Excel title banners) and parse mapped records."""
    if not raw_rows:
        return []
    str_specs = [v for v in gt.columns.values() if isinstance(v, str)]
    hdr_idx = 0
    if str_specs:
        found = None
        for idx, row in enumerate(raw_rows[:15]):
            cells = [c.strip() for c in row]
            if all(s in cells for s in str_specs):
                found = idx
                break
        if found is None:
            for idx, row in enumerate(raw_rows[:15]):
                cells = [c.strip() for c in row]
                if any(s in cells for s in str_specs):
                    found = idx
                    break
        if found is None:
            return []
        hdr_idx = found

    header = [c.strip() for c in raw_rows[hdr_idx]]
    col_idx: dict[str, int] = {}
    for norm_k, spec_col in gt.columns.items():
        if isinstance(spec_col, int):
            col_idx[norm_k] = spec_col
        elif spec_col in header:
            col_idx[norm_k] = header.index(spec_col)

    out: list[dict[str, Any]] = []
    float_keys = ("log2fc", "p_val", "p_adj", "pct_1", "pct_2", "spacing_um", "value", "score")
    int_keys = ("chip_peaks", "n_injected", "n_hatched", "n_emerged", "n_phenotype")
    for r in raw_rows[hdr_idx + 1 :]:
        if col_idx:
            mapped_vals = [r[idx].strip() if idx < len(r) else "" for idx in col_idx.values()]
            if not any(mapped_vals):
                continue
            # Skip trailing notes or separator rows where primary morphometric numeric column is blank/non-numeric
            if gt.kind == "scale_morphometrics":
                num_k = "spacing_um" if "spacing_um" in col_idx else ("value" if "value" in col_idx else None)
                if num_k is not None:
                    raw_num = r[col_idx[num_k]].strip() if col_idx[num_k] < len(r) else ""
                    try:
                        float(raw_num)
                    except ValueError:
                        continue
            rec_row: dict[str, Any] = dict(extra or {})
            for norm_k, idx in col_idx.items():
                val = r[idx].strip() if idx < len(r) else ""
                if norm_k in float_keys:
                    try:
                        rec_row[norm_k] = float(val)
                    except ValueError:
                        rec_row[norm_k] = val
                elif norm_k in int_keys:
                    try:
                        rec_row[norm_k] = int(float(val))
                    except ValueError:
                        rec_row[norm_k] = val
                else:
                    rec_row[norm_k] = val.replace("_", " ") if norm_k == "product" else val
            out.append(rec_row)
        else:
            if not any(c.strip() for c in r):
                continue
            rec_row = dict(extra or {})
            for i in range(len(header)):
                if header[i]:
                    rec_row[header[i]] = r[i].strip() if i < len(r) else ""
            out.append(rec_row)
    return out


def parse_genomic_tables(records_dir: Path, papers_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Schema-driven ingestion of supplemental genomics/genetics/morphometrics CSV/TSV/XLSX files declared in genetics.yaml."""
    from .models import GeneticsFile

    tables_out: list[dict[str, Any]] = []
    relations_out: list[dict[str, Any]] = []
    for gpath in sorted(records_dir.glob("*/genetics.yaml")):
        paper = gpath.parent.name
        gf = GeneticsFile.model_validate(yaml.safe_load(gpath.read_text(encoding="utf-8")))
        for r in gf.relations:
            relations_out.append({"paper": paper, **r.model_dump()})
        for gt in gf.genomic_tables:
            fpath = papers_dir / paper / gt.file
            rows_parsed: list[dict[str, Any]] = []
            if fpath.is_file():
                sfx = fpath.suffix.lower()
                if sfx in (".csv", ".tsv"):
                    delim = "\t" if sfx == ".tsv" else ","
                    with open(fpath, encoding="utf-8-sig") as fh:
                        raw_rows = list(csv.reader(fh, delimiter=delim))
                    rows_parsed.extend(_parse_genomic_row_block(raw_rows, gt))
                elif sfx in (".xlsx", ".xlsm"):
                    wb = openpyxl.load_workbook(fpath, data_only=True, read_only=True)
                    try:
                        multi = len(wb.sheetnames) > 1
                        for sn in wb.sheetnames:
                            ws = wb[sn]
                            sheet_rows = [["" if c is None else str(c).strip() for c in row] for row in ws.iter_rows(values_only=True)]
                            extra = {"sheet": sn} if multi else None
                            rows_parsed.extend(_parse_genomic_row_block(sheet_rows, gt, extra=extra))
                    finally:
                        wb.close()
            tables_out.append({
                "paper": paper,
                "id": gt.id,
                "kind": gt.kind,
                "file": gt.file,
                "title": gt.title,
                "assay": gt.assay,
                "contrast": gt.contrast,
                "stage": gt.stage,
                "taxon": gt.taxon,
                "linked_items": list(gt.linked_items),
                "linked_panels": list(gt.linked_panels),
                "anchor": gt.anchor.model_dump(),
                "note": gt.note,
                "n_rows": len(rows_parsed),
                "rows": rows_parsed,
            })
    return tables_out, relations_out


def build_data_hub(
    tag: str = "data-hub-v1",
    records_dir: Path = RECORDS_DIR,
    papers_dir: Path = PAPERS_DIR,
    releases_dir: Path = RELEASES_DIR,
) -> dict[str, Any]:
    """Build unified data-first release combining digitized figure series, SEM readings, and scraped supplements/code."""
    out_dir = releases_dir / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Collect all resources.yaml, manifest.yaml, and qa/report.json files across active records
    all_resources: dict[str, list[dict]] = {}
    for rf_path in sorted(records_dir.glob("*/resources.yaml")):
        rf = ResourcesFile.model_validate(yaml.safe_load(rf_path.read_text(encoding="utf-8")))
        all_resources[rf.record] = [r.model_dump() for r in rf.resources]

    manifests: dict[str, dict] = {}
    for mf_path in sorted(records_dir.glob("*/manifest.yaml")):
        manifests[mf_path.parent.name] = yaml.safe_load(mf_path.read_text(encoding="utf-8")) or {}

    qa_reports: dict[str, dict] = {}
    for qa_path in sorted(records_dir.glob("*/qa/report.json")):
        qa_reports[qa_path.parent.parent.name] = json.loads(qa_path.read_text(encoding="utf-8"))

    # 2. Collect all digitized panel objects & flat series rows
    all_panels: list[dict] = []
    all_series: list[dict] = []
    for pjson in sorted(records_dir.glob("*/digitized/panels_extracted.json")):
        all_panels.extend(json.loads(pjson.read_text(encoding="utf-8")))
    for scsv in sorted(records_dir.glob("*/digitized/series.csv")):
        with open(scsv, encoding="utf-8") as fh:
            all_series.extend(list(csv.DictReader(fh)))

    # 3. Parse harvested external datasets, generalized genomic tables & code
    parnell_hub = parse_parnell_saxs_and_spectra(papers_dir / "2018_Parnell")
    loh_hub = parse_loh_osf(papers_dir / "2025_Loh")
    seah_hub = parse_seah_elife(papers_dir / "2023_Seah")
    mt_hub = parse_mcdougal_and_totz(papers_dir)
    code_reg = parse_code_registry(papers_dir)
    genomic_tables, genetic_relations = parse_genomic_tables(records_dir, papers_dir)

    # 4. Collect bespoke per-figure Python extractor scripts for auditable code viewing in UI
    extractor_scripts: dict[str, str] = {}
    for ext_py in sorted(records_dir.glob("*/extractors/*.py")):
        rel = f"{ext_py.parent.parent.name}/extractors/{ext_py.name}"
        extractor_scripts[rel] = ext_py.read_text(encoding="utf-8")

    hub = {
        "tag": tag,
        "summary": {
            "n_panel_objects": len(all_panels),
            "n_digitized_series_points": len(all_series),
            "n_custom_extractors": len(extractor_scripts),
            "n_manifests": len(manifests),
            "n_qa_reports": len(qa_reports),
            "n_resource_entries": sum(len(v) for v in all_resources.values()),
            "n_code_scripts_indexed": len(code_reg),
            "n_genetic_relations": len(genetic_relations),
            "n_genomic_tables": len(genomic_tables),
            "n_genomic_table_rows": sum(t["n_rows"] for t in genomic_tables),
            "n_parnell_saxs_scans": len(parnell_hub["saxs_scans"]),
            "n_loh_interridge_scales": len(loh_hub["interridge_rows"]),
            "n_loh_bab_target_genes": len(loh_hub["bab_targets"]),
            "n_seah_honeycomb_measurements": len(seah_hub["rows"]),
            "n_mcdougal_live_scale_timepoints": len(mt_hub["mcdougal_scales"]),
            "n_totz_buckling_stages": len(mt_hub["totz_buckling"]),
        },
        "manifests": manifests,
        "qa_reports": qa_reports,
        "resources": all_resources,
        "code_registry": code_reg,
        "extractor_scripts": extractor_scripts,
        "genetic_relations": genetic_relations,
        "genomic_tables": genomic_tables,
        "parnell": parnell_hub,
        "loh": loh_hub,
        "seah": seah_hub,
        "mcdougal_scales": mt_hub["mcdougal_scales"],
        "totz_buckling": mt_hub["totz_buckling"],
    }

    (out_dir / "data_hub.json").write_text(json.dumps(hub, indent=2), encoding="utf-8")
    (out_dir / "panels_all.json").write_text(json.dumps(all_panels, indent=2), encoding="utf-8")
    if all_series:
        with open(out_dir / "digitized_all_series.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(all_series[0].keys()))
            w.writeheader()
            w.writerows(all_series)
    return hub
