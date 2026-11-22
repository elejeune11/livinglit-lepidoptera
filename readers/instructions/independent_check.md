# Independent Check — Lepidoptera

You perform an independent verification pass on a completed `records/<paper>/` folder without trusting prior summaries.

## Checklist
1. **OA & Manifest check**: Confirm `manifest.yaml` matches every file in `papers_dont_ever_commit/<paper>/` and complies with `policy.oa_only`.
2. **Visual Overlay Proof**: Open `qa_renders/bbox_<paper>.png`, `qa_renders/plots_<paper>.png`, and `qa_renders/fft_<paper>.png` and verify every single panel directly against the pixels (zero composite panels, zero 2× FFT harmonic locks, zero curve/ribbon drops).
3. **Anchor & Claim Fidelity**: Spot-check 5–10 verbatim quotes in `record.yaml` against the paper XML/PDF; verify that overstated or weakly supported claims are flagged honestly across the 7 claim dimensions.
4. **Epistemic Firewall**: Verify that `claims:` never appear in `comparisons.csv` and that every cross-paper comparison transparently reports `context_diff` (`matched`, `differing`, `confounders`).
5. **All Gates Green**: Confirm `gate record`, `gate terms`, `gate derived`, `gate panels`, and `audit` all exit `0`.
