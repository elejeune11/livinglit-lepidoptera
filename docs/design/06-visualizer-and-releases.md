# 06 · Modular Zero-Dependency Visualizer, Releases & CI

## 1. Zero-Dependency Modular Web Architecture (`web/`)

Instead of maintaining a monolithic 3,200-line Python-string HTML file, the visualizer lives as clean, modular, zero-dependency vanilla HTML/CSS/ES-modules under `web/` (no npm, no bundler bloat, no external CDNs — works identically in GitHub Pages and sandboxed offline iframes):

```text
web/
├── index.template.html          # Clean semantic shell (no inline data blobs)
├── styles/
│   ├── tokens.css               # Light/dark editorial design tokens + live themechange sync
│   └── components.css           # Single-row topbar, master-detail atlas, canvases, drawer
├── js/
│   ├── state.js                 # Global state, URL hash/filter sync, CSV/JSON exporters
│   ├── overlays.js              # Unified Plot + Microscopy FFT Grating + Scale-Bar overlay renderer
│   ├── charts.js                # HiDPI canvas renderers (curves+ribbons, x/y errorbars, boxplots, dotplots)
│   ├── views/
│   │   ├── atlas.js             # Panel Atlas + Sticky Inspector (incl. genetic channel/crispant/locus cards) + Live ROI Periodicity
│   │   ├── vault.js             # Plots tab: Digitized Plots & Overlay Verification + Inline .py Extractor Viewer
│   │   ├── scale_comparator.js  # True-Scale (µm/px) side-by-side micrograph comparator
│   │   ├── compare.js           # Relaxed Values + Verdicts + Interactive Context-Diff Controls + Meet Matrix
│   │   ├── graph.js             # GRN & Graph Workbench (Directed GRN SVG, Interactive Genomic Tables / Volcano, Corpus Graph)
│   │   ├── audit.js             # Full 7-dim Within-Paper Claim Audit, Formulas & Data Gaps
│   │   ├── vocab_formulas.js    # Controlled Vocabulary Tree (w/ FlyBase/NCBI xrefs & GRN links) + 40-Formula Live Calculator
│   │   ├── papers_schema.js     # Paper sheets, harvested raw datasets & indexed author scripts
│   │   └── drawer.js            # Slide-over Result Audit Drawer (anchors, quotes, linked crops, checks)
│   └── main.js                  # App router & event delegation
└── build.py                     # Emits BOTH multi-file docs/site/ (GitHub Pages) AND single-file overview.html
```

### Dual Build Targets
1. **Multi-file static site (`docs/site/`)**: Clean separate `.css`, `.js`, and compressed `.json` data chunks — ideal for fast browser caching on GitHub Pages once the repository goes public.
2. **Single-file portable artifact (`releases/<tag>/overview.html`)**: Self-contained zero-CDN HTML bundle that opens instantly offline or inside an artifact preview pane.

---

## 2. Live Verification Features in the UI

- **Live `Overlay check` toggle on EVERY digitized plot AND calibrated micrograph** (in **Atlas** and **Plots**):
  - *Plots*: cyan calibrated `plot_box`, extracted curves + `±SD`/CI bounds, per-point `x`/`y` errorbars, scatter rings, boxplots, and dotplot circle outlines (`dotplot_matrix`) drawn directly onto the source figure crop, paired side-by-side with an interactive HiDPI canvas re-plot.
  - *Microscopy / FFT*: yellow **scale-bar bracket** (`µm` + `nm/px`), cyan **FFT ROI rectangle**, **phase-aligned bright-green parallel ridge grating lines** inside the ROI (plus optional magenta cross-rib grating), and 10 yellow transect peak ticks — plus live drag-to-measure browser ROI periodicity right beside it.
- **GRN & Genomic Tables Workbench (`GRN & Graph`)**: Interactive layered SVG regulatory network styled by `evidence_tier` and relation polarity with verbatim anchor inspection, paired with interactive SVG Volcano plots and searchable/sortable supplemental DE/ChIP/morphometric tables (`genetics.yaml` → `genomic_tables`).
- **Inline `.py` extractor code viewer**: Clicking any panel's `.py` pill expands the exact `records/<paper>/extractors/<fig>.py` source executed by `gate panels`.
- **QA Confidence badge**: Surfaces each panel's `qa/report.json` grade (`verified`, `low_snr_verified`, `flagged`), FFT-vs-transect delta, and raw-data RMSE directly in the Inspector.
- **Interactive Relaxed Comparison controls**: Researchers toggle which context fields (`taxon`, `scale_type`, `functional_architecture`, `life_stage`, `perturbation_modality`, `imaging_modality`, `view_orientation`, `hydration_and_prep`) to match strictly vs. relax, with explicit diff badges on every compared pair.

---

## 3. Release Artifacts & Continuous Integration

### Tidy Scientific Data Exports (`releases/<tag>/`)
Every release generates clean, analysis-ready machine-readable files for downstream Python/R research:
- `values.csv` — all audited empirical values across all papers with resolved controlled-vocabulary context columns and origin tags (`stated`, `data`, `readings`, `derived`).
- `comparisons.csv` — all physically compatible cross-paper pairs with computed value/direction verdicts and explicit `context_diff` fields.
- `relations.csv` — all anchor-backed directed genetic / GRN / genotype→phenotype edges (`source`, `relation`, `target`, `evidence_tier`, `assays`, `context`, `anchor`).
- `terms.csv` — full controlled vocabulary hierarchy including `xref` (`FlyBase`, `NCBI_Gene`, `NCBITaxon`, `ChEBI`).
- `panels_all.json` & `digitized_all_series.csv` — every atomic panel, microscopy FFT measurement, digitized curve (`x, y, lo, hi`), scatter point (`x, y, x_lo, x_hi, y_lo, y_hi`), boxplot, dotplot cell, and `overlay_meta`.
- `data_hub.json` — harvested raw repository datasets, schema-driven `genomic_tables`, indexed author scripts, and bundled `extractors/*.py`.
- `SCHEMA.md` & `CHANGES.md` — auto-generated from Pydantic models and `field/changes.yaml`.

### Continuous Integration (`.github/workflows/ci.yml`)
Every commit and pull request runs:
1. **`pytest`** — unit tests for `extract_lib.py`, `genetics.yaml` evidence-tier guards, unit conversions, relaxed comparison logic, Pydantic strict validation, and web bundle enrichment.
2. **Deterministic repository gates** — schema, vocabulary, ontology xrefs, formula checks, `manifest.yaml` license/OA policy checks, and cached-vs-schema verification (plus full paper re-execution gates locally whenever `papers_dont_ever_commit/` is present).
3. **Web build & Playwright smoke test** — builds both `docs/site/` and `overview.html`, verifying `0` console/page errors, `0` external CDN links, single-row responsive topbar, 100% pass across all 40 interactive SymPy formulas, and live `Overlay check` rendering across light and dark themes.
