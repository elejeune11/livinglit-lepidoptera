---
name: ingest-paper
description: Stage 1 skill — Verify open-access license policy, scan JATS XML / PDF supplements and external repositories, and write manifest.yaml and resources.yaml for a Lepidoptera paper.
---

# `ingest-paper` — OA Gate, Inventory & Repository Harvest

## Objective
Verify that a candidate paper satisfies the repository's Open Access policy, inventory 100% of local source files and external repositories (Dryad, Zenodo, Figshare, OSF, eLife), and emit validated `records/<paper>/manifest.yaml` and `records/<paper>/resources.yaml`.

## Steps

1. **Inspect Source Folder & License**
   - List everything inside `papers_dont_ever_commit/<paper>/` (including `associated/`).
   - Read the `<permissions>` / `<license>` block in JATS XML (`*.xml`) or copyright notice on page 1 of the PDF.
   - Check `fields/lepidoptera/field.yaml` → `policy.oa_only`.
   - **Hard Gate**: When `policy.oa_only: true`, you MUST confirm an explicit Open Access license (`CC-BY-4.0`, `CC-BY-3.0`, `CC0-1.0`, or PMC Open Access) and set `oa_status: open_access`. If the paper is paywalled or all-rights-reserved, stop and do NOT ingest it.

2. **Scan External Data & Code Repositories**
   - Run:
     ```bash
     uv run livinglit-lep harvest --scan <paper>
     ```
   - Inspect all `<supplementary-material>`, `<ext-link>`, Data Availability, and Code Availability sections.
   - Check whether external archives (Zenodo, Figshare, OSF, Dryad, GitHub) contain raw numerical tables (`.csv`, `.xlsx`, `.dat`, `.mat`) or analysis scripts (`.R`, `.m`, `.py`, `.nb`). Note clearly in `resources.yaml` which files were downloaded locally vs. indexed via metadata only (e.g., if a repository is CAPTCHA-gated — never bypass CAPTCHAs!).

3. **Write `records/<paper>/manifest.yaml`**
   Follow the strict `Manifest` schema in `src/livinglit_lepidoptera/models.py`:
   ```yaml
   id: 2024_Lloyd
   doi: 10.1038/s41467-024-48060-3
   title: The actin cytoskeleton plays multiple roles in structural colour formation in butterfly wing scales
   year: 2024
   journal: Nature Communications
   oa_status: open_access               # open_access | restricted
   license: CC-BY-4.0
   figure_embed_policy: public_thumbnails  # public_thumbnails | local_only
   repositories:
     - kind: Figshare
       url: https://doi.org/10.15131/shef.data.25422754
       doi: 10.15131/shef.data.25422754
       note: "7 R statistical scripts downloaded locally; raw measurement CSVs omitted by authors."
   files:
     - file: PMC11106069.xml
       role: main_text                  # main_text | main_figure | supp_text | supp_table | supp_figure | raw_data | code
     - file: fig1.png
       role: main_figure
   not_used:
     - file: 41467_2024_48060_Fig1_HTML.jpg
       why: "Lower-resolution PMC HTML copy of Fig. 1; full-resolution fig1.png is used instead."
   ```
   Every single file present in `papers_dont_ever_commit/<paper>/` must appear under `files` or `not_used`.

4. **Write `records/<paper>/resources.yaml`**
   Document every dataset, supplement, and author code script using `ResourcesFile` (`id`, `kind`, `repository`, `title`, `url`, `doi`, `license`, `local_files`, `feeds_panels`, `feeds_items`, `summary`).

5. **Verify**
   - Validate `manifest.yaml` against `Manifest.model_validate(...)` and `resources.yaml` against `ResourcesFile.model_validate(...)`.
   - Confirm zero source files are staged in `git status`.
