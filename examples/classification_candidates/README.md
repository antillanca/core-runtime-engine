# Classification Candidate Fixtures

Synthetic examples for the CORE classification candidate contract.

## Files

| File | Purpose | Expected Validation |
|------|---------|---------------------|
| `accepted.json` | Valid accepted classification | passed |
| `clarification_required.json` | Ambiguous input needing clarification | passed |
| `rejected_low_confidence.json` | Confidence below clarify threshold | passed |
| `rejected_unsafe_pattern.json` | Safety violation forcing rejection | passed |
| `invalid_confidence_mismatch.json` | Structural invalid: confidence/decision mismatch | failed |
| `invalid_missing_vocabulary_id.json` | Structural invalid: missing vocabulary_id | failed |

## Design Rules

- All domain names, intent names and slot values are **synthetic**.
- No private business names, paths, SQL or endpoints.
- Fingerprint values use the `sha256:` prefix format.
- The `external:` prefix convention (v7.2) is used for vocabulary references
  that belong to downstream forks.

## Validation

```bash
python scripts/validate_classification_candidate.py examples/classification_candidates/
```

Individual files:

```bash
python scripts/validate_classification_candidate.py examples/classification_candidates/accepted.json
```
