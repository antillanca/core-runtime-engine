# CORE v4.1.0 Reference Dataset

This dataset is a minimal deterministic fixture used for replay certification.
Its KB provenance is explicit and matches the manifest fingerprint.

Contains:
- frozen KB export
- event log trace
- replay metadata
- synthetic sensor trace
- projection snapshot
- observation layer snapshot

Validated invariants:
- same content produces same fingerprints
- KB and event log hashes are stable
- observation trace remains deterministic
- projection hash remains fixed for the fixture

Regeneration:
- generated from synthetic fixture values and current CORE v4.1 runtime
- all fingerprints are canonical and reproducible
- canonical command: `python scripts/replay_certification.py --reference-dir tests/reference_data/v4.1.0/ --output report.json`
