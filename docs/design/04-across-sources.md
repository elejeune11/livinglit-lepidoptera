# 04 · Relaxed Cross-Paper Comparison & Epistemic Firewall

This document defines **Shift #2**: keeping cross-paper comparisons **strictly empirical** (zero prose claims, zero hidden interpretive models) while **relaxing rigid standing-key blocking** so researchers exercise explicit discretion across Lepidoptera clades, scale types, developmental stages, and modalities.

![Epistemic Separation: Within-Paper Claim Audit vs. Relaxed Cross-Paper Comparison](figures/fig3_epistemic_comparison.svg)

---

## 1. The Strict Epistemic Firewall

- **Prose claims NEVER cross into cross-paper comparisons.** All cross-paper plots, tables, comparison verdicts, and intersections operate strictly on empirical `evidence` items, `values.csv`, `data.yaml`, and verified `digitized/` measurements.
- **No baked-in theoretical curves or interpretive thresholds**: The platform never superimposes speculative theoretical thresholds or synthesized narrative conclusions across papers. Researchers export tidy CSV/JSON tables to build whatever theoretical or phylogenetic layer they want on top.

---

## 2. Relaxed Standing Keys (Minimal Physical Blockers + Full Context Transparency)

In upstream LivingLit, strict `must_match` standing keys mark most cross-species or cross-modality pairs as `not comparable` (hard-blocked). In comparative Lepidoptera biology, comparing ridge spacing across *Heliconius*, *Morpho*, *Colias*, *Vanessa*, *Parides*, and moths — or comparing SAXS vs. SEM vs. live SIM — is the core scientific use case.

`livinglit-lepidoptera` therefore adopts a **two-tier relaxed comparison rule**:

### Tier 1 · Minimal Hard Blocker (Strictly Physical / Dimensional)
Two empirical items are eligible for direct numerical comparison whenever:
1. They share the **same canonical `measure`** (e.g., `measure:ridge_spacing`, `measure:peak_reflectance_wavelength`, `measure:ridge_height`, `measure:actin_bundle_spacing`), AND
2. Their units are **dimensionally compatible** (auto-convertible by `numbers.convert`, e.g., `nm` ↔ `µm`) with compatible `expressed_as` basis (`absolute` vs. `% change` / `fold` are never mixed numerically).

### Tier 2 · Transparent Context Diff Surface (User Discretion)
Every eligible cross-paper pair computes an explicit **`context_diff`** across all 16 contextual fields (`taxon`, `sex`, `anatomical_region`, `pattern_element`, `scale_type`, `functional_architecture`, `life_stage`, `pupal_stage_pct`, `target_gene`, `genetic_element_type`, `allele_or_zygosity`, `perturbation_modality`, `chemical_agent`, `imaging_modality`, `view_orientation`, `hydration_and_prep`):
- **Matched fields** are shown as green verified pills (e.g., `✓ cover scale`, `✓ adult`, `✓ wild type`).
- **Differing fields** are shown as explicit diff badges (e.g., `≠ taxon (genus)`, `≠ imaging_modality (SAXS vs SEM)`, `≠ perturbation (WT vs Cyto D)`).
- **Known physical and genetic confounders get an explicit warning highlight** (not a silent block!), including `⚠ view_orientation (tilted oblique vs planar apical)`, `⚠ hydration_and_prep (live hydrated vs vacuum dry SEM)`, `⚠ genetic_element_type (coding exon KO vs CRE deletion vs lncRNA)`, and `⚠ allele_or_zygosity (G0 somatic mosaic vs homozygous null vs RNAi knockdown)`.
- **Interactive researcher toggles in the UI**: In **Compare → Values** and **Compare → Verdicts**, the user can interactively check/uncheck any context dimension (`Require exact match` vs. `Relax & color by field`) and group distributions by `paper`, `taxon` (phylogenetic DFS order), `functional_architecture`, `scale_type`, or `imaging_modality`.

---

## 3. Effect Direction & Value Agreement (Computed Strictly by Code)

For any two compared items $(A, B)$:
- **Value comparison** (single-group distributions): computes overlap/difference from `group_mean` and `group_sd` (preferring `stated` → `data` → `readings`, and explicitly labeling each value's origin), yielding `agree`, `differ`, or `not available (no spread)`.
- **Direction comparison** (paired perturbations or comparisons): computes each item's direction (`up`, `down`, `none`) strictly from numerical values + printed `p` (falling back to `stated_direction` only when no values exist, explicitly labeled `stated`), yielding `same direction`, `differ in direction`, or `not available`.

---

## 4. Cross-Paper GRN Synthesis, "Where Do Papers Meet?" & Knowledge Graph

Every paper meets every other paper across **all shared controlled-vocabulary axes** — not just morphometric measures:
- Shared **taxa / clades** (computed along the phylogenetic hierarchy so *H. erato* and *H. melpomene* meet at `Heliconius` and `Nymphalidae`, and butterflies + moths meet at `Lepidoptera`)
- Shared **scale types** & **functional architectures**
- Shared **target genes** (linked by canonical `target_gene:*` IDs + FlyBase/NCBI ortholog xrefs), **genetic element types**, **perturbations**, & **chemical agents**
- Shared **imaging / genomics modalities** & **measures**

### Evidence-Tiered GRN Synthesis (`genetics.yaml` → `relations.csv` → **GRN & Graph**)
Directed regulatory edges (`source → relation → target`) from multiple evo-devo papers compose into a cross-paper **Gene Regulatory Network** while honoring the same epistemic discipline as empirical values:
- Every edge carries a mandatory verbatim paper `anchor`, `assays`, `context` (`taxon`, `sex`, `life_stage`, `genetic_element_type`, `allele_or_zygosity`), and an explicit **`evidence_tier`**:
  1. `direct_binding_and_perturbation` (solid stroke — requires both physical binding/chromatin assay and functional KO/RNAi)
  2. `perturbation_only` (dashed — CRISPR / RNAi functional effect without direct binding proof)
  3. `chromatin_or_binding_only` (dash-dot — ChIP-seq / CUT&Tag / ATAC-seq occupancy paired with expression)
  4. `correlative` (dotted — snRNA-seq cluster enrichment / GWAS association)
- `gate record` enforces that no edge can claim direct binding without a binding assay in `assays`.

Both the **Intersection Matrix** (`Compare → Where Papers Meet`) and the 3-mode **GRN & Graph** workbench (`Regulatory Network (GRN)` · `Genomic Tables` · `Corpus Knowledge Graph`) are 100% deterministically computed from `terms.yaml`, `genetics.yaml`, and `values.csv` with clickable drill-down into exact evidence items, vocabulary xrefs, and figure panels.
