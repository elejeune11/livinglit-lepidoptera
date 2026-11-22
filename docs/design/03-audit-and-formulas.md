# 03 · Within-Paper Audit, Formula Library & Full Claim Auditing

Within-paper auditing in `livinglit-lepidoptera` stays **100% faithful to original LivingLit**: code checks every internal numerical consistency, every mathematical derivation, and every author prose claim strictly against that paper's own evidence — with zero silent corrections.

---

## 1. Internal Numeric & Cross-Origin Reconciliation

For each evidence item, `audit.py` automatically compares all available value origins without choosing a favorite:
1. **Duplicate printed values** (e.g., Abstract vs. Results vs. Table 1 vs. figure legend): checked for numeric equality within printed rounding precision.
2. **Printed summary vs. released raw data (`data.yaml`)**: recomputes mean, median, SD, SEM, and `n` directly from raw spreadsheet/CSV cells and compares against the paper's printed values (`consistent`, `consistent within reading`, `close`, `inconsistent`, `cannot check`).
3. **Printed summary vs. digitized figure readings (`readings.yaml` / `digitized/`)**: checks that extracted points/curves/FFT measurements agree with reported text/table summaries within calibrated pixel uncertainty intervals (`[lo, hi]`).
4. **Statistical check**: when raw or individual figure points exist for a pairwise test (`compares: [condition, reference]`), recomputes test direction and summary statistics and checks consistency with printed `p` values and multiple printed `p_values` (if text and legend conflict).

### Non-Mutation Discipline (`suspect` / `suspected_error`)
- A printed number, cell, or marker that appears erroneous (swapped `n`, 10× unit slip, wrong panel cross-reference) is **never altered or deleted**.
- It is kept verbatim and annotated with `suspected_error: {what, why}` (for printed text/tables) or `suspect: {why}` (for data cells / figure readings).
- Code reports computed summaries and checks **both with and without** suspect entries so the reader sees the exact impact transparently.

---

## 2. Lepidoptera Physics & Morphometrics Formula Library (`field/formulas/` + `derived.yaml`)

Each derived quantity reported by a paper (e.g., thin-film constructive interference wavelength, multilayer Bragg reflection peak, Föppl–von Kármán buckling amplitude scaling, ridge-density ↔ ridge-spacing inversion, optical path length, or acoustic absorption peak) is checked symbolically and numerically using **SymPy**:

- **Library definitions (`field/formulas/*.yaml`)**: Canonical dimensional equations with explicit symbols, SI/nm/µm/Pa/kHz units, assumptions (e.g., chitin refractive index $n_{\text{chitin}} \approx 1.56$, air $n_{\text{air}} = 1.0$, incidence angle $\theta$), and literature citations.
- **Per-paper `derived.yaml`**: Links a paper's printed derived output to its printed or raw inputs and declares the formula used by the paper.
- **Wrong-derivation handling**: If SymPy detects that the paper's formula contradicts the library or that the printed output differs by a constant factor (e.g., diameter vs. radius or missing factor of 2 in optical path length $2 n d \cos\theta$), `audit.py` flags the derivation as `inconsistent` and retains both the printed value and the code-rebuilt value (explicitly tagged `origin: derived`).

---

## 3. Full Within-Paper Claim Auditing (`claims:`)

`livinglit-lepidoptera` implements **full LivingLit claim depth** strictly for within-paper transparency (never fed into cross-paper numerical comparisons):

### Extraction Scope
Every paper's `record.yaml` extracts every assertion from four locations:
1. **Abstract**
2. **Each Results section's concluding sentence(s)**
3. **Discussion conclusions**
4. **Assertive figure titles**

Rules:
- Strictly **one claim per assertion**; when the same assertion appears in Abstract and Discussion, both are recorded and linked via `restates: <claim_id>`.
- **Three `kind` values**:
  - `stated`: assertion about this paper's own findings (requires `rests_on`, optional `opposes`, optional `asserts_direction`, and mandatory 7-dimension `judgement`).
  - `attributed`: assertion citing prior literature (`cites: [...]`, `judgement: null`).
  - `literature`: priority/novelty claim such as *"the first demonstration that..."* (`judgement: null`).

### Seven Fixed Audit Dimensions (`DIMENSIONS`)
Every `stated` claim is judged **against this paper's own evidence only** on all 7 dimensions:

| Dimension | Question Audited |
|---|---|
| `direction` | Does the prose direction match the paper's actual numbers? |
| `support` | Do the reported statistics/values quantitatively support the assertion? |
| `comparison` | Is the appropriate control/reference group actually compared? |
| `scope` | Does the claim stay within the tested species, sex, stage, scale type, and conditions? |
| `replication` | Is biological/specimen replication (`n`) adequate and explicitly stated? |
| `strength` | Does causal/certain phrasing (*"proves"*, *"determines"*, *"causes"*) match the experimental design (correlation vs. perturbation)? |
| `presence` | Are the cited data, figures, or statistical tests actually present in the paper/supplements? |

- **Scoring**: Each dimension receives `follows`, `overstated`, `cannot judge`, or `does not follow`.
- **Computed Verdict (`claim_verdict`)**: Deterministic worst-of-7 ordering (`does not follow > overstated > cannot judge > follows`).
- **Automated Contradiction Guard (`claim_direction_flags`)**: Whenever a claim sets `asserts_direction: up | down | none`, code independently checks it against the computed direction of every item in `rests_on`. If prose asserts the opposite direction to the numbers, code raises an explicit flag beside the verdict without silently overwriting the reader's judgement.
