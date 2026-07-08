# CORE v4.2.0 Reference Dataset

This dataset is a minimal deterministic fixture used for replay and execution
graph certification.
Its KB provenance is explicit and the runtime version recorded in the
fixture is 4.2.0.

Contains:
- frozen KB export
- event log trace
- replay metadata
- synthetic sensor trace
- projection snapshot
- observation layer snapshot
- execution graph + node fingerprints

Validated invariants:
- same content produces same fingerprints
- KB and event log hashes are stable
- observation trace remains deterministic
- projection hash remains fixed for the fixture
- execution graph fingerprints remain stable
- sensor trace is included in provenance

Regeneration:
- generated from synthetic fixture values and current CORE v4.2 runtime
- all fingerprints are canonical and reproducible
- canonical command: `python scripts/replay_certification.py --reference-dir tests/reference_data/v4.2.0/ --output report.json`
