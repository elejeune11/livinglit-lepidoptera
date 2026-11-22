---
name: review-comparison
description: Audit cross-paper comparisons under Shift #2 relaxed user-discretion matching, inspect context_diff confounders (e.g., tilted SEM vs planar, live vs dry), and verify no claim leaks into comparisons.
---

# `review-comparison` — Relaxed Cross-Paper Synthesis & Confounder Check

## Objective
Inspect cross-paper strata and comparison pairs in `releases/<tag>/comparisons.csv` and `strata.csv` to ensure:
1. Only empirical `evidence` items & `values` participate (strict epistemic firewall — zero `claims`).
2. Physical hard blockers (`same measure`, compatible physical units, compatible `expressed_as`) are respected.
3. Biological and methodological differences are never hidden: every compared pair carries transparent `context_diff` (`matched`, `differing`, `confounders`).
4. Physical confounders (`view_orientation` tilt foreshortening, `hydration_and_prep` live hydrated vs dry SEM shrinkage, `imaging_modality` 2D-FFT vs SAXS vs AFM) are explicitly flagged for researcher discretion.

## Steps

1. Run `uv run livinglit-lep release <tag>`.
2. Inspect `releases/<tag>/comparisons.csv` and `releases/<tag>/strata.csv`.
3. For any pair with `differing` fields in `confounder_fields` (defined in `fields/lepidoptera/field.yaml`):
   - Confirm `context_diff.confounders` lists the exact field and states of Paper A vs Paper B.
   - Verify whether a physical correction formula in `fields/lepidoptera/formulas/` applies (e.g., `tilted_sem_foreshortening.yaml` for oblique SEM views).
4. Spot-check the interactive toggles in the web UI's `Compare` tab so researchers can dynamically switch any context field between **Require match** and **Relax**.
