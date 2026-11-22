# `livinglit-lepidoptera`

> [!WARNING]
> **Work in Progress — Unverified Prototype**
>
> This repository and its interactive visualizer are an **early, experimental work in progress**. All paper records, figure panel segmentations, digitized plot curves/points, calibrated 2D-FFT microscopy readings, gene regulatory network (GRN) edges, and within-paper audit verdicts were generated autonomously by an AI-assisted pipeline and **have not yet been manually reviewed or verified by human domain experts**.
>
> - **Expect errors:** Automated digitization, scale-bar calibration, term mapping, and numerical/claim checks may contain mistakes, omissions, or misreadings.
> - **Audit flags are preliminary:** Any `inconsistent`, `close`, or `overstated` flags are automated diagnostic hypotheses — **not** peer-reviewed critiques of the original studies.
> - **Do not cite directly:** Always consult the original published papers, figures, and supplemental datasets before relying on or citing any extracted numbers, overlays, or audit notes.
>
> Every extraction is published alongside its verbatim quote anchor, visual overlay proof, and auditable Python script so researchers can inspect the provenance and open issues or pull requests to verify or correct records.

A standalone, auditable living literature review, developmental GRN workbench, and digitized figure atlas for **Lepidoptera (butterflies and moths)** — spanning scale morphogenesis, ultrastructure, biophotonics, evolutionary developmental genetics, and extensible functional directions.

Built on LivingLit's assumption-free epistemic core (anchored verbatim quotes, raw author data tables, SymPy formula verification, 7-dimension within-paper claim auditing, and deterministic verification gates), extended with **atomic 1-letter figure panel segmentation**, **bespoke per-figure Python digitization**, **phase-aligned microscopy FFT grating overlays**, **`field_set: 4` developmental genetics & GRN curation**, **relaxed user-discretion cross-paper comparison**, and an **autonomous 5-stage agent skill pipeline**.

![livinglit-lepidoptera System Architecture](docs/design/figures/fig1_architecture.svg)

## Current Prototype Corpus (`pilot-v1`, 10 Open-Access Papers)

- **10 Open-Access papers** (`CC-BY-4.0` / `CC-BY-NC-ND-4.0`; 9 butterflies + 1 Bogong moth, *Agrotis infusa*)
- **594 atomic figure panels** (`0` composites, `0` flagged QA panels)
- **110 digitized plots** across **32 bespoke Python extractors** (`18,063` extracted series points) and **80 calibrated 2D-FFT microscopy readings**
- **33 anchor-backed GRN edges** across 4 evo-devo/cytoskeletal papers + **3 supplemental genomic/morphometric tables** (`527` parsed rows)
- **260 controlled-vocabulary terms** (`v4` / `field_set: 4`, 17 fields with FlyBase/NCBI xrefs) and **40 SymPy formulas** (`47` tests)

## Design Specification (`docs/design/`)

| Document | Scope |
|---|---|
| [00 · Overview & Architecture](docs/design/00-overview.md) | Vision, Lepidoptera scope, faithful LivingLit pillars vs. the 3 deliberate shifts, genetics/GRN layer, repo layout, OA license policy |
| [01 · Record, Vocabulary & Schema](docs/design/01-record-and-schema.md) | `manifest.yaml`, `record.yaml`, `data.yaml`, `genetics.yaml`, `field_set: 4` (butterflies + moths + genetics/genomics), ontology xrefs, Claim vs. Evidence rules |
| [02 · Atomic Panels, Digitization & Overlays](docs/design/02-panels-and-digitization.md) | Strict 1-letter panel splits, data hierarchy, `extract_lib.py`, per-figure `extractors/*.py`, unified Plot + Microscopy FFT `overlay_meta`, automated gate guards |
| [03 · Within-Paper Audit & Formulas](docs/design/03-audit-and-formulas.md) | SymPy derivation library (physics, morphometrics, genetics/DE/CRISPR, statistics), printed vs. data vs. digitized checks, 7-dimension claim verdicts |
| [04 · Relaxed Cross-Paper Comparison](docs/design/04-across-sources.md) | Strictly empirical comparisons (`evidence` items & `values` only), minimal physical blockers, transparent context diffs, interactive user discretion, GRN & Knowledge Graph |
| [05 · Autonomous Agent Skill Pipeline](docs/design/05-autonomous-skill-pipeline.md) | 5-stage `skills/` workflow (`ingest-paper` → `segment-panels` → `digitize-panels` → `read-record` → `publish-site`), visual self-verification loops, `qa/report.json` |
| [06 · Visualizer, Releases & CI](docs/design/06-visualizer-and-releases.md) | Zero-dependency modular `web/` architecture (GitHub Pages `docs/site/` + portable `overview.html`), live Plot + FFT overlays, GRN Workbench, `.py` code viewer, CI gates |

## Quickstart (Local Verification)

```bash
uv sync --dev
uv run pytest -v
```

To rebuild a release and static explorer locally once open-access source papers are placed under `papers_dont_ever_commit/<paper_id>/`:

```bash
uv run livinglit-lep release pilot-v1
uv run livinglit-lep harvest --build-hub pilot-v1
uv run python web/build.py --tag pilot-v1
```

## Attribution & License

Code and structured metadata are released under the [MIT License](LICENSE). Derived from and adapted from `livinglit` (Copyright © 2026 Emma Lejeune). Source paper PDFs, raw third-party archives, generated release bundles, and external ontology dumps are strictly `.gitignore`d and never committed to `main`. Underlying paper figures remain under their respective Open-Access licenses (`CC-BY-4.0` or `CC-BY-NC-ND-4.0`, recorded per paper in `records/<paper>/manifest.yaml`).

