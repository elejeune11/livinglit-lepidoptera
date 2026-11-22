---
name: read-record
description: Stage 4 skill — Author record.yaml (field_set 4, context_anchors, full 7-dim within-paper claim audit), optional genetics.yaml (GRN relations + genomic_tables), terms.yaml, derived.yaml (SymPy checks), and pass all deterministic gates.
---

# `read-record` — Structured Record, Genetics GRN, 7-Dim Claim Audit & Symbolic Formulas

## Objective
Capture the complete scientific substance of a Lepidoptera paper into `records/<paper>/record.yaml` (`field_set: 4`), encode directed regulatory edges and supplemental genomics tables in `records/<paper>/genetics.yaml` whenever the paper includes genetics/evo-devo/genomics, map every stated context and measure to `fields/lepidoptera/vocab.yaml` (proposing clean new terms with FlyBase/NCBI xrefs in `terms.yaml` only when genuinely absent), verify mathematical derivations via SymPy in `derived.yaml`, and audit EVERY within-paper claim across all 7 LivingLit dimensions.

## Critical Epistemic Boundary (Never Violate)
- **Within-paper `claims:`** are audited against the paper's own `evidence:` items in the **Audit** tab (full 7-dimension scrutiny: `direction`, `support`, `comparison`, `scope`, `replication`, `strength`, `presence`).
- **Cross-paper comparisons** NEVER compare `claims:` — they compare ONLY empirical `evidence:` items and `values`.
- **GRN Evidence-Tier Honesty (`genetics.yaml`)**: Never assign `direct_binding_and_perturbation`, `chromatin_or_binding_only`, or `directly_binds_cre` unless `assays` includes a physical chromatin/binding assay (`chip_seq`, `cut_and_tag`, `atac_seq`) — enforced automatically by `gate record`!

## Steps

1. **Read Full Paper End-to-End**
   - Read the complete JATS XML (`*.xml`) or PDF text: Title, Abstract, Introduction (only for context), Results (every paragraph + every quantitative test), Discussion, Methods (species, sex, rearing, pupal staging, fixation/hydration, genetic element & zygosity, imaging/genomics modality, sample prep, statistical software & models), Tables, and all Figure Captions.
   - Cross-reference digitized outputs in `records/<paper>/digitized/panels_extracted.json` so figure-derived measurements feed directly into `readings.yaml` / `evidence:`.

2. **Author `records/<paper>/record.yaml` (`field_set: 4`)**
   - `source`: title, doi, year, lab, authors, files (matching `manifest.yaml`).
   - `default_context`: populate all 16 context fields from `fields/lepidoptera/field.yaml` (`taxon`, `sex`, `anatomical_region`, `pattern_element`, `scale_type`, `functional_architecture`, `life_stage`, `pupal_stage_pct`, `target_gene`, `genetic_element_type`, `allele_or_zygosity`, `perturbation_modality`, `chemical_agent`, `imaging_modality`, `view_orientation`, `hydration_and_prep`). Put any field that varies across units/groups at the unit/group level instead of `default_context`, and use `"not stated"` or `"not applicable"` honestly — never guess!
   - `context_anchors` (**required at `field_set: 3+`**): Every stated context value (at paper, unit, or group level) MUST have a verbatim `≤30`-word quote from the paper where every word/number of the stated value appears in the quote (`holds(quote, value)` checked by `gate record`). Write the stated value wording directly from the paper's verbatim text!
   - `units`: group every experimental comparison or observational assay cleanly with explicit `groups` and `design`.
   - `evidence`: record every quantitative empirical finding with `unit`, `measure`, `groups`, `values` (mean/median/SD/SEM/IQR/range/slope/R²/log2FC/ChIP peaks with exact units and `expressed_as`), `n`, `stats` (`test`, `p`, `statistic`, `df`), `finding`, `method`, `software`, and verbatim `≤30`-word `anchor: {where, quote}`.
   - `claims` (**Full 7-Dimension Depth**): Extract ALL major claims from Abstract, Results conclusions, Discussion conclusions, and assertive figure titles. Record `quote`, `where`, `scope`, `rests_on`, and full 7-dimension `judgement` (`direction`, `support`, `comparison`, `scope`, `replication`, `strength`, `presence`).

3. **Author `records/<paper>/genetics.yaml` (When Genetics / Evo-Devo / Genomics Present)**
   - **`relations`**: Record every experimentally supported directed regulatory or genotype→phenotype edge (`source`, `source_label`, `relation`, `target`, `target_label`, `evidence_tier`, `effect_direction`, `assays`, `context`, `linked_items`, `linked_panels`, and verbatim `anchor`).
   - **`genomic_tables`**: Declare supplemental CSV/TSV datasets (`de_genes`, `chip_peaks`, `crispant_counts`, `gwas_loci`, `scale_morphometrics`) with exact `file`, `columns` mapping (by column header name or 0-based integer index when CSV headers duplicate names), `assay`, `contrast`, `stage`, `taxon`, `linked_items`, `linked_panels`, and verbatim `anchor`.

4. **Vocabulary (`terms.yaml`) & Formulas (`derived.yaml`)**
   - Check existing terms via `uv run livinglit-lep lookup "<phrase>"`.
   - Only propose genuinely missing Lepidoptera concepts in `records/<paper>/terms.yaml` (with clean definitions, parent IDs, synonyms, and `FlyBase:` / `NCBI_Gene:` xrefs for genes), then rebuild vocabulary via `uv run livinglit-lep vocab rebuild`.
   - Encode symbolic checks in `records/<paper>/derived.yaml` (thin-film interference, ridge density `1/d`, SAXS Bragg `2π/q*`, foreshortening `d/cos(θ)`, buckling strain, relative pupal stage `%`, CRISPR hatching/emergence/penetrance rates, `FC = 2**log2FC`, Benjamini–Hochberg FDR, ChIP/DE enrichment odds ratio) and run `gate derived`.

5. **Run All Deterministic Gates**
   ```bash
   uv run livinglit-lep gate record <paper>
   uv run livinglit-lep gate terms <paper>
   uv run livinglit-lep gate derived <paper>
   uv run livinglit-lep gate panels <paper>
   uv run livinglit-lep audit <paper>
   ```
   Iterate until **100% of gates exit `0`**.
