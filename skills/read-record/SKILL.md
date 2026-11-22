---
name: read-record
description: Stage 4 skill — Author record.yaml (field_set 3, context_anchors, full 7-dim within-paper claim audit), terms.yaml, derived.yaml (SymPy checks), and pass all deterministic gates.
---

# `read-record` — Structured Record, 7-Dim Claim Audit & Symbolic Formulas

## Objective
Capture the complete scientific substance of a Lepidoptera paper into `records/<paper>/record.yaml` (`field_set: 3`), map every stated context and measure to `fields/lepidoptera/vocab.yaml` (proposing clean new terms in `terms.yaml` only when genuinely absent), verify mathematical derivations via SymPy in `derived.yaml`, and audit EVERY within-paper claim across all 7 LivingLit dimensions.

## Critical Epistemic Boundary (Never Violate)
- **Within-paper `claims:`** are audited against the paper's own `evidence:` items in the **Audit** tab (full 7-dimension scrutiny: `direction`, `support`, `comparison`, `scope`, `replication`, `strength`, `presence`).
- **Cross-paper comparisons** NEVER compare `claims:` — they compare ONLY empirical `evidence:` items and `values`.

## Steps

1. **Read Full Paper End-to-End**
   - Read the complete JATS XML (`*.xml`) or PDF text: Title, Abstract, Introduction (only for context), Results (every paragraph + every quantitative test), Discussion, Methods (species, sex, rearing, pupal staging, fixation/hydration, imaging modality, sample prep, statistical software & models), Tables, and all Figure Captions.
   - Cross-reference digitized outputs in `records/<paper>/digitized/panels_extracted.json` so figure-derived measurements feed directly into `readings.yaml` / `evidence:`.

2. **Author `records/<paper>/record.yaml` (`field_set: 3`)**
   - `source`: title, doi, year, lab, authors, files (matching `manifest.yaml`).
   - `default_context`: populate all 14 context fields from `fields/lepidoptera/field.yaml` (`taxon`, `sex`, `anatomical_region`, `pattern_element`, `scale_type`, `functional_architecture`, `life_stage`, `pupal_stage_pct`, `target_gene`, `perturbation_modality`, `chemical_agent`, `imaging_modality`, `view_orientation`, `hydration_and_prep`). Use `"not stated"` or `"not applicable"` honestly — never guess!
   - `context_anchors` (**required at `field_set: 3`**): Every stated context value (at paper, unit, or group level) MUST have a verbatim `≤30`-word quote from the paper where every word/number of the stated value appears in the quote (`holds(quote, value)` checked by `gate record`). Write the stated value wording directly from the paper's verbatim text!
   - `units`: group every experimental comparison or observational assay cleanly with explicit `groups` and `design`.
   - `evidence`: record every quantitative empirical finding with `unit`, `measure`, `groups`, `values` (mean/median/SD/SEM/IQR/range/slope/R² with exact units and `expressed_as`), `n`, `stats` (`test`, `p`, `statistic`, `df`), `finding`, `method`, `software`, and verbatim `≤30`-word `anchor: {where, quote}`.
   - `claims` (**Full 7-Dimension Depth**): Extract ALL major claims from:
     - Abstract (`kind: abstract`)
     - Results section conclusions (`kind: result`)
     - Discussion conclusions (`kind: discussion`)
     - Assertive figure titles (`kind: figure_title`)
     For every claim, record `quote`, `where`, `scope`, `rests_on` (list of `evidence` IDs), and full `judgement` across all 7 dimensions (`direction`, `support`, `comparison`, `scope`, `replication`, `strength`, `presence`) with concise factual `rationale` whenever any dimension is not `follows` (e.g. `overstated`, `cannot judge`, `does not follow`, `restates`, `not applicable`).

3. **Vocabulary (`terms.yaml`) & Formulas (`derived.yaml`)**
   - Check existing terms via `uv run livinglit-lep lookup "<phrase>"`.
   - Only propose genuinely missing Lepidoptera concepts in `records/<paper>/terms.yaml` (with clean definitions, parent IDs, and synonyms), then rebuild vocabulary via `uv run livinglit-lep vocab rebuild`.
   - If the paper computes or relies on quantitative relationships (thin-film interference, ridge density `1/d`, SAXS Bragg `2π/q*`, foreshortening `d/cos(θ)`, buckling strain, acoustic quarter-wave absorption, relative pupal stage `%`), encode symbolic checks in `records/<paper>/derived.yaml` and run `gate derived`.

4. **Run All Deterministic Gates**
   ```bash
   uv run livinglit-lep gate record <paper>
   uv run livinglit-lep gate terms <paper>
   uv run livinglit-lep gate derived <paper>
   uv run livinglit-lep gate panels <paper>
   uv run livinglit-lep audit <paper>
   ```
   Iterate until **100% of gates exit `0`**.
