# 01 · Record, Controlled Vocabulary & Schema (`field_set: 3`)

## 1. Per-Paper Manifest (`manifest.yaml`)

Every paper directory under `records/<paper>/` starts with a strict `manifest.yaml` validated before any other gate runs:

```yaml
id: 2024_Lloyd
doi: 10.1038/s41467-024-48060-x
title: "Actin-mediated ridge morphogenesis..."
year: 2024
journal: "Nature Communications"
oa_status: open_access
license: "CC-BY-4.0"
figure_embed_policy: public_thumbnails   # public_thumbnails | local_only
repositories:
  - kind: dryad_or_osf_or_github
    url: "https://..."
files:
  - file: "main.pdf"
    role: main_text
  - file: "Fig2.jpg"
    role: main_figure
not_used:
  - file: "peer_review.pdf"
    why: "peer review correspondence; contains no empirical group data"
```

- **100% file accounting**: Every file present in local `papers_dont_ever_commit/<paper>/` must appear in `files` or `not_used`. Unaccounted files fail `gate record`.
- **OA policy check**: While the repo's `policy.oa_only: true` setting is active, `manifest.yaml` rejects any non-OA paper unless explicitly overridden.

---

## 2. Extensible Lepidoptera Context Schema (`field/field.yaml`, `field_set: 3`)

`field_set: 3` generalizes our prototype's butterfly morphogenesis fields to cover **all Lepidoptera (butterflies + moths)** while leaving explicit room for acoustics, pigments, thermal/wetting mechanics, and macro patterning:

| Field | Kind | Scope & Extensibility |
|---|---|---|
| `taxon` | hierarchical terms (set) | Full Lepidoptera phylogenetic tree (`Lepidoptera` → `Papilionoidea` [butterflies] & moth superfamilies `Bombycoidea`, `Noctuoidea`, `Geometroidea`, `Pyraloidea`, `Uraniidae`, `Saturniidae`… → family → subfamily → genus → species → subspecies) with pinned `NCBITaxon` xrefs. |
| `sex` | terms (set) | `male`, `female`, `male and female`, `not stated`. |
| `anatomical_region` | hierarchical terms (set) | Extended from `wing_surface` to cover **wings** (`forewing`/`hindwing` → `dorsal`/`ventral`, `margin`/`discal`) AND **body regions** (`thorax`, `abdomen`, `antenna`, `leg` — supporting moth thoracic acoustic & thermal scales). |
| `pattern_element` | terms (set) | Homologous Nymphalid Groundplan (NGP) symmetry systems, eyespots, bands, marginal regions, or moth acoustic/camouflage zones (`not applicable` when absent). |
| `scale_type` | hierarchical terms (set) | Scale layer & functional specialization (`cover scale`, `ground scale`, `androconia`, `UVI scale`, `spatulate`, `glass/transparent`, `hair-like piliform`, `thoracic acoustic scale`). |
| `functional_architecture` | hierarchical terms (set) | Generalizes `photonic_architecture` into an extensible hierarchy: **optical structural** (ridge multilayers, lower-lamina thin films, 3D gyroids, inter-ridge honeycombs, cross-rib diffusers), **pigmentary** (melanin, pterin, ommochrome, papiliochrome, bile), **acoustic** (broadband ultrasonic absorber, resonant lamina), **thermal / wetting** (superhydrophobic, radiative cooler). |
| `life_stage` | terms (set) | `egg`, `larva`, `pupa`, `adult`. |
| `pupal_stage_pct` | quantity | Normalized `% APF` (after pupation / pupal development); `not applicable` for adults/larvae. |
| `target_gene` | terms (set) | Developmental TFs, signaling pathways, cuticular & cytoskeletal genes (`bab`, `dsx`, `optix`, `WntA`, `cortex`, `mwh`, `Arp2/3`, `F-actin`, `chitin`…) with pinned `FlyBase` (`FBgn`) ortholog xrefs; `none` for WT. |
| `perturbation_modality` | terms (set) | `wild type`, `G0 CRISPR mosaic`, `knockout`, `RNAi`, `artificial selection`, `small-molecule inhibitor`, `FIB milling`, `mechanical ablation`, `thermal/humidity shift`, `vehicle control`. |
| `chemical_agent` | terms (set) | Pharmacological/chemical agent or solvent (`cytochalasin D`, `latrunculin A`, `DMSO`…) with pinned `ChEBI` xrefs; `none` when absent. |
| `imaging_modality` | hierarchical terms (set) | Microscopy (`SEM`, `FIB-SEM`, `TEM`, `confocal`, `SIM`, `AFM`, `optical`), scattering (`SAXS`, `USAXS`), spectroscopy (`microspectrophotometry`, `goniometry`, `Raman`, `FTIR`), acoustic (`ultrasound vibrometry`, `anechoic reflectivity`), genomics (`snRNA-seq`, `ChIP-seq`, `ATAC-seq`). |
| `view_orientation` | terms (set) | `planar apical (top-down)`, `tilted oblique`, `cross-section`, `3D volumetric`, `not applicable`. |
| `hydration_and_prep` | terms (set) | `live in vivo`, `fixed hydrated`, `dry native`, `vacuum sputter-coated`, `FIB-milled`, `critical-point dried`. |
| `measure` | measure | Canonical quantitative trait (morphological, developmental, biomechanical, optical, acoustic, thermal, or genomic) with explicit SI/domain unit conversion rules. |

