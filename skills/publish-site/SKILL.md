---
name: publish-site
description: Stage 5 skill — Build release tables, data hub, modular zero-dependency visualizer (docs/site/ and single-file overview.html), run pytest and Playwright visual QA across light and dark themes.
---

# `publish-site` — Release, Hub, Modular Web Build & Browser Visual QA

## Objective
Compile all passing `records/` into tidy release tables (`releases/<tag>/`), build the unified Data & Code Hub (`data_hub.json`), compile the zero-dependency modular web visualizer (`web/`) into BOTH `docs/site/` (multi-file static site) AND `releases/<tag>/overview.html` (portable single-file bundle), run all unit tests, and visually verify the live rendered app in headless Chromium.

## Steps

1. **Build Release Tables & Data Hub**
   ```bash
   uv run livinglit-lep release <tag>
   uv run livinglit-lep harvest --build-hub <tag>
   ```
   Verify `releases/<tag>/` contains `papers.csv`, `items.csv`, `values.csv`, `comparisons.csv`, `strata.csv`, `claims.csv`, `derivations.csv`, `terms.csv`, `formulas.csv`, `summary.yaml`, `SCHEMA.md`, `panels_all.json`, `digitized_all_series.csv`, and `data_hub.json`.

2. **Compile Modular Zero-Dependency Web Visualizer**
   ```bash
   uv run python web/build.py --tag <tag>
   ```
   This emits:
   - `docs/site/` (`index.html`, `styles/*.css`, `js/*.js`, `js/views/*.js`, `data/bundle.json`)
   - `releases/<tag>/overview.html` (self-contained zero-CDN single-file HTML)
   And automatically enforces:
   - `0` external CDN URLs (`cdn.jsdelivr.net`, `unpkg.com`, `fonts.googleapis.com`, etc.)
   - `0` internal `href="#..."` anchor links (use `button` / JS state switching so iframe previews never navigate away)

3. **Run Automated Test Suite**
   ```bash
   uv run pytest -v
   ```

4. **Headless Browser Visual QA (Playwright)**
   Launch Playwright against BOTH `releases/<tag>/overview.html` and `docs/site/index.html` (via temporary local HTTP server) and verify:
   - `0` `console.error` messages and `0` uncaught `pageerror` exceptions.
   - Single-row topbar height `<= 56px` at BOTH `1360×900` and `1120×840`.
   - Light theme AND Dark theme (`data-theme="dark"` / `themechange` event) contrast & canvas readability.
   - Capture screenshots and **inspect EVERY screenshot via `view_file`**:
     1. **Microscopy Atlas** with live `Overlay check` ON (yellow scale-bar bracket + cyan FFT ROI + bright-green phase-aligned grating lines + QA confidence badge).
     2. **Plot Vault** with live `Overlay check` ON + expanded `.py` extractor code viewer.
     3. **Relaxed Compare** view showing interactive context-dimension toggles and transparent green/amber/red `context_diff` pills + confounder badges.
     4. **Full 7-Dim Claim Audit** tab showing claim verdicts, dimension badges, and source anchors.
     5. **Knowledge Graph** tab in dark mode.

5. **Hygiene Check Before Commit**
   ```bash
   git status --short
   ```
   Confirm ZERO copyrighted source PDFs, XMLs, raw archives, `papers_dont_ever_commit/`, `ontologies_dont_commit/`, or `thumbs*.json` files are tracked by Git.
