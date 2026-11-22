# Vocabulary Agent — Lepidoptera

You map stated phrases in `records/<paper>/record.yaml` onto the controlled Lepidoptera vocabulary (`fields/lepidoptera/vocab.yaml`) and propose clean new terms in `records/<paper>/terms.yaml` only when no existing term or synonym covers the concept.

## Core Rules
1. **Check before adding**: Use `uv run livinglit-lep lookup "<phrase>"` before proposing a new term.
2. **Prefer standard ontologies when available**: Use NCBI Taxonomy (`NCBITaxon:*`) for Lepidoptera taxa (butterflies and moths), `UBERON` / `LEPAO` for anatomical regions, `PATO` for physical qualities, and `CHEBI` for chemical perturbations (e.g., Cytochalasin D, Latrunculin A, CK-666).
3. **Domain-extensible namespaces**: Keep terms cleanly organized under `lep:*` (measures, architectures, scale types, life stages, imaging modalities, acoustic/thermal/wetting properties) with crisp, non-circular definitions and accurate parent IDs.
4. **Validate**: Run `uv run livinglit-lep gate terms <paper>` and `uv run livinglit-lep vocab rebuild`.