- **Mandatory `context_anchors` (`field_set: 3`)**: Every stated context value in a record must carry a verbatim quote anchor (`{field, value, anchor: {quote, where}}`). Never infer unstated context (`not stated` instead) and never carry a paper's default to a group the paper does not say it applies to.
- **`other_conditions`**: Any experimentally stated condition that does not fit an existing field (e.g., illumination polarization, ambient humidity, acoustic frequency band) is captured verbatim in `other_conditions: [{text, anchor}]` — preserving extensibility with zero schema distortion.

---

## 3. Core Record Entities: Units, Groups, Evidence Items, Values & Claims

### Empirical Layer (`units`, `evidence`, `data.yaml`, `readings.yaml`)
- **`units`**: A distinct figure, table, or results block carrying a `context` and named `groups` (experimental/taxonomic cohorts). Model/FDTD simulation outputs are kept in `panels.yaml` (tagged `archetype: spectral_or_profile` / `simulation`) and separated from biological `evidence` groups.
- **`evidence` (Items)**: One item per reported empirical measurement or statistical test, regardless of whether any prose claim cites it:
  - `groups: [g]` (single-group or descriptive multi-group measurement), OR
  - `compares: [condition, reference]` (`test_of: pair`, condition first, reference second), OR
  - `compares: [g1, g2, g3]` (`test_of: omnibus` / `main effect` / `interaction`).
- **`values`**: Every printed number recorded **verbatim as a string** (`printed`, `unit`, `kind`, `group`/`between`/`over`, `x`, `expressed_as`, `spread`, `spread_source`, `origin`). Duplicate numbers printed in both text and table are recorded twice under suffixed keys so `audit.py` verifies they match.
- **`data.yaml`**: Exact cell pointers (`file`, `sheet`, `cell`, `value`, `unit`) from released author spreadsheets/CSVs/SAXS files.
- **`readings.yaml`**: Checked numeric summary/point readings derived from per-figure scripts when no printed table or raw file supplies them.

### Within-Paper Prose Audit Layer (`claims`)
`livinglit-lepidoptera` maintains **full LivingLit claim depth** strictly for **within-paper auditing** (see [03 · Audit & Formulas](03-audit-and-formulas.md) and [04 · Across Sources](04-across-sources.md)):
- **Scope of extraction**: Every assertion in the **Abstract**, each **Results section conclusion**, **Discussion conclusions**, and **assertive figure titles** — strictly **one claim per assertion** (repeated assertions link via `restates: <claim_id>`).
- **Kinds**:
  - `stated`: assertion about *this paper's own findings*. Must specify `rests_on: [item_ids]` (plus `opposes: [item_ids]` if applicable), optional `asserts_direction: up | down | none`, and a **7-dimension `judgement`** against this paper's own evidence only.
  - `attributed`: finding attributed to a cited paper (`judgement: null`, linked via `cites:`).
  - `literature`: priority or state-of-the-field claim such as *"first to show"* (`judgement: null`).
- **Epistemic boundary**: Claims are **never** inputs to cross-paper comparisons. They exist solely so a reader can check whether a paper's prose matches its own data.
