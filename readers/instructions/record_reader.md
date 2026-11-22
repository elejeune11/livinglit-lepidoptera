# Record Reader — Lepidoptera (`field_set: 3`)

You are reading an open-access Lepidoptera (butterfly or moth) research paper into `records/<paper>/record.yaml` following `fields/lepidoptera/field.yaml` (`field_set: 3`).

## Core Rules
1. **Quote before you state**: Every empirical `evidence` item needs a verbatim `≤30`-word `anchor: {where, quote}`. At `field_set: 3`, every stated context value (`default_context`, unit `context`, group `context`) MUST have a verbatim `context_anchors` quote where every word/number of the stated value appears in the quote (`holds(quote, value)`).
2. **Never infer unstated biology**: If sex, wing surface, pupal stage, or fixation/hydration is not explicitly stated in the paper, write `"not stated"` (or `"not applicable"` for adult dry scales when `pupal_stage_pct` does not apply).
3. **All 14 Lepidoptera context fields**:
   - `taxon`, `sex`, `anatomical_region`, `pattern_element`, `scale_type`, `functional_architecture`, `life_stage`, `pupal_stage_pct`, `target_gene`, `perturbation_modality`, `chemical_agent`, `imaging_modality`, `view_orientation`, `hydration_and_prep`.
4. **Full Within-Paper Claims Audit (7 Dimensions)**:
   - Extract all major claims from Abstract, Results conclusions, Discussion conclusions, and assertive figure titles into `claims:`.
   - Link each claim via `rests_on:` to the empirical `evidence:` IDs it draws on.
   - Judge every claim across all 7 dimensions: `direction`, `support`, `comparison`, `scope`, `replication`, `strength`, `presence` (`follows`, `overstated`, `cannot judge`, `does not follow`, `restates`, `not applicable`).
   - Remember: `claims:` stay strictly inside the within-paper `Audit` tab and NEVER enter cross-paper comparisons.
5. **Validate with deterministic gate**: Run `uv run livinglit-lep gate record <paper>` until it passes cleanly.
