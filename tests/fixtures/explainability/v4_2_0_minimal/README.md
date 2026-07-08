# v4.2.0 Minimal Explainability Fixture

This fixture is a frozen copy of certified v4.2.0 replay artifacts used to
validate the static explainability layer without touching the runtime.

## Scope

This fixture is used by v4.3.1 explainability tests and demos.

It includes:

- `manifest.json`
- `execution_graph.json`
- `event_log.json`
- `kb_export.jsonl`
- `replay_metadata.json`

## Source

The files were copied from `tests/reference_data/v4.2.0/` without regenerating
fingerprints or modifying content.

## Rules

- Do not mutate this fixture during tests.
- Do not regenerate fingerprints automatically.
- Do not use this fixture to change replay semantics.
- Static explainability must treat these files as immutable evidence.
