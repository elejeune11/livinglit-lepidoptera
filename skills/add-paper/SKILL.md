---
name: add-paper
description: End-to-end autonomous orchestrator to ingest, atomically segment, digitize, visually verify, audit, and publish an open-access Lepidoptera paper into livinglit-lepidoptera.
---

# `add-paper` — End-to-End Autonomous Paper Ingestion Orchestrator

Use this skill when adding one or more new open-access Lepidoptera (butterfly or moth) papers into `livinglit-lepidoptera`. Every stage runs autonomously with deterministic code gates and mandatory visual inspection of rendered overlay contact sheets — zero shortcuts, zero unverified heuristics.

## Preconditions

- Source paper folder exists under `papers_dont_ever_commit/<YEAR>_<FirstAuthor>/` (git-ignored) containing JATS XML (`*.xml`) and/or PDF (`*.pdf`), full-resolution figure images, and any downloaded supplements/repositories under `associated/`.
- Virtual environment is synced (`uv sync --dev`).

## Pipeline Stages (Execute Strictly in Order)

### Stage 1 — OA Gate & Source Inventory (`ingest-paper`)
1. Follow `skills/ingest-paper/SKILL.md`.
2. **Hard stop**: If `oa_status != "open_access"` under `fields/lepidoptera/field.yaml` (`policy.oa_only: true`), stop immediately and record the paper as skipped (paywalled) without ingesting source content.
3. **Exit artifacts**: `records/<paper>/manifest.yaml`, `records/<paper>/resources.yaml`.

### Stage 2 — Atomic 1-Letter Panel Segmentation (`segment-panels`)
1. Follow `skills/segment-panels/SKILL.md`.
2. Every panel ID must be atomic (`A`, `A_prime`, `A_dprime`, `B`, `C`, …). Composite halves (`AB`, `top`, `A-C`) are rejected by `gate panels`.
3. Render `qa_renders/bbox_<paper>.png` via `uv run livinglit-lep qa <paper> --out qa_renders` and **visually inspect every figure crop**.
4. **Exit criterion**: Zero clipped labels, zero bled neighbor axes, zero composite multi-panel crops.

### Stage 3 — Bespoke Digitization, FFT Metrology & Visual QA (`digitize-panels`)
1. Follow `skills/digitize-panels/SKILL.md`.
2. Write clean, auditable per-figure Python extractors in `records/<paper>/extractors/<fig>.py` using `livinglit_lepidoptera.extract_lib`.
3. Run:
   ```bash
   uv run livinglit-lep gate panels <paper> --apply
   uv run livinglit-lep qa <paper> --out qa_renders
   ```
4. **Visually inspect BOTH** `qa_renders/plots_<paper>.png` AND `qa_renders/fft_<paper>.png`.
   - Fix any curve miss, truncated whisker/box, dropped `±SD`/CI ribbon, scale-bar misdetection, or 2× FFT harmonic lock.
   - Re-run `gate panels --apply` and `qa` until `records/<paper>/qa/report.json` shows `n_flagged == 0` (or every flagged panel is explicitly verified and documented).
5. **Exit criterion**: `gate panels <paper>` exits `0` and all visual overlays are pixel-accurate.

### Stage 4 — Full Scientific Record, Claims Audit & Formulas (`read-record`)
1. Follow `skills/read-record/SKILL.md`.
2. Extract ALL empirical evidence items from text, tables, supplements, and digitized figures into `record.yaml` (`field_set: 3`) with verbatim `≤30`-word anchors and `context_anchors`.
3. Audit ALL within-paper claims (Abstract, Results conclusions, Discussion conclusions, assertive figure titles) across all 7 dimensions (`direction`, `support`, `comparison`, `scope`, `replication`, `strength`, `presence`).
4. Author `terms.yaml` (if novel terms are needed), `derived.yaml` (SymPy symbolic checks), and `figures.yaml` / `readings.yaml` / `data.yaml`.
5. Run all deterministic gates:
   ```bash
   uv run livinglit-lep gate record <paper>
   uv run livinglit-lep gate terms <paper>
   uv run livinglit-lep gate derived <paper>
   uv run livinglit-lep gate panels <paper>
   uv run livinglit-lep audit <paper>
   ```
6. **Exit criterion**: 5/5 gates PASS (`exit 0`) and `records/<paper>/audit.yaml` is generated cleanly.

### Stage 5 — Release, Hub, Web Build & Browser QA (`publish-site`)
1. Follow `skills/publish-site/SKILL.md`.
2. Rebuild release tables, data hub, modular static site (`docs/site/`), and single-file bundle (`releases/<tag>/overview.html`).
3. Run `uv run pytest` and Playwright visual verification (`0` JS errors, light + dark themes, `1360px` + `1120px`).
4. Verify `git status` shows ZERO files from `papers_dont_ever_commit/`, `ontologies_dont_commit/`, or `thumbs*.json`.
